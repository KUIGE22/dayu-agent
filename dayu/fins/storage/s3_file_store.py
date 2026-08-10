"""S3-compatible 对象存储实现（typed boto3 client）。

本模块实现既有 ``FileStore`` 协议（S14-CTRL-06）与私有 staging 能力协议：

- 六方法签名与既有 ``FileStore`` 一致；invalid key/value 抛 ``ValueError``；
  缺失对象统一抛 ``FileNotFoundError``；client/network/checksum/cleanup
  失败统一固定消息的 ``OSError``（不拼入 botocore response/request
  id/endpoint/bucket/key）；
- ``stat_object`` 只做 HEAD 验证（``dayu-sha256`` metadata + ContentLength），
  禁止下载完整对象；
- ``get_object`` 全量读入 ``SpooledTemporaryFile``（8 MiB 后落盘）并流式实算
  SHA-256，与远端 ``dayu-sha256`` 相等才返回；底层 StreamingBody 在完整读取
  后立即 close，不得泄漏；hash mismatch 抛固定消息 ``OSError`` fail closed；
- ``put_object`` 先同步把 caller stream 完整读入 ``SpooledTemporaryFile`` 并
  实算 SHA-256/size（本地读失败零远端请求）；单对象最大 5 GiB，超限在
  upload 前拒绝；
- ``list_objects`` 返回全量 ``list[FileObjectMeta]``（内部穷尽 pagination、
  按 key 升序、排除 ``.dayu-staging/``）；
- staging 能力由私有 ``_StagedFileStore`` runtime-checkable Protocol 表达，
  ``_fs_storage_infra`` 以 ``isinstance`` 判断是否启用 remote journal；
- client 固定 path-style addressing，不读取 ambient AWS profile/credential
  chain/EC2 metadata/session token；
- ``presign`` 只经 ``get_presigned_url`` 返回给显式 Fins owner caller，默认
  300 秒上限、参数必须 ``1..300``。
"""

from __future__ import annotations

import hashlib
import io
import re
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import IO, TYPE_CHECKING, BinaryIO, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from _typeshed import WriteableBuffer
import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
)

from dayu.fins.domain.document_models import FileObjectMeta

from .file_store import FileStore

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_PRINTABLE_ASCII_PATTERN = re.compile(r"^[\x20-\x7e]+$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SHA256_METADATA_KEY = "dayu-sha256"
_MAX_OBJECT_BYTES = 5 * 1024 * 1024 * 1024
_SPOOL_MAX_BYTES = 8 * 1024 * 1024
_CHUNK_BYTES = 1024 * 64
_MAX_PRESIGN_SECONDS = 300
_MIN_PRESIGN_SECONDS = 1
_STAGING_PREFIX = ".dayu-staging/"

_MISSING_CODES = frozenset({"NoSuchKey", "NoSuchBucket", "NotFound", "404"})


@runtime_checkable
class StagedFileStoreProtocol(Protocol):
    """S3 staging 能力协议（仅由 ``S3FileStore`` 实现）。

    供 ``_fs_storage_infra`` 以 ``isinstance`` 判断是否启用 remote journal。
    """

    def stage_publish(self, *, operation_id: str, data: BinaryIO) -> FileObjectMeta:
        """把字节写入 staging key 并返回其元数据。

        Args:
            operation_id: 当前 operation id（FS batch token id）。
            data: caller 二进制流。

        Returns:
            staging key 对应元数据（``uri`` 为 ``s3://{bucket}/{staging_key}``）。

        Raises:
            OSError: 写入失败时抛出。
        """

        ...

    def publish_staged(
        self,
        *,
        staging_key: str,
        final_key: str,
        content_type: Optional[str],
        metadata: dict[str, str],
    ) -> None:
        """单次 server-side CopyObject 把 staging key 发布为 final key。

        Args:
            staging_key: staging key。
            final_key: 最终 key。
            content_type: 可选内容类型。
            metadata: 随 final 对象保留的扩展元数据。

        Returns:
            无。

        Raises:
            OSError: 发布失败时抛出。
        """

        ...

    def object_uri(self, key: str) -> str:
        """构造对象 URI。

        Args:
            key: 对象 key。

        Returns:
            ``s3://{bucket}/{key}`` URI。

        Raises:
            无。
        """

        ...

    def key_from_uri(self, uri: str) -> str:
        """从对象 URI 提取 key。

        Args:
            uri: ``s3://{bucket}/{key}`` URI。

        Returns:
            key 部分。

        Raises:
            ValueError: URI 形态非法时抛出。
        """

        ...

    def delete_object_idempotent(self, key: str) -> None:
        """幂等删除对象（对象缺失视为已清理，不抛错）。

        Args:
            key: 对象 key。

        Returns:
            无。

        Raises:
            OSError: 非缺失原因删除失败时抛出。
        """

        ...


class S3FileStore(FileStore, StagedFileStoreProtocol):
    """基于 boto3 的 S3-compatible 对象存储实现。"""

    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        bucket: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        """初始化 S3 客户端（固定 path-style addressing）。

        Args:
            endpoint_url: S3 兼容服务端点 URL。
            region: 区域名。
            bucket: 目标 bucket 名。
            access_key: access key 值。
            secret_key: secret key 值。

        Returns:
            无。

        Raises:
            ValueError: 任一参数为空时抛出。
        """

        if not endpoint_url or not endpoint_url.strip():
            raise ValueError("endpoint_url 不能为空")
        if not region or not region.strip():
            raise ValueError("region 不能为空")
        if not bucket or not bucket.strip():
            raise ValueError("bucket 不能为空")
        if not access_key or not access_key.strip():
            raise ValueError("access_key 不能为空")
        if not secret_key or not secret_key.strip():
            raise ValueError("secret_key 不能为空")
        self._bucket = bucket
        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                s3={"addressing_style": "path"},
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def head_bucket(self) -> None:
        """对 bucket 执行 HEAD 探活。

        Args:
            无。

        Returns:
            无。

        Raises:
            FileNotFoundError: bucket 不存在时抛出。
            OSError: 无权限或不可达时抛出（固定消息）。
        """

        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as exc:
            if _client_error_code(exc) in _MISSING_CODES:
                raise FileNotFoundError("bucket 不存在") from exc
            raise OSError("S3 bucket 探活失败") from exc
        except (BotoCoreError, EndpointConnectionError) as exc:
            raise OSError("S3 bucket 探活失败") from exc

    def put_object(
        self,
        key: str,
        data: BinaryIO,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """写入对象内容并返回元数据。

        Args:
            key: 对象键（canonical relative POSIX key）。
            data: 二进制流。
            content_type: 可选内容类型。
            metadata: 可选扩展元数据。

        Returns:
            文件对象元数据。

        Raises:
            ValueError: key 非法、metadata 非法或与保留键冲突时抛出。
            OSError: 写入失败时抛出。
        """

        normalized_key = validate_s3_key(key)
        normalized_metadata = _normalize_metadata(metadata)
        spool, sha256, size = _drain_to_spool(data)
        if size > _MAX_OBJECT_BYTES:
            spool.close()
            raise OSError("对象超过 5 GiB 上限，拒绝上传")
        try:
            _put_object(
                self._client,
                bucket=self._bucket,
                key=normalized_key,
                body=spool,
                content_type=content_type,
                metadata={**normalized_metadata, _SHA256_METADATA_KEY: sha256},
            )
        except (ClientError, BotoCoreError, EndpointConnectionError) as exc:
            raise OSError("S3 对象写入失败") from exc
        finally:
            spool.close()
        return FileObjectMeta(
            uri=_build_uri(self._bucket, normalized_key),
            etag=sha256,
            last_modified=_iso_now(),
            size=size,
            content_type=content_type,
            sha256=sha256,
        )

    def get_object(self, key: str) -> BinaryIO:
        """读取对象内容（已验证、seekable、caller-owned 流）。

        Args:
            key: 对象键。

        Returns:
            caller-owned 的二进制流（caller 负责 close）；内容已与远端
            ``dayu-sha256`` 校验一致。

        Raises:
            FileNotFoundError: 对象不存在时抛出。
            OSError: 读取失败或 SHA-256 校验失败时抛出。
        """

        normalized_key = validate_s3_key(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=normalized_key)
        except ClientError as exc:
            if _client_error_code(exc) in _MISSING_CODES:
                raise FileNotFoundError("对象不存在") from exc
            raise OSError("S3 对象读取失败") from exc
        except (BotoCoreError, EndpointConnectionError) as exc:
            raise OSError("S3 对象读取失败") from exc
        body = response["Body"]
        remote_sha256 = _read_remote_sha256(response.get("Metadata") or {})
        spool: IO[bytes] = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_BYTES)
        sha256 = hashlib.sha256()
        try:
            while True:
                chunk = body.read(_CHUNK_BYTES)
                if not chunk:
                    break
                spool.write(chunk)
                sha256.update(chunk)
        finally:
            # 完整读取后立即关闭底层 StreamingBody，避免句柄泄漏。
            body.close()
        if remote_sha256 is None or sha256.hexdigest() != remote_sha256:
            spool.close()
            raise OSError("S3 对象内容校验失败")
        spool.seek(0)
        return io.BufferedReader(_SpooledRawReader(spool))

    def stat_object(self, key: str) -> FileObjectMeta:
        """查询对象元数据（HEAD-only，不下载对象）。

        Args:
            key: 对象键。

        Returns:
            文件对象元数据。

        Raises:
            FileNotFoundError: 对象不存在时抛出。
            OSError: 远端 metadata 非法或 HEAD 失败时抛出。
        """

        normalized_key = validate_s3_key(key)
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=normalized_key)
        except ClientError as exc:
            if _client_error_code(exc) in _MISSING_CODES:
                raise FileNotFoundError("对象不存在") from exc
            raise OSError("S3 对象查询失败") from exc
        except (BotoCoreError, EndpointConnectionError) as exc:
            raise OSError("S3 对象查询失败") from exc
        remote_sha256 = _read_remote_sha256(response.get("Metadata") or {})
        if remote_sha256 is None:
            raise OSError("S3 对象缺少校验元数据")
        content_length = int(response.get("ContentLength", 0))
        return FileObjectMeta(
            uri=_build_uri(self._bucket, normalized_key),
            etag=str(response.get("ETag") or ""),
            last_modified=_iso_from_str(response.get("LastModified")),
            size=content_length,
            content_type=response.get("ContentType"),
            sha256=remote_sha256,
        )

    def delete_object(self, key: str) -> None:
        """删除对象。

        Args:
            key: 对象键。

        Returns:
            无。

        Raises:
            FileNotFoundError: 对象不存在时抛出。
            OSError: 删除失败时抛出。
        """

        normalized_key = validate_s3_key(key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=normalized_key)
        except ClientError as exc:
            if _client_error_code(exc) in _MISSING_CODES:
                raise FileNotFoundError("对象不存在") from exc
            raise OSError("S3 对象删除失败") from exc
        except (BotoCoreError, EndpointConnectionError) as exc:
            raise OSError("S3 对象删除失败") from exc

    def delete_object_idempotent(self, key: str) -> None:
        """幂等删除对象（对象缺失视为已清理，不抛错）。

        Args:
            key: 对象键。

        Returns:
            无。

        Raises:
            OSError: 非缺失原因删除失败时抛出。
        """

        normalized_key = validate_s3_key(key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=normalized_key)
        except ClientError as exc:
            if _client_error_code(exc) not in _MISSING_CODES:
                raise OSError("S3 对象删除失败") from exc
        except (BotoCoreError, EndpointConnectionError) as exc:
            raise OSError("S3 对象删除失败") from exc

    def get_presigned_url(self, key: str, expires_in: int) -> str:
        """获取预签名 URL。

        Args:
            key: 对象键。
            expires_in: 过期秒数，必须为 ``1..300``。

        Returns:
            预签名 GET URL。

        Raises:
            ValueError: 过期秒数越界时抛出。
            OSError: 生成失败时抛出。
        """

        if expires_in < _MIN_PRESIGN_SECONDS or expires_in > _MAX_PRESIGN_SECONDS:
            raise ValueError("expires_in 必须在 1..300 秒范围内")
        normalized_key = validate_s3_key(key)
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": normalized_key},
                ExpiresIn=expires_in,
            )
        except (ClientError, BotoCoreError, EndpointConnectionError) as exc:
            raise OSError("S3 预签名 URL 生成失败") from exc

    def list_objects(self, prefix: str) -> list[FileObjectMeta]:
        """按前缀列出对象（全量、按 key 升序、排除 staging）。

        Args:
            prefix: 对象前缀。

        Returns:
            文件元数据列表。

        Raises:
            OSError: 列出失败时抛出。
        """

        normalized_prefix = prefix.strip().lstrip("/")
        results: dict[str, FileObjectMeta] = {}
        continuation_token: Optional[str] = None
        while True:
            try:
                if continuation_token is None:
                    response = self._client.list_objects_v2(
                        Bucket=self._bucket,
                        Prefix=normalized_prefix,
                    )
                else:
                    response = self._client.list_objects_v2(
                        Bucket=self._bucket,
                        Prefix=normalized_prefix,
                        ContinuationToken=continuation_token,
                    )
            except (ClientError, BotoCoreError, EndpointConnectionError) as exc:
                raise OSError("S3 对象列出失败") from exc
            for content in response.get("Contents", []):
                key = str(content.get("Key", ""))
                if key.startswith(_STAGING_PREFIX):
                    continue
                results[key] = FileObjectMeta(
                    uri=_build_uri(self._bucket, key),
                    etag=str(content.get("ETag") or ""),
                    last_modified=_iso_from_str(content.get("LastModified")),
                    size=int(content.get("Size", 0)),
                    content_type=content.get("ContentType"),
                    sha256=None,
                )
            if not bool(response.get("IsTruncated", False)):
                break
            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                break
        return [results[key] for key in sorted(results)]

    def stage_publish(self, *, operation_id: str, data: BinaryIO) -> FileObjectMeta:
        """把字节写入 staging key 并返回其元数据。

        Args:
            operation_id: 当前 operation id。
            data: caller 二进制流。

        Returns:
            staging key 对应元数据。

        Raises:
            OSError: 写入失败时抛出。
        """

        spool, sha256, size = _drain_to_spool(data)
        if size > _MAX_OBJECT_BYTES:
            spool.close()
            raise OSError("对象超过 5 GiB 上限，拒绝上传")
        staging_key = f"{_STAGING_PREFIX}{operation_id}/{sha256}"
        try:
            _put_object(
                self._client,
                bucket=self._bucket,
                key=staging_key,
                body=spool,
                content_type=None,
                metadata={_SHA256_METADATA_KEY: sha256},
            )
        except (ClientError, BotoCoreError, EndpointConnectionError) as exc:
            raise OSError("S3 对象写入失败") from exc
        finally:
            spool.close()
        return FileObjectMeta(
            uri=_build_uri(self._bucket, staging_key),
            etag=sha256,
            last_modified=_iso_now(),
            size=size,
            content_type=None,
            sha256=sha256,
        )

    def publish_staged(
        self,
        *,
        staging_key: str,
        final_key: str,
        content_type: Optional[str],
        metadata: dict[str, str],
    ) -> None:
        """单次 server-side CopyObject 发布 final key。

        SHA-256 真源为 staging 对象的真实 ``dayu-sha256`` metadata（HEAD
        读取），禁止由 key 字符串推导或信任 caller 传入的任意 staging_key
        末段：staging 对象缺失/无校验元数据 => fail closed。

        Args:
            staging_key: staging key。
            final_key: 最终 key。
            content_type: 可选内容类型。
            metadata: 随 final 对象保留的扩展元数据。

        Returns:
            无。

        Raises:
            FileNotFoundError: staging 对象不存在时抛出。
            OSError: staging 查询失败、缺少校验元数据或发布失败时抛出。
        """

        normalized_staging = validate_s3_key(staging_key)
        normalized_final = validate_s3_key(final_key)
        staged_sha256 = self._head_staging_sha256(normalized_staging)
        try:
            _copy_object(
                self._client,
                bucket=self._bucket,
                source_bucket=self._bucket,
                source_key=normalized_staging,
                key=normalized_final,
                metadata={**metadata, _SHA256_METADATA_KEY: staged_sha256},
                content_type=content_type,
            )
        except (ClientError, BotoCoreError, EndpointConnectionError) as exc:
            raise OSError("S3 对象发布失败") from exc

    def _head_staging_sha256(self, staging_key: str) -> str:
        """HEAD staging 对象并返回其真实 dayu-sha256。

        Args:
            staging_key: staging key。

        Returns:
            staging 对象的真实 SHA-256。

        Raises:
            FileNotFoundError: staging 对象不存在时抛出。
            OSError: HEAD 失败或缺少合法校验元数据时抛出。
        """

        try:
            response = self._client.head_object(Bucket=self._bucket, Key=staging_key)
        except ClientError as exc:
            if _client_error_code(exc) in _MISSING_CODES:
                raise FileNotFoundError("staging 对象不存在") from exc
            raise OSError("S3 staging 对象查询失败") from exc
        except (BotoCoreError, EndpointConnectionError) as exc:
            raise OSError("S3 staging 对象查询失败") from exc
        remote_sha256 = _read_remote_sha256(response.get("Metadata") or {})
        if remote_sha256 is None:
            raise OSError("S3 staging 对象缺少校验元数据")
        return remote_sha256

    def object_uri(self, key: str) -> str:
        """构造对象 URI。

        Args:
            key: 对象 key。

        Returns:
            ``s3://{bucket}/{key}`` URI。

        Raises:
            无。
        """

        return _build_uri(self._bucket, key)

    def key_from_uri(self, uri: str) -> str:
        """从对象 URI 提取 key。

        Args:
            uri: ``s3://{bucket}/{key}`` URI。

        Returns:
            key 部分。

        Raises:
            ValueError: URI 形态非法时抛出。
        """

        return _key_from_uri(uri)

    def close(self) -> None:
        """关闭底层 S3 client（幂等）。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._client.close()


def validate_s3_key(key: str) -> str:
    """校验 canonical relative POSIX key。

    Args:
        key: 待校验对象键。

    Returns:
        规范化后的 key。

    Raises:
        ValueError: key 为空、含 leading/trailing slash、空 segment、
            ``.``/``..``、反斜线或控制字符时抛出。
    """

    raw = str(key).strip()
    if not raw:
        raise ValueError("key 不能为空")
    if raw.startswith("/") or raw.endswith("/"):
        raise ValueError("key 不得以斜杠开头或结尾")
    if "\\" in raw:
        raise ValueError("key 不得包含反斜线")
    for segment in raw.split("/"):
        if not segment:
            raise ValueError("key 不得包含空 segment")
        if segment in {".", ".."}:
            raise ValueError("key 不得包含 . 或 .. segment")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in segment):
            raise ValueError("key 不得包含控制字符")
    return raw


def _client_error_code(exc: ClientError) -> str:
    """提取 ClientError 的错误码。

    Args:
        exc: botocore ClientError。

    Returns:
        错误码字符串；无法提取时返回空字符串。

    Raises:
        无。
    """

    error = exc.response.get("Error", {})
    if not isinstance(error, dict):
        return ""
    code = error.get("Code")
    if isinstance(code, str):
        return code
    return ""


def _normalize_metadata(metadata: Optional[dict[str, str]]) -> dict[str, str]:
    """校验并规范化 caller 扩展元数据。

    Args:
        metadata: 可选扩展元数据。

    Returns:
        规范化后的元数据字典。

    Raises:
        ValueError: 含保留键、空键/值或非可打印 ASCII 字符时抛出。
    """

    if metadata is None:
        return {}
    normalized: dict[str, str] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("metadata 必须为 dict[str, str]")
        if not key or not key.strip():
            raise ValueError("metadata key 不能为空")
        if _PRINTABLE_ASCII_PATTERN.fullmatch(key) is None:
            raise ValueError("metadata key 必须为可打印 ASCII")
        if not value or not value.strip():
            raise ValueError("metadata value 不能为空")
        if _PRINTABLE_ASCII_PATTERN.fullmatch(value) is None:
            raise ValueError("metadata value 必须为可打印 ASCII")
        if key == _SHA256_METADATA_KEY:
            raise ValueError("dayu-sha256 为保留 metadata 键，禁止 caller 使用")
        normalized[key] = value
    return normalized


class _SpooledRawReader(io.RawIOBase):
    """caller-owned、只读、seekable 的 spooled 原始二进制流 adapter。

    私有 ``io.RawIOBase`` 子类，把 ``readinto``/``seek``/``tell``/``close``
    委托给已填充并 seek(0) 的 ``SpooledTemporaryFile``（8 MiB 后自动落系统
    temp）。``get_object`` 以 ``io.BufferedReader`` 包装本 adapter 返回，使
    返回值满足 ``BinaryIO`` 注解（S14-CTRL-06：caller-owned、可 seek、可顺序
    重读、SHA 已验证），且无需任何类型逃逸；写入在
    ``_drain_to_spool``/``get_object`` 内部以 ``IO[bytes]`` 完成，adapter 只读。
    """

    def __init__(self, spool: IO[bytes]) -> None:
        """持有已填充的底层 spool。

        Args:
            spool: 已填充并 seek(0) 的 spooled 临时文件。

        Returns:
            无。

        Raises:
            无。
        """

        self._spool = spool

    def readinto(self, buffer: WriteableBuffer) -> int:
        """读取字节到 caller 提供的缓冲区。

        Args:
            buffer: 目标缓冲区。

        Returns:
            实际读取字节数；EOF 时返回 0。

        Raises:
            OSError: 读取失败或底层已关闭时抛出。
        """

        if self.closed:
            raise OSError("已关闭的流不可读")
        view = memoryview(buffer)
        data = self._spool.read(len(view))
        if data is None:
            raise OSError("spool 读取失败")
        view[:len(data)] = data
        return len(data)

    def seek(self, offset: int, whence: int = 0) -> int:
        """移动读写偏移。

        Args:
            offset: 偏移量。
            whence: 起点（0=文件头，1=当前位置，2=文件尾）。

        Returns:
            新偏移位置。

        Raises:
            OSError: 定位失败时抛出。
        """

        return self._spool.seek(offset, whence)

    def tell(self) -> int:
        """返回当前读写偏移。

        Args:
            无。

        Returns:
            当前偏移。

        Raises:
            OSError: 查询失败时抛出。
        """

        return self._spool.tell()

    def close(self) -> None:
        """关闭并释放底层 spool（幂等）。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        if self.closed:
            return
        try:
            self._spool.close()
        finally:
            super().close()

    def readable(self) -> bool:
        """是否可读。"""

        return not self.closed

    def seekable(self) -> bool:
        """是否可 seek。"""

        return not self.closed


def _drain_to_spool(data: BinaryIO) -> tuple[IO[bytes], str, int]:
    """把 caller 流完整读入 spool 并实算 SHA-256/size。

    Args:
        data: caller 二进制流。

    Returns:
        ``(spool, sha256_hex, size)`` 三元组；spool 已 seek(0)。

    Raises:
        OSError: 本地读取失败时抛出（零远端请求）。
    """

    spool: IO[bytes] = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_BYTES)
    sha256 = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = data.read(_CHUNK_BYTES)
            if not chunk:
                break
            spool.write(chunk)
            sha256.update(chunk)
            size += len(chunk)
    except Exception as exc:
        spool.close()
        raise OSError("本地数据读取失败") from exc
    spool.seek(0)
    return spool, sha256.hexdigest(), size


def _put_object(
    client: S3Client,
    *,
    bucket: str,
    key: str,
    body: IO[bytes],
    content_type: Optional[str],
    metadata: dict[str, str],
) -> None:
    """按 content type 是否存在分支调用 put_object。

    Args:
        client: S3 client。
        bucket: bucket 名。
        key: 对象 key。
        body: 请求体。
        content_type: 可选内容类型。
        metadata: 完整 metadata（含保留 sha256 键）。

    Returns:
        无。

    Raises:
        ClientError/BotoCoreError/EndpointConnectionError: 底层 S3 失败时抛出。
    """

    if content_type and content_type.strip():
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type.strip(),
            Metadata=metadata,
        )
        return
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        Metadata=metadata,
    )


def _copy_object(
    client: S3Client,
    *,
    bucket: str,
    source_bucket: str,
    source_key: str,
    key: str,
    metadata: dict[str, str],
    content_type: Optional[str],
) -> None:
    """按 content type 是否存在分支调用 copy_object。

    Args:
        client: S3 client。
        bucket: bucket 名。
        source_bucket: copy source bucket。
        source_key: copy source key。
        key: 目标对象 key。
        metadata: 完整 metadata（含保留 sha256 键）。
        content_type: 可选内容类型。

    Returns:
        无。

    Raises:
        ClientError/BotoCoreError/EndpointConnectionError: 底层 S3 失败时抛出。
    """

    if content_type and content_type.strip():
        client.copy_object(
            Bucket=bucket,
            Key=key,
            CopySource={"Bucket": source_bucket, "Key": source_key},
            Metadata=metadata,
            MetadataDirective="REPLACE",
            ContentType=content_type.strip(),
        )
        return
    client.copy_object(
        Bucket=bucket,
        Key=key,
        CopySource={"Bucket": source_bucket, "Key": source_key},
        Metadata=metadata,
        MetadataDirective="REPLACE",
    )


def _read_remote_sha256(metadata: Mapping[str, str]) -> Optional[str]:
    """从远端 metadata 读取并校验 ``dayu-sha256``。

    Args:
        metadata: 远端 metadata 字典。

    Returns:
        小写 64-hex SHA-256；缺失或形态非法时返回 ``None``。

    Raises:
        无。
    """

    value = metadata.get(_SHA256_METADATA_KEY)
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if _SHA256_PATTERN.fullmatch(normalized) is None:
        return None
    return normalized


def _build_uri(bucket: str, key: str) -> str:
    """构造对象 URI。

    Args:
        bucket: bucket 名。
        key: 对象 key。

    Returns:
        ``s3://{bucket}/{key}`` URI。

    Raises:
        无。
    """

    return f"s3://{bucket}/{key}"


def _key_from_uri(uri: str) -> str:
    """从对象 URI 提取 key。

    Args:
        uri: ``s3://{bucket}/{key}`` URI。

    Returns:
        key 部分。

    Raises:
        ValueError: URI 形态非法时抛出。
    """

    raw = str(uri or "").strip()
    if not raw.startswith("s3://"):
        raise ValueError(f"不支持的 URI scheme: {raw}")
    key = raw.split("s3://", 1)[1].split("/", 1)[-1]
    if not key:
        raise ValueError("S3 URI 缺少 key")
    return key


def _iso_now() -> str:
    """获取当前 UTC ISO8601 时间。

    Args:
        无。

    Returns:
        ISO8601 字符串。

    Raises:
        无。
    """

    return datetime.now(UTC).isoformat()


def _iso_from_str(value: datetime | None) -> Optional[str]:
    """把 datetime 值格式化为 ISO8601 字符串。

    Args:
        value: 远端返回的 datetime 或 ``None``。

    Returns:
        ISO8601 字符串；非 datetime 时返回 ``None``。

    Raises:
        无。
    """

    if isinstance(value, datetime):
        return value.isoformat()
    return None
