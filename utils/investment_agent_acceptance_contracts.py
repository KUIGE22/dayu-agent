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

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_AS_OF_SUFFIX = "Z"
_PLAN_SCHEMA_VERSION = 1
_PHASE_SCHEMA_VERSION = 1
_RECEIPT_SCHEMA_VERSION = 1
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
    package_inputs: JsonObject
    price_snapshot_sha256: str
    price_material_sha256: str
    budget: JsonObject
    max_wall_seconds: int
    termination_grace_seconds: int
    required_research_artifacts: list[JsonValue]


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
    status: str
    started_at: str
    ended_at: str
    duration_seconds: float
    remaining_wall_seconds: float
    argv: list[JsonValue]
    exit_code: int | None
    stop_reason: str | None
    termination_action: str | None
    partial_by_timeout: bool


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
    package_inputs: PackageInputFingerprints
    price_snapshot_sha256: str
    price_material_sha256: str
    budget: BudgetLimits
    max_wall_seconds: int
    termination_grace_seconds: int
    required_research_artifacts: tuple[str, ...]

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
            "package_inputs": self.package_inputs.to_json(),
            "price_snapshot_sha256": self.price_snapshot_sha256,
            "price_material_sha256": self.price_material_sha256,
            "budget": self.budget.to_json(),
            "max_wall_seconds": self.max_wall_seconds,
            "termination_grace_seconds": self.termination_grace_seconds,
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
    status: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    remaining_wall_seconds: float
    argv: tuple[tuple[str, ...], ...]
    exit_code: int | None
    stop_reason: str | None
    termination_action: str | None
    partial_by_timeout: bool

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
            "argv": [list(command) for command in self.argv],
            "exit_code": self.exit_code,
            "stop_reason": self.stop_reason,
            "termination_action": self.termination_action,
            "partial_by_timeout": self.partial_by_timeout,
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
            "package_inputs",
            "price_snapshot_sha256",
            "price_material_sha256",
            "budget",
            "max_wall_seconds",
            "termination_grace_seconds",
            "required_research_artifacts",
        },
    )
    _expect_equal(
        _require_int(root["schema_version"], "acceptance_plan.schema_version"), 1, "acceptance_plan.schema_version"
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
    return AcceptancePlan(
        ticker=_require_nonempty_string(root["ticker"], "acceptance_plan.ticker"),
        company=_require_nonempty_string(root["company"], "acceptance_plan.company"),
        research_template=_require_nonempty_string(root["research_template"], "acceptance_plan.research_template"),
        as_of=_require_datetime(root["as_of"], "acceptance_plan.as_of"),
        git_sha=_require_sha256(root["git_sha"], "acceptance_plan.git_sha"),
        dirty=_require_bool(root["dirty"], "acceptance_plan.dirty"),
        python_version=_require_nonempty_string(root["python_version"], "acceptance_plan.python_version"),
        platform=_require_nonempty_string(root["platform"], "acceptance_plan.platform"),
        timezone=_require_nonempty_string(root["timezone"], "acceptance_plan.timezone"),
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
            "argv",
            "exit_code",
            "stop_reason",
            "termination_action",
            "partial_by_timeout",
        },
    )
    _expect_equal(
        _require_int(root["schema_version"], "phase_receipt.schema_version"), 1, "phase_receipt.schema_version"
    )
    _expect_equal(
        _require_string(root["receipt_type"], "phase_receipt.receipt_type"),
        "investment_agent_acceptance_phase",
        "phase_receipt.receipt_type",
    )
    argv_rows = _require_list(root["argv"], "phase_receipt.argv")
    commands = tuple(_string_tuple(item, f"phase_receipt.argv[{index}]") for index, item in enumerate(argv_rows))
    return PhaseReceipt(
        plan_fingerprint=_require_sha256(root["plan_fingerprint"], "phase_receipt.plan_fingerprint"),
        phase_name=_require_nonempty_string(root["phase_name"], "phase_receipt.phase_name"),
        status=_require_nonempty_string(root["status"], "phase_receipt.status"),
        started_at=_require_datetime(root["started_at"], "phase_receipt.started_at"),
        ended_at=_require_datetime(root["ended_at"], "phase_receipt.ended_at"),
        duration_seconds=_require_nonnegative_float(root["duration_seconds"], "phase_receipt.duration_seconds"),
        remaining_wall_seconds=_require_nonnegative_float(
            root["remaining_wall_seconds"], "phase_receipt.remaining_wall_seconds"
        ),
        argv=commands,
        exit_code=_optional_int(root["exit_code"], "phase_receipt.exit_code"),
        stop_reason=_optional_nonempty_string(root["stop_reason"], "phase_receipt.stop_reason"),
        termination_action=_optional_nonempty_string(root["termination_action"], "phase_receipt.termination_action"),
        partial_by_timeout=_require_bool(root["partial_by_timeout"], "phase_receipt.partial_by_timeout"),
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
    "REQUIRED_RESEARCH_ARTIFACTS",
    "SHA256_PATTERN",
    "AcceptanceContract",
    "AcceptancePlan",
    "AcceptanceReceipt",
    "AcceptanceReceiptPayload",
    "AcceptanceTarget",
    "BudgetLimits",
    "CanonicalTreeFingerprint",
    "ContractError",
    "FileFingerprint",
    "FindingCounts",
    "FindingSeverity",
    "FingerprintDriftError",
    "InventoryPayload",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "ManualFinding",
    "ModelRoles",
    "OwnerBudgetSummary",
    "OwnerRunSummary",
    "OwnerWriteManifest",
    "PackageInputFingerprints",
    "PhaseReceipt",
    "PhaseReceiptPayload",
    "PlanPayload",
    "PriceSnapshot",
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
