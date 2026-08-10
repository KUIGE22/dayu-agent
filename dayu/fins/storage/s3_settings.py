"""S3 对象存储严格配置解析。

本模块负责把 ``PlatformSettings.object_storage_env`` 指向的环境变量值解析为
严格类型化的 ``S3StorageSettings``。设计约束（S14-CTRL-02）：

- 值必须是 UTF-8 strict JSON 对象，键精确且无 optional/unknown：
  ``backend``、``endpoint_url``、``region``、``bucket``、``access_key_env``、
  ``secret_key_env``；
- 所有标量必须是非空字符串；``backend`` 只允许 ``"s3"``；bucket 使用一般
  S3 bucket 形态；region 只允许小写字母/数字/连字符；两个 credential 字段
  必须是 ``[A-Z][A-Z0-9_]*`` 环境变量名；
- ``endpoint_url`` 只允许不含 userinfo/query/fragment、path 为空或 ``/`` 的
  ``https://``；``http://`` 只允许 loopback（``127.0.0.1``/``localhost``/
  ``::1``），供真实 MinIO integration 使用；
- 任何校验失败消息只输出固定字段名与规则，绝不回显候选值/secret。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from dayu.fins.domain.evidence_locator import JsonValue

_S3_BACKEND = "s3"
_ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$")
_REGION_PATTERN = re.compile(r"^[a-z0-9\-]+$")
_IPV4_PATTERN = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class S3SettingsError(ValueError):
    """S3 配置非法时抛出的错误。"""


@dataclass(frozen=True)
class S3StorageSettings:
    """S3 对象存储严格配置。

    Args:
        backend: 后端类型，本 Slice 固定为 ``"s3"``。
        endpoint_url: S3 兼容服务端点 URL。
        region: 区域名。
        bucket: 目标 bucket 名。
        access_key_env: access key 所在环境变量名。
        secret_key_env: secret key 所在环境变量名。
    """

    backend: str
    endpoint_url: str
    region: str
    bucket: str
    access_key_env: str
    secret_key_env: str


@dataclass(frozen=True)
class S3Credentials:
    """从显式环境变量读取的 S3 凭证。

    Args:
        access_key: access key 值。
        secret_key: secret key 值。
    """

    access_key: str
    secret_key: str


def parse_object_storage_settings(
    env: Mapping[str, str],
    env_name: str,
) -> S3StorageSettings:
    """解析对象存储环境变量值为严格 S3 配置。

    Args:
        env: 进程环境变量映射。
        env_name: ``object_storage_env`` 指定的环境变量名称。

    Returns:
        严格校验通过的 S3 配置。

    Raises:
        S3SettingsError: 环境变量缺失/空、JSON 解析失败、键不精确、
            值类型非法或字段违反形态规则时抛出；消息只含固定字段名与规则。
    """

    raw = _read_raw_setting(env, env_name)
    payload = _parse_json_object(raw, env_name)
    _assert_exact_keys(payload, env_name)
    backend = _require_nonempty_str(payload, "backend", env_name)
    if backend != _S3_BACKEND:
        raise S3SettingsError(f"字段 backend 只允许值 {_S3_BACKEND}")
    endpoint_url = _require_nonempty_str(payload, "endpoint_url", env_name)
    _validate_endpoint(endpoint_url, env_name)
    region = _require_nonempty_str(payload, "region", env_name)
    if _REGION_PATTERN.fullmatch(region) is None:
        raise S3SettingsError("字段 region 只允许小写字母、数字与连字符")
    bucket = _require_nonempty_str(payload, "bucket", env_name)
    _validate_bucket(bucket, env_name)
    access_key_env = _require_nonempty_str(payload, "access_key_env", env_name)
    secret_key_env = _require_nonempty_str(payload, "secret_key_env", env_name)
    _validate_env_name(access_key_env, "access_key_env", env_name)
    _validate_env_name(secret_key_env, "secret_key_env", env_name)
    return S3StorageSettings(
        backend=backend,
        endpoint_url=endpoint_url,
        region=region,
        bucket=bucket,
        access_key_env=access_key_env,
        secret_key_env=secret_key_env,
    )


def read_credentials(env: Mapping[str, str], settings: S3StorageSettings) -> S3Credentials:
    """按配置中的两个 env 名称读取显式凭证值。

    Args:
        env: 进程环境变量映射。
        settings: 已解析的 S3 配置。

    Returns:
        非空凭证值。

    Raises:
        S3SettingsError: 任一凭证环境变量缺失或值为空时抛出（不泄漏候选值）。
    """

    access_key = env.get(settings.access_key_env, "")
    secret_key = env.get(settings.secret_key_env, "")
    if not access_key or not access_key.strip():
        raise S3SettingsError(f"环境变量 {settings.access_key_env} 缺失或为空")
    if not secret_key or not secret_key.strip():
        raise S3SettingsError(f"环境变量 {settings.secret_key_env} 缺失或为空")
    return S3Credentials(access_key=access_key, secret_key=secret_key)


def _read_raw_setting(env: Mapping[str, str], env_name: str) -> str:
    """读取指定环境变量的原始值。

    Args:
        env: 进程环境变量映射。
        env_name: 环境变量名。

    Returns:
        原始字符串值。

    Raises:
        S3SettingsError: 变量缺失或值为空时抛出。
    """

    raw = env.get(env_name, "")
    if not raw or not raw.strip():
        raise S3SettingsError(f"环境变量 {env_name} 缺失或为空")
    return raw


def _parse_json_object(raw: str, env_name: str) -> dict[str, JsonValue]:
    """把原始字符串解析为 JSON 对象。

    Args:
        raw: 原始 JSON 字符串。
        env_name: 来源环境变量名（仅用于错误消息定位）。

    Returns:
        解析后的 JSON 对象。

    Raises:
        S3SettingsError: JSON 无法解析或根节点不是 JSON 对象时抛出。
    """

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise S3SettingsError(f"环境变量 {env_name} 必须是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise S3SettingsError(f"环境变量 {env_name} 根节点必须是 JSON 对象")
    return payload


def _assert_exact_keys(payload: dict[str, JsonValue], env_name: str) -> None:
    """断言 JSON 对象 的键集合精确等于契约键集合。

    Args:
        payload: 已解析的 JSON 对象。
        env_name: 来源环境变量名（仅用于错误消息定位）。

    Returns:
        无。

    Raises:
        S3SettingsError: 存在缺失或未知键时抛出。
    """

    expected = frozenset(
        {"backend", "endpoint_url", "region", "bucket", "access_key_env", "secret_key_env"}
    )
    actual = frozenset(payload)
    missing = expected - actual
    unknown = actual - expected
    if missing:
        raise S3SettingsError(f"环境变量 {env_name} 缺少字段: {_format_field_names(missing)}")
    if unknown:
        raise S3SettingsError(f"环境变量 {env_name} 含未知字段: {_format_field_names(unknown)}")


def _format_field_names(names: frozenset[str]) -> str:
    """把字段名集合格式化为稳定排序的逗号列表。

    Args:
        names: 字段名集合。

    Returns:
        排序后的逗号分隔字符串。

    Raises:
        无。
    """

    return ", ".join(sorted(names))


def _require_nonempty_str(payload: dict[str, JsonValue], field: str, env_name: str) -> str:
    """读取必须为非空字符串的字段。

    Args:
        payload: 已解析的 JSON 对象。
        field: 字段名。
        env_name: 来源环境变量名（仅用于错误消息定位）。

    Returns:
        非空字符串值。

    Raises:
        S3SettingsError: 字段缺失、非字符串或为空时抛出。
    """

    value = payload[field]
    if not isinstance(value, str) or not value.strip():
        raise S3SettingsError(f"字段 {field} 必须是非空字符串")
    return value


def _validate_env_name(value: str, field: str, env_name: str) -> None:
    """校验环境变量名称形态。

    Args:
        value: 待校验的环境变量名。
        field: 配置字段名。
        env_name: 来源环境变量名（仅用于错误消息定位）。

    Returns:
        无。

    Raises:
        S3SettingsError: 形态非法时抛出。
    """

    if _ENV_NAME_PATTERN.fullmatch(value) is None:
        raise S3SettingsError(f"字段 {field} 必须是合法环境变量名称（仅允许大写字母、数字与下划线，且以字母开头）")


def _validate_bucket(bucket: str, env_name: str) -> None:
    """校验 bucket 形态。

    Args:
        bucket: bucket 名。
        env_name: 来源环境变量名（仅用于错误消息定位）。

    Returns:
        无。

    Raises:
        S3SettingsError: bucket 违反一般 S3 形态（3-63 个字符、小写、
            无相邻点、首尾非点/连字符、非 IPv4）时抛出。
    """

    if _BUCKET_PATTERN.fullmatch(bucket) is None:
        raise S3SettingsError(
            "字段 bucket 必须是 3-63 个字符的小写字母/数字/点/连字符，"
            "不得含相邻点、首尾点或连字符，且不得是 IPv4 形态"
        )
    if ".." in bucket:
        raise S3SettingsError("字段 bucket 不得包含相邻点")
    if _IPV4_PATTERN.fullmatch(bucket) is not None:
        raise S3SettingsError("字段 bucket 不得是 IPv4 形态")


def _validate_endpoint(endpoint_url: str, env_name: str) -> None:
    """校验 endpoint URL 形态。

    Args:
        endpoint_url: 端点 URL。
        env_name: 来源环境变量名（仅用于错误消息定位）。

    Returns:
        无。

    Raises:
        S3SettingsError: URL 含 userinfo/query/fragment、path 非空非 ``/``、
            scheme 非法或 ``http://`` 非 loopback 时抛出。
    """

    try:
        parts = urlsplit(endpoint_url)
    except ValueError as exc:
        raise S3SettingsError("字段 endpoint_url 不是合法 URL") from exc
    if parts.scheme not in {"https", "http"}:
        raise S3SettingsError("字段 endpoint_url 只允许 https 或 http scheme")
    if not parts.hostname:
        raise S3SettingsError("字段 endpoint_url 缺少 host")
    if parts.username is not None or parts.password is not None:
        raise S3SettingsError("字段 endpoint_url 不得包含 userinfo")
    if parts.query or parts.fragment:
        raise S3SettingsError("字段 endpoint_url 不得包含 query 或 fragment")
    if parts.path not in {"", "/"}:
        raise S3SettingsError("字段 endpoint_url 的 path 必须为空或 /")
    if parts.scheme == "http" and parts.hostname not in _LOOPBACK_HOSTS:
        raise S3SettingsError("字段 endpoint_url 的 http 只允许 loopback 地址")
