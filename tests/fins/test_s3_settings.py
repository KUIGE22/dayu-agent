"""S3 严格配置解析单元测试（S14-CTRL-02）。"""

from __future__ import annotations

import pytest

from dayu.fins.storage.s3_settings import (
    S3SettingsError,
    parse_object_storage_settings,
    read_credentials,
)


def _valid_payload() -> dict[str, str]:
    """构造合法配置 payload。"""

    return {
        "backend": "s3",
        "endpoint_url": "https://s3.example.com",
        "region": "us-east-1",
        "bucket": "dayu-bucket-123",
        "access_key_env": "DAYU_S3_ACCESS_KEY",
        "secret_key_env": "DAYU_S3_SECRET_KEY",
    }


def test_parse_valid_settings() -> None:
    """合法配置解析为严格设置。"""

    settings = parse_object_storage_settings(
        {"DAYU_OBJECT_STORAGE": '{"backend":"s3","endpoint_url":"https://s3.example.com",'
        '"region":"us-east-1","bucket":"dayu-bucket-123",'
        '"access_key_env":"DAYU_S3_ACCESS_KEY","secret_key_env":"DAYU_S3_SECRET_KEY"}'},
        "DAYU_OBJECT_STORAGE",
    )
    assert settings.backend == "s3"
    assert settings.endpoint_url == "https://s3.example.com"
    assert settings.region == "us-east-1"
    assert settings.bucket == "dayu-bucket-123"
    assert settings.access_key_env == "DAYU_S3_ACCESS_KEY"
    assert settings.secret_key_env == "DAYU_S3_SECRET_KEY"


def test_missing_env_var_fails() -> None:
    """环境变量缺失 => 稳定错误。"""

    with pytest.raises(S3SettingsError):
        parse_object_storage_settings({}, "DAYU_OBJECT_STORAGE")


def test_invalid_json_fails() -> None:
    """JSON 无法解析 => 稳定错误。"""

    with pytest.raises(S3SettingsError):
        parse_object_storage_settings({"DAYU_OBJECT_STORAGE": "not-json"}, "DAYU_OBJECT_STORAGE")


def test_unknown_key_fails() -> None:
    """未知键 => 稳定错误（只报字段名）。"""

    payload = _valid_payload()
    payload["extra"] = "x"
    with pytest.raises(S3SettingsError) as exc_info:
        parse_object_storage_settings({"DAYU_OBJECT_STORAGE": _dump(payload)}, "DAYU_OBJECT_STORAGE")
    assert "extra" in str(exc_info.value)


def test_missing_key_fails() -> None:
    """缺失键 => 稳定错误。"""

    payload = _valid_payload()
    del payload["region"]
    with pytest.raises(S3SettingsError) as exc_info:
        parse_object_storage_settings({"DAYU_OBJECT_STORAGE": _dump(payload)}, "DAYU_OBJECT_STORAGE")
    assert "region" in str(exc_info.value)


def test_non_string_value_fails() -> None:
    """值为空字符串 => 稳定错误（JSON 中非字符串无法表达，测空值）。"""

    payload = _valid_payload()
    payload["bucket"] = ""
    with pytest.raises(S3SettingsError):
        parse_object_storage_settings({"DAYU_OBJECT_STORAGE": _dump(payload)}, "DAYU_OBJECT_STORAGE")


def test_invalid_backend_fails() -> None:
    """backend 非 s3 => 稳定错误。"""

    payload = _valid_payload()
    payload["backend"] = "gcs"
    with pytest.raises(S3SettingsError):
        parse_object_storage_settings({"DAYU_OBJECT_STORAGE": _dump(payload)}, "DAYU_OBJECT_STORAGE")


def test_invalid_region_fails() -> None:
    """region 含大写/非法字符 => 稳定错误。"""

    payload = _valid_payload()
    payload["region"] = "US-EAST-1"
    with pytest.raises(S3SettingsError):
        parse_object_storage_settings({"DAYU_OBJECT_STORAGE": _dump(payload)}, "DAYU_OBJECT_STORAGE")


def test_invalid_bucket_forms_fail() -> None:
    """非法 bucket 形态（相邻点/首尾连字符/IPv4/大写）=> 稳定错误。"""

    for bad_bucket in ("UPPER", "a..b", "-lead", "trail-", "1.2.3.4", "a_b"):
        payload = _valid_payload()
        payload["bucket"] = bad_bucket
        with pytest.raises(S3SettingsError):
            parse_object_storage_settings({"DAYU_OBJECT_STORAGE": _dump(payload)}, "DAYU_OBJECT_STORAGE")


def test_invalid_endpoint_forms_fail() -> None:
    """非法 endpoint（query/fragment/userinfo/path/http 非 loopback）=> 稳定错误。"""

    for bad_endpoint in (
        "https://s3.example.com/path",
        "https://s3.example.com?x=1",
        "https://s3.example.com#frag",
        "https://user:pass@s3.example.com",
        "http://s3.example.com",
        "ftp://s3.example.com",
    ):
        payload = _valid_payload()
        payload["endpoint_url"] = bad_endpoint
        with pytest.raises(S3SettingsError):
            parse_object_storage_settings({"DAYU_OBJECT_STORAGE": _dump(payload)}, "DAYU_OBJECT_STORAGE")


def test_http_loopback_endpoint_allowed() -> None:
    """http:// 仅允许 loopback（供 MinIO integration）。"""

    for host in ("127.0.0.1", "localhost", "[::1]"):
        payload = _valid_payload()
        payload["endpoint_url"] = f"http://{host}:9000"
        settings = parse_object_storage_settings(
            {"DAYU_OBJECT_STORAGE": _dump(payload)}, "DAYU_OBJECT_STORAGE"
        )
        assert settings.endpoint_url == f"http://{host}:9000"


def test_invalid_env_name_fails() -> None:
    """credential 环境变量名非法 => 稳定错误。"""

    for field in ("access_key_env", "secret_key_env"):
        payload = _valid_payload()
        payload[field] = "lowercase"
        with pytest.raises(S3SettingsError):
            parse_object_storage_settings({"DAYU_OBJECT_STORAGE": _dump(payload)}, "DAYU_OBJECT_STORAGE")


def test_read_credentials_ok() -> None:
    """显式读取凭证。"""

    settings = parse_object_storage_settings(
        {"DAYU_OBJECT_STORAGE": _dump(_valid_payload())}, "DAYU_OBJECT_STORAGE"
    )
    creds = read_credentials(
        {"DAYU_S3_ACCESS_KEY": "AKIAFAKE", "DAYU_S3_SECRET_KEY": "s3cret"},
        settings,
    )
    assert creds.access_key == "AKIAFAKE"
    assert creds.secret_key == "s3cret"


def test_read_credentials_missing_fails() -> None:
    """凭证缺失/为空 => 稳定错误（不泄漏候选值）。"""

    settings = parse_object_storage_settings(
        {"DAYU_OBJECT_STORAGE": _dump(_valid_payload())}, "DAYU_OBJECT_STORAGE"
    )
    with pytest.raises(S3SettingsError):
        read_credentials({}, settings)


def _dump(payload: dict[str, str]) -> str:
    """序列化 payload 为 JSON。

    Args:
        payload: 配置字典。

    Returns:
        JSON 字符串。

    Raises:
        无。
    """

    import json

    return json.dumps(payload)
