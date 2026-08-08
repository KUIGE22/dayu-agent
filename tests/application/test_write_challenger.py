"""Tests for isolated Challenger write orchestration."""

from __future__ import annotations

import json
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from dayu.cli.arguments import DayuCliArguments
from dayu.cli.commands._write_challenger import (
    _build_challenger_run_plan_from_args,
    _build_challenger_write_config,
    _persist_challenger_run_authorization_after_preflight,
    _preflight_champion_and_challenger,
    _run_champion_challenger_experiment,
    _verify_and_consume_challenger_run_approval_before_host,
    _verify_challenger_preflight_approval_before_host,
)
from dayu.cli.commands.write import (
    _validate_research_materialization_args,
    run_write_command,
)
from dayu.services.contracts import WritePreflightResult, WriteRunConfig
from dayu.services.write_model_challenger_preflight_approval import (
    build_write_model_challenger_preflight_approval,
)
from dayu.services.write_model_challenger_proposal import (
    build_write_model_challenger_proposal,
)
from dayu.services.write_service import WriteService


def _run_write_command_with_complete_dispatch_args(args: DayuCliArguments) -> int:
    """以真实 parser 默认 selector 补齐直接 fixture 后执行 write 入口。

    真实 argparse parser 会写入全部 Write Protocol 字段；本模块的直接 fixture 只
    声明当前场景字段，因此在测试边界补齐其余 selector 默认值。

    Args:
        args: 当前测试构造的真实 Dayu 参数对象。

    Returns:
        生产 write 入口返回的退出码。

    Raises:
        Exception: 生产 write 入口未转换的异常原样传播。
    """

    for field in (
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
    ):
        args.__dict__.setdefault(field, False)
    for field in (
        "challenger_config_manual_recovery_receipt_input",
        "challenger_config_manual_recovery_plan_output",
        "challenger_config_manual_recovery_approval_output",
        "routing_challenger_run_approval_input",
    ):
        args.__dict__.setdefault(field, None)
    return run_write_command(args)


def _config(output_dir: Path) -> WriteRunConfig:
    return WriteRunConfig(
        ticker="AAPL",
        company="Apple",
        template_path=str(output_dir.parent / "template.md"),
        output_dir=str(output_dir),
        write_max_retries=2,
        web_provider="auto",
        resume=True,
        write_model_override_name="deepseek",
        audit_model_override_name="claude-audit",
    )


def _summary(primary_model: str, cost: float) -> dict[str, Any]:
    return {
        "schema_version": "write_run_summary_v3",
        "ticker": "AAPL",
        "gate_status": "passed",
        "model_roles": {
            "primary": {"model_names": [primary_model]},
            "audit": {"model_names": ["claude-audit"]},
        },
        "model_usage": {
            "usage_status": "complete",
            "total_tokens": 100,
            "cost": {
                "status": "complete",
                "currency": "USD",
                "known_estimated_cost": cost,
            },
        },
        "chapter_count": 1,
        "failed_count": 0,
        "audit": {
            "required": True,
            "failed_count": 0,
            "gate_blocked_count": 0,
            "first_pass_count": 1,
            "total_retries": 0,
        },
        "chapters": [
            {
                "index": 1,
                "title": "Business",
                "gate_passed": True,
                "audit_passed": True,
            }
        ],
    }


def _ready_routing_proposal() -> dict[str, Any]:
    return build_write_model_challenger_proposal(
        recent={
            "run_count": 5,
            "routing_observed_run_count": 5,
            "gate_observed_run_count": 5,
            "gate_pass_rate": 1.0,
            "fallback_switch_count": 4,
        },
        route_pairs=[
            {
                "model_role": "primary",
                "primary_model_name": "deepseek-primary",
                "fallback_model_name": "mimo-fallback",
                "run_count": 5,
                "scene_names": ["write"],
                "primary_scene_call_count": 20,
                "fallback_observed_scene_call_count": 4,
                "fallback_switch_count": 4,
                "fallback_completed_count": 4,
                "fallback_error_count": 0,
                "primary_switch_share": 0.2,
                "fallback_completion_rate": 1.0,
                "fallback_error_rate": 0.0,
            }
        ],
        models=[
            {
                "model_name": "deepseek-primary",
                "status": "degraded",
            },
            {
                "model_name": "mimo-fallback",
                "status": "healthy",
            },
        ],
        history_fingerprint=f"sha256:{'1' * 64}",
        selected_run_count=5,
        baseline_run_count=0,
    )


def _approval_request(
    proposal: dict[str, Any],
    *,
    approved_at: datetime,
) -> dict[str, Any]:
    evidence_window = cast(dict[str, Any], proposal["evidence_window"])
    return {
        "schema_version": (
            "write_model_challenger_preflight_approval_request_v1"
        ),
        "approval_type": "write_model_challenger_common_preflight",
        "scope": "champion_challenger_common_preflight_only",
        "approved_by": "operator@example.test",
        "approval_reference": "OPS-42",
        "approved_at": approved_at.isoformat().replace(
            "+00:00",
            "Z",
        ),
        "expires_at": (
            approved_at + timedelta(hours=1)
        ).isoformat().replace("+00:00", "Z"),
        "proposal_fingerprint": proposal["proposal_fingerprint"],
        "history_fingerprint": evidence_window[
            "history_fingerprint"
        ],
        "acknowledgements": [
            "common_preflight_only",
            "no_model_execution",
            "no_configuration_change",
            "no_challenger_run_authorization",
            "no_challenger_promotion_authorization",
        ],
    }


def _run_approval_request(
    *,
    proposal: dict[str, Any],
    preflight_approval: dict[str, Any],
    execution_plan: dict[str, Any],
    approved_at: datetime,
) -> dict[str, Any]:
    evidence_window = cast(
        dict[str, Any],
        proposal["evidence_window"],
    )
    return {
        "schema_version": (
            "write_model_challenger_run_approval_request_v1"
        ),
        "approval_type": "write_model_challenger_isolated_run",
        "scope": "one_bounded_isolated_champion_challenger_run",
        "approved_by": "operator@example.test",
        "approval_reference": "OPS-RUN-42",
        "approved_at": approved_at.isoformat().replace(
            "+00:00",
            "Z",
        ),
        "expires_at": (
            approved_at + timedelta(hours=2)
        ).isoformat().replace("+00:00", "Z"),
        "proposal_fingerprint": proposal["proposal_fingerprint"],
        "history_fingerprint": evidence_window[
            "history_fingerprint"
        ],
        "preflight_approval_fingerprint": preflight_approval[
            "approval_fingerprint"
        ],
        "execution_plan": execution_plan,
        "acknowledgements": [
            "authorizes_champion_and_challenger_model_execution",
            "preflight_must_pass_before_execution",
            "isolated_outputs_are_new_and_distinct",
            "per_run_budget_applies_to_each_run_separately",
            "authorization_is_single_use",
            "no_configuration_change_authorization",
            "no_challenger_promotion_authorization",
        ],
    }


@pytest.mark.unit
def test_build_challenger_config_uses_isolated_default_output(tmp_path: Path) -> None:
    champion = _config(tmp_path / "AAPL")
    args = Namespace(
        challenger_model_name="claude-write",
        challenger_audit_model_name=None,
        challenger_output=None,
    )

    challenger = _build_challenger_write_config(args=args, champion_config=champion)

    assert Path(challenger.output_dir) == tmp_path / "AAPL-challenger"
    assert challenger.write_model_override_name == "claude-write"
    assert challenger.audit_model_override_name == "claude-audit"
    assert challenger.scene_models == {}
    assert champion.output_dir == str(tmp_path / "AAPL")


@pytest.mark.unit
def test_build_challenger_config_rejects_champion_output(tmp_path: Path) -> None:
    champion = _config(tmp_path / "AAPL")
    args = Namespace(
        challenger_model_name="claude-write",
        challenger_audit_model_name=None,
        challenger_output=str(tmp_path / "AAPL"),
    )

    with pytest.raises(ValueError, match="必须与 Champion 输出目录不同"):
        _build_challenger_write_config(args=args, champion_config=champion)


@pytest.mark.unit
def test_challenger_output_requires_a_model_override() -> None:
    args = Namespace(
        challenger_model_name=None,
        challenger_audit_model_name=None,
        challenger_output="./challenger",
        materialize_research=False,
        preflight_only=False,
        summary=False,
        infer=False,
        research_base=None,
        overwrite_research=False,
    )

    assert _validate_research_materialization_args(args) == (
        "--challenger-output 需要同时提供至少一个 Challenger 模型覆盖参数"
    )


@pytest.mark.unit
def test_challenger_rejects_infer_only_mode() -> None:
    args = Namespace(
        challenger_model_name="claude-write",
        challenger_audit_model_name=None,
        challenger_output=None,
        materialize_research=False,
        preflight_only=False,
        summary=False,
        infer=True,
        research_base=None,
        overwrite_research=False,
    )

    assert _validate_research_materialization_args(args) == (
        "Challenger 运行暂不支持 infer-only 的 --infer"
    )


@pytest.mark.unit
def test_pair_preflight_checks_both_plans(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    champion = _config(tmp_path / "champion")
    challenger = _config(tmp_path / "challenger")
    checked: list[str] = []

    class _Service:
        def preflight(self, request: object) -> WritePreflightResult:
            checked.append(cast(Any, request).write_config.output_dir)
            return WritePreflightResult(
                ready=True,
                scenes=(),
                signature_scenes=(),
                required_environment_variables=(),
                issues=(),
            )

    monkeypatch.setattr("dayu.cli.commands._write_execution.Log.info", lambda *_args, **_kwargs: None)

    result = _preflight_champion_and_challenger(
        champion_config=champion,
        challenger_config=challenger,
        write_service=cast(WriteService, _Service()),
    )

    assert result == 0
    assert checked == [champion.output_dir, challenger.output_dir]


@pytest.mark.unit
def test_pair_preflight_fails_closed_after_checking_both_plans(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    champion = _config(tmp_path / "champion")
    challenger = _config(tmp_path / "challenger")
    results = iter((True, False))
    checked: list[str] = []

    class _Service:
        def preflight(self, request: object) -> WritePreflightResult:
            checked.append(cast(Any, request).write_config.output_dir)
            return WritePreflightResult(
                ready=next(results),
                scenes=(),
                signature_scenes=(),
                required_environment_variables=(),
                issues=(),
            )

    monkeypatch.setattr("dayu.cli.commands._write_execution.Log.info", lambda *_args, **_kwargs: None)

    result = _preflight_champion_and_challenger(
        champion_config=champion,
        challenger_config=challenger,
        write_service=cast(WriteService, _Service()),
    )

    assert result == 2
    assert checked == [champion.output_dir, challenger.output_dir]


@pytest.mark.unit
def test_experiment_runs_both_and_persists_comparison(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    champion = _config(tmp_path / "champion")
    challenger = _config(tmp_path / "challenger")
    challenger.write_model_override_name = "claude-write"
    calls: list[str] = []

    def _fake_run(*, write_config: WriteRunConfig, write_service: object) -> int:
        del write_service
        calls.append(write_config.output_dir)
        output_dir = Path(write_config.output_dir)
        output_dir.mkdir(parents=True)
        is_challenger = write_config is challenger
        payload = _summary(
            "claude-write" if is_challenger else "deepseek",
            0.7 if is_challenger else 1.0,
        )
        (output_dir / "run_summary.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr("dayu.cli.commands._write_challenger._run_write_stage", _fake_run)
    monkeypatch.setattr("dayu.cli.commands._write_challenger.Log.info", lambda *_args, **_kwargs: None)

    exit_code = _run_champion_challenger_experiment(
        champion_config=champion,
        challenger_config=challenger,
        write_service=cast(WriteService, SimpleNamespace()),
    )

    comparison = json.loads(
        (Path(champion.output_dir) / "challenger_comparison.json").read_text(
            encoding="utf-8"
        )
    )
    assert exit_code == 0
    assert calls == [champion.output_dir, challenger.output_dir]
    assert comparison["verdict"] == "promote_challenger"
    assert not (Path(challenger.output_dir) / "challenger_comparison.json").exists()


@pytest.mark.unit
def test_experiment_does_not_compare_stale_summary_after_runtime_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    champion = _config(tmp_path / "champion")
    challenger = _config(tmp_path / "challenger")
    champion_dir = Path(champion.output_dir)
    champion_dir.mkdir(parents=True)
    (champion_dir / "run_summary.json").write_text(
        json.dumps(_summary("old-model", 1.0)),
        encoding="utf-8",
    )
    calls: list[str] = []

    def _failed_run(*, write_config: WriteRunConfig, write_service: object) -> int:
        del write_service
        calls.append(write_config.output_dir)
        return 2

    monkeypatch.setattr("dayu.cli.commands._write_challenger._run_write_stage", _failed_run)
    monkeypatch.setattr("dayu.cli.commands._write_challenger.Log.error", lambda *_args, **_kwargs: None)

    exit_code = _run_champion_challenger_experiment(
        champion_config=champion,
        challenger_config=challenger,
        write_service=cast(WriteService, SimpleNamespace()),
    )

    assert exit_code == 2
    assert calls == [champion.output_dir]
    assert not (champion_dir / "challenger_comparison.json").exists()


@pytest.mark.unit
def test_write_command_preflights_both_before_starting_experiment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "champion"
    challenger_output_dir = tmp_path / "champion-challenger"
    template_path = tmp_path / "template.md"
    template_path.write_text("# Test template\n", encoding="utf-8")
    args = DayuCliArguments(
        command="write",
        ticker="AAPL",
        summary=False,
        preflight_only=False,
        materialize_research=False,
        research_base=None,
        overwrite_research=False,
        research_template=None,
        output=str(output_dir),
        template=str(template_path),
        chapter=None,
        write_max_retries=2,
        write_max_model_requests=60,
        write_max_total_tokens=1_500_000,
        write_max_estimated_cost=12.5,
        write_budget_currency="CNY",
        resume=False,
        web_provider="auto",
        audit_model_name="claude-audit",
        model_name="deepseek",
        fallback_model_name=None,
        audit_fallback_model_name=None,
        challenger_model_name="claude-write",
        challenger_audit_model_name="deepseek-audit",
        challenger_output=str(challenger_output_dir),
        routing_history_root=str(tmp_path / "history"),
        routing_proposal_input=str(tmp_path / "proposal.json"),
        routing_preflight_approval_input=None,
        routing_preflight_approval_request=None,
        routing_preflight_approval_output=None,
        routing_challenger_run_plan_output=None,
        routing_challenger_run_approval_request=None,
        routing_challenger_run_approval_output=None,
        routing_challenger_run_approval_input=str(
            tmp_path / "run-approval.json"
        ),
        temperature=None,
        fast=False,
        force=False,
        infer=False,
    )
    paths = SimpleNamespace(
        workspace_dir=tmp_path,
        ticker="AAPL",
        has_local_filings=True,
    )
    running = SimpleNamespace(web_tools_config=SimpleNamespace(provider="auto"))
    write_cli_config = SimpleNamespace(
        template_path=tmp_path / "template.md",
        output_dir=output_dir,
        write_max_retries=2,
        web_provider="auto",
        resume=False,
        audit_model_override_name="claude-audit",
        write_fallback_model_name="",
        audit_fallback_model_name="",
        chapter_filter="",
        fast=False,
        force=False,
        infer=False,
        research_template_requested_name="",
        research_template_resolved_name="",
        research_template_selection_mode="",
        write_max_model_requests=60,
        write_max_total_tokens=1_500_000,
        write_max_estimated_cost=12.5,
        write_budget_currency="CNY",
    )
    events: list[str] = []

    class _Service:
        def preflight(self, request: object) -> WritePreflightResult:
            output = Path(cast(Any, request).write_config.output_dir).name
            events.append(f"preflight:{output}")
            return WritePreflightResult(
                ready=True,
                scenes=(),
                signature_scenes=(),
                required_environment_variables=(),
                issues=(),
            )

    def _fake_experiment(**kwargs: object) -> int:
        champion_config = cast(WriteRunConfig, kwargs["champion_config"])
        challenger_config = cast(WriteRunConfig, kwargs["challenger_config"])
        events.append("run")
        assert Path(champion_config.output_dir) == output_dir
        assert Path(challenger_config.output_dir) == challenger_output_dir
        return 0

    def _authorize_run(**_kwargs: object) -> int:
        events.append("authorization")
        return 0

    def _prepare_host(**_kwargs: object) -> tuple[object, ...]:
        events.append("host")
        return (
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(get_company_name=lambda _ticker: "Apple"),
        )

    monkeypatch.setattr("dayu.cli.commands.write.setup_loglevel", lambda _args: None)
    monkeypatch.setattr("dayu.cli.commands.write.setup_paths", lambda _args: paths)
    monkeypatch.setattr(
        "dayu.cli.commands.write._resolve_write_model_override_name",
        lambda _args: "deepseek",
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._build_execution_options",
        lambda _args: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._prepare_cli_host_dependencies",
        _prepare_host,
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._verify_and_consume_challenger_run_approval_before_host",
        _authorize_run,
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write.RunningConfig.from_resolved",
        lambda _options: running,
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._build_write_service",
        lambda **_kwargs: _Service(),
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write.setup_write_config",
        lambda *_args, **_kwargs: write_cli_config,
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._run_champion_challenger_experiment",
        _fake_experiment,
    )
    monkeypatch.setattr("dayu.cli.commands.write.Log.info", lambda *_args, **_kwargs: None)

    assert _run_write_command_with_complete_dispatch_args(args) == 0
    assert events == [
        "authorization",
        "host",
        "preflight:champion",
        "preflight:champion-challenger",
        "run",
    ]


@pytest.mark.unit
def test_write_command_blocks_unapproved_common_preflight_before_host(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    args = DayuCliArguments(
        command="write",
        ticker="AAPL",
        summary=False,
        preflight_only=True,
        materialize_research=False,
        research_base=None,
        overwrite_research=False,
        research_template=None,
        output=str(tmp_path / "champion"),
        template=None,
        chapter=None,
        write_max_retries=2,
        resume=True,
        web_provider="auto",
        audit_model_name=None,
        model_name="deepseek-primary",
        challenger_model_name="mimo-fallback",
        challenger_audit_model_name=None,
        challenger_output=None,
        routing_history_root=str(tmp_path / "history"),
        routing_proposal_input=str(tmp_path / "proposal.json"),
        routing_preflight_approval_input=str(
            tmp_path / "approval.json"
        ),
        routing_preflight_approval_request=None,
        routing_preflight_approval_output=None,
        fast=False,
        force=False,
        infer=False,
    )
    paths = SimpleNamespace(
        workspace_dir=tmp_path,
        ticker="AAPL",
        has_local_filings=True,
    )
    captured: list[tuple[str, str]] = []

    def _blocked_gate(
        *,
        args: Namespace,
        write_model_override_name: str,
    ) -> int:
        captured.append(
            (
                args.challenger_model_name,
                write_model_override_name,
            )
        )
        return 4

    monkeypatch.setattr(
        "dayu.cli.commands.write.setup_loglevel",
        lambda _args: None,
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write.setup_paths",
        lambda _args: paths,
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._resolve_write_model_override_name",
        lambda _args: "deepseek-primary",
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._build_execution_options",
        lambda _args: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._verify_challenger_preflight_approval_before_host",
        _blocked_gate,
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._prepare_cli_host_dependencies",
        lambda **_kwargs: pytest.fail(
            "审批未通过时不得初始化 Host"
        ),
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write.Log.info",
        lambda *_args, **_kwargs: None,
    )

    assert _run_write_command_with_complete_dispatch_args(args) == 4
    assert captured == [
        ("mimo-fallback", "deepseek-primary")
    ]


@pytest.mark.unit
def test_write_command_blocks_rejected_full_run_before_host(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    template_path = tmp_path / "template.md"
    template_path.write_text("# Test template\n", encoding="utf-8")
    args = DayuCliArguments(
        command="write",
        ticker="AAPL",
        summary=False,
        preflight_only=False,
        materialize_research=False,
        research_base=None,
        overwrite_research=False,
        research_template=None,
        output=str(tmp_path / "champion"),
        template=str(template_path),
        chapter=None,
        write_max_retries=2,
        write_max_model_requests=60,
        write_max_total_tokens=1_500_000,
        write_max_estimated_cost=12.5,
        write_budget_currency="CNY",
        resume=False,
        web_provider="auto",
        audit_model_name="deepseek-audit",
        model_name="deepseek-primary",
        fallback_model_name=None,
        audit_fallback_model_name=None,
        challenger_model_name="mimo-fallback",
        challenger_audit_model_name=None,
        challenger_output=str(tmp_path / "challenger"),
        routing_history_root=str(tmp_path / "history"),
        routing_proposal_input=str(tmp_path / "proposal.json"),
        routing_preflight_approval_input=None,
        routing_preflight_approval_request=None,
        routing_preflight_approval_output=None,
        routing_challenger_run_plan_output=None,
        routing_challenger_run_approval_request=None,
        routing_challenger_run_approval_output=None,
        routing_challenger_run_approval_input=str(
            tmp_path / "run-approval.json"
        ),
        temperature=None,
        fast=False,
        force=False,
        infer=False,
    )
    paths = SimpleNamespace(
        workspace_dir=tmp_path,
        ticker="AAPL",
        has_local_filings=True,
    )
    captured_plans: list[dict[str, Any]] = []

    def _reject_run(
        *,
        args: Namespace,
        paths_config: object,
        execution_plan: dict[str, Any],
    ) -> int:
        del args, paths_config
        captured_plans.append(execution_plan)
        return 4

    monkeypatch.setattr(
        "dayu.cli.commands.write.setup_loglevel",
        lambda _args: None,
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write.setup_paths",
        lambda _args: paths,
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._resolve_write_model_override_name",
        lambda _args: "deepseek-primary",
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._build_execution_options",
        lambda _args: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._verify_and_consume_challenger_run_approval_before_host",
        _reject_run,
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write._prepare_cli_host_dependencies",
        lambda **_kwargs: pytest.fail(
            "被拒绝的完整双跑不得初始化 Host"
        ),
    )
    monkeypatch.setattr(
        "dayu.cli.commands.write.Log.info",
        lambda *_args, **_kwargs: None,
    )

    assert _run_write_command_with_complete_dispatch_args(args) == 4
    assert len(captured_plans) == 1


@pytest.mark.unit
def test_common_preflight_gate_consumes_matching_receipts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    proposal = _ready_routing_proposal()
    approval = build_write_model_challenger_preflight_approval(
        request=_approval_request(proposal, approved_at=now),
        proposal_receipt=proposal,
        current_proposal=proposal,
        now=now,
    )
    proposal_path = tmp_path / "proposal.json"
    approval_path = tmp_path / "approval.json"
    proposal_path.write_text(
        json.dumps(proposal),
        encoding="utf-8",
    )
    approval_path.write_text(
        json.dumps(approval),
        encoding="utf-8",
    )
    args = Namespace(
        routing_history_root=str(tmp_path / "history"),
        routing_proposal_input=str(proposal_path),
        routing_preflight_approval_input=str(approval_path),
        challenger_model_name="mimo-fallback",
        challenger_audit_model_name=None,
        audit_model_name=None,
    )

    monkeypatch.setattr(
        "dayu.cli.commands._write_challenger.build_write_model_health_trend",
        lambda _root: {"challenger_proposal": proposal},
    )
    monkeypatch.setattr(
        "dayu.cli.commands._write_challenger.Log.info",
        lambda *_args, **_kwargs: None,
    )

    assert (
        _verify_challenger_preflight_approval_before_host(
            args=args,
            write_model_override_name="deepseek-primary",
        )
        == 0
    )

    args.challenger_model_name = "different-challenger"
    assert (
        _verify_challenger_preflight_approval_before_host(
            args=args,
            write_model_override_name="deepseek-primary",
        )
        == 4
    )


@pytest.mark.unit
def test_full_run_gate_consumes_matching_approval_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    template_path = tmp_path / "template.md"
    template_path.write_text("# Test template\n", encoding="utf-8")
    proposal = _ready_routing_proposal()
    preflight_approval = (
        build_write_model_challenger_preflight_approval(
            request=_approval_request(
                proposal,
                approved_at=now,
            ),
            proposal_receipt=proposal,
            current_proposal=proposal,
            now=now,
        )
    )
    proposal_path = tmp_path / "proposal.json"
    preflight_approval_path = (
        tmp_path / "preflight-approval.json"
    )
    run_request_path = tmp_path / "run-request.json"
    run_approval_path = tmp_path / "run-approval.json"
    args = Namespace(
        template=str(template_path),
        output=str(tmp_path / "champion"),
        challenger_output=str(tmp_path / "challenger"),
        model_name="deepseek-primary",
        audit_model_name=None,
        fallback_model_name=None,
        audit_fallback_model_name=None,
        challenger_model_name="mimo-fallback",
        challenger_audit_model_name=None,
        write_max_retries=2,
        web_provider="auto",
        temperature=None,
        write_max_model_requests=60,
        write_max_total_tokens=1_500_000,
        write_max_estimated_cost=12.5,
        write_budget_currency="CNY",
        routing_history_root=str(tmp_path / "history"),
        routing_proposal_input=str(proposal_path),
        routing_preflight_approval_input=str(
            preflight_approval_path
        ),
        routing_challenger_run_plan_output=str(
            tmp_path / "run-plan.json"
        ),
        routing_challenger_run_approval_request=str(
            run_request_path
        ),
        routing_challenger_run_approval_output=str(
            run_approval_path
        ),
        routing_challenger_run_approval_input=str(
            run_approval_path
        ),
    )
    paths = SimpleNamespace(
        workspace_dir=tmp_path,
        ticker="AAPL",
    )
    execution_plan = _build_challenger_run_plan_from_args(
        args=args,
        paths_config=cast(Any, paths),
        write_model_override_name="deepseek-primary",
    )
    proposal_path.write_text(
        json.dumps(proposal),
        encoding="utf-8",
    )
    preflight_approval_path.write_text(
        json.dumps(preflight_approval),
        encoding="utf-8",
    )
    run_request_path.write_text(
        json.dumps(
            _run_approval_request(
                proposal=proposal,
                preflight_approval=preflight_approval,
                execution_plan=execution_plan,
                approved_at=now,
            )
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "dayu.cli.commands._write_challenger.build_write_model_health_trend",
        lambda _root: {"challenger_proposal": proposal},
    )
    monkeypatch.setattr(
        "dayu.cli.commands._write_challenger.Log.info",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dayu.cli.commands._write_challenger.Log.error",
        lambda *_args, **_kwargs: None,
    )

    assert (
        _persist_challenger_run_authorization_after_preflight(
            args=args,
            execution_plan=execution_plan,
        )
        == 0
    )
    assert run_approval_path.is_file()
    args.routing_preflight_approval_input = None
    args.routing_challenger_run_plan_output = None
    args.routing_challenger_run_approval_request = None
    args.routing_challenger_run_approval_output = None

    assert (
        _verify_and_consume_challenger_run_approval_before_host(
            args=args,
            paths_config=cast(Any, paths),
            execution_plan=execution_plan,
        )
        == 0
    )
    assert (
        _verify_and_consume_challenger_run_approval_before_host(
            args=args,
            paths_config=cast(Any, paths),
            execution_plan=execution_plan,
        )
        == 4
    )
    consumption_records = list(
        (
            tmp_path
            / ".dayu"
            / "approvals"
            / "challenger-runs"
        ).glob("*.consumed.json")
    )
    assert len(consumption_records) == 1
