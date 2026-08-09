"""投资 Agent 验收的严格数据契约、规范序列化与输入指纹。

本模块只负责把不可信 JSON 或既有 owner 的宽载荷收窄为不可变对象，并提供
确定性的 JSON/SHA-256 与 package 输入闭包。它不执行模型、网络或子进程。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import stat
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Literal, TypeAlias, TypedDict

from dayu.startup.config_file_resolver import (
    resolve_package_assets_path,
    resolve_package_config_path,
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
Verdict: TypeAlias = Literal["PASS", "PENDING_MANUAL_REVIEW", "FAIL"]
FindingSeverity: TypeAlias = Literal["high", "medium", "low"]
TerminalAction: TypeAlias = Literal["verify"]
PhaseStatus: TypeAlias = Literal["passed", "failed", "timeout", "signal"]
TerminationAction: TypeAlias = Literal["not_started", "terminate", "kill", "termination_unconfirmed"]
DownloadSectionStatus: TypeAlias = Literal["downloaded", "skipped", "failed"]
MaterialAction: TypeAlias = Literal["create", "update"]
ProcessSourceKind: TypeAlias = Literal["filing", "material"]
ProcessDocumentStatus: TypeAlias = Literal["processed", "skipped", "failed"]

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_AS_OF_SUFFIX = "Z"
_PLAN_SCHEMA_VERSION = 2
_PHASE_SCHEMA_VERSION = 3
_RECEIPT_SCHEMA_VERSION = 1
_MIN_COMMAND_TOKEN_COUNT = 4
_COMMAND_SUMMARY_MAX_BYTES = 512
_PAIR_WIDTH = 2
_RESEARCH_TREE_DIR = "research_templates"
_BASE_TEMPLATE_NAME = "定性分析模板.md"
_RESEARCH_SUFFIXES = (".md", ".definition.json")
_CONFIG_DIAGNOSTIC_LOCATORS = (
    "llm_models.json",
    "prompts/manifests/audit.json",
    "prompts/manifests/write.json",
)
REQUIRED_RESEARCH_ARTIFACTS = (
    "common-plus-technology.md",
    "technology.research-workbook.json",
    "technology.research-progress.md",
    "technology.monitoring-rules.json",
    "technology.source-map.json",
    "research-template.manifest.json",
    "technology.research-guide.md",
    "technology.checklist.md",
    "technology.bundle.json",
    "technology.monitoring-plan.json",
    "monitoring-status.json",
    "research-workbook-status.json",
    "research-workbook-report-status.json",
)
PLANNED_PHASE_COMMAND_COUNTS = (
    ("download", 3),
    ("price-snapshot-import", 1),
    ("process", 1),
    ("write-preflight", 1),
    ("write", 1),
    ("validations", 5),
)
REQUIRED_ENVIRONMENT_NAMES = (
    "DEEPSEEK_API_KEY",
    "MIMO_API_KEY",
    "SEC_USER_AGENT",
)
TERMINAL_ACTION = "verify"
SAFE_ARGV_PLACEHOLDERS = (
    "<PYTHON>",
    "<RUN_ROOT>",
    "<PACKAGE_CONFIG>",
)
SUBPROCESS_ENV_POLICY = (
    ("TQDM_DISABLE", "1"),
    ("HF_HUB_DISABLE_PROGRESS_BARS", "1"),
    ("TRANSFORMERS_VERBOSITY", "error"),
)


class ContractError(ValueError):
    """表示验收输入不符合严格 schema 或值域约束。

    Args:
        message: 已脱敏的 contract 错误说明。

    Returns:
        可由验收边界捕获的值错误。

    Raises:
        本类本身不显式抛出其它异常。
    """


class FingerprintDriftError(ContractError):
    """表示 package 配置或研究资产闭包发生漂移。

    Args:
        message: 已脱敏的指纹漂移说明。

    Returns:
        可由 preflight 边界捕获的 contract 错误。

    Raises:
        本类本身不显式抛出其它异常。
    """


class PlanPayload(TypedDict):
    """验收 plan 的规范 JSON 形状。

    Args:
        声明字段: plan 身份、运行环境、package 指纹、预算和产物清单。

    Returns:
        字段闭合的 plan JSON 类型。

    Raises:
        本类型声明不显式抛出异常。
    """

    schema_version: int
    plan_type: str
    ticker: str
    company: str
    research_template: str
    as_of: str
    git_sha: str
    dirty: bool
    python_version: str
    platform: str
    timezone: str
    run_root: str
    package_inputs: JsonObject
    price_snapshot_sha256: str
    price_material_sha256: str
    budget: JsonObject
    max_wall_seconds: int
    termination_grace_seconds: int
    subprocess_env_policy: list[JsonValue]
    price_material_document_id: str
    model_roles: JsonObject
    phase_specs: list[JsonValue]
    required_environment: list[JsonValue]
    terminal_action: str
    required_research_artifacts: list[JsonValue]


class PhaseSpecPayload(TypedDict):
    """计划内一个有序阶段的规范 JSON 形状。

    Args:
        声明字段: 阶段名与一个或多个 argv token 数组。

    Returns:
        字段闭合的阶段规格 JSON 类型。

    Raises:
        本类型声明不显式抛出异常。
    """

    phase_name: str
    commands: list[JsonValue]


class EnvironmentPresencePayload(TypedDict):
    """计划内一个必需环境变量的存在性事实。

    Args:
        声明字段: 环境变量名称与存在性布尔值。

    Returns:
        不包含环境变量值的闭合 JSON 类型。

    Raises:
        本类型声明不显式抛出异常。
    """

    name: str
    present: bool


class PhaseReceiptPayload(TypedDict):
    """阶段 receipt 的规范 JSON 形状。

    Args:
        声明字段: phase 身份、时间、argv、退出状态与 timeout 事实。

    Returns:
        字段闭合的阶段 receipt JSON 类型。

    Raises:
        本类型声明不显式抛出异常。
    """

    schema_version: int
    receipt_type: str
    plan_fingerprint: str
    phase_name: str
    status: PhaseStatus
    started_at: str
    ended_at: str
    duration_seconds: float
    remaining_wall_seconds: float
    command_records: list[JsonValue]


class CommandRecordPayload(TypedDict):
    """单条计划命令的规范执行事实。

    Args:
        声明字段: 命令身份、时间、退出、流摘要与 domain evidence。

    Returns:
        字段闭合的 command record JSON 类型。

    Raises:
        本类型声明不显式抛出异常。
    """

    command_index: int
    safe_argv: list[JsonValue]
    argv_digest: str
    status: PhaseStatus
    started_at: str
    ended_at: str
    duration_seconds: float
    exit_code: int | None
    stop_reason: str | None
    termination_action: str | None
    partial_by_timeout: bool
    stdout_sha256: str | None
    stderr_sha256: str | None
    stdout_summary: str | None
    stderr_summary: str | None
    evidence: JsonValue


class InventoryPayload(TypedDict):
    """源清单的规范 JSON 形状。

    Args:
        声明字段: 清单身份、as-of、窗口、discovery 与文档记录。

    Returns:
        字段闭合的 inventory JSON 类型。

    Raises:
        本类型声明不显式抛出异常。
    """

    schema_version: int
    inventory_type: str
    fixture_id: str
    ticker: str
    company: str
    as_of: str
    live_freshness_claimed: bool
    source_windows: list[JsonValue]
    latest_discovery: JsonObject
    documents: list[JsonValue]


class RubricPayload(TypedDict):
    """人工 rubric 的规范 JSON 形状。

    Args:
        声明字段: reviewer、三态、评分维度、findings 与完成时间。

    Returns:
        字段闭合的 rubric JSON 类型。

    Raises:
        本类型声明不显式抛出异常。
    """

    schema_version: int
    review_type: str
    fixture_id: str
    reviewer_role: str | None
    reviewer_id_label: str | None
    status: str
    dimensions: JsonObject
    total_score: int | None
    finding_counts: JsonObject
    findings: list[JsonValue]
    completed_at: str | None


class AcceptanceReceiptPayload(TypedDict):
    """验收 evaluator 输出 receipt 的规范 JSON 形状。

    Args:
        声明字段: verdict、评分、hard gates、findings、产物引用与 residuals。

    Returns:
        字段闭合的 acceptance receipt JSON 类型。

    Raises:
        本类型声明不显式抛出异常。
    """

    schema_version: int
    receipt_type: str
    evaluated_at: str
    verdict: str
    total_score: int | None
    dimension_scores: JsonObject
    hard_gates: JsonObject
    findings: list[JsonValue]
    artifacts: list[JsonValue]
    residuals: list[JsonValue]


@dataclass(frozen=True)
class FileFingerprint:
    """单个 package-relative regular file 的内容指纹。

    Args:
        locator: 相对 package 根的 POSIX 定位。
        sha256: 文件字节 SHA-256。

    Returns:
        不可变文件指纹对象。

    Raises:
        ContractError: locator 或 SHA-256 非法时抛出。
    """

    locator: str
    sha256: str

    def __post_init__(self) -> None:
        """验证定位与摘要。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: 定位不是安全相对路径或摘要非法时抛出。
        """

        _require_safe_locator(self.locator, "file_fingerprint.locator")
        _require_sha256(self.sha256, "file_fingerprint.sha256")

    def to_json(self) -> JsonObject:
        """转换为规范 JSON 对象。

        Args:
            无。

        Returns:
            仅含 locator 与 sha256 的 JSON 对象。

        Raises:
            本方法不显式抛出异常。
        """

        return {"locator": self.locator, "sha256": self.sha256}


@dataclass(frozen=True)
class CanonicalTreeFingerprint:
    """一棵 package regular-file canonical tree 的指纹。

    Args:
        locator: package-relative 树根定位。
        sha256: 有序文件清单的 canonical SHA-256。
        files: 树内有序普通文件指纹。

    Returns:
        不可变 canonical tree 指纹。

    Raises:
        本类不显式抛出异常。
    """

    locator: str
    sha256: str
    files: tuple[FileFingerprint, ...]

    def to_json(self) -> JsonObject:
        """转换为规范 JSON 对象。

        Args:
            无。

        Returns:
            canonical tree 的定位、摘要和有序文件清单。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "locator": self.locator,
            "sha256": self.sha256,
            "files": [item.to_json() for item in self.files],
        }


@dataclass(frozen=True)
class PackageInputFingerprints:
    """package 配置与研究资产的完整输入闭包。

    Args:
        config_tree: 配置 regular-file tree 指纹。
        config_diagnostics: 诊断关键文件指纹。
        research_tree: research_templates 资产 tree 指纹。
        base_template: 根级定性分析模板指纹。

    Returns:
        不可变 package 输入闭包。

    Raises:
        本类不显式抛出异常。
    """

    config_tree: CanonicalTreeFingerprint
    config_diagnostics: tuple[FileFingerprint, ...]
    research_tree: CanonicalTreeFingerprint
    base_template: FileFingerprint

    def to_json(self) -> JsonObject:
        """转换为不含绝对路径的规范 JSON 对象。

        Args:
            无。

        Returns:
            package-relative locator 与摘要组成的 JSON 对象。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "config_tree": self.config_tree.to_json(),
            "config_diagnostics": [item.to_json() for item in self.config_diagnostics],
            "research_tree": self.research_tree.to_json(),
            "base_template": self.base_template.to_json(),
        }


@dataclass(frozen=True)
class BudgetLimits:
    """一次验收运行的显式预算上限。

    Args:
        max_model_requests: 最大模型请求数。
        max_total_tokens: 最大总 Token 数。
        max_estimated_cost: 最大估算成本。
        budget_currency: 批准预算币种。

    Returns:
        不可变预算限制。

    Raises:
        本类不显式抛出异常。
    """

    max_model_requests: int
    max_total_tokens: int
    max_estimated_cost: Decimal
    budget_currency: str

    def to_json(self) -> JsonObject:
        """转换为规范 JSON 对象。

        Args:
            无。

        Returns:
            预算限制 JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "max_model_requests": self.max_model_requests,
            "max_total_tokens": self.max_total_tokens,
            "max_estimated_cost": str(self.max_estimated_cost),
            "budget_currency": self.budget_currency,
        }


@dataclass(frozen=True)
class PhaseSpec:
    """唯一验收计划中的一个有序执行阶段。

    Args:
        phase_name: 固定 allowlist 中的阶段名。
        commands: 本阶段按顺序执行的一个或多个 raw argv token 元组。

    Returns:
        不可变阶段规格。

    Raises:
        ContractError: 阶段名、命令数量或 token 结构非法时抛出。
    """

    phase_name: str
    commands: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        """验证阶段规格的结构闭包。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: 阶段名、命令数量或 token 结构非法时抛出。
        """

        expected_counts = dict(PLANNED_PHASE_COMMAND_COUNTS)
        if self.phase_name not in expected_counts:
            raise ContractError(f"phase_spec.phase_name 非法: {self.phase_name}")
        if len(self.commands) != expected_counts[self.phase_name]:
            raise ContractError(f"phase_spec.{self.phase_name}.commands 数量非法")
        _validate_command_matrix(self.commands, f"phase_spec.{self.phase_name}.commands")

    def to_json(self) -> JsonObject:
        """转换为 plan fingerprint 使用的规范 JSON。

        Args:
            无。

        Returns:
            阶段名与有序 argv token matrix。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "phase_name": self.phase_name,
            "commands": [list(command) for command in self.commands],
        }


@dataclass(frozen=True)
class EnvironmentPresence:
    """必需环境变量的名称与存在性事实。

    Args:
        name: 固定 allowlist 中的环境变量名称。
        present: 该名称在 prepare 时是否存在。

    Returns:
        不包含 secret 值的不可变事实。

    Raises:
        ContractError: 名称不受支持或存在性不是严格 bool 时抛出。
    """

    name: str
    present: bool

    def __post_init__(self) -> None:
        """验证环境变量事实不携带任意名称或非布尔值。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: 名称不受支持或存在性不是严格 bool 时抛出。
        """

        if self.name not in REQUIRED_ENVIRONMENT_NAMES:
            raise ContractError(f"required_environment.name 非法: {self.name}")
        if not isinstance(self.present, bool):
            raise ContractError("required_environment.present 必须是布尔值")

    def to_json(self) -> JsonObject:
        """转换为不含 secret 值的规范 JSON。

        Args:
            无。

        Returns:
            环境变量名称与存在性布尔值。

        Raises:
            本方法不显式抛出异常。
        """

        return {"name": self.name, "present": self.present}


@dataclass(frozen=True)
class AcceptancePlan:
    """确定性验收计划的不可变 contract。

    Args:
        声明字段: 目标、as-of、代码环境、package 输入、价格、预算和产物清单。

    Returns:
        可生成稳定 fingerprint 的不可变验收计划。

    Raises:
        本类不显式抛出异常。
    """

    ticker: str
    company: str
    research_template: str
    as_of: datetime
    git_sha: str
    dirty: bool
    python_version: str
    platform: str
    timezone: str
    run_root: str
    package_inputs: PackageInputFingerprints
    price_snapshot_sha256: str
    price_material_sha256: str
    budget: BudgetLimits
    max_wall_seconds: int
    termination_grace_seconds: int
    subprocess_env_policy: tuple[tuple[str, str], ...]
    price_material_document_id: str
    model_roles: ModelRoles
    phase_specs: tuple[PhaseSpec, ...]
    required_environment: tuple[EnvironmentPresence, ...]
    terminal_action: TerminalAction
    required_research_artifacts: tuple[str, ...]

    def __post_init__(self) -> None:
        """验证 v2 执行身份的固定结构。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: run root、阶段顺序、模型、环境名称或 terminal action 非法时抛出。
        """

        _require_canonical_absolute_path(self.run_root, "acceptance_plan.run_root")
        phase_names = tuple(item.phase_name for item in self.phase_specs)
        expected_phase_names = tuple(name for name, _count in PLANNED_PHASE_COMMAND_COUNTS)
        if phase_names != expected_phase_names:
            raise ContractError("acceptance_plan.phase_specs 必须精确按固定阶段顺序排列")
        if self.model_roles != ModelRoles(
            primary="deepseek-v4-pro",
            audit="mimo-v2.5-pro-thinking",
        ):
            raise ContractError("acceptance_plan.model_roles 必须绑定固定 DeepSeek/MiMo 角色")
        environment_names = tuple(item.name for item in self.required_environment)
        if environment_names != REQUIRED_ENVIRONMENT_NAMES:
            raise ContractError("acceptance_plan.required_environment 必须精确按固定名称顺序排列")
        if self.terminal_action != TERMINAL_ACTION:
            raise ContractError("acceptance_plan.terminal_action 必须是 verify")
        if self.subprocess_env_policy != SUBPROCESS_ENV_POLICY:
            raise ContractError("acceptance_plan.subprocess_env_policy 必须精确绑定固定非秘密环境策略")
        if not self.price_material_document_id.startswith("mat_"):
            raise ContractError("acceptance_plan.price_material_document_id 必须是稳定 material ID")

    def to_json(self) -> JsonObject:
        """转换为 plan fingerprint 使用的规范 JSON 形状。

        Args:
            无。

        Returns:
            完整 plan JSON 对象。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "schema_version": _PLAN_SCHEMA_VERSION,
            "plan_type": "investment_agent_acceptance_plan",
            "ticker": self.ticker,
            "company": self.company,
            "research_template": self.research_template,
            "as_of": format_utc(self.as_of),
            "git_sha": self.git_sha,
            "dirty": self.dirty,
            "python_version": self.python_version,
            "platform": self.platform,
            "timezone": self.timezone,
            "run_root": self.run_root,
            "package_inputs": self.package_inputs.to_json(),
            "price_snapshot_sha256": self.price_snapshot_sha256,
            "price_material_sha256": self.price_material_sha256,
            "budget": self.budget.to_json(),
            "max_wall_seconds": self.max_wall_seconds,
            "termination_grace_seconds": self.termination_grace_seconds,
            "subprocess_env_policy": [list(item) for item in self.subprocess_env_policy],
            "price_material_document_id": self.price_material_document_id,
            "model_roles": {
                "primary": self.model_roles.primary,
                "audit": self.model_roles.audit,
            },
            "phase_specs": [item.to_json() for item in self.phase_specs],
            "required_environment": [item.to_json() for item in self.required_environment],
            "terminal_action": self.terminal_action,
            "required_research_artifacts": list(self.required_research_artifacts),
        }

    @property
    def fingerprint(self) -> str:
        """计算完整 plan 的 SHA-256 身份。

        Args:
            无。

        Returns:
            plan canonical JSON 的 SHA-256。

        Raises:
            ContractError: plan 无法按严格 JSON 规则序列化时抛出。
        """

        return canonical_json_sha256(self.to_json())


@dataclass(frozen=True)
class DownloadSummary:
    """download owner 的严格非负计数摘要。

    Args:
        total: 总文档数。
        downloaded: 下载数。
        skipped: 跳过数。
        failed: 失败数。

    Returns:
        不可变 download 摘要。

    Raises:
        ContractError: 计数非法或不闭合时抛出。
    """

    total: int
    downloaded: int
    skipped: int
    failed: int

    def __post_init__(self) -> None:
        """验证计数严格非负且总数闭合。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: 计数非法或不闭合时抛出。
        """

        values = (self.total, self.downloaded, self.skipped, self.failed)
        if any(isinstance(value, bool) or value < 0 for value in values):
            raise ContractError("download evidence summary 必须是非负整数")
        if self.total != self.downloaded + self.skipped + self.failed:
            raise ContractError("download evidence summary 计数不闭合")

    def to_json(self) -> JsonObject:
        """转换为规范 JSON。

        Args:
            无。

        Returns:
            download summary JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "total": self.total,
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "failed": self.failed,
        }


@dataclass(frozen=True)
class DownloadEvidenceRow:
    """download 一个可信结构 row。

    Args:
        document_id: 精确 SEC filing document ID。
        accession: SEC accession。
        canonical_form: production normalizer 产生的 form。
        filing_date: filing 日期。
        section_status: 由固定 section header 派生的状态。

    Returns:
        不可变 download row。

    Raises:
        ContractError: 文本、日期或状态非法时抛出。
    """

    document_id: str
    accession: str
    canonical_form: str
    filing_date: date
    section_status: DownloadSectionStatus

    def __post_init__(self) -> None:
        """验证 row 的 SEC 身份与闭合状态。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: SEC 身份或状态非法时抛出。
        """

        if re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", self.accession) is None:
            raise ContractError("download evidence accession 非法")
        if self.document_id != f"fil_{self.accession}":
            raise ContractError("download evidence document_id/accession 不闭合")
        if not self.canonical_form or self.section_status not in {"downloaded", "skipped", "failed"}:
            raise ContractError("download evidence form/status 非法")

    def to_json(self) -> JsonObject:
        """转换为规范 JSON。

        Args:
            无。

        Returns:
            download row JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "document_id": self.document_id,
            "accession": self.accession,
            "canonical_form": self.canonical_form,
            "filing_date": self.filing_date.isoformat(),
            "section_status": self.section_status,
        }


@dataclass(frozen=True)
class DownloadCommandEvidence:
    """一条 download 命令的严格 owner evidence。

    Args:
        ticker: owner ticker。
        planned_forms: plan argv 中的原 form token。
        canonical_forms: production normalizer 结果。
        start/end: 固定窗口日期。
        owner_status: owner 顶层状态。
        summary: owner 汇总。
        rows: 三节可信结构 rows。

    Returns:
        不可变 download evidence。

    Raises:
        ContractError: 字段或计数闭合非法时抛出。
    """

    ticker: str
    planned_forms: tuple[str, ...]
    canonical_forms: tuple[str, ...]
    start: date
    end: date
    owner_status: Literal["ok", "downloaded", "skipped", "cancelled"]
    summary: DownloadSummary
    rows: tuple[DownloadEvidenceRow, ...]

    def __post_init__(self) -> None:
        """验证 download evidence 的 row/count/identity 闭包。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: 行数、重复、目标或窗口非法时抛出。
        """

        if self.ticker != "AAPL" or not self.planned_forms or len(self.planned_forms) != len(self.canonical_forms):
            raise ContractError("download evidence ticker/forms 非法")
        if self.start > self.end:
            raise ContractError("download evidence 窗口非法")
        ids = tuple(row.document_id for row in self.rows)
        if len(ids) != len(set(ids)):
            raise ContractError("download evidence document_id 跨节重复")
        counts = {
            "downloaded": self.summary.downloaded,
            "skipped": self.summary.skipped,
            "failed": self.summary.failed,
        }
        for status, expected in counts.items():
            if sum(row.section_status == status for row in self.rows) != expected:
                raise ContractError("download evidence section rows 与 summary 不闭合")

    def to_json(self) -> JsonObject:
        """转换为闭集 discriminated JSON。

        Args:
            无。

        Returns:
            download evidence JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "evidence_type": "download",
            "ticker": self.ticker,
            "planned_forms": list(self.planned_forms),
            "canonical_forms": list(self.canonical_forms),
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "owner_status": self.owner_status,
            "summary": self.summary.to_json(),
            "rows": [row.to_json() for row in self.rows],
        }


@dataclass(frozen=True)
class MaterialImportCommandEvidence:
    """price material import 的严格 owner/repository evidence。

    Args:
        owner_status: owner 顶层 ok/skipped。
        material_action: create/update intent。
        document_id: plan-bound 稳定 ID。
        source_fingerprint: ok 时必需的 owner SHA。
        report_date: ok 时必需的报告日期。
        price_json_sha256: canonical JSON SHA。
        price_material_sha256: Markdown SHA。
        repository_primary_sha256: repository 主文件 SHA。

    Returns:
        不可变 material evidence。

    Raises:
        ContractError: 状态条件或 SHA 非法时抛出。
    """

    owner_status: Literal["ok", "skipped"]
    material_action: MaterialAction
    document_id: str
    source_fingerprint: str | None
    report_date: date | None
    price_json_sha256: str
    price_material_sha256: str
    repository_primary_sha256: str

    def __post_init__(self) -> None:
        """验证 action/status 正交条件与摘要。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: 条件字段或摘要非法时抛出。
        """

        if self.material_action not in {"create", "update"} or not self.document_id.startswith("mat_"):
            raise ContractError("material evidence action/document_id 非法")
        for label, digest in (
            ("price_json_sha256", self.price_json_sha256),
            ("price_material_sha256", self.price_material_sha256),
            ("repository_primary_sha256", self.repository_primary_sha256),
        ):
            _require_sha256(digest, f"material evidence.{label}")
        if self.source_fingerprint is not None:
            _require_sha256(self.source_fingerprint, "material evidence.source_fingerprint")
        if self.owner_status == "ok" and (self.source_fingerprint is None or self.report_date is None):
            raise ContractError("material evidence owner_status=ok 缺条件字段")

    def to_json(self) -> JsonObject:
        """转换为闭集 discriminated JSON。

        Args:
            无。

        Returns:
            material evidence JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "evidence_type": "material_import",
            "owner_status": self.owner_status,
            "material_action": self.material_action,
            "document_id": self.document_id,
            "source_fingerprint": self.source_fingerprint,
            "report_date": self.report_date.isoformat() if self.report_date is not None else None,
            "price_json_sha256": self.price_json_sha256,
            "price_material_sha256": self.price_material_sha256,
            "repository_primary_sha256": self.repository_primary_sha256,
        }


@dataclass(frozen=True)
class ProcessSummary:
    """process 一侧 filing/material 的严格摘要。

    Args:
        total/processed/skipped/failed: owner 非负计数。

    Returns:
        不可变 process 摘要。

    Raises:
        ContractError: 计数非法或不闭合时抛出。
    """

    total: int
    processed: int
    skipped: int
    failed: int

    def __post_init__(self) -> None:
        """验证计数非负并闭合。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: 计数非法或不闭合时抛出。
        """

        values = (self.total, self.processed, self.skipped, self.failed)
        if any(isinstance(value, bool) or value < 0 for value in values):
            raise ContractError("process evidence summary 必须是非负整数")
        if self.total != self.processed + self.skipped + self.failed:
            raise ContractError("process evidence summary 计数不闭合")

    def to_json(self) -> JsonObject:
        """转换为规范 JSON。

        Args:
            无。

        Returns:
            process summary JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "total": self.total,
            "processed": self.processed,
            "skipped": self.skipped,
            "failed": self.failed,
        }


@dataclass(frozen=True)
class ProcessEvidenceRow:
    """由固定 section 派生状态的 process row。

    Args:
        document_id: owner row 首段文档 ID。
        source_kind: filing/material section 身份。
        status: processed/skipped/failed section 身份。

    Returns:
        不可变 process row。

    Raises:
        ContractError: 文档 ID 或闭集值非法时抛出。
    """

    document_id: str
    source_kind: ProcessSourceKind
    status: ProcessDocumentStatus

    def __post_init__(self) -> None:
        """验证 row 只携带可信结构字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: 字段非法时抛出。
        """

        if not self.document_id or self.document_id.strip() != self.document_id:
            raise ContractError("process evidence document_id 非法")
        if self.source_kind not in {"filing", "material"} or self.status not in {
            "processed",
            "skipped",
            "failed",
        }:
            raise ContractError("process evidence section identity 非法")

    def to_json(self) -> JsonObject:
        """转换为规范 JSON。

        Args:
            无。

        Returns:
            process row JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "document_id": self.document_id,
            "source_kind": self.source_kind,
            "status": self.status,
        }


@dataclass(frozen=True)
class ProcessCommandEvidence:
    """process 命令的严格 owner evidence。

    Args:
        owner_status: owner 顶层状态。
        filing_summary: filing summary。
        material_summary: material summary 或 TODO 时 null。
        materials_todo: 固定 TODO 分支标记。
        rows: 六节可信 document rows。

    Returns:
        不可变 process evidence。

    Raises:
        ContractError: TODO/summary/rows 不闭合时抛出。
    """

    owner_status: Literal["ok", "cancelled"]
    filing_summary: ProcessSummary
    material_summary: ProcessSummary | None
    materials_todo: bool
    rows: tuple[ProcessEvidenceRow, ...]

    def __post_init__(self) -> None:
        """验证 process TODO 与六节 row 数量闭包。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: TODO、重复或计数不闭合时抛出。
        """

        if self.materials_todo == (self.material_summary is not None):
            raise ContractError("process evidence materials summary/TODO 必须互斥")
        ids = tuple(row.document_id for row in self.rows)
        if len(ids) != len(set(ids)):
            raise ContractError("process evidence document_id 跨节重复")
        filing_rows = tuple(row for row in self.rows if row.source_kind == "filing")
        if len(filing_rows) != self.filing_summary.total:
            raise ContractError("process evidence filing rows 与 summary 不闭合")
        if self.material_summary is not None:
            material_rows = tuple(row for row in self.rows if row.source_kind == "material")
            if len(material_rows) != self.material_summary.total:
                raise ContractError("process evidence material rows 与 summary 不闭合")

    def to_json(self) -> JsonObject:
        """转换为闭集 discriminated JSON。

        Args:
            无。

        Returns:
            process evidence JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "evidence_type": "process",
            "owner_status": self.owner_status,
            "filing_summary": self.filing_summary.to_json(),
            "material_summary": self.material_summary.to_json() if self.material_summary is not None else None,
            "materials_todo": self.materials_todo,
            "rows": [row.to_json() for row in self.rows],
        }


CommandEvidence: TypeAlias = DownloadCommandEvidence | MaterialImportCommandEvidence | ProcessCommandEvidence


@dataclass(frozen=True)
class CommandRecord:
    """phase 内单条命令的严格执行事实。

    Args:
        声明字段: 命令序号、脱敏 argv、时间、退出、流摘要与 evidence。

    Returns:
        不可变 command record。

    Raises:
        ContractError: lifecycle、digest、summary 或 evidence 结构非法时抛出。
    """

    command_index: int
    safe_argv: tuple[str, ...]
    argv_digest: str
    status: PhaseStatus
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    exit_code: int | None
    stop_reason: str | None
    termination_action: TerminationAction | None
    partial_by_timeout: bool
    stdout_sha256: str | None
    stderr_sha256: str | None
    stdout_summary: str | None
    stderr_summary: str | None
    evidence: CommandEvidence | None

    def __post_init__(self) -> None:
        """验证单条执行记录的严格 lifecycle。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: 任一字段不闭合时抛出。
        """

        if isinstance(self.command_index, bool) or self.command_index < 0:
            raise ContractError("command_record.command_index 必须是非负整数")
        _validate_safe_command_matrix((self.safe_argv,), "command_record.safe_argv")
        _require_sha256(self.argv_digest, "command_record.argv_digest")
        format_utc(self.started_at)
        format_utc(self.ended_at)
        if self.ended_at < self.started_at or not math.isfinite(self.duration_seconds) or self.duration_seconds < 0:
            raise ContractError("command_record 时间非法")
        for label, digest in (("stdout_sha256", self.stdout_sha256), ("stderr_sha256", self.stderr_sha256)):
            if digest is not None:
                _require_sha256(digest, f"command_record.{label}")
        for label, summary in (("stdout_summary", self.stdout_summary), ("stderr_summary", self.stderr_summary)):
            if summary is not None and (
                not summary or len(summary.encode("utf-8")) > _COMMAND_SUMMARY_MAX_BYTES
            ):
                raise ContractError(f"command_record.{label} 必须是 1..512 UTF-8 bytes")
        _validate_command_record_status(self)

    def to_json(self) -> JsonObject:
        """转换为规范 JSON。

        Args:
            无。

        Returns:
            command record JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "command_index": self.command_index,
            "safe_argv": list(self.safe_argv),
            "argv_digest": self.argv_digest,
            "status": self.status,
            "started_at": format_utc(self.started_at),
            "ended_at": format_utc(self.ended_at),
            "duration_seconds": self.duration_seconds,
            "exit_code": self.exit_code,
            "stop_reason": self.stop_reason,
            "termination_action": self.termination_action,
            "partial_by_timeout": self.partial_by_timeout,
            "stdout_sha256": self.stdout_sha256,
            "stderr_sha256": self.stderr_sha256,
            "stdout_summary": self.stdout_summary,
            "stderr_summary": self.stderr_summary,
            "evidence": self.evidence.to_json() if self.evidence is not None else None,
        }


@dataclass(frozen=True)
class PhaseReceipt:
    """单阶段执行 receipt 的不可变 contract。

    Args:
        声明字段: plan/phase 身份、时间、argv、退出与 timeout/termination 状态。

    Returns:
        可稳定序列化的不可变阶段 receipt。

    Raises:
        本类不显式抛出异常。
    """

    plan_fingerprint: str
    phase_name: str
    status: PhaseStatus
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    remaining_wall_seconds: float
    command_records: tuple[CommandRecord, ...]

    def __post_init__(self) -> None:
        """验证 v3 receipt 的逐命令前缀与聚合状态闭包。

        Args:
            无。

        Returns:
            无。

        Raises:
            ContractError: command records 或阶段聚合结构非法时抛出。
        """

        _require_sha256(self.plan_fingerprint, "phase_receipt.plan_fingerprint")
        if self.ended_at < self.started_at or not math.isfinite(self.duration_seconds) or self.duration_seconds < 0:
            raise ContractError("phase_receipt 时间非法")
        if not math.isfinite(self.remaining_wall_seconds) or self.remaining_wall_seconds < 0:
            raise ContractError("phase_receipt.remaining_wall_seconds 非法")
        for index, record in enumerate(self.command_records):
            if record.command_index != index:
                raise ContractError("phase_receipt.command_records index 必须从零连续")
            if record.started_at < self.started_at or record.ended_at > self.ended_at:
                raise ContractError("phase_receipt 聚合时间必须包住 command records")
            if index > 0 and record.started_at < self.command_records[index - 1].ended_at:
                raise ContractError("phase_receipt command records 时间不得倒退")
        _validate_phase_record_prefix(self)

    def to_json(self) -> JsonObject:
        """转换为阶段 receipt 的严格 JSON 对象。

        Args:
            无。

        Returns:
            阶段 receipt JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "schema_version": _PHASE_SCHEMA_VERSION,
            "receipt_type": "investment_agent_acceptance_phase",
            "plan_fingerprint": self.plan_fingerprint,
            "phase_name": self.phase_name,
            "status": self.status,
            "started_at": format_utc(self.started_at),
            "ended_at": format_utc(self.ended_at),
            "duration_seconds": self.duration_seconds,
            "remaining_wall_seconds": self.remaining_wall_seconds,
            "command_records": [record.to_json() for record in self.command_records],
        }


@dataclass(frozen=True)
class AcceptanceTarget:
    """固定验收目标。

    Args:
        ticker: 规范证券代码。
        company: 规范公司名。
        research_template: 已解析研究模板名。

    Returns:
        不可变验收目标。

    Raises:
        本类不显式抛出异常。
    """

    ticker: str
    company: str
    research_template: str


@dataclass(frozen=True)
class ModelRoles:
    """写作与审计模型职责。

    Args:
        primary: 主写模型规范名。
        audit: 第二路审计模型规范名。

    Returns:
        不可变模型职责绑定。

    Raises:
        本类不显式抛出异常。
    """

    primary: str
    audit: str


@dataclass(frozen=True)
class ValuationReferencePrice:
    """报告唯一允许的估值参考价格。

    Args:
        price: 精确 Decimal 价格。
        currency: 价格币种。
        market_date: 市场日期。
        material_document_id: 绑定价格 material 文档 ID。

    Returns:
        不可变估值参考价。

    Raises:
        本类不显式抛出异常。
    """

    price: Decimal
    currency: str
    market_date: date
    material_document_id: str


@dataclass(frozen=True)
class ScoreContract:
    """100 分 rubric 的阈值 contract。

    Args:
        total_points: rubric 总分上限。
        minimum_total_score: PASS 最低总分。
        dimension_minimums: 有序维度最低分。

    Returns:
        不可变评分阈值 contract。

    Raises:
        本类不显式抛出异常。
    """

    total_points: int
    minimum_total_score: int
    dimension_minimums: tuple[tuple[str, int], ...]

    def minimum_for(self, name: str) -> int | None:
        """查找一个维度的最低分。

        Args:
            name: rubric 维度名。

        Returns:
            找到时返回最低分，否则返回 ``None``。

        Raises:
            本方法不显式抛出异常。
        """

        for candidate, minimum in self.dimension_minimums:
            if candidate == name:
                return minimum
        return None


@dataclass(frozen=True)
class AcceptanceContract:
    """固定 AAPL deterministic fixture 的顶层 contract。

    Args:
        声明字段: fixture/目标/模型身份、主题、证据、价格、评分、hard gates 与产物。

    Returns:
        不可变顶层验收 contract。

    Raises:
        本类不显式抛出异常。
    """

    fixture_id: str
    target: AcceptanceTarget
    deterministic: bool
    external_calls_allowed: bool
    live_freshness_claimed: bool
    model_roles: ModelRoles
    required_topics: tuple[str, ...]
    required_evidence_parts: tuple[str, ...]
    valuation_reference_price: ValuationReferencePrice
    score_contract: ScoreContract
    hard_gates: tuple[str, ...]
    required_research_artifacts: tuple[str, ...]


@dataclass(frozen=True)
class PriceSnapshot:
    """经严格解析的六字段价格快照。

    Args:
        price: 精确 Decimal 价格。
        currency: 价格币种。
        market_date: 市场日期。
        source_url: 价格来源 URL。
        captured_at: 带时区采集时间。
        max_age_days: 最大允许时效天数。

    Returns:
        不可变价格快照。

    Raises:
        本类不显式抛出异常。
    """

    price: Decimal
    currency: str
    market_date: date
    source_url: str
    captured_at: datetime
    max_age_days: int


@dataclass(frozen=True)
class SourceWindow:
    """一组 SEC form 的显式日期窗口。

    Args:
        forms: 该窗口绑定的规范 SEC forms。
        start_date: 显式开始日期。
        end_date: 显式结束日期。

    Returns:
        不可变源窗口。

    Raises:
        本类不显式抛出异常。
    """

    forms: tuple[str, ...]
    start_date: date
    end_date: date

    def to_json(self) -> JsonObject:
        """转换为规范窗口 JSON。

        Args:
            无。

        Returns:
            forms/start/end JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "forms": list(self.forms),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
        }


@dataclass(frozen=True)
class ProcessedState:
    """仓储协议可得的 processed 状态。

    Args:
        声明字段: 存在标志、parser、质量、reprocess、schema 与源指纹。

    Returns:
        可指纹化的不可变 processed 状态。

    Raises:
        本类不显式抛出异常。
    """

    exists: bool
    parser_version: str
    quality: str
    reprocess_required: bool
    schema_version: str
    source_fingerprint: str

    def to_json(self) -> JsonObject:
        """转换为状态指纹使用的严格 JSON 对象。

        Args:
            无。

        Returns:
            processed 状态 JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "exists": self.exists,
            "parser_version": self.parser_version,
            "quality": self.quality,
            "reprocess_required": self.reprocess_required,
            "schema_version": self.schema_version,
            "source_fingerprint": self.source_fingerprint,
        }


@dataclass(frozen=True)
class SourceDocument:
    """严格源文档与 processed 状态闭包。

    Args:
        声明字段: 文档身份、类型/日期、accession、primary 摘要与 processed 闭包。

    Returns:
        不可变源文档事实。

    Raises:
        本类不显式抛出异常。
    """

    document_id: str
    source_kind: Literal["filing", "material"]
    form: str
    filing_date: date
    report_date: date
    fiscal_year: int | None
    fiscal_period: str | None
    accession: str | None
    source_locator: str
    primary_file_sha256: str
    ingest_complete: bool
    processed: ProcessedState
    processed_state_fingerprint: str

    def to_json(self) -> JsonObject:
        """转换为规范 source document JSON。

        Args:
            无。

        Returns:
            文档与 processed 状态闭包 JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "document_id": self.document_id,
            "source_kind": self.source_kind,
            "form": self.form,
            "filing_date": self.filing_date.isoformat(),
            "report_date": self.report_date.isoformat(),
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "accession": self.accession,
            "source_locator": self.source_locator,
            "primary_file_sha256": self.primary_file_sha256,
            "ingest_complete": self.ingest_complete,
            "processed": self.processed.to_json(),
            "processed_state_fingerprint": self.processed_state_fingerprint,
        }


@dataclass(frozen=True)
class SourceInventory:
    """按仓储协议构建或从 fixture 解析的源清单。

    Args:
        声明字段: 清单身份、目标、as-of、freshness、窗口、discovery 与文档。

    Returns:
        不可变源清单。

    Raises:
        本类不显式抛出异常。
    """

    fixture_id: str
    ticker: str
    company: str
    as_of: datetime
    live_freshness_claimed: bool
    source_windows: tuple[SourceWindow, ...]
    latest_discovery: tuple[tuple[str, str], ...]
    documents: tuple[SourceDocument, ...]

    def to_json(self) -> JsonObject:
        """转换为 canonical source inventory JSON。

        Args:
            无。

        Returns:
            严格 inventory JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "schema_version": 1,
            "inventory_type": "investment_agent_source_inventory",
            "fixture_id": self.fixture_id,
            "ticker": self.ticker,
            "company": self.company,
            "as_of": format_utc(self.as_of),
            "live_freshness_claimed": self.live_freshness_claimed,
            "source_windows": [window.to_json() for window in self.source_windows],
            "latest_discovery": dict(self.latest_discovery),
            "documents": [document.to_json() for document in self.documents],
        }

    def document_by_id(self, document_id: str) -> SourceDocument | None:
        """按文档 ID 查找记录。

        Args:
            document_id: 仓储文档 ID。

        Returns:
            找到的文档；不存在时返回 ``None``。

        Raises:
            本方法不显式抛出异常。
        """

        for document in self.documents:
            if document.document_id == document_id:
                return document
        return None


@dataclass(frozen=True)
class RubricItem:
    """人工 rubric 的一个可复核子项。

    Args:
        item_id: 稳定子项 ID。
        score: 人工分数或待填标记。
        max_score: 子项上限。
        evidence_paths: 非 PII 证据定位。
        notes: 人工判断说明或待填标记。

    Returns:
        不可变 rubric 子项。

    Raises:
        本类不显式抛出异常。
    """

    item_id: str
    score: int | None
    max_score: int
    evidence_paths: tuple[str, ...]
    notes: str | None


@dataclass(frozen=True)
class RubricDimension:
    """人工 rubric 的一个评分维度。

    Args:
        name: 稳定维度名。
        score: 维度分或待填标记。
        max_score: 维度上限。
        items: 有序人工子项。

    Returns:
        不可变 rubric 维度。

    Raises:
        本类不显式抛出异常。
    """

    name: str
    score: int | None
    max_score: int
    items: tuple[RubricItem, ...]


@dataclass(frozen=True)
class ManualFinding:
    """人工质量复核 finding。

    Args:
        finding_id: 稳定 finding ID。
        severity: 严重级别。
        status: open/closed 状态。
        summary: 已脱敏摘要。
        evidence_paths: 非 PII 证据定位。

    Returns:
        不可变人工 finding。

    Raises:
        本类不显式抛出异常。
    """

    finding_id: str
    severity: FindingSeverity
    status: Literal["open", "closed"]
    summary: str
    evidence_paths: tuple[str, ...]


@dataclass(frozen=True)
class FindingCounts:
    """人工 finding 的分级计数。

    Args:
        high: High 数量。
        medium: Medium 数量。
        low: Low 数量。

    Returns:
        不可变 finding 计数。

    Raises:
        本类不显式抛出异常。
    """

    high: int
    medium: int
    low: int


@dataclass(frozen=True)
class QualityReview:
    """完整或待填写的三态人工 rubric。

    Args:
        声明字段: fixture、reviewer 标签、三态、维度、总分、findings 与完成时间。

    Returns:
        不可变人工质量复核。

    Raises:
        本类不显式抛出异常。
    """

    fixture_id: str
    reviewer_role: str | None
    reviewer_id_label: str | None
    status: Verdict
    dimensions: tuple[RubricDimension, ...]
    total_score: int | None
    finding_counts: FindingCounts
    findings: tuple[ManualFinding, ...]
    completed_at: datetime | None

    @property
    def is_complete(self) -> bool:
        """判断人工 rubric 的全部必填值是否齐全。

        Args:
            无。

        Returns:
            reviewer、完成时间和全部 item 均填写时返回 ``True``。

        Raises:
            本方法不显式抛出异常。
        """

        return bool(
            self.reviewer_role
            and self.reviewer_id_label
            and self.completed_at is not None
            and self.total_score is not None
            and all(
                dimension.score is not None
                and all(item.score is not None and item.evidence_paths and item.notes for item in dimension.items)
                for dimension in self.dimensions
            )
        )


@dataclass(frozen=True)
class OwnerBudgetSummary:
    """从 WriteModelUsageLedger/RunSummary 收窄出的预算事实。

    Args:
        声明字段: budget enable/status、批准上限、实际 usage/cost、reservation 与 block。

    Returns:
        不可变 owner 预算事实。

    Raises:
        本类不显式抛出异常。
    """

    enabled: bool
    status: str
    max_model_requests: int
    max_total_tokens: int
    max_estimated_cost: Decimal
    budget_currency: str
    model_requests: int
    total_tokens: int
    estimated_cost: Decimal
    usage_status: str
    cost_status: str
    currency: str
    active_reservation_count: int
    block_present: bool


@dataclass(frozen=True)
class OwnerRunSummary:
    """从生产 write_run_summary_v3 严格收窄出的验收事实。

    Args:
        声明字段: schema、目标、发布、模型、usage/cost/budget 与章节审计状态。

    Returns:
        不可变 owner run summary 事实。

    Raises:
        本类不显式抛出异常。
    """

    schema_version: str
    ticker: str
    gate_status: str
    publication_status: str
    primary_models: tuple[str, ...]
    audit_models: tuple[str, ...]
    usage_status: str
    request_count: int
    total_tokens: int
    cost_currency: str
    cost_status: str
    known_estimated_cost: Decimal
    budget: OwnerBudgetSummary
    chapter_count: int
    failed_count: int
    audit_required: bool
    audit_failed_count: int
    audit_skipped_count: int
    gate_blocked_count: int
    chapters_closed: bool


@dataclass(frozen=True)
class OwnerWriteManifest:
    """从生产 write manifest 收窄出的身份、模型与章节证据事实。

    Args:
        声明字段: 目标、模板 provenance、模型、fallback 与章节 evidence。

    Returns:
        不可变 owner write manifest 事实。

    Raises:
        本类不显式抛出异常。
    """

    ticker: str
    company: str
    requested_template: str
    resolved_template: str
    selection_mode: str
    primary_model: str
    audit_model: str
    fallback_disabled: bool
    chapter_evidence: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class ReceiptFinding:
    """从 acceptance receipt 严格解析出的 finding。

    Args:
        code: 稳定 finding code。
        gate: hard gate 名称。
        severity: 严重级别。
        message: 已脱敏说明。
        locator: 可选相对定位。

    Returns:
        不可变 receipt finding。

    Raises:
        本类不显式抛出异常。
    """

    code: str
    gate: str
    severity: FindingSeverity
    message: str
    locator: str | None


@dataclass(frozen=True)
class ReceiptArtifact:
    """从 acceptance receipt 严格解析出的生产 artifact 引用。

    Args:
        locator: package-relative artifact 定位。
        sha256: artifact 字节摘要。

    Returns:
        不含生产原文的不可变引用。

    Raises:
        本类不显式抛出异常。
    """

    locator: str
    sha256: str


@dataclass(frozen=True)
class AcceptanceReceipt:
    """严格解析后的 deterministic acceptance receipt。

    Args:
        声明字段: 时间、三态、评分、hard gates、findings、引用与 residuals。

    Returns:
        不可变 deterministic acceptance receipt。

    Raises:
        本类不显式抛出异常。
    """

    evaluated_at: datetime
    verdict: Verdict
    total_score: int | None
    dimension_scores: tuple[tuple[str, int | None], ...]
    hard_gates: tuple[tuple[str, Literal["passed", "pending", "failed"]], ...]
    findings: tuple[ReceiptFinding, ...]
    artifacts: tuple[ReceiptArtifact, ...]
    residuals: tuple[str, ...]


def canonical_json_bytes(payload: JsonValue) -> bytes:
    """生成禁止 NaN、键排序且无多余空白的 UTF-8 JSON 字节。

    Args:
        payload: 严格 JSON 值。

    Returns:
        canonical JSON UTF-8 字节。

    Raises:
        ContractError: 输入含非有限浮点数或非 JSON 值时抛出。
    """

    _validate_json_value(payload, "$")
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError(f"无法生成 canonical JSON: {exc}") from exc


def canonical_json_sha256(payload: JsonValue) -> str:
    """计算严格 JSON 值的 canonical SHA-256。

    Args:
        payload: 严格 JSON 值。

    Returns:
        小写十六进制 SHA-256。

    Raises:
        ContractError: 输入不是严格 JSON 时抛出。
    """

    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def parse_json_bytes(payload: bytes, *, label: str) -> JsonValue:
    """严格解析 JSON 字节并拒绝 NaN/Infinity。

    Args:
        payload: UTF-8 JSON 字节。
        label: 错误上下文标签。

    Returns:
        严格 JSON 值。

    Raises:
        ContractError: 编码、语法或 JSON 值域非法时抛出。
    """

    try:
        parsed: JsonValue = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"{label} 不是合法 UTF-8 JSON: {exc}") from exc
    _validate_json_value(parsed, label)
    return parsed


def load_json_file(path: Path, *, label: str) -> JsonObject:
    """只读加载一个严格 JSON 对象文件。

    Args:
        path: 待读取的普通文件。
        label: 错误上下文标签。

    Returns:
        JSON 顶层对象。

    Raises:
        ContractError: 路径不是普通非 symlink 文件、JSON 非法或顶层非对象时抛出。
        OSError: 文件读取失败时抛出。
    """

    if path.is_symlink() or not path.is_file():
        raise ContractError(f"{label} 必须是普通非 symlink 文件")
    return _require_mapping(parse_json_bytes(path.read_bytes(), label=label), label)


def format_utc(value: datetime) -> str:
    """把带时区时间规范化为 UTC RFC3339。

    Args:
        value: 带时区 datetime。

    Returns:
        以 ``Z`` 结尾、秒精度的 UTC RFC3339。

    Raises:
        ContractError: 时间不带时区时抛出。
    """

    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractError("datetime 必须带时区")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", _AS_OF_SUFFIX)


def parse_acceptance_contract(payload: JsonValue) -> AcceptanceContract:
    """严格解析固定验收 contract。

    Args:
        payload: 未信任 JSON 值。

    Returns:
        不可变验收 contract。

    Raises:
        ContractError: 缺字段、未知字段、类型或值域非法时抛出。
    """

    root = _strict_object(
        payload,
        "contract",
        {
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
        },
    )
    _expect_equal(_require_int(root["schema_version"], "contract.schema_version"), 1, "contract.schema_version")
    _expect_equal(
        _require_string(root["contract_type"], "contract.contract_type"),
        "investment_agent_acceptance",
        "contract.contract_type",
    )
    target_raw = _strict_object(root["target"], "contract.target", {"ticker", "company", "research_template"})
    policy = _strict_object(
        root["fixture_policy"],
        "contract.fixture_policy",
        {"deterministic", "external_calls_allowed", "live_freshness_claimed"},
    )
    roles = _strict_object(root["model_roles"], "contract.model_roles", {"primary", "audit"})
    report = _strict_object(
        root["report_contract"],
        "contract.report_contract",
        {"required_topics", "required_evidence_parts", "valuation_reference_price"},
    )
    reference = _strict_object(
        report["valuation_reference_price"],
        "contract.report_contract.valuation_reference_price",
        {"price", "currency", "market_date", "material_document_id"},
    )
    score = _strict_object(
        root["score_contract"],
        "contract.score_contract",
        {"total_points", "minimum_total_score", "dimension_minimums"},
    )
    dimension_minimums = _require_mapping(score["dimension_minimums"], "contract.score_contract.dimension_minimums")
    minimum_pairs = tuple(
        (name, _require_nonnegative_int(value, f"contract.score_contract.dimension_minimums.{name}"))
        for name, value in sorted(dimension_minimums.items())
    )
    total_points = _require_positive_int(score["total_points"], "contract.score_contract.total_points")
    minimum_total = _require_nonnegative_int(
        score["minimum_total_score"], "contract.score_contract.minimum_total_score"
    )
    if minimum_total > total_points:
        raise ContractError("contract.minimum_total_score 不得超过 total_points")
    return AcceptanceContract(
        fixture_id=_require_nonempty_string(root["fixture_id"], "contract.fixture_id"),
        target=AcceptanceTarget(
            ticker=_require_nonempty_string(target_raw["ticker"], "contract.target.ticker"),
            company=_require_nonempty_string(target_raw["company"], "contract.target.company"),
            research_template=_require_nonempty_string(
                target_raw["research_template"], "contract.target.research_template"
            ),
        ),
        deterministic=_require_bool(policy["deterministic"], "contract.fixture_policy.deterministic"),
        external_calls_allowed=_require_bool(
            policy["external_calls_allowed"], "contract.fixture_policy.external_calls_allowed"
        ),
        live_freshness_claimed=_require_bool(
            policy["live_freshness_claimed"], "contract.fixture_policy.live_freshness_claimed"
        ),
        model_roles=ModelRoles(
            primary=_require_nonempty_string(roles["primary"], "contract.model_roles.primary"),
            audit=_require_nonempty_string(roles["audit"], "contract.model_roles.audit"),
        ),
        required_topics=_string_tuple(report["required_topics"], "contract.report_contract.required_topics"),
        required_evidence_parts=_string_tuple(
            report["required_evidence_parts"], "contract.report_contract.required_evidence_parts"
        ),
        valuation_reference_price=ValuationReferencePrice(
            price=_require_positive_decimal(reference["price"], "contract.valuation_reference_price.price"),
            currency=_require_nonempty_string(reference["currency"], "contract.valuation_reference_price.currency"),
            market_date=_require_date(reference["market_date"], "contract.valuation_reference_price.market_date"),
            material_document_id=_require_nonempty_string(
                reference["material_document_id"], "contract.valuation_reference_price.material_document_id"
            ),
        ),
        score_contract=ScoreContract(
            total_points=total_points,
            minimum_total_score=minimum_total,
            dimension_minimums=minimum_pairs,
        ),
        hard_gates=_unique_string_tuple(root["hard_gates"], "contract.hard_gates"),
        required_research_artifacts=_fixed_research_artifacts(
            root["required_research_artifacts"],
            "contract.required_research_artifacts",
        ),
    )


def parse_price_snapshot(payload: JsonValue) -> PriceSnapshot:
    """严格解析六字段价格快照。

    Args:
        payload: 未信任 JSON 值。

    Returns:
        不可变价格快照。

    Raises:
        ContractError: 字段、类型、URL、价格或时间非法时抛出。
    """

    root = _strict_object(
        payload,
        "price_snapshot",
        {"price", "currency", "market_date", "source_url", "captured_at", "max_age_days"},
    )
    source_url = _require_nonempty_string(root["source_url"], "price_snapshot.source_url")
    if not source_url.startswith(("https://", "http://")):
        raise ContractError("price_snapshot.source_url 必须是 HTTP(S) URL")
    return PriceSnapshot(
        price=_require_positive_decimal(root["price"], "price_snapshot.price"),
        currency=_require_nonempty_string(root["currency"], "price_snapshot.currency").upper(),
        market_date=_require_date(root["market_date"], "price_snapshot.market_date"),
        source_url=source_url,
        captured_at=_require_datetime(root["captured_at"], "price_snapshot.captured_at"),
        max_age_days=_require_nonnegative_int(root["max_age_days"], "price_snapshot.max_age_days"),
    )


def parse_source_inventory(payload: JsonValue) -> SourceInventory:
    """严格解析验收源清单并规范化文档顺序。

    Args:
        payload: 未信任 JSON 值。

    Returns:
        按 ``filing_date/form/document_id`` 排序的不可变源清单。

    Raises:
        ContractError: schema、字段、日期、指纹或唯一性非法时抛出。
    """

    root = _strict_object(
        payload,
        "source_inventory",
        {
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
        },
    )
    _expect_equal(
        _require_int(root["schema_version"], "source_inventory.schema_version"), 1, "source_inventory.schema_version"
    )
    _expect_equal(
        _require_string(root["inventory_type"], "source_inventory.inventory_type"),
        "investment_agent_source_inventory",
        "source_inventory.inventory_type",
    )
    windows = tuple(
        _parse_source_window(item, f"source_inventory.source_windows[{index}]")
        for index, item in enumerate(_require_list(root["source_windows"], "source_inventory.source_windows"))
    )
    latest_raw = _require_mapping(root["latest_discovery"], "source_inventory.latest_discovery")
    latest = tuple(
        (form, _require_nonempty_string(value, f"source_inventory.latest_discovery.{form}"))
        for form, value in sorted(latest_raw.items())
    )
    documents = tuple(
        sorted(
            (
                _parse_source_document(item, f"source_inventory.documents[{index}]")
                for index, item in enumerate(_require_list(root["documents"], "source_inventory.documents"))
            ),
            key=lambda item: (item.filing_date, item.form, item.document_id),
        )
    )
    document_ids = [item.document_id for item in documents]
    if len(document_ids) != len(set(document_ids)):
        raise ContractError("source_inventory.documents 存在重复 document_id")
    return SourceInventory(
        fixture_id=_require_nonempty_string(root["fixture_id"], "source_inventory.fixture_id"),
        ticker=_require_nonempty_string(root["ticker"], "source_inventory.ticker"),
        company=_require_nonempty_string(root["company"], "source_inventory.company"),
        as_of=_require_datetime(root["as_of"], "source_inventory.as_of"),
        live_freshness_claimed=_require_bool(root["live_freshness_claimed"], "source_inventory.live_freshness_claimed"),
        source_windows=windows,
        latest_discovery=latest,
        documents=documents,
    )


def parse_quality_review(payload: JsonValue) -> QualityReview:
    """严格解析完整或待填写的人工质量 rubric。

    Args:
        payload: 未信任 JSON 值。

    Returns:
        不可变质量复核对象。

    Raises:
        ContractError: schema、三态、计分或字段闭包非法时抛出。
    """

    root = _strict_object(
        payload,
        "quality_review",
        {
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
        },
    )
    _expect_equal(
        _require_int(root["schema_version"], "quality_review.schema_version"), 1, "quality_review.schema_version"
    )
    _expect_equal(
        _require_string(root["review_type"], "quality_review.review_type"),
        "investment_agent_quality_review",
        "quality_review.review_type",
    )
    dimensions_raw = _require_mapping(root["dimensions"], "quality_review.dimensions")
    dimensions = tuple(
        _parse_rubric_dimension(name, value, f"quality_review.dimensions.{name}")
        for name, value in sorted(dimensions_raw.items())
    )
    counts_raw = _strict_object(root["finding_counts"], "quality_review.finding_counts", {"high", "medium", "low"})
    findings = tuple(
        _parse_manual_finding(item, f"quality_review.findings[{index}]")
        for index, item in enumerate(_require_list(root["findings"], "quality_review.findings"))
    )
    status_text = _require_string(root["status"], "quality_review.status")
    if status_text == "PASS":
        status: Verdict = "PASS"
    elif status_text == "PENDING_MANUAL_REVIEW":
        status = "PENDING_MANUAL_REVIEW"
    elif status_text == "FAIL":
        status = "FAIL"
    else:
        raise ContractError("quality_review.status 必须是 PASS/PENDING_MANUAL_REVIEW/FAIL")
    return QualityReview(
        fixture_id=_require_nonempty_string(root["fixture_id"], "quality_review.fixture_id"),
        reviewer_role=_optional_nonempty_string(root["reviewer_role"], "quality_review.reviewer_role"),
        reviewer_id_label=_optional_nonempty_string(root["reviewer_id_label"], "quality_review.reviewer_id_label"),
        status=status,
        dimensions=dimensions,
        total_score=_optional_nonnegative_int(root["total_score"], "quality_review.total_score"),
        finding_counts=FindingCounts(
            high=_require_nonnegative_int(counts_raw["high"], "quality_review.finding_counts.high"),
            medium=_require_nonnegative_int(counts_raw["medium"], "quality_review.finding_counts.medium"),
            low=_require_nonnegative_int(counts_raw["low"], "quality_review.finding_counts.low"),
        ),
        findings=findings,
        completed_at=_optional_datetime(root["completed_at"], "quality_review.completed_at"),
    )


def parse_owner_run_summary(payload: JsonValue) -> OwnerRunSummary:
    """在唯一 owner ingress 把生产 run summary 收窄为验收事实。

    Args:
        payload: 生产 ``write_run_summary_v3`` 宽载荷。

    Returns:
        不再传播宽类型的不可变摘要。

    Raises:
        ContractError: 验收所需字段缺失或类型非法时抛出。
    """

    root = _require_mapping(payload, "run_summary")
    schema_version = _require_nonempty_string(
        _required(root, "schema_version", "run_summary"), "run_summary.schema_version"
    )
    roles = _require_mapping(_required(root, "model_roles", "run_summary"), "run_summary.model_roles")
    primary = _require_mapping(
        _required(roles, "primary", "run_summary.model_roles"), "run_summary.model_roles.primary"
    )
    audit_role = _require_mapping(_required(roles, "audit", "run_summary.model_roles"), "run_summary.model_roles.audit")
    usage = _require_mapping(_required(root, "model_usage", "run_summary"), "run_summary.model_usage")
    cost = _require_mapping(_required(usage, "cost", "run_summary.model_usage"), "run_summary.model_usage.cost")
    budget = _parse_owner_budget(_required(root, "budget", "run_summary"), "run_summary.budget")
    audit = _require_mapping(_required(root, "audit", "run_summary"), "run_summary.audit")
    chapters_raw = _require_list(_required(root, "chapters", "run_summary"), "run_summary.chapters")
    chapters_closed = bool(chapters_raw)
    for index, chapter_value in enumerate(chapters_raw):
        chapter = _require_mapping(chapter_value, f"run_summary.chapters[{index}]")
        chapters_closed = chapters_closed and (
            _require_string(
                _required(chapter, "status", f"run_summary.chapters[{index}]"), f"run_summary.chapters[{index}].status"
            )
            == "passed"
            and _require_bool(
                _required(chapter, "audit_required", f"run_summary.chapters[{index}]"),
                f"run_summary.chapters[{index}].audit_required",
            )
            and _require_bool(
                _required(chapter, "audit_passed", f"run_summary.chapters[{index}]"),
                f"run_summary.chapters[{index}].audit_passed",
            )
            and _require_bool(
                _required(chapter, "gate_passed", f"run_summary.chapters[{index}]"),
                f"run_summary.chapters[{index}].gate_passed",
            )
        )
    return OwnerRunSummary(
        schema_version=schema_version,
        ticker=_require_nonempty_string(_required(root, "ticker", "run_summary"), "run_summary.ticker"),
        gate_status=_require_nonempty_string(_required(root, "gate_status", "run_summary"), "run_summary.gate_status"),
        publication_status=_require_nonempty_string(
            _required(root, "publication_status", "run_summary"), "run_summary.publication_status"
        ),
        primary_models=_string_tuple(
            _required(primary, "model_names", "run_summary.model_roles.primary"),
            "run_summary.model_roles.primary.model_names",
        ),
        audit_models=_string_tuple(
            _required(audit_role, "model_names", "run_summary.model_roles.audit"),
            "run_summary.model_roles.audit.model_names",
        ),
        usage_status=_require_nonempty_string(
            _required(usage, "usage_status", "run_summary.model_usage"), "run_summary.model_usage.usage_status"
        ),
        request_count=_require_nonnegative_int(
            _required(usage, "request_count", "run_summary.model_usage"), "run_summary.model_usage.request_count"
        ),
        total_tokens=_require_nonnegative_int(
            _required(usage, "total_tokens", "run_summary.model_usage"), "run_summary.model_usage.total_tokens"
        ),
        cost_currency=_require_nonempty_string(
            _required(cost, "currency", "run_summary.model_usage.cost"), "run_summary.model_usage.cost.currency"
        ),
        cost_status=_require_nonempty_string(
            _required(cost, "status", "run_summary.model_usage.cost"), "run_summary.model_usage.cost.status"
        ),
        known_estimated_cost=_require_nonnegative_decimal(
            _required(cost, "known_estimated_cost", "run_summary.model_usage.cost"),
            "run_summary.model_usage.cost.known_estimated_cost",
        ),
        budget=budget,
        chapter_count=_require_nonnegative_int(
            _required(root, "chapter_count", "run_summary"), "run_summary.chapter_count"
        ),
        failed_count=_require_nonnegative_int(
            _required(root, "failed_count", "run_summary"), "run_summary.failed_count"
        ),
        audit_required=_require_bool(_required(audit, "required", "run_summary.audit"), "run_summary.audit.required"),
        audit_failed_count=_require_nonnegative_int(
            _required(audit, "failed_count", "run_summary.audit"), "run_summary.audit.failed_count"
        ),
        audit_skipped_count=_require_nonnegative_int(
            _required(audit, "skipped_count", "run_summary.audit"), "run_summary.audit.skipped_count"
        ),
        gate_blocked_count=_require_nonnegative_int(
            _required(audit, "gate_blocked_count", "run_summary.audit"), "run_summary.audit.gate_blocked_count"
        ),
        chapters_closed=chapters_closed,
    )


def parse_owner_write_manifest(payload: JsonValue) -> OwnerWriteManifest:
    """在唯一 owner ingress 把生产 write manifest 收窄为验收事实。

    Args:
        payload: 生产 manifest 宽载荷。

    Returns:
        不可变 manifest 验收视图。

    Raises:
        ContractError: 所需字段、章节或 evidence 类型非法时抛出。
    """

    root = _require_mapping(payload, "write_manifest")
    config = _require_mapping(_required(root, "config", "write_manifest"), "write_manifest.config")
    scenes = _require_mapping(
        _required(config, "scene_models", "write_manifest.config"), "write_manifest.config.scene_models"
    )
    write_scene = _require_mapping(
        _required(scenes, "write", "write_manifest.config.scene_models"), "write_manifest.config.scene_models.write"
    )
    audit_scene = _require_mapping(
        _required(scenes, "audit", "write_manifest.config.scene_models"), "write_manifest.config.scene_models.audit"
    )
    chapters = _require_mapping(_required(root, "chapter_results", "write_manifest"), "write_manifest.chapter_results")
    evidence_rows: list[tuple[str, tuple[str, ...]]] = []
    for title, chapter_value in sorted(chapters.items()):
        chapter = _require_mapping(chapter_value, f"write_manifest.chapter_results.{title}")
        evidence_rows.append(
            (
                title,
                _string_tuple(
                    _required(chapter, "evidence_items", f"write_manifest.chapter_results.{title}"),
                    f"write_manifest.chapter_results.{title}.evidence_items",
                ),
            )
        )
    return OwnerWriteManifest(
        ticker=_require_nonempty_string(
            _required(config, "ticker", "write_manifest.config"), "write_manifest.config.ticker"
        ),
        company=_require_nonempty_string(
            _required(config, "company", "write_manifest.config"), "write_manifest.config.company"
        ),
        requested_template=_require_nonempty_string(
            _required(config, "research_template_requested_name", "write_manifest.config"),
            "write_manifest.config.research_template_requested_name",
        ),
        resolved_template=_require_nonempty_string(
            _required(config, "research_template_resolved_name", "write_manifest.config"),
            "write_manifest.config.research_template_resolved_name",
        ),
        selection_mode=_require_nonempty_string(
            _required(config, "research_template_selection_mode", "write_manifest.config"),
            "write_manifest.config.research_template_selection_mode",
        ),
        primary_model=_require_nonempty_string(
            _required(write_scene, "name", "write_manifest.config.scene_models.write"),
            "write_manifest.config.scene_models.write.name",
        ),
        audit_model=_require_nonempty_string(
            _required(audit_scene, "name", "write_manifest.config.scene_models.audit"),
            "write_manifest.config.scene_models.audit.name",
        ),
        fallback_disabled=(
            _require_string(
                _required(config, "write_fallback_model_name", "write_manifest.config"),
                "write_manifest.config.write_fallback_model_name",
            )
            == ""
            and _require_string(
                _required(config, "audit_fallback_model_name", "write_manifest.config"),
                "write_manifest.config.audit_fallback_model_name",
            )
            == ""
        ),
        chapter_evidence=tuple(evidence_rows),
    )


def parse_acceptance_plan(payload: JsonValue) -> AcceptancePlan:
    """严格解析验收 plan schema。

    Args:
        payload: 未信任 JSON 值。

    Returns:
        不可变验收 plan。

    Raises:
        ContractError: 字段闭包、值域或 package 指纹非法时抛出。
    """

    root = _strict_object(
        payload,
        "acceptance_plan",
        {
            "schema_version",
            "plan_type",
            "ticker",
            "company",
            "research_template",
            "as_of",
            "git_sha",
            "dirty",
            "python_version",
            "platform",
            "timezone",
            "run_root",
            "package_inputs",
            "price_snapshot_sha256",
            "price_material_sha256",
            "budget",
            "max_wall_seconds",
            "termination_grace_seconds",
            "subprocess_env_policy",
            "price_material_document_id",
            "model_roles",
            "phase_specs",
            "required_environment",
            "terminal_action",
            "required_research_artifacts",
        },
    )
    _expect_equal(
        _require_int(root["schema_version"], "acceptance_plan.schema_version"),
        _PLAN_SCHEMA_VERSION,
        "acceptance_plan.schema_version",
    )
    _expect_equal(
        _require_string(root["plan_type"], "acceptance_plan.plan_type"),
        "investment_agent_acceptance_plan",
        "acceptance_plan.plan_type",
    )
    budget_raw = _strict_object(
        root["budget"],
        "acceptance_plan.budget",
        {"max_model_requests", "max_total_tokens", "max_estimated_cost", "budget_currency"},
    )
    roles_raw = _strict_object(
        root["model_roles"],
        "acceptance_plan.model_roles",
        {"primary", "audit"},
    )
    phase_specs = tuple(
        _parse_phase_spec(item, f"acceptance_plan.phase_specs[{index}]")
        for index, item in enumerate(_require_list(root["phase_specs"], "acceptance_plan.phase_specs"))
    )
    environment = tuple(
        _parse_environment_presence(item, f"acceptance_plan.required_environment[{index}]")
        for index, item in enumerate(
            _require_list(root["required_environment"], "acceptance_plan.required_environment")
        )
    )
    terminal_text = _require_string(root["terminal_action"], "acceptance_plan.terminal_action")
    if terminal_text != TERMINAL_ACTION:
        raise ContractError("acceptance_plan.terminal_action 必须是 verify")
    return AcceptancePlan(
        ticker=_require_nonempty_string(root["ticker"], "acceptance_plan.ticker"),
        company=_require_nonempty_string(root["company"], "acceptance_plan.company"),
        research_template=_require_nonempty_string(root["research_template"], "acceptance_plan.research_template"),
        as_of=_require_datetime(root["as_of"], "acceptance_plan.as_of"),
        git_sha=_require_git_object_id(root["git_sha"], "acceptance_plan.git_sha"),
        dirty=_require_bool(root["dirty"], "acceptance_plan.dirty"),
        python_version=_require_nonempty_string(root["python_version"], "acceptance_plan.python_version"),
        platform=_require_nonempty_string(root["platform"], "acceptance_plan.platform"),
        timezone=_require_nonempty_string(root["timezone"], "acceptance_plan.timezone"),
        run_root=_require_canonical_absolute_path(root["run_root"], "acceptance_plan.run_root"),
        package_inputs=_parse_package_inputs(root["package_inputs"], "acceptance_plan.package_inputs"),
        price_snapshot_sha256=_require_sha256(root["price_snapshot_sha256"], "acceptance_plan.price_snapshot_sha256"),
        price_material_sha256=_require_sha256(root["price_material_sha256"], "acceptance_plan.price_material_sha256"),
        budget=BudgetLimits(
            max_model_requests=_require_positive_int(
                budget_raw["max_model_requests"], "acceptance_plan.budget.max_model_requests"
            ),
            max_total_tokens=_require_positive_int(
                budget_raw["max_total_tokens"], "acceptance_plan.budget.max_total_tokens"
            ),
            max_estimated_cost=_require_positive_decimal(
                budget_raw["max_estimated_cost"], "acceptance_plan.budget.max_estimated_cost"
            ),
            budget_currency=_require_nonempty_string(
                budget_raw["budget_currency"], "acceptance_plan.budget.budget_currency"
            ),
        ),
        max_wall_seconds=_require_positive_int(root["max_wall_seconds"], "acceptance_plan.max_wall_seconds"),
        termination_grace_seconds=_require_positive_int(
            root["termination_grace_seconds"], "acceptance_plan.termination_grace_seconds"
        ),
        subprocess_env_policy=_parse_subprocess_env_policy(
            root["subprocess_env_policy"],
            "acceptance_plan.subprocess_env_policy",
        ),
        price_material_document_id=_require_nonempty_string(
            root["price_material_document_id"],
            "acceptance_plan.price_material_document_id",
        ),
        model_roles=ModelRoles(
            primary=_require_nonempty_string(roles_raw["primary"], "acceptance_plan.model_roles.primary"),
            audit=_require_nonempty_string(roles_raw["audit"], "acceptance_plan.model_roles.audit"),
        ),
        phase_specs=phase_specs,
        required_environment=environment,
        terminal_action="verify",
        required_research_artifacts=_fixed_research_artifacts(
            root["required_research_artifacts"],
            "acceptance_plan.required_research_artifacts",
        ),
    )


def parse_phase_receipt(payload: JsonValue) -> PhaseReceipt:
    """严格解析阶段 receipt schema。

    Args:
        payload: 未信任 JSON 值。

    Returns:
        不可变阶段 receipt。

    Raises:
        ContractError: 字段闭包、时间、数值或 argv 非法时抛出。
    """

    root = _strict_object(
        payload,
        "phase_receipt",
        {
            "schema_version",
            "receipt_type",
            "plan_fingerprint",
            "phase_name",
            "status",
            "started_at",
            "ended_at",
            "duration_seconds",
            "remaining_wall_seconds",
            "command_records",
        },
    )
    _expect_equal(
        _require_int(root["schema_version"], "phase_receipt.schema_version"),
        _PHASE_SCHEMA_VERSION,
        "phase_receipt.schema_version",
    )
    _expect_equal(
        _require_string(root["receipt_type"], "phase_receipt.receipt_type"),
        "investment_agent_acceptance_phase",
        "phase_receipt.receipt_type",
    )
    status_text = _require_string(root["status"], "phase_receipt.status")
    if status_text == "passed":
        status: PhaseStatus = "passed"
    elif status_text == "failed":
        status = "failed"
    elif status_text == "timeout":
        status = "timeout"
    elif status_text == "signal":
        status = "signal"
    else:
        raise ContractError("phase_receipt.status 必须是 passed/failed/timeout/signal")
    return PhaseReceipt(
        plan_fingerprint=_require_sha256(root["plan_fingerprint"], "phase_receipt.plan_fingerprint"),
        phase_name=_require_nonempty_string(root["phase_name"], "phase_receipt.phase_name"),
        status=status,
        started_at=_require_datetime(root["started_at"], "phase_receipt.started_at"),
        ended_at=_require_datetime(root["ended_at"], "phase_receipt.ended_at"),
        duration_seconds=_require_nonnegative_float(root["duration_seconds"], "phase_receipt.duration_seconds"),
        remaining_wall_seconds=_require_nonnegative_float(
            root["remaining_wall_seconds"], "phase_receipt.remaining_wall_seconds"
        ),
        command_records=tuple(
            _parse_command_record(item, f"phase_receipt.command_records[{index}]")
            for index, item in enumerate(
                _require_list(root["command_records"], "phase_receipt.command_records")
            )
        ),
    )


def parse_acceptance_receipt(payload: JsonValue) -> AcceptanceReceipt:
    """严格解析 evaluator 产生的 acceptance receipt。

    Args:
        payload: 未信任 JSON 值。

    Returns:
        不可变 receipt contract。

    Raises:
        ContractError: 缺字段、未知字段、三态、finding 或 artifact schema 非法时抛出。
    """

    root = _strict_object(
        payload,
        "acceptance_receipt",
        {
            "schema_version",
            "receipt_type",
            "evaluated_at",
            "verdict",
            "total_score",
            "dimension_scores",
            "hard_gates",
            "findings",
            "artifacts",
            "residuals",
        },
    )
    _expect_equal(
        _require_int(root["schema_version"], "acceptance_receipt.schema_version"),
        _RECEIPT_SCHEMA_VERSION,
        "acceptance_receipt.schema_version",
    )
    _expect_equal(
        _require_string(root["receipt_type"], "acceptance_receipt.receipt_type"),
        "investment_agent_acceptance",
        "acceptance_receipt.receipt_type",
    )
    verdict_text = _require_string(root["verdict"], "acceptance_receipt.verdict")
    if verdict_text == "PASS":
        verdict: Verdict = "PASS"
    elif verdict_text == "PENDING_MANUAL_REVIEW":
        verdict = "PENDING_MANUAL_REVIEW"
    elif verdict_text == "FAIL":
        verdict = "FAIL"
    else:
        raise ContractError("acceptance_receipt.verdict 非法")
    dimensions_raw = _require_mapping(root["dimension_scores"], "acceptance_receipt.dimension_scores")
    dimensions = tuple(
        (name, _optional_nonnegative_int(value, f"acceptance_receipt.dimension_scores.{name}"))
        for name, value in sorted(dimensions_raw.items())
    )
    gates_raw = _require_mapping(root["hard_gates"], "acceptance_receipt.hard_gates")
    gates: list[tuple[str, Literal["passed", "pending", "failed"]]] = []
    for name, value in sorted(gates_raw.items()):
        status_text = _require_string(value, f"acceptance_receipt.hard_gates.{name}")
        if status_text == "passed":
            status: Literal["passed", "pending", "failed"] = "passed"
        elif status_text == "pending":
            status = "pending"
        elif status_text == "failed":
            status = "failed"
        else:
            raise ContractError(f"acceptance_receipt.hard_gates.{name} 非法")
        gates.append((name, status))
    findings = tuple(
        _parse_receipt_finding(item, f"acceptance_receipt.findings[{index}]")
        for index, item in enumerate(_require_list(root["findings"], "acceptance_receipt.findings"))
    )
    artifacts = tuple(
        _parse_receipt_artifact(item, f"acceptance_receipt.artifacts[{index}]")
        for index, item in enumerate(_require_list(root["artifacts"], "acceptance_receipt.artifacts"))
    )
    return AcceptanceReceipt(
        evaluated_at=_require_datetime(root["evaluated_at"], "acceptance_receipt.evaluated_at"),
        verdict=verdict,
        total_score=_optional_nonnegative_int(root["total_score"], "acceptance_receipt.total_score"),
        dimension_scores=dimensions,
        hard_gates=tuple(gates),
        findings=findings,
        artifacts=artifacts,
        residuals=_string_tuple(root["residuals"], "acceptance_receipt.residuals", allow_empty=True),
    )


def build_package_input_fingerprints() -> PackageInputFingerprints:
    """从 package resolver 构建配置与研究资产指纹闭包。

    Args:
        无。

    Returns:
        不含绝对路径的完整 package 输入指纹。

    Raises:
        ContractError: resolver 真源不可读、含 symlink/非普通文件/重复定位或缺关键文件时抛出。
        OSError: 文件读取或 stat 失败时抛出。
    """

    config_root = _require_regular_directory(resolve_package_config_path(), "package config root")
    assets_root = _require_regular_directory(resolve_package_assets_path(), "package assets root")
    config_tree = _fingerprint_tree(config_root, locator="dayu/config", include_all_regular=True)
    diagnostics = tuple(
        _fingerprint_file(config_root / locator, f"dayu/config/{locator}") for locator in _CONFIG_DIAGNOSTIC_LOCATORS
    )
    research_root = _require_regular_directory(assets_root / _RESEARCH_TREE_DIR, "package research template root")
    research_tree = _fingerprint_tree(
        research_root,
        locator="dayu/assets/research_templates",
        include_all_regular=False,
    )
    base_template = _fingerprint_file(
        assets_root / _BASE_TEMPLATE_NAME,
        f"dayu/assets/{_BASE_TEMPLATE_NAME}",
    )
    return PackageInputFingerprints(
        config_tree=config_tree,
        config_diagnostics=diagnostics,
        research_tree=research_tree,
        base_template=base_template,
    )


def assert_package_input_fingerprints(expected: PackageInputFingerprints) -> None:
    """在任何 subprocess 前验证 package 输入闭包未漂移。

    Args:
        expected: plan 已指纹化的 package 输入。

    Returns:
        无。

    Raises:
        FingerprintDriftError: 任一 tree、关键配置或 base template 指纹漂移时抛出。
        ContractError: 当前 package 真源本身非法时抛出。
        OSError: 当前 package 真源读取失败时抛出。
    """

    current = build_package_input_fingerprints()
    if current != expected:
        raise FingerprintDriftError("package config/research asset fingerprint drift")


def _parse_owner_budget(payload: JsonValue, label: str) -> OwnerBudgetSummary:
    """把 owner budget summary 收窄为验收字段。

    Args:
        payload: 宽 owner budget 载荷。
        label: 错误标签。

    Returns:
        不可变预算摘要。

    Raises:
        ContractError: 所需字段类型非法时抛出。
    """

    root = _require_mapping(payload, label)
    limits = _require_mapping(_required(root, "limits", label), f"{label}.limits")
    usage = _require_mapping(_required(root, "usage", label), f"{label}.usage")
    block = _required(root, "block", label)
    if block is not None and not isinstance(block, dict):
        raise ContractError(f"{label}.block 必须是对象或 null")
    return OwnerBudgetSummary(
        enabled=_require_bool(_required(root, "enabled", label), f"{label}.enabled"),
        status=_require_nonempty_string(_required(root, "status", label), f"{label}.status"),
        max_model_requests=_require_positive_int(
            _required(limits, "max_model_requests", f"{label}.limits"), f"{label}.limits.max_model_requests"
        ),
        max_total_tokens=_require_positive_int(
            _required(limits, "max_total_tokens", f"{label}.limits"), f"{label}.limits.max_total_tokens"
        ),
        max_estimated_cost=_require_positive_decimal(
            _required(limits, "max_estimated_cost", f"{label}.limits"), f"{label}.limits.max_estimated_cost"
        ),
        budget_currency=_require_nonempty_string(
            _required(limits, "budget_currency", f"{label}.limits"), f"{label}.limits.budget_currency"
        ),
        model_requests=_require_nonnegative_int(
            _required(usage, "model_requests", f"{label}.usage"), f"{label}.usage.model_requests"
        ),
        total_tokens=_require_nonnegative_int(
            _required(usage, "total_tokens", f"{label}.usage"), f"{label}.usage.total_tokens"
        ),
        estimated_cost=_require_nonnegative_decimal(
            _required(usage, "estimated_cost", f"{label}.usage"), f"{label}.usage.estimated_cost"
        ),
        usage_status=_require_nonempty_string(
            _required(usage, "usage_status", f"{label}.usage"), f"{label}.usage.usage_status"
        ),
        cost_status=_require_nonempty_string(
            _required(usage, "cost_status", f"{label}.usage"), f"{label}.usage.cost_status"
        ),
        currency=_require_nonempty_string(_required(usage, "currency", f"{label}.usage"), f"{label}.usage.currency"),
        active_reservation_count=_require_nonnegative_int(
            _required(root, "active_reservation_count", label), f"{label}.active_reservation_count"
        ),
        block_present=block is not None,
    )


def _parse_source_window(payload: JsonValue, label: str) -> SourceWindow:
    """严格解析一个日期窗口。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        不可变日期窗口。

    Raises:
        ContractError: 字段闭包、form 或日期非法时抛出。
    """

    root = _strict_object(payload, label, {"forms", "start_date", "end_date"})
    return SourceWindow(
        forms=_unique_string_tuple(root["forms"], f"{label}.forms"),
        start_date=_require_date(root["start_date"], f"{label}.start_date"),
        end_date=_require_date(root["end_date"], f"{label}.end_date"),
    )


def _parse_source_document(payload: JsonValue, label: str) -> SourceDocument:
    """严格解析一个 source inventory 文档。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        不可变源文档。

    Raises:
        ContractError: 字段、日期、来源类型或指纹不闭合时抛出。
    """

    root = _strict_object(
        payload,
        label,
        {
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
        },
    )
    kind_text = _require_string(root["source_kind"], f"{label}.source_kind")
    if kind_text == "filing":
        kind: Literal["filing", "material"] = "filing"
    elif kind_text == "material":
        kind = "material"
    else:
        raise ContractError(f"{label}.source_kind 必须是 filing/material")
    processed_raw = _strict_object(
        root["processed"],
        f"{label}.processed",
        {"exists", "parser_version", "quality", "reprocess_required", "schema_version", "source_fingerprint"},
    )
    processed = ProcessedState(
        exists=_require_bool(processed_raw["exists"], f"{label}.processed.exists"),
        parser_version=_require_nonempty_string(processed_raw["parser_version"], f"{label}.processed.parser_version"),
        quality=_require_nonempty_string(processed_raw["quality"], f"{label}.processed.quality"),
        reprocess_required=_require_bool(processed_raw["reprocess_required"], f"{label}.processed.reprocess_required"),
        schema_version=_require_nonempty_string(processed_raw["schema_version"], f"{label}.processed.schema_version"),
        source_fingerprint=_require_sha256(
            processed_raw["source_fingerprint"], f"{label}.processed.source_fingerprint"
        ),
    )
    fingerprint = _require_sha256(root["processed_state_fingerprint"], f"{label}.processed_state_fingerprint")
    if canonical_json_sha256(processed.to_json()) != fingerprint:
        raise ContractError(f"{label}.processed_state_fingerprint 与状态不一致")
    return SourceDocument(
        document_id=_require_nonempty_string(root["document_id"], f"{label}.document_id"),
        source_kind=kind,
        form=_require_nonempty_string(root["form"], f"{label}.form"),
        filing_date=_require_date(root["filing_date"], f"{label}.filing_date"),
        report_date=_require_date(root["report_date"], f"{label}.report_date"),
        fiscal_year=_optional_int(root["fiscal_year"], f"{label}.fiscal_year"),
        fiscal_period=_optional_nonempty_string(root["fiscal_period"], f"{label}.fiscal_period"),
        accession=_optional_nonempty_string(root["accession"], f"{label}.accession"),
        source_locator=_require_nonempty_string(root["source_locator"], f"{label}.source_locator"),
        primary_file_sha256=_require_sha256(root["primary_file_sha256"], f"{label}.primary_file_sha256"),
        ingest_complete=_require_bool(root["ingest_complete"], f"{label}.ingest_complete"),
        processed=processed,
        processed_state_fingerprint=fingerprint,
    )


def _parse_rubric_dimension(name: str, payload: JsonValue, label: str) -> RubricDimension:
    """严格解析一个 rubric 维度。

    Args:
        name: 维度稳定名称。
        payload: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        不可变 rubric 维度。

    Raises:
        ContractError: 维度 schema 或 item 列表非法时抛出。
    """

    root = _strict_object(payload, label, {"score", "max_score", "items"})
    items = tuple(
        _parse_rubric_item(item, f"{label}.items[{index}]")
        for index, item in enumerate(_require_list(root["items"], f"{label}.items"))
    )
    if not items:
        raise ContractError(f"{label}.items 不得为空")
    return RubricDimension(
        name=name,
        score=_optional_nonnegative_int(root["score"], f"{label}.score"),
        max_score=_require_positive_int(root["max_score"], f"{label}.max_score"),
        items=items,
    )


def _parse_rubric_item(payload: JsonValue, label: str) -> RubricItem:
    """严格解析一个 rubric 子项。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        不可变 rubric 子项。

    Raises:
        ContractError: 字段、分数或证据定位非法时抛出。
    """

    root = _strict_object(payload, label, {"item_id", "score", "max_score", "evidence_paths", "notes"})
    score = _optional_nonnegative_int(root["score"], f"{label}.score")
    max_score = _require_positive_int(root["max_score"], f"{label}.max_score")
    if score is not None and score > max_score:
        raise ContractError(f"{label}.score 不得超过 max_score")
    return RubricItem(
        item_id=_require_nonempty_string(root["item_id"], f"{label}.item_id"),
        score=score,
        max_score=max_score,
        evidence_paths=_string_tuple(root["evidence_paths"], f"{label}.evidence_paths", allow_empty=True),
        notes=_optional_nonempty_string(root["notes"], f"{label}.notes"),
    )


def _parse_manual_finding(payload: JsonValue, label: str) -> ManualFinding:
    """严格解析一个人工 finding。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        不可变人工 finding。

    Raises:
        ContractError: finding 字段、severity 或状态非法时抛出。
    """

    root = _strict_object(payload, label, {"finding_id", "severity", "status", "summary", "evidence_paths"})
    severity_text = _require_string(root["severity"], f"{label}.severity")
    if severity_text == "high":
        severity: FindingSeverity = "high"
    elif severity_text == "medium":
        severity = "medium"
    elif severity_text == "low":
        severity = "low"
    else:
        raise ContractError(f"{label}.severity 非法")
    status_text = _require_string(root["status"], f"{label}.status")
    if status_text == "open":
        status: Literal["open", "closed"] = "open"
    elif status_text == "closed":
        status = "closed"
    else:
        raise ContractError(f"{label}.status 非法")
    return ManualFinding(
        finding_id=_require_nonempty_string(root["finding_id"], f"{label}.finding_id"),
        severity=severity,
        status=status,
        summary=_require_nonempty_string(root["summary"], f"{label}.summary"),
        evidence_paths=_string_tuple(root["evidence_paths"], f"{label}.evidence_paths"),
    )


def _parse_receipt_finding(payload: JsonValue, label: str) -> ReceiptFinding:
    """严格解析 receipt 中的一条 finding。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        不可变 receipt finding。

    Raises:
        ContractError: 字段闭包或 severity 非法时抛出。
    """

    root = _strict_object(payload, label, {"code", "gate", "severity", "message", "locator"})
    severity_text = _require_string(root["severity"], f"{label}.severity")
    if severity_text == "high":
        severity: FindingSeverity = "high"
    elif severity_text == "medium":
        severity = "medium"
    elif severity_text == "low":
        severity = "low"
    else:
        raise ContractError(f"{label}.severity 非法")
    return ReceiptFinding(
        code=_require_nonempty_string(root["code"], f"{label}.code"),
        gate=_require_nonempty_string(root["gate"], f"{label}.gate"),
        severity=severity,
        message=_require_nonempty_string(root["message"], f"{label}.message"),
        locator=_optional_nonempty_string(root["locator"], f"{label}.locator"),
    )


def _parse_receipt_artifact(payload: JsonValue, label: str) -> ReceiptArtifact:
    """严格解析 receipt 中的生产 artifact 引用。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        不可变 artifact 引用。

    Raises:
        ContractError: locator 或 SHA-256 非法时抛出。
    """

    root = _strict_object(payload, label, {"locator", "sha256"})
    return ReceiptArtifact(
        locator=_require_safe_locator(root["locator"], f"{label}.locator"),
        sha256=_require_sha256(root["sha256"], f"{label}.sha256"),
    )


def _parse_phase_spec(payload: JsonValue, label: str) -> PhaseSpec:
    """严格解析一个有序 phase spec。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        不可变 phase spec。

    Raises:
        ContractError: 字段、阶段或命令 token matrix 非法时抛出。
    """

    root = _strict_object(payload, label, {"phase_name", "commands"})
    phase_name = _require_nonempty_string(root["phase_name"], f"{label}.phase_name")
    command_rows = _require_list(root["commands"], f"{label}.commands")
    commands = tuple(
        _string_tuple(item, f"{label}.commands[{index}]") for index, item in enumerate(command_rows)
    )
    return PhaseSpec(phase_name=phase_name, commands=commands)


def _parse_environment_presence(payload: JsonValue, label: str) -> EnvironmentPresence:
    """严格解析环境变量名称与存在性事实。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        不含 secret 值的不可变环境事实。

    Raises:
        ContractError: 字段、名称或布尔值非法时抛出。
    """

    root = _strict_object(payload, label, {"name", "present"})
    return EnvironmentPresence(
        name=_require_nonempty_string(root["name"], f"{label}.name"),
        present=_require_bool(root["present"], f"{label}.present"),
    )


def _parse_subprocess_env_policy(payload: JsonValue, label: str) -> tuple[tuple[str, str], ...]:
    """严格解析固定有序 non-secret subprocess 环境策略。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文。

    Returns:
        精确固定顺序的名称/值对。

    Raises:
        ContractError: 结构或固定值漂移时抛出。
    """

    rows = _require_list(payload, label)
    parsed = tuple(
        _string_tuple(row, f"{label}[{index}]")
        for index, row in enumerate(rows)
    )
    pairs: list[tuple[str, str]] = []
    for index, row in enumerate(parsed):
        if len(row) != _PAIR_WIDTH:
            raise ContractError(f"{label}[{index}] 必须精确含名称和值")
        pairs.append((row[0], row[1]))
    result = tuple(pairs)
    if result != SUBPROCESS_ENV_POLICY:
        raise ContractError(f"{label} 必须精确绑定固定策略")
    return result


def _parse_command_record(payload: JsonValue, label: str) -> CommandRecord:
    """严格解析一个 v3 command record。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文。

    Returns:
        不可变 command record。

    Raises:
        ContractError: lifecycle、stream 或 evidence schema 非法时抛出。
    """

    root = _strict_object(
        payload,
        label,
        {
            "command_index",
            "safe_argv",
            "argv_digest",
            "status",
            "started_at",
            "ended_at",
            "duration_seconds",
            "exit_code",
            "stop_reason",
            "termination_action",
            "partial_by_timeout",
            "stdout_sha256",
            "stderr_sha256",
            "stdout_summary",
            "stderr_summary",
            "evidence",
        },
    )
    status = _parse_phase_status(root["status"], f"{label}.status")
    termination = _parse_termination_action(root["termination_action"], f"{label}.termination_action")
    return CommandRecord(
        command_index=_require_nonnegative_int(root["command_index"], f"{label}.command_index"),
        safe_argv=_string_tuple(root["safe_argv"], f"{label}.safe_argv"),
        argv_digest=_require_sha256(root["argv_digest"], f"{label}.argv_digest"),
        status=status,
        started_at=_require_datetime(root["started_at"], f"{label}.started_at"),
        ended_at=_require_datetime(root["ended_at"], f"{label}.ended_at"),
        duration_seconds=_require_nonnegative_float(root["duration_seconds"], f"{label}.duration_seconds"),
        exit_code=_optional_int(root["exit_code"], f"{label}.exit_code"),
        stop_reason=_optional_nonempty_string(root["stop_reason"], f"{label}.stop_reason"),
        termination_action=termination,
        partial_by_timeout=_require_bool(root["partial_by_timeout"], f"{label}.partial_by_timeout"),
        stdout_sha256=_optional_sha256(root["stdout_sha256"], f"{label}.stdout_sha256"),
        stderr_sha256=_optional_sha256(root["stderr_sha256"], f"{label}.stderr_sha256"),
        stdout_summary=_optional_nonempty_string(root["stdout_summary"], f"{label}.stdout_summary"),
        stderr_summary=_optional_nonempty_string(root["stderr_summary"], f"{label}.stderr_summary"),
        evidence=_parse_command_evidence(root["evidence"], f"{label}.evidence"),
    )


def _parse_phase_status(payload: JsonValue, label: str) -> PhaseStatus:
    """严格解析 phase/command 状态闭集。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文。

    Returns:
        四态之一。

    Raises:
        ContractError: 状态不在闭集时抛出。
    """

    text = _require_string(payload, label)
    if text == "passed":
        return "passed"
    if text == "failed":
        return "failed"
    if text == "timeout":
        return "timeout"
    if text == "signal":
        return "signal"
    raise ContractError(f"{label} 必须是 passed/failed/timeout/signal")


def _parse_termination_action(payload: JsonValue, label: str) -> TerminationAction | None:
    """严格解析 timeout termination 闭集。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文。

    Returns:
        termination action 或 null。

    Raises:
        ContractError: 文本不在闭集时抛出。
    """

    if payload is None:
        return None
    text = _require_string(payload, label)
    if text == "not_started":
        return "not_started"
    if text == "terminate":
        return "terminate"
    if text == "kill":
        return "kill"
    if text == "termination_unconfirmed":
        return "termination_unconfirmed"
    raise ContractError(f"{label} 非法")


def _parse_command_evidence(payload: JsonValue, label: str) -> CommandEvidence | None:
    """按 discriminator 严格解析 evidence union 闭集。

    Args:
        payload: 未信任 JSON 值或 null。
        label: 错误上下文。

    Returns:
        三种 evidence 之一或 null。

    Raises:
        ContractError: discriminator 或成员 schema 非法时抛出。
    """

    if payload is None:
        return None
    mapping = _require_mapping(payload, label)
    kind = _require_nonempty_string(_required(mapping, "evidence_type", label), f"{label}.evidence_type")
    if kind == "download":
        return _parse_download_evidence(payload, label)
    if kind == "material_import":
        return _parse_material_evidence(payload, label)
    if kind == "process":
        return _parse_process_evidence(payload, label)
    raise ContractError(f"{label}.evidence_type 非法")


def _parse_download_evidence(payload: JsonValue, label: str) -> DownloadCommandEvidence:
    """严格解析 download evidence。

    Args:
        payload: 未信任 evidence 对象。
        label: 错误上下文。

    Returns:
        不可变 download evidence。

    Raises:
        ContractError: 字段、状态、计数或 row 非法时抛出。
    """

    root = _strict_object(
        payload,
        label,
        {
            "evidence_type",
            "ticker",
            "planned_forms",
            "canonical_forms",
            "start",
            "end",
            "owner_status",
            "summary",
            "rows",
        },
    )
    _expect_equal(_require_string(root["evidence_type"], f"{label}.evidence_type"), "download", label)
    owner_text = _require_string(root["owner_status"], f"{label}.owner_status")
    if owner_text == "ok":
        owner_status: Literal["ok", "downloaded", "skipped", "cancelled"] = "ok"
    elif owner_text == "downloaded":
        owner_status = "downloaded"
    elif owner_text == "skipped":
        owner_status = "skipped"
    elif owner_text == "cancelled":
        owner_status = "cancelled"
    else:
        raise ContractError(f"{label}.owner_status 非法")
    summary_root = _strict_object(
        root["summary"],
        f"{label}.summary",
        {"total", "downloaded", "skipped", "failed"},
    )
    return DownloadCommandEvidence(
        ticker=_require_nonempty_string(root["ticker"], f"{label}.ticker"),
        planned_forms=_unique_string_tuple(root["planned_forms"], f"{label}.planned_forms"),
        canonical_forms=_unique_string_tuple(root["canonical_forms"], f"{label}.canonical_forms"),
        start=_require_date(root["start"], f"{label}.start"),
        end=_require_date(root["end"], f"{label}.end"),
        owner_status=owner_status,
        summary=DownloadSummary(
            total=_require_nonnegative_int(summary_root["total"], f"{label}.summary.total"),
            downloaded=_require_nonnegative_int(summary_root["downloaded"], f"{label}.summary.downloaded"),
            skipped=_require_nonnegative_int(summary_root["skipped"], f"{label}.summary.skipped"),
            failed=_require_nonnegative_int(summary_root["failed"], f"{label}.summary.failed"),
        ),
        rows=tuple(
            _parse_download_row(row, f"{label}.rows[{index}]")
            for index, row in enumerate(_require_list(root["rows"], f"{label}.rows"))
        ),
    )


def _parse_download_row(payload: JsonValue, label: str) -> DownloadEvidenceRow:
    """严格解析一个 download section row。

    Args:
        payload: 未信任 row。
        label: 错误上下文。

    Returns:
        不可变 row。

    Raises:
        ContractError: 字段或 section status 非法时抛出。
    """

    root = _strict_object(
        payload,
        label,
        {"document_id", "accession", "canonical_form", "filing_date", "section_status"},
    )
    status_text = _require_string(root["section_status"], f"{label}.section_status")
    if status_text == "downloaded":
        status: DownloadSectionStatus = "downloaded"
    elif status_text == "skipped":
        status = "skipped"
    elif status_text == "failed":
        status = "failed"
    else:
        raise ContractError(f"{label}.section_status 非法")
    return DownloadEvidenceRow(
        document_id=_require_nonempty_string(root["document_id"], f"{label}.document_id"),
        accession=_require_nonempty_string(root["accession"], f"{label}.accession"),
        canonical_form=_require_nonempty_string(root["canonical_form"], f"{label}.canonical_form"),
        filing_date=_require_date(root["filing_date"], f"{label}.filing_date"),
        section_status=status,
    )


def _parse_material_evidence(payload: JsonValue, label: str) -> MaterialImportCommandEvidence:
    """严格解析 material import evidence。

    Args:
        payload: 未信任 evidence。
        label: 错误上下文。

    Returns:
        不可变 material evidence。

    Raises:
        ContractError: action/status 条件或 SHA 非法时抛出。
    """

    root = _strict_object(
        payload,
        label,
        {
            "evidence_type",
            "owner_status",
            "material_action",
            "document_id",
            "source_fingerprint",
            "report_date",
            "price_json_sha256",
            "price_material_sha256",
            "repository_primary_sha256",
        },
    )
    _expect_equal(_require_string(root["evidence_type"], f"{label}.evidence_type"), "material_import", label)
    owner_text = _require_string(root["owner_status"], f"{label}.owner_status")
    if owner_text == "ok":
        owner_status: Literal["ok", "skipped"] = "ok"
    elif owner_text == "skipped":
        owner_status = "skipped"
    else:
        raise ContractError(f"{label}.owner_status 非法")
    action_text = _require_string(root["material_action"], f"{label}.material_action")
    if action_text == "create":
        action: MaterialAction = "create"
    elif action_text == "update":
        action = "update"
    else:
        raise ContractError(f"{label}.material_action 非法")
    return MaterialImportCommandEvidence(
        owner_status=owner_status,
        material_action=action,
        document_id=_require_nonempty_string(root["document_id"], f"{label}.document_id"),
        source_fingerprint=_optional_sha256(root["source_fingerprint"], f"{label}.source_fingerprint"),
        report_date=_optional_date(root["report_date"], f"{label}.report_date"),
        price_json_sha256=_require_sha256(root["price_json_sha256"], f"{label}.price_json_sha256"),
        price_material_sha256=_require_sha256(
            root["price_material_sha256"], f"{label}.price_material_sha256"
        ),
        repository_primary_sha256=_require_sha256(
            root["repository_primary_sha256"], f"{label}.repository_primary_sha256"
        ),
    )


def _parse_process_evidence(payload: JsonValue, label: str) -> ProcessCommandEvidence:
    """严格解析 process evidence。

    Args:
        payload: 未信任 evidence。
        label: 错误上下文。

    Returns:
        不可变 process evidence。

    Raises:
        ContractError: summary/TODO/row schema 非法时抛出。
    """

    root = _strict_object(
        payload,
        label,
        {"evidence_type", "owner_status", "filing_summary", "material_summary", "materials_todo", "rows"},
    )
    _expect_equal(_require_string(root["evidence_type"], f"{label}.evidence_type"), "process", label)
    owner_text = _require_string(root["owner_status"], f"{label}.owner_status")
    if owner_text == "ok":
        owner_status: Literal["ok", "cancelled"] = "ok"
    elif owner_text == "cancelled":
        owner_status = "cancelled"
    else:
        raise ContractError(f"{label}.owner_status 非法")
    material_summary = (
        None
        if root["material_summary"] is None
        else _parse_process_summary(root["material_summary"], f"{label}.material_summary")
    )
    return ProcessCommandEvidence(
        owner_status=owner_status,
        filing_summary=_parse_process_summary(root["filing_summary"], f"{label}.filing_summary"),
        material_summary=material_summary,
        materials_todo=_require_bool(root["materials_todo"], f"{label}.materials_todo"),
        rows=tuple(
            _parse_process_row(row, f"{label}.rows[{index}]")
            for index, row in enumerate(_require_list(root["rows"], f"{label}.rows"))
        ),
    )


def _parse_process_summary(payload: JsonValue, label: str) -> ProcessSummary:
    """严格解析 process count summary。

    Args:
        payload: 未信任 summary。
        label: 错误上下文。

    Returns:
        不可变 process summary。

    Raises:
        ContractError: 字段或计数非法时抛出。
    """

    root = _strict_object(payload, label, {"total", "processed", "skipped", "failed"})
    return ProcessSummary(
        total=_require_nonnegative_int(root["total"], f"{label}.total"),
        processed=_require_nonnegative_int(root["processed"], f"{label}.processed"),
        skipped=_require_nonnegative_int(root["skipped"], f"{label}.skipped"),
        failed=_require_nonnegative_int(root["failed"], f"{label}.failed"),
    )


def _parse_process_row(payload: JsonValue, label: str) -> ProcessEvidenceRow:
    """严格解析一个 process section row。

    Args:
        payload: 未信任 row。
        label: 错误上下文。

    Returns:
        不可变 process row。

    Raises:
        ContractError: source/status 闭集非法时抛出。
    """

    root = _strict_object(payload, label, {"document_id", "source_kind", "status"})
    source_text = _require_string(root["source_kind"], f"{label}.source_kind")
    if source_text == "filing":
        source_kind: ProcessSourceKind = "filing"
    elif source_text == "material":
        source_kind = "material"
    else:
        raise ContractError(f"{label}.source_kind 非法")
    status_text = _require_string(root["status"], f"{label}.status")
    if status_text == "processed":
        status: ProcessDocumentStatus = "processed"
    elif status_text == "skipped":
        status = "skipped"
    elif status_text == "failed":
        status = "failed"
    else:
        raise ContractError(f"{label}.status 非法")
    return ProcessEvidenceRow(
        document_id=_require_nonempty_string(root["document_id"], f"{label}.document_id"),
        source_kind=source_kind,
        status=status,
    )


def _parse_package_inputs(payload: JsonValue, label: str) -> PackageInputFingerprints:
    """严格解析 package 输入闭包。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        不可变 package 输入指纹。

    Raises:
        ContractError: config/assets tree 或 base template schema 非法时抛出。
    """

    root = _strict_object(payload, label, {"config_tree", "config_diagnostics", "research_tree", "base_template"})
    return PackageInputFingerprints(
        config_tree=_parse_tree_fingerprint(root["config_tree"], f"{label}.config_tree"),
        config_diagnostics=tuple(
            _parse_file_fingerprint(item, f"{label}.config_diagnostics[{index}]")
            for index, item in enumerate(_require_list(root["config_diagnostics"], f"{label}.config_diagnostics"))
        ),
        research_tree=_parse_tree_fingerprint(root["research_tree"], f"{label}.research_tree"),
        base_template=_parse_file_fingerprint(root["base_template"], f"{label}.base_template"),
    )


def _parse_tree_fingerprint(payload: JsonValue, label: str) -> CanonicalTreeFingerprint:
    """严格解析一棵 canonical tree 指纹。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        不可变 canonical tree 指纹。

    Raises:
        ContractError: 文件列表未排序、重复或 tree SHA 不闭合时抛出。
    """

    root = _strict_object(payload, label, {"locator", "sha256", "files"})
    files = tuple(
        _parse_file_fingerprint(item, f"{label}.files[{index}]")
        for index, item in enumerate(_require_list(root["files"], f"{label}.files"))
    )
    if not files:
        raise ContractError(f"{label}.files 不得为空")
    locators = [item.locator for item in files]
    if locators != sorted(locators) or len(locators) != len(set(locators)):
        raise ContractError(f"{label}.files 必须按 locator 排序且唯一")
    expected = canonical_json_sha256([item.to_json() for item in files])
    actual = _require_sha256(root["sha256"], f"{label}.sha256")
    if expected != actual:
        raise ContractError(f"{label}.sha256 与 files 不一致")
    return CanonicalTreeFingerprint(
        locator=_require_safe_locator(root["locator"], f"{label}.locator"),
        sha256=actual,
        files=files,
    )


def _parse_file_fingerprint(payload: JsonValue, label: str) -> FileFingerprint:
    """严格解析一个文件指纹。

    Args:
        payload: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        不可变文件指纹。

    Raises:
        ContractError: locator 或 SHA-256 非法时抛出。
    """

    root = _strict_object(payload, label, {"locator", "sha256"})
    return FileFingerprint(
        locator=_require_safe_locator(root["locator"], f"{label}.locator"),
        sha256=_require_sha256(root["sha256"], f"{label}.sha256"),
    )


def _fingerprint_tree(root: Path, *, locator: str, include_all_regular: bool) -> CanonicalTreeFingerprint:
    """指纹化一棵不含 symlink/非普通文件的 canonical tree。

    Args:
        root: 已验证的 tree 根目录。
        locator: 写入 receipt 的 package-relative 根定位。
        include_all_regular: 是否纳入全部普通文件；否则只纳入研究资产后缀。

    Returns:
        文件按 locator 排序的 canonical tree 指纹。

    Raises:
        ContractError: tree 为空、含 symlink、非普通文件或重复定位时抛出。
        OSError: stat 或文件读取失败时抛出。
    """

    entries: list[FileFingerprint] = []
    seen: set[str] = set()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ContractError(f"{locator}/{relative} 不得是 symlink")
        mode = path.stat(follow_symlinks=False).st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ContractError(f"{locator}/{relative} 必须是普通文件")
        if not include_all_regular and not relative.endswith(_RESEARCH_SUFFIXES):
            continue
        item_locator = f"{locator}/{relative}"
        if item_locator in seen:
            raise ContractError(f"canonical tree 存在重复 locator: {item_locator}")
        seen.add(item_locator)
        entries.append(_fingerprint_file(path, item_locator))
    if not entries:
        raise ContractError(f"{locator} canonical tree 不得为空")
    files = tuple(entries)
    return CanonicalTreeFingerprint(
        locator=locator,
        sha256=canonical_json_sha256([item.to_json() for item in files]),
        files=files,
    )


def _fingerprint_file(path: Path, locator: str) -> FileFingerprint:
    """读取一个普通非 symlink 文件并生成摘要。

    Args:
        path: package 真源文件路径。
        locator: package-relative POSIX 定位。

    Returns:
        文件字节 SHA-256 引用。

    Raises:
        ContractError: 路径不是普通非 symlink 文件时抛出。
        OSError: 文件读取失败时抛出。
    """

    if path.is_symlink() or not path.is_file():
        raise ContractError(f"{locator} 必须是普通非 symlink 文件")
    return FileFingerprint(locator=locator, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _require_regular_directory(path: Path, label: str) -> Path:
    """验证 resolver 根目录是普通非 symlink 目录。

    Args:
        path: resolver 返回路径。
        label: 错误上下文标签。

    Returns:
        解析后的绝对目录路径。

    Raises:
        ContractError: 路径缺失、不是目录或为 symlink 时抛出。
    """

    if path.is_symlink() or not path.is_dir():
        raise ContractError(f"{label} 必须是普通非 symlink 目录")
    return path.resolve()


def _validate_json_value(value: JsonValue, label: str) -> None:
    """递归验证严格 JSON 值并拒绝 NaN/Infinity。

    Args:
        value: 待验证 JSON 值。
        label: 当前递归定位。

    Returns:
        无。

    Raises:
        ContractError: 键不是字符串、浮点非有限或值不是 JSON 类型时抛出。
    """

    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"{label} 不得包含 NaN/Infinity")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError(f"{label} 对象键必须是字符串")
            _validate_json_value(item, f"{label}.{key}")
        return
    raise ContractError(f"{label} 含非 JSON 值")


def _validate_command_matrix(commands: tuple[tuple[str, ...], ...], label: str) -> None:
    """验证 plan 内 raw argv token matrix 的最小结构。

    Args:
        commands: 按执行顺序排列的 raw argv。
        label: 错误上下文标签。

    Returns:
        无。

    Raises:
        ContractError: 命令为空、重复、token 非法或不是 ``python -m dayu.cli`` 形状时抛出。
    """

    if not commands:
        raise ContractError(f"{label} 不得为空")
    if len(commands) != len(set(commands)):
        raise ContractError(f"{label} 不得包含重复命令")
    for index, command in enumerate(commands):
        command_label = f"{label}[{index}]"
        if len(command) < _MIN_COMMAND_TOKEN_COUNT:
            raise ContractError(f"{command_label} argv 不完整")
        for token_index, token in enumerate(command):
            if not isinstance(token, str) or not token or "\x00" in token:
                raise ContractError(f"{command_label}[{token_index}] 必须是非空无 NUL 字符串")
        _require_canonical_absolute_path(command[0], f"{command_label}[0]")
        if command[1:3] != ("-m", "dayu.cli"):
            raise ContractError(f"{command_label} 必须使用 python -m dayu.cli")


def _validate_safe_command_matrix(commands: tuple[tuple[str, ...], ...], label: str) -> None:
    """验证 receipt 只包含受控 placeholder 与非绝对 token。

    Args:
        commands: 已脱敏的 argv token matrix。
        label: 错误上下文标签。

    Returns:
        无。

    Raises:
        ContractError: token 为空、含 raw 绝对路径或未知 placeholder 时抛出。
    """

    for command_index, command in enumerate(commands):
        if not command:
            raise ContractError(f"{label}[{command_index}] 不得为空")
        for token_index, token in enumerate(command):
            token_label = f"{label}[{command_index}][{token_index}]"
            if not isinstance(token, str) or not token or "\x00" in token:
                raise ContractError(f"{token_label} 必须是非空无 NUL 字符串")
            if _is_safe_placeholder_token(token):
                continue
            if "<" in token or ">" in token:
                raise ContractError(f"{token_label} 含未知 placeholder")
            if _looks_absolute_path(token):
                raise ContractError(f"{token_label} 不得包含 raw 绝对路径")


def _is_safe_placeholder_token(token: str) -> bool:
    """判断 token 是否是三个受控 placeholder 之一或其安全子路径。

    Args:
        token: 待检查 safe argv token。

    Returns:
        token 可安全持久化时返回 ``True``。

    Raises:
        本函数不显式抛出异常。
    """

    if token == SAFE_ARGV_PLACEHOLDERS[0]:
        return True
    for placeholder in SAFE_ARGV_PLACEHOLDERS[1:]:
        if token == placeholder:
            return True
        prefix = f"{placeholder}/"
        if token.startswith(prefix):
            suffix = PurePosixPath(token.removeprefix(prefix))
            return bool(suffix.parts) and ".." not in suffix.parts and "\\" not in token
    return False


def _looks_absolute_path(token: str) -> bool:
    """检测 POSIX、Windows 或 home 展开形状的 raw 绝对路径。

    Args:
        token: 待检查 argv token。

    Returns:
        token 看似绝对路径时返回 ``True``。

    Raises:
        本函数不显式抛出异常。
    """

    candidate = token.partition("=")[2] if "=" in token else token
    return (
        PurePosixPath(candidate).is_absolute()
        or candidate.startswith("~")
        or re.match(r"^[A-Za-z]:[\\/]", candidate) is not None
    )


def _validate_command_record_status(record: CommandRecord) -> None:
    """验证单条 command record 的 lifecycle 状态。

    Args:
        record: 待验证执行记录。

    Returns:
        无。

    Raises:
        ContractError: 状态、退出码、termination 或 stream 事实不闭合时抛出。
    """

    if record.status == "passed":
        if (
            record.exit_code != 0
            or record.stop_reason is not None
            or record.termination_action is not None
            or record.partial_by_timeout
        ):
            raise ContractError("passed command record 的退出事实不闭合")
    elif record.status == "timeout":
        if not record.partial_by_timeout or record.termination_action is None or record.stop_reason is None:
            raise ContractError("timeout command record 的 termination 事实不闭合")
        if record.termination_action == "not_started" and record.exit_code is not None:
            raise ContractError("not_started timeout 不得有 exit_code")
    else:
        if record.stop_reason is None or record.partial_by_timeout or record.termination_action is not None:
            raise ContractError("failed/signal command record 的停止事实不闭合")
        if record.status == "signal" and (record.exit_code is None or record.exit_code >= 0):
            raise ContractError("signal command record 必须记录负退出码")
        # Owner formatter/semantic ingress 可在子进程 exit 0 后 fail closed。
        # 此时 ``status=failed`` 与非空静态 stop_reason 是真实执行事实，
        # 不得把 exit 0 误标为 passed。
    _validate_command_record_streams(record)


def _validate_command_record_streams(record: CommandRecord) -> None:
    """按已启动/未启动事实闭合 command record 的 stream 摘要。

    Args:
        record: 已完成通用 lifecycle 校验的 command record。

    Returns:
        无。

    Raises:
        ContractError: stream SHA、summary 或 evidence 与启动事实不闭合时抛出。
    """

    start_failure = (
        record.status == "failed"
        and record.exit_code is None
        and record.stop_reason == "process_start_failed"
    )
    not_started_timeout = record.status == "timeout" and record.termination_action == "not_started"
    streams_absent = record.stdout_sha256 is None and record.stderr_sha256 is None
    if start_failure or not_started_timeout:
        if not streams_absent:
            raise ContractError("未启动 command 的 stdout/stderr SHA 必须同时为 null")
    elif record.stdout_sha256 is None or record.stderr_sha256 is None:
        raise ContractError("已启动 command 的 stdout/stderr SHA 必须均为 SHA-256")
    if streams_absent and (
        record.stdout_summary is not None
        or record.stderr_summary is not None
        or record.evidence is not None
    ):
        raise ContractError("未启动 command 不得包含 stream/evidence")


def _validate_phase_record_prefix(receipt: PhaseReceipt) -> None:
    """验证 phase 聚合状态与 command records 前缀闭合。

    Args:
        receipt: 待验证 v3 receipt。

    Returns:
        无。

    Raises:
        ContractError: phase 名称、record 数量或聚合状态不闭合时抛出。
    """

    allowed = ("prepare", *(name for name, _count in PLANNED_PHASE_COMMAND_COUNTS), TERMINAL_ACTION)
    if receipt.phase_name not in allowed:
        raise ContractError(f"phase_receipt.phase_name 非法: {receipt.phase_name}")
    if receipt.phase_name == "prepare":
        if receipt.command_records or receipt.status != "passed":
            raise ContractError("prepare receipt 必须是 passed 且精确 0 record")
        return
    expected_count = (
        1
        if receipt.phase_name == TERMINAL_ACTION
        else dict(PLANNED_PHASE_COMMAND_COUNTS)[receipt.phase_name]
    )
    if not receipt.command_records or len(receipt.command_records) > expected_count:
        raise ContractError("非 prepare receipt 必须是非空计划前缀")
    if receipt.status == "passed":
        if len(receipt.command_records) != expected_count or any(
            record.status != "passed" for record in receipt.command_records
        ):
            raise ContractError("passed phase receipt 必须含完整 passed records")
        return
    if receipt.command_records[-1].status != receipt.status:
        raise ContractError("phase 聚合状态必须等于最后 record 状态")
    if any(record.status != "passed" for record in receipt.command_records[:-1]):
        raise ContractError("失败 phase 只允许 passed records 后接一个停止 record")


def _require_canonical_absolute_path(value: JsonValue, label: str) -> str:
    """收窄 canonical absolute POSIX path 字符串。

    Args:
        value: 未信任 JSON 值。
        label: 错误上下文标签。

    Returns:
        与 ``Path.resolve(strict=False).as_posix()`` 一致的绝对路径。

    Raises:
        ContractError: 值不是 canonical absolute path 时抛出。
    """

    text = _require_nonempty_string(value, label)
    if "\\" in text or not PurePosixPath(text).is_absolute():
        raise ContractError(f"{label} 必须是 absolute POSIX path")
    canonical = Path(text).resolve(strict=False).as_posix()
    if canonical != text:
        raise ContractError(f"{label} 必须是 canonical absolute path")
    return text


def _strict_object(value: JsonValue, label: str, expected_keys: set[str]) -> JsonObject:
    """把 JSON 值收窄为字段精确闭合的对象。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。
        expected_keys: 精确允许字段集合。

    Returns:
        字段闭合的 JSON 对象。

    Raises:
        ContractError: 值非对象或存在缺失/未知字段时抛出。
    """

    result = _require_mapping(value, label)
    actual = set(result)
    missing = expected_keys - actual
    unknown = actual - expected_keys
    if missing or unknown:
        raise ContractError(f"{label} schema 不闭合: missing={sorted(missing)}, unknown={sorted(unknown)}")
    return result


def _require_mapping(value: JsonValue, label: str) -> JsonObject:
    """把严格 JSON 值收窄为对象。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        JSON 对象。

    Raises:
        ContractError: 值不是对象时抛出。
    """

    if not isinstance(value, dict):
        raise ContractError(f"{label} 必须是对象")
    return value


def _require_list(value: JsonValue, label: str) -> list[JsonValue]:
    """把严格 JSON 值收窄为数组。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        JSON 数组。

    Raises:
        ContractError: 值不是数组时抛出。
    """

    if not isinstance(value, list):
        raise ContractError(f"{label} 必须是数组")
    return value


def _required(mapping: JsonObject, key: str, label: str) -> JsonValue:
    """读取 owner ingress 所需字段并拒绝缺失。

    Args:
        mapping: 已收窄 owner JSON 对象。
        key: 必填字段名。
        label: 错误上下文标签。

    Returns:
        字段 JSON 值。

    Raises:
        ContractError: 字段缺失时抛出。
    """

    if key not in mapping:
        raise ContractError(f"{label} 缺少字段 {key}")
    return mapping[key]


def _require_string(value: JsonValue, label: str) -> str:
    """收窄字符串。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        原始字符串。

    Raises:
        ContractError: 值不是字符串时抛出。
    """

    if not isinstance(value, str):
        raise ContractError(f"{label} 必须是字符串")
    return value


def _require_nonempty_string(value: JsonValue, label: str) -> str:
    """收窄非空字符串。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        去除首尾空白后的非空字符串。

    Raises:
        ContractError: 值不是字符串或去空白后为空时抛出。
    """

    result = _require_string(value, label).strip()
    if not result:
        raise ContractError(f"{label} 不得为空")
    return result


def _optional_nonempty_string(value: JsonValue, label: str) -> str | None:
    """收窄可选非空字符串。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        非空字符串或 ``None``。

    Raises:
        ContractError: 非空值不是合法字符串时抛出。
    """

    if value is None:
        return None
    return _require_nonempty_string(value, label)


def _require_bool(value: JsonValue, label: str) -> bool:
    """收窄布尔值。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        严格布尔值。

    Raises:
        ContractError: 值不是 bool 时抛出。
    """

    if not isinstance(value, bool):
        raise ContractError(f"{label} 必须是布尔值")
    return value


def _require_int(value: JsonValue, label: str) -> int:
    """收窄整数并拒绝 bool-as-int。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        严格整数。

    Raises:
        ContractError: 值不是整数或是 bool 时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{label} 必须是整数且不得是 bool")
    return value


def _optional_int(value: JsonValue, label: str) -> int | None:
    """收窄可选整数并拒绝 bool-as-int。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        严格整数或 ``None``。

    Raises:
        ContractError: 非空值不是整数或是 bool 时抛出。
    """

    if value is None:
        return None
    return _require_int(value, label)


def _require_nonnegative_int(value: JsonValue, label: str) -> int:
    """收窄非负整数。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        非负整数。

    Raises:
        ContractError: 值不是严格整数或小于零时抛出。
    """

    result = _require_int(value, label)
    if result < 0:
        raise ContractError(f"{label} 必须非负")
    return result


def _optional_nonnegative_int(value: JsonValue, label: str) -> int | None:
    """收窄可选非负整数。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        非负整数或 ``None``。

    Raises:
        ContractError: 非空值不是非负整数时抛出。
    """

    if value is None:
        return None
    return _require_nonnegative_int(value, label)


def _require_positive_int(value: JsonValue, label: str) -> int:
    """收窄正整数。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        大于零的整数。

    Raises:
        ContractError: 值不是严格正整数时抛出。
    """

    result = _require_int(value, label)
    if result <= 0:
        raise ContractError(f"{label} 必须大于零")
    return result


def _require_nonnegative_float(value: JsonValue, label: str) -> float:
    """收窄非负有限数并拒绝 bool-as-int。

    Args:
        value: 待收窄 JSON 数值。
        label: 错误上下文标签。

    Returns:
        非负有限浮点数。

    Raises:
        ContractError: 值非数值、为 bool、非有限或小于零时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{label} 必须是有限数且不得是 bool")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ContractError(f"{label} 必须是非负有限数")
    return result


def _require_nonnegative_decimal(value: JsonValue, label: str) -> Decimal:
    """收窄非负有限 Decimal。

    Args:
        value: 待收窄 JSON 数值或十进制字符串。
        label: 错误上下文标签。

    Returns:
        非负有限 Decimal。

    Raises:
        ContractError: 值不是有限十进制数或小于零时抛出。
    """

    result = _require_decimal(value, label)
    if result < 0:
        raise ContractError(f"{label} 必须非负")
    return result


def _require_positive_decimal(value: JsonValue, label: str) -> Decimal:
    """收窄正有限 Decimal。

    Args:
        value: 待收窄 JSON 数值或十进制字符串。
        label: 错误上下文标签。

    Returns:
        正有限 Decimal。

    Raises:
        ContractError: 值不是有限十进制数或不大于零时抛出。
    """

    result = _require_decimal(value, label)
    if result <= 0:
        raise ContractError(f"{label} 必须大于零")
    return result


def _require_decimal(value: JsonValue, label: str) -> Decimal:
    """收窄有限 Decimal 并拒绝 bool。

    Args:
        value: 待收窄 JSON 标量。
        label: 错误上下文标签。

    Returns:
        有限 Decimal。

    Raises:
        ContractError: 值为 bool/null/容器、格式非法或非有限时抛出。
    """

    if isinstance(value, bool) or value is None or isinstance(value, (list, dict)):
        raise ContractError(f"{label} 必须是十进制数")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ContractError(f"{label} 不是合法十进制数") from exc
    if not result.is_finite():
        raise ContractError(f"{label} 必须有限")
    return result


def _require_date(value: JsonValue, label: str) -> date:
    """收窄 ISO 日期。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        ISO ``YYYY-MM-DD`` 日期。

    Raises:
        ContractError: 值不是合法日期字符串时抛出。
    """

    text = _require_nonempty_string(value, label)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ContractError(f"{label} 必须是 YYYY-MM-DD") from exc


def _require_datetime(value: JsonValue, label: str) -> datetime:
    """收窄带时区 RFC3339 datetime。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        规范化到 UTC 的 datetime。

    Raises:
        ContractError: 值不是带时区 RFC3339 时抛出。
    """

    text = _require_nonempty_string(value, label)
    try:
        result = datetime.fromisoformat(text.replace(_AS_OF_SUFFIX, "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{label} 必须是带时区 RFC3339") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ContractError(f"{label} 必须带时区")
    return result.astimezone(UTC)


def _optional_datetime(value: JsonValue, label: str) -> datetime | None:
    """收窄可选带时区 datetime。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        UTC datetime 或 ``None``。

    Raises:
        ContractError: 非空值不是带时区 RFC3339 时抛出。
    """

    if value is None:
        return None
    return _require_datetime(value, label)


def _optional_date(value: JsonValue, label: str) -> date | None:
    """收窄可选 ISO 日期。

    Args:
        value: 未信任 JSON 值。
        label: 错误上下文。

    Returns:
        日期或 ``None``。

    Raises:
        ContractError: 非空值不是合法日期时抛出。
    """

    if value is None:
        return None
    return _require_date(value, label)


def _string_tuple(value: JsonValue, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    """收窄字符串数组。

    Args:
        value: 待收窄 JSON 数组。
        label: 错误上下文标签。
        allow_empty: 是否允许空数组。

    Returns:
        非空字符串元组。

    Raises:
        ContractError: 值非数组、元素为空或禁止的空数组时抛出。
    """

    result = tuple(
        _require_nonempty_string(item, f"{label}[{index}]") for index, item in enumerate(_require_list(value, label))
    )
    if not allow_empty and not result:
        raise ContractError(f"{label} 不得为空")
    return result


def _unique_string_tuple(value: JsonValue, label: str) -> tuple[str, ...]:
    """收窄非空且无重复的字符串数组。

    Args:
        value: 待收窄 JSON 数组。
        label: 错误上下文标签。

    Returns:
        唯一非空字符串元组。

    Raises:
        ContractError: 数组非法、为空或含重复值时抛出。
    """

    result = _string_tuple(value, label)
    if len(result) != len(set(result)):
        raise ContractError(f"{label} 不得包含重复值")
    return result


def _fixed_research_artifacts(value: JsonValue, label: str) -> tuple[str, ...]:
    """收窄并规范化固定 AAPL/technology 的 13 文件集合。

    Args:
        value: 待收窄 JSON 数组。
        label: 错误上下文标签。

    Returns:
        固定顺序的 13 个研究 artifact 文件名。

    Raises:
        ContractError: 数组不是精确固定 13 文件集合时抛出。
    """

    result = _unique_string_tuple(value, label)
    if frozenset(result) != frozenset(REQUIRED_RESEARCH_ARTIFACTS):
        raise ContractError(f"{label} 必须精确等于固定 AAPL/technology 13 文件集合")
    return REQUIRED_RESEARCH_ARTIFACTS


def _require_sha256(value: JsonValue, label: str) -> str:
    """收窄小写 SHA-256 字符串。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        64 位小写十六进制摘要。

    Raises:
        ContractError: 值不是合法 SHA-256 时抛出。
    """

    result = _require_nonempty_string(value, label)
    if SHA256_PATTERN.fullmatch(result) is None:
        raise ContractError(f"{label} 必须是小写 SHA-256")
    return result


def _optional_sha256(value: JsonValue, label: str) -> str | None:
    """收窄可选 SHA-256。

    Args:
        value: 未信任 JSON 值。
        label: 错误上下文。

    Returns:
        小写 SHA-256 或 ``None``。

    Raises:
        ContractError: 非空值不是 SHA-256 时抛出。
    """

    if value is None:
        return None
    return _require_sha256(value, label)


def _require_git_object_id(value: JsonValue, label: str) -> str:
    """收窄 Git SHA-1/SHA-256 object id。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        原 40 或 64 位小写十六进制 object id。

    Raises:
        ContractError: 值不是规范 Git object id 时抛出。
    """

    result = _require_nonempty_string(value, label)
    if GIT_OBJECT_ID_PATTERN.fullmatch(result) is None:
        raise ContractError(f"{label} 必须是规范小写 Git object id")
    return result


def _require_safe_locator(value: JsonValue, label: str) -> str:
    """收窄无绝对路径和 ``..`` 的 POSIX locator。

    Args:
        value: 待收窄 JSON 值。
        label: 错误上下文标签。

    Returns:
        规范 package-relative POSIX locator。

    Raises:
        ContractError: locator 为空、绝对、含 ``..``/反斜线或 home 展开时抛出。
    """

    result = _require_nonempty_string(value, label)
    pure = PurePosixPath(result)
    if pure.is_absolute() or ".." in pure.parts or result.startswith("~") or "\\" in result:
        raise ContractError(f"{label} 必须是安全 package-relative POSIX locator")
    return pure.as_posix()


def _expect_equal(actual: JsonScalar, expected: JsonScalar, label: str) -> None:
    """验证固定 schema 常量。

    Args:
        actual: 实际 JSON 标量。
        expected: 期望 JSON 标量。
        label: 错误上下文标签。

    Returns:
        无。

    Raises:
        ContractError: 实际值与期望不等时抛出。
    """

    if actual != expected:
        raise ContractError(f"{label} 必须是 {expected!r}")


__all__ = [
    "GIT_OBJECT_ID_PATTERN",
    "PLANNED_PHASE_COMMAND_COUNTS",
    "REQUIRED_ENVIRONMENT_NAMES",
    "REQUIRED_RESEARCH_ARTIFACTS",
    "SAFE_ARGV_PLACEHOLDERS",
    "SHA256_PATTERN",
    "SUBPROCESS_ENV_POLICY",
    "TERMINAL_ACTION",
    "AcceptanceContract",
    "AcceptancePlan",
    "AcceptanceReceipt",
    "AcceptanceReceiptPayload",
    "AcceptanceTarget",
    "BudgetLimits",
    "CanonicalTreeFingerprint",
    "CommandEvidence",
    "CommandRecord",
    "CommandRecordPayload",
    "ContractError",
    "DownloadCommandEvidence",
    "DownloadEvidenceRow",
    "DownloadSummary",
    "EnvironmentPresence",
    "EnvironmentPresencePayload",
    "FileFingerprint",
    "FindingCounts",
    "FindingSeverity",
    "FingerprintDriftError",
    "InventoryPayload",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "ManualFinding",
    "MaterialImportCommandEvidence",
    "ModelRoles",
    "OwnerBudgetSummary",
    "OwnerRunSummary",
    "OwnerWriteManifest",
    "PackageInputFingerprints",
    "PhaseReceipt",
    "PhaseReceiptPayload",
    "PhaseSpec",
    "PhaseSpecPayload",
    "PhaseStatus",
    "PlanPayload",
    "PriceSnapshot",
    "ProcessCommandEvidence",
    "ProcessEvidenceRow",
    "ProcessSummary",
    "ProcessedState",
    "QualityReview",
    "ReceiptArtifact",
    "ReceiptFinding",
    "RubricDimension",
    "RubricItem",
    "RubricPayload",
    "ScoreContract",
    "SourceDocument",
    "SourceInventory",
    "SourceWindow",
    "TerminalAction",
    "ValuationReferencePrice",
    "Verdict",
    "assert_package_input_fingerprints",
    "build_package_input_fingerprints",
    "canonical_json_bytes",
    "canonical_json_sha256",
    "format_utc",
    "load_json_file",
    "parse_acceptance_contract",
    "parse_acceptance_plan",
    "parse_acceptance_receipt",
    "parse_json_bytes",
    "parse_owner_run_summary",
    "parse_owner_write_manifest",
    "parse_phase_receipt",
    "parse_price_snapshot",
    "parse_quality_review",
    "parse_source_inventory",
]
