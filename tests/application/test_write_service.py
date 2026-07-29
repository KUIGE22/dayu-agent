"""WriteService 测试。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Literal, cast, overload

import pytest

from dayu.contracts.infrastructure import ConfigLoaderProtocol, ModelCatalogProtocol
from dayu.contracts.model_config import ModelConfig
from dayu.contracts.prompt_assets import SceneManifestAsset, TaskPromptContractAsset
from dayu.contracts.session import SessionSource
from dayu.execution.options import ExecutionOptions
from dayu.execution.options import ResolvedExecutionOptions, build_base_execution_options
from dayu.host.host import Host
from dayu.contracts.host_execution import ConcurrencyAcquirePolicy
from dayu.host.host_execution import HostedRunContext, HostedRunSpec
from dayu.host.protocols import HostedExecutionGatewayProtocol, HostGovernanceProtocol
from dayu.host.protocols import RunRegistryProtocol
from dayu.services.conversation_policy_reader import ConversationPolicyReader
from dayu.services.scene_definition_reader import SceneDefinitionReader
from dayu.services.contracts import (
    SceneModelConfig,
    WriteModelRole,
    WritePreflightIssueCode,
    WriteRequest,
    WriteRunConfig,
)
from dayu.services.scene_execution_acceptance import SceneExecutionAcceptancePreparer
from dayu.services.write_service import WRITE_CANCELLED_EXIT_CODE, WritePreflightError, WriteService
from dayu.services.protocols import WriteServiceProtocol
from dayu.services.write_model_challenger_preflight_approval import (
    WriteModelPreflightApprovalBlockedError,
)
from dayu.startup.workspace import WorkspaceResources


@pytest.mark.unit
def test_write_service_report_prints_challenger_comparison(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Summary reporting should append the deterministic comparison receipt."""

    output_dir = tmp_path / "champion"
    output_dir.mkdir()
    comparison = {
        "schema_version": "write_run_comparison_v2",
        "verdict": "promote_challenger",
        "reason_codes": ["equivalent_quality_at_lower_cost"],
        "quality": {"status": "equivalent"},
        "routing": {
            "comparable": True,
            "integrity_issue": False,
            "status": "improved",
            "champion": {
                "status": "complete",
                "fallback_switch_count": 2,
                "fallback_call_completed_count": 2,
                "fallback_call_error_count": 0,
                "fallback_call_completion_rate": 1.0,
                "scene_call_count": 10,
                "fallback_scene_call_share": 0.2,
            },
            "challenger": {
                "status": "complete",
                "fallback_switch_count": 0,
                "fallback_call_completed_count": 0,
                "fallback_call_error_count": 0,
                "fallback_call_completion_rate": None,
                "scene_call_count": 10,
                "fallback_scene_call_share": 0.0,
            },
            "fallback_switch_delta": -2,
            "fallback_call_error_delta": 0,
            "fallback_call_completion_rate_delta": None,
            "fallback_scene_call_share_delta": -0.2,
        },
        "cost": {
            "basis": "current_model_catalog",
            "comparable": True,
            "champion": {
                "status": "complete",
                "currency": "CNY",
                "known_estimated_cost": 3.0,
                "cost_per_passed_chapter": 3.0,
            },
            "challenger": {
                "status": "complete",
                "currency": "CNY",
                "known_estimated_cost": 1.5,
                "cost_per_passed_chapter": 1.5,
            },
            "cost_delta": -1.5,
            "cost_per_passed_chapter_delta": -1.5,
            "token_delta": -500_000,
            "request_delta": 0,
            "scene_call_delta": 0,
        },
    }
    current_catalog = {"deepseek-v4-pro": {"pricing": {"currency": "CNY"}}}
    captured: dict[str, object] = {}

    def _fake_print_write_report(
        path: str | Path,
        *,
        model_catalog: object = None,
    ) -> int:
        captured["base_path"] = Path(path)
        captured["base_catalog"] = model_catalog
        return 0

    def _fake_resolve_comparison(
        path: str | Path,
        *,
        model_catalog: object = None,
    ) -> tuple[dict[str, Any], bool]:
        captured["comparison_path"] = Path(path)
        captured["comparison_catalog"] = model_catalog
        return comparison, True

    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        _fake_print_write_report,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.resolve_write_run_comparison_for_report",
        _fake_resolve_comparison,
    )

    exit_code = WriteService.print_report(
        output_dir,
        model_catalog=current_catalog,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert captured["base_path"] == output_dir
    assert captured["base_catalog"] is current_catalog
    assert captured["comparison_path"] == output_dir
    assert captured["comparison_catalog"] is current_catalog
    assert "Champion/Challenger 对比" in output
    assert "promote_challenger" in output
    assert "CNY 3.000000" in output
    assert "CNY 1.500000" in output
    assert "Scene 差额 : +0" in output
    assert "路由状态   : improved" in output
    assert "Champion备 : 2 (完成率 100.0% / Scene占比 20.0%)" in output
    assert "挑战者备   : 0 (完成率 不适用 / Scene占比 0.0%)" in output
    assert "后备切换差 : -2" in output
    assert "当前模型目录只读重估" in output


@pytest.mark.unit
def test_write_service_report_ignores_missing_comparison(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing comparison artifact should preserve the manifest report result."""

    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 4,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )

    exit_code = WriteService.print_report(tmp_path)

    assert exit_code == 4
    assert "Champion/Challenger" not in capsys.readouterr().out


@pytest.mark.unit
def test_write_service_report_exports_promotion_review_proposal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A summary export should persist a review-only proposal."""

    output_dir = tmp_path / "champion"
    target = tmp_path / "receipts" / "promotion.json"
    proposal = {
        "schema_version": (
            "write_model_challenger_promotion_proposal_v1"
        ),
        "status": "ready_for_human_review",
    }
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )

    def _fake_build(path: str | Path) -> dict[str, object]:
        captured["build_path"] = Path(path)
        return proposal

    def _fake_persist(
        payload: object,
        path: str | Path,
    ) -> Path:
        captured["persist_payload"] = payload
        captured["persist_path"] = Path(path)
        return Path(path)

    monkeypatch.setattr(
        "dayu.services.write_service."
        "build_write_model_challenger_promotion_proposal",
        _fake_build,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "persist_write_model_challenger_promotion_proposal",
        _fake_persist,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "format_write_model_challenger_promotion_report",
        lambda _payload: ["promotion review only"],
    )

    exit_code = WriteService.print_report(
        output_dir,
        challenger_promotion_proposal_output=target,
    )

    assert exit_code == 0
    assert captured["build_path"] == output_dir
    assert captured["persist_payload"] is proposal
    assert captured["persist_path"] == target
    output = capsys.readouterr().out
    assert "promotion review only" in output
    assert str(target) in output


@pytest.mark.unit
@pytest.mark.parametrize(
    ("verification_status", "expected_exit_code"),
    [
        ("current", 0),
        ("stale_sources", 4),
    ],
)
def test_write_service_report_verifies_promotion_review_proposal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    verification_status: str,
    expected_exit_code: int,
) -> None:
    """Proposal verification must remain read-only and fail closed."""

    target = tmp_path / "promotion.json"
    receipt = {"proposal_fingerprint": "sha256:receipt"}
    verification = {"status": verification_status}
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "load_write_model_challenger_promotion_proposal",
        lambda path: (Path(path), receipt),
    )

    def _fake_verify(payload: object) -> dict[str, object]:
        captured["receipt"] = payload
        return verification

    monkeypatch.setattr(
        "dayu.services.write_service."
        "verify_write_model_challenger_promotion_proposal",
        _fake_verify,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "format_write_model_challenger_promotion_verification_report",
        lambda _payload: [f"verification {verification_status}"],
    )

    exit_code = WriteService.print_report(
        tmp_path / "champion",
        challenger_promotion_proposal_input=target,
    )

    assert exit_code == expected_exit_code
    assert captured["receipt"] is receipt
    output = capsys.readouterr().out
    assert f"verification {verification_status}" in output
    assert str(target) in output


@pytest.mark.unit
def test_write_service_report_rejects_both_promotion_proposal_modes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )

    assert (
        WriteService.print_report(
            tmp_path,
            challenger_promotion_proposal_input=(
                tmp_path / "input.json"
            ),
            challenger_promotion_proposal_output=(
                tmp_path / "output.json"
            ),
        )
        == 2
    )


@pytest.mark.unit
def test_write_service_report_exports_configuration_change_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A summary export should bind a current promotion proposal."""

    promotion_path = tmp_path / "promotion.json"
    target = tmp_path / "change-request.json"
    promotion = {"proposal_fingerprint": "sha256:promotion"}
    change_request = {
        "request_fingerprint": "sha256:request",
    }
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "load_write_model_challenger_promotion_proposal",
        lambda path: (Path(path), promotion),
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "verify_write_model_challenger_promotion_proposal",
        lambda _payload: {"status": "current"},
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "format_write_model_challenger_promotion_verification_report",
        lambda _payload: [],
    )

    def _fake_build(path: str | Path) -> dict[str, object]:
        captured["build_path"] = Path(path)
        return change_request

    def _fake_persist(
        payload: object,
        path: str | Path,
    ) -> Path:
        captured["persist_payload"] = payload
        captured["persist_path"] = Path(path)
        return Path(path)

    monkeypatch.setattr(
        "dayu.services.write_service."
        "build_write_model_configuration_change_request",
        _fake_build,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "persist_write_model_configuration_change_request",
        _fake_persist,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "format_write_model_configuration_change_request_report",
        lambda _payload: ["change request review only"],
    )

    exit_code = WriteService.print_report(
        tmp_path / "champion",
        challenger_promotion_proposal_input=promotion_path,
        challenger_config_change_request_output=target,
    )

    assert exit_code == 0
    assert captured["build_path"] == promotion_path
    assert captured["persist_payload"] is change_request
    assert captured["persist_path"] == target
    output = capsys.readouterr().out
    assert "change request review only" in output
    assert str(target) in output


@pytest.mark.unit
def test_write_service_report_issues_configuration_change_approval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Approval issuance should verify the request and never apply it."""

    request_path = tmp_path / "change-request.json"
    human_path = tmp_path / "human-approval.json"
    output_path = tmp_path / "approval.json"
    change_request = {
        "request_fingerprint": "sha256:request",
    }
    human_request = {"approved_by": "operator@example.com"}
    approval = {"status": "approved_for_one_future_change"}
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "load_write_model_configuration_change_request",
        lambda path: (Path(path), change_request),
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "verify_write_model_configuration_change_request",
        lambda _payload: {"status": "current"},
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "format_write_model_configuration_change_request_"
        "verification_report",
        lambda _payload: ["request current"],
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "load_write_model_configuration_change_approval_request",
        lambda path: (Path(path), human_request),
    )

    def _fake_build(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return approval

    def _fake_persist(
        payload: object,
        path: str | Path,
    ) -> Path:
        captured["persist_payload"] = payload
        captured["persist_path"] = Path(path)
        return Path(path)

    monkeypatch.setattr(
        "dayu.services.write_service."
        "build_write_model_configuration_change_approval",
        _fake_build,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "persist_write_model_configuration_change_approval",
        _fake_persist,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "format_write_model_configuration_change_approval_report",
        lambda _payload: ["approval issued; not applied"],
    )

    exit_code = WriteService.print_report(
        tmp_path / "champion",
        challenger_config_change_request_input=request_path,
        challenger_config_change_approval_request=human_path,
        challenger_config_change_approval_output=output_path,
    )

    assert exit_code == 0
    assert captured["approval_request"] is human_request
    assert captured["configuration_change_request"] is change_request
    assert (
        captured["configuration_change_request_path"]
        == request_path
    )
    assert captured["persist_payload"] is approval
    assert captured["persist_path"] == output_path
    output = capsys.readouterr().out
    assert "request current" in output
    assert "approval issued; not applied" in output
    assert str(human_path) in output
    assert str(output_path) in output


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "expected_exit_code"),
    [("approved", 0), ("expired", 4)],
)
def test_write_service_report_verifies_configuration_change_approval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    status: str,
    expected_exit_code: int,
) -> None:
    """Approval verification must remain summary-only and fail closed."""

    approval_path = tmp_path / "approval.json"
    approval = {"approval_fingerprint": "sha256:approval"}
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "load_write_model_configuration_change_approval",
        lambda path: (Path(path), approval),
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "verify_write_model_configuration_change_approval",
        lambda _payload, **_kwargs: {"status": status},
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "format_write_model_configuration_change_approval_"
        "verification_report",
        lambda _payload: [f"approval verification {status}"],
    )

    exit_code = WriteService.print_report(
        tmp_path / "champion",
        challenger_config_change_approval_input=approval_path,
    )

    assert exit_code == expected_exit_code
    output = capsys.readouterr().out
    assert f"approval verification {status}" in output
    assert str(approval_path) in output


@pytest.mark.unit
def test_write_service_report_appends_read_only_model_health_trend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A requested history root should append health even without a comparison."""

    history_root = tmp_path / "history"
    current_catalog = {"model": {"pricing": {"currency": "CNY"}}}
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )

    def _fake_build_health(
        root: str | Path,
        *,
        model_catalog: object = None,
    ) -> dict[str, object]:
        captured["root"] = Path(root)
        captured["model_catalog"] = model_catalog
        return {"schema_version": "write_model_health_trend_v1"}

    monkeypatch.setattr(
        "dayu.services.write_service.build_write_model_health_trend",
        _fake_build_health,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.format_write_model_health_report",
        lambda _payload: [
            "模型健康趋势（只读）：",
            "  安全边界   : 不自动改配置",
        ],
    )

    exit_code = WriteService.print_report(
        tmp_path,
        model_catalog=current_catalog,
        routing_history_root=history_root,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert captured["root"] == history_root
    assert captured["model_catalog"] is current_catalog
    assert "模型健康趋势（只读）" in output
    assert "不自动改配置" in output


@pytest.mark.unit
def test_write_service_report_exports_requested_challenger_proposal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An explicit export should persist only the generated proposal receipt."""

    history_root = tmp_path / "history"
    target = tmp_path / "receipts" / "routing-proposal.json"
    proposal = {
        "schema_version": "write_model_challenger_proposal_v2",
        "proposal_fingerprint": "a" * 64,
    }
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.build_write_model_health_trend",
        lambda *_args, **_kwargs: {
            "schema_version": "write_model_health_trend_v1",
            "challenger_proposal": proposal,
        },
    )
    monkeypatch.setattr(
        "dayu.services.write_service.format_write_model_health_report",
        lambda _payload: ["模型健康趋势（只读）"],
    )

    def _fake_persist(
        payload: dict[str, object],
        path: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        captured["payload"] = payload
        captured["path"] = Path(path)
        captured["overwrite"] = overwrite
        return Path(path)

    monkeypatch.setattr(
        "dayu.services.write_service.persist_write_model_challenger_proposal",
        _fake_persist,
    )

    exit_code = WriteService.print_report(
        tmp_path,
        routing_history_root=history_root,
        routing_proposal_output=target,
        overwrite_routing_proposal=True,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert captured == {
        "payload": proposal,
        "path": target,
        "overwrite": True,
    }
    assert f"Challenger 提案凭据: {target}" in output


@pytest.mark.unit
def test_write_service_report_fails_closed_when_proposal_export_conflicts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A conflicting receipt must fail unless overwrite was explicitly enabled."""

    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.build_write_model_health_trend",
        lambda *_args, **_kwargs: {
            "challenger_proposal": {
                "schema_version": "write_model_challenger_proposal_v2",
                "proposal_fingerprint": "a" * 64,
            }
        },
    )
    monkeypatch.setattr(
        "dayu.services.write_service.format_write_model_health_report",
        lambda _payload: [],
    )
    monkeypatch.setattr(
        "dayu.services.write_service.persist_write_model_challenger_proposal",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FileExistsError("different content")
        ),
    )

    exit_code = WriteService.print_report(
        tmp_path,
        routing_history_root=tmp_path / "history",
        routing_proposal_output=tmp_path / "proposal.json",
    )

    assert exit_code == 2
    assert "Challenger 提案导出失败" in capsys.readouterr().out


@pytest.mark.unit
@pytest.mark.parametrize(
    ("verification_status", "expected_exit_code"),
    [
        ("current", 0),
        ("stale_history", 4),
    ],
)
def test_write_service_report_verifies_requested_challenger_proposal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    verification_status: str,
    expected_exit_code: int,
) -> None:
    """Verification should compare the receipt without executing a model."""

    proposal = {
        "schema_version": "write_model_challenger_proposal_v2",
        "proposal_fingerprint": "a" * 64,
    }
    receipt = {
        "schema_version": "write_model_challenger_proposal_v2",
        "proposal_fingerprint": "b" * 64,
    }
    target = tmp_path / "proposal.json"
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.build_write_model_health_trend",
        lambda *_args, **_kwargs: {
            "challenger_proposal": proposal,
        },
    )
    monkeypatch.setattr(
        "dayu.services.write_service.format_write_model_health_report",
        lambda _payload: [],
    )
    monkeypatch.setattr(
        "dayu.services.write_service.load_write_model_challenger_proposal",
        lambda path: (Path(path), receipt),
    )

    def _fake_verify(
        loaded: dict[str, object],
        current: dict[str, object],
    ) -> dict[str, object]:
        captured["loaded"] = loaded
        captured["current"] = current
        return {"status": verification_status}

    monkeypatch.setattr(
        "dayu.services.write_service.verify_write_model_challenger_proposal",
        _fake_verify,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "format_write_model_challenger_verification_report",
        lambda payload: [f"verification={payload['status']}"],
    )

    exit_code = WriteService.print_report(
        tmp_path,
        routing_history_root=tmp_path / "history",
        routing_proposal_input=target,
    )

    output = capsys.readouterr().out
    assert exit_code == expected_exit_code
    assert captured == {
        "loaded": receipt,
        "current": proposal,
    }
    assert f"Challenger 提案凭据: {target}" in output
    assert f"verification={verification_status}" in output


@pytest.mark.unit
def test_write_service_report_rejects_invalid_proposal_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.build_write_model_health_trend",
        lambda *_args, **_kwargs: {
            "challenger_proposal": {"status": "ready"},
        },
    )
    monkeypatch.setattr(
        "dayu.services.write_service.format_write_model_health_report",
        lambda _payload: [],
    )
    monkeypatch.setattr(
        "dayu.services.write_service.load_write_model_challenger_proposal",
        lambda _path: (_ for _ in ()).throw(
            ValueError("fingerprint mismatch")
        ),
    )

    exit_code = WriteService.print_report(
        tmp_path,
        routing_history_root=tmp_path / "history",
        routing_proposal_input=tmp_path / "proposal.json",
    )

    assert exit_code == 2
    assert "Challenger 提案验证失败" in capsys.readouterr().out


@pytest.mark.unit
def test_write_service_report_issues_preflight_approval_after_verification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proposal = {"status": "ready", "proposal_fingerprint": "proposal"}
    receipt = {"proposal_fingerprint": "receipt"}
    approval_request = {"approved_by": "operator"}
    approval: dict[str, object] = {
        "status": "approved_for_common_preflight"
    }
    request_path = tmp_path / "approval-request.json"
    approval_path = tmp_path / "approval.json"
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.build_write_model_health_trend",
        lambda *_args, **_kwargs: {"challenger_proposal": proposal},
    )
    monkeypatch.setattr(
        "dayu.services.write_service.format_write_model_health_report",
        lambda _payload: [],
    )
    monkeypatch.setattr(
        "dayu.services.write_service.load_write_model_challenger_proposal",
        lambda path: (Path(path), receipt),
    )
    monkeypatch.setattr(
        "dayu.services.write_service.verify_write_model_challenger_proposal",
        lambda *_args, **_kwargs: {"status": "current"},
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "format_write_model_challenger_verification_report",
        lambda _payload: [],
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "load_write_model_challenger_preflight_approval_request",
        lambda path: (Path(path), approval_request),
    )

    def _fake_build(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return approval

    monkeypatch.setattr(
        "dayu.services.write_service."
        "build_write_model_challenger_preflight_approval",
        _fake_build,
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "persist_write_model_challenger_preflight_approval",
        lambda payload, path: (
            captured.update(
                {
                    "persisted_payload": payload,
                    "persisted_path": path,
                }
            )
            or Path(path)
        ),
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "format_write_model_challenger_preflight_approval_report",
        lambda payload: [f"approval={payload['status']}"],
    )

    exit_code = WriteService.print_report(
        tmp_path,
        routing_history_root=tmp_path / "history",
        routing_proposal_input=tmp_path / "proposal.json",
        routing_preflight_approval_request=request_path,
        routing_preflight_approval_output=approval_path,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert captured["request"] is approval_request
    assert captured["proposal_receipt"] is receipt
    assert captured["current_proposal"] is proposal
    assert captured["persisted_payload"] is approval
    assert captured["persisted_path"] == approval_path
    assert f"Challenger preflight approval request: {request_path}" in output
    assert f"Challenger preflight approval receipt: {approval_path}" in output
    assert "approval=approved_for_common_preflight" in output


@pytest.mark.unit
def test_write_service_report_returns_policy_exit_for_blocked_approval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proposal = {"status": "ready"}
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.build_write_model_health_trend",
        lambda *_args, **_kwargs: {"challenger_proposal": proposal},
    )
    monkeypatch.setattr(
        "dayu.services.write_service.format_write_model_health_report",
        lambda _payload: [],
    )
    monkeypatch.setattr(
        "dayu.services.write_service.load_write_model_challenger_proposal",
        lambda path: (Path(path), proposal),
    )
    monkeypatch.setattr(
        "dayu.services.write_service.verify_write_model_challenger_proposal",
        lambda *_args, **_kwargs: {"status": "current"},
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "format_write_model_challenger_verification_report",
        lambda _payload: [],
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "load_write_model_challenger_preflight_approval_request",
        lambda path: (Path(path), {"approved_by": "operator"}),
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "build_write_model_challenger_preflight_approval",
        lambda **_kwargs: (_ for _ in ()).throw(
            WriteModelPreflightApprovalBlockedError("approval has expired")
        ),
    )
    monkeypatch.setattr(
        "dayu.services.write_service."
        "persist_write_model_challenger_preflight_approval",
        lambda *_args, **_kwargs: pytest.fail(
            "blocked approval must not be persisted"
        ),
    )

    exit_code = WriteService.print_report(
        tmp_path,
        routing_history_root=tmp_path / "history",
        routing_proposal_input=tmp_path / "proposal.json",
        routing_preflight_approval_request=tmp_path / "request.json",
        routing_preflight_approval_output=tmp_path / "approval.json",
    )

    assert exit_code == 4
    assert "blocked: approval has expired" in capsys.readouterr().out


@pytest.mark.unit
def test_write_service_report_falls_back_when_repricing_source_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A moved source summary should not hide the persisted comparison receipt."""

    comparison = {
        "schema_version": "write_run_comparison_v1",
        "verdict": "manual_review",
        "reason_codes": ["complete_same_currency_cost_required"],
        "quality": {"status": "equivalent"},
        "cost": {
            "comparable": False,
            "champion": {"status": "unavailable"},
            "challenger": {"status": "unavailable"},
            "cost_delta": None,
        },
    }
    monkeypatch.setattr(
        "dayu.services.write_service.print_write_report",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "dayu.services.write_service.resolve_write_run_comparison_for_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FileNotFoundError("moved source")
        ),
    )
    monkeypatch.setattr(
        "dayu.services.write_service.load_write_run_comparison",
        lambda *_args, **_kwargs: (
            tmp_path / "challenger_comparison.json",
            comparison,
        ),
    )

    exit_code = WriteService.print_report(
        tmp_path,
        model_catalog={"model": {}},
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "成本重估失败" in output
    assert "Champion/Challenger 对比" in output
    assert "manual_review" in output
    assert "路由状态   : 未记录" in output
    assert "当前模型目录只读重估" not in output


class _FakeCompanyMetaProvider:
    """测试用公司 meta provider。"""

    def get_company_name(self, ticker: str) -> str:
        return f"{ticker}-NAME"

    def get_company_meta_summary(self, ticker: str) -> dict[str, str]:
        return {"ticker": ticker, "company_name": f"{ticker}-NAME"}


@dataclass(frozen=True)
class _FakeCreatedSession:
    """测试用已创建 Host session。"""

    session_id: str


class _CancellingHostedGateway:
    """测试用宿主网关，模拟同步路径在 Host 内部收口为取消退出码。"""

    def __init__(self) -> None:
        """初始化测试网关。"""

        self.last_spec: HostedRunSpec | None = None
        self.create_session_count = 0
        self.sync_call_count = 0

    def create_session(self, source: SessionSource) -> _FakeCreatedSession:
        """返回固定 session。

        Args:
            source: session 来源。

        Returns:
            固定 session 记录。

        Raises:
            无。
        """

        del source
        self.create_session_count += 1
        return _FakeCreatedSession(session_id="cancelled-session")

    def run_operation_sync(
        self,
        *,
        spec: HostedRunSpec,
        operation: Callable[[HostedRunContext], int],
        on_cancel: Callable[[], int] | None = None,
    ) -> int:
        """直接走 Host 取消收口回调。

        Args:
            spec: 托管同步执行规格。
            operation: 同步执行体。
            on_cancel: 取消收口回调。

        Returns:
            取消退出码。

        Raises:
            AssertionError: 未提供取消回调时抛出。
        """

        del operation
        self.last_spec = spec
        self.sync_call_count += 1
        if on_cancel is None:
            raise AssertionError("测试前提不成立：缺少 on_cancel 回调")
        return on_cancel()


class _FakeConfigLoader:
    """测试用配置加载器。"""

    def load_run_config(self) -> dict[str, Any]:
        """返回最小 run 配置。"""

        return {}

    def load_llm_models(self) -> dict[str, ModelConfig]:
        """返回空模型表。"""

        return {}

    def load_llm_model(self, model_name: str) -> ModelConfig:
        """返回最小模型配置。"""

        return {"model": model_name, "max_context_tokens": 32000}

    def load_toolset_registrars(self) -> dict[str, str]:
        """返回空 registrar 配置。"""

        return {}

    def collect_model_referenced_env_vars(self, model_names: Iterable[str]) -> tuple[str, ...]:
        """返回指定模型引用的环境变量。"""

        del model_names
        return ()


class _FakePromptAssetStore:
    """测试用 prompt 资产仓储。"""

    def load_scene_manifest(self, scene_name: str) -> SceneManifestAsset:
        """当前测试不应读取 scene manifest。"""

        return {
            "scene": scene_name,
            "model": {
                "default_name": "test-model",
                "allowed_names": ["test-model"],
                "temperature_profile": "default",
            },
            "runtime": {
                "agent": {"max_iterations": 4},
                "runner": {"tool_timeout_seconds": 90.0},
            },
            "fragments": [],
            "context_slots": [],
            "tool_selection": {"mode": "allow_all"},
        }

    @overload
    def load_fragment_template(self, fragment_path: str, *, required: Literal[True] = True) -> str:
        ...

    @overload
    def load_fragment_template(self, fragment_path: str, *, required: Literal[False]) -> str | None:
        ...

    def load_fragment_template(self, fragment_path: str, *, required: bool = True) -> str | None:
        """当前测试不应读取 fragment。"""

        del fragment_path, required
        return None

    def load_task_prompt(self, task_name: str) -> str:
        """当前测试不应读取 task prompt。"""

        raise AssertionError(f"当前测试不应读取 task prompt: {task_name}")

    def load_task_prompt_contract(self, task_name: str) -> TaskPromptContractAsset:
        """当前测试不应读取 task contract。"""

        return {
            "prompt_name": task_name,
            "version": "1",
            "inputs": [],
        }


class _FakeModelCatalog(ModelCatalogProtocol):
    """测试用模型目录。"""

    def load_model(self, model_name: str) -> ModelConfig:
        """返回最小模型配置。"""

        return {"model": model_name, "max_context_tokens": 32000}

    def load_models(self) -> dict[str, ModelConfig]:
        """返回空模型表。"""

        return {}


class _FakeSceneDefinitionReader(SceneDefinitionReader):
    """测试用 scene reader。"""

    def __init__(self) -> None:
        """初始化空 reader。"""

        pass

    def read(self, scene_name: str):
        """当前测试不会调用 read。"""

        raise AssertionError(f"当前测试不应读取 scene 定义: {scene_name}")


class _FakeConversationPolicyReader(ConversationPolicyReader):
    """测试用 conversation policy reader。"""

    def __init__(self) -> None:
        """初始化空 reader。"""

        pass

    def resolve(self, *, resolved_execution_options: ResolvedExecutionOptions, model_config: ModelConfig | None):
        """返回当前 resolved options 自带的 memory settings。"""

        del model_config
        return resolved_execution_options.conversation_memory_settings


class _FakeSceneExecutionAcceptancePreparer(SceneExecutionAcceptancePreparer):
    """测试用 scene 执行接受器。"""

    def __init__(self, *, workspace_dir: Path) -> None:
        """构造只覆盖被测方法的最小 preparer。"""

        super().__init__(
            workspace_dir=workspace_dir,
            base_execution_options=build_base_execution_options(workspace_dir=workspace_dir, run_config={}),
            model_catalog=_FakeModelCatalog(),
            scene_definition_reader=_FakeSceneDefinitionReader(),
            conversation_policy_reader=_FakeConversationPolicyReader(),
        )

    def resolve_execution_options(
        self,
        scene_name: str,
        execution_options: ExecutionOptions | None = None,
    ) -> ResolvedExecutionOptions:
        """返回最小可用的 resolved execution options。"""

        del scene_name, execution_options
        return build_base_execution_options(workspace_dir=self.workspace_dir, run_config={})

    def resolve_scene_model(
        self,
        scene_name: str,
        execution_options: ExecutionOptions | None = None,
    ) -> SceneModelConfig:
        """返回稳定 scene model 摘要。"""

        del execution_options
        return SceneModelConfig(name=f"model-{scene_name}", temperature=0.2)


def _build_workspace(
    workspace_dir: Path,
    *,
    config_loader: ConfigLoaderProtocol | None = None,
) -> WorkspaceResources:
    """构造最小 WorkspaceResources。"""

    return WorkspaceResources(
        workspace_dir=workspace_dir,
        config_root=workspace_dir / "config",
        output_dir=workspace_dir / "output",
        config_loader=config_loader or _FakeConfigLoader(),
        prompt_asset_store=_FakePromptAssetStore(),
    )


def _run_registry() -> RunRegistryProtocol:
    """构造满足 Host 依赖的 run registry。"""

    from tests.application.conftest import StubRunRegistry

    return StubRunRegistry()


def _build_request() -> WriteRequest:
    """构建最小写作请求。"""

    return WriteRequest(
        write_config=WriteRunConfig(
            ticker="AAPL",
            company="Apple",
            template_path="/tmp/template.md",
            output_dir="/tmp/output",
            write_max_retries=1,
            web_provider="off",
            resume=False,
        ),
    )


def _build_service(
    *,
    workspace: WorkspaceResources,
    host_gateway: _CancellingHostedGateway,
) -> WriteService:
    """构造用于体检测试的最小写作服务。"""

    return WriteService(
        host=cast(HostedExecutionGatewayProtocol, host_gateway),
        host_governance=cast(HostGovernanceProtocol, host_gateway),
        workspace=workspace,
        scene_execution_acceptance_preparer=_FakeSceneExecutionAcceptancePreparer(
            workspace_dir=workspace.workspace_dir,
        ),
    )


@pytest.mark.unit
def test_write_service_preflight_resolves_full_dual_model_scene_plan() -> None:
    """全文模式体检应覆盖主写、决策、审计和修复链路。"""

    workspace = _build_workspace(Path("/tmp/dayu-write-preflight-full"))
    service = _build_service(
        workspace=workspace,
        host_gateway=_CancellingHostedGateway(),
    )

    result = service.preflight(_build_request())

    assert result.ready is True
    assert {scene.scene_name for scene in result.scenes} == {
        "write",
        "regenerate",
        "fix",
        "repair",
        "infer",
        "decision",
        "audit",
        "confirm",
        "overview",
    }
    assert {scene.model_role for scene in result.scenes} == {
        WriteModelRole.PRIMARY,
        WriteModelRole.AUDIT,
    }
    assert result.issues == ()


@pytest.mark.unit
def test_write_service_preflight_rejects_unpriced_models_for_cost_budget() -> None:
    class _UnpricedModelConfigLoader(_FakeConfigLoader):
        def load_llm_models(self) -> dict[str, ModelConfig]:
            return {
                f"model-{scene_name}": {
                    "model": f"model-{scene_name}",
                    "max_context_tokens": 32_000,
                }
                for scene_name in (
                    "write",
                    "regenerate",
                    "fix",
                    "repair",
                    "infer",
                    "decision",
                    "audit",
                    "confirm",
                    "overview",
                )
            }

    workspace = _build_workspace(
        Path("/tmp/dayu-write-preflight-budget"),
        config_loader=_UnpricedModelConfigLoader(),
    )
    service = _build_service(
        workspace=workspace,
        host_gateway=_CancellingHostedGateway(),
    )
    request = replace(
        _build_request(),
        write_config=replace(
            _build_request().write_config,
            write_max_estimated_cost=10.0,
            write_budget_currency="CNY",
        ),
    )

    result = service.preflight(request)

    assert result.ready is False
    assert result.issues
    assert {
        issue.code for issue in result.issues
    } == {WritePreflightIssueCode.BUDGET_CONFIGURATION}
    assert all("缺少可审计价格" in issue.message for issue in result.issues)


@pytest.mark.unit
def test_write_service_preflight_infer_mode_only_requires_audit_environment() -> None:
    """infer-only 只暴露审核 scene，但仍验证完整运行签名模型配置。"""

    workspace = _build_workspace(Path("/tmp/dayu-write-preflight-infer"))
    service = _build_service(
        workspace=workspace,
        host_gateway=_CancellingHostedGateway(),
    )
    request = replace(
        _build_request(),
        write_config=replace(_build_request().write_config, infer=True),
    )

    result = service.preflight(request)

    assert result.ready is True
    assert tuple(scene.scene_name for scene in result.scenes) == ("infer",)
    assert tuple(scene.model_role for scene in result.scenes) == (WriteModelRole.AUDIT,)
    assert {scene.scene_name for scene in result.signature_scenes} == {
        "write",
        "regenerate",
        "fix",
        "repair",
        "infer",
        "decision",
        "audit",
        "confirm",
        "overview",
    }


@pytest.mark.unit
def test_write_service_preflight_resolves_and_persists_fallback_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """体检应校验 fallback 路由，并把完整 fallback 签名交给流水线。"""

    from tests.application.conftest import StubHostExecutor, StubSessionRegistry

    workspace = _build_workspace(Path("/tmp/dayu-write-preflight-fallback"))
    host = Host(
        executor=StubHostExecutor(),
        session_registry=StubSessionRegistry(),
        run_registry=_run_registry(),
    )

    class _FallbackAwarePreparer(_FakeSceneExecutionAcceptancePreparer):
        def resolve_scene_model(
            self,
            scene_name: str,
            execution_options: ExecutionOptions | None = None,
        ) -> SceneModelConfig:
            model_name = str(
                execution_options.model_name
                if execution_options is not None and execution_options.model_name
                else f"model-{scene_name}"
            )
            return SceneModelConfig(name=model_name, temperature=0.2)

    service = WriteService(
        host=host,
        host_governance=host,
        workspace=workspace,
        scene_execution_acceptance_preparer=_FallbackAwarePreparer(
            workspace_dir=workspace.workspace_dir,
        ),
    )
    request = replace(
        _build_request(),
        write_config=replace(
            _build_request().write_config,
            write_fallback_model_name="fallback-write",
            audit_fallback_model_name="fallback-audit",
        ),
    )
    captured: dict[str, SceneModelConfig] = {}

    def _capture_run_write_pipeline(**kwargs: object) -> int:
        write_config = kwargs["write_config"]
        assert isinstance(write_config, WriteRunConfig)
        captured.update(write_config.scene_fallback_models)
        return 0

    monkeypatch.setattr(
        "dayu.services.write_service.run_write_pipeline",
        _capture_run_write_pipeline,
    )

    preflight = service.preflight(request)

    assert preflight.ready is True
    assert {
        scene.model_name for scene in preflight.fallback_scenes
    } == {"fallback-write", "fallback-audit"}
    assert {
        scene.model_name for scene in preflight.signature_fallback_scenes
    } == {"fallback-write", "fallback-audit"}
    assert service.run(request) == 0
    assert set(captured) == {
        "write",
        "regenerate",
        "fix",
        "repair",
        "infer",
        "decision",
        "audit",
        "confirm",
        "overview",
    }
    assert captured["write"].name == "fallback-write"
    assert captured["audit"].name == "fallback-audit"


@pytest.mark.unit
def test_write_service_infer_run_preserves_complete_scene_model_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """infer-only 正式运行仍应保留完整 scene 模型映射，避免误清理旧章节。"""

    from tests.application.conftest import StubHostExecutor, StubSessionRegistry

    workspace = _build_workspace(Path("/tmp/dayu-write-preflight-infer-signature"))
    host = Host(
        executor=StubHostExecutor(),
        session_registry=StubSessionRegistry(),
        run_registry=_run_registry(),
    )
    service = WriteService(
        host=host,
        host_governance=host,
        workspace=workspace,
        scene_execution_acceptance_preparer=_FakeSceneExecutionAcceptancePreparer(
            workspace_dir=workspace.workspace_dir,
        ),
    )
    request = replace(
        _build_request(),
        write_config=replace(_build_request().write_config, infer=True),
    )
    captured_scene_models: dict[str, SceneModelConfig] = {}

    def _capture_run_write_pipeline(**kwargs: object) -> int:
        write_config = kwargs["write_config"]
        assert isinstance(write_config, WriteRunConfig)
        captured_scene_models.update(write_config.scene_models)
        return 0

    monkeypatch.setattr("dayu.services.write_service.run_write_pipeline", _capture_run_write_pipeline)

    assert service.run(request) == 0
    assert set(captured_scene_models) == {
        "write",
        "regenerate",
        "fix",
        "repair",
        "infer",
        "decision",
        "audit",
        "confirm",
        "overview",
    }


@pytest.mark.unit
def test_write_service_preflight_blocks_before_host_session_without_leaking_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺少审核模型密钥时应在创建 Host session 前失败且不泄露已有密钥。"""

    class _DualModelConfigLoader(_FakeConfigLoader):
        """返回 DeepSeek 与 Claude 所需环境变量的测试配置加载器。"""

        def collect_model_referenced_env_vars(self, model_names: Iterable[str]) -> tuple[str, ...]:
            """返回双模型环境变量名称。"""

            del model_names
            return ("MIMO_API_KEY", "DEEPSEEK_API_KEY")

    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret-must-not-appear")
    workspace = _build_workspace(
        Path("/tmp/dayu-write-preflight-env"),
        config_loader=_DualModelConfigLoader(),
    )
    host_gateway = _CancellingHostedGateway()
    service = _build_service(workspace=workspace, host_gateway=host_gateway)

    result = service.preflight(_build_request())

    assert result.ready is False
    assert result.required_environment_variables == ("DEEPSEEK_API_KEY", "MIMO_API_KEY")
    assert tuple(issue.code for issue in result.issues) == (
        WritePreflightIssueCode.MISSING_ENVIRONMENT_VARIABLE,
    )
    assert result.issues[0].environment_variable == "MIMO_API_KEY"
    assert "deepseek-secret-must-not-appear" not in repr(result)

    with pytest.raises(WritePreflightError) as exc_info:
        service.run(_build_request())

    assert host_gateway.create_session_count == 0
    assert host_gateway.sync_call_count == 0
    assert "MIMO_API_KEY" in str(exc_info.value)
    assert "deepseek-secret-must-not-appear" not in str(exc_info.value)


@pytest.mark.unit
def test_write_service_runs_pipeline_via_host_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    """WriteService 应通过 host executor 托管同步执行。"""

    from tests.application.conftest import StubHostExecutor, StubSessionRegistry

    host_executor = StubHostExecutor()
    workspace = _build_workspace(Path("/tmp/dayu-write-service"))
    host = Host(
        executor=host_executor,
        session_registry=StubSessionRegistry(),
        run_registry=_run_registry(),
    )
    service = WriteService(
        host=host,
        host_governance=host,
        workspace=workspace,
        scene_execution_acceptance_preparer=_FakeSceneExecutionAcceptancePreparer(
            workspace_dir=workspace.workspace_dir,
        ),
        company_name_resolver=lambda ticker: f"{ticker}-NAME",
        company_meta_summary_resolver=lambda ticker: {"ticker": ticker},
    )

    monkeypatch.setattr(
        "dayu.services.write_service.run_write_pipeline",
        lambda **kwargs: 0,
    )

    result = service.run(_build_request())

    assert result == 0
    assert host_executor.sync_call_count == 1
    assert host_executor.last_spec is not None
    assert host_executor.last_spec.operation_name == "write_pipeline"
    assert host_executor.last_spec.business_concurrency_lane is None
    assert host_executor.last_spec.concurrency_acquire_policy == ConcurrencyAcquirePolicy.unbounded()
    assert host_executor.last_spec.metadata == {}

    assert isinstance(service, WriteServiceProtocol)


@pytest.mark.unit
def test_write_service_resolves_overview_scene_with_primary_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """WriteService 应为 overview scene 解析主写作模型配置。"""

    from tests.application.conftest import StubHostExecutor, StubSessionRegistry

    workspace = _build_workspace(Path("/tmp/dayu-write-service-overview"))
    host = Host(
        executor=StubHostExecutor(),
        session_registry=StubSessionRegistry(),
        run_registry=_run_registry(),
    )
    scene_queries: list[tuple[str, ExecutionOptions | None]] = []
    captured_scene_models: dict[str, SceneModelConfig] = {}

    class _CapturingSceneExecutionAcceptancePreparer(_FakeSceneExecutionAcceptancePreparer):
        """记录 scene model 查询的测试用 preparer。"""

        def resolve_scene_model(
            self,
            scene_name: str,
            execution_options: ExecutionOptions | None = None,
        ) -> SceneModelConfig:
            """记录查询并返回稳定 scene model 摘要。"""

            scene_queries.append((scene_name, execution_options))
            return SceneModelConfig(name=f"model-{scene_name}", temperature=0.2)

    service = WriteService(
        host=host,
        host_governance=host,
        workspace=workspace,
        scene_execution_acceptance_preparer=_CapturingSceneExecutionAcceptancePreparer(
            workspace_dir=workspace.workspace_dir,
        ),
    )

    def _capture_run_write_pipeline(**kwargs: object) -> int:
        write_config = kwargs["write_config"]
        assert isinstance(write_config, WriteRunConfig)
        captured_scene_models.update(write_config.scene_models)
        return 0

    monkeypatch.setattr("dayu.services.write_service.run_write_pipeline", _capture_run_write_pipeline)

    result = service.run(_build_request())

    assert result == 0
    assert "overview" in captured_scene_models
    assert captured_scene_models["overview"].name == "model-overview"
    assert any(scene_name == "overview" for scene_name, _execution_options in scene_queries)


@pytest.mark.unit
def test_write_service_returns_cancelled_exit_code_when_host_sync_path_is_cancelled() -> None:
    """WriteService 应在真实宿主同步取消收口路径上返回显式取消退出码。"""

    workspace = _build_workspace(Path("/tmp/dayu-write-service-cancelled"))
    host_gateway = _CancellingHostedGateway()
    service = WriteService(
        host=cast(HostedExecutionGatewayProtocol, host_gateway),
        host_governance=cast(HostGovernanceProtocol, host_gateway),
        workspace=workspace,
        scene_execution_acceptance_preparer=_FakeSceneExecutionAcceptancePreparer(
            workspace_dir=workspace.workspace_dir,
        ),
    )

    result = service.run(_build_request())

    assert result == WRITE_CANCELLED_EXIT_CODE
    assert host_gateway.sync_call_count == 1
    assert host_gateway.last_spec is not None
    assert host_gateway.last_spec.operation_name == "write_pipeline"


@pytest.mark.unit
def test_write_service_passes_hosted_run_context_cancellation_token_to_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WriteService 必须把 ``HostedRunContext.cancellation_token`` 透传给 ``run_write_pipeline``。

    回归覆盖：之前 ``operation`` lambda 直接丢弃 ``context``，
    导致 pipeline 无法在章节边界响应 ``host.cancel_run`` 触发的协作式取消。
    """

    from tests.application.conftest import StubHostExecutor, StubSessionRegistry

    workspace = _build_workspace(Path("/tmp/dayu-write-service-token"))
    host = Host(
        executor=StubHostExecutor(),
        session_registry=StubSessionRegistry(),
        run_registry=_run_registry(),
    )
    service = WriteService(
        host=host,
        host_governance=host,
        workspace=workspace,
        scene_execution_acceptance_preparer=_FakeSceneExecutionAcceptancePreparer(
            workspace_dir=workspace.workspace_dir,
        ),
    )

    captured: dict[str, object] = {}

    def _capture(**kwargs: object) -> int:
        captured["cancellation_token"] = kwargs.get("cancellation_token")
        return 0

    monkeypatch.setattr("dayu.services.write_service.run_write_pipeline", _capture)

    assert service.run(_build_request()) == 0

    from dayu.contracts.cancellation import CancellationToken

    assert isinstance(captured.get("cancellation_token"), CancellationToken)


@pytest.mark.unit
def test_write_service_run_pipeline_cancellation_token_triggers_pipeline_cancelled_error() -> None:
    """token 触发后，``run_write_pipeline`` 内部应立刻抛 ``CancelledError``。

    回归覆盖：write 真正接入了协作式取消的章节边界 checkpoint。
    """

    from dayu.contracts.cancellation import CancelledError, CancellationToken
    from dayu.services.internal.write_pipeline.pipeline import WritePipelineRunner

    token = CancellationToken()
    token.cancel()

    runner = object.__new__(WritePipelineRunner)
    # 仅供 _check_cancellation 单元 verify。
    runner._cancellation_token = token  # type: ignore[attr-defined]

    with pytest.raises(CancelledError):
        runner._check_cancellation()  # type: ignore[attr-defined]
