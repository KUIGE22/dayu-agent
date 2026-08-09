"""刻画投资 Agent AAPL 固定验收语料与现有生产 owner 契约。"""

from __future__ import annotations

import collections.abc
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, fields, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Mapping, TypeAlias
from unittest.mock import create_autospec

import pytest

from dayu.cli import main as dayu_main_module
from dayu.cli.commands import write as write_command_module
from dayu.cli.commands._research_template_materialize import (
    _materialization_artifact_paths,
    materialize_research_template_bundle,
    materialize_research_workspace,
)
from dayu.cli.commands._research_template_monitoring import (
    build_monitoring_execution_plan,
    validate_monitoring_execution_plan,
)
from dayu.cli.commands._write_dispatch import _EarlyWriteSubcommandEntry
from dayu.cli.commands.research_workbook import build_research_workbook_payload
from dayu.contracts.fins import (
    DownloadCommandPayload,
    DownloadFilingResultItem,
    DownloadFilingResultStatus,
    DownloadResultData,
    FinsCommand,
    FinsCommandName,
    FinsEvent,
    FinsEventType,
    ProcessCommandPayload,
    ProcessDocumentResultItem,
    ProcessResultData,
    UploadFileResultItem,
    UploadMaterialCommandPayload,
    UploadMaterialResultData,
)
from dayu.contracts.fins import (
    DownloadSummary as OwnerDownloadSummary,
)
from dayu.contracts.fins import (
    ProcessSummary as OwnerProcessSummary,
)
from dayu.contracts.model_usage import ModelUsage
from dayu.fins.cli_formatters import format_cli_result
from dayu.fins.domain.document_models import CompanyMeta, FileObjectMeta, SourceHandle
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.docling_upload_service import build_material_ids
from dayu.fins.storage import (
    DocumentBlobRepositoryProtocol,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.storage.fs_company_meta_repository import FsCompanyMetaRepository
from dayu.redaction import REDACTED_SECRET
from dayu.services.contracts import FinsSubmission, FinsSubmitRequest, SceneModelConfig, WriteRunConfig
from dayu.services.internal.write_pipeline.execution_summary_builder import ExecutionSummaryBuilder
from dayu.services.internal.write_pipeline.model_usage_ledger import WriteModelUsageLedger
from dayu.services.internal.write_pipeline.models import ChapterResult, RunManifest
from dayu.startup.config_file_resolver import resolve_package_assets_path, resolve_package_config_path
from utils import investment_agent_acceptance as acceptance_cli_module
from utils import investment_agent_acceptance_contracts as acceptance_contracts_module
from utils import investment_agent_acceptance_evaluator as acceptance_evaluator_module
from utils.investment_agent_acceptance import (
    MappingEnvironmentPresenceProvider,
    PrepareCliCommand,
    PreparedAcceptance,
    PrepareRequest,
    PrepareServices,
    RepositoryState,
    RunCliCommand,
    RunRequest,
    RunResult,
    RunServices,
    RuntimeIdentity,
    VerifyCliCommand,
    VerifyRequest,
    build_terminal_verify_command,
    parse_cli_arguments,
    prepare_acceptance,
    run_acceptance,
    safe_argv_and_digests,
    verify_acceptance,
)
from utils.investment_agent_acceptance_contracts import (
    PLANNED_PHASE_COMMAND_COUNTS,
    REQUIRED_ENVIRONMENT_NAMES,
    REQUIRED_RESEARCH_ARTIFACTS,
    SUBPROCESS_ENV_POLICY,
    AcceptancePlan,
    BudgetLimits,
    CommandEvidence,
    CommandRecord,
    ContractError,
    DownloadCommandEvidence,
    DownloadEvidenceRow,
    EnvironmentPresence,
    FingerprintDriftError,
    JsonObject,
    MaterialImportCommandEvidence,
    ModelRoles,
    PackageInputFingerprints,
    PhaseReceipt,
    PhaseSpec,
    PriceSnapshot,
    ProcessCommandEvidence,
    ProcessedState,
    ProcessEvidenceRow,
    SourceWindow,
    assert_package_input_fingerprints,
    build_package_input_fingerprints,
    canonical_json_bytes,
    canonical_json_sha256,
    load_json_file,
    parse_acceptance_contract,
    parse_acceptance_plan,
    parse_acceptance_receipt,
    parse_json_bytes,
    parse_owner_run_summary,
    parse_phase_receipt,
)
from utils.investment_agent_acceptance_contracts import (
    DownloadSummary as AcceptanceDownloadSummary,
)
from utils.investment_agent_acceptance_contracts import (
    ProcessSummary as AcceptanceProcessSummary,
)
from utils.investment_agent_acceptance_evaluator import (
    AcceptanceInputs,
    EvaluationResult,
    FixtureInputRequest,
    RepositoryInventoryRequest,
    build_source_inventory_from_repositories,
    evaluate_acceptance,
    inspect_research_artifacts,
    load_fixture_inputs,
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "investment_agent" / "aapl_acceptance"
_JSON_FIXTURE_SHA256 = {
    "contract-v1.json": "60a7e0dfdccd35120542b7018b46924c34a5fe97027cff8fb533d8d3e5a07cd4",
    "price-snapshot-v1.json": "6c8da51d65063576597534880986a4093568b70e3d69dce83c6909e2bb388a50",
    "quality-review-v1.json": "90ac48387253599e6d025ab287fa169e815cc1d0f4e5ec62cdc72d1bb1ca3bd8",
    "run-summary-v1.json": "d3fdfacc5df7c8519586e01c5c2c78770c4f39b1da42a7d3986602b4510e3fa4",
    "source-inventory-v1.json": "9a014eb569d9f0841c14bf84e6911b37ba802e96199303e8e0e229c0454478d5",
    "write-manifest-v1.json": "066d398d7c651b2b16ff230be6ee33f640f3ee160a6d6fb2e2dac20c5a1cb16f",
}
_REPORT_SHA256 = "4b256afc6fcae8d3ed543654c0a24f2ef0579a0b18ee70b7dad46bdd75914796"
_PRICE_MATERIAL_DOCUMENT_ID = build_material_ids(
    form_type="MATERIAL_OTHER",
    material_name="aapl-price-snapshot",
    fiscal_year=None,
    fiscal_period=None,
)[0]
_WORKBOOK_CATEGORIES = {
    "research_question",
    "business_analysis",
    "evidence_requirement",
    "monitoring_variable",
    "falsifier",
    "synthesis",
    "valuation",
    "catalyst",
    "management_governance",
    "portfolio_decision",
}
_RESEARCH_ARTIFACT_NAMES = list(REQUIRED_RESEARCH_ARTIFACTS)
_DOCUMENT_KEYS = {
    "document_id",
    "source_kind",
    "form",
    "filing_date",
    "report_date",
    "fiscal_year",
    "fiscal_period",
    "accession",
    "source_locator",
    "primary_file_sha256",
    "ingest_complete",
    "processed",
    "processed_state_fingerprint",
}
_PROCESSED_KEYS = {
    "exists",
    "parser_version",
    "quality",
    "reprocess_required",
    "schema_version",
    "source_fingerprint",
}


def _slice2_v2_plan(tmp_path: Path, package_inputs: PackageInputFingerprints) -> AcceptancePlan:
    """构造供 strict v2 contract 回归使用的最小合法 plan。

    Args:
        tmp_path: pytest 隔离目录。
        package_inputs: 当前 package 指纹闭包。

    Returns:
        不执行任何命令的严格 v2 plan 值。

    Raises:
        ContractError: 测试构造与 v2 schema 不一致时抛出。
    """

    phase_specs = tuple(
        PhaseSpec(
            phase_name=phase_name,
            commands=tuple(
                (Path(sys.executable).resolve().as_posix(), "-m", "dayu.cli", phase_name, str(index))
                for index in range(command_count)
            ),
        )
        for phase_name, command_count in PLANNED_PHASE_COMMAND_COUNTS
    )
    return AcceptancePlan(
        ticker="AAPL",
        company="Apple Inc.",
        research_template="technology",
        as_of=datetime(2025, 2, 1, tzinfo=UTC),
        git_sha="a" * 64,
        dirty=False,
        python_version="3.11.15",
        platform="darwin",
        timezone="UTC",
        run_root=(tmp_path / "run").resolve().as_posix(),
        package_inputs=package_inputs,
        price_snapshot_sha256="b" * 64,
        price_material_sha256="c" * 64,
        budget=_APPROVED_BUDGET,
        max_wall_seconds=_MAX_WALL_SECONDS,
        termination_grace_seconds=10,
        subprocess_env_policy=SUBPROCESS_ENV_POLICY,
        price_material_document_id="mat_" + "d" * 40,
        model_roles=ModelRoles(primary="deepseek-v4-pro", audit="mimo-v2.5-pro-thinking"),
        phase_specs=phase_specs,
        required_environment=tuple(
            EnvironmentPresence(name=name, present=True) for name in REQUIRED_ENVIRONMENT_NAMES
        ),
        terminal_action="verify",
        required_research_artifacts=tuple(_RESEARCH_ARTIFACT_NAMES),
    )


@dataclass(frozen=True)
class _StaticRepositoryStateProvider:
    """测试用固定 Git 状态 provider。

    Args:
        state: prepare/run 共享的 commit 与 dirty 事实。

    Returns:
        不读取真实仓库的 provider。

    Raises:
        本类不显式抛出异常。
    """

    state: RepositoryState

    def read(self, repository_root: Path) -> RepositoryState:
        """返回注入状态。

        Args:
            repository_root: 为满足 owner 协议传入的仓库根。

        Returns:
            固定状态。

        Raises:
            本方法不显式抛出异常。
        """

        assert repository_root.is_dir()
        return self.state


@dataclass(frozen=True)
class _FixedClock:
    """测试用不前进 UTC/monotonic 时钟。

    Args:
        now: 固定 UTC 时间。
        monotonic_value: 固定单调秒数。

    Returns:
        可复现 receipt 时钟。

    Raises:
        本类不显式抛出异常。
    """

    now: datetime
    monotonic_value: float = 100.0

    def utc_now(self) -> datetime:
        """返回固定 UTC 时间。

        Args:
            无。

        Returns:
            注入时间。

        Raises:
            本方法不显式抛出异常。
        """

        return self.now

    def monotonic(self) -> float:
        """返回固定单调值。

        Args:
            无。

        Returns:
            注入秒数。

        Raises:
            本方法不显式抛出异常。
        """

        return self.monotonic_value


@dataclass
class _AdvancingClock:
    """允许 fake Popen.start 显式推进 monotonic 的测试时钟。

    Args:
        now: 固定 UTC receipt 时间。
        monotonic_value: 当前单调秒数。

    Returns:
        可由 fake factory 推进的时钟。

    Raises:
        本类不显式抛出异常。
    """

    now: datetime
    monotonic_value: float

    def utc_now(self) -> datetime:
        """返回固定 UTC 时间。

        Args:
            无。

        Returns:
            注入时间。

        Raises:
            本方法不显式抛出异常。
        """

        return self.now

    def monotonic(self) -> float:
        """返回当前可推进单调值。

        Args:
            无。

        Returns:
            当前单调秒数。

        Raises:
            本方法不显式抛出异常。
        """

        return self.monotonic_value


def _fake_owner_stdout(argv: tuple[str, ...]) -> bytes:
    """为旧 runner lifecycle 测试生成可被严格 ingress 接受的 owner stdout。

    Args:
        argv: 当前 plan-owned command。

    Returns:
        download/upload/process 为固定 UTF-8 formatter 形状，其它命令为空流。

    Raises:
        AssertionError: owner command 缺计划内必需 token 时抛出。
    """

    if len(argv) < 4:
        return b""
    action = argv[3]
    if action == "download":
        forms_start = argv.index("--forms") + 1
        forms: list[str] = []
        for token in argv[forms_start:]:
            if token.startswith("--"):
                break
            forms.append(token)
        form = "DEF 14A" if "DEF14A" in forms else ("10-K" if "10K" in forms else "10-Q")
        accession = {
            "10-K": "0000320193-24-000123",
            "10-Q": "0000320193-24-000124",
            "DEF 14A": "0000320193-24-000125",
        }[form]
        return (
            "下载结果\n"
            "- ticker: AAPL\n"
            "- status: ok\n"
            "- 汇总: total=1, downloaded=1, skipped=0, failed=0, elapsed_ms=1, reused_downloads=0, converted=1\n"
            "成功下载的 filings:\n"
            f"  - fil_{accession} | form={form} | filing_date=2025-01-30 | report_date=2025-01-30 | "
            "status=downloaded | downloaded_files=1 | skipped_files=0 | failed_files=0 | reason=- | message=-\n"
            "跳过的 filings:\n"
            "  - （无）\n"
            "失败的 filings:\n"
            "  - （无）"
        ).encode()
    if action == "upload_material":
        document_id = argv[argv.index("--document-id") + 1]
        return (
            "上传材料结果\n"
            "- pipeline: upload_material\n"
            "- ticker: AAPL\n"
            "- status: ok\n"
            "- material_action: create\n"
            f"- document_id: {document_id}\n"
            f"- source_fingerprint: {'d' * 64}\n"
            "- report_date: 2025-01-15\n"
            "files:\n"
            "  - price-snapshot.material.md"
        ).encode()
    if action == "process":
        return (
            "全量处理结果\n"
            "- ticker: AAPL\n"
            "- status: ok\n"
            "- filings 汇总: total=3, processed=3, skipped=0, failed=0\n"
            "- materials 汇总: total=1, processed=1, skipped=0, failed=0\n"
            "成功处理的 filings:\n"
            "  - fil_0000320193-24-000123 | status=processed\n"
            "  - fil_0000320193-24-000124 | status=processed\n"
            "  - fil_0000320193-24-000125 | status=processed\n"
            "跳过的 filings:\n"
            "  - （无）\n"
            "失败的 filings:\n"
            "  - （无）\n"
            "成功处理的 materials:\n"
            f"  - {_PRICE_MATERIAL_DOCUMENT_ID} | status=processed\n"
            "跳过的 materials:\n"
            "  - （无）\n"
            "失败的 materials:\n"
            "  - （无）"
        ).encode()
    return b""


def _real_download_stdout(status: str = "ok") -> bytes:
    """用 production formatter 构造一条 10-K download stdout。

    Args:
        status: owner 顶层状态。

    Returns:
        人读 formatter UTF-8 bytes。

    Raises:
        本函数不显式抛出异常。
    """

    return format_cli_result(
        FinsCommandName.DOWNLOAD,
        DownloadResultData(
            pipeline="sec",
            status=status,
            ticker="AAPL",
            filings=(
                DownloadFilingResultItem(
                    document_id="fil_0000320193-24-000123",
                    status=DownloadFilingResultStatus.DOWNLOADED,
                    form_type="10-K",
                    filing_date="2025-01-30",
                    report_date="2025-01-30",
                    downloaded_files=1,
                ),
            ),
            summary=OwnerDownloadSummary(total=1, downloaded=1, skipped=0, failed=0, elapsed_ms=1),
        ),
    ).encode()


def _real_material_stdout(
    *,
    status: str = "ok",
    action: str = "create",
    sparse: bool = False,
) -> bytes:
    """用 production formatter 构造 full 或 sparse upload stdout。

    Args:
        status: owner 顶层 ok/skipped/攻击变异。
        action: owner create/update/攻击变异。
        sparse: 是否省略 skipped 允许缺席的条件字段。

    Returns:
        人读 formatter UTF-8 bytes。

    Raises:
        本函数不显式抛出异常。
    """

    return format_cli_result(
        FinsCommandName.UPLOAD_MATERIAL,
        UploadMaterialResultData(
            pipeline="upload_material",
            status=status,
            ticker="AAPL",
            material_action=action,
            files=(UploadFileResultItem(path="price-snapshot.material.md"),),
            form_type=None if sparse else "MATERIAL_OTHER",
            material_name=None if sparse else "aapl-price-snapshot",
            document_id=_PRICE_MATERIAL_DOCUMENT_ID,
            source_fingerprint=None if sparse else "d" * 64,
            report_date=None if sparse else "2025-01-15",
        ),
    ).encode()


def _real_process_stdout(
    *,
    status: str = "ok",
    material_todo: bool = False,
    reason: str | None = None,
) -> bytes:
    """用 production formatter 构造 process 六节 stdout。

    Args:
        status: owner 顶层状态。
        material_todo: 是否使用 owner TODO 摘要分支。
        reason: filing row 不可信 opaque tail。

    Returns:
        人读 formatter UTF-8 bytes。

    Raises:
        本函数不显式抛出异常。
    """

    material_summary = OwnerProcessSummary(
        total=0 if material_todo else 1,
        processed=0 if material_todo else 1,
        skipped=0,
        failed=0,
        todo=material_todo,
    )
    return format_cli_result(
        FinsCommandName.PROCESS,
        ProcessResultData(
            pipeline="sec",
            status=status,
            ticker="AAPL",
            filings=(
                ProcessDocumentResultItem(
                    document_id="fil_0000320193-24-000123",
                    status="processed",
                    reason=reason,
                ),
            ),
            filing_summary=OwnerProcessSummary(total=1, processed=1, skipped=0, failed=0),
            materials=()
            if material_todo
            else (
                ProcessDocumentResultItem(
                    document_id=_PRICE_MATERIAL_DOCUMENT_ID,
                    status="processed",
                ),
            ),
            material_summary=material_summary,
        ),
    ).encode()


@dataclass
class _FakeProcess:
    """fake runner 的单命令退出或 timeout 句柄。

    Args:
        outcome: 整数退出码或 ``timeout``。
        survives_terminate: timeout 后是否必须进入 kill。
        terminate_raises: terminate 是否注入 OSError。
        kill_raises: kill 是否注入 OSError。

    Returns:
        可观察 terminate/kill/wait 的进程句柄。

    Raises:
        subprocess.TimeoutExpired: 注入 timeout 或存活 terminate 时抛出。
    """

    outcome: int | str
    survives_terminate: bool = False
    terminate_raises: bool = False
    kill_raises: bool = False
    stdout: bytes = b""
    stderr: bytes = b""
    timeout_partial_stdout: bytes = b""
    timeout_partial_stderr: bytes = b""
    timeout_drained_stdout: bytes | None = None
    timeout_drained_stderr: bytes | None = None
    terminated: bool = False
    killed: bool = False
    _returncode: int | None = None
    last_communicate_timeout: float | None = None

    @property
    def returncode(self) -> int | None:
        """返回当前退出码。

        Args:
            无。

        Returns:
            未结束为 ``None``，否则为退出码。

        Raises:
            本属性不显式抛出异常。
        """

        return self._returncode

    def communicate(self, *, timeout: float) -> tuple[bytes, bytes]:
        """返回固定输出或触发 timeout。

        Args:
            timeout: runner 计算的剩余 whole-run 秒数。

        Returns:
            空 stdout 与固定 stderr。

        Raises:
            subprocess.TimeoutExpired: outcome 为 timeout 时抛出。
        """

        assert timeout > 0
        self.last_communicate_timeout = timeout
        if self.outcome == "timeout":
            if not self.terminated and not self.killed:
                raise subprocess.TimeoutExpired(
                    cmd="fake",
                    timeout=timeout,
                    output=self.timeout_partial_stdout,
                    stderr=self.timeout_partial_stderr,
                )
            if self.terminated and self.survives_terminate and not self.killed:
                raise subprocess.TimeoutExpired(
                    cmd="fake",
                    timeout=timeout,
                    output=self.timeout_partial_stdout,
                    stderr=self.timeout_partial_stderr,
                )
            self._returncode = -9 if self.killed else -15
            return (
                self.timeout_drained_stdout
                if self.timeout_drained_stdout is not None
                else self.timeout_partial_stdout,
                self.timeout_drained_stderr
                if self.timeout_drained_stderr is not None
                else self.timeout_partial_stderr,
            )
        assert isinstance(self.outcome, int)
        self._returncode = self.outcome
        stderr = self.stderr or (b"sk-abcdefghijklmnopqrstuvwxyz" if self.outcome != 0 else b"")
        return self.stdout, stderr

    def terminate(self) -> None:
        """记录 terminate。

        Args:
            无。

        Returns:
            无。

        Raises:
            本方法不显式抛出异常。
        """

        self.terminated = True
        if self.terminate_raises:
            raise OSError("fake terminate failure")

    def kill(self) -> None:
        """记录 kill。

        Args:
            无。

        Returns:
            无。

        Raises:
            本方法不显式抛出异常。
        """

        self.killed = True
        if self.kill_raises:
            raise OSError("fake kill failure")

    def wait(self, *, timeout: float) -> int:
        """按 terminate/kill 状态返回固定 signal 码。

        Args:
            timeout: 固定 grace 秒数。

        Returns:
            terminate 为 -15，kill 为 -9。

        Raises:
            subprocess.TimeoutExpired: 注入进程在 terminate 后仍存活时抛出。
        """

        assert timeout == 10.0
        if self.killed:
            self._returncode = -9
            return -9
        if self.terminated and self.survives_terminate:
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
        self._returncode = -15
        return -15


@dataclass
class _FakeProcessFactory:
    """按顺序返回 fake 进程并记录 exact argv。

    Args:
        outcomes: 每次 start 对应的退出或 timeout 事实。
        survives_terminate: timeout 进程是否强制走 kill。
        stdout_overrides: 可选的逐命令 owner stdout 攻击样本。
        terminate_raises: terminate 是否注入 OSError。
        kill_raises: kill 是否注入 OSError。

    Returns:
        可用于断言允许前缀的 fake factory。

    Raises:
        AssertionError: 实际 start 数超过注入 outcomes 时抛出。
    """

    outcomes: tuple[int | str, ...]
    survives_terminate: bool = False
    stdout_overrides: tuple[bytes | None, ...] = ()
    terminate_raises: bool = False
    kill_raises: bool = False
    stderr_overrides: tuple[bytes | None, ...] = ()
    timeout_partial_stdout: bytes = b""
    timeout_partial_stderr: bytes = b""
    timeout_drained_stdout: bytes | None = None
    timeout_drained_stderr: bytes | None = None
    start_clock: _AdvancingClock | None = None
    start_delay_seconds: float = 0.0

    def __post_init__(self) -> None:
        """初始化可变调用记录。

        Args:
            无。

        Returns:
            无。

        Raises:
            本方法不显式抛出异常。
        """

        self.calls: list[tuple[str, ...]] = []
        self.processes: list[_FakeProcess] = []

    def start(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        env: Mapping[str, str],
    ) -> _FakeProcess:
        """记录 argv 并返回下一 fake process。

        Args:
            argv: 已与 canonical builder 闭合的命令。
            cwd: 固定 repository root。
            env: 显式 subprocess environment。

        Returns:
            下一 fake 句柄。

        Raises:
            AssertionError: outcomes 不足时抛出。
        """

        index = len(self.calls)
        assert index < len(self.outcomes)
        assert cwd.is_dir()
        assert isinstance(env, dict)
        assert all(env[name] == value for name, value in SUBPROCESS_ENV_POLICY)
        if self.start_clock is not None:
            self.start_clock.monotonic_value += self.start_delay_seconds
        self.calls.append(argv)
        stdout = _fake_owner_stdout(argv)
        if index < len(self.stdout_overrides):
            override = self.stdout_overrides[index]
            if override is not None:
                stdout = override
        stderr = b""
        if index < len(self.stderr_overrides):
            stderr_override = self.stderr_overrides[index]
            if stderr_override is not None:
                stderr = stderr_override
        process = _FakeProcess(
            outcome=self.outcomes[index],
            survives_terminate=self.survives_terminate,
            terminate_raises=self.terminate_raises,
            kill_raises=self.kill_raises,
            stdout=stdout,
            stderr=stderr,
            timeout_partial_stdout=self.timeout_partial_stdout,
            timeout_partial_stderr=self.timeout_partial_stderr,
            timeout_drained_stdout=self.timeout_drained_stdout,
            timeout_drained_stderr=self.timeout_drained_stderr,
        )
        self.processes.append(process)
        return process


def _fake_price_material_repository_facts(plan: AcceptancePlan) -> tuple[str, date, str]:
    """返回 generic runner 测试的严格 material 仓储事实。

    Args:
        plan: 当前 canonical plan。

    Returns:
        与 fake owner stdout 闭合的 fingerprint、报告日与 primary SHA。

    Raises:
        本函数不显式抛出异常。
    """

    return "d" * 64, date(2025, 1, 15), plan.price_material_sha256


def _fake_process_repository_stop_reason(
    plan: AcceptancePlan,
    evidence: ProcessCommandEvidence,
) -> str | None:
    """表示 generic runner 测试的 processed 仓储闭包已通过。

    Args:
        plan: 当前 canonical plan。
        evidence: 已严格解析的 process evidence。

    Returns:
        固定返回 null，表示仓储闭包通过。

    Raises:
        本函数不显式抛出异常。
    """

    del plan, evidence
    return None


def _stub_runner_repository_closure(monkeypatch: pytest.MonkeyPatch) -> None:
    """仅为 generic runner lifecycle 测试注入可复现仓储边界。

    Args:
        monkeypatch: pytest 属性替换器。

    Returns:
        无。

    Raises:
        本函数不显式抛出异常。
    """

    monkeypatch.setattr(
        acceptance_cli_module,
        "_price_material_repository_facts",
        _fake_price_material_repository_facts,
    )
    monkeypatch.setattr(
        acceptance_cli_module,
        "_process_repository_stop_reason",
        _fake_process_repository_stop_reason,
    )


def _v3_passed_record(command_index: int, evidence: CommandEvidence) -> CommandRecord:
    """构造包含一种 strict evidence 的 v3 passed command record。

    Args:
        command_index: phase 内连续序号。
        evidence: 闭集 evidence union 成员。

    Returns:
        时间、流摘要与退出事实闭合的 record。

    Raises:
        ContractError: 注入 evidence 本身非法时抛出。
    """

    started = datetime(2025, 2, 1, 0, command_index, tzinfo=UTC)
    ended = started + timedelta(seconds=1)
    empty_sha = hashlib.sha256(b"").hexdigest()
    return CommandRecord(
        command_index=command_index,
        safe_argv=("<PYTHON>", "-m", "dayu.cli", "download"),
        argv_digest=canonical_json_sha256(["python", "-m", "dayu.cli", "download", str(command_index)]),
        status="passed",
        started_at=started,
        ended_at=ended,
        duration_seconds=1.0,
        exit_code=0,
        stop_reason=None,
        termination_action=None,
        partial_by_timeout=False,
        stdout_sha256=empty_sha,
        stderr_sha256=empty_sha,
        stdout_summary=None,
        stderr_summary=None,
        evidence=evidence,
    )


def _v3_evidence_samples() -> tuple[CommandEvidence, CommandEvidence, CommandEvidence]:
    """构造 v3 当前全部三种 evidence union 样本。

    Args:
        无。

    Returns:
        download、material import 与 process evidence。

    Raises:
        ContractError: 固定样本不再符合当前 contract 时抛出。
    """

    filing_id = "fil_0000320193-24-000123"
    download = DownloadCommandEvidence(
        ticker="AAPL",
        planned_forms=("10K",),
        canonical_forms=("10-K",),
        start=date(2020, 2, 1),
        end=date(2025, 2, 1),
        owner_status="ok",
        summary=AcceptanceDownloadSummary(total=1, downloaded=1, skipped=0, failed=0),
        rows=(
            DownloadEvidenceRow(
                document_id=filing_id,
                accession="0000320193-24-000123",
                canonical_form="10-K",
                filing_date=date(2025, 1, 30),
                section_status="downloaded",
            ),
        ),
    )
    material = MaterialImportCommandEvidence(
        owner_status="ok",
        material_action="create",
        document_id=_PRICE_MATERIAL_DOCUMENT_ID,
        source_fingerprint="d" * 64,
        report_date=date(2025, 1, 15),
        price_json_sha256="a" * 64,
        price_material_sha256="b" * 64,
        repository_primary_sha256="b" * 64,
    )
    process = ProcessCommandEvidence(
        owner_status="ok",
        filing_summary=AcceptanceProcessSummary(total=1, processed=1, skipped=0, failed=0),
        material_summary=AcceptanceProcessSummary(total=1, processed=1, skipped=0, failed=0),
        materials_todo=False,
        rows=(
            ProcessEvidenceRow(document_id=filing_id, source_kind="filing", status="processed"),
            ProcessEvidenceRow(
                document_id=_PRICE_MATERIAL_DOCUMENT_ID,
                source_kind="material",
                status="processed",
            ),
        ),
    )
    return download, material, process


def _slice2_prepare_inputs(tmp_path: Path) -> tuple[PrepareRequest, PrepareServices]:
    """构造隔离、完全离线的 prepare 输入与依赖。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        prepare 请求与可复用 services。

    Raises:
        ContractError: 测试输入不符合固定 contract 时抛出。
        OSError: 隔离文件写入失败时抛出。
    """

    repository_root = tmp_path / "repository"
    run_parent = repository_root / "workspace/acceptance/investment-agent-aapl"
    run_parent.mkdir(parents=True)
    run_root = run_parent / "run-001"
    price_path = tmp_path / "price-snapshot.json"
    shutil.copy2(_FIXTURE_ROOT / "price-snapshot-v1.json", price_path)
    runtime = RuntimeIdentity(
        repository_root=repository_root,
        python_executable=Path(sys.executable).resolve().as_posix(),
        python_version="3.11.15",
        platform="test-platform",
        timezone="UTC",
    )
    environment = MappingEnvironmentPresenceProvider(
        {name: True for name in REQUIRED_ENVIRONMENT_NAMES}
    )
    state = _StaticRepositoryStateProvider(
        RepositoryState(git_sha="a99322c65aa7aedbfb3ab4516cb36d66311e71ba", dirty=False)
    )
    services = PrepareServices(
        runtime=runtime,
        environment=environment,
        repository_state=state,
        clock=_FixedClock(datetime(2025, 2, 1, tzinfo=UTC)),
    )
    request = PrepareRequest(
        ticker="AAPL",
        company="Apple Inc.",
        template="technology",
        as_of=datetime(2025, 2, 1, tzinfo=UTC),
        run_root=run_root,
        price_snapshot=price_path,
        budget=_APPROVED_BUDGET,
        max_wall_seconds=_MAX_WALL_SECONDS,
    )
    return request, services


def _prepare_slice2_run(tmp_path: Path) -> tuple[PreparedAcceptance, PrepareServices]:
    """在隔离仓库根内执行一次完全离线 prepare。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        prepared plan 与可复用 services。

    Raises:
        ContractError: 测试输入不符合固定 contract 时抛出。
        OSError: 隔离文件写入失败时抛出。
    """

    request, services = _slice2_prepare_inputs(tmp_path)
    prepared = prepare_acceptance(request, services)
    return prepared, services
# 以下常量只锁定 Slice 0 fixture 的已接受语义；Slice 1 evaluator 必须解析
# contract fixture 本身，不能把这些测试期望复制成第二套生产枚举。
_EXPECTED_HARD_GATES = (
    "run_summary_passed",
    "audit_complete",
    "dual_model_roles_closed",
    "budget_within_limits",
    "research_artifacts_valid",
    "workbook_progress_valid",
    "monitoring_safe",
    "source_price_closed",
    "acceptance_outputs_sanitized",
    "manual_review_passed",
)
_EXPECTED_DIMENSION_MINIMUMS = {
    "source_traceability": 20,
    "investment_research_completeness": 24,
    "evidence_reasoning_quality": 20,
    # 后两维的 0 是有意表示“不设独立 hard minimum”，而不是待填占位。
    "reproducibility_recovery": 0,
    "run_governance": 0,
}
_EXPECTED_REQUIRED_TOPICS = (
    "thesis",
    "bear_case",
    "valuation",
    "catalyst",
    "risk",
)
_EXPECTED_EVIDENCE_PARTS = (
    "source",
    "type_or_identifier",
    "date",
    "locator",
)
_REPORT_HEADING_BY_TOPIC = {
    "thesis": "## 投资主线（thesis）",
    "bear_case": "## Bear case 与反证",
    "valuation": "## 估值（valuation）",
    "catalyst": "## 催化剂（catalyst）",
    "risk": "## 风险（risk）",
}
_APPROVED_BUDGET = BudgetLimits(
    max_model_requests=20,
    max_total_tokens=200_000,
    max_estimated_cost=Decimal("5.0"),
    budget_currency="CNY",
)
_FIXED_EVALUATED_AT = datetime(2025, 2, 1, 1, 0, tzinfo=UTC)
_MAX_WALL_SECONDS = 3_600
_ACTUAL_WALL_SECONDS = 120.0
_ACCEPTANCE_ARTIFACT_PREFIX = "research/assets/research_templates"


def _materialize_acceptance_artifacts(tmp_path: Path) -> Path:
    """在临时目录物化真实 technology 13 产物。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        ``assets/research_templates`` 产物目录。

    Raises:
        OSError: owner 写入产物失败时抛出。
        ValueError: owner validator 拒绝物化结果时抛出。
    """

    materialize_research_workspace(
        "technology",
        workspace_root=tmp_path,
        ticker="AAPL",
        company="Apple Inc.",
    )
    return tmp_path / "assets" / "research_templates"


def _load_acceptance_inputs(
    tmp_path: Path,
    *,
    acceptance_owned_outputs: tuple[JsonValue, ...] = (),
) -> AcceptanceInputs:
    """构造一个真实 13 产物支持的 happy evaluator 输入。

    Args:
        tmp_path: pytest 隔离目录。
        acceptance_owned_outputs: 仅供 sanitizer 检查的验收自有 JSON。

    Returns:
        完整严格 evaluator 输入。

    Raises:
        OSError: fixture 或临时研究产物读取失败时抛出。
        ContractError: fixture 或产物 contract 非法时抛出。
    """

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    return _load_acceptance_inputs_from_artifacts(
        artifact_root,
        acceptance_owned_outputs=acceptance_owned_outputs,
    )


def _load_acceptance_inputs_from_artifacts(
    artifact_root: Path,
    *,
    acceptance_owned_outputs: tuple[JsonValue, ...] = (),
    expected_artifact_sha256: tuple[tuple[str, str], ...] = (),
) -> AcceptanceInputs:
    """从一个已物化产物目录加载 evaluator 输入。

    Args:
        artifact_root: 精确研究产物目录。
        acceptance_owned_outputs: 仅供 sanitizer 检查的验收自有 JSON。
        expected_artifact_sha256: 可选的 artifact 绑定摘要。

    Returns:
        完整严格 evaluator 输入。

    Raises:
        OSError: fixture 或产物读取失败时抛出。
        ContractError: fixture 或产物 contract 非法时抛出。
    """

    return load_fixture_inputs(
        FixtureInputRequest(
            fixture_root=_FIXTURE_ROOT,
            artifact_root=artifact_root,
            approved_budget=_APPROVED_BUDGET,
            max_wall_seconds=_MAX_WALL_SECONDS,
            actual_wall_seconds=_ACTUAL_WALL_SECONDS,
            acceptance_owned_outputs=acceptance_owned_outputs,
            expected_artifact_sha256=expected_artifact_sha256,
        )
    )


def _finding_codes(inputs: AcceptanceInputs) -> set[str]:
    """执行固定时钟 evaluator 并返回 finding code 集合。

    Args:
        inputs: 严格 evaluator 输入。

    Returns:
        finding code 集合。

    Raises:
        ContractError: evaluator receipt 生成失败时抛出。
    """

    return {item.code for item in evaluate_acceptance(inputs, evaluated_at=_FIXED_EVALUATED_AT).findings}


def _drop_markdown_section(report: str, heading: str) -> str:
    """从测试报告删除一个二级 Markdown 章节。

    Args:
        report: 原报告文本。
        heading: 不含 ``##`` 的精确标题。

    Returns:
        删除目标章节后的文本。

    Raises:
        AssertionError: 目标章节不存在时抛出。
    """

    marker = f"## {heading}"
    before, separator, after = report.partition(marker)
    assert separator
    _section, next_separator, remainder = after.partition("\n## ")
    return before + (f"\n## {remainder}" if next_separator else "")


def _load_json_fixture(name: str) -> dict[str, JsonValue]:
    """读取一个固定 JSON fixture。

    Args:
        name: fixture 文件名。

    Returns:
        JSON 顶层对象。

    Raises:
        OSError: 文件读取失败时抛出。
        json.JSONDecodeError: fixture 不是合法 JSON 时抛出。
        AssertionError: JSON 顶层不是对象时抛出。
    """
    payload: JsonValue = json.loads((_FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{name} 顶层必须是对象"
    return payload


def _require_mapping(value: JsonValue, *, label: str) -> dict[str, JsonValue]:
    """把已解析 JSON 值收窄为对象。

    Args:
        value: 待收窄的 JSON 值。
        label: 断言失败时使用的字段标签。

    Returns:
        已验证的 JSON 对象。

    Raises:
        AssertionError: 值不是对象时抛出。
    """
    assert isinstance(value, dict), f"{label} 必须是对象"
    return value


def _require_list(value: JsonValue, *, label: str) -> list[JsonValue]:
    """把已解析 JSON 值收窄为数组。

    Args:
        value: 待收窄的 JSON 值。
        label: 断言失败时使用的字段标签。

    Returns:
        已验证的 JSON 数组。

    Raises:
        AssertionError: 值不是数组时抛出。
    """
    assert isinstance(value, list), f"{label} 必须是数组"
    return value


def _canonical_json_bytes(payload: dict[str, JsonValue]) -> bytes:
    """按验收 contract 的固定规则生成 canonical JSON 字节。

    Args:
        payload: 待序列化的 JSON 对象。

    Returns:
        UTF-8 编码、键排序且无多余空白的 JSON 字节。

    Raises:
        ValueError: 载荷包含 NaN 或其它非标准浮点数时抛出。
        TypeError: 载荷包含不可序列化值时抛出。
    """
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    """计算字节载荷的 SHA-256。

    Args:
        payload: 待计算的字节载荷。

    Returns:
        小写十六进制 SHA-256。

    Raises:
        本函数不显式抛出异常。
    """
    return hashlib.sha256(payload).hexdigest()


def _chapter_passed(result: ChapterResult | None) -> bool:
    """判断生产运行摘要测试中的章节是否通过门禁。

    Args:
        result: 可选章节结果。

    Returns:
        章节存在、状态通过且审计通过时返回 ``True``。

    Raises:
        本函数不显式抛出异常。
    """
    return bool(result is not None and result.status == "passed" and result.audit_passed)


@pytest.mark.unit
def test_fixture_files_have_strict_shapes_and_stable_canonical_serialization() -> None:
    """验证全部固定语料的字段闭包与 canonical 指纹稳定。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一 fixture 漂移、增删字段或失去 canonical 稳定性时抛出。
        OSError: fixture 无法读取时抛出。
        json.JSONDecodeError: fixture 不是合法 JSON 时抛出。
    """
    assert {path.name for path in _FIXTURE_ROOT.iterdir()} == {
        *_JSON_FIXTURE_SHA256,
        "report-v1.md",
    }
    for name, expected_sha256 in _JSON_FIXTURE_SHA256.items():
        payload = _load_json_fixture(name)
        canonical = _canonical_json_bytes(payload)
        assert _sha256_bytes(canonical) == expected_sha256
        reparsed: JsonValue = json.loads(canonical)
        assert isinstance(reparsed, dict)
        assert _canonical_json_bytes(reparsed) == canonical
    assert _sha256_bytes((_FIXTURE_ROOT / "report-v1.md").read_bytes()) == _REPORT_SHA256

    contract = _load_json_fixture("contract-v1.json")
    assert set(contract) == {
        "schema_version",
        "contract_type",
        "fixture_id",
        "target",
        "fixture_policy",
        "model_roles",
        "report_contract",
        "score_contract",
        "hard_gates",
        "required_research_artifacts",
    }
    assert set(_require_mapping(contract["target"], label="contract.target")) == {
        "ticker",
        "company",
        "research_template",
    }
    assert set(_require_mapping(contract["fixture_policy"], label="contract.fixture_policy")) == {
        "deterministic",
        "external_calls_allowed",
        "live_freshness_claimed",
    }
    assert set(_require_mapping(contract["model_roles"], label="contract.model_roles")) == {
        "primary",
        "audit",
    }
    report_contract = _require_mapping(contract["report_contract"], label="contract.report_contract")
    assert set(report_contract) == {
        "required_topics",
        "required_evidence_parts",
        "valuation_reference_price",
    }
    score_contract = _require_mapping(contract["score_contract"], label="contract.score_contract")
    assert set(score_contract) == {"total_points", "minimum_total_score", "dimension_minimums"}
    assert (
        _require_mapping(
            score_contract["dimension_minimums"],
            label="contract.score_contract.dimension_minimums",
        )
        == _EXPECTED_DIMENSION_MINIMUMS
    )
    hard_gates = _require_list(contract["hard_gates"], label="contract.hard_gates")
    assert hard_gates == list(_EXPECTED_HARD_GATES)
    assert len(hard_gates) == len(set(hard_gates)) == len(_EXPECTED_HARD_GATES)
    assert _require_list(
        report_contract["required_topics"],
        label="contract.report_contract.required_topics",
    ) == list(_EXPECTED_REQUIRED_TOPICS)
    assert _require_list(
        report_contract["required_evidence_parts"],
        label="contract.report_contract.required_evidence_parts",
    ) == list(_EXPECTED_EVIDENCE_PARTS)
    assert (
        _require_list(
            contract["required_research_artifacts"],
            label="contract.required_research_artifacts",
        )
        == _RESEARCH_ARTIFACT_NAMES
    )

    price = _load_json_fixture("price-snapshot-v1.json")
    assert set(price) == {"price", "currency", "market_date", "source_url", "captured_at", "max_age_days"}

    inventory = _load_json_fixture("source-inventory-v1.json")
    assert set(inventory) == {
        "schema_version",
        "inventory_type",
        "fixture_id",
        "ticker",
        "company",
        "as_of",
        "live_freshness_claimed",
        "source_windows",
        "latest_discovery",
        "documents",
    }
    source_windows = _require_list(inventory["source_windows"], label="inventory.source_windows")
    assert len(source_windows) == 3
    for index, window_value in enumerate(source_windows):
        window = _require_mapping(window_value, label=f"inventory.source_windows[{index}]")
        assert set(window) == {"forms", "start_date", "end_date"}
    documents = _require_list(inventory["documents"], label="inventory.documents")
    assert len(documents) == 4
    for index, document_value in enumerate(documents):
        document = _require_mapping(document_value, label=f"inventory.documents[{index}]")
        assert set(document) == _DOCUMENT_KEYS
        assert document["ingest_complete"] is True
        assert isinstance(document["primary_file_sha256"], str)
        assert len(document["primary_file_sha256"]) == 64
        processed = _require_mapping(document["processed"], label=f"inventory.documents[{index}].processed")
        assert set(processed) == _PROCESSED_KEYS
        assert processed["exists"] is True
        assert processed["reprocess_required"] is False
        assert isinstance(processed["source_fingerprint"], str)
        assert len(processed["source_fingerprint"]) == 64
        assert document["processed_state_fingerprint"] == _sha256_bytes(_canonical_json_bytes(processed))

    quality_review = _load_json_fixture("quality-review-v1.json")
    assert set(quality_review) == {
        "schema_version",
        "review_type",
        "fixture_id",
        "reviewer_role",
        "reviewer_id_label",
        "status",
        "dimensions",
        "total_score",
        "finding_counts",
        "findings",
        "completed_at",
    }
    dimensions = _require_mapping(quality_review["dimensions"], label="quality_review.dimensions")
    assert set(dimensions) == {
        "source_traceability",
        "investment_research_completeness",
        "evidence_reasoning_quality",
        "reproducibility_recovery",
        "run_governance",
    }
    for dimension_name, dimension_value in dimensions.items():
        dimension = _require_mapping(dimension_value, label=f"quality_review.dimensions.{dimension_name}")
        assert set(dimension) == {"score", "max_score", "items"}
        items = _require_list(dimension["items"], label=f"quality_review.dimensions.{dimension_name}.items")
        assert items
        for item_index, item_value in enumerate(items):
            item = _require_mapping(
                item_value,
                label=f"quality_review.dimensions.{dimension_name}.items[{item_index}]",
            )
            assert set(item) == {"item_id", "score", "max_score", "evidence_paths", "notes"}
            assert _require_list(item["evidence_paths"], label=f"{dimension_name}.evidence_paths")
            assert isinstance(item["notes"], str) and item["notes"]

    manifest = _load_json_fixture("write-manifest-v1.json")
    assert set(manifest) == {"version", "signature", "config", "chapter_results", "company_facets"}
    config = _require_mapping(manifest["config"], label="manifest.config")
    assert set(config) == {
        "ticker",
        "company",
        "template_path",
        "output_dir",
        "write_max_retries",
        "web_provider",
        "resume",
        "write_model_override_name",
        "audit_model_override_name",
        "write_fallback_model_name",
        "audit_fallback_model_name",
        "scene_models",
        "scene_fallback_models",
        "chapter_filter",
        "fast",
        "force",
        "infer",
        "research_template_requested_name",
        "research_template_resolved_name",
        "research_template_selection_mode",
        "write_max_model_requests",
        "write_max_total_tokens",
        "write_max_estimated_cost",
        "write_budget_currency",
    }
    chapter_results = _require_mapping(manifest["chapter_results"], label="manifest.chapter_results")
    assert len(chapter_results) == 5
    for chapter_title, chapter_value in chapter_results.items():
        chapter = _require_mapping(chapter_value, label=f"manifest.chapter_results.{chapter_title}")
        assert set(chapter) == {
            "index",
            "title",
            "status",
            "content",
            "audit_passed",
            "retry_count",
            "failure_reason",
            "evidence_items",
            "process_state",
        }
        process_state = _require_mapping(chapter["process_state"], label=f"{chapter_title}.process_state")
        assert set(process_state) == {
            "final_stage",
            "audit_history",
            "confirm_history",
            "anchor_rewrite_history",
        }

    run_summary = _load_json_fixture("run-summary-v1.json")
    assert set(run_summary) == {
        "schema_version",
        "completed_at",
        "ticker",
        "output_file",
        "gate_status",
        "publication_status",
        "model_roles",
        "model_usage",
        "model_routing",
        "budget",
        "chapter_count",
        "failed_count",
        "failed_chapters",
        "audit",
        "chapters",
    }
    assert set(_require_mapping(run_summary["model_roles"], label="run_summary.model_roles")) == {
        "primary",
        "audit",
    }
    assert "usage_status" in _require_mapping(run_summary["model_usage"], label="run_summary.model_usage")
    assert set(_require_mapping(run_summary["model_routing"], label="run_summary.model_routing")) == {
        "fallback_switch_count",
        "fallback_call_completed_count",
        "fallback_call_error_count",
        "routes",
    }
    assert set(_require_mapping(run_summary["budget"], label="run_summary.budget")) == {
        "enabled",
        "status",
        "enforcement",
        "limits",
        "usage",
        "active_reservation_count",
        "projection",
        "block",
    }
    assert set(_require_mapping(run_summary["audit"], label="run_summary.audit")) == {
        "required",
        "passed_count",
        "failed_count",
        "skipped_count",
        "gate_blocked_count",
        "first_pass_count",
        "repaired_pass_count",
        "total_retries",
        "audit_attempt_count",
        "confirmation_check_count",
        "anchor_rewrite_count",
    }


@pytest.mark.unit
def test_fixture_contract_is_aapl_technology_85_point_pass_with_closed_sources() -> None:
    """验证固定语料覆盖五类研究内容、四段引用和精确估值价格闭环。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: contract、评分、报告或来源闭环不一致时抛出。
        OSError: fixture 无法读取时抛出。
        json.JSONDecodeError: fixture 不是合法 JSON 时抛出。
    """
    contract = _load_json_fixture("contract-v1.json")
    target = _require_mapping(contract["target"], label="contract.target")
    policy = _require_mapping(contract["fixture_policy"], label="contract.fixture_policy")
    score_contract = _require_mapping(contract["score_contract"], label="contract.score_contract")
    assert target == {"ticker": "AAPL", "company": "Apple Inc.", "research_template": "technology"}
    assert policy == {
        "deterministic": True,
        "external_calls_allowed": False,
        "live_freshness_claimed": False,
    }
    assert score_contract["total_points"] == 100
    assert score_contract["minimum_total_score"] == 85
    dimension_minimums = _require_mapping(
        score_contract["dimension_minimums"],
        label="contract.score_contract.dimension_minimums",
    )
    assert dimension_minimums == _EXPECTED_DIMENSION_MINIMUMS

    quality_review = _load_json_fixture("quality-review-v1.json")
    dimensions = _require_mapping(quality_review["dimensions"], label="quality_review.dimensions")
    assert set(dimensions) == set(dimension_minimums)
    dimension_score_total = 0
    dimension_max_total = 0
    for dimension_name, dimension_value in dimensions.items():
        dimension = _require_mapping(dimension_value, label=f"quality_review.dimensions.{dimension_name}")
        dimension_score = dimension["score"]
        dimension_max_score = dimension["max_score"]
        dimension_minimum = dimension_minimums[dimension_name]
        assert isinstance(dimension_score, int) and not isinstance(dimension_score, bool)
        assert isinstance(dimension_max_score, int) and not isinstance(dimension_max_score, bool)
        assert isinstance(dimension_minimum, int) and not isinstance(dimension_minimum, bool)
        assert dimension_score >= dimension_minimum
        items = _require_list(dimension["items"], label=f"quality_review.dimensions.{dimension_name}.items")
        item_score_total = 0
        item_max_total = 0
        for item_index, item_value in enumerate(items):
            item = _require_mapping(
                item_value,
                label=f"quality_review.dimensions.{dimension_name}.items[{item_index}]",
            )
            item_score = item["score"]
            item_max_score = item["max_score"]
            assert isinstance(item_score, int) and not isinstance(item_score, bool)
            assert isinstance(item_max_score, int) and not isinstance(item_max_score, bool)
            item_score_total += item_score
            item_max_total += item_max_score
        assert item_score_total == dimension_score
        assert item_max_total == dimension_max_score
        dimension_score_total += dimension_score
        dimension_max_total += dimension_max_score
    assert dimension_score_total == quality_review["total_score"] == 85
    assert dimension_max_total == score_contract["total_points"] == 100
    assert quality_review["status"] == "PASS"
    finding_counts = _require_mapping(quality_review["finding_counts"], label="quality_review.finding_counts")
    assert finding_counts["high"] == finding_counts["medium"] == 0

    price = _load_json_fixture("price-snapshot-v1.json")
    report_contract = _require_mapping(contract["report_contract"], label="contract.report_contract")
    required_topics = _require_list(
        report_contract["required_topics"],
        label="contract.report_contract.required_topics",
    )
    required_evidence_parts = _require_list(
        report_contract["required_evidence_parts"],
        label="contract.report_contract.required_evidence_parts",
    )
    assert required_topics == list(_EXPECTED_REQUIRED_TOPICS)
    assert required_evidence_parts == list(_EXPECTED_EVIDENCE_PARTS)
    reference_price = _require_mapping(
        report_contract["valuation_reference_price"],
        label="contract.report_contract.valuation_reference_price",
    )
    assert {key: price[key] for key in ("price", "currency", "market_date")} == {
        key: reference_price[key] for key in ("price", "currency", "market_date")
    }

    report = (_FIXTURE_ROOT / "report-v1.md").read_text(encoding="utf-8")
    assert set(_REPORT_HEADING_BY_TOPIC) == set(required_topics)
    for topic_value in required_topics:
        assert isinstance(topic_value, str)
        assert _REPORT_HEADING_BY_TOPIC[topic_value] in report
    expected_reference_record = (
        'valuation_reference_price: {"price":"236.85","currency":"USD",'
        '"market_date":"2025-01-15",'
        '"material_document_id":"material-aapl-price-snapshot-2025-01-15"}'
    )
    assert report.count("valuation_reference_price:") == 1
    assert expected_reference_record in report
    assert "不声明实时性" in report

    report_body, source_list = report.split("## 来源清单", maxsplit=1)
    body_citations = [line for line in report_body.splitlines() if line.startswith("- ")]
    source_entries = [line for line in source_list.splitlines() if line.startswith("- ")]
    assert body_citations and source_entries
    citations = body_citations + source_entries
    assert all(len(line.removeprefix("- ").split(" | ")) == len(required_evidence_parts) for line in citations)
    evidence_document_ids = {line.removeprefix("- ").split(" | ", maxsplit=1)[0] for line in body_citations}
    source_list_document_ids = {line.removeprefix("- ").split(" | ", maxsplit=1)[0] for line in source_entries}
    inventory = _load_json_fixture("source-inventory-v1.json")
    inventory_documents = _require_list(inventory["documents"], label="inventory.documents")
    inventory_by_document_id: dict[str, dict[str, JsonValue]] = {}
    for document_value in inventory_documents:
        document = _require_mapping(document_value, label="inventory.document")
        document_id = document["document_id"]
        assert isinstance(document_id, str) and document_id
        inventory_by_document_id[document_id] = document
    inventory_document_ids = set(inventory_by_document_id)
    assert inventory["live_freshness_claimed"] is False
    assert evidence_document_ids <= source_list_document_ids == inventory_document_ids

    as_of_value = inventory["as_of"]
    assert isinstance(as_of_value, str)
    as_of_date = datetime.fromisoformat(as_of_value.replace("Z", "+00:00")).date()
    for citation in citations:
        document_id, type_or_identifier, citation_date_text, _locator = citation.removeprefix("- ").split(" | ")
        assert date.fromisoformat(citation_date_text) <= as_of_date
        document = inventory_by_document_id[document_id]
        if document["source_kind"] == "filing":
            form = document["form"]
            accession = document["accession"]
            assert isinstance(form, str) and form
            assert isinstance(accession, str) and accession
            assert type_or_identifier == f"{form} / {accession}"

    latest_discovery = _require_mapping(inventory["latest_discovery"], label="inventory.latest_discovery")
    for form, latest_accession in latest_discovery.items():
        matching_filings = [
            document
            for document in inventory_by_document_id.values()
            if document["source_kind"] == "filing" and document["form"] == form
        ]
        assert len(matching_filings) == 1
        assert matching_filings[0]["accession"] == latest_accession


@pytest.mark.unit
def test_write_manifest_fixture_is_accepted_by_current_production_owner() -> None:
    """验证固定 write manifest 可由现有生产模型无兼容分支地恢复。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 恢复后的 AAPL/technology/双模型契约不闭合时抛出。
        OSError: fixture 无法读取时抛出。
        json.JSONDecodeError: fixture 不是合法 JSON 时抛出。
        KeyError: manifest 缺少生产 owner 必填字段时抛出。
        TypeError: manifest 字段类型不符合生产 owner 契约时抛出。
    """
    raw_manifest = json.loads((_FIXTURE_ROOT / "write-manifest-v1.json").read_text(encoding="utf-8"))
    manifest = RunManifest.from_dict(raw_manifest)

    assert manifest.version == "write_manifest_v1"
    assert manifest.config.ticker == "AAPL"
    assert manifest.config.research_template_requested_name == "technology"
    assert manifest.config.research_template_resolved_name == "technology"
    assert manifest.config.research_template_selection_mode == "named"
    assert manifest.config.scene_models["write"].name == "deepseek-v4-pro"
    assert manifest.config.scene_models["audit"].name == "mimo-v2.5-pro-thinking"
    assert len(manifest.chapter_results) == 5
    assert all(chapter.status == "passed" and chapter.audit_passed for chapter in manifest.chapter_results.values())


@pytest.mark.unit
def test_technology_workbook_owner_has_ten_categories_and_37_items() -> None:
    """直接刻画 production owner 生成的 technology 工作簿规模。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: technology 工作簿不再是 10 类、37 项时抛出。
        FileNotFoundError: packaged technology 模板不存在时抛出。
        OSError: packaged technology 模板读取失败时抛出。
        ValueError: packaged technology 模板没有可执行章节时抛出。
    """
    workbook = build_research_workbook_payload("technology", ticker="AAPL", company="Apple Inc.")
    summary_value = workbook["summary"]
    assert isinstance(summary_value, dict)
    category_counts = summary_value["category_counts"]
    assert isinstance(category_counts, dict)

    assert set(category_counts) == _WORKBOOK_CATEGORIES
    assert len(category_counts) == 10
    assert sum(int(count) for count in category_counts.values()) == 37
    assert summary_value["item_count"] == 37
    assert summary_value["open_item_count"] == 37


@pytest.mark.unit
def test_materialization_owner_protects_exactly_thirteen_artifacts(tmp_path: Path) -> None:
    """直接刻画 production materializer 的 13 产物回滚边界。

    Args:
        tmp_path: pytest 提供的隔离临时目录。

    Returns:
        无。

    Raises:
        AssertionError: owner 的受保护路径数量、顺序或名称漂移时抛出。
    """
    artifact_paths = _materialization_artifact_paths(tmp_path, "technology")

    assert len(artifact_paths) == len(set(artifact_paths)) == 13
    assert [path.name for path in artifact_paths] == _RESEARCH_ARTIFACT_NAMES
    assert all(path.parent == (tmp_path / "assets" / "research_templates").resolve() for path in artifact_paths)


@pytest.mark.unit
def test_monitoring_owner_forces_dry_run_and_disables_automation(tmp_path: Path) -> None:
    """直接刻画 monitoring owner 的 dry-run 与禁止自动执行安全边界。

    Args:
        tmp_path: pytest 提供的隔离临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 生成器或 validator 不再强制安全开关时抛出。
        OSError: 本地物化产物无法读写时抛出。
        ValueError: 本地 bundle 或 monitoring plan 不健康时抛出。
    """
    materialized = materialize_research_template_bundle(
        "technology",
        workspace_root=tmp_path,
        ticker="AAPL",
        company="Apple Inc.",
    )
    plan = build_monitoring_execution_plan(Path(str(materialized["bundle_file"])))

    assert plan["execution_mode"] == "dry_run"
    assert plan["automated_execution_allowed"] is False
    valid_result = validate_monitoring_execution_plan(plan)
    assert valid_result["ok"] is True
    assert valid_result["errors"] == []

    unsafe_automation = dict(plan)
    unsafe_automation["automated_execution_allowed"] = True
    unsafe_automation_result = validate_monitoring_execution_plan(unsafe_automation)
    assert unsafe_automation_result["ok"] is False
    unsafe_automation_errors = unsafe_automation_result["errors"]
    assert isinstance(unsafe_automation_errors, list)
    assert "automated_execution_allowed must be false" in unsafe_automation_errors
    unsafe_mode = dict(plan)
    unsafe_mode["execution_mode"] = "live"
    unsafe_mode_result = validate_monitoring_execution_plan(unsafe_mode)
    assert unsafe_mode_result["ok"] is False
    unsafe_mode_errors = unsafe_mode_result["errors"]
    assert isinstance(unsafe_mode_errors, list)
    assert "execution_mode must be dry_run" in unsafe_mode_errors


@pytest.mark.unit
def test_run_summary_v3_owner_includes_budget_usage_and_audit() -> None:
    """直接刻画 production run summary v3 的预算、usage 与审计字段。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: v3 owner 不再保留预算、usage 或审计 receipt 时抛出。
        ValueError: 固定完成时间不带时区时抛出。
    """
    config = WriteRunConfig(
        ticker="AAPL",
        company="Apple Inc.",
        template_path="dayu/assets/定性分析模板.md",
        output_dir="write",
        write_max_retries=2,
        web_provider="auto",
        resume=False,
        scene_models={
            "write": SceneModelConfig(name="deepseek-v4-pro", temperature=1.0),
            "audit": SceneModelConfig(name="mimo-v2.5-pro-thinking", temperature=0.2),
        },
    )
    model_usage = {
        "usage_status": "complete",
        "scene_call_count": 2,
        "total_tokens": 120,
    }
    budget = {
        "enabled": True,
        "status": "within_budget",
        "block": None,
    }
    summary = ExecutionSummaryBuilder(write_config=config).build_summary(
        {
            "投资主线": ChapterResult(
                index=1,
                title="投资主线",
                status="passed",
                content="fixture",
                audit_passed=True,
                process_state={"audit_history": [{"phase": "initial"}], "final_stage": "complete"},
            )
        },
        output_file=Path("write/AAPL_qual_report.md"),
        success_predicate=_chapter_passed,
        model_usage=model_usage,
        budget=budget,
        completed_at=datetime(2025, 1, 16, tzinfo=UTC),
    )

    assert summary["schema_version"] == "write_run_summary_v3"
    assert summary["gate_status"] == "passed"
    assert summary["publication_status"] == "published"
    assert summary["model_usage"] == model_usage
    assert summary["budget"] == budget
    audit = summary["audit"]
    assert isinstance(audit, dict)
    assert audit["required"] is True
    assert audit["passed_count"] == 1
    assert audit["failed_count"] == 0
    assert audit["skipped_count"] == 0

    fixture_summary = _load_json_fixture("run-summary-v1.json")
    assert set(summary) == set(fixture_summary)
    fixture_audit = _require_mapping(fixture_summary["audit"], label="fixture_summary.audit")
    assert set(audit) == set(fixture_audit)

    owner_chapters = summary["chapters"]
    assert isinstance(owner_chapters, list) and owner_chapters
    owner_first_chapter = owner_chapters[0]
    assert isinstance(owner_first_chapter, dict)
    fixture_chapters = _require_list(fixture_summary["chapters"], label="fixture_summary.chapters")
    fixture_first_chapter = _require_mapping(fixture_chapters[0], label="fixture_summary.chapters[0]")
    assert set(owner_first_chapter) == set(fixture_first_chapter)

    owner_routing = summary["model_routing"]
    assert isinstance(owner_routing, dict)
    fixture_routing = _require_mapping(fixture_summary["model_routing"], label="fixture_summary.model_routing")
    assert set(owner_routing) == set(fixture_routing)

    owner_roles = summary["model_roles"]
    assert isinstance(owner_roles, dict)
    fixture_roles = _require_mapping(fixture_summary["model_roles"], label="fixture_summary.model_roles")
    assert set(owner_roles) == set(fixture_roles)
    for role_name in ("primary", "audit"):
        owner_role = owner_roles[role_name]
        assert isinstance(owner_role, dict)
        fixture_role = _require_mapping(fixture_roles[role_name], label=f"fixture_summary.model_roles.{role_name}")
        assert set(owner_role) == set(fixture_role)
        owner_scenes = owner_role["scenes"]
        fixture_scenes = _require_list(fixture_role["scenes"], label=f"fixture_summary.{role_name}.scenes")
        assert isinstance(owner_scenes, list) and owner_scenes
        assert fixture_scenes
        assert isinstance(owner_scenes[0], dict)
        assert set(owner_scenes[0]) == set(
            _require_mapping(fixture_scenes[0], label=f"fixture_summary.{role_name}.scenes[0]")
        )


@pytest.mark.unit
def test_slice1_evaluator_happy_fixture_passes_and_receipt_is_byte_stable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 happy fixture 精确 PASS、85 分且固定时钟 receipt 字节稳定。

    Args:
        tmp_path: pytest 隔离目录。
        capsys: pytest 标准输出捕获器。

    Returns:
        无。

    Raises:
        AssertionError: verdict、分数、门禁、序列化或 stdout 行为漂移时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)

    first = evaluate_acceptance(inputs, evaluated_at=_FIXED_EVALUATED_AT)
    second = evaluate_acceptance(inputs, evaluated_at=_FIXED_EVALUATED_AT)

    assert first.verdict == "PASS"
    assert first.total_score == 85
    assert first.findings == ()
    assert len(first.artifacts) == 13
    assert all(status == "passed" for _gate, status in first.hard_gates)
    assert first.canonical_bytes() == second.canonical_bytes()
    parsed_receipt = parse_acceptance_receipt(parse_json_bytes(first.canonical_bytes(), label="acceptance receipt"))
    assert parsed_receipt.verdict == "PASS"
    assert parsed_receipt.total_score == 85
    assert len(parsed_receipt.artifacts) == 13
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.unit
def test_slice1_strict_schemas_reject_unknown_nan_bool_and_round_trip_plan_phase(
    tmp_path: Path,
) -> None:
    """验证 plan/phase/contract/receipt 严格 schema 与 JSON 数值规则。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 未知字段、NaN 或 bool-as-int 被接受时抛出。
    """

    contract_payload = _load_json_fixture("contract-v1.json")
    contract_with_unknown = dict(contract_payload)
    contract_with_unknown["unexpected"] = True
    with pytest.raises(ContractError, match="unknown"):
        parse_acceptance_contract(contract_with_unknown)
    contract_missing_required = dict(contract_payload)
    contract_missing_required.pop("model_roles")
    with pytest.raises(
        ContractError,
        match=r"contract schema 不闭合: missing=\['model_roles'\], unknown=\[\]",
    ):
        parse_acceptance_contract(contract_missing_required)

    contract_with_bool = json.loads((_FIXTURE_ROOT / "contract-v1.json").read_text(encoding="utf-8"))
    contract_with_bool["score_contract"]["total_points"] = True
    with pytest.raises(ContractError, match="bool"):
        parse_acceptance_contract(contract_with_bool)
    with pytest.raises(ContractError, match="NaN"):
        parse_json_bytes(b'{"value":NaN}', label="nan fixture")

    package_inputs = build_package_input_fingerprints()
    plan = _slice2_v2_plan(tmp_path, package_inputs)
    assert parse_acceptance_plan(plan.to_json()) == plan
    plan_unknown = dict(plan.to_json())
    plan_unknown["unexpected"] = "rejected"
    with pytest.raises(ContractError, match="unknown"):
        parse_acceptance_plan(plan_unknown)

    phase = PhaseReceipt(
        plan_fingerprint=plan.fingerprint,
        phase_name="prepare",
        status="passed",
        started_at=datetime(2025, 2, 1, tzinfo=UTC),
        ended_at=datetime(2025, 2, 1, 0, 1, tzinfo=UTC),
        duration_seconds=60.0,
        remaining_wall_seconds=3_540.0,
        command_records=(),
    )
    assert parse_phase_receipt(phase.to_json()) == phase
    phase_unknown = dict(phase.to_json())
    phase_unknown["unexpected"] = 1
    with pytest.raises(ContractError, match="unknown"):
        parse_phase_receipt(phase_unknown)

    result = evaluate_acceptance(_load_acceptance_inputs(tmp_path), evaluated_at=_FIXED_EVALUATED_AT)
    receipt_unknown = dict(result.to_json())
    receipt_unknown["unexpected"] = 1
    with pytest.raises(ContractError, match="unknown"):
        parse_acceptance_receipt(receipt_unknown)


@pytest.mark.unit
def test_slice2_phase_receipt_v3_round_trips_all_evidence_and_rejects_old_versions() -> None:
    """验证 v3 三种 evidence union 均 strict round-trip，v1/v2 无兼容读取。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: evidence 丢失或旧 schema 被接受时抛出。
    """

    evidences = _v3_evidence_samples()
    cases = (
        ("download", tuple(_v3_passed_record(index, evidences[0]) for index in range(3))),
        ("price-snapshot-import", (_v3_passed_record(0, evidences[1]),)),
        ("process", (_v3_passed_record(0, evidences[2]),)),
    )
    for phase_name, records in cases:
        receipt = PhaseReceipt(
            plan_fingerprint="a" * 64,
            phase_name=phase_name,
            status="passed",
            started_at=records[0].started_at,
            ended_at=records[-1].ended_at,
            duration_seconds=(records[-1].ended_at - records[0].started_at).total_seconds(),
            remaining_wall_seconds=3_500.0,
            command_records=records,
        )
        assert parse_phase_receipt(receipt.to_json()) == receipt

    payload = PhaseReceipt(
        plan_fingerprint="a" * 64,
        phase_name="process",
        status="passed",
        started_at=cases[2][1][0].started_at,
        ended_at=cases[2][1][0].ended_at,
        duration_seconds=1.0,
        remaining_wall_seconds=3_500.0,
        command_records=cases[2][1],
    ).to_json()
    for old_version in (1, 2):
        legacy = dict(payload)
        legacy["schema_version"] = old_version
        with pytest.raises(ContractError, match="schema_version"):
            parse_phase_receipt(legacy)


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["missing", "unknown", "type", "discriminator"])
def test_slice2_phase_receipt_v3_evidence_schema_fails_closed(mutation: str) -> None:
    """验证 v3 discriminated evidence 拒绝 missing/unknown/type/discriminator 变异。

    Args:
        mutation: 当前 schema 变异类型。

    Returns:
        无。

    Raises:
        AssertionError: 变异 evidence 被接受时抛出。
    """

    process = _v3_evidence_samples()[2]
    record = _v3_passed_record(0, process)
    receipt = PhaseReceipt(
        plan_fingerprint="a" * 64,
        phase_name="process",
        status="passed",
        started_at=record.started_at,
        ended_at=record.ended_at,
        duration_seconds=1.0,
        remaining_wall_seconds=3_500.0,
        command_records=(record,),
    )
    payload = receipt.to_json()
    records = payload["command_records"]
    assert isinstance(records, list)
    first = records[0]
    assert isinstance(first, dict)
    evidence = first["evidence"]
    assert isinstance(evidence, dict)
    if mutation == "missing":
        evidence.pop("owner_status")
    elif mutation == "unknown":
        evidence["unknown"] = True
    elif mutation == "type":
        evidence["materials_todo"] = 1
    else:
        evidence["evidence_type"] = "future_evidence"
    with pytest.raises(ContractError):
        parse_phase_receipt(payload)


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["missing", "renamed"])
def test_slice1_required_research_artifact_set_is_fixed_before_semantic_lookup(
    tmp_path: Path,
    mutation: str,
) -> None:
    """验证 contract 与 inspection 在语义下标前拒绝非固定 13 文件集合。

    Args:
        tmp_path: pytest 隔离目录。
        mutation: 删除或重命名一个语义 artifact 的变异类型。

    Returns:
        无。

    Raises:
        AssertionError: 非固定集合未以 ContractError fail closed 时抛出。
    """

    contract_payload = _load_json_fixture("contract-v1.json")
    artifact_values = _require_list(
        contract_payload["required_research_artifacts"],
        label="contract.required_research_artifacts",
    )
    mutated_values: list[JsonValue] = list(artifact_values)
    if mutation == "missing":
        mutated_values.remove("technology.monitoring-plan.json")
    else:
        index = mutated_values.index("technology.monitoring-plan.json")
        mutated_values[index] = "technology.monitoring-plan-renamed.json"
    contract_payload["required_research_artifacts"] = mutated_values
    expected_message = "必须精确等于固定 AAPL/technology 13 文件集合"
    with pytest.raises(ContractError, match=expected_message):
        parse_acceptance_contract(contract_payload)

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    mutated_names = tuple(value for value in mutated_values if isinstance(value, str))
    with pytest.raises(ContractError, match=expected_message):
        inspect_research_artifacts(
            artifact_root,
            required_artifacts=mutated_names,
        )


@pytest.mark.unit
def test_slice1_manual_review_skeleton_and_partial_are_pending_but_low_complete_review_fails(
    tmp_path: Path,
) -> None:
    """验证人工 rubric 骨架、部分填写与完整低分的严格三态。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: pending/FAIL 状态聚合错误时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    skeleton_dimensions = tuple(
        replace(
            dimension,
            score=None,
            items=tuple(replace(item, score=None, evidence_paths=(), notes=None) for item in dimension.items),
        )
        for dimension in inputs.quality_review.dimensions
    )
    skeleton = replace(
        inputs.quality_review,
        reviewer_role=None,
        reviewer_id_label=None,
        status="PENDING_MANUAL_REVIEW",
        dimensions=skeleton_dimensions,
        total_score=None,
        completed_at=None,
    )
    skeleton_result = evaluate_acceptance(
        replace(inputs, quality_review=skeleton),
        evaluated_at=_FIXED_EVALUATED_AT,
    )
    assert skeleton_result.verdict == "PENDING_MANUAL_REVIEW"
    assert skeleton_result.findings == ()
    assert dict(skeleton_result.hard_gates)["manual_review_passed"] == "pending"

    first_dimension = skeleton_dimensions[0]
    partial_first_item = replace(
        first_dimension.items[0],
        score=0,
        evidence_paths=("report-v1.md",),
        notes="部分复核。",
    )
    partial = replace(
        skeleton,
        reviewer_role="investment-reviewer",
        reviewer_id_label="reviewer-1",
        dimensions=(
            replace(first_dimension, items=(partial_first_item, *first_dimension.items[1:])),
            *skeleton_dimensions[1:],
        ),
    )
    partial_result = evaluate_acceptance(
        replace(inputs, quality_review=partial),
        evaluated_at=_FIXED_EVALUATED_AT,
    )
    assert partial_result.verdict == "PENDING_MANUAL_REVIEW"

    source_dimension = inputs.quality_review.dimensions[0]
    lowered_first_item = replace(source_dimension.items[0], score=6)
    lowered_source = replace(
        source_dimension,
        score=19,
        items=(lowered_first_item, *source_dimension.items[1:]),
    )
    low_review = replace(
        inputs.quality_review,
        status="FAIL",
        dimensions=(lowered_source, *inputs.quality_review.dimensions[1:]),
        total_score=83,
    )
    low_result = evaluate_acceptance(
        replace(inputs, quality_review=low_review),
        evaluated_at=_FIXED_EVALUATED_AT,
    )
    assert low_result.verdict == "FAIL"
    assert "rubric.dimension_threshold" in {item.code for item in low_result.findings}


@pytest.mark.unit
def test_slice1_report_topics_citations_and_acceptance_quality_fail_closed(tmp_path: Path) -> None:
    """验证缺 bear、断 citation 与三段 evidence 均按确定性门禁失败。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 报告质量缺口未被拒绝时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    without_bear = replace(
        inputs,
        report_text=_drop_markdown_section(inputs.report_text, "Bear case 与反证"),
    )
    assert "report.topic.bear_case" in _finding_codes(without_bear)

    disconnected = replace(
        inputs,
        report_text=inputs.report_text.replace(
            "filing-aapl-10q-2025q1 | 10-Q / 0000320193-25-000008",
            "filing-not-in-inventory | 10-Q / 0000320193-25-000008",
            1,
        ),
    )
    disconnected_codes = _finding_codes(disconnected)
    assert "report.citation_closure" in disconnected_codes
    assert "report.inventory_closure" in disconnected_codes

    three_part = replace(
        inputs,
        report_text=inputs.report_text.replace(
            (
                "- filing-aapl-10k-2024 | 10-K / 0000320193-24-000123 | "
                "2024-11-01 | Item 1 与 Item 8，业务分部及现金流量表"
            ),
            "- filing-aapl-10k-2024 | 10-K / 0000320193-24-000123 | 2024-11-01",
            1,
        ),
    )
    assert "report.acceptance_quality.thesis" in _finding_codes(three_part)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('"price":"236.85"', '"price":"236.86"'),
        ('"currency":"USD"', '"currency":"EUR"'),
        ('"market_date":"2025-01-15"', '"market_date":"2025-01-14"'),
    ],
)
def test_slice1_report_price_currency_and_date_must_exactly_match_snapshot(
    tmp_path: Path,
    old: str,
    new: str,
) -> None:
    """验证报告估值基准的价格、币种与 market date 均需精确一致。

    Args:
        tmp_path: pytest 隔离目录。
        old: baseline reference 片段。
        new: 制造漂移的替换片段。

    Returns:
        无。

    Raises:
        AssertionError: 任一 reference 漂移未触发 FAIL 时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    mutated = replace(inputs, report_text=inputs.report_text.replace(old, new, 1))

    assert "report.valuation_reference_mismatch" in _finding_codes(mutated)


@pytest.mark.unit
def test_slice1_indented_valuation_reference_uses_one_normalized_line(tmp_path: Path) -> None:
    """验证缩进 reference 的合法与 mismatch 分支不被 schema 偏移掩盖。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 合法缩进误报或 mismatch 未命中特定 code 时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    reference_line = next(
        line for line in inputs.report_text.splitlines() if line.startswith("valuation_reference_price:")
    )
    indented_valid = replace(
        inputs,
        report_text=inputs.report_text.replace(reference_line, f"  {reference_line}", 1),
    )
    assert evaluate_acceptance(indented_valid, evaluated_at=_FIXED_EVALUATED_AT).verdict == "PASS"

    mismatch_line = reference_line.replace('"price":"236.85"', '"price":"236.86"', 1)
    indented_mismatch = replace(
        inputs,
        report_text=inputs.report_text.replace(reference_line, f"  {mismatch_line}", 1),
    )
    codes = _finding_codes(indented_mismatch)
    assert "report.valuation_reference_mismatch" in codes
    assert "report.valuation_reference_schema" not in codes


@pytest.mark.unit
def test_slice1_exact_headings_ignore_decoys_and_reject_combined_topics(tmp_path: Path) -> None:
    """验证 source-list/topic 只接受唯一精确标题且合并标题不能复用。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 诱饵遮蔽真实章节或合并标题满足多个 topic 时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    decoy_block = "## 来源清单说明\n\n诱饵内容\n\n## 风险说明\n\n诱饵内容\n\n"
    decoy_report = inputs.report_text.replace("## 来源清单", f"{decoy_block}## 来源清单", 1)
    decoy_result = evaluate_acceptance(
        replace(inputs, report_text=decoy_report),
        evaluated_at=_FIXED_EVALUATED_AT,
    )
    assert decoy_result.verdict == "PASS"

    without_catalyst = _drop_markdown_section(inputs.report_text, "催化剂（catalyst）")
    without_risk = _drop_markdown_section(without_catalyst, "风险（risk）")
    combined = (
        "## 风险与催化剂\n\n合并章节不得复用。\n\n### 证据与出处\n\n"
        "- filing-aapl-10k-2024 | 10-K / 0000320193-24-000123 | "
        "2024-11-01 | Item 1\n\n"
    )
    combined_report = without_risk.replace("## 来源清单", f"{combined}## 来源清单", 1)
    codes = _finding_codes(replace(inputs, report_text=combined_report))
    assert "report.topic.catalyst" in codes
    assert "report.topic.risk" in codes


@pytest.mark.unit
def test_slice1_inventory_future_processed_and_reprocess_cases_fail_closed(tmp_path: Path) -> None:
    """验证未来源、processed 缺失和 reprocess_required 均硬失败。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一 inventory 失败条件未被拒绝时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    document = inputs.inventory.documents[0]
    future_document = replace(document, filing_date=date(2025, 2, 2), report_date=date(2025, 2, 2))
    future_inventory = replace(
        inputs.inventory,
        documents=(future_document, *inputs.inventory.documents[1:]),
    )
    assert "inventory.future_source" in _finding_codes(replace(inputs, inventory=future_inventory))

    missing_processed = ProcessedState(
        exists=False,
        parser_version="",
        quality="",
        reprocess_required=False,
        schema_version="",
        source_fingerprint="",
    )
    missing_document = replace(
        document,
        processed=missing_processed,
        processed_state_fingerprint=canonical_json_sha256(missing_processed.to_json()),
    )
    missing_inventory = replace(
        inputs.inventory,
        documents=(missing_document, *inputs.inventory.documents[1:]),
    )
    assert "inventory.processed_missing" in _finding_codes(replace(inputs, inventory=missing_inventory))

    reprocess_state = replace(document.processed, reprocess_required=True)
    reprocess_document = replace(
        document,
        processed=reprocess_state,
        processed_state_fingerprint=canonical_json_sha256(reprocess_state.to_json()),
    )
    reprocess_inventory = replace(
        inputs.inventory,
        documents=(reprocess_document, *inputs.inventory.documents[1:]),
    )
    assert "inventory.reprocess_required" in _finding_codes(replace(inputs, inventory=reprocess_inventory))


@pytest.mark.unit
def test_slice1_price_max_age_is_a_hard_gate(tmp_path: Path) -> None:
    """验证显式 price snapshot 超过 max_age_days 时硬失败。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 超龄价格未触发 FAIL 时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    stale_price = replace(inputs.price_snapshot, max_age_days=1)

    assert "price.stale" in _finding_codes(replace(inputs, price_snapshot=stale_price))


@pytest.mark.unit
def test_slice1_budget_audit_cost_and_wall_clock_failures_are_distinct(tmp_path: Path) -> None:
    """验证 blocked budget、audit skip、超成本与 wall-clock 各自失败。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一治理失败未触发对应 code 时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    blocked_budget = replace(inputs.run_summary.budget, status="blocked", block_present=True)
    blocked_summary = replace(inputs.run_summary, budget=blocked_budget)
    assert "budget.blocked" in _finding_codes(replace(inputs, run_summary=blocked_summary))

    skipped_summary = replace(inputs.run_summary, audit_skipped_count=1)
    assert "audit.incomplete" in _finding_codes(replace(inputs, run_summary=skipped_summary))

    expensive_budget = replace(inputs.run_summary.budget, estimated_cost=Decimal("5.01"))
    expensive_summary = replace(
        inputs.run_summary,
        known_estimated_cost=Decimal("5.01"),
        budget=expensive_budget,
    )
    assert "budget.exceeded" in _finding_codes(replace(inputs, run_summary=expensive_summary))

    slow_runtime = replace(inputs.runtime, actual_wall_seconds=3_600.01)
    assert "wall_clock.exceeded" in _finding_codes(replace(inputs, runtime=slow_runtime))


@pytest.mark.unit
def test_slice1_ledger_owner_builders_bind_fixture_nested_summary_shape() -> None:
    """把真实 WriteModelUsageLedger 两个 builder 的嵌套形状绑定到 fixture parser。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: ledger usage/budget 嵌套字段与验收 fixture 漂移时抛出。
    """

    ledger = WriteModelUsageLedger(
        max_model_requests=20,
        max_total_tokens=200_000,
        max_estimated_cost=5.0,
        budget_currency="CNY",
    )
    pricing = {
        "currency": "CNY",
        "input_per_million": 1.0,
        "cached_input_per_million": 0.1,
        "output_per_million": 2.0,
    }
    ledger.record(
        scene_name="write",
        model_name="deepseek-v4-pro",
        model_role="primary",
        model_config={"pricing": pricing},
        usage=ModelUsage(
            request_count=1,
            usage_report_count=1,
            input_tokens=70_000,
            uncached_input_tokens=70_000,
            output_tokens=10_000,
            total_tokens=80_000,
        ),
        replay=False,
    )
    ledger.record(
        scene_name="audit",
        model_name="mimo-v2.5-pro-thinking",
        model_role="audit",
        model_config={"pricing": pricing},
        usage=ModelUsage(
            request_count=1,
            usage_report_count=1,
            input_tokens=30_000,
            uncached_input_tokens=30_000,
            output_tokens=10_000,
            total_tokens=40_000,
        ),
        replay=False,
    )
    payload = json.loads((_FIXTURE_ROOT / "run-summary-v1.json").read_text(encoding="utf-8"))
    payload["model_usage"] = ledger.build_summary()
    payload["budget"] = ledger.build_budget_summary()

    parsed = parse_owner_run_summary(payload)

    assert parsed.request_count == 2
    assert parsed.total_tokens == 120_000
    assert parsed.budget.model_requests == 2
    assert parsed.budget.total_tokens == 120_000
    assert parsed.budget.status == "within_budget"
    assert parsed.budget.block_present is False


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["stale", "tampered"])
def test_slice1_owner_report_validator_detects_stale_and_tampered_artifacts(
    tmp_path: Path,
    mutation: str,
) -> None:
    """验证真实 owner report validator 能区分 stale 与 body tamper。

    Args:
        tmp_path: pytest 隔离目录。
        mutation: ``stale`` 或 ``tampered`` 注入方式。

    Returns:
        无。

    Raises:
        AssertionError: 真实 owner validator 未触发对应门禁时抛出。
    """

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    if mutation == "stale":
        workbook_path = artifact_root / "technology.research-workbook.json"
        workbook = json.loads(workbook_path.read_text(encoding="utf-8"))
        workbook["company"] = "Apple Inc. fixture drift"
        workbook_path.write_text(json.dumps(workbook, ensure_ascii=False), encoding="utf-8")
    else:
        report_path = artifact_root / "technology.research-progress.md"
        report_path.write_text(report_path.read_text(encoding="utf-8") + "\nmanual tamper\n", encoding="utf-8")
    inputs = _load_acceptance_inputs_from_artifacts(artifact_root)

    codes = _finding_codes(inputs)

    assert ("workbook.stale" if mutation == "stale" else "workbook.tampered") in codes


@pytest.mark.unit
def test_slice1_monitoring_fingerprint_and_forged_bound_source_fail_closed(tmp_path: Path) -> None:
    """验证 monitoring 输入指纹漂移与伪造 bound source 均被 owner 拒绝。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 指纹或绑定伪造未触发 monitoring hard gate 时抛出。
    """

    fingerprint_root = _materialize_acceptance_artifacts(tmp_path / "fingerprint")
    source_map = fingerprint_root / "technology.source-map.json"
    source_map.write_text(source_map.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    fingerprint_inputs = _load_acceptance_inputs_from_artifacts(fingerprint_root)
    assert "monitoring.unsafe" in _finding_codes(fingerprint_inputs)

    forged_root = _materialize_acceptance_artifacts(tmp_path / "forged")
    plan_path = forged_root / "technology.monitoring-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    task = plan["tasks"][0]
    task["status"] = "ready_for_review"
    task["bound_data_sources"] = [task["data_source_candidates"][0]]
    plan["readiness"]["status"] = "blocked_unbound_sources"
    plan["readiness"]["ready_task_count"] = 1
    plan["readiness"]["blocked_task_count"] -= 1
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    forged_inputs = _load_acceptance_inputs_from_artifacts(forged_root)
    assert "monitoring.unsafe" in _finding_codes(forged_inputs)


@pytest.mark.unit
def test_slice1_artifact_symlink_and_bound_sha_tamper_fail_containment(tmp_path: Path) -> None:
    """验证研究 artifact symlink 越界与已绑定 SHA 漂移均失败。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: containment 或 tamper 未被拒绝时抛出。
    """

    tamper_root = _materialize_acceptance_artifacts(tmp_path / "tamper")
    target_name = "technology.checklist.md"
    original_sha = hashlib.sha256((tamper_root / target_name).read_bytes()).hexdigest()
    (tamper_root / target_name).write_text("tampered", encoding="utf-8")
    tampered_inputs = _load_acceptance_inputs_from_artifacts(
        tamper_root,
        expected_artifact_sha256=((target_name, original_sha),),
    )
    assert "artifacts.inventory" in _finding_codes(tampered_inputs)

    symlink_root = _materialize_acceptance_artifacts(tmp_path / "symlink")
    external = tmp_path / "external.md"
    external.write_text("outside", encoding="utf-8")
    symlink_target = symlink_root / target_name
    symlink_target.unlink()
    symlink_target.symlink_to(external)
    symlink_inputs = _load_acceptance_inputs_from_artifacts(symlink_root)
    assert "artifacts.inventory" in _finding_codes(symlink_inputs)


@pytest.mark.unit
def test_slice1_production_artifact_json_rejects_nan_before_owner_validation(tmp_path: Path) -> None:
    """验证全部生产 JSON 先经 strict ingress，NaN 不进入 owner validator。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: NaN 未以 ContractError fail closed 时抛出。
    """

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    workbook_path = artifact_root / "technology.research-workbook.json"
    original = workbook_path.read_text(encoding="utf-8")
    mutated = original.replace('"schema_version": 1', '"schema_version": NaN', 1)
    assert mutated != original
    workbook_path.write_text(mutated, encoding="utf-8")

    with pytest.raises(ContractError, match="不得包含 NaN/Infinity"):
        _load_acceptance_inputs_from_artifacts(artifact_root)


@pytest.mark.unit
def test_slice1_non_json_owner_result_is_normalized_to_contract_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 owner validator 的非 JSON 返回在既有 ingress 归一化。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。

    Returns:
        无。

    Raises:
        AssertionError: TypeError 未归一化为 ContractError 时抛出。
    """

    def non_json_workbook_result(_payload: dict[str, JsonValue]) -> dict[str, set[str]]:
        """返回一个故意包含 set 的 owner 宽结果。

        Args:
            _payload: owner workbook 输入；本替身不读取。

        Returns:
            不能 JSON 序列化的测试结果。

        Raises:
            本函数不显式抛出异常。
        """

        return {"errors": {"not-json"}}

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    monkeypatch.setattr(
        acceptance_evaluator_module,
        "validate_research_workbook_payload",
        non_json_workbook_result,
    )
    with pytest.raises(ContractError, match="workbook validation owner result 不是严格 JSON"):
        _load_acceptance_inputs_from_artifacts(artifact_root)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tree", "relative_path"),
    [
        ("assets", "定性分析模板.md"),
        ("assets", "research_templates/technology.definition.json"),
        ("assets", "research_templates/common.md"),
        ("assets", "research_templates/technology.md"),
        ("assets", "research_templates/consumer.md"),
        ("config", "prompts/manifests/write.json"),
    ],
)
def test_slice1_package_input_tree_drift_covers_all_materialization_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tree: str,
    relative_path: str,
) -> None:
    """验证 config/tree、base、definition 与 manifest-enumerated 资产漂移。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。
        tree: 要修改的复制树名称。
        relative_path: 树内相对文件路径。

    Returns:
        无。

    Raises:
        AssertionError: 目标未纳入闭包或 drift 未在执行前失败时抛出。
    """

    config_root = tmp_path / "config"
    assets_root = tmp_path / "assets"
    shutil.copytree(resolve_package_config_path(), config_root)
    shutil.copytree(resolve_package_assets_path(), assets_root)
    monkeypatch.setattr(acceptance_contracts_module, "resolve_package_config_path", lambda: config_root)
    monkeypatch.setattr(acceptance_contracts_module, "resolve_package_assets_path", lambda: assets_root)
    expected = build_package_input_fingerprints()
    research_locators = {item.locator for item in expected.research_tree.files}
    assert "dayu/assets/research_templates/common.md" in research_locators
    assert "dayu/assets/research_templates/technology.md" in research_locators
    assert "dayu/assets/research_templates/technology.definition.json" in research_locators
    assert "dayu/assets/research_templates/consumer.md" in research_locators
    assert "dayu/config/prompts/manifests/write.json" in {item.locator for item in expected.config_tree.files}
    target_root = assets_root if tree == "assets" else config_root
    target = target_root / relative_path
    target.write_bytes(target.read_bytes() + b"\nfixture drift\n")

    with pytest.raises(FingerprintDriftError, match="drift"):
        assert_package_input_fingerprints(expected)


@pytest.mark.unit
def test_slice1_package_tree_rejects_symlink_nonregular_and_duplicate_locator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 package canonical tree 对 symlink、FIFO 与重复 locator fail closed。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。

    Returns:
        无。

    Raises:
        AssertionError: 非普通输入或重复 canonical locator 被接受时抛出。
    """

    config_root = tmp_path / "config"
    assets_root = tmp_path / "assets"
    shutil.copytree(resolve_package_config_path(), config_root)
    shutil.copytree(resolve_package_assets_path(), assets_root)
    monkeypatch.setattr(acceptance_contracts_module, "resolve_package_config_path", lambda: config_root)
    monkeypatch.setattr(acceptance_contracts_module, "resolve_package_assets_path", lambda: assets_root)
    external = tmp_path / "external.md"
    external.write_text("external", encoding="utf-8")
    (assets_root / "research_templates" / "linked.md").symlink_to(external)
    with pytest.raises(ContractError, match="symlink"):
        build_package_input_fingerprints()
    (assets_root / "research_templates" / "linked.md").unlink()
    fifo = config_root / "nonregular.fifo"
    os.mkfifo(fifo)
    with pytest.raises(ContractError, match="普通文件"):
        build_package_input_fingerprints()
    fifo.unlink()

    package_inputs = build_package_input_fingerprints()
    plan = _slice2_v2_plan(tmp_path, package_inputs)
    plan_payload = plan.to_json()
    package_payload = _require_mapping(plan_payload["package_inputs"], label="plan.package_inputs")
    research_payload = _require_mapping(package_payload["research_tree"], label="plan.research_tree")
    files = _require_list(research_payload["files"], label="plan.research_tree.files")
    research_payload["files"] = [*files, files[0]]
    with pytest.raises(ContractError, match="排序且唯一"):
        parse_acceptance_plan(plan_payload)


@pytest.mark.unit
@pytest.mark.parametrize(
    "sensitive_value",
    [
        "Authorization: Bearer secret-token-value",
        "Cookie: session=secret-token-value",
        "sk-abcdefghijklmnopqrstuvwx",
        "/Users/alice/private/result.json",
        "/home/alice/private/result.json",
        r"C:\Users\alice\private\result.json",
    ],
)
def test_slice1_sanitizer_rejects_secret_and_posix_windows_home_shapes(
    tmp_path: Path,
    sensitive_value: str,
) -> None:
    """验证 sanitizer 只对验收自有输出拒绝秘密与绝对 home 路径。

    Args:
        tmp_path: pytest 隔离目录。
        sensitive_value: 待注入 acceptance-owned JSON 的敏感文本。

    Returns:
        无。

    Raises:
        AssertionError: 敏感形状未触发 hard gate 时抛出。
    """

    inputs = _load_acceptance_inputs(
        tmp_path,
        acceptance_owned_outputs=({"value": sensitive_value},),
    )

    assert "sanitizer.sensitive_shape" in _finding_codes(inputs)


@pytest.mark.unit
def test_slice1_phase_receipt_and_reviewer_labels_share_bounded_sanitizer(tmp_path: Path) -> None:
    """验证 phase receipt 与 reviewer 标签也进入验收自有敏感信息边界。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: phase argv home 路径或 reviewer PII 未被拒绝时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    with pytest.raises(ContractError, match="绝对路径"):
        CommandRecord(
            command_index=0,
            safe_argv=("<PYTHON>", "--config", "/Users/alice/private/config"),
            argv_digest="d" * 64,
            status="passed",
            started_at=datetime(2025, 2, 1, tzinfo=UTC),
            ended_at=datetime(2025, 2, 1, 0, 1, tzinfo=UTC),
            duration_seconds=60.0,
            exit_code=0,
            stop_reason=None,
            termination_action=None,
            partial_by_timeout=False,
            stdout_sha256=None,
            stderr_sha256=None,
            stdout_summary=None,
            stderr_summary=None,
            evidence=None,
        )

    pii_review = replace(inputs.quality_review, reviewer_id_label="alice@example.com")
    reviewer_inputs = replace(inputs, quality_review=pii_review)
    assert "rubric.reviewer_pii" in _finding_codes(reviewer_inputs)


@pytest.mark.unit
def test_slice1_status_snapshot_tamper_fails_research_artifact_validator(tmp_path: Path) -> None:
    """验证三个 13 产物状态快照不是仅存在即通过。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: unhealthy snapshot 未触发 artifact validator finding 时抛出。
    """

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    status_path = artifact_root / "research-workbook-report-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["overall_status"] = "unhealthy"
    status["summary"]["invalid_report_count"] = 1
    status_path.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    inputs = _load_acceptance_inputs_from_artifacts(artifact_root)

    assert "artifacts.validators" in _finding_codes(inputs)


@pytest.mark.unit
def test_slice1_inventory_and_quality_review_unknown_fields_are_rejected() -> None:
    """验证 inventory 与 rubric 顶层未知字段同样 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: inventory/rubric 未知字段被接受时抛出。
    """

    inventory = _load_json_fixture("source-inventory-v1.json")
    inventory["unexpected"] = True
    with pytest.raises(ContractError, match="unknown"):
        acceptance_contracts_module.parse_source_inventory(inventory)
    review = _load_json_fixture("quality-review-v1.json")
    review["unexpected"] = True
    with pytest.raises(ContractError, match="unknown"):
        acceptance_contracts_module.parse_quality_review(review)


@pytest.mark.unit
def test_slice1_production_absolute_paths_are_not_rewritten_or_copied_to_receipt(tmp_path: Path) -> None:
    """验证生产 artifact 原生绝对 package 路径不被扫描、改写或复制。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 生产字节变化、误判 FAIL 或 receipt 泄漏绝对路径时抛出。
    """

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    manifest_path = artifact_root / "research-template.manifest.json"
    rules_path = artifact_root / "technology.monitoring-rules.json"
    before_manifest = manifest_path.read_bytes()
    before_rules = rules_path.read_bytes()
    manifest_value: JsonValue = json.loads(before_manifest)
    rules_value: JsonValue = json.loads(before_rules)
    manifest_payload = _require_mapping(manifest_value, label="research template manifest")
    rules_payload = _require_mapping(rules_value, label="monitoring rules")
    template_entries = _require_list(manifest_payload["templates"], label="research template manifest.templates")
    technology_entry = next(
        _require_mapping(value, label="research template manifest.template")
        for value in template_entries
        if isinstance(value, dict) and value.get("name") == "technology"
    )
    template_file = technology_entry["template_file"]
    source_template_file = rules_payload["source_template_file"]
    assert isinstance(template_file, str) and Path(template_file).is_absolute()
    assert isinstance(source_template_file, str) and Path(source_template_file).is_absolute()
    inputs = _load_acceptance_inputs_from_artifacts(artifact_root)

    result = evaluate_acceptance(inputs, evaluated_at=_FIXED_EVALUATED_AT)

    assert result.verdict == "PASS"
    assert manifest_path.read_bytes() == before_manifest
    assert rules_path.read_bytes() == before_rules
    receipt = result.canonical_bytes()
    assert template_file.encode("utf-8") not in receipt
    assert source_template_file.encode("utf-8") not in receipt
    assert b"template_file" not in receipt
    assert b"source_template_file" not in receipt
    assert all(reference.locator.startswith(f"{_ACCEPTANCE_ARTIFACT_PREFIX}/") for reference in result.artifacts)


@pytest.mark.unit
def test_slice1_repository_inventory_uses_only_protocol_methods_and_strict_ingress() -> None:
    """验证 source inventory 只通过三个仓储 Protocol 读取并立即严格收窄。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 协议调用、排序或 primary/processed 指纹闭包错误时抛出。
    """

    source_repository = create_autospec(SourceDocumentRepositoryProtocol, instance=True)
    processed_repository = create_autospec(ProcessedDocumentRepositoryProtocol, instance=True)
    blob_repository = create_autospec(DocumentBlobRepositoryProtocol, instance=True)
    source_repository.list_source_document_ids.side_effect = lambda _ticker, kind: (
        ["filing-aapl-10k-2024"] if kind == SourceKind.FILING else ["material-price"]
    )
    source_payloads = {
        "filing-aapl-10k-2024": {
            "document_id": "filing-aapl-10k-2024",
            "internal_document_id": "0000320193-24-000123",
            "form_type": "10-K",
            "filing_date": "2024-11-01",
            "report_date": "2024-09-28",
            "fiscal_year": 2024,
            "fiscal_period": "FY",
            "ingest_complete": True,
        },
        "material-price": {
            "document_id": "material-price",
            "internal_document_id": "material-price",
            "form_type": "MATERIAL_OTHER",
            "filing_date": "2025-01-15",
            "report_date": "2025-01-15",
            "fiscal_year": None,
            "fiscal_period": None,
            "ingest_complete": True,
        },
    }
    source_repository.get_source_meta.side_effect = lambda _ticker, document_id, _kind: source_payloads[document_id]
    processed_repository.get_processed_meta.side_effect = lambda _ticker, document_id: {
        "document_id": document_id,
        "parser_version": "fixture-parser-v1",
        "quality": "accepted_fixture",
        "reprocess_required": False,
        "schema_version": "processed_document_v1",
        "source_fingerprint": hashlib.sha256(document_id.encode("utf-8")).hexdigest(),
    }
    source_repository.get_primary_file.side_effect = lambda _ticker, document_id, _kind: FileObjectMeta(
        uri=f"storage://{document_id}/primary.md",
        sha256=hashlib.sha256(document_id.encode("utf-8")).hexdigest(),
    )
    source_repository.get_source_handle.side_effect = lambda ticker, document_id, kind: SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=kind.value,
    )
    blob_repository.read_file_bytes.side_effect = lambda handle, _name: handle.document_id.encode("utf-8")
    as_of = datetime(2025, 2, 1, tzinfo=UTC)

    inventory = build_source_inventory_from_repositories(
        RepositoryInventoryRequest(
            fixture_id="repository-fixture",
            ticker="AAPL",
            company="Apple Inc.",
            as_of=as_of,
            live_freshness_claimed=True,
            source_windows=(
                SourceWindow(("10-K",), date(2020, 2, 1), date(2025, 2, 1)),
                SourceWindow(("10-Q",), date(2023, 2, 1), date(2025, 2, 1)),
                SourceWindow(("8-K", "DEF 14A"), date(2023, 2, 1), date(2025, 2, 1)),
            ),
            latest_discovery=(("10-K", "0000320193-24-000123"),),
            source_repository=source_repository,
            processed_repository=processed_repository,
            blob_repository=blob_repository,
        )
    )

    assert [item.document_id for item in inventory.documents] == [
        "filing-aapl-10k-2024",
        "material-price",
    ]
    assert all(item.processed.exists for item in inventory.documents)
    assert all(
        item.primary_file_sha256 == hashlib.sha256(item.document_id.encode()).hexdigest()
        for item in inventory.documents
    )
    assert source_repository.list_source_document_ids.call_count == 2
    assert source_repository.get_source_meta.call_count == 2
    assert processed_repository.get_processed_meta.call_count == 2
    assert blob_repository.read_file_bytes.call_count == 2


@pytest.mark.unit
def test_slice2_prepare_builds_atomic_v2_plan_skeleton_and_terminal_after_fingerprint(tmp_path: Path) -> None:
    """验证 prepare 离线原子骨架、唯一 plan 与 fingerprint 后 terminal 派生。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: plan、目录、价格、rubric 或 terminal contract 漂移时抛出。
    """

    prepared, services = _prepare_slice2_run(tmp_path)
    run_root = Path(prepared.plan.run_root)
    assert prepared.plan_path == run_root / "acceptance-plan.json"
    assert parse_acceptance_plan(load_json_file(prepared.plan_path, label="prepared plan")) == prepared.plan
    assert hashlib.sha256(prepared.plan_path.read_bytes()).hexdigest() == prepared.fingerprint
    assert tuple((spec.phase_name, len(spec.commands)) for spec in prepared.plan.phase_specs) == tuple(
        PLANNED_PHASE_COMMAND_COUNTS
    )
    assert all(spec.phase_name != "verify" for spec in prepared.plan.phase_specs)
    terminal = build_terminal_verify_command(
        plan=prepared.plan,
        fingerprint=prepared.fingerprint,
        python_executable=services.runtime.python_executable,
    )
    assert terminal[-3:] == ("--fingerprint", prepared.fingerprint, "--json")
    assert all(
        prepared.fingerprint not in token
        for spec in prepared.plan.phase_specs
        for command in spec.commands
        for token in command
    )
    expected_paths = (
        "inputs/price-snapshot.json",
        "inputs/price-snapshot.material.md",
        "phase-receipts/prepare.json",
        "data-workspace",
        "write",
        "research/assets/research_templates",
        "quality-review.json",
    )
    assert all((run_root / locator).exists() for locator in expected_paths)
    quality = load_json_file(run_root / "quality-review.json", label="quality skeleton")
    assert quality["status"] == "PENDING_MANUAL_REVIEW"
    assert quality["reviewer_role"] is None
    assert quality["reviewer_id_label"] is None
    assert not tuple(run_root.parent.glob(f".{run_root.name}.staging-*"))

    v1_payload = prepared.plan.to_json()
    v1_payload["schema_version"] = 1
    with pytest.raises(ContractError, match="schema_version"):
        parse_acceptance_plan(v1_payload)


@pytest.mark.unit
def test_slice2_prepare_failure_cleans_exact_staging_without_publishing_run_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 staging 构建失败不会留下正式 run root 或本次 staging。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。

    Returns:
        无。

    Raises:
        AssertionError: 失败后出现正式目录或 staging 残留时抛出。
    """

    request, services = _slice2_prepare_inputs(tmp_path)

    def fail_skeleton(
        *,
        staging: Path,
        plan: AcceptancePlan,
        price_bytes: bytes,
        material_bytes: bytes,
        clock: _FixedClock,
    ) -> None:
        del staging, plan, price_bytes, material_bytes, clock
        raise OSError("fixture staging failure")

    monkeypatch.setattr(acceptance_cli_module, "_write_run_skeleton", fail_skeleton)
    with pytest.raises(OSError, match="staging failure"):
        prepare_acceptance(request, services)
    assert not request.run_root.exists()
    assert not tuple(request.run_root.parent.glob(f".{request.run_root.name}.staging-*"))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("argv", "expected_type"),
    [
        (("verify", "--fixture", str(_FIXTURE_ROOT), "--json"), VerifyCliCommand),
        (
            (
                "verify",
                "--plan",
                "/tmp/run/acceptance-plan.json",
                "--fingerprint",
                "a" * 64,
                "--json",
            ),
            VerifyCliCommand,
        ),
        (
            (
                "prepare",
                "--ticker",
                "AAPL",
                "--company",
                "Apple Inc.",
                "--template",
                "technology",
                "--as-of",
                "2025-02-01T00:00:00Z",
                "--run-root",
                "/tmp/run",
                "--price-snapshot",
                "/tmp/price.json",
                "--max-model-requests",
                "20",
                "--max-total-tokens",
                "200000",
                "--max-estimated-cost",
                "5",
                "--budget-currency",
                "CNY",
                "--max-wall-seconds",
                "3600",
                "--json",
            ),
            PrepareCliCommand,
        ),
    ],
)
def test_slice2_cli_parser_accepts_complete_prepare_and_two_verify_modes(
    argv: tuple[str, ...],
    expected_type: type[PrepareCliCommand] | type[VerifyCliCommand],
) -> None:
    """验证 prepare 显式预算与 fixture/live verify 两个 happy parser mode。

    Args:
        argv: 完整 CLI 参数。
        expected_type: 期望的收窄命令类型。

    Returns:
        无。

    Raises:
        AssertionError: parser 未收窄到预期命令时抛出。
    """

    assert isinstance(parse_cli_arguments(argv), expected_type)


@pytest.mark.unit
@pytest.mark.parametrize(
    "argv",
    [
        ("verify", "--fixture", str(_FIXTURE_ROOT), "--plan", "/tmp/plan", "--fingerprint", "a" * 64),
        ("verify", "--plan", "/tmp/plan"),
        ("verify", "--fingerprint", "a" * 64),
        ("verify",),
    ],
)
def test_slice2_cli_parser_rejects_mixed_or_partial_verify_before_read(argv: tuple[str, ...]) -> None:
    """验证混合或缺半边 live verify 参数在读取产物前 fail closed。

    Args:
        argv: 非法 verify 参数组合。

    Returns:
        无。

    Raises:
        AssertionError: parser 未以标准 code 2 拒绝时抛出。
    """

    with pytest.raises(SystemExit) as exc_info:
        parse_cli_arguments(argv)
    assert exc_info.value.code == 2


@pytest.mark.unit
def test_slice2_fixture_verify_is_offline_pass_and_byte_stable(tmp_path: Path) -> None:
    """验证 deterministic fixture 模式不需要 plan 且同输入字节稳定 PASS。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: fixture policy、verdict 或重复输出不稳定时抛出。
    """

    request = VerifyRequest(
        mode="fixture",
        fixture_root=_FIXTURE_ROOT,
        plan_path=None,
        fingerprint=None,
    )
    clock = _FixedClock(datetime(2030, 1, 1, tzinfo=UTC))
    first = verify_acceptance(request, clock=clock)
    second = verify_acceptance(request, clock=clock)
    assert first["verdict"] == "PASS"
    assert canonical_json_sha256(first) == canonical_json_sha256(second)
    assert not (tmp_path / "unexpected").exists()


@pytest.mark.unit
def test_slice2_safe_argv_uses_only_three_placeholders_and_digest_binds_raw_command(tmp_path: Path) -> None:
    """验证真实 absolute argv 只持久化三个 placeholder 与 raw digest。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: receipt 泄露 absolute 路径或 digest 不闭合时抛出。
    """

    run_root = (tmp_path / "run").resolve()
    config_root = resolve_package_config_path().resolve()
    python_path = Path(sys.executable).resolve().as_posix()
    command = (
        python_path,
        "-m",
        "dayu.cli",
        "process",
        "--base",
        f"{run_root.as_posix()}/data-workspace",
        "--config",
        config_root.as_posix(),
    )
    safe, digests = safe_argv_and_digests(
        (command,),
        python_executable=python_path,
        run_root=run_root.as_posix(),
        package_config_root=config_root,
    )
    assert safe == (
        (
            "<PYTHON>",
            "-m",
            "dayu.cli",
            "process",
            "--base",
            "<RUN_ROOT>/data-workspace",
            "--config",
            "<PACKAGE_CONFIG>",
        ),
    )
    assert digests == (canonical_json_sha256(list(command)),)
    encoded = canonical_json_bytes({"safe_argv": [list(safe[0])], "argv_digests": list(digests)})
    assert run_root.as_posix().encode() not in encoded
    assert config_root.as_posix().encode() not in encoded
    assert python_path.encode() not in encoded


@pytest.mark.unit
def test_slice2_runner_executes_exact_allowlisted_order_and_writes_success_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 fake runner 精确执行 12 planned 命令再派生 terminal verify。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。

    Returns:
        无。

    Raises:
        AssertionError: argv 顺序、receipt 或 terminal derivation 漂移时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    factory = _FakeProcessFactory((0,) * 13)
    services = RunServices(
        runtime=prepare_services.runtime,
        environment=prepare_services.environment,
        repository_state=prepare_services.repository_state,
        clock=prepare_services.clock,
        process_factory=factory,
    )
    result = run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        services,
    )
    expected_planned = tuple(command for spec in prepared.plan.phase_specs for command in spec.commands)
    expected_terminal = build_terminal_verify_command(
        plan=prepared.plan,
        fingerprint=prepared.fingerprint,
        python_executable=services.runtime.python_executable,
    )
    assert result.succeeded
    assert tuple(factory.calls) == (*expected_planned, expected_terminal)
    receipt_root = Path(prepared.plan.run_root) / "phase-receipts"
    assert {path.name for path in receipt_root.iterdir()} == {
        "prepare.json",
        "download.json",
        "price-snapshot-import.json",
        "process.json",
        "write-preflight.json",
        "write.json",
        "validations.json",
        "verify.json",
    }
    receipts = acceptance_cli_module._load_and_validate_receipt_prefix(prepared.plan, prepared.fingerprint)
    assert tuple(receipt.phase_name for receipt in receipts) == (
        *(phase_name for phase_name, _count in PLANNED_PHASE_COMMAND_COUNTS),
        "verify",
    )


@pytest.mark.unit
def test_slice2_real_download_formatter_ingress_is_anchored_strict_and_semantic(
    tmp_path: Path,
) -> None:
    """验证真实 download formatter 的前缀、严格结构与 exit-0 semantic stop。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 前缀改变 evidence 或结构变异被接受时抛出。
    """

    prepared, _services = _prepare_slice2_run(tmp_path)
    command = prepared.plan.phase_specs[0].commands[0]
    clean = _real_download_stdout()
    clean_evidence, clean_prefix = acceptance_cli_module._parse_download_output(command, clean.decode())
    prefixed = b"WARNING httpx retry\n" + clean
    prefixed_evidence, prefix_count = acceptance_cli_module._parse_download_output(command, prefixed.decode())
    assert clean_prefix == 0
    assert prefix_count == 1
    assert prefixed_evidence == clean_evidence
    assert hashlib.sha256(prefixed).hexdigest() != hashlib.sha256(clean).hexdigest()
    prefix_summary = acceptance_cli_module._stream_summary(prefixed, category="prefix_noise", line_number=1)
    assert prefix_summary is not None
    assert prefix_summary.startswith("category=prefix_noise line=1")

    cancelled, _prefix = acceptance_cli_module._parse_download_output(
        command,
        _real_download_stdout("cancelled").decode(),
    )
    assert acceptance_cli_module._owner_semantic_stop_reason(prepared.plan, cancelled) == "download_semantic_failure"

    malformed = (
        clean.decode().replace("form=10-K", "form=", 1),
        clean.decode().replace("fil_0000320193-24-000123", "fil_sec_bad", 1),
        clean.decode().replace("- status: ok\n", "", 1),
        clean.decode() + "\n下载结果",
    )
    for text in malformed:
        with pytest.raises(acceptance_cli_module._OwnerOutputError):
            acceptance_cli_module._parse_download_output(command, text)


@pytest.mark.unit
def test_slice2_download_sections_failed_duplicate_and_all_skipped_are_closed(tmp_path: Path) -> None:
    """验证 failed/重复 section 停机，all-skipped 仍是 usable discovery。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: section status 未闭合或 failed 被当作 usable 时抛出。
    """

    prepared, _services = _prepare_slice2_run(tmp_path)
    command = prepared.plan.phase_specs[0].commands[0]
    skipped_text = format_cli_result(
        FinsCommandName.DOWNLOAD,
        DownloadResultData(
            pipeline="sec",
            status="ok",
            ticker="AAPL",
            filings=(
                DownloadFilingResultItem(
                    document_id="fil_0000320193-24-000123",
                    status=DownloadFilingResultStatus.SKIPPED,
                    form_type="10-K",
                    filing_date="2025-01-30",
                ),
            ),
            summary=OwnerDownloadSummary(total=1, downloaded=0, skipped=1, failed=0),
        ),
    )
    skipped, _prefix = acceptance_cli_module._parse_download_output(command, skipped_text)
    assert skipped.rows[0].section_status == "skipped"
    assert acceptance_cli_module._owner_semantic_stop_reason(prepared.plan, skipped) is None

    failed_text = format_cli_result(
        FinsCommandName.DOWNLOAD,
        DownloadResultData(
            pipeline="sec",
            status="ok",
            ticker="AAPL",
            filings=(
                DownloadFilingResultItem(
                    document_id="fil_0000320193-24-000123",
                    status=DownloadFilingResultStatus.FAILED,
                    form_type="10-K",
                    filing_date="2025-01-30",
                ),
            ),
            summary=OwnerDownloadSummary(total=1, downloaded=0, skipped=0, failed=1),
        ),
    )
    failed, _prefix = acceptance_cli_module._parse_download_output(command, failed_text)
    assert failed.rows[0].section_status == "failed"
    assert acceptance_cli_module._owner_semantic_stop_reason(prepared.plan, failed) == "download_semantic_failure"

    duplicate = skipped_text.replace(
        "失败的 filings:\n  - （无）",
        "失败的 filings:\n"
        "  - fil_0000320193-24-000123 | form=10-K | filing_date=2025-01-30 | report_date=- | "
        "status=failed | downloaded_files=0 | skipped_files=0 | failed_files=0 | reason=- | message=-",
    ).replace("failed=0", "failed=1", 1).replace("total=1", "total=2", 1)
    with pytest.raises(ContractError, match="重复"):
        acceptance_cli_module._parse_download_output(command, duplicate)


@pytest.mark.unit
@pytest.mark.parametrize(("status", "action", "sparse"), [("ok", "create", False), ("ok", "update", False), ("skipped", "create", True), ("skipped", "update", True)])
def test_slice2_real_upload_formatter_accepts_orthogonal_full_and_sparse_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    action: str,
    sparse: bool,
) -> None:
    """验证 upload status/action 正交且 full/sparse grammar 都闭合仓储。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。
        status: ok 或 skipped。
        action: create 或 update。
        sparse: 是否省略 skipped 条件字段。

    Returns:
        无。

    Raises:
        AssertionError: 正交状态未保留或仓储闭包失败时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, _services = _prepare_slice2_run(tmp_path)
    evidence, prefix = acceptance_cli_module._parse_material_output(
        prepared.plan,
        _real_material_stdout(status=status, action=action, sparse=sparse).decode(),
    )
    assert prefix == 0
    assert evidence.owner_status == status
    assert evidence.material_action == action
    assert evidence.document_id == prepared.plan.price_material_document_id
    assert acceptance_cli_module._owner_semantic_stop_reason(prepared.plan, evidence) is None


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["delete", "unknown_status", "duplicate", "reorder", "missing_files"])
def test_slice2_upload_grammar_mutations_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    """验证 upload delete/未知状态/可选字段重复重排/缺 files 全部拒绝。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。
        mutation: 当前文法变异。

    Returns:
        无。

    Raises:
        AssertionError: 非法 grammar 被接受时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, _services = _prepare_slice2_run(tmp_path)
    text = _real_material_stdout().decode()
    if mutation == "delete":
        text = text.replace("- material_action: create", "- material_action: delete")
    elif mutation == "unknown_status":
        text = text.replace("- status: ok", "- status: future")
    elif mutation == "duplicate":
        text = text.replace("- report_date: 2025-01-15", "- report_date: 2025-01-15\n- report_date: 2025-01-15")
    elif mutation == "reorder":
        text = text.replace(
            "- form_type: MATERIAL_OTHER\n- material_name: aapl-price-snapshot",
            "- material_name: aapl-price-snapshot\n- form_type: MATERIAL_OTHER",
        )
    else:
        text = text.replace("files:\n  - price-snapshot.material.md", "")
    with pytest.raises(acceptance_cli_module._OwnerOutputError):
        acceptance_cli_module._parse_material_output(prepared.plan, text)


@pytest.mark.unit
def test_slice2_real_process_formatter_only_trusts_document_id_and_todo_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 process opaque quality 不入 evidence，TODO/cancelled 按 semantic gate 停机。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。

    Returns:
        无。

    Raises:
        AssertionError: opaque tail 污染 evidence 或 semantic stop 丢失时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, _services = _prepare_slice2_run(tmp_path)
    evidence, prefix = acceptance_cli_module._parse_process_output(
        _real_process_stdout(reason="opaque | quality=fake").decode()
    )
    assert prefix == 0
    assert evidence.rows[0] == ProcessEvidenceRow(
        document_id="fil_0000320193-24-000123",
        source_kind="filing",
        status="processed",
    )
    assert b"quality" not in canonical_json_bytes(evidence.to_json())
    assert acceptance_cli_module._owner_semantic_stop_reason(prepared.plan, evidence) is None

    todo, _prefix = acceptance_cli_module._parse_process_output(_real_process_stdout(material_todo=True).decode())
    assert todo.materials_todo
    assert todo.material_summary is None
    assert acceptance_cli_module._owner_semantic_stop_reason(prepared.plan, todo) == "process_semantic_failure"
    cancelled, _prefix = acceptance_cli_module._parse_process_output(_real_process_stdout(status="cancelled").decode())
    assert acceptance_cli_module._owner_semantic_stop_reason(prepared.plan, cancelled) == "process_semantic_failure"

    reordered = _real_process_stdout().decode().replace(
        "成功处理的 filings:",
        "临时标记",
    ).replace("失败的 filings:", "成功处理的 filings:").replace("临时标记", "失败的 filings:")
    with pytest.raises(acceptance_cli_module._OwnerOutputError):
        acceptance_cli_module._parse_process_output(reordered)


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["cancelled", "empty_form"])
def test_slice2_runner_normalizes_exit_zero_owner_reject_before_paid_write(
    tmp_path: Path,
    mutation: str,
) -> None:
    """验证 exit-0 cancelled/空 form 均形成 failed v3 record 且不越过首命令。

    Args:
        tmp_path: pytest 隔离目录。
        mutation: 语义失败或结构失败。

    Returns:
        无。

    Raises:
        AssertionError: runner 越过失败或 receipt 分类不真实时抛出。
    """

    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    stdout = _real_download_stdout("cancelled")
    expected_reason = "download_semantic_failure"
    if mutation == "empty_form":
        stdout = _real_download_stdout().replace(b"form=10-K", b"form=")
        expected_reason = "owner_output_structure_reject"
    factory = _FakeProcessFactory((0,), stdout_overrides=(stdout,))
    result = run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=factory,
        ),
    )
    assert not result.succeeded
    assert result.stop_reason == expected_reason
    assert len(factory.calls) == 1
    receipt = parse_phase_receipt(
        load_json_file(Path(prepared.plan.run_root) / "phase-receipts/download.json", label="owner reject receipt")
    )
    assert len(receipt.command_records) == 1
    record = receipt.command_records[0]
    assert record.status == "failed"
    assert record.exit_code == 0
    assert record.stop_reason == expected_reason
    if mutation == "empty_form":
        assert record.evidence is None
        assert record.stdout_summary is not None
        assert record.stdout_summary.startswith("category=structure_reject line=6")
    else:
        assert isinstance(record.evidence, DownloadCommandEvidence)
        assert record.evidence.owner_status == "cancelled"


@pytest.mark.unit
@pytest.mark.parametrize("failure", ["terminate", "kill"])
def test_slice2_timeout_termination_oserror_is_unconfirmed(tmp_path: Path, failure: str) -> None:
    """验证 terminate/kill OSError 均不伪造已终止事实。

    Args:
        tmp_path: pytest 隔离目录。
        failure: 注入 terminate 或 kill 失败。

    Returns:
        无。

    Raises:
        AssertionError: termination action 未归一化时抛出。
    """

    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    factory = _FakeProcessFactory(
        ("timeout",),
        survives_terminate=failure == "kill",
        terminate_raises=failure == "terminate",
        kill_raises=failure == "kill",
    )
    result = acceptance_cli_module._execute_command(
        (Path(sys.executable).resolve().as_posix(), "-m", "dayu.cli", "process"),
        timeout_seconds=30.0,
        plan=prepared.plan,
        services=RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=factory,
        ),
    )
    assert result.status == "timeout"
    assert result.partial_by_timeout
    assert result.termination_action == "termination_unconfirmed"


@pytest.mark.unit
@pytest.mark.parametrize("target", ["first_command", "terminal"])
def test_slice2_whole_wall_exhaustion_is_not_started_timeout(tmp_path: Path, target: str) -> None:
    """验证首命令前与 terminal 前耗尽都写 timeout/not_started 事实。

    Args:
        tmp_path: pytest 隔离目录。
        target: 注入 first command 或 terminal 边界。

    Returns:
        无。

    Raises:
        AssertionError: 超时被误标或启动了子进程时抛出。
    """

    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    factory = _FakeProcessFactory(())
    services = RunServices(
        runtime=prepare_services.runtime,
        environment=prepare_services.environment,
        repository_state=prepare_services.repository_state,
        clock=_FixedClock(datetime(2025, 2, 1, 0, 1, tzinfo=UTC), monotonic_value=3_601.0),
        process_factory=factory,
    )
    if target == "first_command":
        result = acceptance_cli_module._execute_phase(
            plan=prepared.plan,
            spec=prepared.plan.phase_specs[0],
            run_started=0.0,
            services=services,
            config_root=resolve_package_config_path().resolve(strict=True),
        )
        receipt_path = Path(prepared.plan.run_root) / "phase-receipts/download.json"
    else:
        command = build_terminal_verify_command(
            plan=prepared.plan,
            fingerprint=prepared.fingerprint,
            python_executable=prepare_services.runtime.python_executable,
        )
        result = acceptance_cli_module._execute_terminal_verify(
            plan=prepared.plan,
            command=command,
            run_started=0.0,
            services=services,
            config_root=resolve_package_config_path().resolve(strict=True),
        )
        receipt_path = Path(prepared.plan.run_root) / "phase-receipts/verify.json"
    receipt = parse_phase_receipt(load_json_file(receipt_path, label="not-started timeout receipt"))
    record = receipt.command_records[0]
    assert result.status == receipt.status == record.status == "timeout"
    assert record.termination_action == "not_started"
    assert record.partial_by_timeout
    assert record.exit_code is None
    assert factory.calls == []


@pytest.mark.unit
def test_slice2_atomic_source_inventory_create_same_and_drift(tmp_path: Path) -> None:
    """验证 source inventory 仅允许 canonical 新建或同字节重验。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 非同字节或 symlink 目标被接受时抛出。
    """

    path = tmp_path / "source-inventory.json"
    payload = canonical_json_bytes({"inventory": "fixed"})
    acceptance_cli_module._atomic_write_or_assert_same(path, payload)
    acceptance_cli_module._atomic_write_or_assert_same(path, payload)
    assert path.read_bytes() == payload
    with pytest.raises(ContractError, match="不同"):
        acceptance_cli_module._atomic_write_or_assert_same(path, canonical_json_bytes({"inventory": "drift"}))
    path.unlink()
    path.symlink_to(tmp_path / "missing-target")
    with pytest.raises(ContractError, match="普通文件"):
        acceptance_cli_module._atomic_write_or_assert_same(path, payload)


@pytest.mark.unit
@pytest.mark.parametrize(
    "mutation",
    ["phase_order", "subcommand", "download_quiet", "write_quiet", "document_id", "validator", "duplicate"],
)
def test_slice2_structural_allowlist_rejects_each_independent_identity(
    tmp_path: Path,
    mutation: str,
) -> None:
    """验证 phase/subcommand/quiet/stable-ID/validator/重复命令均独立 fail closed。

    Args:
        tmp_path: pytest 隔离目录。
        mutation: 当前结构身份变异。

    Returns:
        无。

    Raises:
        AssertionError: 变异 phase matrix 被 allowlist 接受时抛出。
    """

    prepared, _services = _prepare_slice2_run(tmp_path)
    specs = list(prepared.plan.phase_specs)
    if mutation == "phase_order":
        specs[0], specs[1] = specs[1], specs[0]
    elif mutation == "subcommand":
        command = specs[0].commands[0]
        specs[0] = replace(specs[0], commands=(((*command[:3], "process", *command[4:])), *specs[0].commands[1:]))
    elif mutation == "download_quiet":
        command = tuple(token for token in specs[0].commands[0] if token != "--quiet")
        specs[0] = replace(specs[0], commands=(command, *specs[0].commands[1:]))
    elif mutation == "write_quiet":
        specs[4] = replace(specs[4], commands=((*specs[4].commands[0], "--quiet"),))
    elif mutation == "document_id":
        command = specs[1].commands[0]
        index = command.index("--document-id")
        specs[1] = replace(specs[1], commands=((*command[:index], *command[index + 2 :]),))
    elif mutation == "validator":
        command = specs[-1].commands[0]
        specs[-1] = replace(specs[-1], commands=((*command[:4], "future-action", *command[5:]), *specs[-1].commands[1:]))
    else:
        with pytest.raises(ContractError, match="重复"):
            replace(specs[0], commands=(specs[0].commands[0], specs[0].commands[0], specs[0].commands[2]))
        return
    with pytest.raises(ContractError):
        acceptance_cli_module._assert_structural_allowlist(tuple(specs))


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["module", "config", "shell"])
def test_slice2_dayu_command_shape_rejects_module_config_and_shell(
    tmp_path: Path,
    mutation: str,
) -> None:
    """验证单命令 module/base-config/shell token 结构边界。

    Args:
        tmp_path: pytest 隔离目录。
        mutation: 命令形状变异。

    Returns:
        无。

    Raises:
        AssertionError: 非法命令被接受时抛出。
    """

    prepared, _services = _prepare_slice2_run(tmp_path)
    command = prepared.plan.phase_specs[0].commands[0]
    if mutation == "module":
        command = (*command[:2], "future.cli", *command[3:])
    elif mutation == "config":
        config_index = command.index("--config")
        command = (*command[:config_index], *command[config_index + 2 :])
    else:
        command = (*command, "&&")
    with pytest.raises(ContractError):
        acceptance_cli_module._validate_cli_command_shape(command)


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["flag_abs", "outside_abs", "home", "windows"])
def test_slice2_safe_argv_rejects_all_uncontrolled_absolute_shapes(tmp_path: Path, mutation: str) -> None:
    """验证 flag 右值、外部 POSIX、home 与 Windows 路径全部拒绝。

    Args:
        tmp_path: pytest 隔离目录。
        mutation: 待测路径形状。

    Returns:
        无。

    Raises:
        AssertionError: 未受控路径被持久化时抛出。
    """

    token = {
        "flag_abs": "--output=/tmp/uncontrolled",
        "outside_abs": "/tmp/uncontrolled",
        "home": "~/private",
        "windows": r"C:\\Users\\alice\\private",
    }[mutation]
    with pytest.raises(ContractError):
        acceptance_cli_module._safe_argv_token(
            token,
            python_executable=Path(sys.executable).resolve().as_posix(),
            run_root=(tmp_path / "run").resolve().as_posix(),
            package_config_root=resolve_package_config_path().resolve().as_posix(),
        )


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["target", "utc_naive", "utc_precision", "years", "leap"])
def test_slice2_scalar_identity_and_time_helpers_are_strict(mutation: str) -> None:
    """验证固定目标、UTC 精度与 calendar-year clamp 边界。

    Args:
        mutation: 当前 scalar/time 边界。

    Returns:
        无。

    Raises:
        AssertionError: 非法值被接受或闰日未 clamp 时抛出。
    """

    if mutation == "target":
        with pytest.raises(ContractError, match="AAPL"):
            acceptance_cli_module._validate_fixed_target("MSFT", "Apple Inc.", "technology")
    elif mutation == "utc_naive":
        with pytest.raises(ContractError, match="时区"):
            acceptance_cli_module._require_utc_datetime(datetime(2025, 2, 1), "test")
    elif mutation == "utc_precision":
        with pytest.raises(ContractError, match="秒精度"):
            acceptance_cli_module._require_utc_datetime(
                datetime(2025, 2, 1, 0, 0, 0, 1, tzinfo=UTC),
                "test",
            )
    elif mutation == "years":
        with pytest.raises(ContractError, match="正整数"):
            acceptance_cli_module._subtract_calendar_years(date(2024, 2, 29), 0)
    else:
        assert acceptance_cli_module._subtract_calendar_years(date(2024, 2, 29), 1) == date(2023, 2, 28)


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["future_capture", "future_market", "old_capture", "old_market"])
def test_slice2_price_freshness_rejects_each_time_boundary(mutation: str) -> None:
    """验证 price captured/market 的 future 与 max-age 边界。

    Args:
        mutation: 时间变异类型。

    Returns:
        无。

    Raises:
        AssertionError: 未来或超龄价格被接受时抛出。
    """

    as_of = datetime(2025, 2, 1, tzinfo=UTC)
    captured_at = datetime(2025, 1, 15, tzinfo=UTC)
    market_date = date(2025, 1, 15)
    if mutation == "future_capture":
        captured_at = datetime(2025, 2, 2, tzinfo=UTC)
    elif mutation == "future_market":
        market_date = date(2025, 2, 2)
    elif mutation == "old_capture":
        captured_at = datetime(2024, 12, 1, tzinfo=UTC)
    else:
        market_date = date(2024, 12, 1)
    price = PriceSnapshot(
        price=Decimal("236.85"),
        currency="USD",
        market_date=market_date,
        source_url="https://example.invalid/AAPL",
        captured_at=captured_at,
        max_age_days=30,
    )
    with pytest.raises(ContractError):
        acceptance_cli_module._validate_price_freshness(price, as_of)


@pytest.mark.unit
def test_slice2_fixture_lock_reports_owner_and_cleanup_preserves_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 repo-private fixture lock 可诊断且 cleanup 失败不掩盖主异常。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。

    Returns:
        无。

    Raises:
        AssertionError: stale 诊断或主异常优先级丢失时抛出。
    """

    locator = f"workspace/acceptance/.fixture-test-{tmp_path.name}"
    monkeypatch.setattr(acceptance_cli_module, "_FIXTURE_RUNTIME_LOCATOR", locator)
    repository_root = Path(acceptance_cli_module.__file__).resolve().parent.parent
    workspace = repository_root / locator
    lock = workspace.parent / f"{workspace.name}.lock"
    lock.mkdir(parents=True)
    owner: JsonObject = {
        "pid": 1,
        "started_at": "2025-02-01T00:00:00Z",
        "run_label": "stale-test-owner",
    }
    (lock / "owner.json").write_bytes(canonical_json_bytes(owner))
    try:
        with pytest.raises(ContractError, match="stale-test-owner"):
            acceptance_cli_module._verify_fixture(_FIXTURE_ROOT)
    finally:
        shutil.rmtree(lock)

    def fail_materialize(
        template: str,
        *,
        workspace_root: Path,
        ticker: str,
        company: str,
    ) -> None:
        del template, workspace_root, ticker, company
        raise ContractError("primary fixture failure")

    def fail_cleanup(_workspace: Path, _lock: Path) -> str:
        return "cleanup_os_error"

    monkeypatch.setattr(acceptance_cli_module, "materialize_research_workspace", fail_materialize)
    monkeypatch.setattr(acceptance_cli_module, "_cleanup_fixture_runtime", fail_cleanup)
    try:
        with pytest.raises(ContractError, match="primary fixture failure") as exc_info:
            acceptance_cli_module._verify_fixture(_FIXTURE_ROOT)
        assert exc_info.value.__notes__ == ["fixture cleanup failed"]
    finally:
        if lock.exists():
            shutil.rmtree(lock)


@pytest.mark.unit
def test_slice2_fixture_cleanup_failure_without_primary_is_raised(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 fixture 主流程成功后 cleanup 失败不会被静默忽略。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。

    Returns:
        无。

    Raises:
        AssertionError: cleanup error 未向调用方报告时抛出。
    """

    locator = f"workspace/acceptance/.fixture-cleanup-{tmp_path.name}"
    monkeypatch.setattr(acceptance_cli_module, "_FIXTURE_RUNTIME_LOCATOR", locator)
    repository_root = Path(acceptance_cli_module.__file__).resolve().parent.parent
    workspace = repository_root / locator
    lock = workspace.parent / f"{workspace.name}.lock"

    def fail_cleanup(_workspace: Path, _lock: Path) -> str:
        return "cleanup_os_error"

    monkeypatch.setattr(acceptance_cli_module, "_cleanup_fixture_runtime", fail_cleanup)
    try:
        with pytest.raises(OSError, match="fixture cleanup failed"):
            acceptance_cli_module._verify_fixture(_FIXTURE_ROOT)
    finally:
        if workspace.exists():
            shutil.rmtree(workspace)
        if lock.exists():
            shutil.rmtree(lock)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("failure_index", "expected_phase"),
    [
        (0, "download"),
        (1, "download"),
        (2, "download"),
        (3, "price-snapshot-import"),
        (4, "process"),
        (5, "write-preflight"),
        (6, "write"),
        (7, "validations"),
        (8, "validations"),
        (9, "validations"),
        (10, "validations"),
        (11, "validations"),
        (12, "verify"),
    ],
)
def test_slice2_runner_nonzero_stops_at_every_exact_allowed_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_index: int,
    expected_phase: str,
) -> None:
    """验证每条 planned 命令 nonzero 后都不启动下一命令或 terminal。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。
        failure_index: 注入 nonzero 的 flattened planned argv 下标。
        expected_phase: 首停阶段。

    Returns:
        无。

    Raises:
        AssertionError: runner 越过失败前缀或泄漏 stderr 原文时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    outcomes = (*((0,) * failure_index), 7)
    factory = _FakeProcessFactory(outcomes)
    services = RunServices(
        runtime=prepare_services.runtime,
        environment=prepare_services.environment,
        repository_state=prepare_services.repository_state,
        clock=prepare_services.clock,
        process_factory=factory,
    )
    result = run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        services,
    )
    assert not result.succeeded
    assert result.stop_phase == expected_phase
    assert len(factory.calls) == failure_index + 1
    assert result.stop_reason == "command_failed_with_stderr"
    receipt_bytes = b"".join(
        path.read_bytes() for path in (Path(prepared.plan.run_root) / "phase-receipts").glob("*.json")
    )
    assert b"sk-abcdefghijklmnopqrstuvwxyz" not in receipt_bytes
    terminal_receipt = Path(prepared.plan.run_root) / "phase-receipts/verify.json"
    assert terminal_receipt.exists() is (failure_index == 12)


@pytest.mark.unit
def test_slice2_runner_timeout_terminates_waits_kills_and_preserves_partial_root(tmp_path: Path) -> None:
    """验证 timeout 固定 terminate→10s→kill 且不清理 run root。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: timeout 收敛、receipt 或现场保留不符合 contract 时抛出。
    """

    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    factory = _FakeProcessFactory(("timeout",), survives_terminate=True)
    result = run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=factory,
        ),
    )
    assert not result.succeeded
    assert len(factory.calls) == 1
    assert factory.processes[0].terminated
    assert factory.processes[0].killed
    receipt = parse_phase_receipt(
        load_json_file(
            Path(prepared.plan.run_root) / "phase-receipts/download.json",
            label="timeout receipt",
        )
    )
    assert receipt.status == "timeout"
    assert receipt.command_records[-1].partial_by_timeout
    assert receipt.command_records[-1].termination_action == "kill"
    assert Path(prepared.plan.run_root).is_dir()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("outcome", "expected_status", "expected_reason"),
    [
        (-9, "signal", "process_terminated_by_signal"),
        (7, "failed", "command_failed_with_stderr"),
        ("timeout", "timeout", "whole_run_wall_clock_timeout"),
    ],
)
def test_slice2_command_exit_signal_nonzero_and_terminate_timeout_are_structured(
    tmp_path: Path,
    outcome: int | str,
    expected_status: str,
    expected_reason: str,
) -> None:
    """验证单命令 signal/nonzero/温和 timeout 全部形成固定事实。

    Args:
        tmp_path: pytest 隔离目录。
        outcome: fake 退出码或 timeout。
        expected_status: 期望 receipt 状态。
        expected_reason: 期望固定停止码。

    Returns:
        无。

    Raises:
        AssertionError: 退出分类或 timeout 动作漂移时抛出。
    """

    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    factory = _FakeProcessFactory((outcome,))
    result = acceptance_cli_module._execute_command(
        (Path(sys.executable).resolve().as_posix(), "-m", "dayu.cli", "process"),
        timeout_seconds=30.0,
        plan=prepared.plan,
        services=RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=factory,
        ),
    )
    assert result.status == expected_status
    assert result.stop_reason == expected_reason
    if outcome == "timeout":
        assert result.termination_action == "terminate"
        assert factory.processes[0].terminated
        assert not factory.processes[0].killed


@pytest.mark.unit
@pytest.mark.parametrize("drift_kind", ["environment", "head", "price", "package"])
def test_slice2_runner_rejects_preflight_drift_before_first_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_kind: str,
) -> None:
    """验证 presence/HEAD/price/package 漂移全部在首次 Popen 前失败。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。
        drift_kind: 当前注入的 drift 类别。

    Returns:
        无。

    Raises:
        AssertionError: drift 后仍创建 fake process 时抛出。
    """

    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    environment = prepare_services.environment
    repository_state = prepare_services.repository_state
    if drift_kind == "environment":
        environment = MappingEnvironmentPresenceProvider(
            {name: name != "MIMO_API_KEY" for name in REQUIRED_ENVIRONMENT_NAMES}
        )
    elif drift_kind == "head":
        repository_state = _StaticRepositoryStateProvider(
            RepositoryState(git_sha="b" * 40, dirty=False)
        )
    elif drift_kind == "price":
        price_path = Path(prepared.plan.run_root) / "inputs/price-snapshot.material.md"
        price_path.write_bytes(price_path.read_bytes() + b"drift")
    else:

        def fail_package(_expected: PackageInputFingerprints) -> None:
            raise FingerprintDriftError("package drift")

        monkeypatch.setattr(acceptance_cli_module, "assert_package_input_fingerprints", fail_package)
    factory = _FakeProcessFactory((0,) * 13)
    with pytest.raises((ContractError, FingerprintDriftError), match="drift"):
        run_acceptance(
            RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
            RunServices(
                runtime=prepare_services.runtime,
                environment=environment,
                repository_state=repository_state,
                clock=prepare_services.clock,
                process_factory=factory,
            ),
        )
    assert factory.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["digest", "skip", "unknown"])
def test_slice2_verify_receipt_prefix_rejects_tamper_skip_and_unknown_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    """验证 verify 对 digest mismatch、skip/reorder 与计划外 receipt fail closed。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。
        mutation: receipt 变异类型。

    Returns:
        无。

    Raises:
        AssertionError: receipt 前缀变异未被拒绝时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    factory = _FakeProcessFactory((0,) * 13)
    run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=factory,
        ),
    )
    receipt_root = Path(prepared.plan.run_root) / "phase-receipts"
    if mutation == "digest":
        path = receipt_root / "process.json"
        payload = load_json_file(path, label="process receipt")
        records = payload["command_records"]
        assert isinstance(records, list)
        first_record = records[0]
        assert isinstance(first_record, dict)
        first_record["argv_digest"] = "f" * 64
        path.write_bytes(canonical_json_bytes(payload))
    elif mutation == "skip":
        (receipt_root / "process.json").unlink()
    else:
        (receipt_root / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ContractError):
        acceptance_cli_module._load_and_validate_receipt_prefix(prepared.plan, prepared.fingerprint)


@pytest.mark.unit
def test_slice2_material_owner_date_uses_report_date_without_filing_fallback() -> None:
    """验证 material 严格用 report_date，filing 仍严格要求 filing_date。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: source-kind 日期语义被全局 fallback 污染时抛出。
    """

    material = acceptance_evaluator_module._source_document_from_owner(
        document_id=_PRICE_MATERIAL_DOCUMENT_ID,
        source_kind=SourceKind.MATERIAL,
        source_meta={
            "document_id": _PRICE_MATERIAL_DOCUMENT_ID,
            "form_type": "MATERIAL_OTHER",
            "report_date": "2025-01-15",
            "ingest_complete": True,
        },
        processed_meta=None,
        primary_sha256="a" * 64,
    )
    assert material.filing_date == material.report_date == date(2025, 1, 15)
    with pytest.raises(ContractError, match="filing_date"):
        acceptance_evaluator_module._source_document_from_owner(
            document_id="fil_0000320193-24-000123",
            source_kind=SourceKind.FILING,
            source_meta={
                "document_id": "fil_0000320193-24-000123",
                "form_type": "10-K",
                "report_date": "2024-09-30",
                "ingest_complete": True,
            },
            processed_meta=None,
            primary_sha256="b" * 64,
        )


@pytest.mark.unit
def test_slice2_repository_contract_error_writes_truthful_failed_process_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 process repository ContractError 不越过 failed record/receipt。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: repository closure 故障注入器。

    Returns:
        无。

    Raises:
        AssertionError: evidence、streams、digests 或 receipt 丢失时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)

    def reject_repository(_plan: AcceptancePlan, _evidence: ProcessCommandEvidence) -> str | None:
        """注入严格 repository ingress failure。

        Args:
            _plan: 当前 plan。
            _evidence: 已解析 process evidence。

        Returns:
            不返回正常值。

        Raises:
            ContractError: 固定注入仓储 contract failure。
        """

        raise ContractError("repository meta missing report date")

    monkeypatch.setattr(acceptance_cli_module, "_process_repository_stop_reason", reject_repository)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    result = run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=_FakeProcessFactory((0,) * 5),
        ),
    )
    assert result.stop_phase == "process"
    assert result.stop_reason == "owner_semantic_contract_reject"
    receipt = parse_phase_receipt(
        load_json_file(Path(prepared.plan.run_root) / "phase-receipts/process.json", label="process failed receipt")
    )
    record = receipt.command_records[0]
    assert record.status == "failed"
    assert record.exit_code == 0
    assert record.stop_reason == "owner_semantic_contract_reject"
    assert isinstance(record.evidence, ProcessCommandEvidence)
    process_stdout = _fake_owner_stdout(prepared.plan.phase_specs[2].commands[0])
    assert record.stdout_sha256 == hashlib.sha256(process_stdout).hexdigest()
    assert record.stderr_sha256 == hashlib.sha256(b"").hexdigest()


@pytest.mark.unit
@pytest.mark.parametrize(
    "mutation",
    ["process_null", "cross_type", "cancelled", "failed_summary", "wrong_window", "wrong_forms", "non_domain"],
)
def test_slice2_persisted_phase_evidence_tamper_is_rejected_without_inventory_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    """验证 canonical v3 evidence tamper 在纯 reload boundary fail closed。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: deterministic repository closure 注入器。
        mutation: 当前 phase/domain tamper 类型。

    Returns:
        无。

    Raises:
        AssertionError: tamper 被接受或 loader 写 source inventory 时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=_FakeProcessFactory((0,) * 13),
        ),
    )
    receipt_root = Path(prepared.plan.run_root) / "phase-receipts"
    download_path = receipt_root / "download.json"
    process_path = receipt_root / "process.json"
    target_path = process_path if mutation == "process_null" else download_path
    if mutation == "non_domain":
        target_path = receipt_root / "write.json"
    target = load_json_file(target_path, label="target receipt")
    process = load_json_file(process_path, label="process receipt")
    target_records = target["command_records"]
    process_records = process["command_records"]
    assert isinstance(target_records, list) and isinstance(process_records, list)
    target_record = target_records[0]
    process_record = process_records[0]
    assert isinstance(target_record, dict) and isinstance(process_record, dict)
    if mutation == "process_null":
        target_record["evidence"] = None
    elif mutation in {"cross_type", "non_domain"}:
        target_record["evidence"] = process_record["evidence"]
    else:
        evidence = target_record["evidence"]
        assert isinstance(evidence, dict)
        if mutation == "cancelled":
            evidence["owner_status"] = "cancelled"
        elif mutation == "failed_summary":
            summary = evidence["summary"]
            rows = evidence["rows"]
            assert isinstance(summary, dict) and isinstance(rows, list)
            summary["downloaded"] = 0
            summary["failed"] = 1
            first_row = rows[0]
            assert isinstance(first_row, dict)
            first_row["section_status"] = "failed"
        elif mutation == "wrong_window":
            evidence["start"] = "2020-01-01"
        else:
            evidence["planned_forms"] = ["10Q"]
            evidence["canonical_forms"] = ["10-Q"]
    target_path.write_bytes(canonical_json_bytes(target))
    with pytest.raises(ContractError):
        acceptance_cli_module._load_and_validate_receipt_prefix(prepared.plan, prepared.fingerprint)
    assert not (Path(prepared.plan.run_root) / "source-inventory.json").exists()


@pytest.mark.unit
@pytest.mark.parametrize("domain", ["material", "process"])
def test_slice2_persisted_domain_evidence_rechecks_current_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    domain: str,
) -> None:
    """验证 persisted material/process evidence 不能替代当前 repository truth。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: repository drift 注入器。
        domain: material 或 process。

    Returns:
        无。

    Raises:
        AssertionError: 当前仓储 drift 未被 reload gate 拒绝时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=_FakeProcessFactory((0,) * 13),
        ),
    )
    if domain == "material":
        def drift_material_repository(_plan: AcceptancePlan) -> tuple[str, date, str]:
            """返回 primary SHA drift 的当前 material repository facts。

            Args:
                _plan: 当前 plan。

            Returns:
                source fingerprint、report date 与故意漂移的 primary SHA。

            Raises:
                本函数不显式抛出异常。
            """

            return "d" * 64, date(2025, 1, 15), "e" * 64

        monkeypatch.setattr(
            acceptance_cli_module,
            "_price_material_repository_facts",
            drift_material_repository,
        )
    else:
        def reject_processed_repository(
            _plan: AcceptancePlan,
            _evidence: ProcessCommandEvidence,
        ) -> str | None:
            """返回固定 processed repository semantic drift。

            Args:
                _plan: 当前 plan。
                _evidence: persisted process evidence。

            Returns:
                固定 repository incomplete stop reason。

            Raises:
                本函数不显式抛出异常。
            """

            return "process_repository_state_incomplete"

        monkeypatch.setattr(
            acceptance_cli_module,
            "_process_repository_stop_reason",
            reject_processed_repository,
        )
    with pytest.raises(ContractError):
        acceptance_cli_module._load_and_validate_receipt_prefix(prepared.plan, prepared.fingerprint)
    assert not (Path(prepared.plan.run_root) / "source-inventory.json").exists()


@pytest.mark.unit
@pytest.mark.parametrize("field_name", ["price_json_sha256", "price_material_sha256"])
def test_slice2_persisted_material_plan_hash_tamper_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
) -> None:
    """验证 material evidence 的两项 plan-owned price SHA 不可 canonical 篡改。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: deterministic repository closure 注入器。
        field_name: 当前篡改 JSON 或 Markdown SHA 字段。

    Returns:
        无。

    Raises:
        AssertionError: 独立 SHA tamper 未被 persisted loader 拒绝时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=_FakeProcessFactory((0,) * 13),
        ),
    )
    receipt_path = Path(prepared.plan.run_root) / "phase-receipts/price-snapshot-import.json"
    payload = load_json_file(receipt_path, label="material receipt")
    records = payload["command_records"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    evidence = record["evidence"]
    assert isinstance(evidence, dict)
    evidence[field_name] = "e" * 64
    receipt_path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(ContractError, match="material persisted evidence"):
        acceptance_cli_module._load_and_validate_receipt_prefix(prepared.plan, prepared.fingerprint)


@pytest.mark.unit
@pytest.mark.parametrize("terminal_status", ["failed", "signal", "timeout"])
def test_slice2_persisted_nonpassed_terminal_is_rejected_without_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: str,
) -> None:
    """验证 failed/signal/timeout terminal 不能被独立 verify 提升或覆盖 receipt。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: deterministic repository closure 注入器。
        terminal_status: 当前 canonical terminal 停止态。

    Returns:
        无。

    Raises:
        AssertionError: non-passed terminal 被 loader 接受或触发 resume 时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=_FakeProcessFactory((0,) * 13),
        ),
    )
    terminal_path = Path(prepared.plan.run_root) / "phase-receipts/verify.json"
    payload = load_json_file(terminal_path, label="terminal receipt")
    records = payload["command_records"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    payload["status"] = terminal_status
    record["status"] = terminal_status
    record["stop_reason"] = f"terminal_{terminal_status}"
    if terminal_status == "failed":
        record["exit_code"] = 7
    elif terminal_status == "signal":
        record["exit_code"] = -9
    else:
        record["exit_code"] = -9
        record["termination_action"] = "kill"
        record["partial_by_timeout"] = True
    terminal_path.write_bytes(canonical_json_bytes(payload))
    acceptance_path = Path(prepared.plan.run_root) / "acceptance-receipt.json"
    sentinel = b"no-resume-terminal-failure"
    acceptance_path.write_bytes(sentinel)
    request = VerifyRequest(
        mode="live",
        fixture_root=None,
        plan_path=prepared.plan_path,
        fingerprint=prepared.fingerprint,
    )
    with pytest.raises(ContractError, match="terminal"):
        verify_acceptance(request, clock=prepare_services.clock)
    assert acceptance_path.read_bytes() == sentinel


@pytest.mark.unit
@pytest.mark.parametrize("phase_name", ["verify", "write", "validations"])
@pytest.mark.parametrize("null_shape", ["both", "stdout", "stderr"])
def test_slice2_started_passed_receipt_requires_both_stream_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase_name: str,
    null_shape: str,
) -> None:
    """验证 terminal/write/validation 的已启动 passed record 不可删除 stream SHA。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: deterministic repository closure 注入器。
        phase_name: 当前篡改 phase receipt。
        null_shape: 双 null、仅 stdout null 或仅 stderr null。

    Returns:
        无。

    Raises:
        AssertionError: canonical stream SHA tamper 未被共享 contract 拒绝时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=_FakeProcessFactory((0,) * 13),
        ),
    )
    receipt_path = Path(prepared.plan.run_root) / "phase-receipts" / f"{phase_name}.json"
    payload = load_json_file(receipt_path, label=f"{phase_name} receipt")
    records = payload["command_records"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    if null_shape in {"both", "stdout"}:
        record["stdout_sha256"] = None
    if null_shape in {"both", "stderr"}:
        record["stderr_sha256"] = None
    receipt_path.write_bytes(canonical_json_bytes(payload))
    with pytest.raises(ContractError, match="stdout/stderr SHA"):
        acceptance_cli_module._load_and_validate_receipt_prefix(prepared.plan, prepared.fingerprint)


@pytest.mark.unit
def test_slice2_process_start_failure_keeps_legal_double_null_stream_representation() -> None:
    """验证明确 process_start_failed 仍合法使用双 null stream SHA。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 合法 start-failure round-trip 或严格 null 规则漂移时抛出。
    """

    started_at = datetime(2025, 2, 1, tzinfo=UTC)
    record = CommandRecord(
        command_index=0,
        safe_argv=("<PYTHON>", "-m", "dayu.cli", "process"),
        argv_digest="a" * 64,
        status="failed",
        started_at=started_at,
        ended_at=started_at,
        duration_seconds=0.0,
        exit_code=None,
        stop_reason="process_start_failed",
        termination_action=None,
        partial_by_timeout=False,
        stdout_sha256=None,
        stderr_sha256=None,
        stdout_summary=None,
        stderr_summary=None,
        evidence=None,
    )
    receipt = PhaseReceipt(
        plan_fingerprint="b" * 64,
        phase_name="process",
        status="failed",
        started_at=started_at,
        ended_at=started_at,
        duration_seconds=0.0,
        remaining_wall_seconds=3600.0,
        command_records=(record,),
    )
    assert parse_phase_receipt(receipt.to_json()) == receipt
    with pytest.raises(ContractError, match="同时为 null"):
        replace(
            record,
            stdout_sha256=hashlib.sha256(b"").hexdigest(),
            stderr_sha256=hashlib.sha256(b"").hexdigest(),
        )


@pytest.mark.unit
@pytest.mark.parametrize("termination", ["terminate", "kill", "unconfirmed"])
def test_slice2_timeout_receipt_preserves_partial_or_cumulative_streams(
    tmp_path: Path,
    termination: str,
) -> None:
    """验证 timeout terminate/kill/unconfirmed 均保留可取得 stream bytes。

    Args:
        tmp_path: pytest 隔离目录。
        termination: 期望终止收口分支。

    Returns:
        无。

    Raises:
        AssertionError: cumulative 选择、digest 或静态脱敏漂移时抛出。
    """

    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    partial_stdout = b"partial stdout"
    partial_stderr = b"Authorization: Bearer timeout-partial-secret"
    complete_stdout = b"partial stdout complete"
    complete_stderr = b"Cookie: timeout-complete-secret"
    factory = _FakeProcessFactory(
        ("timeout",),
        survives_terminate=termination == "kill",
        terminate_raises=termination == "unconfirmed",
        timeout_partial_stdout=partial_stdout,
        timeout_partial_stderr=partial_stderr,
        timeout_drained_stdout=complete_stdout,
        timeout_drained_stderr=complete_stderr,
    )
    run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=factory,
        ),
    )
    receipt_path = Path(prepared.plan.run_root) / "phase-receipts/download.json"
    receipt = parse_phase_receipt(load_json_file(receipt_path, label="partial timeout receipt"))
    record = receipt.command_records[0]
    expected_stdout = partial_stdout if termination == "unconfirmed" else complete_stdout
    expected_stderr = partial_stderr if termination == "unconfirmed" else complete_stderr
    expected_action = "termination_unconfirmed" if termination == "unconfirmed" else termination
    assert record.termination_action == expected_action
    assert record.stdout_sha256 == hashlib.sha256(expected_stdout).hexdigest()
    assert record.stderr_sha256 == hashlib.sha256(expected_stderr).hexdigest()
    raw = receipt_path.read_bytes()
    assert b"timeout-partial-secret" not in raw
    assert b"timeout-complete-secret" not in raw
    assert record.stderr_summary is not None
    assert record.stderr_summary.startswith("category=stderr_present line=0")


@pytest.mark.unit
def test_slice2_static_stream_sanitizer_covers_receipt_and_cli_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 stderr/prefix/structure reject 与 CLI 均在落盘前静态脱敏。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: CLI exception 注入器。
        capsys: CLI stderr 捕获器。

    Returns:
        无。

    Raises:
        AssertionError: 任一原始 header/assignment/provider/path 泄漏时抛出。
    """

    secrets = (
        "bearer-secret-value",
        "cookie-secret-value",
        "proxy-secret-value",
        "x-api-secret-value",
        "assignment-secret-value",
        "password-secret-value",
        "sk-abcdefghijklmnopqrstuvwxyz",
        "AIzaabcdefghijklmnopqrstuvwxyz123456",
        "/Users/private-user/provider/body.json",
    )
    stderr = (
        "Authorization: Bearer bearer-secret-value\n"
        "Proxy-Authorization: Basic proxy-secret-value\n"
        "Cookie: sid=cookie-secret-value\n"
        "Set-Cookie: sid=cookie-secret-value\n"
        "X-API-Key: x-api-secret-value\n"
        "MIMO_API_KEY=assignment-secret-value PASSWORD=password-secret-value\n"
        "sk-abcdefghijklmnopqrstuvwxyz AIzaabcdefghijklmnopqrstuvwxyz123456\n"
        "/Users/private-user/provider/body.json"
    ).encode()
    sanitized_stream = acceptance_cli_module._redact_cli_text(stderr.decode())
    assert all(secret not in sanitized_stream for secret in secrets)
    prepared, prepare_services = _prepare_slice2_run(tmp_path / "stderr")
    run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=_FakeProcessFactory((7,), stderr_overrides=(stderr,)),
        ),
    )
    stderr_receipt = Path(prepared.plan.run_root) / "phase-receipts/download.json"

    prefixed, prefix_services = _prepare_slice2_run(tmp_path / "prefix")
    prefix_stdout = b"Cookie: sid=cookie-secret-value\n" + _real_download_stdout()
    run_acceptance(
        RunRequest(plan_path=prefixed.plan_path, fingerprint=prefixed.fingerprint),
        RunServices(
            runtime=prefix_services.runtime,
            environment=prefix_services.environment,
            repository_state=prefix_services.repository_state,
            clock=prefix_services.clock,
            process_factory=_FakeProcessFactory((0, 7), stdout_overrides=(prefix_stdout, None)),
        ),
    )
    prefix_receipt = Path(prefixed.plan.run_root) / "phase-receipts/download.json"

    rejected, reject_services = _prepare_slice2_run(tmp_path / "reject")
    reject_stdout = _real_download_stdout().replace(
        b"filing_date=2025-01-30",
        b"filing_date=X-API-Key: x-api-secret-value",
        1,
    )
    run_acceptance(
        RunRequest(plan_path=rejected.plan_path, fingerprint=rejected.fingerprint),
        RunServices(
            runtime=reject_services.runtime,
            environment=reject_services.environment,
            repository_state=reject_services.repository_state,
            clock=reject_services.clock,
            process_factory=_FakeProcessFactory((0,), stdout_overrides=(reject_stdout,)),
        ),
    )
    reject_receipt = Path(rejected.plan.run_root) / "phase-receipts/download.json"
    combined = stderr_receipt.read_bytes() + prefix_receipt.read_bytes() + reject_receipt.read_bytes()
    assert all(secret.encode() not in combined for secret in secrets)
    assert b"category=stderr_present" in combined
    assert b"category=prefix_noise" in combined
    assert b"category=structure_reject" in combined

    def reject_cli(_argv: tuple[str, ...] | None = None) -> PrepareCliCommand:
        """注入含静态 secret header 的 CLI ContractError。

        Args:
            _argv: 未使用 CLI argv。

        Returns:
            不返回命令。

        Raises:
            ContractError: 固定含敏感形状错误。
        """

        raise ContractError("Authorization: Bearer bearer-secret-value")

    monkeypatch.setattr(acceptance_cli_module, "parse_cli_arguments", reject_cli)
    assert acceptance_cli_module.main(()) == 2
    captured = capsys.readouterr()
    assert "bearer-secret-value" not in captured.err
    assert REDACTED_SECRET in captured.err


@pytest.mark.unit
@pytest.mark.parametrize(
    "secret_line",
    [
        "Authorization = Bearer review-secret-value-123",
        "Cookie=session=review-secret-value-123",
        "api-key = review-secret-value-123",
    ],
)
@pytest.mark.parametrize("ingress", ["stderr", "prefix", "structure_reject", "cli"])
def test_slice2_evaluator_equivalent_secret_variants_never_persist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    secret_line: str,
    ingress: str,
) -> None:
    """参数化验证等号/连字符敏感形状在四个输出入口均先脱敏。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: CLI exception 注入器。
        capsys: CLI stderr 捕获器。
        secret_line: evaluator 已识别的静态敏感形状。
        ingress: stderr、prefix、structure reject 或 CLI。

    Returns:
        无。

    Raises:
        AssertionError: 原始 secret value 进入 canonical receipt 或 CLI 输出时抛出。
    """

    secret_value = "review-secret-value-123"
    if ingress == "cli":
        def reject_cli(_argv: tuple[str, ...] | None = None) -> PrepareCliCommand:
            """把当前敏感形状注入 CLI ContractError。

            Args:
                _argv: 未使用 CLI argv。

            Returns:
                不返回命令。

            Raises:
                ContractError: 当前参数化敏感文本。
            """

            raise ContractError(secret_line)

        monkeypatch.setattr(acceptance_cli_module, "parse_cli_arguments", reject_cli)
        assert acceptance_cli_module.main(()) == 2
        captured = capsys.readouterr()
        assert secret_value not in captured.err
        assert REDACTED_SECRET in captured.err
        return

    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    category = ingress
    if ingress == "stderr":
        factory = _FakeProcessFactory((7,), stderr_overrides=(secret_line.encode(),))
        category = "stderr_present"
    elif ingress == "prefix":
        prefixed = f"{secret_line}\n".encode() + _real_download_stdout()
        factory = _FakeProcessFactory((0, 7), stdout_overrides=(prefixed, None))
        category = "prefix_noise"
    else:
        rejected = _real_download_stdout().replace(
            b"filing_date=2025-01-30",
            f"filing_date={secret_line}".encode(),
            1,
        )
        factory = _FakeProcessFactory((0,), stdout_overrides=(rejected,))
    run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=factory,
        ),
    )
    receipt_path = Path(prepared.plan.run_root) / "phase-receipts/download.json"
    receipt_bytes = receipt_path.read_bytes()
    assert secret_value.encode() not in receipt_bytes
    assert f"category={category}".encode() in receipt_bytes


@pytest.mark.unit
def test_slice2_popen_start_time_is_deducted_from_communicate_deadline(tmp_path: Path) -> None:
    """验证 Popen.start 的慢启动耗时从同一 monotonic deadline 扣除。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: communicate 仍收到启动前完整预算时抛出。
    """

    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    clock = _AdvancingClock(datetime(2025, 2, 1, tzinfo=UTC), 100.0)
    factory = _FakeProcessFactory(
        (0,),
        start_clock=clock,
        start_delay_seconds=29.0,
    )
    result = acceptance_cli_module._execute_command(
        (Path(sys.executable).resolve().as_posix(), "-m", "dayu.cli", "process"),
        timeout_seconds=30.0,
        plan=prepared.plan,
        services=RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=clock,
            process_factory=factory,
        ),
    )
    assert result.status == "passed"
    assert factory.processes[0].last_communicate_timeout == pytest.approx(1.0)


@pytest.mark.unit
def test_slice2_runtime_evidence_includes_persisted_terminal_without_current_clock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 original run wall 使用 persisted terminal，而非独立 verify 当前时间。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: deterministic repository closure 注入器。

    Returns:
        无。

    Raises:
        AssertionError: terminal 未进入 runtime receipts/actual wall 时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=_FakeProcessFactory((0,) * 13),
        ),
    )
    receipts = acceptance_cli_module._load_and_validate_receipt_prefix(prepared.plan, prepared.fingerprint)
    assert receipts[-1].phase_name == "verify"
    terminal_end = receipts[0].started_at + timedelta(seconds=125)
    terminal = replace(
        receipts[-1],
        started_at=receipts[-2].ended_at,
        ended_at=terminal_end,
        duration_seconds=125.0,
    )
    runtime = acceptance_cli_module._build_runtime_evidence(prepared.plan, (*receipts[:-1], terminal))
    assert runtime.phase_receipts[-1].phase_name == "verify"
    assert runtime.actual_wall_seconds == 125.0


@pytest.mark.unit
def test_slice2_git_object_id_uses_contracts_single_truth_for_sha1_and_sha256() -> None:
    """验证 CLI 直接复用 contracts 唯一 Git object-id pattern。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: pattern 复制或 40/64 小写行为漂移时抛出。
    """

    assert acceptance_cli_module.GIT_OBJECT_ID_PATTERN is acceptance_contracts_module.GIT_OBJECT_ID_PATTERN
    assert acceptance_contracts_module.GIT_OBJECT_ID_PATTERN.fullmatch("a" * 40) is not None
    assert acceptance_contracts_module.GIT_OBJECT_ID_PATTERN.fullmatch("b" * 64) is not None
    assert acceptance_contracts_module.GIT_OBJECT_ID_PATTERN.fullmatch("A" * 40) is None
    assert acceptance_contracts_module.GIT_OBJECT_ID_PATTERN.fullmatch("c" * 39) is None
    assert acceptance_contracts_module.GIT_OBJECT_ID_PATTERN.fullmatch("d" * 65) is None


@pytest.mark.unit
def test_slice2_live_verify_binds_plan_receipts_and_atomically_replaces_repeat_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 live verify 绑定完整前缀并允许同 fixed clock 重复原子替换 receipt。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。

    Returns:
        无。

    Raises:
        AssertionError: live mode、receipt 原子替换或重复字节稳定性失效时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=_FakeProcessFactory((0,) * 13),
        ),
    )
    evaluated_at = datetime(2025, 2, 1, 1, 0, tzinfo=UTC)
    expected = EvaluationResult(
        verdict="PENDING_MANUAL_REVIEW",
        total_score=None,
        dimension_scores=(),
        hard_gates=(),
        findings=(),
        artifacts=(),
        residuals=("manual_quality_review_required",),
        evaluated_at=evaluated_at,
    )

    def fake_live_evaluation(
        _plan: AcceptancePlan,
        _receipts: tuple[PhaseReceipt, ...],
        *,
        clock: _FixedClock,
    ) -> EvaluationResult:
        del clock
        return expected

    monkeypatch.setattr(acceptance_cli_module, "_evaluate_live_plan", fake_live_evaluation)
    request = VerifyRequest(
        mode="live",
        fixture_root=None,
        plan_path=prepared.plan_path,
        fingerprint=prepared.fingerprint,
    )
    first = verify_acceptance(request, clock=prepare_services.clock)
    receipt_path = Path(prepared.plan.run_root) / "acceptance-receipt.json"
    first_bytes = receipt_path.read_bytes()
    second = verify_acceptance(request, clock=prepare_services.clock)
    assert first == expected.to_json()
    assert second == first
    assert receipt_path.read_bytes() == first_bytes == expected.canonical_bytes()


@pytest.mark.unit
def test_slice2_main_fixture_emits_json_and_runtime_adapters_are_bounded(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """覆盖真实 CLI fixture dispatch 与最小 runtime/process adapters。

    Args:
        tmp_path: pytest 隔离目录。
        capsys: pytest stdout/stderr 捕获器。

    Returns:
        无。

    Raises:
        AssertionError: CLI 退出码、输出或 adapter 边界漂移时抛出。
    """

    assert acceptance_cli_module.main(("verify", "--fixture", str(_FIXTURE_ROOT), "--json")) == 0
    captured = capsys.readouterr()
    assert '"verdict":"PASS"' in captured.out
    assert captured.err == ""
    runtime = acceptance_cli_module.default_runtime_identity()
    assert runtime.repository_root == Path(acceptance_cli_module.__file__).resolve().parent.parent
    clock = acceptance_cli_module.SystemClock()
    assert clock.utc_now().utcoffset() == timedelta(0)
    assert clock.monotonic() > 0
    child_script = (
        "import os,sys;"
        "values=[os.getcwd(),str(len(sys.stdin.buffer.read())),"
        "os.environ['TQDM_DISABLE'],os.environ['HF_HUB_DISABLE_PROGRESS_BARS'],"
        "os.environ['TRANSFORMERS_VERBOSITY']];"
        "sys.stdout.buffer.write('|'.join(values).encode())"
    )
    process = acceptance_cli_module.SubprocessFactory().start(
        (Path(sys.executable).resolve().as_posix(), "-c", child_script),
        cwd=tmp_path,
        env={name: value for name, value in SUBPROCESS_ENV_POLICY},
    )
    stdout, stderr = process.communicate(timeout=10.0)
    assert stdout.decode() == f"{tmp_path}|0|1|1|error"
    assert stderr == b""
    assert process.returncode == 0
    with pytest.raises(ContractError, match="缺少名称"):
        MappingEnvironmentPresenceProvider({}).is_present("MIMO_API_KEY")
    with pytest.raises(ContractError, match="计划外"):
        acceptance_cli_module.OsEnvironmentPresenceProvider().is_present("NOT_ALLOWED")
    assert all("json_output" not in {field.name for field in fields(command_type)} for command_type in (
        PrepareCliCommand,
        RunCliCommand,
        VerifyCliCommand,
    ))


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["prepare", "run_pass", "run_fail", "verify_pending", "verify_fail"])
def test_slice2_main_dispatches_all_static_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
) -> None:
    """验证 acceptance CLI prepare/run/verify 的固定 JSON 与 exit-code 路由。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。
        capsys: pytest stdout/stderr 捕获器。
        mode: 当前 dispatch 分支。

    Returns:
        无。

    Raises:
        AssertionError: JSON 或 exit code 与三态语义不闭合时抛出。
    """

    prepared, _prepare_services = _prepare_slice2_run(tmp_path)

    def fake_prepare(_request: PrepareRequest, _services: PrepareServices) -> PreparedAcceptance:
        return prepared

    def fake_run_pass(_request: RunRequest, _services: RunServices) -> RunResult:
        return RunResult(succeeded=True, completed_phases=("download",), stop_phase=None, stop_reason=None)

    def fake_run_fail(_request: RunRequest, _services: RunServices) -> RunResult:
        return RunResult(
            succeeded=False,
            completed_phases=("download",),
            stop_phase="process",
            stop_reason="fixed_stop",
        )

    def fake_verify_pending(_request: VerifyRequest, *, clock: acceptance_cli_module.Clock) -> JsonObject:
        del clock
        return {"verdict": "PENDING_MANUAL_REVIEW"}

    def fake_verify_fail(_request: VerifyRequest, *, clock: acceptance_cli_module.Clock) -> JsonObject:
        del clock
        return {"verdict": "FAIL"}

    if mode == "prepare":
        monkeypatch.setattr(acceptance_cli_module, "prepare_acceptance", fake_prepare)
        argv = (
            "prepare",
            "--ticker",
            "AAPL",
            "--company",
            "Apple Inc.",
            "--template",
            "technology",
            "--as-of",
            "2025-02-01T00:00:00Z",
            "--run-root",
            str(tmp_path / "unused-run"),
            "--price-snapshot",
            str(_FIXTURE_ROOT / "price-snapshot-v1.json"),
            "--max-model-requests",
            "20",
            "--max-total-tokens",
            "200000",
            "--max-estimated-cost",
            "5",
            "--budget-currency",
            "CNY",
            "--max-wall-seconds",
            "3600",
            "--json",
        )
        expected_exit = 0
    elif mode.startswith("run"):
        monkeypatch.setattr(
            acceptance_cli_module,
            "run_acceptance",
            fake_run_pass if mode == "run_pass" else fake_run_fail,
        )
        argv = ("run", "--plan", str(prepared.plan_path), "--fingerprint", prepared.fingerprint, "--json")
        expected_exit = 0 if mode == "run_pass" else 1
    else:
        monkeypatch.setattr(
            acceptance_cli_module,
            "verify_acceptance",
            fake_verify_pending if mode == "verify_pending" else fake_verify_fail,
        )
        argv = ("verify", "--fixture", str(_FIXTURE_ROOT), "--json")
        expected_exit = 3 if mode == "verify_pending" else 1
    assert acceptance_cli_module.main(argv) == expected_exit
    captured = capsys.readouterr()
    assert captured.out.endswith("\n")
    assert captured.err == ""


@pytest.mark.unit
def test_slice2_main_unexpected_exception_is_static_and_secret_free(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 unexpected exception 只输出静态类型且无 traceback/secret value。

    Args:
        monkeypatch: pytest 属性替换器。
        capsys: pytest stdout/stderr 捕获器。

    Returns:
        无。

    Raises:
        AssertionError: 异常原文、secret 或 traceback 被输出时抛出。
    """

    def fail_parse(_argv: tuple[str, ...]) -> acceptance_cli_module.ParsedCliCommand:
        raise RuntimeError("sk-abcdefghijklmnopqrstuvwxyz")

    monkeypatch.setattr(acceptance_cli_module, "parse_cli_arguments", fail_parse)
    assert acceptance_cli_module.main(("verify", "--json")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unexpected RuntimeError" in captured.err
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.unit
def test_slice2_main_contract_error_is_nonzero_and_secret_redacted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 main 的 contract 错误不向 stdout 泄漏 secret-shaped 参数。

    Args:
        capsys: pytest stdout/stderr 捕获器。

    Returns:
        无。

    Raises:
        AssertionError: 错误码或脱敏边界失效时抛出。
    """

    missing = _FIXTURE_ROOT / "sk-abcdefghijklmnopqrstuvwxyz"
    assert acceptance_cli_module.main(("verify", "--fixture", str(missing), "--json")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in captured.err
    assert "fixture_root 无法解析" in captured.err


@pytest.mark.unit
def test_slice2_main_dispatches_prepare_run_and_pending_verify_without_live_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """用注入 handler 覆盖 main 三分支而不执行任何 live 命令。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。
        capsys: pytest stdout/stderr 捕获器。

    Returns:
        无。

    Raises:
        AssertionError: dispatch、退出码或 JSON 输出不符合 contract 时抛出。
    """

    prepared, _services = _prepare_slice2_run(tmp_path)

    def fake_prepare(_request: PrepareRequest, _prepare_services: PrepareServices) -> PreparedAcceptance:
        return prepared

    monkeypatch.setattr(acceptance_cli_module, "prepare_acceptance", fake_prepare)
    prepare_args = (
        "prepare",
        "--ticker",
        "AAPL",
        "--company",
        "Apple Inc.",
        "--template",
        "technology",
        "--as-of",
        "2025-02-01T00:00:00Z",
        "--run-root",
        str(tmp_path / "unused-run"),
        "--price-snapshot",
        str(_FIXTURE_ROOT / "price-snapshot-v1.json"),
        "--max-model-requests",
        "20",
        "--max-total-tokens",
        "200000",
        "--max-estimated-cost",
        "5",
        "--budget-currency",
        "CNY",
        "--max-wall-seconds",
        "3600",
        "--json",
    )
    assert acceptance_cli_module.main(prepare_args) == 0
    assert '"status":"prepared"' in capsys.readouterr().out

    def fake_run(_request: RunRequest, _run_services: RunServices) -> acceptance_cli_module.RunResult:
        return acceptance_cli_module.RunResult(
            succeeded=False,
            completed_phases=("download",),
            stop_phase="download",
            stop_reason="command_failed",
        )

    monkeypatch.setattr(acceptance_cli_module, "run_acceptance", fake_run)
    assert acceptance_cli_module.main(
        ("run", "--plan", str(prepared.plan_path), "--fingerprint", prepared.fingerprint, "--json")
    ) == 1
    assert '"succeeded":false' in capsys.readouterr().out

    def fake_verify(_request: VerifyRequest, *, clock: acceptance_cli_module.Clock) -> JsonObject:
        del clock
        return {"verdict": "PENDING_MANUAL_REVIEW"}

    monkeypatch.setattr(acceptance_cli_module, "verify_acceptance", fake_verify)
    assert acceptance_cli_module.main(("verify", "--fixture", str(_FIXTURE_ROOT), "--json")) == 3
    assert '"verdict":"PENDING_MANUAL_REVIEW"' in capsys.readouterr().out


def _slice3_golden_command_contract(
    *,
    python_executable: str,
    run_root: str,
    package_config: str,
    plan_fingerprint: str,
) -> tuple[tuple[str, ...], ...]:
    """独立构造 accepted Slice 3 的十二条 Dayu 命令与 terminal 命令。

    Args:
        python_executable: prepare 固定的 Python 解释器绝对路径。
        run_root: prepare 固定的隔离运行根。
        package_config: resolver 返回的 package config 绝对路径。
        plan_fingerprint: 已签名 plan 的 canonical SHA-256。

    Returns:
        不依赖 production phase builder 的十三条逐 token golden argv。

    Raises:
        本函数不显式抛出异常。
    """

    prefix = (python_executable, "-m", "dayu.cli")
    data_workspace = f"{run_root}/data-workspace"
    write_root = f"{run_root}/write"
    research_root = f"{run_root}/research"
    artifact_root = f"{research_root}/assets/research_templates"
    data_suffix = ("--base", data_workspace, "--config", package_config)
    validator_suffix = ("--base", research_root, "--config", package_config)
    write_budget = (
        "--write-max-model-requests",
        "20",
        "--write-max-total-tokens",
        "200000",
        "--write-max-estimated-cost",
        "5.0",
        "--write-budget-currency",
        "CNY",
    )
    return (
        (
            *prefix,
            "download",
            "--ticker",
            "AAPL",
            "--forms",
            "10K",
            "--start",
            "2020-02-01",
            "--end",
            "2025-02-01",
            *data_suffix,
            "--quiet",
        ),
        (
            *prefix,
            "download",
            "--ticker",
            "AAPL",
            "--forms",
            "10Q",
            "--start",
            "2023-02-01",
            "--end",
            "2025-02-01",
            *data_suffix,
            "--quiet",
        ),
        (
            *prefix,
            "download",
            "--ticker",
            "AAPL",
            "--forms",
            "8K",
            "DEF14A",
            "--start",
            "2023-02-01",
            "--end",
            "2025-02-01",
            *data_suffix,
            "--quiet",
        ),
        (
            *prefix,
            "upload_material",
            "--ticker",
            "AAPL",
            "--forms",
            "MATERIAL_OTHER",
            "--material-name",
            "aapl-price-snapshot",
            "--document-id",
            "mat_cddbbff62246cd1c9ee49acbaca55d552c1093ca",
            "--files",
            f"{run_root}/inputs/price-snapshot.material.md",
            "--report-date",
            "2025-01-15",
            *data_suffix,
            "--quiet",
        ),
        (
            *prefix,
            "process",
            "--ticker",
            "AAPL",
            *data_suffix,
            "--quiet",
        ),
        (
            *prefix,
            "write",
            "--ticker",
            "AAPL",
            "--model-name",
            "deepseek-v4-pro",
            "--audit-model-name",
            "mimo-v2.5-pro-thinking",
            "--research-template",
            "technology",
            "--output",
            write_root,
            "--preflight-only",
            "--no-resume",
            *write_budget,
            *data_suffix,
        ),
        (
            *prefix,
            "write",
            "--ticker",
            "AAPL",
            "--model-name",
            "deepseek-v4-pro",
            "--audit-model-name",
            "mimo-v2.5-pro-thinking",
            "--research-template",
            "technology",
            "--output",
            write_root,
            "--materialize-research",
            "--research-base",
            research_root,
            "--no-resume",
            *write_budget,
            *data_suffix,
        ),
        (
            *prefix,
            "research-template",
            "validate-research-workbook",
            "--workbook",
            f"{artifact_root}/technology.research-workbook.json",
            *validator_suffix,
        ),
        (
            *prefix,
            "research-template",
            "validate-workbook-report",
            "--report",
            f"{artifact_root}/technology.research-progress.md",
            "--workbook",
            f"{artifact_root}/technology.research-workbook.json",
            *validator_suffix,
        ),
        (
            *prefix,
            "research-template",
            "validate-source-map",
            "--rules",
            f"{artifact_root}/technology.monitoring-rules.json",
            "--source-map",
            f"{artifact_root}/technology.source-map.json",
            *validator_suffix,
        ),
        (
            *prefix,
            "research-template",
            "validate-bundle",
            "--bundle",
            f"{artifact_root}/technology.bundle.json",
            *validator_suffix,
        ),
        (
            *prefix,
            "research-template",
            "validate-monitoring-plan",
            "--plan",
            f"{artifact_root}/technology.monitoring-plan.json",
            *validator_suffix,
        ),
        (
            python_executable,
            "-m",
            "utils.investment_agent_acceptance",
            "verify",
            "--plan",
            f"{run_root}/acceptance-plan.json",
            "--fingerprint",
            plan_fingerprint,
            "--json",
        ),
    )


class _Slice3FinsService:
    """在真实 Fins parser/dispatch 之后替代外部服务执行。"""

    def __init__(self, commands: list[FinsCommand]) -> None:
        """保存真实 owner 构造出的 command。

        Args:
            commands: 跨全部 Fins 命令共享的捕获列表。

        Returns:
            无。

        Raises:
            本方法不显式抛出异常。
        """

        self._commands = commands

    def submit(self, request: FinsSubmitRequest) -> FinsSubmission:
        """返回与真实 command variant 闭合的成功流。

        Args:
            request: 真实 ``run_fins_command`` 构造的提交请求。

        Returns:
            仅替代外部仓储/网络执行的 typed 提交句柄。

        Raises:
            AssertionError: Slice 3 golden contract 出现未知 Fins command 时抛出。
        """

        command = request.command
        self._commands.append(command)
        payload = command.payload
        if isinstance(payload, DownloadCommandPayload):
            result = DownloadResultData(
                pipeline="slice3-owner-dispatch",
                status="ok",
                ticker=payload.ticker,
                summary=OwnerDownloadSummary(total=0, downloaded=0, skipped=0, failed=0),
            )
        elif isinstance(payload, UploadMaterialCommandPayload):
            result = UploadMaterialResultData(
                pipeline="slice3-owner-dispatch",
                status="ok",
                ticker=payload.ticker,
                material_action="create",
                form_type=payload.form_type,
                material_name=payload.material_name,
                document_id=payload.document_id,
                report_date=payload.report_date,
            )
        elif isinstance(payload, ProcessCommandPayload):
            result = ProcessResultData(
                pipeline="slice3-owner-dispatch",
                status="ok",
                ticker=payload.ticker,
                filing_summary=OwnerProcessSummary(total=0, processed=0, skipped=0, failed=0),
                material_summary=OwnerProcessSummary(total=0, processed=0, skipped=0, failed=0),
            )
        else:
            raise AssertionError(f"Slice 3 出现未授权 Fins payload: {type(payload).__name__}")

        async def _events() -> collections.abc.AsyncIterator[FinsEvent]:
            yield FinsEvent(type=FinsEventType.RESULT, command=command.name, payload=result)

        return FinsSubmission(session_id="slice3-owner-dispatch", execution=_events())


@pytest.mark.unit
def test_slice3_real_parser_dispatch_locks_complete_aapl_command_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """经真实 run parser/dispatch 锁定 AAPL 全链 argv，外部执行保持 fake。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: 外部仓储、进程与运行身份替换器。
        capsys: pytest stdout/stderr 捕获器。

    Returns:
        无。

    Raises:
        AssertionError: parser、dispatch、窗口、模型、预算或隔离路径漂移时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    factory = _FakeProcessFactory((0,) * 13)
    monkeypatch.setattr(
        acceptance_cli_module,
        "default_runtime_identity",
        lambda: prepare_services.runtime,
    )
    monkeypatch.setattr(
        acceptance_cli_module,
        "OsEnvironmentPresenceProvider",
        lambda: prepare_services.environment,
    )
    monkeypatch.setattr(
        acceptance_cli_module,
        "GitRepositoryStateProvider",
        lambda: prepare_services.repository_state,
    )
    monkeypatch.setattr(acceptance_cli_module, "SystemClock", lambda: prepare_services.clock)
    monkeypatch.setattr(acceptance_cli_module, "SubprocessFactory", lambda: factory)

    exit_code = acceptance_cli_module.main(
        (
            "run",
            "--plan",
            str(prepared.plan_path),
            "--fingerprint",
            prepared.fingerprint,
            "--json",
        )
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["succeeded"] is True
    package_config = resolve_package_config_path().resolve(strict=True).as_posix()
    golden_commands = _slice3_golden_command_contract(
        python_executable=prepare_services.runtime.python_executable,
        run_root=prepared.plan.run_root,
        package_config=package_config,
        plan_fingerprint=prepared.fingerprint,
    )
    planned_commands = tuple(command for spec in prepared.plan.phase_specs for command in spec.commands)
    assert planned_commands == golden_commands[:-1]
    assert tuple(factory.calls) == golden_commands
    assert tuple(command[3] for command in golden_commands[:-1]) == (
        "download",
        "download",
        "download",
        "upload_material",
        "process",
        "write",
        "write",
        "research-template",
        "research-template",
        "research-template",
        "research-template",
        "research-template",
    )
    assert _PRICE_MATERIAL_DOCUMENT_ID == "mat_cddbbff62246cd1c9ee49acbaca55d552c1093ca"

    research_root = Path(prepared.plan.run_root) / "research"
    FsCompanyMetaRepository(Path(prepared.plan.run_root) / "data-workspace").upsert_company_meta(
        CompanyMeta(
            company_id="apple-inc",
            company_name="Apple Inc.",
            ticker="AAPL",
            market="US",
            resolver_version="slice3-owner-dispatch",
            updated_at="2025-02-01T00:00:00+00:00",
        )
    )
    materialize_research_workspace(
        "technology",
        workspace_root=research_root,
        ticker="AAPL",
        company="Apple Inc.",
    )
    fins_commands: list[FinsCommand] = []
    validated_writes: list[str] = []
    monkeypatch.setattr(
        "dayu.cli.commands.fins._build_fins_ops_service",
        lambda _args: _Slice3FinsService(fins_commands),
    )
    monkeypatch.setattr(
        write_command_module,
        "_WRITE_PHASE_EARLY_RECOVERY",
        (
            _EarlyWriteSubcommandEntry(
                predicate=lambda _args: True,
                runner=lambda _context: validated_writes.append("write") or 0,
            ),
        ),
    )
    for command in golden_commands[:-1]:
        monkeypatch.setattr(sys, "argv", ["dayu-cli", *command[3:]])
        assert dayu_main_module.main() == 0

    assert tuple(command.name for command in fins_commands) == (
        FinsCommandName.DOWNLOAD,
        FinsCommandName.DOWNLOAD,
        FinsCommandName.DOWNLOAD,
        FinsCommandName.UPLOAD_MATERIAL,
        FinsCommandName.PROCESS,
    )
    assert all(
        isinstance(command.payload, DownloadCommandPayload) and command.payload.ticker == "AAPL"
        for command in fins_commands[:3]
    )
    upload_payload = fins_commands[3].payload
    assert isinstance(upload_payload, UploadMaterialCommandPayload)
    assert upload_payload.form_type == "MATERIAL_OTHER"
    assert upload_payload.material_name == "aapl-price-snapshot"
    assert upload_payload.document_id == "mat_cddbbff62246cd1c9ee49acbaca55d552c1093ca"
    assert upload_payload.report_date == "2025-01-15"
    process_payload = fins_commands[4].payload
    assert isinstance(process_payload, ProcessCommandPayload)
    assert process_payload.ticker == "AAPL"
    assert validated_writes == ["write", "write"]

    invalid_preflight = (
        *golden_commands[5],
        "--materialize-research",
        "--research-base",
        research_root.as_posix(),
    )
    monkeypatch.setattr(sys, "argv", ["dayu-cli", *invalid_preflight[3:]])
    assert dayu_main_module.main() == 2
    assert validated_writes == ["write", "write"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "receipt_case",
    [
        "terminal_failed",
        "terminal_signal",
        "terminal_timeout",
        "terminal_incomplete",
        "planned_failed",
        "planned_signal",
    ],
)
def test_slice3_public_live_verify_rejects_untrusted_receipt_before_evaluator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    receipt_case: str,
) -> None:
    """证明不可信 persisted lifecycle 只经 public live verify 且前置拒绝。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: 仓储闭包与 evaluator 调用观察器。
        receipt_case: terminal 异常或完整 planned non-passed 前缀攻击类型。

    Returns:
        无。

    Raises:
        AssertionError: loader 调用 evaluator或改写任一保留现场时抛出。
    """

    _stub_runner_repository_closure(monkeypatch)
    prepared, prepare_services = _prepare_slice2_run(tmp_path)
    run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=_FakeProcessFactory((0,) * 13),
        ),
    )
    run_root = Path(prepared.plan.run_root)
    receipt_root = run_root / "phase-receipts"
    planned_nonpassed = receipt_case.startswith("planned_")
    target_path = receipt_root / ("validations.json" if planned_nonpassed else "verify.json")
    payload = load_json_file(target_path, label="slice3 untrusted receipt")
    records = payload["command_records"]
    assert isinstance(records, list) and records
    record = records[-1] if planned_nonpassed else records[0]
    assert isinstance(record, dict)
    if receipt_case == "terminal_incomplete":
        record.pop("ended_at")
    else:
        status = receipt_case.removeprefix("terminal_").removeprefix("planned_")
        payload["status"] = status
        record["status"] = status
        record["stop_reason"] = f"slice3_{status}"
        record["exit_code"] = -9 if status in {"signal", "timeout"} else 7
        if status == "timeout":
            record["termination_action"] = "kill"
            record["partial_by_timeout"] = True
    target_path.write_bytes(canonical_json_bytes(payload))
    if planned_nonpassed:
        (receipt_root / "verify.json").unlink()

    acceptance_path = run_root / "acceptance-receipt.json"
    source_inventory_path = run_root / "source-inventory.json"
    partial_artifact_path = run_root / "write/partial-output.bin"
    acceptance_path.write_bytes(b"slice3-acceptance-sentinel")
    source_inventory_path.write_bytes(b"slice3-inventory-sentinel")
    partial_artifact_path.write_bytes(b"slice3-partial-artifact")
    receipt_snapshot = tuple(
        (path.name, path.read_bytes())
        for path in sorted(receipt_root.iterdir())
        if path.is_file()
    )
    evaluator = create_autospec(acceptance_cli_module._evaluate_live_plan)
    monkeypatch.setattr(acceptance_cli_module, "_evaluate_live_plan", evaluator)

    expected_error = "live verify 要求全部 planned phase 成功" if planned_nonpassed else None
    with pytest.raises(ContractError, match=expected_error):
        verify_acceptance(
            VerifyRequest(
                mode="live",
                fixture_root=None,
                plan_path=prepared.plan_path,
                fingerprint=prepared.fingerprint,
            ),
            clock=prepare_services.clock,
        )

    assert evaluator.call_count == 0
    assert acceptance_path.read_bytes() == b"slice3-acceptance-sentinel"
    assert source_inventory_path.read_bytes() == b"slice3-inventory-sentinel"
    assert partial_artifact_path.read_bytes() == b"slice3-partial-artifact"
    assert tuple(
        (path.name, path.read_bytes())
        for path in sorted(receipt_root.iterdir())
        if path.is_file()
    ) == receipt_snapshot


@pytest.mark.unit
def test_slice3_existing_receipt_blocks_same_plan_rerun_and_requires_fresh_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """锁定 fresh-run/no-resume：旧现场只读保留，恢复需新 root/plan。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: evaluator 调用观察器。

    Returns:
        无。

    Raises:
        AssertionError: 同 plan 重跑、隐式 resume 或旧 receipt 被改写时抛出。
    """

    request, prepare_services = _slice2_prepare_inputs(tmp_path)
    prepared = prepare_acceptance(request, prepare_services)
    first_factory = _FakeProcessFactory((7,))
    first_result = run_acceptance(
        RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
        RunServices(
            runtime=prepare_services.runtime,
            environment=prepare_services.environment,
            repository_state=prepare_services.repository_state,
            clock=prepare_services.clock,
            process_factory=first_factory,
        ),
    )
    assert first_result.succeeded is False
    assert first_result.stop_phase == "download"

    writes = tuple(
        command
        for spec in prepared.plan.phase_specs
        for command in spec.commands
        if command[3] == "write"
    )
    assert len(writes) == 2
    assert all(command.count("--no-resume") == 1 for command in writes)
    assert all("--resume" not in command for command in writes)

    receipt_root = Path(prepared.plan.run_root) / "phase-receipts"
    old_receipts = tuple(
        (path.name, path.read_bytes())
        for path in sorted(receipt_root.iterdir())
        if path.is_file()
    )
    partial_path = Path(prepared.plan.run_root) / "write/partial-output.bin"
    partial_path.write_bytes(b"preserve-old-run")
    second_factory = _FakeProcessFactory((0,) * 13)
    evaluator = create_autospec(acceptance_cli_module._evaluate_live_plan)
    monkeypatch.setattr(acceptance_cli_module, "_evaluate_live_plan", evaluator)
    with pytest.raises(ContractError, match="不得覆盖已有 phase receipt"):
        run_acceptance(
            RunRequest(plan_path=prepared.plan_path, fingerprint=prepared.fingerprint),
            RunServices(
                runtime=prepare_services.runtime,
                environment=prepare_services.environment,
                repository_state=prepare_services.repository_state,
                clock=prepare_services.clock,
                process_factory=second_factory,
            ),
        )
    assert second_factory.calls == []
    assert evaluator.call_count == 0
    assert partial_path.read_bytes() == b"preserve-old-run"
    assert tuple(
        (path.name, path.read_bytes())
        for path in sorted(receipt_root.iterdir())
        if path.is_file()
    ) == old_receipts

    fresh_request = replace(request, run_root=request.run_root.with_name("run-002"))
    fresh = prepare_acceptance(fresh_request, prepare_services)
    assert fresh.fingerprint != prepared.fingerprint
    assert Path(fresh.plan.run_root) != Path(prepared.plan.run_root)
    assert {path.name for path in (Path(fresh.plan.run_root) / "phase-receipts").iterdir()} == {"prepare.json"}
    assert partial_path.read_bytes() == b"preserve-old-run"


@pytest.mark.unit
def test_slice3_unbound_technology_is_structurally_healthy_and_reported_in_final_residuals(
    tmp_path: Path,
) -> None:
    """证明 technology monitoring 可结构健康但 blocked，receipt 如实留 residual。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: owner 健康状态、blocked 事实或最终 residual 丢失时抛出。
        ContractError: 真实物化产物不再满足 evaluator ingress 时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    inspection = inputs.research_artifacts
    bundle_path = tmp_path / "assets/research_templates/technology.bundle.json"
    monitoring_plan = build_monitoring_execution_plan(bundle_path)
    owner_validation = validate_monitoring_execution_plan(monitoring_plan)
    assert owner_validation["ok"] is True
    assert inspection.monitoring_valid is True
    assert inspection.monitoring_execution_mode == "dry_run"
    assert inspection.automated_execution_allowed is False
    assert inspection.monitoring_readiness == "blocked_unbound_sources"
    assert inspection.monitoring_blocked_task_count > 0
    assert inspection.monitoring_unbound_sources

    receipt = evaluate_acceptance(inputs, evaluated_at=_FIXED_EVALUATED_AT)
    assert receipt.verdict == "PASS"
    residuals = set(receipt.residuals)
    assert "monitoring_readiness=blocked_unbound_sources" in residuals
    assert f"monitoring_blocked_task_count={inspection.monitoring_blocked_task_count}" in residuals
    assert {
        f"monitoring_unbound_source={source}" for source in inspection.monitoring_unbound_sources
    }.issubset(residuals)
