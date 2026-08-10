"""S3FileStore 单元测试（narrow typed fake client）。

覆盖 S14-CTRL-06 的 concrete adapter 契约：staging publish 的 SHA 真源、
get_object 校验、stat HEAD-only、pagination/排序/staging 排除、presign 边界，
以及 stage_publish -> publish_staged 的回归（SHA 必须来自 staging 对象真实
metadata，禁止 key 推导）。

禁止使用类型逃逸手段（详见项目 AGENTS.md 约束）：fake
client 使用 TypedDict 收窄响应类型；client 注入经 ``monkeypatch`` 替换
``boto3.client`` 工厂实现（构造时赋值，无手动赋值与类型注释逃逸）。
"""

from __future__ import annotations

import hashlib
import io
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, TypedDict

import pytest
from botocore.exceptions import ClientError

from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.storage._fs_storage_core import FsStorageCore
from dayu.fins.storage.s3_file_store import S3FileStore, validate_s3_key


class _FakeObjectRecord(TypedDict):
    """fake 存储中的对象记录。"""

    Metadata: dict[str, str]
    Body: bytes


class _HeadObjectResponse(TypedDict):
    """head_object 响应。"""

    Metadata: dict[str, str]


class _GetObjectResponse(TypedDict):
    """get_object 响应。"""

    Body: BinaryIO
    Metadata: dict[str, str]


class _ListContentsItem(TypedDict):
    """list_objects_v2 的单条对象摘要。"""

    Key: str
    Size: int
    ETag: str
    Metadata: dict[str, str]


class _ListObjectsV2Response(TypedDict, total=False):
    """list_objects_v2 响应。"""

    Contents: list[_ListContentsItem]
    IsTruncated: bool
    NextContinuationToken: str


class _FakeClientError(ClientError):
    """模拟 botocore ClientError（继承真实 ClientError 以便生产 except 捕获）。

    Args:
        code: 错误码。

    Returns:
        无。

    Raises:
        无。
    """

    def __init__(self, code: str) -> None:
        """构造带响应字典的异常。"""

        super().__init__(
            error_response={
                "Error": {"Code": code, "Message": code},
                "ResponseMetadata": {
                    "RequestId": "fake-request",
                    "HostId": "fake-host",
                    "HTTPStatusCode": 404,
                    "HTTPHeaders": {},
                    "RetryAttempts": 0,
                },
            },
            operation_name="fake",
        )


class _FakeS3Client:
    """覆盖 S3FileStore 使用的 boto3 client 表面（typed fake）。"""

    _PAGE_SIZE = 2

    def __init__(self) -> None:
        self.objects: dict[str, _FakeObjectRecord] = {}
        self.head_calls: list[str] = []
        self.put_calls: list[str] = []
        self.copy_calls: list[tuple[str, str, dict[str, str]]] = []
        self.delete_calls: list[str] = []
        self.list_calls: list[str] = []
        self._list_cursor = 0
        self.closed = False
        self.fail_put_code: str | None = None
        self.fail_head_code: str | None = None
        self.fail_get_code: str | None = None
        self.fail_delete_code: str | None = None
        self.fail_list_code: str | None = None

    def _missing_error(self, code: str = "NoSuchKey") -> _FakeClientError:
        """构造带 response 的缺失异常。

        Args:
            code: 错误码。

        Returns:
            模拟 ClientError（含 ``.response``）。

        Raises:
            无。
        """

        return _FakeClientError(code)

    def head_bucket(self, *, Bucket: str) -> None:
        """HEAD bucket 探活。"""

        del Bucket

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: BinaryIO,
        Metadata: dict[str, str] | None = None,
        ContentType: str | None = None,
    ) -> dict[str, str]:
        """写入对象。"""

        del Bucket, ContentType
        self.put_calls.append(Key)
        if self.fail_put_code is not None:
            raise self._missing_error(self.fail_put_code)
        content = Body.read() if Body is not None else b""
        self.objects[Key] = {"Metadata": dict(Metadata or {}), "Body": content}
        return {}

    def head_object(self, *, Bucket: str, Key: str) -> _HeadObjectResponse:
        """HEAD 对象。"""

        del Bucket
        self.head_calls.append(Key)
        if self.fail_head_code is not None:
            raise self._missing_error(self.fail_head_code)
        if Key not in self.objects:
            raise self._missing_error("NoSuchKey")
        return {"Metadata": dict(self.objects[Key]["Metadata"])}

    def copy_object(
        self,
        *,
        Bucket: str,
        Key: str,
        CopySource: dict[str, str],
        Metadata: dict[str, str],
        MetadataDirective: str,
        ContentType: str | None = None,
    ) -> dict[str, str]:
        """CopyObject。"""

        del Bucket, MetadataDirective, ContentType
        source_key = str(CopySource["Key"])
        self.copy_calls.append((source_key, Key, dict(Metadata)))
        if source_key not in self.objects:
            raise self._missing_error("NoSuchKey")
        self.objects[Key] = {"Metadata": dict(Metadata), "Body": self.objects[source_key]["Body"]}
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> _GetObjectResponse:
        """GET 对象。"""

        del Bucket
        if self.fail_get_code is not None:
            raise self._missing_error(self.fail_get_code)
        if Key not in self.objects:
            raise self._missing_error("NoSuchKey")
        record = self.objects[Key]
        return {
            "Body": BytesIO(record["Body"]),
            "Metadata": dict(record["Metadata"]),
        }

    def delete_object(self, *, Bucket: str, Key: str) -> dict[str, str]:
        """删除对象。"""

        del Bucket
        self.delete_calls.append(Key)
        if self.fail_delete_code is not None:
            raise self._missing_error(self.fail_delete_code)
        self.objects.pop(Key, None)
        return {}

    def list_objects_v2(
        self,
        *,
        Bucket: str,
        Prefix: str,
        ContinuationToken: str | None = None,
    ) -> _ListObjectsV2Response:
        """列出对象（每页 2 条，token 推进游标）。

        Args:
            Bucket: bucket。
            Prefix: 前缀。
            ContinuationToken: 分页 token（None 表示第一页）。

        Returns:
            分页响应。

        Raises:
            无。
        """

        del Bucket
        self.list_calls.append(Prefix)
        if self.fail_list_code is not None:
            raise self._missing_error(self.fail_list_code)
        if ContinuationToken is None:
            self._list_cursor = 0
        keys = sorted(key for key in self.objects if key.startswith(Prefix))
        page = keys[self._list_cursor:self._list_cursor + _FakeS3Client._PAGE_SIZE]
        self._list_cursor += len(page)
        truncated = self._list_cursor < len(keys)
        response: _ListObjectsV2Response = {
            "Contents": [
                {
                    "Key": key,
                    "Size": 0,
                    "ETag": "",
                    "Metadata": dict(self.objects[key]["Metadata"]),
                }
                for key in page
            ],
            "IsTruncated": truncated,
        }
        if truncated:
            response["NextContinuationToken"] = "next"
        return response

    def generate_presigned_url(self, ClientMethod: str, Params: dict[str, str], ExpiresIn: int) -> str:
        """生成预签名 URL。"""

        del ClientMethod, Params, ExpiresIn
        return "https://presigned.example/presigned"

    def close(self) -> None:
        """关闭 client。"""

        self.closed = True


def _build_store(monkeypatch: pytest.MonkeyPatch, fake: _FakeS3Client) -> S3FileStore:
    """构造注入 fake client 的 S3FileStore（经 boto3.client 工厂替换）。"""

    monkeypatch.setattr(
        "dayu.fins.storage.s3_file_store.boto3.client",
        lambda *args, **kwargs: fake,
    )
    return S3FileStore(
        endpoint_url="https://s3.example.com",
        region="us-east-1",
        bucket="test-bucket",
        access_key="AKIAFAKE",
        secret_key="fake-secret",
    )


def _sha256_of(data: bytes) -> str:
    """计算内容 SHA-256。

    Args:
        data: 字节内容。

    Returns:
        SHA-256 hex。

    Raises:
        无。
    """

    return hashlib.sha256(data).hexdigest()


# ---------- spooled file 契约 ----------


def test_spooled_file_rollover_seek_read_close_ownership() -> None:
    """私有 RawIO adapter + BufferedReader：8 MiB 后落盘、可 seek/重读、close 幂等。

    验证 ``get_object`` 返回流满足 caller-owned、seekable、可顺序重读语义，
    且超过 8 MiB 后仍可完整写入与重读（内部 rollover 到系统 temp）。
    """

    import tempfile
    from typing import IO

    from dayu.fins.storage.s3_file_store import _SpooledRawReader

    spool: IO[bytes] = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    chunk = b"x" * (8 * 1024 * 1024)
    spool.write(chunk)
    spool.write(b"tail")
    spool.seek(0)
    stream = io.BufferedReader(_SpooledRawReader(spool))
    try:
        assert stream.readable() is True
        assert stream.seekable() is True
        assert stream.read(len(chunk)) == chunk
        assert stream.read() == b"tail"
        stream.seek(0)
        assert stream.read() == chunk + b"tail"
    finally:
        stream.close()
        stream.close()


def test_drain_to_spool_returns_verified_stream() -> None:
    """_drain_to_spool 实算 SHA/size 并返回可重读流。"""

    from dayu.fins.storage.s3_file_store import _drain_to_spool

    content = b"some binary payload"
    spool, sha256, size = _drain_to_spool(BytesIO(content))
    try:
        assert size == len(content)
        assert sha256 == _sha256_of(content)
        assert spool.read() == content
    finally:
        spool.close()


# ---------- stage_publish -> publish_staged 回归 ----------


def test_publish_staged_uses_real_staging_metadata_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """publish_staged 必须使用 staging 对象真实 dayu-sha256（HEAD 读取）。

    回归：不得由 staging key 字符串推导（旧实现 ``_sha256_from_key`` 还因
    前缀 ``.dayu-staging/`` 与 ``dayu-staging`` 不匹配而必然 ValueError）。
    """

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    content = b"%PDF-1.7 fake content"
    real_sha = _sha256_of(content)

    store.stage_publish(operation_id="op123", data=BytesIO(content))

    store.publish_staged(
        staging_key=".dayu-staging/op123/" + real_sha,
        final_key="AAPL/filings/fil_1/primary.pdf",
        content_type="application/pdf",
        metadata={"source": "original"},
    )

    assert fake.copy_calls, "publish_staged 未触发 copy"
    _, final_key, metadata = fake.copy_calls[-1]
    assert final_key == "AAPL/filings/fil_1/primary.pdf"
    assert metadata["dayu-sha256"] == real_sha
    assert metadata["source"] == "original"


def test_publish_staged_rejects_missing_staging_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """staging 对象缺失 => FileNotFoundError，fail closed。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)

    with pytest.raises(FileNotFoundError):
        store.publish_staged(
            staging_key=".dayu-staging/op1/" + ("b" * 64),
            final_key="AAPL/filings/fil_1/primary.pdf",
            content_type=None,
            metadata={},
        )
    assert fake.copy_calls == []


def test_publish_staged_rejects_missing_sha_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """staging 对象缺 dayu-sha256 metadata => OSError，fail closed。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    fake.objects[".dayu-staging/op2/" + ("c" * 64)] = {"Metadata": {}, "Body": b""}

    with pytest.raises(OSError):
        store.publish_staged(
            staging_key=".dayu-staging/op2/" + ("c" * 64),
            final_key="AAPL/filings/fil_2/primary.pdf",
            content_type=None,
            metadata={},
        )
    assert fake.copy_calls == []


def test_stage_publish_writes_sha_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stage_publish 必须把内容 SHA-256 写入 staging metadata。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    content = b"some bytes"
    real_sha = _sha256_of(content)

    staged_meta = store.stage_publish(operation_id="op3", data=BytesIO(content))

    assert staged_meta.sha256 == real_sha
    assert staged_meta.uri == f"s3://test-bucket/.dayu-staging/op3/{real_sha}"


# ---------- get_object / stat_object 契约 ----------


def test_get_object_returns_verified_seekable_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_object 全量读入并校验 SHA，返回 seekable、caller-owned 流。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    content = b"verified content"
    sha = _sha256_of(content)
    fake.objects["AAPL/filings/fil_1/primary.pdf"] = {
        "Metadata": {"dayu-sha256": sha},
        "Body": content,
    }

    stream = store.get_object("AAPL/filings/fil_1/primary.pdf")
    try:
        assert stream.read() == content
        stream.seek(0)
        assert stream.read() == content
    finally:
        stream.close()


def test_get_object_rejects_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """远端 dayu-sha256 与内容不符 => OSError fail closed。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    fake.objects["AAPL/filings/fil_1/primary.pdf"] = {
        "Metadata": {"dayu-sha256": "0" * 64},
        "Body": b"different content",
    }

    with pytest.raises(OSError):
        store.get_object("AAPL/filings/fil_1/primary.pdf")


def test_stat_object_is_head_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stat_object 只做 HEAD，不下载对象（fake 证明零 GET）。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    sha = "d" * 64
    fake.objects["AAPL/filings/fil_1/primary.pdf"] = {
        "Metadata": {"dayu-sha256": sha},
        "Body": b"",
    }

    meta = store.stat_object("AAPL/filings/fil_1/primary.pdf")

    assert meta.sha256 == sha
    assert fake.head_calls == ["AAPL/filings/fil_1/primary.pdf"]
    assert fake.copy_calls == []
    assert fake.put_calls == []


# ---------- list / delete / presign ----------


def test_list_objects_paginates_sorts_excludes_staging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """list_objects 内部穷尽 pagination、按 key 升序、排除 staging。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    for key in (
        "AAPL/filings/b/one.pdf",
        "AAPL/filings/a/two.pdf",
        ".dayu-staging/op1/aaa",
        "AAPL/filings/c/three.pdf",
    ):
        fake.objects[key] = {"Metadata": {"dayu-sha256": "e" * 64}, "Body": b""}

    metas = store.list_objects("AAPL/filings/")

    assert [meta.uri for meta in metas] == [
        "s3://test-bucket/AAPL/filings/a/two.pdf",
        "s3://test-bucket/AAPL/filings/b/one.pdf",
        "s3://test-bucket/AAPL/filings/c/three.pdf",
    ]
    assert fake.list_calls == ["AAPL/filings/"] * 2


def test_delete_object_idempotent_missing_is_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """delete_object_idempotent 对缺失 key 视为已清理，不抛错。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)

    store.delete_object_idempotent("AAPL/filings/missing.pdf")

    assert fake.delete_calls == ["AAPL/filings/missing.pdf"]


def test_presigned_url_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """presign expires_in 必须为 1..300。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)

    with pytest.raises(ValueError):
        store.get_presigned_url("AAPL/filings/x.pdf", expires_in=0)
    with pytest.raises(ValueError):
        store.get_presigned_url("AAPL/filings/x.pdf", expires_in=301)
    url = store.get_presigned_url("AAPL/filings/x.pdf", expires_in=300)
    assert url.startswith("https://")


# ---------- key validator ----------


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/leading",
        "trailing/",
        "a//b",
        "a/./b",
        "a/../b",
        "a\\b",
        "a/\x00b",
    ],
)
def test_validate_s3_key_rejects_invalid(key: str) -> None:
    """非法 key 一律 ValueError。"""

    with pytest.raises(ValueError):
        validate_s3_key(key)


def test_validate_s3_key_accepts_canonical() -> None:
    """canonical relative POSIX key 通过。"""

    assert validate_s3_key("AAPL/filings/fil_1/primary.pdf") == "AAPL/filings/fil_1/primary.pdf"


# ---------- 校验与错误契约分支（S14-CTRL-06） ----------


def test_s3_file_store_init_rejects_empty_args() -> None:
    """构造参数任一为空 => ValueError。"""

    base = dict(
        endpoint_url="https://s3.example.com",
        region="us-east-1",
        bucket="test-bucket",
        access_key="AKIAFAKE",
        secret_key="fake-secret",
    )
    for field in ("endpoint_url", "region", "bucket", "access_key", "secret_key"):
        kwargs = dict(base)
        kwargs[field] = ""
        with pytest.raises(ValueError):
            S3FileStore(**kwargs)


def test_s3_file_store_close_closes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """``close()`` 关闭底层 boto3 client。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    store.close()
    assert fake.closed is True


def test_put_object_rejects_oversize(monkeypatch: pytest.MonkeyPatch) -> None:
    """put_object 超过 5 GiB 上限 => OSError（不发起远端请求）。"""

    import dayu.fins.storage.s3_file_store as store_module

    monkeypatch.setattr(store_module, "_MAX_OBJECT_BYTES", 4)
    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    with pytest.raises(OSError, match="5 GiB"):
        store.put_object("AAPL/a.bin", BytesIO(b"12345"))
    assert fake.put_calls == []


def test_stage_publish_rejects_oversize(monkeypatch: pytest.MonkeyPatch) -> None:
    """stage_publish 超过 5 GiB 上限 => OSError。"""

    import dayu.fins.storage.s3_file_store as store_module

    monkeypatch.setattr(store_module, "_MAX_OBJECT_BYTES", 4)
    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    with pytest.raises(OSError, match="5 GiB"):
        store.stage_publish(operation_id="op", data=BytesIO(b"12345"))
    assert fake.put_calls == []


def test_put_object_client_error_maps_to_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """put_object 抛 ClientError => 固定消息 OSError。"""

    fake = _FakeS3Client()
    fake.fail_put_code = "InternalError"
    store = _build_store(monkeypatch, fake)
    with pytest.raises(OSError, match="S3 对象写入失败"):
        store.put_object("AAPL/a.bin", BytesIO(b"x"))


def test_get_object_missing_raises_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_object 缺失 => FileNotFoundError。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    with pytest.raises(FileNotFoundError, match="对象不存在"):
        store.get_object("AAPL/missing.pdf")


def test_get_object_other_error_maps_to_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_object 非缺失 ClientError => OSError。"""

    fake = _FakeS3Client()
    fake.fail_get_code = "InternalError"
    store = _build_store(monkeypatch, fake)
    with pytest.raises(OSError, match="S3 对象读取失败"):
        store.get_object("AAPL/a.pdf")


def test_stat_object_missing_sha_metadata_raises_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stat_object 远端缺 ``dayu-sha256`` metadata => OSError。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    store.put_object("AAPL/a.pdf", BytesIO(b"x"))
    fake.objects["AAPL/a.pdf"] = {"Metadata": {"source": "original"}, "Body": b"x"}
    with pytest.raises(OSError, match="缺少校验元数据"):
        store.stat_object("AAPL/a.pdf")


def test_stat_object_other_error_maps_to_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """stat_object 非缺失 ClientError => OSError。"""

    fake = _FakeS3Client()
    fake.fail_head_code = "InternalError"
    store = _build_store(monkeypatch, fake)
    with pytest.raises(OSError, match="S3 对象查询失败"):
        store.stat_object("AAPL/a.pdf")


def test_delete_object_other_error_maps_to_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """delete_object 非缺失 ClientError => OSError。"""

    fake = _FakeS3Client()
    fake.fail_delete_code = "InternalError"
    store = _build_store(monkeypatch, fake)
    with pytest.raises(OSError, match="S3 对象删除失败"):
        store.delete_object("AAPL/a.pdf")


def test_delete_object_idempotent_swallows_missing_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """delete_object_idempotent 缺失（NoSuchKey）视为幂等 cleaned，不抛错。"""

    fake = _FakeS3Client()
    fake.fail_delete_code = "NoSuchKey"
    store = _build_store(monkeypatch, fake)
    store.delete_object_idempotent("AAPL/a.pdf")


def test_list_objects_client_error_maps_to_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """list_objects 抛 ClientError => OSError。"""

    fake = _FakeS3Client()
    fake.fail_list_code = "InternalError"
    store = _build_store(monkeypatch, fake)
    with pytest.raises(OSError, match="S3 对象列出失败"):
        store.list_objects("AAPL/")


def test_put_object_rejects_invalid_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """put_object metadata 非法（非 str 值/空 key/保留键/非打印）=> ValueError。"""

    fake = _FakeS3Client()
    store = _build_store(monkeypatch, fake)
    with pytest.raises(ValueError, match="metadata key 不能为空"):
        store.put_object("AAPL/a.pdf", BytesIO(b"x"), metadata={"": "v"})
    with pytest.raises(ValueError, match="dayu-sha256 为保留"):
        store.put_object(
            "AAPL/a.pdf",
            BytesIO(b"x"),
            metadata={"dayu-sha256": "0" * 64},
        )
    with pytest.raises(ValueError, match="可打印 ASCII"):
        store.put_object("AAPL/a.pdf", BytesIO(b"x"), metadata={"bad\x01": "v"})


def test_client_error_code_extraction() -> None:
    """``_client_error_code`` 提取 ClientError 的错误码。"""

    from dayu.fins.storage.s3_file_store import _client_error_code

    err = _FakeClientError("NoSuchKey")
    assert _client_error_code(err) == "NoSuchKey"


# ---------- core S3 模式 blob 访问（S14-CTRL-03 byte-path matrix） ----------


def _build_staged_core(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake: _FakeS3Client,
) -> FsStorageCore:
    """构造注入 fake-client S3FileStore 的 core。"""

    store = _build_store(monkeypatch, fake)
    return build_fs_repository_set(workspace_root=tmp_path, file_store=store).core


def test_core_s3_list_and_read_file_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """S3 模式 ``list_entries``/``read_file_bytes`` 经 FileStore 访问。"""

    from dayu.fins.domain.document_models import SourceHandle

    fake = _FakeS3Client()
    core = _build_staged_core(monkeypatch, tmp_path, fake)
    handle = SourceHandle(ticker="AAPL", document_id="fil_1", source_kind="filing")
    token = core.begin_batch("AAPL")
    core.store_file(handle, "a.pdf", BytesIO(b"%PDF-1.7"))
    core.commit_batch(token)

    entries = core.list_entries(handle)
    assert [entry.name for entry in entries] == ["a.pdf"]
    assert core.read_file_bytes(handle, "a.pdf") == b"%PDF-1.7"
    with pytest.raises(FileNotFoundError):
        core.read_file_bytes(handle, "missing.pdf")

    material = SourceHandle(ticker="AAPL", document_id="m1", source_kind="material")
    token = core.begin_batch("AAPL")
    core.store_file(material, "note.pdf", BytesIO(b"m"))
    core.commit_batch(token)
    material_entries = core.list_entries(material)
    assert [entry.name for entry in material_entries] == ["note.pdf"]
    assert core.read_file_bytes(material, "note.pdf") == b"m"
