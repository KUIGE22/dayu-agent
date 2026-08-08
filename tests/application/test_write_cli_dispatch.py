"""写作 phase-table 与 research-template mapping 的 CLI 分派契约测试。

写作入口通过结构断言与 monkeypatch call trace 锁定 16 路 phase-table；
research-template 入口验证 39-key mapping、selector 防御性语义与错误边界。

覆盖:
  A. _canonical_json str 变体
  B. _canonical_json bytes 变体
  C. _validated_fingerprint 两异常文本族
  D. _parse_utc offset 差异（锁定 defer）
  F. CLI 混合 flag 优先级矩阵
  G. monkeypatch 路径契约
  H. 惰性计算 / 阶段顺序
  I-a. write phase-table 集成契约（16 selectors）
  I-b. research-template mapping 集成表征（39 action keys）
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar, Never, Protocol

import pytest

from dayu.cli.arg_parsing import parse_arguments
from dayu.cli.arguments import DayuCliArguments, WriteDispatchArguments
from dayu.cli.commands import _write_challenger as write_challenger
from dayu.cli.commands import _write_config_helpers as write_config_helpers
from dayu.cli.commands import _write_config_rollback as write_config_rollback
from dayu.cli.commands import _write_execution as write_execution
from dayu.cli.commands import _write_manual_recovery as write_manual_recovery
from dayu.cli.commands import _write_params_validation as write_params_validation
from dayu.cli.commands import research_template as research_template_command_module
from dayu.cli.commands import write as write_command_module
from dayu.cli.commands.research_template import run_research_template_command
from dayu.cli.commands.write import run_write_command
from dayu.cli.dependency_setup import WorkspaceConfig
from dayu.contracts.model_config import ModelConfigJsonValue
from dayu.execution.options import ExecutionOptions
from dayu.services._write_artifact_utils import (
    canonical_json_bytes,
    canonical_json_str,
    validated_fingerprint,
)

# ============================================================================
# 测试辅助类型
# ============================================================================


class _SentinelExecOptions:
    """_build_execution_options mock 返回的轻量哨兵。

    产能侧 mock 用此类型替代真实构造，同时独立追踪调用次数。
    """


class _SentinelFinsRuntime:
    """为 Phase H 测试提供最小公司名称解析边界。"""

    def get_company_name(self, ticker: str) -> str:
        """返回固定公司名以隔离真实 Fins 运行时。

        Args:
            ticker: 当前股票代码。

        Returns:
            固定测试公司名。

        Raises:
            本函数不显式抛出异常。
        """

        assert ticker == "AAPL"
        return "Apple Inc."


class _WriteRunnerProto(Protocol):
    """mock runner 协议：接受 keyword args 返回 int。

    覆盖 write.py 中全部 Phase A/B _run_* 函数的最宽 keyword 签名。
    """

    def __call__(
        self,
        *,
        args: argparse.Namespace | None = None,
        paths_config: WorkspaceConfig | None = None,
        execution_options: ExecutionOptions | _SentinelExecOptions | None = None,
    ) -> int: ...


# ============================================================================
# 辅助函数
# ============================================================================


def _make_write_args(**overrides: str | bool | None) -> DayuCliArguments:
    """构造 run_write_command 所需的最小 Dayu 参数对象。

    所有 dispatch 相关字段默认 None/False，调用方按需逐项覆盖。

    Args:
        **overrides: 需要覆盖的写作 CLI 字段。

    Returns:
        包含完整分派默认值与调用方覆盖值的 Dayu 参数对象。

    Raises:
        本函数不显式抛出异常。
    """
    base: dict[str, str | bool | None] = {
        "ticker": "AAPL",
        "summary": False,
        "preflight_only": False,
        "reprice_costs": False,
        "apply_write_model_configuration": False,
        "rollback_write_model_configuration": False,
        "revalidate_write_model_configuration_manual_recovery_incident_dossier": False,
        "inspect_write_model_configuration_manual_recovery_incident": False,
        "audit_write_model_configuration_manual_recovery_history": False,
        "revalidate_write_model_configuration_manual_recovery_gate_verification": False,
        "verify_write_model_configuration_manual_recovery_gate": False,
        "check_write_model_configuration_manual_recovery_gate": False,
        "revoke_write_model_configuration_manual_recovery_clearance": False,
        "restart_write_model_configuration_manual_recovery_after_clearance_revocation": False,
        "clear_write_model_configuration_manual_recovery": False,
        "verify_write_model_configuration_manual_recovery": False,
        "recover_write_model_configuration": False,
        "challenger_config_manual_recovery_receipt_input": None,
        "challenger_config_manual_recovery_plan_output": None,
        "challenger_config_manual_recovery_approval_output": None,
        "output": None,
        "materialize_research": False,
        "infer": False,
        "model_name": "",
        "write_routing_snapshot_output": None,
        "write_live_smoke_plan_output": None,
        "routing_proposal_input": None,
        "routing_proposal_output": None,
        "routing_history_root": None,
        "overwrite_routing_proposal": False,
        "routing_preflight_approval_request": None,
        "routing_preflight_approval_output": None,
        "challenger_promotion_proposal_input": None,
        "challenger_promotion_proposal_output": None,
        "challenger_config_change_request_input": None,
        "challenger_config_change_request_output": None,
        "challenger_config_change_approval_request": None,
        "challenger_config_change_approval_output": None,
        "challenger_config_change_approval_input": None,
        "challenger_config_preapplication_plan_output": None,
        "challenger_config_preapplication_plan_input": None,
        "challenger_config_application_receipt_input": None,
        "challenger_config_rollback_plan_output": None,
        "challenger_config_rollback_plan_input": None,
        "challenger_config_rollback_approval_request": None,
        "challenger_config_rollback_approval_output": None,
        "challenger_config_rollback_approval_input": None,
        "challenger_config_rollback_receipt_input": None,
        "routing_challenger_run_plan_output": None,
        "routing_challenger_run_approval_request": None,
        "routing_challenger_run_approval_output": None,
        "routing_challenger_run_approval_input": None,
    }
    for key, val in overrides.items():
        base[key] = val
    return DayuCliArguments(**base)


def _install_write_baseline_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    paths_config_ticker: str = "AAPL",
) -> tuple[dict[str, int], dict[str, int], list[int]]:
    """安装 run_write_command 所需的基础 mock。

    所有 Phase A + Phase B runner 均被 mock 为返回唯一 exit code 并递增计数。
    同时 mock _build_execution_options 以追踪调用次数。

    Returns:
        (call_counts, sentinels, beo_calls):
          call_counts --- {runner_attr: call_count} 可变字典；
          sentinels --- {runner_attr: sentinel_exit_code} 可变字典；
          beo_calls --- 每次 _build_execution_options 被调用时 append(1) 的列表。
    """
    call_counts: dict[str, int] = {}
    sentinels: dict[str, int] = {}

    # ---- 基础基础设施 mock ----
    monkeypatch.setattr("dayu.cli.commands.write.setup_loglevel", lambda _a: None)
    monkeypatch.setattr("dayu.cli.commands.write.Log.info", lambda *a, **kw: None)
    monkeypatch.setattr("dayu.cli.commands.write.Log.error", lambda *a, **kw: None)
    monkeypatch.setattr(
        "dayu.cli.commands.write._validate_research_materialization_args",
        lambda _a: None,
    )

    fake_ws = WorkspaceConfig(
        workspace_dir=Path("/tmp/ws"),
        output_dir=Path("/tmp/ws/output"),
        ticker=paths_config_ticker,
        has_local_filings=False,
    )
    monkeypatch.setattr("dayu.cli.commands.write.setup_paths", lambda _a: fake_ws)

    # ---- _build_execution_options 调用追踪 ----
    beo_calls: list[int] = []
    _sentinel = _SentinelExecOptions()
    monkeypatch.setattr(
        "dayu.cli.commands.write._build_execution_options",
        lambda _a: (beo_calls.append(1), _sentinel)[1],
    )

    # ---- Phase A runners（14 个）----
    _phase_a_runners: list[tuple[str, str, int]] = [
        (
            "revalidate_write_model_configuration_manual_recovery_incident_dossier",
            "_run_write_model_configuration_manual_recovery_incident_dossier_revalidation",
            10,
        ),
        (
            "inspect_write_model_configuration_manual_recovery_incident",
            "_run_write_model_configuration_manual_recovery_incident_dossier",
            11,
        ),
        (
            "audit_write_model_configuration_manual_recovery_history",
            "_run_write_model_configuration_manual_recovery_audit_timeline",
            12,
        ),
        (
            "revalidate_write_model_configuration_manual_recovery_gate_verification",
            "_run_write_model_configuration_manual_recovery_gate_revalidation",
            13,
        ),
        (
            "verify_write_model_configuration_manual_recovery_gate",
            "_run_write_model_configuration_manual_recovery_gate_verification",
            14,
        ),
        (
            "check_write_model_configuration_manual_recovery_gate",
            "_run_write_model_configuration_manual_recovery_gate_check",
            15,
        ),
        (
            "revoke_write_model_configuration_manual_recovery_clearance",
            "_run_write_model_configuration_manual_recovery_clearance_revocation",
            16,
        ),
        (
            "restart_write_model_configuration_manual_recovery_after_clearance_revocation",
            "_run_write_model_configuration_manual_recovery_restart",
            17,
        ),
        (
            "clear_write_model_configuration_manual_recovery",
            "_run_write_model_configuration_manual_recovery_clearance",
            18,
        ),
        (
            "verify_write_model_configuration_manual_recovery",
            "_run_write_model_configuration_manual_recovery_verification",
            19,
        ),
        (
            "recover_write_model_configuration",
            "_run_write_model_configuration_manual_recovery_application",
            20,
        ),
        # path-valued
        (
            "challenger_config_manual_recovery_receipt_input",
            "_run_write_model_configuration_manual_recovery_evidence",
            21,
        ),
        (
            "challenger_config_manual_recovery_plan_output",
            "_run_write_model_configuration_manual_recovery_plan",
            22,
        ),
        (
            "challenger_config_manual_recovery_approval_output",
            "_run_write_model_configuration_manual_recovery_approval",
            23,
        ),
    ]

    for _field, runner_attr, sentinel in _phase_a_runners:
        key = runner_attr
        sentinels[key] = sentinel
        call_counts[key] = 0

        def _make_runner(k: str = key, s: int = sentinel) -> _WriteRunnerProto:
            def _runner(
                *,
                args: argparse.Namespace | None = None,
                paths_config: WorkspaceConfig | None = None,
                execution_options: ExecutionOptions | _SentinelExecOptions | None = None,
            ) -> int:
                call_counts[k] += 1
                return s
            return _runner

        monkeypatch.setattr(
            f"dayu.cli.commands.write.{runner_attr}",
            _make_runner(),
        )

    # ---- Phase B runners（2 个）----
    _phase_b_runners: list[tuple[str, str, int]] = [
        ("apply_write_model_configuration", "_run_write_model_configuration_application", 30),
        ("rollback_write_model_configuration", "_run_write_model_configuration_rollback", 31),
    ]

    for _field, runner_attr, sentinel in _phase_b_runners:
        key = runner_attr
        sentinels[key] = sentinel
        call_counts[key] = 0

        def _make_runner_b(k: str = key, s: int = sentinel) -> _WriteRunnerProto:
            def _runner(
                *,
                args: argparse.Namespace | None = None,
                paths_config: WorkspaceConfig | None = None,
                execution_options: ExecutionOptions | _SentinelExecOptions | None = None,
            ) -> int:
                call_counts[k] += 1
                return s
            return _runner

        monkeypatch.setattr(
            f"dayu.cli.commands.write.{runner_attr}",
            _make_runner_b(),
        )

    # ---- _resolve_write_model_override_name ----
    monkeypatch.setattr(
        "dayu.cli.commands.write._resolve_write_model_override_name",
        lambda _a: "test-model",
    )

    # ---- recovery gate ----
    monkeypatch.setattr(
        "dayu.cli.commands.write._check_write_model_configuration_manual_recovery_gate",
        lambda **kw: 0,
    )

    return call_counts, sentinels, beo_calls


def _install_phase_h_mocks(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """安装抵达 Phase H 所需的最小真实入口依赖替身。

    Args:
        monkeypatch: pytest 属性替换工具。

    Returns:
        收集 ``Log.error`` 消息的可变列表。

    Raises:
        本函数不显式抛出异常。
    """

    _install_write_baseline_mocks(monkeypatch)
    sentinel = _SentinelExecOptions()
    fins_runtime = _SentinelFinsRuntime()
    errors: list[str] = []
    monkeypatch.setattr(
        write_command_module,
        "_prepare_cli_host_dependencies",
        lambda **_kwargs: (sentinel, sentinel, sentinel, sentinel, fins_runtime),
    )
    monkeypatch.setattr(
        write_command_module.RunningConfig,
        "from_resolved",
        lambda _resolved: sentinel,
    )
    monkeypatch.setattr(write_command_module, "_build_write_service", lambda **_kwargs: sentinel)
    monkeypatch.setattr(
        write_command_module,
        "_resolve_write_company_name",
        lambda **_kwargs: "Apple Inc.",
    )
    monkeypatch.setattr(
        write_command_module,
        "_resolve_write_output_dir",
        lambda **_kwargs: Path("/tmp/write-output"),
    )
    monkeypatch.setattr(
        write_command_module,
        "_needs_auto_research_bootstrap",
        lambda _args, **_kwargs: False,
    )
    monkeypatch.setattr(write_command_module, "setup_write_config", lambda *_args: sentinel)
    monkeypatch.setattr(
        write_command_module,
        "_build_write_run_config",
        lambda **_kwargs: argparse.Namespace(output_dir="/tmp/write-output"),
    )
    monkeypatch.setattr(
        write_command_module.Log,
        "error",
        lambda message, **_kwargs: errors.append(str(message)),
    )
    return errors


def _make_rt_args(action: str) -> DayuCliArguments:
    """构造 research-template 命令的 Dayu 参数对象。

    Args:
        action: 待分派的 research-template action。

    Returns:
        仅写入 selector 字段的 Dayu 参数对象。

    Raises:
        本函数不显式抛出异常。
    """

    return DayuCliArguments(research_template_action=action)


def _raise_research_template_error(
    args: DayuCliArguments,
    *,
    error: FileNotFoundError | FileExistsError | ValueError,
) -> int:
    """让 mapping runner 抛出指定的入口可转换异常。

    Args:
        args: 入口传入的 Dayu 参数对象。
        error: 需要由 runner 抛出的已知异常。

    Returns:
        本函数不会正常返回。

    Raises:
        FileNotFoundError: ``error`` 为文件不存在异常时抛出。
        FileExistsError: ``error`` 为文件已存在异常时抛出。
        ValueError: ``error`` 为输入校验异常时抛出。
    """

    del args
    raise error


def _raise_challenger_plan_error(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
    write_model_override_name: str,
    error: FileExistsError | FileNotFoundError | OSError | TypeError | ValueError,
) -> dict[str, ModelConfigJsonValue]:
    """从 Challenger 计划构造边界抛出指定异常。

    Args:
        args: 写作命令参数。
        paths_config: 写作工作区配置。
        write_model_override_name: 当前模型覆盖名称。
        error: 需要抛出的计划构造异常。

    Returns:
        本函数不会正常返回。

    Raises:
        FileExistsError: ``error`` 为目标已存在异常时抛出。
        FileNotFoundError: ``error`` 为输入不存在异常时抛出。
        OSError: ``error`` 为文件系统异常时抛出。
        TypeError: ``error`` 为类型异常时抛出。
        ValueError: ``error`` 为值异常时抛出。
    """

    del args, paths_config, write_model_override_name
    raise error


def _raise_challenger_config_error(
    *,
    args: argparse.Namespace,
    champion_config: argparse.Namespace,
    message: str,
) -> argparse.Namespace:
    """从 Challenger 配置构造边界抛出值异常。

    Args:
        args: 写作命令参数。
        champion_config: 当前 Champion 配置替身。
        message: 需要抛出的错误消息。

    Returns:
        本函数不会正常返回。

    Raises:
        ValueError: 始终使用 ``message`` 抛出。
    """

    del args, champion_config
    raise ValueError(message)


def _raise_materialize_error(
    args: argparse.Namespace,
    *,
    workspace_dir: Path,
    ticker: str,
    write_output_dir: Path,
    message: str,
) -> dict[str, ModelConfigJsonValue]:
    """从写后研究物化边界抛出代表性运行时异常。

    Args:
        args: 写作命令参数。
        workspace_dir: 写作工作区目录。
        ticker: 股票代码。
        write_output_dir: 已生成报告的输出目录。
        message: 需要抛出的错误消息。

    Returns:
        本函数不会正常返回。

    Raises:
        RuntimeError: 始终使用 ``message`` 抛出。
    """

    del args, workspace_dir, ticker, write_output_dir
    raise RuntimeError(message)


# ============================================================================
# A. _canonical_json str 变体
# ============================================================================


class TestCanonicalJsonStr:
    """验证迁移后的 canonical JSON str 固定 corpus。"""

    @pytest.mark.unit
    def test_null_serializes_to_null(self) -> None:
        """null -> "null"。"""
        assert canonical_json_str(None) == "null"

    @pytest.mark.unit
    def test_empty_dict_serializes(self) -> None:
        """空 dict -> "{}"。"""
        assert canonical_json_str({}) == "{}"

    @pytest.mark.unit
    def test_sort_keys_is_deterministic(self) -> None:
        """排序键确保输出确定性。"""
        result = canonical_json_str({"b": 1, "a": 2})
        assert result == '{"a":2,"b":1}'

    @pytest.mark.unit
    def test_nan_raises_value_error(self) -> None:
        """allow_nan=False -> NaN 引发 ValueError。"""
        with pytest.raises(ValueError, match="Out of range float"):
            canonical_json_str(float("nan"))


# ============================================================================
# B. _canonical_json bytes 变体
# ============================================================================


class TestCanonicalJsonBytes:
    """验证迁移后的 canonical JSON bytes 固定 corpus。"""

    @pytest.mark.unit
    def test_empty_dict_returns_empty_object_bytes(self) -> None:
        """空 dict -> b"{}"。"""
        assert canonical_json_bytes({}) == b"{}"

    @pytest.mark.unit
    def test_nested_dict_serializes_correctly(self) -> None:
        """嵌套 dict -> 正确 UTF-8 bytes。"""
        result = canonical_json_bytes({"x": {"y": 1}})
        assert result == b'{"x":{"y":1}}'

    @pytest.mark.unit
    def test_proxy_mapping_works(self) -> None:
        """MappingProxyType 同样可用。"""
        payload: Mapping[str, ModelConfigJsonValue] = MappingProxyType({"z": "v"})
        assert canonical_json_bytes(payload) == b'{"z":"v"}'


# ============================================================================
# C. _validated_fingerprint 两异常文本族
# ============================================================================


class TestValidatedFingerprintErrorTexts:
    """验证 str 系 vs bytes 系 _validated_fingerprint 的错误文本差异。"""

    @pytest.mark.unit
    def test_str_variant_uses_must_be_sha256_fingerprint(self) -> None:
        """str 系错误文本为 "must be a sha256 fingerprint"。"""
        with pytest.raises(ValueError, match="must be a sha256 fingerprint"):
            validated_fingerprint(
                "not-a-fingerprint",
                name="test_field",
            )

    @pytest.mark.unit
    def test_bytes_variant_uses_must_use_sha256(self) -> None:
        """bytes 系错误文本为 "must use sha256"。"""
        from dayu.services.write_model_configuration_application import _validated_fingerprint

        with pytest.raises(ValueError, match="must use sha256"):
            _validated_fingerprint("not-sha256-prefixed", name="test_field")


# ============================================================================
# D. _parse_utc offset 差异（锁定 defer）
# ============================================================================


class TestParseUtcOffset:
    """确认 _parse_utc 变体 a 正确处理 offset，锁定 defer 决策。"""

    @pytest.mark.unit
    def test_variant_a_correctly_handles_z_suffix(self) -> None:
        """变体 a: fromisoformat 替换 Z 后 astimezone(UTC)。"""
        from dayu.services.write_model_configuration_application import _parse_utc

        result = _parse_utc("2024-01-15T10:30:00Z", name="ts")
        assert result.tzinfo is not None
        assert result == datetime(2024, 1, 15, 10, 30, tzinfo=UTC)

    @pytest.mark.unit
    def test_variant_a_rejects_missing_timezone(self) -> None:
        """变体 a: 缺少时区的输入->ValueError。"""
        from dayu.services.write_model_configuration_application import _parse_utc

        with pytest.raises(ValueError, match="must include a timezone"):
            _parse_utc("2024-01-15T10:30:00", name="ts")

    @pytest.mark.unit
    def test_all_parse_utc_functions_in_write_models_are_variant_a(self) -> None:
        """确认当前代码库所有 write_model_* 的 _parse_utc 均为变体 a。

        变体 a 特征: astimezone(UTC)（将 offset 正确转换为 UTC）。
        变体 b（fromisoformat(text).replace(tzinfo=UTC)）不存在于当前代码库，
        锁定 defer 决策成立。
        """
        import inspect

        from dayu.services import write_model_challenger_preflight_approval as mod_c
        from dayu.services import write_model_challenger_run_approval as mod_d
        from dayu.services import write_model_configuration_application as mod_a
        from dayu.services import write_model_configuration_manual_recovery as mod_b

        modules = [mod_a, mod_b, mod_c, mod_d]
        for mod in modules:
            for name in dir(mod):
                if "parse_utc" in name and not name.startswith("__"):
                    func = getattr(mod, name)
                    if callable(func):
                        src = inspect.getsource(func)
                        assert "astimezone(UTC)" in src, (
                            f"{mod.__name__}.{name} 缺少 astimezone(UTC) -> 非变体 a"
                        )
                        assert "replace(tzinfo" not in src, (
                            f"{mod.__name__}.{name} 使用 replace(tzinfo=...) -> 变体 b，"
                            "与 defer 预期不符"
                        )


# ============================================================================
# F. CLI 混合 flag 优先级矩阵
# ============================================================================


class TestCliMixedFlagPriority:
    """验证 write if-chain 中 flag 优先级顺序。"""

    @pytest.mark.unit
    def test_revalidate_before_inspect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """revalidate 分支在 inspect 分支之前 --- 同时置 true 时 revalidate 胜出。"""
        call_counts, sentinels, _beo = _install_write_baseline_mocks(monkeypatch)
        args = _make_write_args(
            revalidate_write_model_configuration_manual_recovery_incident_dossier=True,
            inspect_write_model_configuration_manual_recovery_incident=True,
        )
        exit_code = run_write_command(args)
        assert exit_code == sentinels[
            "_run_write_model_configuration_manual_recovery_incident_dossier_revalidation"
        ]
        assert call_counts["_run_write_model_configuration_manual_recovery_incident_dossier_revalidation"] == 1
        assert call_counts["_run_write_model_configuration_manual_recovery_incident_dossier"] == 0

    @pytest.mark.unit
    def test_path_arg_over_bool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """verify bool 在 receipt_input path 之前；同时置值时 verify 先命中。"""
        call_counts, sentinels, _beo = _install_write_baseline_mocks(monkeypatch)
        args = _make_write_args(
            challenger_config_manual_recovery_receipt_input="/tmp/receipt.json",
            verify_write_model_configuration_manual_recovery=True,
        )
        exit_code = run_write_command(args)
        assert exit_code == sentinels["_run_write_model_configuration_manual_recovery_verification"]
        assert call_counts["_run_write_model_configuration_manual_recovery_verification"] == 1
        assert call_counts["_run_write_model_configuration_manual_recovery_evidence"] == 0

    @pytest.mark.unit
    def test_summary_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """summary=True 且无其他 dispatch flag 时进入 Phase G summary 路径。

        验证 summary flag 不会被 Phase A/B 的 dispatch 误捕获：
        即所有 runner 计数为 0，函数至少运行到 summary 分支。
        """
        call_counts, _sentinels, _beo = _install_write_baseline_mocks(monkeypatch)
        monkeypatch.setattr(
            "dayu.cli.commands.write._resolve_write_output_dir",
            lambda **kw: Path("/tmp/out"),
        )
        monkeypatch.setattr(
            "dayu.cli.commands.write.WriteService.print_report",
            lambda *a, **kw: 42,
        )
        args = _make_write_args(summary=True)
        exit_code = run_write_command(args)
        for key in call_counts:
            assert call_counts[key] == 0, f"runner {key} 不应被调用但被调用了 {call_counts[key]} 次"
        assert exit_code == 42

    @pytest.mark.unit
    def test_default_execution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 dispatch flag 且 summary=False 时进入 Phase H 默认执行。

        验证 _prepare_cli_host_dependencies 被调用（隔离 host/fs），
        且所有 Phase A/B runner 均未被调用。
        """
        call_counts, _sentinels, _beo = _install_write_baseline_mocks(monkeypatch)
        host_deps_called: list[bool] = []

        def _track_host_deps(
            workspace_config: WorkspaceConfig,
            execution_options: ExecutionOptions,
            interactive: bool = False,
        ) -> Never:
            host_deps_called.append(True)
            raise RuntimeError("host deps 不应在单元测试中真实执行")

        monkeypatch.setattr(
            "dayu.cli.commands.write._prepare_cli_host_dependencies",
            _track_host_deps,
        )

        args = _make_write_args(summary=False, preflight_only=False)
        with pytest.raises(RuntimeError, match="host deps"):
            run_write_command(args)

        assert len(host_deps_called) == 1, (
            "default execution 应调用 _prepare_cli_host_dependencies 1 次"
        )
        for key in call_counts:
            assert call_counts[key] == 0, (
                f"default execution 不应调用任何 Phase A/B runner，"
                f"{key} 被调用了 {call_counts[key]} 次"
            )


# ============================================================================
# G. monkeypatch 路径契约
# ============================================================================


class TestMonkeypatchPathContract:
    """锁定 monkeypatch 路径契约，防止未来代码移动破坏下游测试。"""

    @pytest.mark.unit
    def test_write_private_imports_preserve_function_identity(self) -> None:
        """确认五个仍由 write 使用的顶层 import 与真实定义保持对象同一性。

        Args:
            self: 当前测试实例。

        Returns:
            无。

        Raises:
            AssertionError: 任一 write 顶层绑定不是新模块中的真实函数对象。
        """

        assert (
            write_command_module._resolve_write_model_override_name
            is write_config_helpers._resolve_write_model_override_name
        )
        assert (
            write_command_module._resolve_write_company_name
            is write_config_helpers._resolve_write_company_name
        )
        assert (
            write_command_module._build_write_run_config
            is write_config_helpers._build_write_run_config
        )
        assert (
            write_command_module._challenger_requested
            is write_params_validation._challenger_requested
        )
        assert (
            write_command_module._validate_research_materialization_args
            is write_params_validation._validate_research_materialization_args
        )


    @pytest.mark.unit
    def test_write_runner_imports_preserve_function_identity(self) -> None:
        """确认十七个功能性 runner 顶层绑定与真实 owner 保持对象同一性。

        Args:
            self: 当前测试实例。

        Returns:
            无。

        Raises:
            AssertionError: 任一 write 顶层绑定不是新模块中的真实函数对象。
        """

        assert write_command_module._run_write_stage is write_execution._run_write_stage
        assert write_command_module._run_write_preflight is write_execution._run_write_preflight
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_evidence
            is write_manual_recovery._run_write_model_configuration_manual_recovery_evidence
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_plan
            is write_manual_recovery._run_write_model_configuration_manual_recovery_plan
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_approval
            is write_manual_recovery._run_write_model_configuration_manual_recovery_approval
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_application
            is write_manual_recovery._run_write_model_configuration_manual_recovery_application
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_verification
            is write_manual_recovery._run_write_model_configuration_manual_recovery_verification
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_clearance
            is write_manual_recovery._run_write_model_configuration_manual_recovery_clearance
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_clearance_revocation
            is write_manual_recovery._run_write_model_configuration_manual_recovery_clearance_revocation
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_restart
            is write_manual_recovery._run_write_model_configuration_manual_recovery_restart
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_gate_check
            is write_manual_recovery._run_write_model_configuration_manual_recovery_gate_check
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_gate_verification
            is write_manual_recovery._run_write_model_configuration_manual_recovery_gate_verification
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_gate_revalidation
            is write_manual_recovery._run_write_model_configuration_manual_recovery_gate_revalidation
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_audit_timeline
            is write_manual_recovery._run_write_model_configuration_manual_recovery_audit_timeline
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_incident_dossier
            is write_manual_recovery._run_write_model_configuration_manual_recovery_incident_dossier
        )
        assert (
            write_command_module._run_write_model_configuration_manual_recovery_incident_dossier_revalidation
            is write_manual_recovery._run_write_model_configuration_manual_recovery_incident_dossier_revalidation
        )
        assert (
            write_command_module._check_write_model_configuration_manual_recovery_gate
            is write_manual_recovery._check_write_model_configuration_manual_recovery_gate
        )

    @pytest.mark.unit
    def test_write_challenger_and_rollback_imports_preserve_identity(self) -> None:
        """确认十一项 Challenger 与回滚功能绑定指向真实 owner。

        Args:
            self: 当前测试实例。

        Returns:
            无。

        Raises:
            AssertionError: 任一 ``write`` 功能绑定不是新 owner 中的同一函数对象。
        """

        assert (
            write_command_module._assert_challenger_run_output_boundaries
            is write_challenger._assert_challenger_run_output_boundaries
        )
        assert (
            write_command_module._build_auto_bootstrap_args
            is write_challenger._build_auto_bootstrap_args
        )
        assert (
            write_command_module._build_challenger_run_plan_from_args
            is write_challenger._build_challenger_run_plan_from_args
        )
        assert (
            write_command_module._build_challenger_write_config
            is write_challenger._build_challenger_write_config
        )
        assert (
            write_command_module._needs_auto_research_bootstrap
            is write_challenger._needs_auto_research_bootstrap
        )
        assert (
            write_command_module._persist_challenger_run_authorization_after_preflight
            is write_challenger._persist_challenger_run_authorization_after_preflight
        )
        assert (
            write_command_module._preflight_champion_and_challenger
            is write_challenger._preflight_champion_and_challenger
        )
        assert (
            write_command_module._run_champion_challenger_experiment
            is write_challenger._run_champion_challenger_experiment
        )
        assert (
            write_command_module._verify_and_consume_challenger_run_approval_before_host
            is write_challenger._verify_and_consume_challenger_run_approval_before_host
        )
        assert (
            write_command_module._verify_challenger_preflight_approval_before_host
            is write_challenger._verify_challenger_preflight_approval_before_host
        )
        assert (
            write_command_module._run_write_model_configuration_rollback
            is write_config_rollback._run_write_model_configuration_rollback
        )


    @pytest.mark.unit
    def test_write_challenger_owner_controls_real_run_command(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """确认 write owner 控制真实 run_write_command 的 Challenger 分支。

        Args:
            self: 当前测试实例。
            monkeypatch: pytest 属性替换工具。

        Returns:
            无。

        Raises:
            AssertionError: 真实命令未读取 write 模块中的 patched binding。
        """

        _install_write_baseline_mocks(monkeypatch)
        requested_args: list[argparse.Namespace] = []

        def _requested(args: argparse.Namespace) -> bool:
            """记录真实命令传入的参数并启用 Challenger 分支。

            Args:
                args: 真实命令传入的参数对象。

            Returns:
                固定返回 True。

            Raises:
                本函数不显式抛出异常。
            """

            requested_args.append(args)
            return True

        def _approval_result(
            *,
            args: argparse.Namespace,
            write_model_override_name: str,
        ) -> int:
            """终止真实命令于共同 preflight 审批边界。

            Args:
                args: 真实命令传入的参数对象。
                write_model_override_name: 已解析的主模型覆盖名。

            Returns:
                用于确认命中审批分支的固定退出码。

            Raises:
                本函数不显式抛出异常。
            """

            assert args is requested_args[-1]
            assert write_model_override_name == "test-model"
            return 47

        monkeypatch.setattr(write_command_module, "_challenger_requested", _requested)
        monkeypatch.setattr(
            write_command_module,
            "_verify_challenger_preflight_approval_before_host",
            _approval_result,
        )
        args = _make_write_args(preflight_only=True)

        assert run_write_command(args) == 47
        assert requested_args == [args]

    @pytest.mark.unit
    def test_params_challenger_owner_controls_real_validator(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """确认 params owner 控制真实研究物化 validator 的内部调用。

        Args:
            self: 当前测试实例。
            monkeypatch: pytest 属性替换工具。

        Returns:
            无。

        Raises:
            AssertionError: 真实 validator 未读取 params 模块中的 patched binding。
        """

        requested_args: list[argparse.Namespace] = []

        def _requested(args: argparse.Namespace) -> bool:
            """记录 validator 参数并模拟 Challenger 已请求。

            Args:
                args: 真实 validator 传入的参数对象。

            Returns:
                固定返回 True。

            Raises:
                本函数不显式抛出异常。
            """

            requested_args.append(args)
            return True

        monkeypatch.setattr(
            write_params_validation,
            "_challenger_requested",
            _requested,
        )
        args = argparse.Namespace(preflight_only=True, summary=False)

        assert (
            write_params_validation._validate_research_materialization_args(args)
            == "Champion/Challenger 共同 preflight 需要提供 --routing-preflight-approval-input"
        )
        assert requested_args == [args]

    @pytest.mark.unit
    def test_write_service_top_level_import_in_write_py_is_stable(self) -> None:
        """确认 WriteService 在 write.py 中的顶层 import 路径稳定。

        test_cli_running_config.py 依赖此路径进行 monkeypatch。
        """
        import dayu.cli.commands.write as write_mod
        from dayu.services.write_service import WriteService

        assert write_mod.WriteService is WriteService, (
            "write.py 中的 WriteService 必须指向 dayu.services.write_service.WriteService，"
            "test_cli_running_config.py 依赖 monkeypatch.setattr("
            "'dayu.cli.commands.write.WriteService.print_report', ...)"
        )


# ============================================================================
# H. 惰性计算 / 阶段顺序
# ============================================================================


class TestLazyComputePhaseOrder:
    """验证 _build_execution_options 的惰性计算和 phase 间调用顺序。"""

    @pytest.mark.unit
    def test_early_recovery_does_not_call_resolve_model_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Phase A 命中时不应调用 _resolve_write_model_override_name。"""
        _call_counts, _sentinels, _beo = _install_write_baseline_mocks(monkeypatch)
        resolve_called: list[bool] = []

        def _track_resolve(args: argparse.Namespace) -> str:
            resolve_called.append(True)
            return "tracked"

        monkeypatch.setattr(
            "dayu.cli.commands.write._resolve_write_model_override_name",
            _track_resolve,
        )

        args = _make_write_args(
            revalidate_write_model_configuration_manual_recovery_incident_dossier=True,
        )
        run_write_command(args)
        assert not resolve_called, (
            "Phase A 命中时不应调用 _resolve_write_model_override_name"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("flag,runner_key", [
        ("clear_write_model_configuration_manual_recovery",
         "_run_write_model_configuration_manual_recovery_clearance"),
        ("verify_write_model_configuration_manual_recovery",
         "_run_write_model_configuration_manual_recovery_verification"),
        ("recover_write_model_configuration",
         "_run_write_model_configuration_manual_recovery_application"),
    ])
    def test_clear_verify_recover_call_build_execution_options_inline(
        self, monkeypatch: pytest.MonkeyPatch, flag: str, runner_key: str
    ) -> None:
        """clear/verify/recover 在 dispatch 分支内调用 _build_execution_options。

        在当前代码中这三个分支以 execution_options=_build_execution_options(args)
        作为关键字参数传给 runner。验证 build=1。
        """
        call_counts, sentinels, beo = _install_write_baseline_mocks(monkeypatch)
        args = _make_write_args(**{flag: True})
        exit_code = run_write_command(args)
        assert exit_code == sentinels[runner_key]
        assert call_counts[runner_key] == 1
        assert len(beo) == 1, (
            f"clear/verify/recover ({flag}) 应在分支内调用 _build_execution_options 1 次，"
            f"实际 {len(beo)} 次"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("flag,runner_key", [
        ("challenger_config_manual_recovery_receipt_input",
         "_run_write_model_configuration_manual_recovery_evidence"),
        ("challenger_config_manual_recovery_plan_output",
         "_run_write_model_configuration_manual_recovery_plan"),
        ("challenger_config_manual_recovery_approval_output",
         "_run_write_model_configuration_manual_recovery_approval"),
    ])
    def test_path_runners_do_not_call_build_execution_options(
        self, monkeypatch: pytest.MonkeyPatch, flag: str, runner_key: str
    ) -> None:
        """Phase A path runner 不调用 _build_execution_options（build=0）。"""
        call_counts, sentinels, beo = _install_write_baseline_mocks(monkeypatch)
        args = _make_write_args(**{flag: "/tmp/some/path"})
        exit_code = run_write_command(args)
        assert exit_code == sentinels[runner_key]
        assert call_counts[runner_key] == 1
        assert len(beo) == 0, (
            f"path runner ({flag}) 不应调用 _build_execution_options，"
            f"实际 {len(beo)} 次"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("flag,runner_key", [
        ("apply_write_model_configuration",
         "_run_write_model_configuration_application"),
        ("rollback_write_model_configuration",
         "_run_write_model_configuration_rollback"),
    ])
    def test_apply_rollback_use_precomputed_execution_options(
        self, monkeypatch: pytest.MonkeyPatch, flag: str, runner_key: str
    ) -> None:
        """Phase B apply/rollback 在 run_write_command 中预计算 _build_execution_options。

        build=1 且 runner 不重算。
        """
        call_counts, sentinels, beo = _install_write_baseline_mocks(monkeypatch)
        args = _make_write_args(**{flag: True})
        exit_code = run_write_command(args)
        assert exit_code == sentinels[runner_key]
        assert call_counts[runner_key] == 1
        assert len(beo) == 1, (
            f"Phase B ({flag}) 应预计算 _build_execution_options 1 次，"
            f"实际 {len(beo)} 次"
        )

    @pytest.mark.unit
    def test_recovery_gate_after_config_before_challenger(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Phase C recovery gate 应在 Phase B 未命中后、Phase D challenger 之前执行。"""
        _call_counts, _sentinels, _beo = _install_write_baseline_mocks(monkeypatch)
        gate_calls: list[bool] = []

        def _track_gate(paths_config: WorkspaceConfig) -> int:
            gate_calls.append(True)
            return 2

        monkeypatch.setattr(
            "dayu.cli.commands.write._check_write_model_configuration_manual_recovery_gate",
            _track_gate,
        )

        args = _make_write_args(summary=False, preflight_only=False)
        exit_code = run_write_command(args)
        assert len(gate_calls) == 1
        assert exit_code == 2

    @pytest.mark.unit
    def test_summary_path_does_not_resolve_non_summary_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """summary=True 时不应调用 Phase H 的 write execution 路径。

        monkeypatch _prepare_cli_host_dependencies/_run_write_stage 若被调用即失败，
        验证 summary 只走自身的 print_report 路径。
        """
        _call_counts, _sentinels, _beo = _install_write_baseline_mocks(monkeypatch)

        def _make_fail(name: str) -> _WriteRunnerProto:
            def _fail(
                *,
                args: argparse.Namespace | None = None,
                paths_config: WorkspaceConfig | None = None,
                execution_options: ExecutionOptions | _SentinelExecOptions | None = None,
            ) -> int:
                pytest.fail(f"summary 路径不应调用 {name}")
            return _fail

        monkeypatch.setattr(
            "dayu.cli.commands.write._prepare_cli_host_dependencies",
            _make_fail("_prepare_cli_host_dependencies"),
        )
        monkeypatch.setattr(
            "dayu.cli.commands.write._run_write_stage",
            _make_fail("_run_write_stage"),
        )
        monkeypatch.setattr(
            "dayu.cli.commands.write._resolve_write_output_dir",
            lambda **kw: Path("/tmp/out"),
        )
        monkeypatch.setattr(
            "dayu.cli.commands.write.WriteService.print_report",
            lambda *a, **kw: 42,
        )

        args = _make_write_args(summary=True)
        exit_code = run_write_command(args)
        assert exit_code == 42, (
            f"summary 路径应返回 print_report 的 sentinel 42，实际 {exit_code}"
        )


# ============================================================================
# I-a. write phase-table 结构与集成契约（16 selectors）
# ============================================================================


class TestWritePhaseTableStructure:
    """验证 Protocol、不可变上下文、adapter 与 phase-table 的精确结构。"""

    WRITE_FIELDS: ClassVar[set[str]] = {
        "revalidate_write_model_configuration_manual_recovery_incident_dossier",
        "inspect_write_model_configuration_manual_recovery_incident",
        "audit_write_model_configuration_manual_recovery_history",
        "revalidate_write_model_configuration_manual_recovery_gate_verification",
        "verify_write_model_configuration_manual_recovery_gate",
        "check_write_model_configuration_manual_recovery_gate",
        "revoke_write_model_configuration_manual_recovery_clearance",
        "restart_write_model_configuration_manual_recovery_after_clearance_revocation",
        "clear_write_model_configuration_manual_recovery",
        "verify_write_model_configuration_manual_recovery",
        "recover_write_model_configuration",
        "apply_write_model_configuration",
        "rollback_write_model_configuration",
        "summary",
        "preflight_only",
        "reprice_costs",
        "challenger_config_manual_recovery_receipt_input",
        "challenger_config_manual_recovery_plan_output",
        "challenger_config_manual_recovery_approval_output",
        "routing_challenger_run_approval_input",
    }

    @pytest.mark.unit
    def test_protocol_and_dayu_fields_form_exact_union(self) -> None:
        """Write Protocol exact20 与 Dayu 终态 exact21 必须精确闭合。

        Args:
            self: 当前测试实例。

        Returns:
            无。

        Raises:
            AssertionError: 字段、继承、默认值或 structural conformance 漂移时抛出。
        """

        tree = ast.parse(Path("dayu/cli/arguments.py").read_text(encoding="utf-8"))
        classes = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        }
        research_fields = {
            node.target.id
            for node in classes["ResearchTemplateDispatchArguments"].body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        write_fields = {
            node.target.id
            for node in classes["WriteDispatchArguments"].body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        dayu_fields = {
            node.target.id
            for node in classes["DayuCliArguments"].body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }

        assert research_fields == {"research_template_action"}
        assert write_fields == self.WRITE_FIELDS
        assert len(write_fields) == 20
        assert dayu_fields == research_fields | write_fields
        assert len(dayu_fields) == 21
        dayu_class = classes["DayuCliArguments"]
        assert [ast.unparse(base) for base in dayu_class.bases] == ["argparse.Namespace"]
        assert all(
            node.value is None
            for node in dayu_class.body
            if isinstance(node, ast.AnnAssign)
        )
        assert not any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "__init__"
            for node in dayu_class.body
        )
        write_args: WriteDispatchArguments = _make_write_args()
        assert write_command_module._WRITE_PHASE_EARLY_RECOVERY[0].predicate(write_args) is False

    @pytest.mark.unit
    def test_dispatch_module_contains_exact_four_frozen_dataclasses(self) -> None:
        """dispatch owner 必须只定义四个 frozen dataclass 与精确字段。

        Args:
            self: 当前测试实例。

        Returns:
            无。

        Raises:
            AssertionError: class 数量、冻结属性、字段或函数 inventory 漂移时抛出。
        """

        del self
        tree = ast.parse(
            Path("dayu/cli/commands/_write_dispatch.py").read_text(encoding="utf-8")
        )
        classes = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        }
        expected_fields = {
            "_WriteCommandContext": ["args", "paths_config"],
            "_WriteConfigurationContext": [
                "args",
                "paths_config",
                "write_model_override_name",
                "execution_options",
            ],
            "_EarlyWriteSubcommandEntry": ["predicate", "runner"],
            "_ConfigurationWriteSubcommandEntry": ["predicate", "runner"],
        }

        assert set(classes) == set(expected_fields)
        assert not any(isinstance(node, ast.FunctionDef) for node in tree.body)
        for name, expected in expected_fields.items():
            class_node = classes[name]
            actual = [
                node.target.id
                for node in class_node.body
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
            ]
            assert actual == expected
            assert any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Name)
                and decorator.func.id == "dataclass"
                and any(
                    keyword.arg == "frozen"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in decorator.keywords
                )
                for decorator in class_node.decorator_list
            )

    @pytest.mark.unit
    def test_phase_tables_bind_exact_adapter_order(self) -> None:
        """14+2 phase tables 必须按 HEAD 优先级绑定 exact16 adapters。

        Args:
            self: 当前测试实例。

        Returns:
            无。

        Raises:
            AssertionError: 表长度、顺序或 adapter identity 漂移时抛出。
        """

        del self
        expected_early = (
            write_command_module._run_incident_dossier_revalidation_adapter,
            write_command_module._run_incident_dossier_adapter,
            write_command_module._run_audit_timeline_adapter,
            write_command_module._run_gate_revalidation_adapter,
            write_command_module._run_gate_verification_adapter,
            write_command_module._run_gate_check_adapter,
            write_command_module._run_clearance_revocation_adapter,
            write_command_module._run_restart_after_revocation_adapter,
            write_command_module._run_clearance_adapter,
            write_command_module._run_verification_adapter,
            write_command_module._run_evidence_adapter,
            write_command_module._run_plan_adapter,
            write_command_module._run_approval_adapter,
            write_command_module._run_recover_adapter,
        )
        expected_configuration = (
            write_command_module._run_apply_adapter,
            write_command_module._run_rollback_adapter,
        )

        assert tuple(
            entry.runner
            for entry in write_command_module._WRITE_PHASE_EARLY_RECOVERY
        ) == expected_early
        assert tuple(
            entry.runner
            for entry in write_command_module._WRITE_PHASE_CONFIGURATION
        ) == expected_configuration
        assert tuple(runner.__name__ for runner in expected_early) == (
            "_run_incident_dossier_revalidation_adapter",
            "_run_incident_dossier_adapter",
            "_run_audit_timeline_adapter",
            "_run_gate_revalidation_adapter",
            "_run_gate_verification_adapter",
            "_run_gate_check_adapter",
            "_run_clearance_revocation_adapter",
            "_run_restart_after_revocation_adapter",
            "_run_clearance_adapter",
            "_run_verification_adapter",
            "_run_evidence_adapter",
            "_run_plan_adapter",
            "_run_approval_adapter",
            "_run_recover_adapter",
        )

    @pytest.mark.unit
    def test_run_write_command_keeps_bounded_phase_order(self) -> None:
        """入口顺序必须保持 A loop、共享构造、B loop、后续阶段。

        Args:
            self: 当前测试实例。

        Returns:
            无。

        Raises:
            AssertionError: 顺序、adapter 数量或 phantom helper 出现时抛出。
        """

        del self
        source = Path("dayu/cli/commands/write.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        run_command = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "run_write_command"
        )
        phase_a_context_index = next(
            index
            for index, node in enumerate(run_command.body)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "phase_a_ctx"
                for target in node.targets
            )
        )
        phase_a_loop_index = next(
            index
            for index, node in enumerate(run_command.body)
            if isinstance(node, ast.For)
            and isinstance(node.iter, ast.Name)
            and node.iter.id == "_WRITE_PHASE_EARLY_RECOVERY"
        )
        override_index = next(
            index
            for index, node in enumerate(run_command.body)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "write_model_override_name"
                for target in node.targets
            )
        )
        execution_options_index = next(
            index
            for index, node in enumerate(run_command.body)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "execution_options"
                for target in node.targets
            )
        )
        phase_b_context_index = next(
            index
            for index, node in enumerate(run_command.body)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "phase_b_ctx"
                for target in node.targets
            )
        )
        phase_b_loop_index = next(
            index
            for index, node in enumerate(run_command.body)
            if isinstance(node, ast.For)
            and isinstance(node.iter, ast.Name)
            and node.iter.id == "_WRITE_PHASE_CONFIGURATION"
        )

        assert (
            phase_a_context_index
            < phase_a_loop_index
            < override_index
            < execution_options_index
            < phase_b_context_index
            < phase_b_loop_index
        )
        assert "_build_challenger_run_plan_if_required" not in source
        adapters = {
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name.endswith("_adapter")
        }
        assert len(adapters) == 16


class TestWritePhaseTableGroup1PhaseABool:
    """Group 1 --- Phase A boolean selectors（11 个）。"""

    PHASE_A_BOOL_PARAMS: ClassVar[list[tuple[str, str, bool]]] = [
        # (field_name, runner_key, calls_build_execution_options)
        (
            "revalidate_write_model_configuration_manual_recovery_incident_dossier",
            "_run_write_model_configuration_manual_recovery_incident_dossier_revalidation",
            False,
        ),
        (
            "inspect_write_model_configuration_manual_recovery_incident",
            "_run_write_model_configuration_manual_recovery_incident_dossier",
            False,
        ),
        (
            "audit_write_model_configuration_manual_recovery_history",
            "_run_write_model_configuration_manual_recovery_audit_timeline",
            False,
        ),
        (
            "revalidate_write_model_configuration_manual_recovery_gate_verification",
            "_run_write_model_configuration_manual_recovery_gate_revalidation",
            False,
        ),
        (
            "verify_write_model_configuration_manual_recovery_gate",
            "_run_write_model_configuration_manual_recovery_gate_verification",
            False,
        ),
        (
            "check_write_model_configuration_manual_recovery_gate",
            "_run_write_model_configuration_manual_recovery_gate_check",
            False,
        ),
        (
            "revoke_write_model_configuration_manual_recovery_clearance",
            "_run_write_model_configuration_manual_recovery_clearance_revocation",
            False,
        ),
        (
            "restart_write_model_configuration_manual_recovery_after_clearance_revocation",
            "_run_write_model_configuration_manual_recovery_restart",
            False,
        ),
        (
            "clear_write_model_configuration_manual_recovery",
            "_run_write_model_configuration_manual_recovery_clearance",
            True,  # build=1
        ),
        (
            "verify_write_model_configuration_manual_recovery",
            "_run_write_model_configuration_manual_recovery_verification",
            True,  # build=1
        ),
        (
            "recover_write_model_configuration",
            "_run_write_model_configuration_manual_recovery_application",
            True,  # build=1
        ),
    ]

    @pytest.mark.unit
    @pytest.mark.parametrize("field,runner_key,calls_beo", PHASE_A_BOOL_PARAMS)
    def test_phase_a_bool_selector_triggers_correct_runner(
        self,
        monkeypatch: pytest.MonkeyPatch,
        field: str,
        runner_key: str,
        calls_beo: bool,
    ) -> None:
        """每个 Phase A bool flag 触发对应 runner，其余 runner 不被调用。"""
        call_counts, sentinels, beo = _install_write_baseline_mocks(monkeypatch)
        args = _make_write_args(**{field: True})
        exit_code = run_write_command(args)

        assert exit_code == sentinels[runner_key], (
            f"{field} -> 期望 {runner_key}（sentinel={sentinels[runner_key]}），"
            f"实际 {exit_code}"
        )
        assert call_counts[runner_key] == 1, (
            f"{runner_key} 应被调用 1 次，实际 {call_counts[runner_key]} 次"
        )

        for other_key, count in call_counts.items():
            if other_key != runner_key:
                assert count == 0, (
                    f"{field} 触发时 {other_key} 不应被调用，实际 {count} 次"
                )

        if calls_beo:
            assert len(beo) == 1, (
                f"{field} 应在分支内调用 _build_execution_options 1 次"
            )
        else:
            assert len(beo) == 0, (
                f"{field} 不应调用 _build_execution_options，实际 {len(beo)} 次"
            )


class TestWritePhaseTableGroup2PhaseAPath:
    """Group 2 --- Phase A path-valued selectors（3 个）。"""

    PHASE_A_PATH_PARAMS: ClassVar[list[tuple[str, str]]] = [
        ("challenger_config_manual_recovery_receipt_input",
         "_run_write_model_configuration_manual_recovery_evidence"),
        ("challenger_config_manual_recovery_plan_output",
         "_run_write_model_configuration_manual_recovery_plan"),
        ("challenger_config_manual_recovery_approval_output",
         "_run_write_model_configuration_manual_recovery_approval"),
    ]

    @pytest.mark.unit
    @pytest.mark.parametrize("field,runner_key", PHASE_A_PATH_PARAMS)
    def test_nonempty_path_triggers_runner(
        self, monkeypatch: pytest.MonkeyPatch, field: str, runner_key: str
    ) -> None:
        """nonempty path -> runner 被调用，其余 runner 不被调用，build=0。"""
        call_counts, sentinels, beo = _install_write_baseline_mocks(monkeypatch)
        args = _make_write_args(**{field: "/tmp/some/path"})
        exit_code = run_write_command(args)

        assert exit_code == sentinels[runner_key]
        assert call_counts[runner_key] == 1
        for other_key, count in call_counts.items():
            if other_key != runner_key:
                assert count == 0, (
                    f"{field}='/tmp/some/path' 触发时 {other_key} 不应被调用"
                )
        assert len(beo) == 0, (
            f"path runner {field} 不应调用 _build_execution_options"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("field,runner_key", PHASE_A_PATH_PARAMS)
    def test_empty_path_does_not_trigger_runner(
        self, monkeypatch: pytest.MonkeyPatch, field: str, runner_key: str
    ) -> None:
        """empty/None path -> runner 不被调用。

        当 path 为空且所有 bool flag 也为 false 时 dispatch 链 fall-through
        到后续阶段。只要 runner 不被调用即为通过。
        """
        call_counts, _sentinels, _beo = _install_write_baseline_mocks(monkeypatch)
        monkeypatch.setattr(
            "dayu.cli.commands.write._resolve_write_output_dir",
            lambda **kw: Path("/tmp/out"),
        )
        monkeypatch.setattr(
            "dayu.cli.commands.write.WriteService.print_report",
            lambda *a, **kw: 99,
        )
        args = _make_write_args(**{field: None}, summary=True)
        run_write_command(args)
        assert call_counts[runner_key] == 0, (
            f"empty path {field}=None 不应触发 {runner_key}"
        )


class TestWritePhaseTableGroup3PhaseBBool:
    """Group 3 --- Phase B boolean selectors（2 个）。"""

    PHASE_B_BOOL_PARAMS: ClassVar[list[tuple[str, str]]] = [
        ("apply_write_model_configuration",
         "_run_write_model_configuration_application"),
        ("rollback_write_model_configuration",
         "_run_write_model_configuration_rollback"),
    ]

    @pytest.mark.unit
    @pytest.mark.parametrize("field,runner_key", PHASE_B_BOOL_PARAMS)
    def test_phase_b_bool_selector_triggers_correct_runner(
        self, monkeypatch: pytest.MonkeyPatch, field: str, runner_key: str
    ) -> None:
        """每个 Phase B bool flag 触发对应 runner，build=1（预计算）。"""
        call_counts, sentinels, beo = _install_write_baseline_mocks(monkeypatch)
        args = _make_write_args(**{field: True})
        exit_code = run_write_command(args)

        assert exit_code == sentinels[runner_key], (
            f"{field} -> 期望 {runner_key}，实际 {exit_code}"
        )
        assert call_counts[runner_key] == 1
        for other_key, count in call_counts.items():
            if other_key != runner_key:
                assert count == 0, (
                    f"{field} 触发时 {other_key} 不应被调用"
                )
        assert len(beo) == 1, (
            f"Phase B {field} 应预计算 _build_execution_options 1 次，"
            f"实际 {len(beo)} 次"
        )


class TestWritePhaseTableMixedPriority:
    """Mixed priority 独立保留。"""

    @pytest.mark.unit
    def test_summary_plus_apply_apply_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """summary=True + apply=True -> apply runner 被调用，summary 路径不被进入。"""
        call_counts, sentinels, _beo = _install_write_baseline_mocks(monkeypatch)
        args = _make_write_args(summary=True, apply_write_model_configuration=True)
        exit_code = run_write_command(args)
        assert exit_code == sentinels["_run_write_model_configuration_application"]
        assert call_counts["_run_write_model_configuration_application"] == 1


# ============================================================================
# I-b. write Phase E/F/H 保留契约
# ============================================================================


class TestWriteRetainedPhaseContracts:
    """验证 bounded replacement 外的 Phase E/F/H 关键行为保持不变。"""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "required_field",
        (
            "routing_challenger_run_plan_output",
            "routing_challenger_run_approval_request",
            "routing_challenger_run_approval_output",
            "routing_challenger_run_approval_input",
        ),
    )
    def test_phase_e_required_field_builds_and_validates_once(
        self,
        monkeypatch: pytest.MonkeyPatch,
        required_field: str,
    ) -> None:
        """Phase E 任一 required 字段非空时必须构造并验证计划各一次。

        Args:
            self: 当前测试实例。
            monkeypatch: pytest 属性替换工具。
            required_field: 当前置为非空的 Phase E 字段。

        Returns:
            无。

        Raises:
            AssertionError: build、boundary 或后续返回次数发生漂移时抛出。
        """

        _install_write_baseline_mocks(monkeypatch)
        plan: dict[str, ModelConfigJsonValue] = {}
        build_calls: list[int] = []
        boundary_calls: list[int] = []
        monkeypatch.setattr(
            write_command_module,
            "_build_challenger_run_plan_from_args",
            lambda **_kwargs: (build_calls.append(1), plan)[1],
        )
        monkeypatch.setattr(
            write_command_module,
            "_assert_challenger_run_output_boundaries",
            lambda **_kwargs: boundary_calls.append(1),
        )
        monkeypatch.setattr(
            write_command_module,
            "_verify_and_consume_challenger_run_approval_before_host",
            lambda **_kwargs: 0,
        )
        monkeypatch.setattr(
            write_command_module,
            "_resolve_write_output_dir",
            lambda **_kwargs: Path("/tmp/write-output"),
        )
        monkeypatch.setattr(write_command_module.WriteService, "print_report", lambda *_args, **_kwargs: 0)
        args = _make_write_args(summary=True, **{required_field: "/tmp/required.json"})

        assert run_write_command(args) == 0
        assert build_calls == [1]
        assert boundary_calls == [1]

    @pytest.mark.unit
    def test_phase_e_empty_inventory_skips_build_and_boundary(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Phase E 四字段全空时不得构造或验证 Challenger 计划。

        Args:
            self: 当前测试实例。
            monkeypatch: pytest 属性替换工具。

        Returns:
            无。

        Raises:
            AssertionError: 空 inventory 仍调用 build 或 boundary 时抛出。
        """

        del self
        _install_write_baseline_mocks(monkeypatch)
        build_calls: list[int] = []
        boundary_calls: list[int] = []
        monkeypatch.setattr(
            write_command_module,
            "_build_challenger_run_plan_from_args",
            lambda **_kwargs: build_calls.append(1),
        )
        monkeypatch.setattr(
            write_command_module,
            "_assert_challenger_run_output_boundaries",
            lambda **_kwargs: boundary_calls.append(1),
        )
        monkeypatch.setattr(
            write_command_module,
            "_resolve_write_output_dir",
            lambda **_kwargs: Path("/tmp/write-output"),
        )
        monkeypatch.setattr(write_command_module.WriteService, "print_report", lambda *_args, **_kwargs: 0)

        assert run_write_command(_make_write_args(summary=True)) == 0
        assert build_calls == []
        assert boundary_calls == []

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "error",
        (
            FileExistsError("exists"),
            FileNotFoundError("missing"),
            OSError("io"),
            TypeError("type"),
            ValueError("value"),
        ),
    )
    def test_phase_e_five_errors_return_two_with_exact_log(
        self,
        monkeypatch: pytest.MonkeyPatch,
        error: FileExistsError | FileNotFoundError | OSError | TypeError | ValueError,
    ) -> None:
        """Phase E 五类计划异常必须记录原消息并转换为退出码 2。

        Args:
            self: 当前测试实例。
            monkeypatch: pytest 属性替换工具。
            error: 当前模拟的计划构造异常。

        Returns:
            无。

        Raises:
            AssertionError: 异常映射、日志或退出码漂移时抛出。
        """

        del self
        _install_write_baseline_mocks(monkeypatch)
        errors: list[str] = []
        monkeypatch.setattr(
            write_command_module,
            "_build_challenger_run_plan_from_args",
            partial(_raise_challenger_plan_error, error=error),
        )
        monkeypatch.setattr(
            write_command_module.Log,
            "error",
            lambda message, **_kwargs: errors.append(str(message)),
        )
        args = _make_write_args(
            routing_challenger_run_plan_output="/tmp/plan.json",
        )

        assert run_write_command(args) == 2
        assert errors == [f"Challenger 双跑计划无效: {error}"]

    @pytest.mark.unit
    def test_phase_f_keeps_fail_loud_plan_assertion(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """审批 selector 非空但计划为空时 Phase F 必须 fail-loud。

        Args:
            self: 当前测试实例。
            monkeypatch: pytest 属性替换工具。

        Returns:
            无。

        Raises:
            AssertionError: 计划不变量按契约触发，或被静默 guard 吞掉时测试失败。
        """

        del self
        _install_write_baseline_mocks(monkeypatch)
        monkeypatch.setattr(
            write_command_module,
            "_build_challenger_run_plan_from_args",
            lambda **_kwargs: None,
        )
        monkeypatch.setattr(
            write_command_module,
            "_assert_challenger_run_output_boundaries",
            lambda **_kwargs: None,
        )
        args = _make_write_args(
            routing_challenger_run_approval_input="/tmp/approval.json",
        )

        with pytest.raises(AssertionError):
            run_write_command(args)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "error",
        (
            FileNotFoundError("missing"),
            OSError("io"),
            TypeError("type"),
            ValueError("value"),
        ),
    )
    def test_phase_h_plan_rebuild_errors_return_two(
        self,
        monkeypatch: pytest.MonkeyPatch,
        error: FileNotFoundError | OSError | TypeError | ValueError,
    ) -> None:
        """Phase H 二次计划构造的四类异常必须转换为退出码 2。

        Args:
            self: 当前测试实例。
            monkeypatch: pytest 属性替换工具。
            error: 当前模拟的二次计划构造异常。

        Returns:
            无。

        Raises:
            AssertionError: 二次调用时序、错误日志或退出码漂移时抛出。
        """

        del self
        errors = _install_phase_h_mocks(monkeypatch)
        plan: dict[str, ModelConfigJsonValue] = {}
        build_calls: list[int] = []

        def _build_plan(
            *,
            args: argparse.Namespace,
            paths_config: WorkspaceConfig,
            write_model_override_name: str,
        ) -> dict[str, ModelConfigJsonValue]:
            """首次返回计划、第二次抛出当前复核异常。

            Args:
                args: 写作命令参数。
                paths_config: 写作工作区配置。
                write_model_override_name: 当前模型覆盖名称。

            Returns:
                首次调用返回固定计划。

            Raises:
                FileNotFoundError: 当前参数化异常为文件不存在时抛出。
                OSError: 当前参数化异常为文件系统错误时抛出。
                TypeError: 当前参数化异常为类型错误时抛出。
                ValueError: 当前参数化异常为值错误时抛出。
            """

            del args, paths_config, write_model_override_name
            build_calls.append(1)
            if len(build_calls) == 2:
                raise error
            return plan

        monkeypatch.setattr(write_command_module, "_challenger_requested", lambda _args: True)
        monkeypatch.setattr(write_command_module, "_build_challenger_run_plan_from_args", _build_plan)
        monkeypatch.setattr(
            write_command_module,
            "_assert_challenger_run_output_boundaries",
            lambda **_kwargs: None,
        )
        args = _make_write_args(
            routing_challenger_run_plan_output="/tmp/plan.json",
        )

        assert run_write_command(args) == 2
        assert build_calls == [1, 1]
        assert errors == [f"Challenger 双跑计划复核失败: {error}"]

    @pytest.mark.unit
    @pytest.mark.parametrize("preflight_only", (False, True))
    def test_phase_h_challenger_config_value_error_returns_two(
        self,
        monkeypatch: pytest.MonkeyPatch,
        preflight_only: bool,
    ) -> None:
        """preflight 与 main 两个 Challenger 配置错误边界必须保持一致。

        Args:
            self: 当前测试实例。
            monkeypatch: pytest 属性替换工具。
            preflight_only: 是否选择 preflight Challenger 调用点。

        Returns:
            无。

        Raises:
            AssertionError: 任一调用点未记录错误并返回 2 时抛出。
        """

        del self
        errors = _install_phase_h_mocks(monkeypatch)
        monkeypatch.setattr(write_command_module, "_challenger_requested", lambda _args: True)
        monkeypatch.setattr(
            write_command_module,
            "_verify_challenger_preflight_approval_before_host",
            lambda **_kwargs: 0,
        )
        monkeypatch.setattr(
            write_command_module,
            "_build_challenger_write_config",
            partial(_raise_challenger_config_error, message="invalid challenger config"),
        )
        args = _make_write_args(preflight_only=preflight_only)

        assert run_write_command(args) == 2
        assert errors == ["invalid challenger config"]

    @pytest.mark.unit
    def test_phase_h_materialize_exception_is_partial_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """写作成功后的物化异常必须记录为 partial-success 退出码 2。

        Args:
            self: 当前测试实例。
            monkeypatch: pytest 属性替换工具。

        Returns:
            无。

        Raises:
            AssertionError: 物化异常逃逸、日志或退出码漂移时抛出。
        """

        del self
        errors = _install_phase_h_mocks(monkeypatch)
        monkeypatch.setattr(write_command_module, "_challenger_requested", lambda _args: False)
        monkeypatch.setattr(write_command_module, "_run_write_stage", lambda **_kwargs: 0)
        monkeypatch.setattr(
            write_command_module,
            "_materialize_research_after_write",
            partial(_raise_materialize_error, message="materialize failed"),
        )
        args = _make_write_args(materialize_research=True)

        assert run_write_command(args) == 2
        assert errors == ["研究工件 materialize 失败: RuntimeError: materialize failed"]


# ============================================================================
# I-c. research-template mapping 集成表征（39 action keys）
# ============================================================================


class TestResearchTemplateDispatchMapping:
    """验证 research-template 的 39 路 mapping 与入口错误边界。"""

    ACTION_RUNNER_MAP: ClassVar[list[tuple[str, str, int]]] = [
        ("list", "_run_list", 101),
        ("show", "_run_show", 102),
        ("scorecard", "_run_scorecard", 103),
        ("evidence", "_run_evidence", 104),
        ("schema", "_run_schema", 105),
        ("checklist", "_run_checklist", 106),
        ("materialize-checklist", "_run_materialize_checklist", 107),
        ("copy", "_run_copy", 108),
        ("recommend", "_run_recommend", 109),
        ("compose", "_run_compose", 110),
        ("monitoring-rules", "_run_monitoring_rules", 111),
        ("research-workbook", "_run_research_workbook", 112),
        ("validate-research-workbook", "_run_validate_research_workbook", 113),
        ("update-research-workbook", "_run_update_research_workbook", 114),
        ("rollback-research-workbook", "_run_rollback_research_workbook", 115),
        ("source-map", "_run_source_map", 116),
        ("validate-source-map", "_run_validate_source_map", 117),
        ("package-manifest", "_run_package_manifest", 118),
        ("materialize", "_run_materialize", 119),
        ("refresh-workspace", "_run_refresh_workspace", 120),
        ("list-bundles", "_run_list_bundles", 121),
        ("validate-bundle", "_run_validate_bundle", 122),
        ("rebind-bundle", "_run_rebind_bundle", 123),
        ("rollback-bundle-rebind", "_run_rollback_bundle_rebind", 124),
        ("monitoring-plan", "_run_monitoring_plan", 125),
        ("validate-monitoring-plan", "_run_validate_monitoring_plan", 126),
        ("list-monitoring-plans", "_run_list_monitoring_plans", 127),
        ("monitoring-status", "_run_monitoring_status", 128),
        ("workbook-status", "_run_workbook_status", 129),
        ("workbook-report", "_run_workbook_report", 130),
        ("validate-workbook-report", "_run_validate_workbook_report", 131),
        ("workbook-report-status", "_run_workbook_report_status", 132),
        ("materialize-portfolio", "_run_materialize_portfolio", 133),
        ("preview-portfolio", "_run_preview_portfolio", 134),
        ("scheduler-manifest", "_run_scheduler_manifest", 135),
        ("validate-scheduler-manifest", "_run_validate_scheduler_manifest", 136),
        ("source-bindings", "_run_source_bindings", 137),
        ("rollback-source-bindings", "_run_rollback_source_bindings", 138),
        ("source-binding-history", "_run_source_binding_history", 139),
    ]

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("action", "runner_attr"),
        [(action, runner_attr) for action, runner_attr, _sentinel in ACTION_RUNNER_MAP],
    )
    def test_action_mapping_points_to_exact_runner(
        self,
        action: str,
        runner_attr: str,
    ) -> None:
        """每个 action key 应映射到逐名锁定的真实 runner。

        Args:
            action: 待核对的 action key。
            runner_attr: 对应 runner 的函数名。

        Returns:
            无。

        Raises:
            AssertionError: mapping 缺项、数量错误或 runner 名称不匹配时抛出。
        """

        mapping = research_template_command_module._RESEARCH_TEMPLATE_ACTION_DISPATCH

        assert len(mapping) == 39
        assert set(mapping) == {item[0] for item in self.ACTION_RUNNER_MAP}
        assert mapping[action].__name__ == runner_attr
        assert callable(mapping[action])

    @pytest.mark.unit
    def test_unknown_action_returns_1_silently(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """未知 action 应静默返回 1。

        Args:
            monkeypatch: pytest monkeypatch 工具。
            capsys: 标准输出与错误输出捕获器。

        Returns:
            无。

        Raises:
            AssertionError: 返回码或静默输出契约漂移时抛出。
        """

        monkeypatch.setattr(
            "dayu.cli.commands.research_template.setup_loglevel",
            lambda _a: None,
        )
        args = _make_rt_args("nonexistent-subcommand")
        exit_code = run_research_template_command(args)

        assert exit_code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "error",
        (
            FileNotFoundError("missing"),
            FileExistsError("exists"),
            ValueError("invalid"),
        ),
    )
    def test_caught_runner_errors_emit_exact_stderr(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        error: FileNotFoundError | FileExistsError | ValueError,
    ) -> None:
        """三类已知 runner 异常应转换为精确 stderr 与退出码 1。

        Args:
            monkeypatch: pytest monkeypatch 工具。
            capsys: 标准输出与错误输出捕获器。
            error: 当前需要模拟的入口可转换异常。

        Returns:
            无。

        Raises:
            AssertionError: 异常转换的输出或退出码漂移时抛出。
        """

        monkeypatch.setattr(
            research_template_command_module,
            "setup_loglevel",
            lambda _args: None,
        )
        mapping = dict(research_template_command_module._RESEARCH_TEMPLATE_ACTION_DISPATCH)
        mapping["list"] = partial(_raise_research_template_error, error=error)
        monkeypatch.setattr(
            research_template_command_module,
            "_RESEARCH_TEMPLATE_ACTION_DISPATCH",
            MappingProxyType(mapping),
        )

        exit_code = run_research_template_command(_make_rt_args("list"))

        captured = capsys.readouterr()
        assert exit_code == 1
        assert captured.out == ""
        assert captured.err == f"research-template error: {error}\n"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("args", "expected"),
        (
            (DayuCliArguments(), ""),
            (DayuCliArguments(research_template_action=None), ""),
            (DayuCliArguments(research_template_action=123), "123"),
            (DayuCliArguments(research_template_action="  LiSt  "), "list"),
        ),
    )
    def test_selector_preserves_defensive_normalization(
        self,
        args: DayuCliArguments,
        expected: str,
    ) -> None:
        """selector 应保留缺字段、空值、非字符串与大小写规范化语义。

        Args:
            args: 当前防御性输入场景的 Dayu 参数对象。
            expected: 预期规范化结果。

        Returns:
            无。

        Raises:
            AssertionError: selector 结果与既有语义不一致时抛出。
        """

        assert research_template_command_module._resolve_research_template_action(args) == expected

    @pytest.mark.unit
    def test_parse_arguments_returns_real_dayu_namespace(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """真实 parser 应原位填充并返回 DayuCliArguments 实例。

        Args:
            monkeypatch: pytest monkeypatch 工具。

        Returns:
            无。

        Raises:
            AssertionError: runtime 类型身份或解析字段丢失时抛出。
        """

        monkeypatch.setattr("sys.argv", ["dayu-cli", "write", "--summary"])

        args = parse_arguments()

        assert isinstance(args, argparse.Namespace)
        assert isinstance(args, DayuCliArguments)
        assert args.command == "write"
        assert args.summary is True
        assert args.materialize_research is False

    @pytest.mark.unit
    def test_parser_choices_match_action_runner_map(self) -> None:
        """argparse parser choices 与 ACTION_RUNNER_MAP 一一对应，且数量为 39。

        通过程序化访问 parser 的 subparser choices 验证。
        """
        import argparse

        from dayu.cli.arg_parsing import (
            DayuCliArgumentParser,
            _register_research_template_subcommands,
        )

        parser = DayuCliArgumentParser()
        sub = parser.add_subparsers(dest="cmd", required=True)
        _register_research_template_subcommands(sub)
        rt_parser = sub.choices["research-template"]
        parser_actions: set[str] = set()
        for action in rt_parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                parser_actions = set(action.choices.keys())
                break

        assert len(parser_actions) == 39, (
            f"argparse research-template subparser choices 应为 39，"
            f"实际 {len(parser_actions)}"
        )

        table_actions = {entry[0] for entry in self.ACTION_RUNNER_MAP}
        assert len(table_actions) == 39, (
            f"ACTION_RUNNER_MAP 应有 39 个 action key，实际 {len(table_actions)}"
        )

        missing_from_table = parser_actions - table_actions
        extra_in_table = table_actions - parser_actions
        assert not missing_from_table, (
            f"parser choices 中存在但 ACTION_RUNNER_MAP 缺失: {sorted(missing_from_table)}"
        )
        assert not extra_in_table, (
            f"ACTION_RUNNER_MAP 中存在但 parser choices 缺失: {sorted(extra_in_table)}"
        )
