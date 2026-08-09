"""AAPL 投资 Agent 验收的离线 prepare、allowlisted runner 与只读 verify CLI。

本模块只编排已接受的固定 AAPL/technology 运行契约。它不承载评分规则，
不提供任意命令执行入口，也不在 deterministic 测试中读取真实凭据或发起外部调用。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform as platform_module
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePath
from typing import Literal, Mapping, Never, Protocol, TypeAlias

from dayu.cli.commands._research_template_materialize import materialize_research_workspace
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.docling_upload_service import build_material_ids
from dayu.fins.pipelines.sec_form_utils import normalize_form
from dayu.fins.storage.fs_document_blob_repository import FsDocumentBlobRepository
from dayu.fins.storage.fs_processed_document_repository import FsProcessedDocumentRepository
from dayu.fins.storage.fs_source_document_repository import FsSourceDocumentRepository
from dayu.redaction import REDACTED_SECRET, SECRET_KEY_PATTERN
from dayu.startup.config_file_resolver import resolve_package_config_path
from utils.investment_agent_acceptance_contracts import (
    GIT_OBJECT_ID_PATTERN,
    PLANNED_PHASE_COMMAND_COUNTS,
    REQUIRED_ENVIRONMENT_NAMES,
    REQUIRED_RESEARCH_ARTIFACTS,
    SAFE_ARGV_PLACEHOLDERS,
    SUBPROCESS_ENV_POLICY,
    TERMINAL_ACTION,
    AcceptancePlan,
    BudgetLimits,
    CommandEvidence,
    CommandRecord,
    ContractError,
    DownloadCommandEvidence,
    DownloadEvidenceRow,
    DownloadSummary,
    EnvironmentPresence,
    JsonObject,
    JsonValue,
    MaterialImportCommandEvidence,
    ModelRoles,
    PhaseReceipt,
    PhaseSpec,
    PriceSnapshot,
    ProcessCommandEvidence,
    ProcessEvidenceRow,
    ProcessSummary,
    SourceWindow,
    assert_package_input_fingerprints,
    build_package_input_fingerprints,
    canonical_json_bytes,
    canonical_json_sha256,
    format_utc,
    load_json_file,
    parse_acceptance_plan,
    parse_json_bytes,
    parse_owner_run_summary,
    parse_owner_write_manifest,
    parse_phase_receipt,
    parse_price_snapshot,
    parse_quality_review,
    parse_source_inventory,
)
from utils.investment_agent_acceptance_evaluator import (
    AcceptanceInputs,
    EvaluationResult,
    FixtureInputRequest,
    RepositoryInventoryRequest,
    RuntimeEvidence,
    build_live_acceptance_contract,
    build_pending_quality_review,
    build_source_inventory_from_repositories,
    evaluate_acceptance,
    inspect_research_artifacts,
    load_fixture_inputs,
)

Command: TypeAlias = tuple[str, ...]
CommandMatrix: TypeAlias = tuple[Command, ...]
VerifyMode: TypeAlias = Literal["fixture", "live"]

_TICKER = "AAPL"
_COMPANY = "Apple Inc."
_TEMPLATE = "technology"
_PRIMARY_MODEL = "deepseek-v4-pro"
_AUDIT_MODEL = "mimo-v2.5-pro-thinking"
_TIMEZONE = "UTC"
_TERMINATION_GRACE_SECONDS = 10
_RUN_PARENT_LOCATOR = Path("workspace/acceptance/investment-agent-aapl")
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SEC_ACCESSION_PATTERN = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_WINDOW_FORMS = (("10-K",), ("10-Q",), ("8-K", "DEF 14A"))
_STREAM_SUMMARY_MAX_BYTES = 512
_STATIC_SECRET_FIELD_PATTERN = re.compile(
    r'''(?ix)
    (?<![A-Z0-9_-])
    ["']?
    (?:
        AUTHORIZATION
        | PROXY[-_]AUTHORIZATION
        | COOKIE
        | SET[-_]COOKIE
        | [A-Z0-9_-]*API[-_]?KEY
        | [A-Z0-9_-]*(?:ACCESS[-_]?TOKEN|TOKEN|SECRET)
        | [A-Z0-9_-]*PASSWORD
    )
    ["']?
    \s*[:=]\s*
    [^\r\n]*
    '''
)
_GOOGLE_API_KEY_PATTERN = re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b")
_POSIX_HOME_PATH_PATTERN = re.compile(r"/(?:Users|home)/[^/\s]+(?:/[^\s]*)?")
_WINDOWS_HOME_PATH_PATTERN = re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+(?:\\[^\s]*)?")
_DOWNLOAD_SCALAR_LINE_COUNT = 3
_DOWNLOAD_MIN_LINE_COUNT = 6
_DOWNLOAD_SECTION_COUNT = 3
_DOWNLOAD_ROW_MIN_PART_COUNT = 8
_UPLOAD_REQUIRED_LINE_COUNT = 4
_UPLOAD_MIN_LINE_COUNT = 5
_PROCESS_SCALAR_LINE_COUNT = 4
_PROCESS_MIN_LINE_COUNT = 10
_EMPTY_STREAM_SHA256 = hashlib.sha256(b"").hexdigest()
_FIXTURE_MAX_MODEL_REQUESTS = 20
_FIXTURE_MAX_TOTAL_TOKENS = 200_000
_FIXTURE_MAX_ESTIMATED_COST = Decimal("5")
_FIXTURE_BUDGET_CURRENCY = "CNY"
_FIXTURE_MAX_WALL_SECONDS = 3_600
_FIXTURE_ACTUAL_WALL_SECONDS = 120.0
_FIXTURE_EVALUATION_OFFSET = timedelta(hours=1)
_FIXTURE_RUNTIME_LOCATOR = Path("workspace/tmp/investment-agent-aapl-fixture-verify")
_VALIDATOR_ACTIONS = (
    "validate-research-workbook",
    "validate-workbook-report",
    "validate-source-map",
    "validate-bundle",
    "validate-monitoring-plan",
)
_PHASE_RECEIPT_FILES = (
    ("download", "download.json"),
    ("price-snapshot-import", "price-snapshot-import.json"),
    ("process", "process.json"),
    ("write-preflight", "write-preflight.json"),
    ("write", "write.json"),
    ("validations", "validations.json"),
)


class EnvironmentPresenceProvider(Protocol):
    """只暴露环境变量名称存在性、不暴露值的协议。

    Args:
        协议方法接收一个固定环境变量名称。

    Returns:
        名称存在时返回 ``True``。

    Raises:
        实现可在存在性查询失败时抛出运行时异常。
    """

    def is_present(self, name: str) -> bool:
        """查询一个名称是否存在。

        Args:
            name: 固定 allowlist 中的环境变量名称。

        Returns:
            名称存在时返回 ``True``。

        Raises:
            实现可在查询失败时抛出运行时异常。
        """

        ...


class RepositoryStateProvider(Protocol):
    """提供当前仓库 commit 与 dirty 状态的只读协议。

    Args:
        协议方法接收精确仓库根。

    Returns:
        不可变仓库状态。

    Raises:
        实现可在仓库不可读时抛出运行时异常。
    """

    def read(self, repository_root: Path) -> RepositoryState:
        """读取仓库状态。

        Args:
            repository_root: 精确仓库根。

        Returns:
            当前 commit 与 dirty 状态。

        Raises:
            ContractError: 仓库状态不能安全解析时抛出。
        """

        ...


class Clock(Protocol):
    """为 receipt 时间与 whole-run timeout 提供可注入时钟。

    Args:
        协议无初始化参数要求。

    Returns:
        UTC wall clock 与单调时钟。

    Raises:
        实现可在系统时钟不可用时抛出运行时异常。
    """

    def utc_now(self) -> datetime:
        """返回当前 UTC 时间。

        Args:
            无。

        Returns:
            带时区 UTC 时间。

        Raises:
            实现可在系统时钟不可用时抛出运行时异常。
        """

        ...

    def monotonic(self) -> float:
        """返回不可倒退的秒计数。

        Args:
            无。

        Returns:
            单调秒计数。

        Raises:
            实现可在系统时钟不可用时抛出运行时异常。
        """

        ...


class RunningProcess(Protocol):
    """跨平台 timeout 收敛所需的最小子进程协议。

    Args:
        协议由 ``ProcessFactory`` 创建。

    Returns:
        可通信、终止、强杀并读取退出码的进程句柄。

    Raises:
        实现按 ``subprocess`` 语义抛出 timeout 或系统异常。
    """

    @property
    def returncode(self) -> int | None:
        """返回当前退出码。

        Args:
            无。

        Returns:
            未结束时为 ``None``，否则为进程退出码。

        Raises:
            本属性不显式抛出异常。
        """

    def communicate(self, *, timeout: float) -> tuple[bytes, bytes]:
        """等待进程并收集文本输出。

        Args:
            timeout: 本次命令可用的 whole-run 剩余秒数。

        Returns:
            stdout 与 stderr 文本。

        Raises:
            subprocess.TimeoutExpired: 超过剩余时间时抛出。
        """

        ...

    def terminate(self) -> None:
        """请求跨平台温和终止。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 进程终止请求失败时抛出。
        """

        ...

    def kill(self) -> None:
        """请求跨平台强制终止。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 进程强杀请求失败时抛出。
        """

        ...

    def wait(self, *, timeout: float) -> int:
        """等待进程退出。

        Args:
            timeout: 最长等待秒数。

        Returns:
            进程退出码。

        Raises:
            subprocess.TimeoutExpired: 等待超时时抛出。
        """

        ...


class ProcessFactory(Protocol):
    """只允许 argv list、``shell=False`` 的进程创建协议。

    Args:
        协议方法接收一个不可变 argv token 元组。

    Returns:
        可由 runner 收敛的进程句柄。

    Raises:
        OSError: 进程无法创建时抛出。
    """

    def start(
        self,
        argv: Command,
        *,
        cwd: Path,
        env: Mapping[str, str],
    ) -> RunningProcess:
        """创建一个 allowlisted 子进程。

        Args:
            argv: 已由 plan 纯构造器重建并校验的 token 元组。
            cwd: 固定 resolved repository root。
            env: 已复制并应用 plan non-secret policy 的显式环境。

        Returns:
            运行中进程句柄。

        Raises:
            OSError: 进程无法创建时抛出。
        """

        ...


@dataclass(frozen=True)
class RepositoryState:
    """仓库 commit 与 dirty 状态。

    Args:
        git_sha: 当前 HEAD 的小写 SHA-256/40 位 Git object id 规范化摘要。
        dirty: 工作树是否含未提交变化。

    Returns:
        不可变仓库状态。

    Raises:
        本类不显式抛出异常。
    """

    git_sha: str
    dirty: bool


@dataclass(frozen=True)
class RuntimeIdentity:
    """测试可注入、live 默认来自当前进程的运行身份。

    Args:
        repository_root: 当前仓库根。
        python_executable: 当前 Python 可执行文件 canonical path。
        python_version: 当前 Python 版本文本。
        platform: 当前平台文本。
        timezone: 计划绑定的 IANA timezone。

    Returns:
        不可变运行身份。

    Raises:
        本类不显式抛出异常。
    """

    repository_root: Path
    python_executable: str
    python_version: str
    platform: str
    timezone: str


@dataclass(frozen=True)
class PrepareRequest:
    """离线 prepare 的显式输入。

    Args:
        声明字段: 固定目标、UTC as-of、run root、价格文件与全部预算。

    Returns:
        不可变 prepare 请求。

    Raises:
        本类不显式抛出异常。
    """

    ticker: str
    company: str
    template: str
    as_of: datetime
    run_root: Path
    price_snapshot: Path
    budget: BudgetLimits
    max_wall_seconds: int


@dataclass(frozen=True)
class PhaseBuildInputs:
    """固定 AAPL phase pure builder 的全部显式输入。

    Args:
        run_root: canonical absolute run root。
        python_executable: canonical Python 可执行文件。
        package_config_root: resolver 返回的 package config 根。
        as_of: 固定 UTC as-of。
        price_snapshot: 严格六字段价格快照。
        budget: 显式写作预算。

    Returns:
        不可变 builder 输入值。

    Raises:
        本类不显式抛出异常。
    """

    run_root: str
    python_executable: str
    package_config_root: Path
    as_of: datetime
    price_snapshot: PriceSnapshot
    budget: BudgetLimits
    price_material_document_id: str


@dataclass(frozen=True)
class RunRequest:
    """allowlisted runner 的 plan 与指纹输入。

    Args:
        plan_path: 精确 ``acceptance-plan.json`` 路径。
        fingerprint: 用户显式确认的 plan canonical SHA-256。

    Returns:
        不可变 run 请求。

    Raises:
        本类不显式抛出异常。
    """

    plan_path: Path
    fingerprint: str


@dataclass(frozen=True)
class VerifyRequest:
    """互斥 fixture/live verify 请求。

    Args:
        mode: ``fixture`` 或 ``live``。
        fixture_root: fixture 模式唯一输入目录。
        plan_path: live 模式 plan 路径。
        fingerprint: live 模式 exact plan 指纹。

    Returns:
        不可变 verify 请求。

    Raises:
        本类不显式抛出异常。
    """

    mode: VerifyMode
    fixture_root: Path | None
    plan_path: Path | None
    fingerprint: str | None


@dataclass(frozen=True)
class PrepareServices:
    """prepare 所需的可测试只读依赖。

    Args:
        runtime: 当前运行身份。
        environment: 只暴露名称存在性的 provider。
        repository_state: 只读 HEAD/dirty provider。
        clock: receipt 时钟。

    Returns:
        不可变依赖集合。

    Raises:
        本类不显式抛出异常。
    """

    runtime: RuntimeIdentity
    environment: EnvironmentPresenceProvider
    repository_state: RepositoryStateProvider
    clock: Clock


@dataclass(frozen=True)
class RunServices:
    """runner 所需的只读身份、presence、时钟与进程工厂。

    Args:
        runtime: 当前运行身份。
        environment: run 前二次检查的 presence provider。
        repository_state: run 前 HEAD/dirty provider。
        clock: receipt 与 whole-run 时钟。
        process_factory: 只接受 allowlisted argv 的进程工厂。

    Returns:
        不可变依赖集合。

    Raises:
        本类不显式抛出异常。
    """

    runtime: RuntimeIdentity
    environment: EnvironmentPresenceProvider
    repository_state: RepositoryStateProvider
    clock: Clock
    process_factory: ProcessFactory
    subprocess_environment: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PreparedAcceptance:
    """成功 prepare 后的唯一 plan 身份。

    Args:
        plan: 已原子落盘的 v2 plan。
        fingerprint: plan canonical SHA-256。
        plan_path: 正式 run root 内 plan 路径。

    Returns:
        不可变 prepare 结果。

    Raises:
        本类不显式抛出异常。
    """

    plan: AcceptancePlan
    fingerprint: str
    plan_path: Path


@dataclass(frozen=True)
class RunResult:
    """runner 的最终停止事实。

    Args:
        succeeded: 全部 phase 与 terminal verify 是否通过。
        completed_phases: 已写 receipt 的有序 phase 名称。
        stop_phase: 首个停止阶段；成功时为 ``None``。
        stop_reason: 已脱敏停止原因；成功时为 ``None``。

    Returns:
        不可变 runner 结果。

    Raises:
        本类不显式抛出异常。
    """

    succeeded: bool
    completed_phases: tuple[str, ...]
    stop_phase: str | None
    stop_reason: str | None


@dataclass(frozen=True)
class CommandResult:
    """单条命令的退出或 timeout 事实。

    Args:
        status: passed/failed/timeout/signal。
        exit_code: 可选退出码。
        stop_reason: 已脱敏停止原因。
        termination_action: timeout 收敛动作。
        partial_by_timeout: 是否因 timeout 形成部分产物。

    Returns:
        不可变命令结果。

    Raises:
        本类不显式抛出异常。
    """

    status: Literal["passed", "failed", "timeout", "signal"]
    exit_code: int | None
    stop_reason: str | None
    termination_action: Literal["not_started", "terminate", "kill", "termination_unconfirmed"] | None
    partial_by_timeout: bool
    stdout: bytes | None = None
    stderr: bytes | None = None


class _OwnerOutputError(ContractError):
    """表示 owner formatter ingress 的结构拒绝。

    Args:
        message: 静态、无 owner 原文的错误说明。
        line_number: 触发拒绝的 1-based 行号；未知时为 0。

    Returns:
        可被 phase runner 归一化为 failed record 的 contract error。

    Raises:
        本类初始化不显式抛出其它异常。
    """

    def __init__(self, message: str, *, line_number: int = 0) -> None:
        """保存结构拒绝的静态类别与行号。

        Args:
            message: 静态错误说明。
            line_number: 1-based 行号或 0。

        Returns:
            无。

        Raises:
            本方法不显式抛出异常。
        """

        super().__init__(message)
        self.line_number = line_number


@dataclass(frozen=True)
class PrepareCliCommand:
    """已收窄的 prepare CLI 命令。

    Args:
        request: 严格 prepare 请求。

    Returns:
        不可变 CLI 命令。

    Raises:
        本类不显式抛出异常。
    """

    request: PrepareRequest


@dataclass(frozen=True)
class RunCliCommand:
    """已收窄的 run CLI 命令。

    Args:
        request: 严格 run 请求。

    Returns:
        不可变 CLI 命令。

    Raises:
        本类不显式抛出异常。
    """

    request: RunRequest


@dataclass(frozen=True)
class VerifyCliCommand:
    """已收窄的 verify CLI 命令。

    Args:
        request: 严格互斥 verify 请求。

    Returns:
        不可变 CLI 命令。

    Raises:
        本类不显式抛出异常。
    """

    request: VerifyRequest


ParsedCliCommand: TypeAlias = PrepareCliCommand | RunCliCommand | VerifyCliCommand


class _PrepareNamespace(argparse.Namespace):
    """prepare argparse 字段的静态声明。

    Args:
        字段由 argparse 按固定参数表写入。

    Returns:
        只在 CLI ingress 内使用的 typed namespace。

    Raises:
        本类不显式抛出异常。
    """

    ticker: str
    company: str
    template: str
    as_of: str
    run_root: Path
    price_snapshot: Path
    max_model_requests: int
    max_total_tokens: int
    max_estimated_cost: str
    budget_currency: str
    max_wall_seconds: int
    json_output: bool


class _RunNamespace(argparse.Namespace):
    """run argparse 字段的静态声明。

    Args:
        字段由 argparse 按固定参数表写入。

    Returns:
        只在 CLI ingress 内使用的 typed namespace。

    Raises:
        本类不显式抛出异常。
    """

    plan: Path
    fingerprint: str
    json_output: bool


class _VerifyNamespace(argparse.Namespace):
    """verify argparse 字段的静态声明。

    Args:
        字段由 argparse 按固定参数表写入。

    Returns:
        只在 CLI ingress 内使用的 typed namespace。

    Raises:
        本类不显式抛出异常。
    """

    fixture: Path | None
    plan: Path | None
    fingerprint: str | None
    json_output: bool


class _PresenceSafeArgumentParser(argparse.ArgumentParser):
    """只按静态 provider secret shape 脱敏且不读取环境值的 parser。

    Args:
        参数沿用 ``argparse.ArgumentParser``。

    Returns:
        help/usage/error 均不触碰环境变量 value 的 parser。

    Raises:
        SystemExit: 参数错误保持 argparse 标准退出语义。
    """

    def format_usage(self) -> str:
        """返回静态 secret shape 脱敏后的 usage。

        Args:
            无。

        Returns:
            安全 usage 文本。

        Raises:
            本方法不显式抛出异常。
        """

        return _redact_cli_text(super().format_usage())

    def format_help(self) -> str:
        """返回静态 secret shape 脱敏后的 help。

        Args:
            无。

        Returns:
            安全 help 文本。

        Raises:
            本方法不显式抛出异常。
        """

        return _redact_cli_text(super().format_help())

    def error(self, message: str) -> Never:
        """输出安全 usage/error 并保持标准 code 2。

        Args:
            message: argparse 生成的未信任错误文本。

        Returns:
            永不返回。

        Raises:
            SystemExit: 固定 code 2 退出。
        """

        self.print_usage(sys.stderr)
        safe_program = _redact_cli_text(self.prog)
        safe_message = _redact_cli_text(message)
        self.exit(2, f"{safe_program}: error: {safe_message}\n")


@dataclass(frozen=True)
class _ReceiptValidationContext:
    """receipt prefix 校验共享的固定身份。

    Args:
        plan: 唯一 v2 plan。
        fingerprint: 已验证 plan SHA-256。
        receipt_root: 固定 receipt 目录。
        config_root: 当前 package config 根。
        python_executable: plan 内 canonical Python 路径。

    Returns:
        不可变内部校验上下文。

    Raises:
        本类不显式抛出异常。
    """

    plan: AcceptancePlan
    fingerprint: str
    receipt_root: Path
    config_root: Path
    python_executable: str


@dataclass(frozen=True)
class _CommandRecordIdentity:
    """持有一条 v3 record 的序号与 argv 身份。

    Args:
        command_index: phase 内连续序号。
        safe_argv: 仅含受控 placeholder 的 argv。
        argv_digest: raw argv canonical SHA-256。

    Returns:
        不可变 command record 身份。

    Raises:
        本类不显式抛出异常。
    """

    command_index: int
    safe_argv: Command
    argv_digest: str


@dataclass(frozen=True)
class _CommandTiming:
    """持有一条 command record 的 wall-clock 区间。

    Args:
        started_at: command 开始 UTC 时刻。
        ended_at: command 结束 UTC 时刻。

    Returns:
        不可变 command 时间区间。

    Raises:
        本类不显式抛出异常。
    """

    started_at: datetime
    ended_at: datetime


@dataclass(frozen=True)
class MappingEnvironmentPresenceProvider:
    """deterministic 测试使用的显式 presence mapping。

    Args:
        presence: 环境变量名称到严格布尔值的映射。

    Returns:
        只由注入 mapping 决定的存在性 provider。

    Raises:
        ContractError: mapping 缺名称或值不是严格 bool 时抛出。
    """

    presence: Mapping[str, bool]

    def is_present(self, name: str) -> bool:
        """从注入 mapping 查询存在性。

        Args:
            name: 固定环境变量名称。

        Returns:
            mapping 中的严格布尔值。

        Raises:
            ContractError: 名称缺失或值不是严格 bool 时抛出。
        """

        if name not in self.presence:
            raise ContractError(f"presence provider 缺少名称: {name}")
        present = self.presence[name]
        if not isinstance(present, bool):
            raise ContractError(f"presence provider 的 {name} 必须是布尔值")
        return present


@dataclass(frozen=True)
class OsEnvironmentPresenceProvider:
    """live CLI 仅用 membership 检查真实环境变量名称。

    Args:
        names: 允许查询的固定环境变量名称集合。

    Returns:
        不读取、hash 或回显值的存在性 provider。

    Raises:
        ContractError: 查询计划外名称时抛出。
    """

    names: tuple[str, ...] = REQUIRED_ENVIRONMENT_NAMES

    def is_present(self, name: str) -> bool:
        """仅检查名称是否存在于 ``os.environ``。

        Args:
            name: 固定环境变量名称。

        Returns:
            名称存在时返回 ``True``。

        Raises:
            ContractError: 查询计划外名称时抛出。
        """

        if name not in self.names:
            raise ContractError(f"禁止查询计划外环境变量名称: {name}")
        return name in os.environ


@dataclass(frozen=True)
class GitRepositoryStateProvider:
    """通过本地 Git CLI 只读解析 HEAD 与 dirty 状态。

    Args:
        git_executable: Git 可执行文件名。

    Returns:
        不访问网络的仓库状态 provider。

    Raises:
        ContractError: Git 输出无法验证时抛出。
    """

    git_executable: str = "git"

    def read(self, repository_root: Path) -> RepositoryState:
        """读取当前 HEAD 与工作树状态。

        Args:
            repository_root: 精确仓库根。

        Returns:
            当前 commit 与 dirty 标志。

        Raises:
            ContractError: Git 命令失败或 HEAD 不是 40/64 位小写十六进制时抛出。
        """

        try:
            head = subprocess.run(
                (self.git_executable, "rev-parse", "HEAD"),
                cwd=repository_root,
                check=True,
                capture_output=True,
                text=True,
                shell=False,
            ).stdout.strip()
            status = subprocess.run(
                (self.git_executable, "status", "--porcelain", "--untracked-files=normal"),
                cwd=repository_root,
                check=True,
                capture_output=True,
                text=True,
                shell=False,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ContractError("无法读取本地 Git 运行身份") from exc
        if GIT_OBJECT_ID_PATTERN.fullmatch(head) is None:
            raise ContractError("Git HEAD 不是规范小写 object id")
        return RepositoryState(git_sha=head, dirty=bool(status))


@dataclass(frozen=True)
class SystemClock:
    """live CLI 使用的 UTC 与单调系统时钟。

    Args:
        无显式字段。

    Returns:
        当前系统时钟 provider。

    Raises:
        本类不显式抛出异常。
    """

    def utc_now(self) -> datetime:
        """读取当前 UTC wall clock。

        Args:
            无。

        Returns:
            带时区 UTC 时间。

        Raises:
            本方法不显式抛出异常。
        """

        return datetime.now(tz=UTC)

    def monotonic(self) -> float:
        """读取系统单调时钟。

        Args:
            无。

        Returns:
            单调秒计数。

        Raises:
            本方法不显式抛出异常。
        """

        return time.monotonic()


@dataclass
class SubprocessHandle:
    """把 ``subprocess.Popen`` 收窄为 runner 最小进程协议。

    Args:
        process: 已用 ``shell=False`` 创建的文本进程。

    Returns:
        跨平台 terminate/kill/wait 句柄。

    Raises:
        本类方法按 ``subprocess`` 语义传播系统异常。
    """

    process: subprocess.Popen[bytes]

    @property
    def returncode(self) -> int | None:
        """读取底层退出码。

        Args:
            无。

        Returns:
            未结束时为 ``None``，否则为退出码。

        Raises:
            本属性不显式抛出异常。
        """

        return self.process.returncode

    def communicate(self, *, timeout: float) -> tuple[bytes, bytes]:
        """等待并收集底层文本输出。

        Args:
            timeout: 本次命令最大等待秒数。

        Returns:
            stdout 与 stderr。

        Raises:
            subprocess.TimeoutExpired: 等待超时时抛出。
        """

        return self.process.communicate(timeout=timeout)

    def terminate(self) -> None:
        """请求底层进程温和终止。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 系统拒绝终止请求时抛出。
        """

        self.process.terminate()

    def kill(self) -> None:
        """请求底层进程强制终止。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 系统拒绝强杀请求时抛出。
        """

        self.process.kill()

    def wait(self, *, timeout: float) -> int:
        """等待底层进程退出。

        Args:
            timeout: 最长等待秒数。

        Returns:
            退出码。

        Raises:
            subprocess.TimeoutExpired: 等待超时时抛出。
        """

        return self.process.wait(timeout=timeout)


@dataclass(frozen=True)
class SubprocessFactory:
    """真实 ``shell=False`` 文本子进程工厂。

    Args:
        无显式字段。

    Returns:
        只接受 argv token 元组的进程工厂。

    Raises:
        OSError: 进程创建失败时抛出。
    """

    def start(
        self,
        argv: Command,
        *,
        cwd: Path,
        env: Mapping[str, str],
    ) -> RunningProcess:
        """以 ``shell=False`` 启动一个 allowlisted 命令。

        Args:
            argv: 已验证的不可变 argv token 元组。
            cwd: 固定 resolved repository root。
            env: 显式 subprocess environment。

        Returns:
            收窄后的运行中进程句柄。

        Raises:
            OSError: 进程创建失败时抛出。
        """

        process = subprocess.Popen(
            argv,
            shell=False,
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        return SubprocessHandle(process=process)


def default_runtime_identity() -> RuntimeIdentity:
    """构建 live CLI 当前进程的 canonical 运行身份。

    Args:
        无。

    Returns:
        仓库根、解释器、版本、平台与 UTC timezone。

    Raises:
        ContractError: 仓库根或解释器路径不能 canonicalize 时抛出。
    """

    repository_root = Path(__file__).resolve().parent.parent
    python_executable = Path(sys.executable).resolve(strict=True).as_posix()
    if not repository_root.is_dir():
        raise ContractError("当前仓库根不可读")
    return RuntimeIdentity(
        repository_root=repository_root,
        python_executable=python_executable,
        python_version=platform_module.python_version(),
        platform=platform_module.platform(),
        timezone=_TIMEZONE,
    )


def build_phase_specs(inputs: PhaseBuildInputs) -> tuple[PhaseSpec, ...]:
    """从 plan scalars 纯构造固定有序 phase specs。

    Args:
        inputs: 固定 run root、Python、config、as-of、价格与预算。

    Returns:
        download/import/process/preflight/write/validators 六个有序 frozen specs。

    Raises:
        ContractError: 输入身份或固定模型不符合 v2 contract 时抛出。
    """

    run_root = _canonical_absolute_path(Path(inputs.run_root), "plan_run_root", require_exists=False)
    python_path = _canonical_absolute_path(Path(inputs.python_executable), "python_executable", require_exists=True)
    config_root = _canonical_absolute_path(inputs.package_config_root, "package_config_root", require_exists=True)
    as_of_utc = _require_utc_datetime(inputs.as_of, "as_of")
    as_of_date = as_of_utc.date()
    start_5y = _subtract_calendar_years(as_of_date, 5).isoformat()
    start_2y = _subtract_calendar_years(as_of_date, 2).isoformat()
    end_date = as_of_date.isoformat()
    data_workspace = f"{run_root}/data-workspace"
    write_root = f"{run_root}/write"
    research_root = f"{run_root}/research"
    artifact_root = f"{research_root}/assets/research_templates"
    command_prefix = (python_path, "-m", "dayu.cli")
    config_suffix = ("--base", data_workspace, "--config", config_root)
    download_commands = (
        (
            *command_prefix,
            "download",
            "--ticker",
            _TICKER,
            "--forms",
            "10K",
            "--start",
            start_5y,
            "--end",
            end_date,
            *config_suffix,
            "--quiet",
        ),
        (
            *command_prefix,
            "download",
            "--ticker",
            _TICKER,
            "--forms",
            "10Q",
            "--start",
            start_2y,
            "--end",
            end_date,
            *config_suffix,
            "--quiet",
        ),
        (
            *command_prefix,
            "download",
            "--ticker",
            _TICKER,
            "--forms",
            "8K",
            "DEF14A",
            "--start",
            start_2y,
            "--end",
            end_date,
            *config_suffix,
            "--quiet",
        ),
    )
    price_import = (
        *command_prefix,
        "upload_material",
        "--ticker",
        _TICKER,
        "--forms",
        "MATERIAL_OTHER",
        "--material-name",
        "aapl-price-snapshot",
        "--document-id",
        inputs.price_material_document_id,
        "--files",
        f"{run_root}/inputs/price-snapshot.material.md",
        "--report-date",
        inputs.price_snapshot.market_date.isoformat(),
        *config_suffix,
        "--quiet",
    )
    process = (
        *command_prefix,
        "process",
        "--ticker",
        _TICKER,
        *config_suffix,
        "--quiet",
    )
    write_budget = (
        "--write-max-model-requests",
        str(inputs.budget.max_model_requests),
        "--write-max-total-tokens",
        str(inputs.budget.max_total_tokens),
        "--write-max-estimated-cost",
        str(inputs.budget.max_estimated_cost),
        "--write-budget-currency",
        inputs.budget.budget_currency,
    )
    write_common = (
        *command_prefix,
        "write",
        "--ticker",
        _TICKER,
        "--model-name",
        _PRIMARY_MODEL,
        "--audit-model-name",
        _AUDIT_MODEL,
        "--research-template",
        _TEMPLATE,
        "--output",
        write_root,
    )
    write_preflight = (
        *write_common,
        "--preflight-only",
        "--no-resume",
        *write_budget,
        *config_suffix,
    )
    paid_write = (
        *write_common,
        "--materialize-research",
        "--research-base",
        research_root,
        "--no-resume",
        *write_budget,
        *config_suffix,
    )
    validator_suffix = ("--base", research_root, "--config", config_root)
    validators = (
        (
            *command_prefix,
            "research-template",
            "validate-research-workbook",
            "--workbook",
            f"{artifact_root}/technology.research-workbook.json",
            *validator_suffix,
        ),
        (
            *command_prefix,
            "research-template",
            "validate-workbook-report",
            "--report",
            f"{artifact_root}/technology.research-progress.md",
            "--workbook",
            f"{artifact_root}/technology.research-workbook.json",
            *validator_suffix,
        ),
        (
            *command_prefix,
            "research-template",
            "validate-source-map",
            "--rules",
            f"{artifact_root}/technology.monitoring-rules.json",
            "--source-map",
            f"{artifact_root}/technology.source-map.json",
            *validator_suffix,
        ),
        (
            *command_prefix,
            "research-template",
            "validate-bundle",
            "--bundle",
            f"{artifact_root}/technology.bundle.json",
            *validator_suffix,
        ),
        (
            *command_prefix,
            "research-template",
            "validate-monitoring-plan",
            "--plan",
            f"{artifact_root}/technology.monitoring-plan.json",
            *validator_suffix,
        ),
    )
    specs = (
        PhaseSpec(phase_name="download", commands=download_commands),
        PhaseSpec(phase_name="price-snapshot-import", commands=(price_import,)),
        PhaseSpec(phase_name="process", commands=(process,)),
        PhaseSpec(phase_name="write-preflight", commands=(write_preflight,)),
        PhaseSpec(phase_name="write", commands=(paid_write,)),
        PhaseSpec(phase_name="validations", commands=validators),
    )
    _assert_structural_allowlist(specs)
    return specs


def build_terminal_verify_command(
    *,
    plan: AcceptancePlan,
    fingerprint: str,
    python_executable: str,
) -> Command:
    """在 plan fingerprint 计算后固定派生 terminal verify argv。

    Args:
        plan: 已严格解析的唯一 v2 plan。
        fingerprint: 已核对的 plan canonical SHA-256。
        python_executable: 当前 canonical Python 可执行文件。

    Returns:
        不进入 plan phase specs 的固定 terminal argv。

    Raises:
        ContractError: fingerprint、terminal action 或解释器非法时抛出。
    """

    _require_sha256_text(fingerprint, "fingerprint")
    if plan.terminal_action != TERMINAL_ACTION:
        raise ContractError("terminal action drift")
    python_path = _canonical_absolute_path(Path(python_executable), "python_executable", require_exists=True)
    return (
        python_path,
        "-m",
        "utils.investment_agent_acceptance",
        "verify",
        "--plan",
        f"{plan.run_root}/acceptance-plan.json",
        "--fingerprint",
        fingerprint,
        "--json",
    )


def safe_argv_and_digests(
    commands: CommandMatrix,
    *,
    python_executable: str,
    run_root: str,
    package_config_root: Path,
) -> tuple[CommandMatrix, tuple[str, ...]]:
    """把 raw argv 转换为三个 placeholder 与 canonical digest。

    Args:
        commands: 进程内或 local plan 中的 raw argv。
        python_executable: 当前 canonical Python 路径。
        run_root: plan 绑定的 canonical run root。
        package_config_root: resolver 返回的 canonical package config 根。

    Returns:
        可安全持久化的 argv matrix 与每条 raw argv canonical SHA-256。

    Raises:
        ContractError: raw argv 含三个 placeholder 无法覆盖的绝对路径时抛出。
    """

    python_path = _canonical_absolute_path(Path(python_executable), "python_executable", require_exists=True)
    canonical_run_root = _canonical_absolute_path(Path(run_root), "run_root", require_exists=False)
    config_root = _canonical_absolute_path(package_config_root, "package_config_root", require_exists=True)
    safe_rows: list[Command] = []
    digests: list[str] = []
    for command in commands:
        safe_rows.append(
            tuple(
                _safe_argv_token(
                    token,
                    python_executable=python_path,
                    run_root=canonical_run_root,
                    package_config_root=config_root,
                )
                for token in command
            )
        )
        digests.append(canonical_json_sha256(list(command)))
    return tuple(safe_rows), tuple(digests)


def prepare_acceptance(request: PrepareRequest, services: PrepareServices) -> PreparedAcceptance:
    """完全离线地构建 v2 plan 与 run root 骨架并原子发布。

    Args:
        request: 固定目标、价格、预算与 run root。
        services: 可注入运行身份、presence、Git 与时钟。

    Returns:
        已原子落盘的唯一 plan 与 fingerprint。

    Raises:
        ContractError: 输入、价格、模型价格、presence 或运行身份非法时抛出。
        OSError: staging 写入或同父目录原子 rename 失败时抛出。
    """

    _validate_fixed_target(request.ticker, request.company, request.template)
    as_of = _require_utc_datetime(request.as_of, "as_of")
    if request.max_wall_seconds <= 0:
        raise ContractError("max_wall_seconds 必须大于零")
    run_root = _validate_new_run_root(request.run_root, services.runtime.repository_root)
    price_payload = load_json_file(_validate_price_input(request.price_snapshot), label="price snapshot")
    price = parse_price_snapshot(price_payload)
    _validate_price_freshness(price, as_of)
    price_bytes = canonical_json_bytes(_price_snapshot_to_json(price))
    price_sha256 = hashlib.sha256(price_bytes).hexdigest()
    material_bytes = _render_price_material(price, price_sha256)
    material_sha256 = hashlib.sha256(material_bytes).hexdigest()
    package_inputs = build_package_input_fingerprints()
    config_root = resolve_package_config_path().resolve(strict=True)
    _validate_model_catalog(config_root, request.budget.budget_currency)
    environment = _read_required_environment(services.environment)
    if not all(item.present for item in environment):
        raise ContractError("live prepare 缺少必需环境变量名称")
    repository_state = services.repository_state.read(services.runtime.repository_root)
    model_roles = ModelRoles(primary=_PRIMARY_MODEL, audit=_AUDIT_MODEL)
    try:
        price_material_document_id, _internal_document_id = build_material_ids(
            form_type="MATERIAL_OTHER",
            material_name="aapl-price-snapshot",
            fiscal_year=None,
            fiscal_period=None,
        )
    except ValueError as exc:
        raise ContractError("owner 无法构建稳定 price material ID") from exc
    phase_specs = build_phase_specs(
        PhaseBuildInputs(
            run_root=run_root,
            python_executable=services.runtime.python_executable,
            package_config_root=config_root,
            as_of=as_of,
            price_snapshot=price,
            budget=request.budget,
            price_material_document_id=price_material_document_id,
        )
    )
    plan = AcceptancePlan(
        ticker=_TICKER,
        company=_COMPANY,
        research_template=_TEMPLATE,
        as_of=as_of,
        git_sha=repository_state.git_sha,
        dirty=repository_state.dirty,
        python_version=services.runtime.python_version,
        platform=services.runtime.platform,
        timezone=services.runtime.timezone,
        run_root=run_root,
        package_inputs=package_inputs,
        price_snapshot_sha256=price_sha256,
        price_material_sha256=material_sha256,
        budget=request.budget,
        max_wall_seconds=request.max_wall_seconds,
        termination_grace_seconds=_TERMINATION_GRACE_SECONDS,
        subprocess_env_policy=SUBPROCESS_ENV_POLICY,
        price_material_document_id=price_material_document_id,
        model_roles=model_roles,
        phase_specs=phase_specs,
        required_environment=environment,
        terminal_action="verify",
        required_research_artifacts=REQUIRED_RESEARCH_ARTIFACTS,
    )
    strict_plan = parse_acceptance_plan(plan.to_json())
    if strict_plan != plan:
        raise ContractError("prepare plan strict round trip 不闭合")
    fingerprint = plan.fingerprint
    terminal_command = build_terminal_verify_command(
        plan=plan,
        fingerprint=fingerprint,
        python_executable=services.runtime.python_executable,
    )
    if any(fingerprint in token for spec in plan.phase_specs for command in spec.commands for token in command):
        raise ContractError("fingerprinted phase specs 不得自引用 plan fingerprint")
    if fingerprint not in terminal_command:
        raise ContractError("terminal verify 未绑定计算后的 plan fingerprint")
    staging = Path(tempfile.mkdtemp(prefix=f".{Path(run_root).name}.staging-", dir=Path(run_root).parent))
    try:
        _write_run_skeleton(
            staging=staging,
            plan=plan,
            price_bytes=price_bytes,
            material_bytes=material_bytes,
            clock=services.clock,
        )
        staging.replace(run_root)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return PreparedAcceptance(
        plan=plan,
        fingerprint=fingerprint,
        plan_path=Path(run_root) / "acceptance-plan.json",
    )


def run_acceptance(request: RunRequest, services: RunServices) -> RunResult:
    """在全部 drift check 通过后执行固定 allowlisted phase 前缀。

    Args:
        request: plan 路径与 exact fingerprint。
        services: 当前身份、presence、时钟与进程工厂。

    Returns:
        成功或首个停止阶段的结构化结果。

    Raises:
        ContractError: 任一 plan/HEAD/package/price/budget/argv/receipt drift 在首次进程前发现时抛出。
        OSError: receipt 无法原子写入时抛出。
    """

    plan, fingerprint = _load_bound_plan(request.plan_path, request.fingerprint)
    config_root = resolve_package_config_path().resolve(strict=True)
    price = _preflight_run(plan, request.plan_path, services, config_root)
    _assert_no_existing_run_receipts(plan)
    rebuilt = build_phase_specs(
        PhaseBuildInputs(
            run_root=plan.run_root,
            python_executable=services.runtime.python_executable,
            package_config_root=config_root,
            as_of=plan.as_of,
            price_snapshot=price,
            budget=plan.budget,
            price_material_document_id=plan.price_material_document_id,
        )
    )
    if rebuilt != plan.phase_specs:
        raise ContractError("ordered phase specs drift")
    run_started = services.clock.monotonic()
    completed: list[str] = []
    for spec in plan.phase_specs:
        result = _execute_phase(
            plan=plan,
            spec=spec,
            run_started=run_started,
            services=services,
            config_root=config_root,
        )
        completed.append(spec.phase_name)
        if result.status != "passed":
            return RunResult(
                succeeded=False,
                completed_phases=tuple(completed),
                stop_phase=spec.phase_name,
                stop_reason=result.stop_reason,
            )
    terminal = build_terminal_verify_command(
        plan=plan,
        fingerprint=fingerprint,
        python_executable=services.runtime.python_executable,
    )
    terminal_result = _execute_terminal_verify(
        plan=plan,
        command=terminal,
        run_started=run_started,
        services=services,
        config_root=config_root,
    )
    completed.append(TERMINAL_ACTION)
    if terminal_result.status != "passed":
        return RunResult(
            succeeded=False,
            completed_phases=tuple(completed),
            stop_phase=TERMINAL_ACTION,
            stop_reason=terminal_result.stop_reason,
        )
    return RunResult(
        succeeded=True,
        completed_phases=tuple(completed),
        stop_phase=None,
        stop_reason=None,
    )


def verify_acceptance(request: VerifyRequest, *, clock: Clock) -> JsonObject:
    """按严格互斥模式执行 deterministic fixture 或 live plan verify。

    Args:
        request: 已由 CLI ingress 收窄的互斥 verify 请求。
        clock: 显式验证时钟。

    Returns:
        evaluator canonical receipt JSON。

    Raises:
        ContractError: 模式、plan、receipt、仓储或 artifact contract 不闭合时抛出。
        OSError: 只读输入或 receipt 写入失败时抛出。
    """

    if request.mode == "fixture":
        if request.fixture_root is None or request.plan_path is not None or request.fingerprint is not None:
            raise ContractError("fixture verify 只允许 fixture_root")
        return _verify_fixture(request.fixture_root)
    if request.mode != "live":
        raise ContractError("verify mode 非法")
    if request.fixture_root is not None or request.plan_path is None or request.fingerprint is None:
        raise ContractError("live verify 必须同时提供 plan 与 fingerprint")
    plan, fingerprint = _load_bound_plan(request.plan_path, request.fingerprint)
    receipts = _load_and_validate_receipt_prefix(plan, fingerprint)
    result = _evaluate_live_plan(plan, receipts, clock=clock)
    receipt_path = Path(plan.run_root) / "acceptance-receipt.json"
    _atomic_replace_bytes(receipt_path, result.canonical_bytes())
    return result.to_json()


def parse_cli_arguments(argv: tuple[str, ...]) -> ParsedCliCommand:
    """解析且立即收窄 prepare/run/verify 三个子命令。

    Args:
        argv: 不含程序名的不可变参数元组。

    Returns:
        三种严格 CLI 命令之一。

    Raises:
        SystemExit: 参数缺失、冲突、类型或模式非法时由 argparse 抛出。
        ContractError: UTC 时间或 Decimal 非法时抛出。
    """

    if not argv:
        _command_parser().error("必须指定 prepare、run 或 verify")
    command = argv[0]
    if command == "prepare":
        parser = _prepare_parser()
        namespace = parser.parse_args(argv[1:], namespace=_PrepareNamespace())
        budget = BudgetLimits(
            max_model_requests=namespace.max_model_requests,
            max_total_tokens=namespace.max_total_tokens,
            max_estimated_cost=_parse_decimal_text(namespace.max_estimated_cost, "max_estimated_cost"),
            budget_currency=namespace.budget_currency,
        )
        return PrepareCliCommand(
            request=PrepareRequest(
                ticker=namespace.ticker,
                company=namespace.company,
                template=namespace.template,
                as_of=_parse_utc_text(namespace.as_of, "as_of"),
                run_root=namespace.run_root,
                price_snapshot=namespace.price_snapshot,
                budget=budget,
                max_wall_seconds=namespace.max_wall_seconds,
            ),
        )
    if command == "run":
        parser = _run_parser()
        namespace = parser.parse_args(argv[1:], namespace=_RunNamespace())
        return RunCliCommand(
            request=RunRequest(plan_path=namespace.plan, fingerprint=namespace.fingerprint),
        )
    if command == "verify":
        parser = _verify_parser()
        namespace = parser.parse_args(argv[1:], namespace=_VerifyNamespace())
        if namespace.fixture is not None:
            if namespace.plan is not None or namespace.fingerprint is not None:
                parser.error("--fixture 与 --plan/--fingerprint 严格互斥")
            request = VerifyRequest(
                mode="fixture",
                fixture_root=namespace.fixture,
                plan_path=None,
                fingerprint=None,
            )
        else:
            if namespace.plan is None or namespace.fingerprint is None:
                parser.error("live verify 必须同时提供 --plan 与 --fingerprint")
            request = VerifyRequest(
                mode="live",
                fixture_root=None,
                plan_path=namespace.plan,
                fingerprint=namespace.fingerprint,
            )
        return VerifyCliCommand(request=request)
    _command_parser().error("子命令必须是 prepare、run 或 verify")


def main(argv: tuple[str, ...] | None = None) -> int:
    """执行投资 Agent 验收 CLI 的离线控制面。

    Args:
        argv: 可选测试参数；省略时读取 ``sys.argv[1:]``。

    Returns:
        0 表示命令完成；1 表示 run/verify FAIL；3 表示等待人工复核；2 表示 contract/I/O 失败。

    Raises:
        SystemExit: argparse 参数错误保持标准退出流程。
    """

    arguments = tuple(sys.argv[1:]) if argv is None else argv
    try:
        command = parse_cli_arguments(arguments)
        runtime = default_runtime_identity()
        clock = SystemClock()
        if isinstance(command, PrepareCliCommand):
            prepared = prepare_acceptance(
                command.request,
                PrepareServices(
                    runtime=runtime,
                    environment=OsEnvironmentPresenceProvider(),
                    repository_state=GitRepositoryStateProvider(),
                    clock=clock,
                ),
            )
            payload: JsonObject = {
                "status": "prepared",
                "plan": prepared.plan_path.as_posix(),
                "fingerprint": prepared.fingerprint,
            }
            _emit_json(payload)
            return 0
        if isinstance(command, RunCliCommand):
            run_result = run_acceptance(
                command.request,
                RunServices(
                    runtime=runtime,
                    environment=OsEnvironmentPresenceProvider(),
                    repository_state=GitRepositoryStateProvider(),
                    clock=clock,
                    process_factory=SubprocessFactory(),
                    subprocess_environment=os.environ,
                ),
            )
            payload = {
                "succeeded": run_result.succeeded,
                "completed_phases": list(run_result.completed_phases),
                "stop_phase": run_result.stop_phase,
                "stop_reason": run_result.stop_reason,
            }
            _emit_json(payload)
            return 0 if run_result.succeeded else 1
        receipt = verify_acceptance(command.request, clock=clock)
        _emit_json(receipt)
        verdict = _json_string(_required_json(receipt, "verdict", "acceptance receipt"), "receipt.verdict")
        if verdict == "PASS":
            return 0
        if verdict == "PENDING_MANUAL_REVIEW":
            return 3
        return 1
    except (ContractError, OSError) as exc:
        message = _redact_cli_text(str(exc))
        sys.stderr.write(f"investment-agent-acceptance: {message}\n")
        return 2
    except Exception as exc:
        message = _redact_cli_text(f"unexpected {type(exc).__name__}")
        sys.stderr.write(f"investment-agent-acceptance: {message}\n")
        return 2


def _command_parser() -> _PresenceSafeArgumentParser:
    """构建仅用于顶层子命令错误的脱敏 parser。

    Args:
        无。

    Returns:
        不含动态命令入口的 parser。

    Raises:
        本函数不显式抛出异常。
    """

    return _PresenceSafeArgumentParser(prog="investment-agent-acceptance")


def _prepare_parser() -> _PresenceSafeArgumentParser:
    """构建无默认预算的 prepare parser。

    Args:
        无。

    Returns:
        全部 live 风险参数显式必填的 parser。

    Raises:
        本函数不显式抛出异常。
    """

    parser = _PresenceSafeArgumentParser(prog="investment-agent-acceptance prepare")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--price-snapshot", required=True, type=Path)
    parser.add_argument("--max-model-requests", required=True, type=int)
    parser.add_argument("--max-total-tokens", required=True, type=int)
    parser.add_argument("--max-estimated-cost", required=True)
    parser.add_argument("--budget-currency", required=True)
    parser.add_argument("--max-wall-seconds", required=True, type=int)
    parser.add_argument("--json", action="store_true", required=True, dest="json_output")
    return parser


def _run_parser() -> _PresenceSafeArgumentParser:
    """构建 plan+fingerprint 均必填的 run parser。

    Args:
        无。

    Returns:
        runner parser。

    Raises:
        本函数不显式抛出异常。
    """

    parser = _PresenceSafeArgumentParser(prog="investment-agent-acceptance run")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--json", action="store_true", required=True, dest="json_output")
    return parser


def _verify_parser() -> _PresenceSafeArgumentParser:
    """构建由 ingress 手动闭合两种互斥模式的 verify parser。

    Args:
        无。

    Returns:
        fixture/live verify parser。

    Raises:
        本函数不显式抛出异常。
    """

    parser = _PresenceSafeArgumentParser(prog="investment-agent-acceptance verify")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--fingerprint")
    parser.add_argument("--json", action="store_true", required=True, dest="json_output")
    return parser


def _parse_utc_text(value: str, label: str) -> datetime:
    """解析秒精度 Z 结尾 UTC RFC3339 文本。

    Args:
        value: CLI 时间文本。
        label: 错误上下文。

    Returns:
        秒精度 UTC datetime。

    Raises:
        ContractError: 格式、时区或精度非法时抛出。
    """

    if not value.endswith("Z"):
        raise ContractError(f"{label} 必须以 Z 表示 UTC")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as exc:
        raise ContractError(f"{label} 不是合法 RFC3339 时间") from exc
    return _require_utc_datetime(parsed, label)


def _parse_decimal_text(value: str, label: str) -> Decimal:
    """解析 CLI 显式有限正 Decimal。

    Args:
        value: CLI 十进制文本。
        label: 错误上下文。

    Returns:
        有限正 Decimal。

    Raises:
        ContractError: 文本非法、非有限或非正时抛出。
    """

    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ContractError(f"{label} 不是合法十进制数") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ContractError(f"{label} 必须是正有限十进制数")
    return parsed


def _emit_json(payload: JsonObject) -> None:
    """向 stdout 写一行 canonical JSON。

    Args:
        payload: 已收窄 JSON 对象。

    Returns:
        无。

    Raises:
        ContractError: JSON 值域非法时抛出。
        OSError: stdout 写入失败时抛出。
    """

    sys.stdout.buffer.write(canonical_json_bytes(payload))
    sys.stdout.buffer.write(b"\n")


def _redact_cli_text(text: str) -> str:
    """按静态 header/key/provider/path 形状脱敏且不枚举环境值。

    Args:
        text: 待输出 CLI 文本。

    Returns:
        已替换 header、assignment、provider token 与 home path 的文本。

    Raises:
        本函数不显式抛出异常。
    """

    redacted = _STATIC_SECRET_FIELD_PATTERN.sub(REDACTED_SECRET, text)
    redacted = SECRET_KEY_PATTERN.sub(REDACTED_SECRET, redacted)
    redacted = _GOOGLE_API_KEY_PATTERN.sub(REDACTED_SECRET, redacted)
    redacted = _POSIX_HOME_PATH_PATTERN.sub("<HOME_PATH>", redacted)
    return _WINDOWS_HOME_PATH_PATTERN.sub("<HOME_PATH>", redacted)


def _preflight_run(
    plan: AcceptancePlan,
    plan_path: Path,
    services: RunServices,
    config_root: Path,
) -> PriceSnapshot:
    """在首次进程创建前重算全部运行身份与文件指纹。

    Args:
        plan: 已严格解析的唯一 v2 plan。
        plan_path: 用户提供的 plan 路径。
        services: 当前 runtime/Git/presence 依赖。
        config_root: 当前 resolver package config 根。

    Returns:
        已重验 freshness 与 digest 的价格快照。

    Raises:
        ContractError: 任一运行身份或文件 drift 时抛出。
    """

    _validate_plan_runtime_identity(plan, plan_path, services, config_root)
    price = _load_verified_price_inputs(plan)
    if plan.max_wall_seconds <= 0 or plan.termination_grace_seconds != _TERMINATION_GRACE_SECONDS:
        raise ContractError("wall-clock/grace drift")
    if plan.subprocess_env_policy != SUBPROCESS_ENV_POLICY:
        raise ContractError("subprocess env policy drift")
    stable_document_id, _stable_internal_id = build_material_ids(
        form_type="MATERIAL_OTHER",
        material_name="aapl-price-snapshot",
        fiscal_year=None,
        fiscal_period=None,
    )
    if plan.price_material_document_id != stable_document_id:
        raise ContractError("price material stable ID drift")
    _validate_budget(plan.budget)
    _assert_structural_allowlist(plan.phase_specs)
    return price


def _validate_plan_runtime_identity(
    plan: AcceptancePlan,
    plan_path: Path,
    services: RunServices,
    config_root: Path,
) -> None:
    """核对 plan 路径、仓库、runtime、package 与 environment 身份。

    Args:
        plan: 唯一 v2 plan。
        plan_path: 用户提供的 plan 路径。
        services: 当前 runtime/Git/presence 依赖。
        config_root: 当前 resolver package config 根。

    Returns:
        无。

    Raises:
        ContractError: 任一身份 drift 时抛出。
    """

    run_root = Path(plan.run_root)
    if not run_root.is_dir() or run_root.is_symlink():
        raise ContractError("plan run root 不再是普通目录")
    expected_plan_path = run_root / "acceptance-plan.json"
    if plan_path.resolve(strict=True) != expected_plan_path.resolve(strict=True):
        raise ContractError("plan path 与 canonical run root 不闭合")
    _validate_existing_run_root(run_root, services.runtime.repository_root)
    state = services.repository_state.read(services.runtime.repository_root)
    if state.git_sha != plan.git_sha or state.dirty != plan.dirty:
        raise ContractError("HEAD/dirty drift")
    if (
        services.runtime.python_version != plan.python_version
        or services.runtime.platform != plan.platform
        or services.runtime.timezone != plan.timezone
    ):
        raise ContractError("Python/platform/timezone runtime identity drift")
    assert_package_input_fingerprints(plan.package_inputs)
    _validate_model_catalog(config_root, plan.budget.budget_currency)
    environment = _read_required_environment(services.environment)
    if environment != plan.required_environment or not all(item.present for item in environment):
        raise ContractError("required environment presence drift")


def _load_verified_price_inputs(plan: AcceptancePlan) -> PriceSnapshot:
    """重读并核对 canonical 价格 JSON 与 Markdown 指纹。

    Args:
        plan: 唯一 v2 plan。

    Returns:
        与 plan 闭合的价格快照。

    Raises:
        ContractError: 文件、时效、canonical bytes 或摘要 drift 时抛出。
        OSError: 文件读取失败时抛出。
    """

    run_root = Path(plan.run_root)
    price_path = run_root / "inputs" / "price-snapshot.json"
    material_path = run_root / "inputs" / "price-snapshot.material.md"
    price_payload = load_json_file(price_path, label="run price snapshot")
    price = parse_price_snapshot(price_payload)
    _validate_price_freshness(price, plan.as_of)
    canonical_price = canonical_json_bytes(_price_snapshot_to_json(price))
    if price_path.read_bytes() != canonical_price:
        raise ContractError("price snapshot 不是 canonical bytes")
    if hashlib.sha256(canonical_price).hexdigest() != plan.price_snapshot_sha256:
        raise ContractError("price snapshot fingerprint drift")
    if material_path.is_symlink() or not material_path.is_file():
        raise ContractError("price material 必须是普通非 symlink 文件")
    expected_material = _render_price_material(price, plan.price_snapshot_sha256)
    material_bytes = material_path.read_bytes()
    if material_bytes != expected_material or hashlib.sha256(material_bytes).hexdigest() != plan.price_material_sha256:
        raise ContractError("price material fingerprint drift")
    return price


def _execute_phase(
    *,
    plan: AcceptancePlan,
    spec: PhaseSpec,
    run_started: float,
    services: RunServices,
    config_root: Path,
) -> CommandResult:
    """执行一个 plan-owned phase 并写逐命令 v3 receipt。

    Args:
        plan: 唯一 v2 plan。
        spec: 当前有序 phase spec。
        run_started: 整次 run 唯一单调起点。
        services: 时钟与进程工厂。
        config_root: 当前 package config 根。

    Returns:
        phase 聚合退出事实。

    Raises:
        ContractError: owner formatter 或 repository evidence 不闭合时转为 truthful failed record。
        OSError: receipt 无法写入时抛出。
    """

    started_at = services.clock.utc_now()
    records: list[CommandRecord] = []
    result = CommandResult(
        status="passed",
        exit_code=0,
        stop_reason=None,
        termination_action=None,
        partial_by_timeout=False,
    )
    for command_index, command in enumerate(spec.commands):
        command_started_at = services.clock.utc_now()
        remaining = plan.max_wall_seconds - (services.clock.monotonic() - run_started)
        if remaining <= 0:
            result = CommandResult(
                status="timeout",
                exit_code=None,
                stop_reason="whole_run_wall_clock_exhausted_before_start",
                termination_action="not_started",
                partial_by_timeout=True,
            )
        else:
            result = _execute_command(
                command,
                timeout_seconds=remaining,
                plan=plan,
                services=services,
            )
        command_ended_at = services.clock.utc_now()
        evidence: CommandEvidence | None = None
        stdout_summary = _stream_summary(result.stdout, category="stdout_present")
        if result.status == "passed" and spec.phase_name in {"download", "price-snapshot-import", "process"}:
            try:
                evidence, prefix_line_count = _parse_owner_command_evidence(
                    plan=plan,
                    phase_name=spec.phase_name,
                    command=command,
                    stdout=result.stdout,
                )
                stdout_summary = (
                    _stream_summary(result.stdout, category="prefix_noise", line_number=1)
                    if prefix_line_count > 0
                    else None
                )
                semantic_stop = _owner_semantic_stop_reason(plan, evidence)
                if semantic_stop is not None:
                    result = CommandResult(
                        status="failed",
                        exit_code=0,
                        stop_reason=semantic_stop,
                        termination_action=None,
                        partial_by_timeout=False,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )
            except _OwnerOutputError as exc:
                result = CommandResult(
                    status="failed",
                    exit_code=0,
                    stop_reason="owner_output_structure_reject",
                    termination_action=None,
                    partial_by_timeout=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
                stdout_summary = _stream_summary(
                    result.stdout,
                    category="structure_reject",
                    line_number=exc.line_number,
                )
            except ContractError:
                result = CommandResult(
                    status="failed",
                    exit_code=0,
                    stop_reason="owner_semantic_contract_reject",
                    termination_action=None,
                    partial_by_timeout=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
        safe_argv, digests = safe_argv_and_digests(
            (command,),
            python_executable=services.runtime.python_executable,
            run_root=plan.run_root,
            package_config_root=config_root,
        )
        records.append(
            _command_record(
                identity=_CommandRecordIdentity(
                    command_index=command_index,
                    safe_argv=safe_argv[0],
                    argv_digest=digests[0],
                ),
                result=result,
                timing=_CommandTiming(
                    started_at=command_started_at,
                    ended_at=command_ended_at,
                ),
                stdout_summary=stdout_summary,
                evidence=evidence,
            )
        )
        if result.status != "passed":
            break
    ended_at = services.clock.utc_now()
    elapsed = max(0.0, services.clock.monotonic() - run_started)
    remaining_wall = max(0.0, plan.max_wall_seconds - elapsed)
    receipt = PhaseReceipt(
        plan_fingerprint=plan.fingerprint,
        phase_name=spec.phase_name,
        status=result.status,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=max(0.0, (ended_at - started_at).total_seconds()),
        remaining_wall_seconds=remaining_wall,
        command_records=tuple(records),
    )
    _write_phase_receipt(plan, receipt)
    return result


def _execute_terminal_verify(
    *,
    plan: AcceptancePlan,
    command: Command,
    run_started: float,
    services: RunServices,
    config_root: Path,
) -> CommandResult:
    """执行 fingerprint 后派生的 terminal verify 并写固定 verify.json。

    Args:
        plan: 唯一 v2 plan。
        command: 固定派生 terminal argv。
        run_started: 整次 run 唯一单调起点。
        services: 时钟与进程工厂。
        config_root: 当前 package config 根。

    Returns:
        terminal verify 退出事实。

    Raises:
        OSError: receipt 无法写入时抛出。
    """

    started_at = services.clock.utc_now()
    remaining = plan.max_wall_seconds - (services.clock.monotonic() - run_started)
    if remaining <= 0:
        result = CommandResult(
            status="timeout",
            exit_code=None,
            stop_reason="whole_run_wall_clock_exhausted_before_terminal_verify",
            termination_action="not_started",
            partial_by_timeout=True,
        )
    else:
        result = _execute_command(
            command,
            timeout_seconds=remaining,
            plan=plan,
            services=services,
        )
    ended_at = services.clock.utc_now()
    elapsed = max(0.0, services.clock.monotonic() - run_started)
    safe_argv, digests = safe_argv_and_digests(
        (command,),
        python_executable=services.runtime.python_executable,
        run_root=plan.run_root,
        package_config_root=config_root,
    )
    receipt = PhaseReceipt(
        plan_fingerprint=plan.fingerprint,
        phase_name=TERMINAL_ACTION,
        status=result.status,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=max(0.0, (ended_at - started_at).total_seconds()),
        remaining_wall_seconds=max(0.0, plan.max_wall_seconds - elapsed),
        command_records=(
            _command_record(
                identity=_CommandRecordIdentity(
                    command_index=0,
                    safe_argv=safe_argv[0],
                    argv_digest=digests[0],
                ),
                result=result,
                timing=_CommandTiming(
                    started_at=started_at,
                    ended_at=ended_at,
                ),
                stdout_summary=_stream_summary(result.stdout, category="stdout_present"),
                evidence=None,
            ),
        ),
    )
    _write_phase_receipt(plan, receipt)
    return result


def _execute_command(
    command: Command,
    *,
    timeout_seconds: float,
    plan: AcceptancePlan,
    services: RunServices,
) -> CommandResult:
    """执行一条命令并按 terminate→grace→kill 收敛 timeout。

    Args:
        command: 已经 pure-builder equality 校验的 argv。
        timeout_seconds: whole-run 当前剩余秒数。
        plan: termination grace 与静态环境策略真源。
        services: 进程工厂、repository cwd 与内存环境。

    Returns:
        退出、signal 或 timeout 结构化事实。

    Raises:
        本函数把进程创建/通信异常归一化为 failed 结果，不显式传播。
    """

    deadline = services.clock.monotonic() + timeout_seconds
    subprocess_environment = _build_subprocess_environment(
        services.subprocess_environment,
        plan.subprocess_env_policy,
    )
    try:
        process = services.process_factory.start(
            command,
            cwd=services.runtime.repository_root,
            env=subprocess_environment,
        )
    except OSError:
        return CommandResult(
            status="failed",
            exit_code=None,
            stop_reason="process_start_failed",
            termination_action=None,
            partial_by_timeout=False,
        )
    remaining_after_start = deadline - services.clock.monotonic()
    if remaining_after_start <= 0:
        return _terminate_timed_out_process(
            process,
            termination_grace_seconds=plan.termination_grace_seconds,
            partial_stdout=b"",
            partial_stderr=b"",
        )
    try:
        stdout, stderr = process.communicate(timeout=remaining_after_start)
    except subprocess.TimeoutExpired as exc:
        return _terminate_timed_out_process(
            process,
            termination_grace_seconds=plan.termination_grace_seconds,
            partial_stdout=_timeout_stream_bytes(exc.output),
            partial_stderr=_timeout_stream_bytes(exc.stderr),
        )
    except OSError:
        return CommandResult(
            status="failed",
            exit_code=process.returncode,
            stop_reason="process_communication_failed",
            termination_action=None,
            partial_by_timeout=False,
            stdout=b"",
            stderr=b"",
        )
    exit_code = process.returncode
    if exit_code is None:
        return CommandResult(
            status="failed",
            exit_code=None,
            stop_reason="process_exit_unconfirmed",
            termination_action=None,
            partial_by_timeout=False,
            stdout=stdout,
            stderr=stderr,
        )
    if exit_code < 0:
        return CommandResult(
            status="signal",
            exit_code=exit_code,
            stop_reason="process_terminated_by_signal",
            termination_action=None,
            partial_by_timeout=False,
            stdout=stdout,
            stderr=stderr,
        )
    if exit_code != 0:
        return CommandResult(
            status="failed",
            exit_code=exit_code,
            stop_reason=_stderr_stop_reason(stderr),
            termination_action=None,
            partial_by_timeout=False,
            stdout=stdout,
            stderr=stderr,
        )
    return CommandResult(
        status="passed",
        exit_code=0,
        stop_reason=None,
        termination_action=None,
        partial_by_timeout=False,
        stdout=stdout,
        stderr=stderr,
    )


def _terminate_timed_out_process(
    process: RunningProcess,
    *,
    termination_grace_seconds: int,
    partial_stdout: bytes,
    partial_stderr: bytes,
) -> CommandResult:
    """跨平台收敛一个已 timeout 的进程并保留 partial 事实。

    Args:
        process: 已 timeout 的进程句柄。
        termination_grace_seconds: terminate 与 kill 后各自等待秒数。
        partial_stdout: 首次 TimeoutExpired 已捕获的 stdout bytes。
        partial_stderr: 首次 TimeoutExpired 已捕获的 stderr bytes。

    Returns:
        timeout receipt 所需退出码与 termination action。

    Raises:
        本函数把终止系统异常归一化为 ``termination_unconfirmed``。
    """

    try:
        process.terminate()
        stdout, stderr = process.communicate(timeout=float(termination_grace_seconds))
        return CommandResult(
            status="timeout",
            exit_code=process.returncode,
            stop_reason="whole_run_wall_clock_timeout",
            termination_action="terminate",
            partial_by_timeout=True,
            stdout=_prefer_complete_stream(partial_stdout, stdout),
            stderr=_prefer_complete_stream(partial_stderr, stderr),
        )
    except subprocess.TimeoutExpired as exc:
        partial_stdout = _prefer_complete_stream(partial_stdout, _timeout_stream_bytes(exc.output))
        partial_stderr = _prefer_complete_stream(partial_stderr, _timeout_stream_bytes(exc.stderr))
    except OSError:
        return CommandResult(
            status="timeout",
            exit_code=process.returncode,
            stop_reason="whole_run_wall_clock_timeout",
            termination_action="termination_unconfirmed",
            partial_by_timeout=True,
            stdout=partial_stdout,
            stderr=partial_stderr,
        )
    try:
        process.kill()
        stdout, stderr = process.communicate(timeout=float(termination_grace_seconds))
        return CommandResult(
            status="timeout",
            exit_code=process.returncode,
            stop_reason="whole_run_wall_clock_timeout",
            termination_action="kill",
            partial_by_timeout=True,
            stdout=_prefer_complete_stream(partial_stdout, stdout),
            stderr=_prefer_complete_stream(partial_stderr, stderr),
        )
    except subprocess.TimeoutExpired as exc:
        partial_stdout = _prefer_complete_stream(partial_stdout, _timeout_stream_bytes(exc.output))
        partial_stderr = _prefer_complete_stream(partial_stderr, _timeout_stream_bytes(exc.stderr))
    except OSError:
        pass
    return CommandResult(
        status="timeout",
        exit_code=process.returncode,
        stop_reason="whole_run_wall_clock_timeout",
        termination_action="termination_unconfirmed",
        partial_by_timeout=True,
        stdout=partial_stdout,
        stderr=partial_stderr,
    )


def _timeout_stream_bytes(payload: bytes | str | None) -> bytes:
    """把 TimeoutExpired 的可选 partial stream 收窄为 bytes。

    Args:
        payload: subprocess 暴露的 bytes、兼容 text 或 null。

    Returns:
        原始 bytes；text 以 UTF-8 编码；null 返回空 bytes。

    Raises:
        本函数不显式抛出异常。
    """

    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return b""


def _prefer_complete_stream(partial: bytes, complete: bytes) -> bytes:
    """按 Popen cumulative communicate 语义选择最终完整 stream。

    Args:
        partial: TimeoutExpired 已捕获的前缀 bytes。
        complete: 后续 bounded communicate 返回的 cumulative bytes。

    Returns:
        非空 complete 优先；否则保留 partial，绝不拼接造成重复。

    Raises:
        本函数不显式抛出异常。
    """

    return complete if complete else partial


def _build_subprocess_environment(
    source: Mapping[str, str],
    policy: tuple[tuple[str, str], ...],
) -> dict[str, str]:
    """复制进程环境并应用 plan-bound non-secret overrides。

    Args:
        source: live ``os.environ`` 或 deterministic 注入 mapping。
        policy: AcceptancePlan 中精确固定的三项策略。

    Returns:
        只在进程内存中使用的全新环境 mapping。

    Raises:
        ContractError: policy 漂移或 source 含非字符串键值时抛出。
    """

    if policy != SUBPROCESS_ENV_POLICY:
        raise ContractError("subprocess env policy drift")
    environment: dict[str, str] = {}
    for name, value in source.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise ContractError("subprocess environment 必须是字符串 mapping")
        environment[name] = value
    environment.update(dict(policy))
    return environment


def _command_record(
    *,
    identity: _CommandRecordIdentity,
    result: CommandResult,
    timing: _CommandTiming,
    stdout_summary: str | None,
    evidence: CommandEvidence | None,
) -> CommandRecord:
    """把进程事实机械转换为 v3 command record。

    Args:
        identity: phase 内序号与 argv 身份。
        result: 进程/semantic 结果。
        timing: command wall-clock 区间。
        stdout_summary: clean/prefix/reject 分类摘要。
        evidence: owner strict evidence 或 null。

    Returns:
        严格不可变 CommandRecord。

    Raises:
        ContractError: record lifecycle 不闭合时由 contract 抛出。
    """

    stdout_sha = hashlib.sha256(result.stdout).hexdigest() if result.stdout is not None else None
    stderr_sha = hashlib.sha256(result.stderr).hexdigest() if result.stderr is not None else None
    return CommandRecord(
        command_index=identity.command_index,
        safe_argv=identity.safe_argv,
        argv_digest=identity.argv_digest,
        status=result.status,
        started_at=timing.started_at,
        ended_at=timing.ended_at,
        duration_seconds=max(0.0, (timing.ended_at - timing.started_at).total_seconds()),
        exit_code=result.exit_code,
        stop_reason=result.stop_reason,
        termination_action=result.termination_action,
        partial_by_timeout=result.partial_by_timeout,
        stdout_sha256=stdout_sha,
        stderr_sha256=stderr_sha,
        stdout_summary=stdout_summary,
        stderr_summary=_stream_summary(result.stderr, category="stderr_present"),
        evidence=evidence,
    )


def _stream_summary(
    payload: bytes | None,
    *,
    category: str,
    line_number: int = 0,
) -> str | None:
    """生成 512-byte 内静态脱敏 stream 摘要。

    Args:
        payload: 完整 stream bytes；仅用于有界诊断，不落原文。
        category: allowlisted 静态分类。
        line_number: 可选 1-based 触发行号。

    Returns:
        空流返回 null；否则返回合法 UTF-8 bounded 摘要。

    Raises:
        本函数不显式抛出异常。
    """

    if not payload:
        return None
    line_fragment = ""
    if category in {"prefix_noise", "structure_reject", "stderr_present"}:
        lines = payload.decode("utf-8", errors="replace").splitlines()
        target_index = max(0, line_number - 1)
        fragment = lines[target_index] if target_index < len(lines) else ""
        fragment = _redact_cli_text(fragment)
        line_fragment = f" fragment={fragment}"
    summary = f"category={category} line={line_number}{line_fragment}"
    encoded = summary.encode("utf-8")
    if len(encoded) <= _STREAM_SUMMARY_MAX_BYTES:
        return summary
    return encoded[:_STREAM_SUMMARY_MAX_BYTES].decode("utf-8", errors="ignore")


def _parse_owner_command_evidence(
    *,
    plan: AcceptancePlan,
    phase_name: str,
    command: Command,
    stdout: bytes | None,
) -> tuple[CommandEvidence, int]:
    """按 phase 选择唯一 owner formatter ingress。

    Args:
        plan: plan-bound price/repository identity。
        phase_name: download/import/process 之一。
        command: 当前 raw argv。
        stdout: 子进程完整 stdout bytes。

    Returns:
        严格 evidence 与 title 前缀行数。

    Raises:
        _OwnerOutputError: UTF-8、title 或结构 grammar 不闭合时抛出。
    """

    raw = stdout if stdout is not None else b""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _OwnerOutputError("owner stdout 不是合法 UTF-8") from exc
    if phase_name == "download":
        return _parse_download_output(command, text)
    if phase_name == "price-snapshot-import":
        return _parse_material_output(plan, text)
    if phase_name == "process":
        return _parse_process_output(text)
    raise _OwnerOutputError("owner ingress phase 非法")


def _anchored_owner_lines(text: str, title: str) -> tuple[tuple[str, ...], int]:
    """要求 formatter title 全局唯一并返回 anchor 后行。

    Args:
        text: 已严格 UTF-8 解码的 stdout。
        title: 固定 owner formatter title。

    Returns:
        anchor 后全部行与 anchor 前缀行数。

    Raises:
        _OwnerOutputError: title 数量不是一时抛出。
    """

    lines = tuple(text.splitlines())
    indices = tuple(index for index, line in enumerate(lines) if line == title)
    if len(indices) != 1:
        raise _OwnerOutputError("owner formatter title 必须全局唯一")
    anchor = indices[0]
    return lines[anchor + 1 :], anchor


def _command_flag_values(command: Command, flag: str) -> tuple[str, ...]:
    """从 pure-builder argv 提取一个 flag 到下个 flag 前的值。

    Args:
        command: 已 canonical equality 校验的 argv。
        flag: 固定 flag 名称。

    Returns:
        一个或多个非空值 token。

    Raises:
        ContractError: flag 缺失/重复或值为空时抛出。
    """

    if command.count(flag) != 1:
        raise ContractError(f"command flag 数量非法: {flag}")
    start = command.index(flag) + 1
    values: list[str] = []
    for token in command[start:]:
        if token.startswith("--"):
            break
        values.append(token)
    if not values:
        raise ContractError(f"command flag 缺值: {flag}")
    return tuple(values)


def _parse_download_header(
    lines: tuple[str, ...],
    *,
    prefix_count: int,
) -> tuple[
    Literal["ok", "downloaded", "skipped", "cancelled"],
    DownloadSummary,
    tuple[int, ...],
]:
    """收窄 download 标量、摘要与三节位置。

    Args:
        lines: title anchor 后全部行。
        prefix_count: title 前噪声行数。

    Returns:
        owner status、严格计数摘要与三节行号。

    Raises:
        _OwnerOutputError: 标量、摘要或 warning/section 结构非法时抛出。
    """

    if len(lines) < _DOWNLOAD_MIN_LINE_COUNT or lines[0] != "- ticker: AAPL":
        raise _OwnerOutputError("download ticker 结构非法", line_number=prefix_count + 2)
    if not lines[1].startswith("- status: "):
        raise _OwnerOutputError("download status 结构非法", line_number=prefix_count + 3)
    owner_status_text = lines[1].removeprefix("- status: ")
    if owner_status_text == "ok":
        owner_status: Literal["ok", "downloaded", "skipped", "cancelled"] = "ok"
    elif owner_status_text == "downloaded":
        owner_status = "downloaded"
    elif owner_status_text == "skipped":
        owner_status = "skipped"
    elif owner_status_text == "cancelled":
        owner_status = "cancelled"
    else:
        raise _OwnerOutputError("download owner status 非法", line_number=prefix_count + 3)
    summary_match = re.fullmatch(
        r"- 汇总: total=([0-9]+), downloaded=([0-9]+), skipped=([0-9]+), failed=([0-9]+), "
        r"elapsed_ms=[0-9]+, reused_downloads=[0-9]+, converted=[0-9]+",
        lines[2],
    )
    if summary_match is None:
        raise _OwnerOutputError("download summary 结构非法", line_number=prefix_count + 4)
    summary = DownloadSummary(
        total=int(summary_match.group(1)),
        downloaded=int(summary_match.group(2)),
        skipped=int(summary_match.group(3)),
        failed=int(summary_match.group(4)),
    )
    section_headers = ("成功下载的 filings:", "跳过的 filings:", "失败的 filings:")
    section_indices = _unique_ordered_indices(lines, section_headers, prefix_count=prefix_count)
    first_section = section_indices[0]
    if first_section < _DOWNLOAD_SCALAR_LINE_COUNT:
        raise _OwnerOutputError("download section 位置非法", line_number=prefix_count + 5)
    if first_section > _DOWNLOAD_SCALAR_LINE_COUNT and (
        lines[_DOWNLOAD_SCALAR_LINE_COUNT] != "- warnings:"
        or any(
            not line.startswith("  - ")
            for line in lines[_DOWNLOAD_SCALAR_LINE_COUNT + 1 : first_section]
        )
    ):
        raise _OwnerOutputError("download warning tail 结构非法", line_number=prefix_count + 5)
    return owner_status, summary, section_indices


def _parse_download_output(command: Command, text: str) -> tuple[DownloadCommandEvidence, int]:
    """严格解析 download 固定 formatter grammar。

    Args:
        command: 当前 plan-owned download argv。
        text: 完整 stdout 文本。

    Returns:
        DownloadCommandEvidence 与 title 前缀行数。

    Raises:
        _OwnerOutputError: scalar/summary/section/row 结构漂移时抛出。
    """

    lines, prefix_count = _anchored_owner_lines(text, "下载结果")
    owner_status, summary, section_indices = _parse_download_header(lines, prefix_count=prefix_count)
    section_statuses: tuple[Literal["downloaded", "skipped", "failed"], ...] = (
        "downloaded",
        "skipped",
        "failed",
    )
    rows: list[DownloadEvidenceRow] = []
    for section_index, status in enumerate(section_statuses):
        start = section_indices[section_index] + 1
        end = (
            section_indices[section_index + 1]
            if section_index < _DOWNLOAD_SECTION_COUNT - 1
            else len(lines)
        )
        rows.extend(
            _parse_download_section_rows(
                lines[start:end],
                status=status,
                first_line_number=prefix_count + start + 2,
            )
        )
    planned_forms = _command_flag_values(command, "--forms")
    try:
        canonical_forms = tuple(normalize_form(form) for form in planned_forms)
    except ValueError as exc:
        raise _OwnerOutputError("download plan form 无法规范化") from exc
    evidence = DownloadCommandEvidence(
        ticker="AAPL",
        planned_forms=planned_forms,
        canonical_forms=canonical_forms,
        start=date.fromisoformat(_command_flag_values(command, "--start")[0]),
        end=date.fromisoformat(_command_flag_values(command, "--end")[0]),
        owner_status=owner_status,
        summary=summary,
        rows=tuple(rows),
    )
    return evidence, prefix_count


def _unique_ordered_indices(
    lines: tuple[str, ...],
    headers: tuple[str, ...],
    *,
    prefix_count: int,
) -> tuple[int, ...]:
    """要求固定 headers 各出现一次且严格有序。

    Args:
        lines: anchor 后行。
        headers: 固定 header 顺序。
        prefix_count: title 前缀行数，用于诊断行号。

    Returns:
        各 header 的 0-based 行索引。

    Raises:
        _OwnerOutputError: header 缺失、重复或重排时抛出。
    """

    indices: list[int] = []
    for header in headers:
        matches = tuple(index for index, line in enumerate(lines) if line == header)
        if len(matches) != 1:
            raise _OwnerOutputError("owner section header 必须唯一", line_number=prefix_count + 1)
        indices.append(matches[0])
    if indices != sorted(indices):
        raise _OwnerOutputError("owner section headers 顺序非法", line_number=prefix_count + 1)
    return tuple(indices)


def _parse_download_section_rows(
    lines: tuple[str, ...],
    *,
    status: Literal["downloaded", "skipped", "failed"],
    first_line_number: int,
) -> tuple[DownloadEvidenceRow, ...]:
    """解析一个 download section 的可信 row 前缀。

    Args:
        lines: 当前 section rows。
        status: 由 header 派生的状态。
        first_line_number: 首行 1-based stdout 行号。

    Returns:
        不可变 download rows。

    Raises:
        _OwnerOutputError: 占位、form、日期或 SEC 身份非法时抛出。
    """

    if lines == ("  - （无）",):
        return ()
    if not lines or "  - （无）" in lines:
        raise _OwnerOutputError("download 空节占位非法", line_number=first_line_number)
    rows: list[DownloadEvidenceRow] = []
    for offset, line in enumerate(lines):
        line_number = first_line_number + offset
        if not line.startswith("  - "):
            raise _OwnerOutputError("download row 前缀非法", line_number=line_number)
        parts = line.removeprefix("  - ").split(" | ")
        fixed_prefixes = (
            "form=",
            "filing_date=",
            "report_date=",
            "status=",
            "downloaded_files=",
            "skipped_files=",
            "failed_files=",
        )
        if len(parts) < _DOWNLOAD_ROW_MIN_PART_COUNT or any(
            not parts[index + 1].startswith(prefix) for index, prefix in enumerate(fixed_prefixes)
        ):
            raise _OwnerOutputError("download row 固定字段非法", line_number=line_number)
        document_id = parts[0]
        accession = document_id.removeprefix("fil_")
        if _SEC_ACCESSION_PATTERN.fullmatch(accession) is None or document_id != f"fil_{accession}":
            raise _OwnerOutputError("download row SEC identity 非法", line_number=line_number)
        raw_form = parts[1].removeprefix("form=")
        if not raw_form:
            raise _OwnerOutputError("download row form 为空", line_number=line_number)
        try:
            canonical_form = normalize_form(raw_form)
        except ValueError as exc:
            raise _OwnerOutputError("download row form 非法", line_number=line_number) from exc
        try:
            filing_date = date.fromisoformat(parts[2].removeprefix("filing_date="))
        except ValueError as exc:
            raise _OwnerOutputError("download row filing_date 非法", line_number=line_number) from exc
        rows.append(
            DownloadEvidenceRow(
                document_id=document_id,
                accession=accession,
                canonical_form=canonical_form,
                filing_date=filing_date,
                section_status=status,
            )
        )
    return tuple(rows)


def _parse_material_header(
    lines: tuple[str, ...],
    *,
    prefix_count: int,
) -> tuple[Literal["ok", "skipped"], Literal["create", "update"], int]:
    """收窄 upload material 必需行与 files header。

    Args:
        lines: title anchor 后全部行。
        prefix_count: title 前噪声行数。

    Returns:
        owner status、material action 与唯一 files header 行号。

    Raises:
        _OwnerOutputError: 必需行、身份、状态、action 或 files header 非法时抛出。
    """

    required_prefixes = ("- pipeline: ", "- ticker: ", "- status: ", "- material_action: ")
    if len(lines) < _UPLOAD_MIN_LINE_COUNT:
        raise _OwnerOutputError("upload material 行数不足", line_number=prefix_count + 2)
    for index, prefix in enumerate(required_prefixes):
        if not lines[index].startswith(prefix) or lines[index].count(prefix) != 1:
            raise _OwnerOutputError("upload material 必需行非法", line_number=prefix_count + index + 2)
    if lines[0] != "- pipeline: upload_material" or lines[1] != "- ticker: AAPL":
        raise _OwnerOutputError("upload material identity 非法", line_number=prefix_count + 2)
    status_text = lines[2].removeprefix("- status: ")
    if status_text == "ok":
        owner_status: Literal["ok", "skipped"] = "ok"
    elif status_text == "skipped":
        owner_status = "skipped"
    else:
        raise _OwnerOutputError("upload material owner status 非法", line_number=prefix_count + 4)
    action_text = lines[3].removeprefix("- material_action: ")
    if action_text == "create":
        action: Literal["create", "update"] = "create"
    elif action_text == "update":
        action = "update"
    else:
        raise _OwnerOutputError("upload material action 非法", line_number=prefix_count + 5)
    files_indices = tuple(index for index, line in enumerate(lines) if line == "files:")
    if len(files_indices) != 1 or files_indices[0] < _UPLOAD_REQUIRED_LINE_COUNT:
        raise _OwnerOutputError("upload material files header 非法", line_number=prefix_count + 6)
    return owner_status, action, files_indices[0]


def _parse_material_optional_values(
    lines: tuple[str, ...],
    *,
    files_index: int,
    prefix_count: int,
) -> dict[str, str]:
    """按 owner 固定次序收窄 upload 可选标量。

    Args:
        lines: title anchor 后全部行。
        files_index: 已验证的 files header 行号。
        prefix_count: title 前噪声行数。

    Returns:
        不重复、顺序闭合的稀疏字段 mapping。

    Raises:
        _OwnerOutputError: 可选行未知、重复或重排时抛出。
    """

    optional_order = (
        "form_type",
        "material_name",
        "company_id",
        "company_name",
        "document_id",
        "internal_document_id",
        "primary_document",
        "uploaded_files",
        "document_version",
        "source_fingerprint",
        "filing_date",
        "report_date",
        "overwrite",
        "skip_reason",
        "message",
    )
    values: dict[str, str] = {}
    last_position = -1
    for offset, line in enumerate(
        lines[_UPLOAD_REQUIRED_LINE_COUNT:files_index],
        start=_UPLOAD_REQUIRED_LINE_COUNT,
    ):
        if not line.startswith("- ") or ": " not in line:
            raise _OwnerOutputError("upload material optional 行非法", line_number=prefix_count + offset + 2)
        name, value = line.removeprefix("- ").split(": ", 1)
        if name not in optional_order or name in values:
            raise _OwnerOutputError(
                "upload material optional 字段未知或重复",
                line_number=prefix_count + offset + 2,
            )
        position = optional_order.index(name)
        if position <= last_position:
            raise _OwnerOutputError("upload material optional 字段重排", line_number=prefix_count + offset + 2)
        last_position = position
        values[name] = value
    return values


def _parse_optional_material_date(value: str | None, *, line_number: int) -> date | None:
    """收窄 upload material 可选报告日期。

    Args:
        value: 缺席或 ISO 日期。
        line_number: 失败诊断行号。

    Returns:
        缺席为 null，否则返回解析日期。

    Raises:
        _OwnerOutputError: 日期文本非法时抛出。
    """

    try:
        return date.fromisoformat(value) if value is not None else None
    except ValueError as exc:
        raise _OwnerOutputError("upload material report_date 非法", line_number=line_number) from exc


def _parse_material_output(
    plan: AcceptancePlan,
    text: str,
) -> tuple[MaterialImportCommandEvidence, int]:
    """严格解析 upload_material 稀疏 formatter grammar。

    Args:
        plan: price/material identity 真源。
        text: 完整 stdout 文本。

    Returns:
        MaterialImportCommandEvidence 与 title 前缀行数。

    Raises:
        _OwnerOutputError: 必需行、可选顺序或 repository closure 非法时抛出。
    """

    lines, prefix_count = _anchored_owner_lines(text, "上传材料结果")
    owner_status, action, files_index = _parse_material_header(lines, prefix_count=prefix_count)
    values = _parse_material_optional_values(
        lines,
        files_index=files_index,
        prefix_count=prefix_count,
    )
    repository_source_fingerprint, repository_report_date, primary_sha256 = _price_material_repository_facts(plan)
    document_id = values.get("document_id")
    if document_id is None:
        raise _OwnerOutputError("upload material 缺稳定 document_id", line_number=prefix_count + 6)
    source_fingerprint = values.get("source_fingerprint")
    report_date = _parse_optional_material_date(
        values.get("report_date"),
        line_number=prefix_count + 6,
    )
    if owner_status == "ok":
        if source_fingerprint is None or report_date is None:
            raise _OwnerOutputError("upload material ok 缺条件字段", line_number=prefix_count + 6)
        if source_fingerprint != repository_source_fingerprint or report_date != repository_report_date:
            raise _OwnerOutputError("upload material owner/repository meta 不闭合", line_number=prefix_count + 6)
    return (
        MaterialImportCommandEvidence(
            owner_status=owner_status,
            material_action=action,
            document_id=document_id,
            source_fingerprint=source_fingerprint,
            report_date=report_date,
            price_json_sha256=plan.price_snapshot_sha256,
            price_material_sha256=plan.price_material_sha256,
            repository_primary_sha256=primary_sha256,
        ),
        prefix_count,
    )


def _price_material_repository_facts(plan: AcceptancePlan) -> tuple[str, date, str]:
    """仅通过 Fins 仓储边界读取 price material identity。

    Args:
        plan: canonical run root 与稳定 material ID。

    Returns:
        source fingerprint、report date 与 primary bytes SHA。

    Raises:
        _OwnerOutputError: meta、primary 或 blob 不可严格闭合时抛出。
    """

    root = Path(plan.run_root) / "data-workspace"
    source_repository = FsSourceDocumentRepository(root, create_directories=False)
    blob_repository = FsDocumentBlobRepository(root)
    try:
        meta_value: JsonValue = source_repository.get_source_meta(
            plan.ticker,
            plan.price_material_document_id,
            SourceKind.MATERIAL,
        )
        meta = _json_mapping(meta_value, "price material source meta")
        document_id = _json_string(
            _required_json(meta, "document_id", "price material source meta"),
            "price material source meta.document_id",
        )
        source_fingerprint = _require_sha256_text(
            _json_string(
                _required_json(meta, "source_fingerprint", "price material source meta"),
                "price material source meta.source_fingerprint",
            ),
            "price material source fingerprint",
        )
        report_date = date.fromisoformat(
            _json_string(
                _required_json(meta, "report_date", "price material source meta"),
                "price material source meta.report_date",
            )
        )
        primary = source_repository.get_primary_file(
            plan.ticker,
            plan.price_material_document_id,
            SourceKind.MATERIAL,
        )
        primary_name = Path(primary.uri).name
        blob = blob_repository.read_file_bytes(
            source_repository.get_source_handle(
                plan.ticker,
                plan.price_material_document_id,
                SourceKind.MATERIAL,
            ),
            primary_name,
        )
    except (ContractError, FileNotFoundError, OSError, ValueError) as exc:
        raise _OwnerOutputError("price material repository closure 失败") from exc
    if document_id != plan.price_material_document_id or not primary_name:
        raise _OwnerOutputError("price material repository identity 不闭合")
    primary_sha256 = hashlib.sha256(blob).hexdigest()
    if primary.sha256 is not None and primary.sha256 != primary_sha256:
        raise _OwnerOutputError("price material primary meta SHA 不闭合")
    return source_fingerprint, report_date, primary_sha256


def _parse_process_output(text: str) -> tuple[ProcessCommandEvidence, int]:
    """严格解析 process 六节 formatter grammar。

    Args:
        text: 完整 stdout 文本。

    Returns:
        ProcessCommandEvidence 与 title 前缀行数。

    Raises:
        _OwnerOutputError: summary/TODO/header/row 结构非法时抛出。
    """

    lines, prefix_count = _anchored_owner_lines(text, "全量处理结果")
    if (
        len(lines) < _PROCESS_MIN_LINE_COUNT
        or lines[0] != "- ticker: AAPL"
        or not lines[1].startswith("- status: ")
    ):
        raise _OwnerOutputError("process identity/status 结构非法", line_number=prefix_count + 2)
    status_text = lines[1].removeprefix("- status: ")
    if status_text == "ok":
        owner_status: Literal["ok", "cancelled"] = "ok"
    elif status_text == "cancelled":
        owner_status = "cancelled"
    else:
        raise _OwnerOutputError("process owner status 非法", line_number=prefix_count + 3)
    filing_summary = _parse_process_summary_line(lines[2], "filings", prefix_count + 4)
    if lines[3] == "- materials 处理: 未实现（TODO）":
        materials_todo = True
        material_summary = None
    else:
        materials_todo = False
        material_summary = _parse_process_summary_line(lines[3], "materials", prefix_count + 5)
    headers = (
        "成功处理的 filings:",
        "跳过的 filings:",
        "失败的 filings:",
        "成功处理的 materials:",
        "跳过的 materials:",
        "失败的 materials:",
    )
    indices = _unique_ordered_indices(lines, headers, prefix_count=prefix_count)
    if indices[0] != _PROCESS_SCALAR_LINE_COUNT:
        raise _OwnerOutputError("process sections 必须紧随 summaries", line_number=prefix_count + 6)
    identities: tuple[tuple[Literal["filing", "material"], Literal["processed", "skipped", "failed"]], ...] = (
        ("filing", "processed"),
        ("filing", "skipped"),
        ("filing", "failed"),
        ("material", "processed"),
        ("material", "skipped"),
        ("material", "failed"),
    )
    rows: list[ProcessEvidenceRow] = []
    for index, (source_kind, status) in enumerate(identities):
        start = indices[index] + 1
        end = indices[index + 1] if index < len(indices) - 1 else len(lines)
        rows.extend(
            _parse_process_section_rows(
                lines[start:end],
                source_kind=source_kind,
                status=status,
                first_line_number=prefix_count + start + 2,
            )
        )
    return (
        ProcessCommandEvidence(
            owner_status=owner_status,
            filing_summary=filing_summary,
            material_summary=material_summary,
            materials_todo=materials_todo,
            rows=tuple(rows),
        ),
        prefix_count,
    )


def _parse_process_summary_line(line: str, label: str, line_number: int) -> ProcessSummary:
    """解析一行 process counts summary。

    Args:
        line: 固定 summary 行。
        label: filings/materials。
        line_number: 1-based 诊断行号。

    Returns:
        严格 ProcessSummary。

    Raises:
        _OwnerOutputError: 行不匹配固定 grammar 时抛出。
    """

    match = re.fullmatch(
        rf"- {re.escape(label)} 汇总: total=([0-9]+), processed=([0-9]+), skipped=([0-9]+), failed=([0-9]+)",
        line,
    )
    if match is None:
        raise _OwnerOutputError("process summary 结构非法", line_number=line_number)
    return ProcessSummary(
        total=int(match.group(1)),
        processed=int(match.group(2)),
        skipped=int(match.group(3)),
        failed=int(match.group(4)),
    )


def _parse_process_section_rows(
    lines: tuple[str, ...],
    *,
    source_kind: Literal["filing", "material"],
    status: Literal["processed", "skipped", "failed"],
    first_line_number: int,
) -> tuple[ProcessEvidenceRow, ...]:
    """仅收窄 process row 首个 document_id。

    Args:
        lines: 当前 section rows。
        source_kind: 由 header 派生的来源。
        status: 由 header 派生的状态。
        first_line_number: 首行 1-based 诊断行号。

    Returns:
        不读取自由 tail 的 process rows。

    Raises:
        _OwnerOutputError: 占位或 document ID 前缀非法时抛出。
    """

    if lines == ("  - （无）",):
        return ()
    if not lines or "  - （无）" in lines:
        raise _OwnerOutputError("process 空节占位非法", line_number=first_line_number)
    rows: list[ProcessEvidenceRow] = []
    for offset, line in enumerate(lines):
        line_number = first_line_number + offset
        if not line.startswith("  - ") or " | " not in line:
            raise _OwnerOutputError("process row 前缀非法", line_number=line_number)
        document_id = line.removeprefix("  - ").split(" | ", 1)[0]
        if not document_id:
            raise _OwnerOutputError("process document_id 为空", line_number=line_number)
        rows.append(ProcessEvidenceRow(document_id=document_id, source_kind=source_kind, status=status))
    return tuple(rows)


def _owner_semantic_stop_reason(plan: AcceptancePlan, evidence: CommandEvidence) -> str | None:
    """对已解析 owner evidence 执行命令特定 hard-stop。

    Args:
        plan: price/material/repository identity。
        evidence: strict closed evidence union。

    Returns:
        通过时 null；失败时固定 stop reason。

    Raises:
        ContractError: receipt/repository 无法严格读取时抛出。
    """

    if isinstance(evidence, DownloadCommandEvidence):
        return _download_semantic_stop_reason(evidence)
    if isinstance(evidence, MaterialImportCommandEvidence):
        price = parse_price_snapshot(
            load_json_file(Path(plan.run_root) / "inputs/price-snapshot.json", label="run price snapshot")
        )
        if (
            evidence.document_id != plan.price_material_document_id
            or evidence.repository_primary_sha256 != plan.price_material_sha256
            or evidence.report_date not in {None, price.market_date}
        ):
            return "price_material_repository_mismatch"
        return None
    if evidence.owner_status != "ok" or evidence.materials_todo:
        return "process_semantic_failure"
    if evidence.filing_summary.failed > 0 or (
        evidence.material_summary is not None and evidence.material_summary.failed > 0
    ):
        return "process_failed_documents"
    if any(row.status == "failed" for row in evidence.rows):
        return "process_failed_documents"
    return _process_repository_stop_reason(plan, evidence)


def _download_semantic_stop_reason(evidence: DownloadCommandEvidence) -> str | None:
    """重放 download owner status、summary、required discovery 与窗口门禁。

    Args:
        evidence: 已 strict parse 的单条 download evidence。

    Returns:
        通过时 null；失败时固定 semantic stop reason。

    Raises:
        本函数不显式抛出异常。
    """

    if evidence.owner_status != "ok" or evidence.summary.failed > 0:
        return "download_semantic_failure"
    usable = tuple(row for row in evidence.rows if row.section_status in {"downloaded", "skipped"})
    required = tuple(form for form in evidence.canonical_forms if form != "8-K")
    if any(not any(row.canonical_form == form for row in usable) for form in required):
        return "download_required_discovery_missing"
    if any(
        row.canonical_form not in evidence.canonical_forms
        or not evidence.start <= row.filing_date <= evidence.end
        for row in usable
    ):
        return "download_discovery_outside_plan"
    return None


def _process_repository_stop_reason(plan: AcceptancePlan, evidence: ProcessCommandEvidence) -> str | None:
    """用 receipt discovery 与仓储 processed truth 闭合 process 结果。

    Args:
        plan: canonical run identity。
        evidence: strict process evidence。

    Returns:
        闭合时 null；否则固定 semantic stop reason。

    Raises:
        ContractError: download receipt 或仓储 ingress 非法时抛出。
    """

    download = _load_phase_receipt(Path(plan.run_root) / "phase-receipts/download.json", "download receipt")
    latest_discovery, usable_ids = _receipt_discovery(download)
    windows = _source_windows(plan)
    inventory = build_source_inventory_from_repositories(
        RepositoryInventoryRequest(
            fixture_id=f"live-{plan.fingerprint[:16]}",
            ticker=plan.ticker,
            company=plan.company,
            as_of=plan.as_of,
            live_freshness_claimed=True,
            source_windows=windows,
            latest_discovery=latest_discovery,
            source_repository=FsSourceDocumentRepository(
                Path(plan.run_root) / "data-workspace",
                create_directories=False,
            ),
            processed_repository=FsProcessedDocumentRepository(Path(plan.run_root) / "data-workspace"),
            blob_repository=FsDocumentBlobRepository(Path(plan.run_root) / "data-workspace"),
        )
    )
    expected_ids = {*usable_ids, plan.price_material_document_id}
    inventory_ids = {document.document_id for document in inventory.documents}
    process_ids = {row.document_id for row in evidence.rows if row.status in {"processed", "skipped"}}
    if inventory_ids != expected_ids or not expected_ids.issubset(process_ids):
        return "process_repository_inventory_mismatch"
    if any(
        not document.ingest_complete
        or not document.processed.exists
        or document.processed.reprocess_required
        or not document.processed.quality
        for document in inventory.documents
    ):
        return "process_repository_state_incomplete"
    return None


def _source_windows(plan: AcceptancePlan) -> tuple[SourceWindow, ...]:
    """从 plan as-of 与唯一 form 真源派生三组窗口。

    Args:
        plan: 固定 UTC as-of。

    Returns:
        与 phase builder 同构的三组 SourceWindow。

    Raises:
        本函数不显式抛出异常。
    """

    years = (5, 2, 2)
    return tuple(
        SourceWindow(forms, _subtract_calendar_years(plan.as_of.date(), year), plan.as_of.date())
        for forms, year in zip(_WINDOW_FORMS, years, strict=True)
    )


def _receipt_discovery(download: PhaseReceipt) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    """从 v3 download receipt 提取 latest discovery 与 usable IDs。

    Args:
        download: 已 strict parse 的 download phase receipt。

    Returns:
        固定 form/accession pairs 与全部 downloaded/skipped IDs。

    Raises:
        ContractError: receipt 不是三个 download records 或必需 form 缺失时抛出。
    """

    download_command_count = dict(PLANNED_PHASE_COMMAND_COUNTS)["download"]
    if download.phase_name != "download" or len(download.command_records) != download_command_count:
        raise ContractError("download receipt 必须精确含三个 command records")
    usable_rows: list[DownloadEvidenceRow] = []
    for record in download.command_records:
        if record.status != "passed" or not isinstance(record.evidence, DownloadCommandEvidence):
            raise ContractError("download receipt record/evidence 不闭合")
        usable_rows.extend(
            row for row in record.evidence.rows if row.section_status in {"downloaded", "skipped"}
        )
    pairs: list[tuple[str, str]] = []
    for form in ("10-K", "10-Q", "DEF 14A"):
        candidates = tuple(row for row in usable_rows if row.canonical_form == form)
        if not candidates:
            raise ContractError(f"download receipt 缺少 {form} usable discovery")
        latest = max(candidates, key=lambda row: (row.filing_date, row.document_id))
        pairs.append((form, latest.accession))
    ids = tuple(row.document_id for row in usable_rows)
    if len(ids) != len(set(ids)):
        raise ContractError("download receipt usable document_id 重复")
    return tuple(pairs), ids


def _write_run_skeleton(
    *,
    staging: Path,
    plan: AcceptancePlan,
    price_bytes: bytes,
    material_bytes: bytes,
    clock: Clock,
) -> None:
    """在同父 staging 中写完整可运行骨架。

    Args:
        staging: 本次 prepare 独占的临时目录。
        plan: 已严格 round-trip 的唯一 v2 plan。
        price_bytes: canonical 六字段价格 JSON。
        material_bytes: 确定性 Markdown 派生物。
        clock: prepare receipt 的注入时钟。

    Returns:
        无。

    Raises:
        ContractError: skeleton 自校验失败时抛出。
        OSError: 目录或文件无法写入时抛出。
    """

    fingerprint = plan.fingerprint
    for locator in (
        "inputs",
        "phase-receipts",
        "data-workspace",
        "write",
        "research/assets/research_templates",
    ):
        (staging / locator).mkdir(parents=True, exist_ok=False)
    _atomic_write_bytes(staging / "acceptance-plan.json", canonical_json_bytes(plan.to_json()))
    _atomic_write_bytes(staging / "inputs/price-snapshot.json", price_bytes)
    _atomic_write_bytes(staging / "inputs/price-snapshot.material.md", material_bytes)
    quality = build_pending_quality_review(f"live-{fingerprint[:16]}")
    parse_quality_review(quality)
    _atomic_write_bytes(staging / "quality-review.json", canonical_json_bytes(quality))
    recorded_at = _require_utc_datetime(clock.utc_now(), "prepare receipt time")
    prepare_receipt = PhaseReceipt(
        plan_fingerprint=fingerprint,
        phase_name="prepare",
        status="passed",
        started_at=recorded_at,
        ended_at=recorded_at,
        duration_seconds=0.0,
        remaining_wall_seconds=float(plan.max_wall_seconds),
        command_records=(),
    )
    _atomic_write_bytes(
        staging / "phase-receipts/prepare.json",
        canonical_json_bytes(prepare_receipt.to_json()),
    )


def _load_bound_plan(plan_path: Path, fingerprint: str) -> tuple[AcceptancePlan, str]:
    """读取 canonical plan 并与用户提供的 exact fingerprint 绑定。

    Args:
        plan_path: 精确 plan 文件路径。
        fingerprint: 用户显式提供的 canonical SHA-256。

    Returns:
        严格 v2 plan 与已验证 fingerprint。

    Raises:
        ContractError: 路径、JSON、canonical bytes 或 digest 不闭合时抛出。
        OSError: 文件读取失败时抛出。
    """

    expected = _require_sha256_text(fingerprint, "plan fingerprint")
    if ".." in PurePath(plan_path).parts or plan_path.is_symlink() or not plan_path.is_file():
        raise ContractError("plan 必须是无 .. 的普通非 symlink 文件")
    raw = plan_path.read_bytes()
    plan = parse_acceptance_plan(parse_json_bytes(raw, label="acceptance plan"))
    canonical = canonical_json_bytes(plan.to_json())
    if raw != canonical:
        raise ContractError("plan 文件必须使用 canonical JSON bytes")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected or plan.fingerprint != expected:
        raise ContractError("plan fingerprint mismatch")
    if plan_path.resolve(strict=True) != (Path(plan.run_root) / "acceptance-plan.json").resolve(strict=True):
        raise ContractError("plan 文件与 plan.run_root 不闭合")
    return plan, expected


def _assert_no_existing_run_receipts(plan: AcceptancePlan) -> None:
    """保证 runner 只从 atomic prepare receipt 后的新鲜状态启动。

    Args:
        plan: 唯一 v2 plan。

    Returns:
        无。

    Raises:
        ContractError: prepare receipt 不闭合或已有执行 receipt 时抛出。
    """

    receipt_root = Path(plan.run_root) / "phase-receipts"
    if receipt_root.is_symlink() or not receipt_root.is_dir():
        raise ContractError("phase-receipts 必须是普通目录")
    prepare = _load_phase_receipt(receipt_root / "prepare.json", "prepare receipt")
    if (
        prepare.phase_name != "prepare"
        or prepare.plan_fingerprint != plan.fingerprint
        or prepare.status != "passed"
    ):
        raise ContractError("prepare receipt 与 plan 不闭合")
    for _phase_name, filename in _PHASE_RECEIPT_FILES:
        path = receipt_root / filename
        if path.exists() or path.is_symlink():
            raise ContractError("run 不得覆盖已有 phase receipt")
    terminal = receipt_root / "verify.json"
    if terminal.exists() or terminal.is_symlink():
        raise ContractError("run 不得覆盖已有 terminal receipt")


def _load_and_validate_receipt_prefix(
    plan: AcceptancePlan,
    fingerprint: str,
) -> tuple[PhaseReceipt, ...]:
    """验证 ordered planned receipts 与可选 terminal receipt 的闭包。

    Args:
        plan: 唯一 v2 plan。
        fingerprint: 已验证 plan identity。

    Returns:
        evaluator 使用的六个 planned receipts 与可选 persisted terminal receipt。

    Raises:
        ContractError: 未知、跳过、重排、失败后续、argv 或 digest 不闭合时抛出。
    """

    config_root = resolve_package_config_path().resolve(strict=True)
    assert_package_input_fingerprints(plan.package_inputs)
    context = _ReceiptValidationContext(
        plan=plan,
        fingerprint=fingerprint,
        receipt_root=Path(plan.run_root) / "phase-receipts",
        config_root=config_root,
        python_executable=plan.phase_specs[0].commands[0][0],
    )
    prepare = _validate_receipt_root(context)
    receipts = _load_planned_receipt_prefix(context, prepare)
    terminal = _validate_terminal_receipt(context, receipts)
    return (*receipts, terminal) if terminal is not None else receipts


def _validate_receipt_root(context: _ReceiptValidationContext) -> PhaseReceipt:
    """验证 receipt 目录 inventory 与 prepare identity。

    Args:
        context: plan、目录与 runtime 绑定。

    Returns:
        已闭合 prepare receipt。

    Raises:
        ContractError: 目录、未知文件或 prepare receipt 非法时抛出。
    """

    receipt_root = context.receipt_root
    if receipt_root.is_symlink() or not receipt_root.is_dir():
        raise ContractError("phase-receipts 必须是普通非 symlink 目录")
    allowed_files = {"prepare.json", "verify.json", *(filename for _phase, filename in _PHASE_RECEIPT_FILES)}
    for path in receipt_root.iterdir():
        if path.is_symlink() or not path.is_file() or path.name not in allowed_files:
            raise ContractError(f"未知或非普通 phase receipt: {path.name}")
    prepare = _load_phase_receipt(receipt_root / "prepare.json", "prepare receipt")
    if (
        prepare.plan_fingerprint != context.fingerprint
        or prepare.phase_name != "prepare"
        or prepare.status != "passed"
    ):
        raise ContractError("prepare receipt 与 plan 不闭合")
    return prepare


def _load_planned_receipt_prefix(
    context: _ReceiptValidationContext,
    prepare: PhaseReceipt,
) -> tuple[PhaseReceipt, ...]:
    """加载并机械闭合 ordered planned receipt 成功前缀。

    Args:
        context: plan、目录与 runtime 绑定。
        prepare: 已验证 prepare receipt。

    Returns:
        全部存在的 ordered planned receipts。

    Raises:
        ContractError: skip/reorder、argv/digest 或时间预算不闭合时抛出。
    """

    receipts: list[PhaseReceipt] = []
    previous_end = prepare.ended_at
    previous_remaining = prepare.remaining_wall_seconds
    stopped = False
    for spec, (phase_name, filename) in zip(context.plan.phase_specs, _PHASE_RECEIPT_FILES, strict=True):
        path = context.receipt_root / filename
        if not path.exists():
            stopped = True
            continue
        if stopped:
            raise ContractError("phase receipts 不得 skip/reorder")
        receipt = _load_phase_receipt(path, f"{phase_name} receipt")
        expected_safe, expected_digests = safe_argv_and_digests(
            spec.commands,
            python_executable=context.python_executable,
            run_root=context.plan.run_root,
            package_config_root=context.config_root,
        )
        if receipt.plan_fingerprint != context.fingerprint or receipt.phase_name != phase_name:
            raise ContractError(f"{phase_name} receipt identity/argv drift")
        _validate_record_argv_prefix(receipt, expected_safe, expected_digests, phase_name)
        _validate_persisted_phase_evidence(context.plan, spec, receipt)
        if receipt.started_at < previous_end or receipt.remaining_wall_seconds > previous_remaining:
            raise ContractError(f"{phase_name} receipt 时间/剩余预算非单调")
        receipts.append(receipt)
        previous_end = receipt.ended_at
        previous_remaining = receipt.remaining_wall_seconds
        if receipt.status != "passed":
            stopped = True
    return tuple(receipts)


def _validate_terminal_receipt(
    context: _ReceiptValidationContext,
    receipts: tuple[PhaseReceipt, ...],
) -> PhaseReceipt | None:
    """要求完整 planned 成功前缀并验证可选 terminal receipt。

    Args:
        context: plan、目录与 runtime 绑定。
        receipts: 已按顺序加载的 planned receipts。

    Returns:
        已存在且闭合的首次 terminal receipt；尚未由 outer run 写入时为 null。

    Raises:
        ContractError: planned 前缀不完整或 terminal identity 不闭合时抛出。
    """

    terminal_path = context.receipt_root / "verify.json"
    if len(receipts) != len(context.plan.phase_specs) or any(item.status != "passed" for item in receipts):
        if terminal_path.exists():
            raise ContractError("terminal receipt 只能位于完整成功前缀之后")
        raise ContractError("live verify 要求全部 planned phase 成功")
    if terminal_path.exists():
        terminal = _load_phase_receipt(terminal_path, "terminal verify receipt")
        previous_end = receipts[-1].ended_at
        previous_remaining = receipts[-1].remaining_wall_seconds
        terminal_command = build_terminal_verify_command(
            plan=context.plan,
            fingerprint=context.fingerprint,
            python_executable=context.python_executable,
        )
        expected_safe, expected_digests = safe_argv_and_digests(
            (terminal_command,),
            python_executable=context.python_executable,
            run_root=context.plan.run_root,
            package_config_root=context.config_root,
        )
        if (
            terminal.plan_fingerprint != context.fingerprint
            or terminal.phase_name != TERMINAL_ACTION
            or terminal.started_at < previous_end
            or terminal.remaining_wall_seconds > previous_remaining
        ):
            raise ContractError("terminal verify receipt 不闭合")
        if terminal.status != "passed" or len(terminal.command_records) != 1:
            raise ContractError("persisted terminal receipt 必须是精确单 record passed 终态")
        terminal_record = terminal.command_records[0]
        if (
            terminal_record.status != "passed"
            or terminal_record.exit_code != 0
            or terminal_record.stop_reason is not None
            or terminal_record.termination_action is not None
            or terminal_record.partial_by_timeout
        ):
            raise ContractError("persisted terminal record lifecycle 必须完整 passed")
        _validate_record_argv_prefix(terminal, expected_safe, expected_digests, TERMINAL_ACTION)
        _validate_null_command_evidence(terminal, TERMINAL_ACTION)
        return terminal
    return None


def _validate_persisted_phase_evidence(
    plan: AcceptancePlan,
    spec: PhaseSpec,
    receipt: PhaseReceipt,
) -> None:
    """在 canonical receipt reload 边界重放 phase/domain evidence 语义。

    Args:
        plan: 唯一 plan、price 与 repository identity。
        spec: 当前 phase 的 raw canonical argv 真源。
        receipt: 已完成 schema/argv/lifecycle 校验的 persisted receipt。

    Returns:
        无。

    Raises:
        ContractError: evidence 缺失、跨类型、argv/window 或 owner/repository 语义不闭合时抛出。
    """

    if spec.phase_name not in {"download", "price-snapshot-import", "process"}:
        _validate_null_command_evidence(receipt, spec.phase_name)
        return
    for index, record in enumerate(receipt.command_records):
        command = spec.commands[index]
        if record.status != "passed":
            continue
        evidence = record.evidence
        if spec.phase_name == "download":
            if not isinstance(evidence, DownloadCommandEvidence):
                raise ContractError("download passed record 必须含 download evidence")
            _validate_persisted_download_evidence(command, evidence)
        elif spec.phase_name == "price-snapshot-import":
            if not isinstance(evidence, MaterialImportCommandEvidence):
                raise ContractError("material passed record 必须含 material evidence")
            _validate_persisted_material_evidence(plan, command, evidence)
        else:
            if not isinstance(evidence, ProcessCommandEvidence):
                raise ContractError("process passed record 必须含 process evidence")
            _require_persisted_semantic_pass(plan, evidence, "process")


def _validate_null_command_evidence(receipt: PhaseReceipt, label: str) -> None:
    """要求无 owner domain 的 phase/terminal records 不携带 evidence。

    Args:
        receipt: 已 strict parse 的 persisted receipt。
        label: phase 诊断标签。

    Returns:
        无。

    Raises:
        ContractError: 任一 record 携带 domain evidence 时抛出。
    """

    if any(record.evidence is not None for record in receipt.command_records):
        raise ContractError(f"{label} command evidence 必须为 null")


def _validate_persisted_download_evidence(
    command: Command,
    evidence: DownloadCommandEvidence,
) -> None:
    """把 persisted download evidence 精确绑定 raw argv 并重放语义。

    Args:
        command: 对应 plan-owned raw download argv。
        evidence: persisted download evidence。

    Returns:
        无。

    Raises:
        ContractError: forms/canonical forms/window/status/summary/discovery 不闭合时抛出。
    """

    planned_forms = _command_flag_values(command, "--forms")
    try:
        canonical_forms = tuple(normalize_form(form) for form in planned_forms)
        start = date.fromisoformat(_command_flag_values(command, "--start")[0])
        end = date.fromisoformat(_command_flag_values(command, "--end")[0])
    except ValueError as exc:
        raise ContractError("download plan argv form/window 非法") from exc
    if (
        evidence.ticker != _TICKER
        or evidence.planned_forms != planned_forms
        or evidence.canonical_forms != canonical_forms
        or evidence.start != start
        or evidence.end != end
    ):
        raise ContractError("download persisted evidence 与 raw argv/window 不闭合")
    _require_persisted_semantic_pass(None, evidence, "download")


def _validate_persisted_material_evidence(
    plan: AcceptancePlan,
    command: Command,
    evidence: MaterialImportCommandEvidence,
) -> None:
    """重放 persisted material evidence 的 argv、纯语义与当前仓储闭包。

    Args:
        plan: 唯一 price/material identity。
        command: 对应 plan-owned upload argv。
        evidence: persisted material evidence。

    Returns:
        无。

    Raises:
        ContractError: argv、owner evidence 或当前 repository truth 不闭合时抛出。
    """

    document_ids = _command_flag_values(command, "--document-id")
    report_dates = _command_flag_values(command, "--report-date")
    price = parse_price_snapshot(
        load_json_file(Path(plan.run_root) / "inputs/price-snapshot.json", label="run price snapshot")
    )
    if (
        document_ids != (plan.price_material_document_id,)
        or report_dates != (price.market_date.isoformat(),)
        or evidence.price_json_sha256 != plan.price_snapshot_sha256
        or evidence.price_material_sha256 != plan.price_material_sha256
    ):
        raise ContractError("material persisted evidence 与 plan/raw argv 不闭合")
    _require_persisted_semantic_pass(plan, evidence, "material")
    source_fingerprint, report_date, primary_sha256 = _price_material_repository_facts(plan)
    if evidence.repository_primary_sha256 != primary_sha256:
        raise ContractError("material persisted evidence 与当前 repository primary SHA 不闭合")
    if evidence.owner_status == "ok" and (
        evidence.source_fingerprint != source_fingerprint or evidence.report_date != report_date
    ):
        raise ContractError("material persisted evidence 与当前 repository meta 不闭合")


def _require_persisted_semantic_pass(
    plan: AcceptancePlan | None,
    evidence: CommandEvidence,
    label: str,
) -> None:
    """把 persisted domain evidence 重放到无写副作用的 semantic gate。

    Args:
        plan: material/process 所需 plan；download 无需 plan。
        evidence: strict evidence union 成员。
        label: domain 诊断标签。

    Returns:
        无。

    Raises:
        ContractError: evidence 类型/plan 或 semantic/repository closure 不通过时抛出。
    """

    if isinstance(evidence, DownloadCommandEvidence):
        reason = _download_semantic_stop_reason(evidence)
    else:
        if plan is None:
            raise ContractError(f"{label} persisted semantic gate 缺 plan")
        reason = _owner_semantic_stop_reason(plan, evidence)
    if reason is not None:
        raise ContractError(f"{label} persisted semantic failure: {reason}")


def _validate_record_argv_prefix(
    receipt: PhaseReceipt,
    expected_safe: CommandMatrix,
    expected_digests: tuple[str, ...],
    label: str,
) -> None:
    """把 v3 records 逐条绑定到 plan command 前缀。

    Args:
        receipt: 已 strict parse 的 v3 receipt。
        expected_safe: 全量 planned placeholder argv。
        expected_digests: 全量 raw argv digests。
        label: phase 诊断名称。

    Returns:
        无。

    Raises:
        ContractError: record 数量、index、argv 或 digest 不闭合时抛出。
    """

    if len(receipt.command_records) > len(expected_safe):
        raise ContractError(f"{label} command records 超出计划")
    for index, record in enumerate(receipt.command_records):
        if (
            record.command_index != index
            or record.safe_argv != expected_safe[index]
            or record.argv_digest != expected_digests[index]
        ):
            raise ContractError(f"{label} command record argv/digest drift")


def _load_phase_receipt(path: Path, label: str) -> PhaseReceipt:
    """从固定路径严格加载一份 canonical phase receipt。

    Args:
        path: 固定 receipt 路径。
        label: 错误上下文。

    Returns:
        严格 v3 receipt。

    Raises:
        ContractError: 文件或 canonical bytes 不闭合时抛出。
        OSError: 文件读取失败时抛出。
    """

    raw = path.read_bytes() if path.is_file() and not path.is_symlink() else b""
    if not raw:
        raise ContractError(f"{label} 缺失或为空")
    receipt = parse_phase_receipt(parse_json_bytes(raw, label=label))
    if raw != canonical_json_bytes(receipt.to_json()):
        raise ContractError(f"{label} 必须是 canonical JSON bytes")
    return receipt


def _write_phase_receipt(plan: AcceptancePlan, receipt: PhaseReceipt) -> None:
    """把一份严格 receipt 原子写入固定 phase 文件名。

    Args:
        plan: 唯一 v2 plan。
        receipt: 待持久化 receipt。

    Returns:
        无。

    Raises:
        ContractError: phase 未知、fingerprint 不匹配或目标已存在时抛出。
        OSError: 原子写入失败时抛出。
    """

    filename_by_phase = dict(_PHASE_RECEIPT_FILES)
    filename_by_phase[TERMINAL_ACTION] = "verify.json"
    if receipt.phase_name not in filename_by_phase:
        raise ContractError("不得写入未知 phase receipt")
    if receipt.plan_fingerprint != plan.fingerprint:
        raise ContractError("phase receipt plan fingerprint drift")
    path = Path(plan.run_root) / "phase-receipts" / filename_by_phase[receipt.phase_name]
    if path.exists() or path.is_symlink():
        raise ContractError(f"不得覆盖已有 phase receipt: {path.name}")
    parsed = parse_phase_receipt(receipt.to_json())
    if parsed != receipt:
        raise ContractError("phase receipt strict round trip 不闭合")
    _atomic_write_bytes(path, canonical_json_bytes(receipt.to_json()))


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """在目标同父目录原子写入一份新文件。

    Args:
        path: 精确目标文件。
        payload: 待写字节。

    Returns:
        无。

    Raises:
        ContractError: 父目录非法或目标已存在时抛出。
        OSError: 临时文件写入或 rename 失败时抛出。
    """

    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ContractError("atomic write parent 必须是普通目录")
    if path.exists() or path.is_symlink():
        raise ContractError(f"atomic write 不得覆盖: {path.name}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise


def _atomic_replace_bytes(path: Path, payload: bytes) -> None:
    """原子创建或替换唯一可重复生成的 acceptance receipt。

    Args:
        path: 固定 ``acceptance-receipt.json`` 路径。
        payload: 新一次显式 verification time 对应的 canonical bytes。

    Returns:
        无。

    Raises:
        ContractError: 路径不是固定 acceptance receipt 或现有目标为 symlink/非普通文件时抛出。
        OSError: 临时写入或原子 replace 失败时抛出。
    """

    if path.name != "acceptance-receipt.json":
        raise ContractError("atomic replace 只允许 acceptance-receipt.json")
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ContractError("acceptance receipt parent 必须是普通目录")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ContractError("acceptance receipt 目标必须是普通文件或不存在")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise


def _atomic_write_or_assert_same(path: Path, payload: bytes) -> None:
    """原子创建 canonical source inventory 或接受相同既有字节。

    Args:
        path: 固定 ``source-inventory.json`` 路径。
        payload: 当前 frozen inventory canonical bytes。

    Returns:
        新建成功或既有字节完全相同时返回。

    Raises:
        ContractError: 路径、symlink 或既有非同字节内容非法时抛出。
        OSError: 原子写入失败时抛出。
    """

    if path.name != "source-inventory.json":
        raise ContractError("atomic source inventory 目标非法")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ContractError("source inventory 目标必须是普通文件或不存在")
    if path.exists():
        if path.read_bytes() != payload:
            raise ContractError("既有 source inventory 与当前 frozen inventory 不同")
        return
    _atomic_write_bytes(path, payload)


def _stderr_stop_reason(stderr: bytes) -> str:
    """把任意 stderr 收窄为固定、无原文的停止分类。

    Args:
        stderr: 子进程 stderr；只用于判断是否为空。

    Returns:
        不含输入原文或秘密的固定代码。

    Raises:
        本函数不显式抛出异常。
    """

    return "command_failed_with_stderr" if stderr else "command_failed"


def _verify_fixture(fixture_root: Path) -> JsonObject:
    """在临时物化产物上执行固定 deterministic fixture verify。

    Args:
        fixture_root: 固定脱敏 fixture 根。

    Returns:
        字节稳定 evaluator receipt JSON。

    Raises:
        ContractError: fixture policy 或严格输入不闭合时抛出。
        OSError: fixture 或临时物化失败时抛出。
    """

    root = Path(_canonical_absolute_path(fixture_root, "fixture_root", require_exists=True))
    if root.is_symlink() or not root.is_dir():
        raise ContractError("fixture root 必须是普通非 symlink 目录")
    budget = BudgetLimits(
        max_model_requests=_FIXTURE_MAX_MODEL_REQUESTS,
        max_total_tokens=_FIXTURE_MAX_TOTAL_TOKENS,
        max_estimated_cost=_FIXTURE_MAX_ESTIMATED_COST,
        budget_currency=_FIXTURE_BUDGET_CURRENCY,
    )
    repository_root = Path(__file__).resolve().parent.parent
    workspace = repository_root / _FIXTURE_RUNTIME_LOCATOR
    temporary_parent = workspace.parent
    temporary_parent.mkdir(parents=True, exist_ok=True)
    lock = temporary_parent / f"{workspace.name}.lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        owner = lock / "owner.json"
        diagnostic = "owner metadata unavailable"
        if owner.is_file() and not owner.is_symlink():
            try:
                payload = load_json_file(owner, label="fixture lock owner")
                diagnostic = _json_string(_required_json(payload, "run_label", "fixture lock owner"), "run_label")
            except (ContractError, OSError):
                diagnostic = "owner metadata invalid"
        raise ContractError(f"fixture verify 已有并发或 stale lock: {diagnostic}") from exc
    owner_payload: JsonObject = {
        "pid": os.getpid(),
        "started_at": format_utc(datetime.now(tz=UTC)),
        "run_label": "aapl-fixture-verify",
    }
    _atomic_write_bytes(lock / "owner.json", canonical_json_bytes(owner_payload))
    try:
        if workspace.exists() or workspace.is_symlink():
            raise ContractError("fixture verify 固定临时目录存在 stale 状态")
        materialize_research_workspace(
            _TEMPLATE,
            workspace_root=workspace,
            ticker=_TICKER,
            company=_COMPANY,
        )
        inputs = load_fixture_inputs(
            FixtureInputRequest(
                fixture_root=root,
                artifact_root=workspace / "assets/research_templates",
                approved_budget=budget,
                max_wall_seconds=_FIXTURE_MAX_WALL_SECONDS,
                actual_wall_seconds=_FIXTURE_ACTUAL_WALL_SECONDS,
            )
        )
        if (
            not inputs.contract.deterministic
            or inputs.contract.external_calls_allowed
            or inputs.contract.live_freshness_claimed
            or inputs.inventory.live_freshness_claimed
        ):
            raise ContractError("fixture verify policy 必须 deterministic/offline/non-live")
        evaluated_at = inputs.inventory.as_of + _FIXTURE_EVALUATION_OFFSET
        result = evaluate_acceptance(inputs, evaluated_at=evaluated_at).to_json()
    except BaseException as exc:
        cleanup_error = _cleanup_fixture_runtime(workspace, lock)
        if cleanup_error is not None:
            exc.add_note("fixture cleanup failed")
        raise
    cleanup_error = _cleanup_fixture_runtime(workspace, lock)
    if cleanup_error is not None:
        raise OSError("fixture cleanup failed")
    return result


def _cleanup_fixture_runtime(workspace: Path, lock: Path) -> str | None:
    """清理本次精确 fixture runtime 且不掩盖调用方主异常。

    Args:
        workspace: 精确固定物化目录。
        lock: 本进程已取得的精确 lock 目录。

    Returns:
        成功为 null；失败为静态诊断码。

    Raises:
        本函数把 OSError 收窄为静态返回值，不显式抛出。
    """

    try:
        if workspace.is_dir() and not workspace.is_symlink():
            shutil.rmtree(workspace)
        owner = lock / "owner.json"
        if owner.is_file() and not owner.is_symlink():
            owner.unlink()
        lock.rmdir()
    except OSError:
        return "cleanup_os_error"
    return None


def _evaluate_live_plan(
    plan: AcceptancePlan,
    receipts: tuple[PhaseReceipt, ...],
    *,
    clock: Clock,
) -> EvaluationResult:
    """通过 Fins 仓储协议构建 live 输入并调用纯 evaluator。

    Args:
        plan: 唯一 v2 plan。
        receipts: 已闭合的六阶段成功 receipts。
        clock: 显式验证时钟。

    Returns:
        evaluator 的结构化三态结果。

    Raises:
        ContractError: 仓储、产物、价格 material 或 live policy 不闭合时抛出。
        OSError: 只读生产产物失败时抛出。
    """

    run_root = Path(plan.run_root)
    data_workspace = run_root / "data-workspace"
    source_repository = FsSourceDocumentRepository(data_workspace, create_directories=False)
    processed_repository = FsProcessedDocumentRepository(data_workspace)
    blob_repository = FsDocumentBlobRepository(data_workspace)
    windows = _source_windows(plan)
    fixture_id = f"live-{plan.fingerprint[:16]}"
    download_receipt = next((receipt for receipt in receipts if receipt.phase_name == "download"), None)
    if download_receipt is None:
        raise ContractError("live verify 缺 download receipt")
    latest_discovery, _usable_ids = _receipt_discovery(download_receipt)
    inventory = build_source_inventory_from_repositories(
        RepositoryInventoryRequest(
            fixture_id=fixture_id,
            ticker=plan.ticker,
            company=plan.company,
            as_of=plan.as_of,
            live_freshness_claimed=True,
            source_windows=windows,
            latest_discovery=latest_discovery,
            source_repository=source_repository,
            processed_repository=processed_repository,
            blob_repository=blob_repository,
        )
    )
    strict_inventory = parse_source_inventory(inventory.to_json())
    if strict_inventory != inventory:
        raise ContractError("live source inventory strict round trip 不闭合")
    _atomic_write_or_assert_same(
        run_root / "source-inventory.json",
        canonical_json_bytes(strict_inventory.to_json()),
    )
    price = parse_price_snapshot(load_json_file(run_root / "inputs/price-snapshot.json", label="live price"))
    material_candidates = tuple(
        document
        for document in inventory.documents
        if document.document_id == plan.price_material_document_id
        and document.source_kind == "material"
        and document.primary_file_sha256 == plan.price_material_sha256
    )
    if len(material_candidates) != 1:
        raise ContractError("price material identity/primary SHA 不闭合")
    contract = build_live_acceptance_contract(
        plan=plan,
        fixture_id=fixture_id,
        price=price,
        material_document_id=plan.price_material_document_id,
    )
    if contract.deterministic or not contract.external_calls_allowed or not contract.live_freshness_claimed:
        raise ContractError("live verify policy 必须 non-deterministic/external/live-freshness")
    quality = parse_quality_review(load_json_file(run_root / "quality-review.json", label="live quality review"))
    manifest = parse_owner_write_manifest(load_json_file(run_root / "write/manifest.json", label="write manifest"))
    summary = parse_owner_run_summary(load_json_file(run_root / "write/run_summary.json", label="run summary"))
    report_path = run_root / "write/AAPL_qual_report.md"
    if report_path.is_symlink() or not report_path.is_file():
        raise ContractError("live report 必须是固定普通非 symlink 文件")
    report_text = report_path.read_text(encoding="utf-8")
    artifact_root = run_root / "research/assets/research_templates"
    research_artifacts = inspect_research_artifacts(
        artifact_root,
        required_artifacts=plan.required_research_artifacts,
    )
    runtime = _build_runtime_evidence(plan, receipts)
    acceptance_outputs: tuple[JsonValue, ...] = tuple(item.to_json() for item in receipts)
    inputs = AcceptanceInputs(
        contract=contract,
        inventory=inventory,
        price_snapshot=price,
        quality_review=quality,
        write_manifest=manifest,
        run_summary=summary,
        report_text=report_text,
        research_artifacts=research_artifacts,
        runtime=runtime,
        acceptance_owned_outputs=acceptance_outputs,
    )
    evaluated_at = _require_utc_datetime(clock.utc_now(), "evaluated_at")
    return evaluate_acceptance(inputs, evaluated_at=evaluated_at)


def _build_runtime_evidence(
    plan: AcceptancePlan,
    receipts: tuple[PhaseReceipt, ...],
) -> RuntimeEvidence:
    """仅由 persisted 首末 receipts 构建原始自动运行 wall evidence。

    Args:
        plan: 批准预算与 whole-run ceiling 真源。
        receipts: 已验证 planned receipts 与可选首次 terminal receipt。

    Returns:
        不使用当前 verify 时钟的 end-to-end runtime evidence。

    Raises:
        ContractError: receipt 序列为空时抛出。
    """

    if not receipts:
        raise ContractError("live runtime evidence 缺少 phase receipts")
    actual_wall_seconds = max(0.0, (receipts[-1].ended_at - receipts[0].started_at).total_seconds())
    return RuntimeEvidence(
        approved_budget=plan.budget,
        max_wall_seconds=plan.max_wall_seconds,
        actual_wall_seconds=actual_wall_seconds,
        phase_receipts=receipts,
    )


def _validate_fixed_target(ticker: str, company: str, template: str) -> None:
    """验证 prepare 只能构建固定 AAPL/technology 验收。

    Args:
        ticker: 用户请求 ticker。
        company: 用户请求公司名。
        template: 用户请求研究模板。

    Returns:
        无。

    Raises:
        ContractError: 任一身份不等于固定 contract 时抛出。
    """

    if ticker != _TICKER or company != _COMPANY or template != _TEMPLATE:
        raise ContractError("prepare 只允许 AAPL / Apple Inc. / technology")


def _require_utc_datetime(value: datetime, label: str) -> datetime:
    """收窄带时区且已规范到 UTC 的 datetime。

    Args:
        value: 待验证时间。
        label: 错误上下文标签。

    Returns:
        秒精度 UTC datetime。

    Raises:
        ContractError: 时间不带时区、不在 UTC 或含微秒时抛出。
    """

    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractError(f"{label} 必须带时区")
    normalized = value.astimezone(UTC)
    if value.utcoffset() != timedelta(0) or value.microsecond != 0:
        raise ContractError(f"{label} 必须是秒精度 UTC")
    return normalized


def _subtract_calendar_years(value: date, years: int) -> date:
    """按日历年回退并对闰日 clamp。

    Args:
        value: 原日期。
        years: 正整数回退年数。

    Returns:
        目标年同月同日或该月最后合法日。

    Raises:
        ContractError: years 不为正整数时抛出。
    """

    if isinstance(years, bool) or years <= 0:
        raise ContractError("calendar years 必须是正整数")
    target_year = value.year - years
    try:
        return value.replace(year=target_year)
    except ValueError:
        return value.replace(year=target_year, day=28)


def _canonical_absolute_path(path: Path, label: str, *, require_exists: bool) -> str:
    """规范化并验证一个 absolute POSIX path。

    Args:
        path: 待验证路径。
        label: 错误上下文标签。
        require_exists: 是否要求路径当前存在。

    Returns:
        canonical absolute POSIX 字符串。

    Raises:
        ContractError: 路径含 ``..``、不存在或不能规范化时抛出。
    """

    if ".." in PurePath(path).parts:
        raise ContractError(f"{label} 不得包含 ..")
    try:
        resolved = path.resolve(strict=require_exists)
    except OSError as exc:
        raise ContractError(f"{label} 无法解析") from exc
    if not resolved.is_absolute():
        raise ContractError(f"{label} 必须是绝对路径")
    return resolved.as_posix()


def _validate_new_run_root(path: Path, repository_root: Path) -> str:
    """验证 prepare 目标位于仓库固定父目录且尚不存在。

    Args:
        path: 用户请求 run root。
        repository_root: 当前仓库根。

    Returns:
        canonical absolute run root。

    Raises:
        ContractError: 父目录、run-id、symlink、containment 或存在性非法时抛出。
    """

    if path.exists() or path.is_symlink():
        raise ContractError("run root 必须尚不存在")
    run_id = path.name
    if _RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ContractError("run-id 只能使用安全字母数字点下划线横线")
    repository = Path(_canonical_absolute_path(repository_root, "repository_root", require_exists=True))
    expected_parent = repository / _RUN_PARENT_LOCATOR
    if expected_parent.is_symlink() or not expected_parent.is_dir():
        raise ContractError("固定 acceptance run parent 必须存在且非 symlink")
    canonical_parent = expected_parent.resolve(strict=True)
    if path.parent.resolve(strict=True) != canonical_parent:
        raise ContractError("run root 必须精确位于固定 acceptance parent")
    if _has_symlink_component(canonical_parent, repository):
        raise ContractError("acceptance run parent 祖先不得含 symlink")
    canonical = path.resolve(strict=False)
    if canonical.parent != canonical_parent:
        raise ContractError("run root canonical parent drift")
    return canonical.as_posix()


def _validate_existing_run_root(path: Path, repository_root: Path) -> str:
    """验证已 prepare 的 run root 仍位于固定父目录。

    Args:
        path: plan 声明 run root。
        repository_root: 当前仓库根。

    Returns:
        canonical existing run root。

    Raises:
        ContractError: run root 不存在、为 symlink 或越界时抛出。
    """

    repository = Path(_canonical_absolute_path(repository_root, "repository_root", require_exists=True))
    expected_parent = (repository / _RUN_PARENT_LOCATOR).resolve(strict=True)
    if path.is_symlink() or not path.is_dir():
        raise ContractError("existing run root 必须是普通非 symlink 目录")
    canonical = path.resolve(strict=True)
    if canonical.parent != expected_parent or _RUN_ID_PATTERN.fullmatch(canonical.name) is None:
        raise ContractError("existing run root containment drift")
    return canonical.as_posix()


def _has_symlink_component(path: Path, stop: Path) -> bool:
    """检查从 stop 到 path 的现有组件是否含 symlink。

    Args:
        path: 待检查后代路径。
        stop: 不继续向上的祖先边界。

    Returns:
        任一组件为 symlink 时返回 ``True``。

    Raises:
        ContractError: path 不位于 stop 下时抛出。
    """

    try:
        relative = path.relative_to(stop)
    except ValueError as exc:
        raise ContractError("路径不在仓库根内") from exc
    current = stop
    if current.is_symlink():
        return True
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _validate_price_input(path: Path) -> Path:
    """验证 prepare 唯一外部输入是普通非 symlink JSON 文件。

    Args:
        path: 用户显式 price snapshot 路径。

    Returns:
        canonical 普通文件路径。

    Raises:
        ContractError: 路径含 ``..``、为 symlink 或不是普通文件时抛出。
    """

    if ".." in PurePath(path).parts or path.is_symlink() or not path.is_file():
        raise ContractError("price snapshot 必须是无 .. 的普通非 symlink 文件")
    return path.resolve(strict=True)


def _validate_price_freshness(price: PriceSnapshot, as_of: datetime) -> None:
    """验证价格六字段时间不未来且未超过自身 max-age。

    Args:
        price: 严格价格快照。
        as_of: 固定 UTC as-of。

    Returns:
        无。

    Raises:
        ContractError: captured/market date 未来或超龄时抛出。
    """

    normalized_as_of = _require_utc_datetime(as_of, "as_of")
    max_age = timedelta(days=price.max_age_days)
    if price.captured_at > normalized_as_of or price.market_date > normalized_as_of.date():
        raise ContractError("price snapshot 时间不得晚于 as-of")
    if normalized_as_of - price.captured_at > max_age:
        raise ContractError("price snapshot captured_at 已超龄")
    if normalized_as_of.date() - price.market_date > max_age:
        raise ContractError("price snapshot market_date 已超龄")


def _price_snapshot_to_json(price: PriceSnapshot) -> JsonObject:
    """把六字段价格快照转换为无损 canonical JSON 形状。

    Args:
        price: 严格价格快照。

    Returns:
        Decimal 以字符串保存的六字段 JSON。

    Raises:
        ContractError: captured_at 不能规范化时抛出。
    """

    return {
        "price": str(price.price),
        "currency": price.currency,
        "market_date": price.market_date.isoformat(),
        "source_url": price.source_url,
        "captured_at": format_utc(price.captured_at),
        "max_age_days": price.max_age_days,
    }


def _render_price_material(price: PriceSnapshot, canonical_sha256: str) -> bytes:
    """确定性渲染可由 upload_material 接受的无损 Markdown。

    Args:
        price: 严格六字段价格快照。
        canonical_sha256: canonical JSON SHA-256。

    Returns:
        UTF-8 Markdown 字节。

    Raises:
        ContractError: SHA-256 或 captured_at 非法时抛出。
    """

    _require_sha256_text(canonical_sha256, "price canonical sha256")
    lines = (
        "# AAPL price snapshot",
        "",
        f"canonical_json_sha256: {canonical_sha256}",
        f"price: {price.price}",
        f"currency: {price.currency}",
        f"market_date: {price.market_date.isoformat()}",
        f"source_url: {price.source_url}",
        f"captured_at: {format_utc(price.captured_at)}",
        f"max_age_days: {price.max_age_days}",
        "",
    )
    return "\n".join(lines).encode("utf-8")


def _validate_budget(budget: BudgetLimits) -> None:
    """验证全部 live 预算显式、正值且币种规范。

    Args:
        budget: plan 预算。

    Returns:
        无。

    Raises:
        ContractError: 请求、Token、成本或币种非法时抛出。
    """

    if budget.max_model_requests <= 0 or budget.max_total_tokens <= 0:
        raise ContractError("模型请求与 Token 预算必须大于零")
    if not budget.max_estimated_cost.is_finite() or budget.max_estimated_cost <= 0:
        raise ContractError("成本预算必须是正有限 Decimal")
    if not budget.budget_currency or budget.budget_currency != budget.budget_currency.upper():
        raise ContractError("budget currency 必须是大写非空字符串")


def _read_required_environment(provider: EnvironmentPresenceProvider) -> tuple[EnvironmentPresence, ...]:
    """只读取固定三名称的 presence boolean。

    Args:
        provider: 不暴露值的存在性 provider。

    Returns:
        固定顺序的三条环境事实。

    Raises:
        ContractError: provider 返回非严格 bool 时抛出。
    """

    facts: list[EnvironmentPresence] = []
    for name in REQUIRED_ENVIRONMENT_NAMES:
        present = provider.is_present(name)
        if not isinstance(present, bool):
            raise ContractError(f"presence provider 的 {name} 必须是布尔值")
        facts.append(EnvironmentPresence(name=name, present=present))
    return tuple(facts)


def _validate_model_catalog(config_root: Path, budget_currency: str) -> None:
    """严格验证固定双模型 usage 与价格币种覆盖。

    Args:
        config_root: resolver 返回的 package config 根。
        budget_currency: 显式批准预算币种。

    Returns:
        无。

    Raises:
        ContractError: 模型缺失、usage 不支持、价格不完整或币种不一致时抛出。
    """

    _validate_budget(
        BudgetLimits(
            max_model_requests=1,
            max_total_tokens=1,
            max_estimated_cost=Decimal("1"),
            budget_currency=budget_currency,
        )
    )
    catalog = load_json_file(config_root / "llm_models.json", label="model catalog")
    for model_name in (_PRIMARY_MODEL, _AUDIT_MODEL):
        model = _json_mapping(_required_json(catalog, model_name, "model catalog"), f"model catalog.{model_name}")
        if _required_json(model, "supports_usage", model_name) is not True:
            raise ContractError(f"模型 {model_name} 不支持 usage")
        pricing = _json_mapping(_required_json(model, "pricing", model_name), f"{model_name}.pricing")
        currency = _json_string(_required_json(pricing, "currency", f"{model_name}.pricing"), "pricing.currency")
        if currency.upper() != budget_currency:
            raise ContractError(f"模型 {model_name} 价格币种与预算不一致")
        for rate_name in ("input_per_million", "cached_input_per_million", "output_per_million"):
            rate = _json_decimal(
                _required_json(pricing, rate_name, f"{model_name}.pricing"),
                f"{model_name}.pricing.{rate_name}",
            )
            if rate <= 0:
                raise ContractError(f"模型 {model_name} 的 {rate_name} 必须大于零")


def _validate_allowlisted_phase(
    spec: PhaseSpec,
    *,
    expected_phase: str,
    subcommands: tuple[str, ...],
) -> tuple[Command, ...]:
    """验证一个 phase 的 subcommand 与命令特有开关。

    Args:
        spec: 当前 phase spec。
        expected_phase: 固定 phase 名。
        subcommands: 该 phase 的有序 subcommand 闭集。

    Returns:
        通过独立结构校验的命令元组。

    Raises:
        ContractError: phase、subcommand、quiet 或 stable document ID 结构漂移时抛出。
    """

    if spec.phase_name != expected_phase:
        raise ContractError("phase structural allowlist drift")
    if tuple(command[3] for command in spec.commands) != subcommands:
        raise ContractError(f"{spec.phase_name} subcommand allowlist drift")
    for command in spec.commands:
        _validate_cli_command_shape(command)
        if spec.phase_name in {"download", "price-snapshot-import", "process"}:
            if command.count("--quiet") != 1:
                raise ContractError(f"{spec.phase_name} 必须精确含一个 --quiet")
        elif "--quiet" in command:
            raise ContractError(f"{spec.phase_name} 不得含 --quiet")
        if spec.phase_name == "price-snapshot-import" and command.count("--document-id") != 1:
            raise ContractError("price import 必须精确含一个 stable --document-id")
    return spec.commands


def _assert_structural_allowlist(specs: tuple[PhaseSpec, ...]) -> None:
    """在 canonical equality 外独立验证命令结构 allowlist。

    Args:
        specs: plan 内有序 phase specs。

    Returns:
        无。

    Raises:
        ContractError: phase、subcommand、validator action、config/base 或 shell token 非法时抛出。
    """

    expected_names = tuple(name for name, _count in PLANNED_PHASE_COMMAND_COUNTS)
    if tuple(spec.phase_name for spec in specs) != expected_names:
        raise ContractError("phase allowlist order drift")
    expected_subcommands = (
        ("download", ("download", "download", "download")),
        ("price-snapshot-import", ("upload_material",)),
        ("process", ("process",)),
        ("write-preflight", ("write",)),
        ("write", ("write",)),
        ("validations", ("research-template",) * len(_VALIDATOR_ACTIONS)),
    )
    all_commands: list[Command] = []
    for spec, (expected_phase, subcommands) in zip(specs, expected_subcommands, strict=True):
        all_commands.extend(
            _validate_allowlisted_phase(
                spec,
                expected_phase=expected_phase,
                subcommands=subcommands,
            )
        )
    validator_actions = tuple(command[4] for command in specs[-1].commands)
    if validator_actions != _VALIDATOR_ACTIONS:
        raise ContractError("validator action allowlist drift")
    if len(all_commands) != len(set(all_commands)):
        raise ContractError("plan commands 不得重复")


def _validate_cli_command_shape(command: Command) -> None:
    """验证单条 dayu.cli 命令的结构与 shell 隔离。

    Args:
        command: pure builder 产生的 argv。

    Returns:
        无。

    Raises:
        ContractError: module、base/config 数量或 shell token 非法时抛出。
    """

    if command[1:3] != ("-m", "dayu.cli"):
        raise ContractError("command 必须使用 -m dayu.cli")
    if command.count("--config") != 1 or command.count("--base") != 1:
        raise ContractError("每条 dayu.cli command 必须各含一个 --base/--config")
    if any(token in {"|", "||", "&&", ";", "`"} for token in command):
        raise ContractError("command 不得包含 shell token")


def _safe_argv_token(
    token: str,
    *,
    python_executable: str,
    run_root: str,
    package_config_root: str,
) -> str:
    """把一个 raw argv token 替换为受控 placeholder。

    Args:
        token: raw argv token。
        python_executable: canonical Python 路径。
        run_root: canonical run root。
        package_config_root: canonical package config 根。

    Returns:
        可持久化 token。

    Raises:
        ContractError: token 是三个 placeholder 无法覆盖的绝对路径时抛出。
    """

    if token == python_executable:
        return SAFE_ARGV_PLACEHOLDERS[0]
    candidate = token.partition("=")[2] if "=" in token else token
    if "=" in token and Path(candidate).is_absolute():
        raise ContractError("receipt argv 不接受 --flag=/abs 形状")
    if Path(candidate).is_absolute():
        path = Path(candidate).resolve(strict=False)
        run_path = Path(run_root)
        config_path = Path(package_config_root)
        if path == run_path or path.is_relative_to(run_path):
            relative = path.relative_to(run_path).as_posix()
            return SAFE_ARGV_PLACEHOLDERS[1] if relative == "." else f"{SAFE_ARGV_PLACEHOLDERS[1]}/{relative}"
        if path == config_path or path.is_relative_to(config_path):
            relative = path.relative_to(config_path).as_posix()
            return SAFE_ARGV_PLACEHOLDERS[2] if relative == "." else f"{SAFE_ARGV_PLACEHOLDERS[2]}/{relative}"
        raise ContractError("receipt argv 含 placeholder 无法覆盖的绝对路径")
    if candidate.startswith("~") or re.match(r"^[A-Za-z]:[\\/]", candidate) is not None:
        raise ContractError("receipt argv 含 home/Windows absolute path")
    return token


def _require_sha256_text(value: str, label: str) -> str:
    """验证小写 SHA-256 文本。

    Args:
        value: 待验证文本。
        label: 错误上下文标签。

    Returns:
        原 SHA-256 文本。

    Raises:
        ContractError: 文本不是 64 位小写十六进制时抛出。
    """

    if _SHA256_PATTERN.fullmatch(value) is None:
        raise ContractError(f"{label} 必须是小写 SHA-256")
    return value


def _json_mapping(value: JsonValue, label: str) -> JsonObject:
    """把 strict JSON value 收窄为字符串键对象。

    Args:
        value: 已通过 strict JSON ingress 的值。
        label: 错误上下文。

    Returns:
        原 JSON 对象。

    Raises:
        ContractError: 值不是对象时抛出。
    """

    if not isinstance(value, dict):
        raise ContractError(f"{label} 必须是 JSON 对象")
    return value


def _required_json(mapping: JsonObject, key: str, label: str) -> JsonValue:
    """从 strict JSON 对象取得一个必需字段。

    Args:
        mapping: 已收窄 JSON 对象。
        key: 必需键。
        label: 错误上下文。

    Returns:
        字段 JSON 值。

    Raises:
        ContractError: 字段缺失时抛出。
    """

    if key not in mapping:
        raise ContractError(f"{label} 缺少字段: {key}")
    return mapping[key]


def _json_string(value: JsonValue, label: str) -> str:
    """把 strict JSON value 收窄为非空字符串。

    Args:
        value: JSON 值。
        label: 错误上下文。

    Returns:
        非空字符串。

    Raises:
        ContractError: 值不是非空字符串时抛出。
    """

    if not isinstance(value, str) or not value:
        raise ContractError(f"{label} 必须是非空字符串")
    return value


def _json_decimal(value: JsonValue, label: str) -> Decimal:
    """把 JSON 数字或十进制字符串收窄为有限 Decimal。

    Args:
        value: JSON 数字或十进制字符串。
        label: 错误上下文。

    Returns:
        有限 Decimal。

    Raises:
        ContractError: bool、非法文本或非有限值时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ContractError(f"{label} 必须是十进制数")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ContractError(f"{label} 不是合法十进制数") from exc
    if not parsed.is_finite():
        raise ContractError(f"{label} 必须是有限十进制数")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
