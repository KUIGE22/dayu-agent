"""提供 write artifact 模块共享的叶子辅助函数。

本模块只依赖 Python 标准库和配置 JSON 契约，集中实现已经由源码审计确认
语义等价的 canonical JSON、指纹、校验、时间、路径、序列化与 Base64 操作。
业务校验、事务标识和持久化策略仍由各 write model 服务自行负责。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeAlias

from dayu.contracts.model_config import ModelConfigJsonValue

JsonObject: TypeAlias = Mapping[str, ModelConfigJsonValue]

_FILE_READ_CHUNK_BYTES = 1024 * 1024
_SHA256_PREFIX = "sha256:"
_SHA256_HEX_LENGTH = 64
_SHA256_HEX_CHARACTERS = frozenset("0123456789abcdef")


def canonical_json_str(value: ModelConfigJsonValue) -> str:
    """把 JSON 值编码为确定性的紧凑 JSON 文本。

    Args:
        value: 待编码的 JSON 值。

    Returns:
        使用固定键顺序和紧凑分隔符的 JSON 文本。

    Raises:
        ValueError: 当值包含 NaN 或无穷大时抛出。
        TypeError: 当运行时值不能被 JSON 编码时抛出。
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_json_bytes(payload: JsonObject) -> bytes:
    """把 JSON 对象编码为确定性的 UTF-8 字节。

    Args:
        payload: 待编码的 JSON 对象。

    Returns:
        先复制顶层映射再 canonical 编码得到的 UTF-8 字节。

    Raises:
        ValueError: 当对象包含 NaN 或无穷大时抛出。
        TypeError: 当运行时值不能被 JSON 编码时抛出。
    """
    return canonical_json_str(dict(payload)).encode("utf-8")


def fingerprint_str(value: ModelConfigJsonValue) -> str:
    """计算 JSON 值 canonical 文本的 SHA-256 指纹。

    Args:
        value: 待计算指纹的 JSON 值。

    Returns:
        形如 ``sha256:<64位十六进制摘要>`` 的字符串。

    Raises:
        ValueError: 当值包含 NaN 或无穷大时抛出。
        TypeError: 当运行时值不能被 JSON 编码时抛出。
    """
    encoded = canonical_json_str(value).encode("utf-8")
    return f"{_SHA256_PREFIX}{hashlib.sha256(encoded).hexdigest()}"


def fingerprint_bytes(payload: JsonObject) -> str:
    """计算 JSON 对象 canonical 字节的 SHA-256 指纹。

    Args:
        payload: 待计算指纹的 JSON 对象。

    Returns:
        形如 ``sha256:<64位十六进制摘要>`` 的字符串。

    Raises:
        ValueError: 当对象包含 NaN 或无穷大时抛出。
        TypeError: 当运行时值不能被 JSON 编码时抛出。
    """
    return (
        f"{_SHA256_PREFIX}"
        f"{hashlib.sha256(canonical_json_bytes(payload)).hexdigest()}"
    )


def file_fingerprint(path: Path) -> str:
    """以固定大小的数据块计算文件的 SHA-256 指纹。

    Args:
        path: 待读取的文件路径。

    Returns:
        形如 ``sha256:<64位十六进制摘要>`` 的字符串。

    Raises:
        OSError: 当文件不能打开或读取时抛出。
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_FILE_READ_CHUNK_BYTES):
            digest.update(chunk)
    return f"{_SHA256_PREFIX}{digest.hexdigest()}"


def bytes_fingerprint(value: bytes) -> str:
    """计算原始字节的 SHA-256 指纹。

    Args:
        value: 待计算指纹的字节。

    Returns:
        形如 ``sha256:<64位十六进制摘要>`` 的字符串。

    Raises:
        TypeError: 当运行时参数不是 bytes-like 值时由 hashlib 抛出。
    """
    return f"{_SHA256_PREFIX}{hashlib.sha256(value).hexdigest()}"


def validated_fingerprint(
    value: ModelConfigJsonValue,
    *,
    name: str,
    error_label: str = "must be a sha256 fingerprint",
) -> str:
    """规范化并校验族 A/G 的 SHA-256 指纹。

    Args:
        value: 待校验的 JSON 值；空值按空文本处理，其余值先转为文本。
        name: 用于错误消息的字段名。
        error_label: 校验失败时追加在字段名后的错误说明。

    Returns:
        去除首尾空白并转换为小写的合法 SHA-256 指纹。

    Raises:
        ValueError: 当前缀、摘要长度或十六进制字符不合法时抛出。
    """
    normalized = str(value or "").strip().lower()
    digest = normalized.removeprefix(_SHA256_PREFIX)
    if (
        not normalized.startswith(_SHA256_PREFIX)
        or len(digest) != _SHA256_HEX_LENGTH
        or any(
            character not in _SHA256_HEX_CHARACTERS
            for character in digest
        )
    ):
        raise ValueError(f"{name} {error_label}")
    return normalized


def require_mapping(
    value: ModelConfigJsonValue | JsonObject,
    *,
    name: str,
) -> JsonObject:
    """要求 JSON 值为映射并原样返回该映射。

    Args:
        value: 待校验的 JSON 值或 JSON 对象映射。
        name: 用于错误消息的字段名。

    Returns:
        与输入相同的映射实例，不复制其内容。

    Raises:
        ValueError: 当输入不是映射时抛出。
    """
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")  # noqa: TRY004
    return value


def optional_mapping(value: ModelConfigJsonValue) -> JsonObject:
    """在 JSON 值为映射时原样返回，否则返回空映射。

    Args:
        value: 待检查的 JSON 值。

    Returns:
        输入映射本身，或在输入不是映射时返回新的空字典。

    Raises:
        本函数不主动抛出异常。
    """
    return value if isinstance(value, Mapping) else {}


def require_text(
    value: ModelConfigJsonValue,
    *,
    name: str,
    maximum_length: int,
) -> str:
    """按族 1 规则校验并规范化必填文本。

    Args:
        value: 待校验的 JSON 值。
        name: 用于错误消息的字段名。
        maximum_length: NFKC 规范化并去除首尾空白后的最大长度。

    Returns:
        NFKC 规范化并去除首尾空白后的文本。

    Raises:
        ValueError: 当输入非文本、为空、过长或含低位控制字符时抛出。
    """
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")  # noqa: TRY004
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) > maximum_length:
        raise ValueError(f"{name} is too long")
    if any(ord(character) < 32 for character in normalized):
        raise ValueError(f"{name} contains control characters")
    return normalized


def format_utc(value: datetime) -> str:
    """把时间转换为 UTC 并固定输出微秒精度。

    Args:
        value: 待格式化的 datetime。

    Returns:
        以 ``Z`` 结尾、保留六位微秒的 ISO-8601 文本。

    Raises:
        ValueError: 当 datetime 的时区实现不能提供有效偏移时抛出。
    """
    return (
        value.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def format_utc_seconds(value: datetime) -> str:
    """把时区感知时间转换为 UTC 并固定输出秒精度。

    Args:
        value: 待格式化且必须包含有效 UTC 偏移的 datetime。

    Returns:
        以 ``Z`` 结尾、截断微秒的 ISO-8601 文本。

    Raises:
        ValueError: 当输入没有时区或时区不能提供 UTC 偏移时抛出。
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must include a timezone")
    return (
        value.astimezone(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def is_subpath(path: Path, root: Path) -> bool:
    """按词法路径判断 path 是否位于 root 之下。

    Args:
        path: 待检查的路径。
        root: 作为边界的根路径。

    Returns:
        当 ``path.relative_to(root)`` 成功时返回 True，否则返回 False。

    Raises:
        本函数捕获路径不相对的 ValueError，不主动传播业务异常。
    """
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def absolute_path(text: str, *, name: str) -> Path:
    """展开用户目录、校验绝对性并解析路径。

    Args:
        text: 已由调用方按自身文本家族校验的路径文本。
        name: 用于错误消息的字段名。

    Returns:
        展开 ``~`` 并解析后的绝对路径。

    Raises:
        ValueError: 当展开后的路径不是绝对路径时抛出。
        OSError: 当路径解析触发底层文件系统错误时抛出。
    """
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return path.resolve()


def serialize_pretty(payload: JsonObject) -> str:
    """把 JSON 对象序列化为稳定的两空格缩进文本。

    Args:
        payload: 待序列化的 JSON 对象。

    Returns:
        顶层映射已复制、键已排序且以换行符结尾的 JSON 文本。

    Raises:
        ValueError: 当对象包含 NaN 或无穷大时抛出。
        TypeError: 当运行时值不能被 JSON 编码时抛出。
    """
    return (
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def decode_base64(text: str, *, name: str) -> bytes:
    """按族 A 规则解码严格的标准 Base64 文本。

    Args:
        text: 已由调用方按自身文本家族校验的 Base64 文本。
        name: 用于错误消息的字段名。

    Returns:
        标准 Base64 解码得到的原始字节。

    Raises:
        ValueError: 当输入不是合法的标准 Base64 时以 ``is invalid`` 抛出。
    """
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, TypeError, ValueError) as exc:
        raise ValueError(f"{name} is invalid") from exc


def decode_base64_strict(text: str, *, name: str) -> bytes:
    """按族 B 规则解码严格的标准 Base64 文本。

    Args:
        text: 已由调用方按族 1 文本规则校验的 Base64 文本。
        name: 用于错误消息的字段名。

    Returns:
        标准 Base64 解码得到的原始字节。

    Raises:
        ValueError: 当输入不是合法的标准 Base64 时以
            ``must be valid base64`` 抛出。
    """
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{name} must be valid base64") from exc


__all__ = [
    "absolute_path",
    "bytes_fingerprint",
    "canonical_json_bytes",
    "canonical_json_str",
    "decode_base64",
    "decode_base64_strict",
    "file_fingerprint",
    "fingerprint_bytes",
    "fingerprint_str",
    "format_utc",
    "format_utc_seconds",
    "is_subpath",
    "optional_mapping",
    "require_mapping",
    "require_text",
    "serialize_pretty",
    "validated_fingerprint",
]
