"""验证 write artifact 共享辅助函数及迁移前的行为边界。"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from types import MappingProxyType

import pytest

from dayu.contracts.model_config import ModelConfigJsonValue
from dayu.services import _write_artifact_utils as artifact_utils
from dayu.services import write_model_challenger_promotion as promotion
from dayu.services import write_model_challenger_run_approval as run_approval
from dayu.services import write_model_configuration_application as application
from dayu.services import write_model_configuration_change as configuration_change
from dayu.services import write_model_configuration_manual_recovery as manual_recovery
from dayu.services import (
    write_model_configuration_manual_recovery_gate_revalidation as gate_revalidation,
)
from dayu.services import (
    write_model_configuration_manual_recovery_incident_dossier_revalidation as dossier_revalidation,
)
from dayu.services import (
    write_model_configuration_manual_recovery_verification as recovery_verification,
)
from dayu.services import (
    write_model_configuration_rollback_application as rollback_application,
)
from dayu.services import write_model_live_smoke_plan as live_smoke_plan
from dayu.services._write_artifact_utils import (
    absolute_path,
    bytes_fingerprint,
    canonical_json_bytes,
    canonical_json_str,
    decode_base64,
    decode_base64_strict,
    file_fingerprint,
    fingerprint_bytes,
    fingerprint_str,
    format_utc,
    format_utc_seconds,
    is_subpath,
    optional_mapping,
    require_mapping,
    require_text,
    serialize_pretty,
    validated_fingerprint,
)
from tests.conftest import requires_symlink


class _JsonDict(dict[str, ModelConfigJsonValue]):
    """用于验证映射实例身份的合法 JSON 字典子类。"""


class _MissingOffsetTimezone(tzinfo):
    """提供 tzinfo 但拒绝提供 UTC 偏移的测试时区。"""

    def utcoffset(self, value: datetime | None) -> None:
        """返回缺失的 UTC 偏移。

        Args:
            value: datetime 调用方传入的时间。

        Returns:
            固定返回 None，表示偏移不可用。

        Raises:
            本方法不主动抛出异常。
        """
        return

    def dst(self, value: datetime | None) -> None:
        """返回缺失的夏令时偏移。

        Args:
            value: datetime 调用方传入的时间。

        Returns:
            固定返回 None。

        Raises:
            本方法不主动抛出异常。
        """
        return

    def tzname(self, value: datetime | None) -> str:
        """返回测试时区名称。

        Args:
            value: datetime 调用方传入的时间。

        Returns:
            测试时区的稳定名称。

        Raises:
            本方法不主动抛出异常。
        """
        return "missing-offset"


def test_public_surface_contains_exactly_seventeen_helpers() -> None:
    """公开面只包含 accepted plan 指定的 17 个 helper。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当公开符号数量、名称或顺序偏离计划时抛出。
    """
    assert artifact_utils.__all__ == [
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


def test_canonical_and_fingerprint_helpers_match_eligible_private_families() -> None:
    """验证已迁移 canonical 与 fingerprint helper 保持固定 corpus 输出。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当 shared 输出偏离迁移前固定 corpus 时抛出。
    """
    payload: dict[str, ModelConfigJsonValue] = {
        "z": ["雪", 2],
        "a": {"enabled": True},
    }

    expected = '{"a":{"enabled":true},"z":["雪",2]}'

    assert canonical_json_str(payload) == expected
    assert canonical_json_bytes(payload) == expected.encode("utf-8")
    assert fingerprint_str(payload) == (
        f"sha256:{hashlib.sha256(expected.encode('utf-8')).hexdigest()}"
    )
    assert fingerprint_bytes(payload) == (
        f"sha256:{hashlib.sha256(expected.encode('utf-8')).hexdigest()}"
    )


def test_canonical_helpers_reject_non_finite_numbers() -> None:
    """验证 canonical helper 保持 allow_nan=False 的失败行为。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当非有限浮点数未按预期被拒绝时抛出。
    """
    invalid: ModelConfigJsonValue = {"value": float("nan")}

    with pytest.raises(ValueError, match="Out of range float values"):
        canonical_json_str(invalid)
    with pytest.raises(ValueError, match="Out of range float values"):
        canonical_json_bytes({"value": float("inf")})


def test_file_and_bytes_fingerprints_match_existing_implementations(
    tmp_path: Path,
) -> None:
    """验证文件与字节指纹覆盖多块读取并匹配既有实现。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当摘要不稳定或与迁移前实现不一致时抛出。
    """
    content = b"dayu-artifact-" * 100_000
    target = tmp_path / "artifact.bin"
    target.write_bytes(content)
    expected = f"sha256:{hashlib.sha256(content).hexdigest()}"

    assert bytes_fingerprint(content) == expected
    assert file_fingerprint(target) == expected


def test_validated_fingerprint_case_sensitivity() -> None:
    """验证 shared 仅与 lower() 的族 A/G 等价并锁定 defer 族差异。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当大小写规范化或 defer 族行为发生变化时抛出。
    """
    upper = f"SHA256:{'A' * 64}"
    lower = upper.lower()

    assert validated_fingerprint(upper, name="fingerprint") == lower
    assert rollback_application._validated_fingerprint(upper, name="fingerprint") == lower
    with pytest.raises(ValueError, match="fingerprint must use sha256"):
        application._validated_fingerprint(upper, name="fingerprint")
    with pytest.raises(ValueError, match="fingerprint is not a SHA-256 fingerprint"):
        gate_revalidation._validated_fingerprint(upper, name="fingerprint")


def test_validated_fingerprint_error_text_variants() -> None:
    """固定六个私有子族的错误文本，防止把 defer 族误接到 shared。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当任一指纹子族的错误文本发生变化时抛出。
    """
    with pytest.raises(ValueError, match="field must be a sha256 fingerprint"):
        validated_fingerprint("bad", name="field")
    with pytest.raises(ValueError, match="field must be a sha256 fingerprint"):
        rollback_application._validated_fingerprint("bad", name="field")
    with pytest.raises(ValueError, match="field must use sha256"):
        application._validated_fingerprint("md5:bad", name="field")
    with pytest.raises(ValueError, match="field is invalid"):
        application._validated_fingerprint(f"sha256:{'g' * 64}", name="field")
    with pytest.raises(ValueError, match="field must be a SHA-256 fingerprint"):
        manual_recovery._validated_fingerprint("bad", name="field")
    with pytest.raises(ValueError, match="field is not a SHA-256 fingerprint"):
        recovery_verification._validated_fingerprint("bad", name="field")
    with pytest.raises(ValueError, match="field is not a SHA-256 fingerprint"):
        gate_revalidation._validated_fingerprint("bad", name="field")


def test_validated_fingerprint_custom_error_label() -> None:
    """验证 shared helper 保留族 A/G 所需的可配置错误标签。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当自定义错误标签未进入异常文本时抛出。
    """
    with pytest.raises(ValueError, match="field is invalid"):
        validated_fingerprint(
            "bad",
            name="field",
            error_label="is invalid",
        )


def test_require_mapping_identity_vs_copy() -> None:
    """用字典子类验证 identity、copy 及 str+dict adapter 的精确语义。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当映射身份或 adapter 输出偏离迁移前语义时抛出。
    """
    value = _JsonDict({"z": 2, "a": "雪"})

    identity = require_mapping(value, name="payload")
    copied = dict(require_mapping(value, name="payload"))

    assert identity is value
    assert copied is not value
    assert copied == value
    expected = '{"a":"雪","z":2}'
    assert canonical_json_str(dict(value)) == expected
    expected_fingerprint = (
        f"sha256:{hashlib.sha256(expected.encode('utf-8')).hexdigest()}"
    )
    assert fingerprint_str(dict(value)) == expected_fingerprint


def test_require_mapping_non_dict_mapping_identity() -> None:
    """验证严格映射 helper 对非字典 Mapping 仍原样返回。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当 helper 复制或替换非字典映射时抛出。
    """
    value: Mapping[str, ModelConfigJsonValue] = MappingProxyType(
        {"key": "value"}
    )

    identity = require_mapping(value, name="payload")

    assert identity is value


def test_mapping_helpers_reject_or_default_non_mapping_values() -> None:
    """验证严格映射校验报错且宽松映射校验返回空字典。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当严格或宽松映射边界不符合契约时抛出。
    """
    value: ModelConfigJsonValue = ["not", "a", "mapping"]

    with pytest.raises(ValueError, match="payload must be an object"):
        require_mapping(value, name="payload")
    assert optional_mapping(value) == {}
    mapping: ModelConfigJsonValue = {"key": "value"}
    assert optional_mapping(mapping) is mapping


def test_require_text_family_1_behavior() -> None:
    """验证 shared 与族 1 等价，并用反例锁定族 2-8 的独立行为。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当族 1 不等价或任一 defer 文本族差异丢失时抛出。
    """
    full_width = "  ＡＢＣ  "
    control_text = "alpha\x00beta"

    assert require_text(full_width, name="field", maximum_length=16) == "ABC"
    with pytest.raises(ValueError, match="field contains control characters"):
        require_text(control_text, name="field", maximum_length=16)

    assert recovery_verification._required_text(control_text, name="field", maximum_length=16) == control_text
    with pytest.raises(ValueError, match="cannot have leading or trailing whitespace"):
        configuration_change._required_text(" alpha ", name="field")
    with pytest.raises(ValueError, match="cannot have leading or trailing whitespace"):
        run_approval._required_text(" alpha ", name="field", maximum_length=16)
    assert promotion._required_text(control_text, name="field") == control_text
    assert dossier_revalidation._required_text("Ａ", name="field", maximum_length=16) == "Ａ"
    assert gate_revalidation._required_text(control_text, name="field", maximum_length=16) == control_text
    assert live_smoke_plan._required_text(f" {control_text} ", name="field") == control_text


def test_require_text_family_1_errors_and_length_boundary() -> None:
    """验证族 1 对类型、空文本与最大长度保持既有错误契约。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当任一族 1 错误或长度边界发生变化时抛出。
    """
    with pytest.raises(ValueError, match="field must be a string"):
        require_text(7, name="field", maximum_length=3)
    with pytest.raises(ValueError, match="field must not be empty"):
        require_text("  ", name="field", maximum_length=3)
    with pytest.raises(ValueError, match="field is too long"):
        require_text("abcd", name="field", maximum_length=3)
    assert require_text("abc", name="field", maximum_length=3) == "abc"


def test_format_utc_microseconds_vs_seconds_precision() -> None:
    """验证 microseconds 与 seconds 两族保持不同精度并匹配私有实现。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当 UTC 转换、精度或迁移前差分结果不一致时抛出。
    """
    value = datetime(
        2026,
        8,
        7,
        20,
        30,
        45,
        123456,
        tzinfo=timezone(timedelta(hours=8)),
    )

    assert format_utc(value) == "2026-08-07T12:30:45.123456Z"
    assert format_utc_seconds(value) == "2026-08-07T12:30:45Z"


def test_format_utc_naive_matches_eligible_microseconds_family() -> None:
    """验证 naive datetime 仍与三个 eligible microseconds 私有实现等价。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当 shared 与任一迁移前私有实现的本地时区转换不一致时抛出。
    """
    value = datetime(2026, 8, 7, 12, 30, 45, 123456)  # noqa: DTZ001 - 固定迁移前 naive 反例
    assert format_utc(value) == (
        value.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 8, 7, 12, 30, 45),  # noqa: DTZ001 - 固定 naive 反例
        datetime(
            2026,
            8,
            7,
            12,
            30,
            45,
            tzinfo=_MissingOffsetTimezone(),
        ),
    ],
)
def test_format_utc_seconds_naive_raises(value: datetime) -> None:
    """验证 seconds 族拒绝无 tzinfo 或 utcoffset 的 datetime。

    Args:
        value: 参数化提供的无有效 UTC 偏移时间。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当输入未以指定错误文本被拒绝时抛出。
    """
    with pytest.raises(ValueError, match="now must include a timezone"):
        format_utc_seconds(value)


@requires_symlink
def test_is_subpath_does_not_resolve_symlinks(tmp_path: Path) -> None:
    """验证词法包含判断不把解析到同一目录的符号链接视为同一路径。

    Args:
        tmp_path: pytest 提供且已确认可创建符号链接的临时目录。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当 helper 意外解析符号链接或偏离私有实现时抛出。
    """
    real_root = tmp_path / "real"
    real_root.mkdir()
    alias_root = tmp_path / "alias"
    alias_root.symlink_to(real_root, target_is_directory=True)
    real_child = real_root / "artifact.json"
    real_child.write_text("{}", encoding="utf-8")
    alias_child = alias_root / "artifact.json"

    assert is_subpath(real_child, alias_root) is False
    assert is_subpath(alias_child, alias_root) is True
    assert real_child.resolve() == alias_child.resolve()


def test_absolute_path_relative_raises(tmp_path: Path) -> None:
    """验证 absolute_path 在 resolve 前拒绝相对路径并解析绝对路径。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当相对路径未被拒绝或绝对路径未解析时抛出。
    """
    with pytest.raises(ValueError, match="artifact must be absolute"):
        absolute_path("relative/artifact.json", name="artifact")

    target = tmp_path / "nested" / ".." / "artifact.json"
    assert absolute_path(str(target), name="artifact") == target.resolve()


def test_serialize_pretty_matches_eligible_private_family() -> None:
    """验证 pretty serializer 保持排序、缩进、末尾换行及既有输出。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当序列化格式或迁移前差分输出变化时抛出。
    """
    payload: dict[str, ModelConfigJsonValue] = {"z": 2, "a": "雪"}
    serialized = serialize_pretty(payload)

    assert serialized == '{\n  "a": "雪",\n  "z": 2\n}\n'
    assert serialized.endswith("\n")
    assert list(json.loads(serialized)) == ["a", "z"]


def test_decode_base64_standard_vs_urlsafe_rejection() -> None:
    """验证 shared codec 接受标准 Base64 并拒绝 URL-safe 字母表变体。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当标准或 URL-safe Base64 边界发生变化时抛出。
    """
    raw = b"\xfb\xff"
    standard = base64.b64encode(raw).decode("ascii")
    urlsafe = base64.urlsafe_b64encode(raw).decode("ascii")

    assert decode_base64(standard, name="payload") == raw
    assert decode_base64_strict(standard, name="payload") == raw
    with pytest.raises(ValueError, match="payload is invalid"):
        decode_base64(urlsafe, name="payload")
    with pytest.raises(ValueError, match="payload must be valid base64"):
        decode_base64_strict(urlsafe, name="payload")


def test_decode_base64_error_text_families() -> None:
    """验证族 A 与族 B 对同一非法输入保留不同错误文本。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当两族 codec 的错误文本差异丢失时抛出。
    """
    invalid = "not-base64!"

    with pytest.raises(ValueError, match="payload is invalid"):
        decode_base64(invalid, name="payload")
    with pytest.raises(ValueError, match="payload must be valid base64"):
        decode_base64_strict(invalid, name="payload")


def test_empty_bytes_have_stable_fingerprint() -> None:
    """验证空字节输入仍生成标准 SHA-256 指纹。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当空字节摘要偏离标准 SHA-256 值时抛出。
    """
    assert bytes_fingerprint(b"") == (
        "sha256:e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855"
    )


def test_utc_value_with_zero_microseconds_keeps_declared_precision() -> None:
    """验证两种时间 helper 即使微秒为零也保持各自固定精度。

    Returns:
        本测试不返回值。

    Raises:
        AssertionError: 当固定精度输出发生变化时抛出。
    """
    value = datetime(2026, 8, 7, tzinfo=UTC)

    assert format_utc(value) == "2026-08-07T00:00:00.000000Z"
    assert format_utc_seconds(value) == "2026-08-07T00:00:00Z"
