"""投资 Agent AAPL 验收的确定性只读 evaluator。

本模块组合严格 contract、仓储协议清单、报告、生产 validator 结果与人工 rubric，
输出稳定的三态 receipt。它不执行网络、模型或子进程，也不修改生产研究产物。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal, TypeAlias

from dayu.cli.commands._research_template_bundle import inspect_research_template_bundle
from dayu.cli.commands._research_template_core import validate_monitoring_source_map_payload
from dayu.cli.commands._research_template_monitoring import inspect_monitoring_execution_plan
from dayu.cli.commands.research_workbook import (
    inspect_research_workbook_report,
    validate_research_workbook_payload,
)
from dayu.fins.domain.enums import SourceKind
from utils.investment_agent_acceptance_contracts import (
    REQUIRED_RESEARCH_ARTIFACTS,
    AcceptanceContract,
    BudgetLimits,
    ContractError,
    FindingSeverity,
    JsonObject,
    JsonValue,
    OwnerRunSummary,
    OwnerWriteManifest,
    PhaseReceipt,
    PriceSnapshot,
    ProcessedState,
    QualityReview,
    SourceDocument,
    SourceInventory,
    SourceWindow,
    Verdict,
    canonical_json_bytes,
    canonical_json_sha256,
    format_utc,
    load_json_file,
    parse_acceptance_contract,
    parse_json_bytes,
    parse_owner_run_summary,
    parse_owner_write_manifest,
    parse_price_snapshot,
    parse_quality_review,
    parse_source_inventory,
)

if TYPE_CHECKING:
    from dayu.fins.storage import (
        DocumentBlobRepositoryProtocol,
        ProcessedDocumentRepositoryProtocol,
        SourceDocumentRepositoryProtocol,
    )

GateStatus: TypeAlias = Literal["passed", "pending", "failed"]

_FIXTURE_FILES = {
    "contract": "contract-v1.json",
    "inventory": "source-inventory-v1.json",
    "manifest": "write-manifest-v1.json",
    "price": "price-snapshot-v1.json",
    "quality": "quality-review-v1.json",
    "report": "report-v1.md",
    "summary": "run-summary-v1.json",
}
_TOPIC_HEADINGS = {
    "thesis": ("投资主线（thesis）", "投资主线", "thesis"),
    "bear_case": ("bear case 与反证", "bear case", "反证"),
    "valuation": ("估值（valuation）", "估值", "valuation"),
    "catalyst": ("催化剂（catalyst）", "催化剂", "catalyst"),
    "risk": ("风险（risk）", "风险", "risk"),
}
_SOURCE_LIST_HEADING = "来源清单"
_EVIDENCE_HEADING = "证据与出处"
_REFERENCE_PREFIX = "valuation_reference_price:"
_EVIDENCE_PART_COUNT = 4
_MIN_EVIDENCE_LOCATOR_LENGTH = 4
_TEMPLATE_LOCATORS = {"见财报", "见报告", "见官网", "官网", "财报", "待补充", "n/a", "na"}
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:authorization|proxy-authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(?:cookie|set-cookie)\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*[A-Za-z0-9_-]{12,}"),
)
_HOME_PATH_PATTERNS = (
    re.compile(r"/(?:Users|home)/[^/\s]+(?:/[^\s]*)?"),
    re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+(?:\\[^\s]*)?"),
)
_SENSITIVE_KEYS = {"authorization", "proxy-authorization", "cookie", "set-cookie"}
_EXPECTED_TICKER = "AAPL"
_EXPECTED_COMPANIES = {"Apple", "Apple Inc."}
_EXPECTED_TEMPLATE = "technology"
_EXPECTED_PRIMARY_MODEL = "deepseek-v4-pro"
_EXPECTED_AUDIT_MODEL = "mimo-v2.5-pro-thinking"
_ACCEPTANCE_ARTIFACT_PREFIX = "research/assets/research_templates"


@dataclass(frozen=True)
class Finding:
    """一条确定性验收 finding。

    Args:
        code: 稳定错误码。
        gate: 对应 hard gate。
        severity: 严重级别。
        message: 不含秘密与绝对 home 路径的说明。
        locator: 可选相对输入定位。

    Returns:
        不可变 finding。

    Raises:
        本类不显式抛出异常。
    """

    code: str
    gate: str
    severity: FindingSeverity
    message: str
    locator: str | None = None

    def to_json(self) -> JsonObject:
        """转换为稳定 JSON 对象。

        Args:
            无。

        Returns:
            finding JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "code": self.code,
            "gate": self.gate,
            "severity": self.severity,
            "message": self.message,
            "locator": self.locator,
        }


@dataclass(frozen=True)
class ArtifactReference:
    """生产研究产物的相对定位与字节摘要。

    Args:
        locator: package-relative artifact 定位。
        sha256: artifact 字节 SHA-256。

    Returns:
        不含生产内容的不可变 artifact 引用。

    Raises:
        本类不显式抛出异常。
    """

    locator: str
    sha256: str

    def to_json(self) -> JsonObject:
        """转换为不含生产原文的 JSON 引用。

        Args:
            无。

        Returns:
            package-relative locator 与 SHA-256。

        Raises:
            本方法不显式抛出异常。
        """

        return {"locator": self.locator, "sha256": self.sha256}


@dataclass(frozen=True)
class ResearchArtifactInspection:
    """13 个研究产物及 owner validator 的只读检查结果。

    Args:
        声明字段: 引用、inventory/workbook/bundle/source-map/monitoring 状态与 residual facts。

    Returns:
        不包含生产原文的不可变检查结果。

    Raises:
        本类不显式抛出异常。
    """

    references: tuple[ArtifactReference, ...]
    inventory_ok: bool
    workbook_valid: bool
    progress_current: bool
    progress_untampered: bool
    bundle_valid: bool
    source_map_valid: bool
    status_snapshots_valid: bool
    monitoring_valid: bool
    monitoring_execution_mode: str
    automated_execution_allowed: bool
    workbook_completion_status: str
    workbook_open_item_count: int
    monitoring_readiness: str
    monitoring_blocked_task_count: int
    monitoring_unbound_sources: tuple[str, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeEvidence:
    """deterministic 或 live verify 的预算与总耗时证据。

    Args:
        approved_budget: 显式批准预算。
        max_wall_seconds: 整次运行 wall-clock 上限。
        actual_wall_seconds: 已消耗 wall-clock。
        phase_receipts: 有序严格阶段 receipts。

    Returns:
        不可变运行治理证据。

    Raises:
        本类不显式抛出异常。
    """

    approved_budget: BudgetLimits
    max_wall_seconds: int
    actual_wall_seconds: float
    phase_receipts: tuple[PhaseReceipt, ...]


@dataclass(frozen=True)
class AcceptanceInputs:
    """evaluator 的全部严格输入。

    Args:
        声明字段: contract、源/价格、rubric、owner 事实、报告、产物与 runtime。

    Returns:
        owner 宽载荷已在边界收窄的不可变 evaluator 输入。

    Raises:
        本类不显式抛出异常。
    """

    contract: AcceptanceContract
    inventory: SourceInventory
    price_snapshot: PriceSnapshot
    quality_review: QualityReview
    write_manifest: OwnerWriteManifest
    run_summary: OwnerRunSummary
    report_text: str
    research_artifacts: ResearchArtifactInspection
    runtime: RuntimeEvidence
    acceptance_owned_outputs: tuple[JsonValue, ...]


@dataclass(frozen=True)
class FixtureInputRequest:
    """固定 fixture 与临时 artifact 的严格加载请求。

    Args:
        fixture_root: 只读固定 fixture 目录。
        artifact_root: 临时物化的研究 artifact 目录。
        approved_budget: 显式批准预算。
        max_wall_seconds: 整次运行 wall-clock 上限。
        actual_wall_seconds: 已消耗 wall-clock。
        phase_receipts: 可选严格阶段 receipts。
        acceptance_owned_outputs: 仅允许 sanitizer 扫描的验收自有输出。
        expected_artifact_sha256: 可选 artifact locator/已绑定摘要。

    Returns:
        不可变 fixture 加载请求。

    Raises:
        本类不显式抛出异常。
    """

    fixture_root: Path
    artifact_root: Path
    approved_budget: BudgetLimits
    max_wall_seconds: int
    actual_wall_seconds: float
    phase_receipts: tuple[PhaseReceipt, ...] = ()
    acceptance_owned_outputs: tuple[JsonValue, ...] = ()
    expected_artifact_sha256: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RepositoryInventoryRequest:
    """通过三个仓储 Protocol 构建源清单的严格请求。

    Args:
        fixture_id: 清单身份标签。
        ticker: 规范 ticker。
        company: 公司规范名。
        as_of: 本次固定 UTC as-of。
        live_freshness_claimed: 是否由本次 discovery 支撑 live freshness。
        source_windows: 三组显式 SEC 窗口。
        latest_discovery: form 到最新 accession 的本次 discovery 结果。
        source_repository: 源文档窄协议。
        processed_repository: processed 文档窄协议。
        blob_repository: 文件字节窄协议。

    Returns:
        不可变仓储清单请求。

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
    source_repository: SourceDocumentRepositoryProtocol
    processed_repository: ProcessedDocumentRepositoryProtocol
    blob_repository: DocumentBlobRepositoryProtocol


@dataclass(frozen=True)
class EvaluationResult:
    """确定性 evaluator 的三态结果与 canonical receipt。

    Args:
        声明字段: verdict、评分、hard gates、findings、artifact 引用、residuals 与固定时钟。

    Returns:
        可稳定序列化的不可变 evaluator 结果。

    Raises:
        本类不显式抛出异常。
    """

    verdict: Verdict
    total_score: int | None
    dimension_scores: tuple[tuple[str, int | None], ...]
    hard_gates: tuple[tuple[str, GateStatus], ...]
    findings: tuple[Finding, ...]
    artifacts: tuple[ArtifactReference, ...]
    residuals: tuple[str, ...]
    evaluated_at: datetime

    def to_json(self) -> JsonObject:
        """转换为稳定、脱敏的 acceptance receipt。

        Args:
            无。

        Returns:
            不含生产 artifact 原文或绝对路径的 receipt JSON。

        Raises:
            本方法不显式抛出异常。
        """

        return {
            "schema_version": 1,
            "receipt_type": "investment_agent_acceptance",
            "evaluated_at": format_utc(self.evaluated_at),
            "verdict": self.verdict,
            "total_score": self.total_score,
            "dimension_scores": dict(self.dimension_scores),
            "hard_gates": dict(self.hard_gates),
            "findings": [finding.to_json() for finding in self.findings],
            "artifacts": [artifact.to_json() for artifact in self.artifacts],
            "residuals": list(self.residuals),
        }

    def canonical_bytes(self) -> bytes:
        """生成字节稳定的 canonical receipt。

        Args:
            无。

        Returns:
            canonical JSON 字节。

        Raises:
            ContractError: receipt 含非严格 JSON 值时抛出。
        """

        return canonical_json_bytes(self.to_json())


def load_fixture_inputs(request: FixtureInputRequest) -> AcceptanceInputs:
    """从固定 fixture 与临时物化目录加载严格 evaluator 输入。

    Args:
        request: 严格 frozen fixture 加载请求。

    Returns:
        完整严格输入。

    Raises:
        ContractError: fixture 路径、JSON schema 或数值非法时抛出。
        OSError: fixture 或研究 artifact 读取失败时抛出。
    """

    root = _require_bounded_directory(request.fixture_root, "fixture_root")
    report_path = _bounded_file(root, _FIXTURE_FILES["report"], "fixture report")
    report_text = report_path.read_text(encoding="utf-8")
    contract = parse_acceptance_contract(
        load_json_file(
            _bounded_file(root, _FIXTURE_FILES["contract"], "contract"),
            label="contract",
        )
    )
    return AcceptanceInputs(
        contract=contract,
        inventory=parse_source_inventory(
            load_json_file(_bounded_file(root, _FIXTURE_FILES["inventory"], "inventory"), label="inventory")
        ),
        price_snapshot=parse_price_snapshot(
            load_json_file(_bounded_file(root, _FIXTURE_FILES["price"], "price"), label="price")
        ),
        quality_review=parse_quality_review(
            load_json_file(_bounded_file(root, _FIXTURE_FILES["quality"], "quality"), label="quality")
        ),
        write_manifest=parse_owner_write_manifest(
            load_json_file(_bounded_file(root, _FIXTURE_FILES["manifest"], "manifest"), label="manifest")
        ),
        run_summary=parse_owner_run_summary(
            load_json_file(_bounded_file(root, _FIXTURE_FILES["summary"], "summary"), label="summary")
        ),
        report_text=report_text,
        research_artifacts=inspect_research_artifacts(
            request.artifact_root,
            required_artifacts=contract.required_research_artifacts,
            expected_sha256=request.expected_artifact_sha256,
        ),
        runtime=RuntimeEvidence(
            approved_budget=request.approved_budget,
            max_wall_seconds=_positive_runtime_int(request.max_wall_seconds, "max_wall_seconds"),
            actual_wall_seconds=_nonnegative_runtime_float(
                request.actual_wall_seconds,
                "actual_wall_seconds",
            ),
            phase_receipts=request.phase_receipts,
        ),
        acceptance_owned_outputs=request.acceptance_owned_outputs,
    )


def inspect_research_artifacts(
    artifact_root: Path,
    *,
    required_artifacts: tuple[str, ...],
    expected_sha256: tuple[tuple[str, str], ...] = (),
) -> ResearchArtifactInspection:
    """只读检查 13 个研究产物、containment、指纹与 owner validators。

    Args:
        artifact_root: ``assets/research_templates`` 精确目录。
        required_artifacts: contract 固定的 13 个文件名。
        expected_sha256: 可选的已绑定 artifact 摘要。

    Returns:
        不包含生产原文和绝对路径的检查结果。

    Raises:
        ContractError: root、locator 或 expected SHA 形状非法时抛出。
        OSError: 读取已存在普通文件失败时抛出。
    """

    if len(required_artifacts) != len(REQUIRED_RESEARCH_ARTIFACTS) or frozenset(required_artifacts) != frozenset(
        REQUIRED_RESEARCH_ARTIFACTS
    ):
        raise ContractError("required_research_artifacts 必须精确等于固定 AAPL/technology 13 文件集合")
    root = _require_bounded_directory(artifact_root, "artifact_root")
    paths, references, issues = _collect_research_artifact_files(
        root,
        required_artifacts,
        _expected_hash_pairs(expected_sha256),
    )
    inventory_ok = len(paths) == len(required_artifacts) and len(paths) == len(set(required_artifacts)) and not issues
    if not inventory_ok:
        return ResearchArtifactInspection(
            references=references,
            inventory_ok=False,
            workbook_valid=False,
            progress_current=False,
            progress_untampered=False,
            bundle_valid=False,
            source_map_valid=False,
            status_snapshots_valid=False,
            monitoring_valid=False,
            monitoring_execution_mode="",
            automated_execution_allowed=True,
            workbook_completion_status="unknown",
            workbook_open_item_count=-1,
            monitoring_readiness="unknown",
            monitoring_blocked_task_count=-1,
            monitoring_unbound_sources=(),
            issues=issues,
        )
    payloads = _load_strict_artifact_json(paths)
    workbook = _inspect_workbook_artifacts(paths, payloads)
    bundle = _inspect_bundle_artifacts(paths, payloads)
    monitoring = _inspect_monitoring_artifacts(paths, payloads)
    return ResearchArtifactInspection(
        references=references,
        inventory_ok=True,
        workbook_valid=workbook[0],
        progress_current=workbook[1],
        progress_untampered=workbook[2],
        bundle_valid=bundle[0],
        source_map_valid=bundle[1],
        status_snapshots_valid=bundle[2],
        monitoring_valid=monitoring[0],
        monitoring_execution_mode=monitoring[1],
        automated_execution_allowed=monitoring[2],
        workbook_completion_status=workbook[3],
        workbook_open_item_count=workbook[4],
        monitoring_readiness=monitoring[3],
        monitoring_blocked_task_count=monitoring[4],
        monitoring_unbound_sources=monitoring[5],
        issues=issues,
    )


def _collect_research_artifact_files(
    root: Path,
    required_artifacts: tuple[str, ...],
    expected: dict[str, str],
) -> tuple[dict[str, Path], tuple[ArtifactReference, ...], tuple[str, ...]]:
    """收集 containment 内普通文件并绑定摘要。

    Args:
        root: 已解析的 artifact 根目录。
        required_artifacts: contract 要求的文件名。
        expected: 可选文件名到已绑定摘要的映射。

    Returns:
        文件映射、稳定排序的引用与问题列表。

    Raises:
        ContractError: locator 不安全时抛出。
        OSError: 普通文件读取失败时抛出。
    """

    references: list[ArtifactReference] = []
    issues: list[str] = []
    paths: dict[str, Path] = {}
    for name in required_artifacts:
        if not _is_safe_artifact_name(name):
            raise ContractError(f"research artifact locator 非法: {name}")
        candidate = root / name
        if candidate.is_symlink():
            issues.append(f"{name}: symlink forbidden")
            continue
        if not candidate.is_file():
            issues.append(f"{name}: regular file missing")
            continue
        resolved = candidate.resolve()
        if resolved.parent != root:
            issues.append(f"{name}: containment violation")
            continue
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        bound_digest = expected.get(name)
        if bound_digest is not None and bound_digest != digest:
            issues.append(f"{name}: bound SHA-256 mismatch")
        paths[name] = candidate
        references.append(
            ArtifactReference(
                locator=f"{_ACCEPTANCE_ARTIFACT_PREFIX}/{name}",
                sha256=digest,
            )
        )
    return (
        paths,
        tuple(sorted(references, key=lambda item: item.locator)),
        tuple(issues),
    )


def _load_strict_artifact_json(paths: dict[str, Path]) -> dict[str, JsonObject]:
    """经统一 strict JSON ingress 预载全部生产 JSON artifacts。

    Args:
        paths: 已通过 containment 与文件类型检查的文件映射。

    Returns:
        JSON 文件名到严格顶层对象的映射。

    Raises:
        ContractError: JSON 含 NaN/Infinity、非 JSON 值或顶层非对象时抛出。
        OSError: artifact 读取失败时抛出。
    """

    payloads: dict[str, JsonObject] = {}
    for name, path in sorted(paths.items()):
        if path.suffix != ".json":
            continue
        label = f"research artifact {name}"
        payloads[name] = _owner_mapping(load_json_file(path, label=label), label)
    return payloads


def _inspect_workbook_artifacts(
    paths: dict[str, Path],
    payloads: dict[str, JsonObject],
) -> tuple[bool, bool, bool, str, int]:
    """调用 owner workbook validators 并收窄结果。

    Args:
        paths: 已通过 containment 与文件类型检查的文件映射。
        payloads: 已通过 strict JSON ingress 的 artifact 对象。

    Returns:
        workbook 有效、progress 当前、progress 未篡改、完成状态与 open 数量。

    Raises:
        ContractError: owner 返回形状非法时抛出。
        OSError: artifact 读取失败时抛出。
    """

    workbook_path = paths["technology.research-workbook.json"]
    report_path = paths["technology.research-progress.md"]
    workbook_payload = payloads["technology.research-workbook.json"]
    try:
        workbook_result_bytes = json.dumps(
            validate_research_workbook_payload(json.loads(canonical_json_bytes(workbook_payload))),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("workbook validation owner result 不是严格 JSON") from exc
    workbook_validation = _narrow_owner_result(workbook_result_bytes, "workbook validation")
    workbook_valid = _owner_ok(workbook_validation, "workbook validation")
    completion_status, open_item_count = _workbook_completion(workbook_payload)
    try:
        report_result_bytes = json.dumps(
            inspect_research_workbook_report(report_path, workbook_path),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("workbook report inspection owner result 不是严格 JSON") from exc
    report_inspection = _narrow_owner_result(report_result_bytes, "workbook report inspection")
    report_validation = _owner_nested_mapping(
        report_inspection,
        "validation",
        "workbook report inspection",
    )
    progress_current = _owner_ok(
        report_validation,
        "workbook report validation",
    ) and not _owner_bool(report_inspection, "stale", "workbook report inspection")
    progress_untampered = not _owner_bool(
        report_inspection,
        "report_tampered",
        "workbook report inspection",
    )
    return (
        workbook_valid,
        progress_current,
        progress_untampered,
        completion_status,
        open_item_count,
    )


def _inspect_bundle_artifacts(
    paths: dict[str, Path],
    payloads: dict[str, JsonObject],
) -> tuple[bool, bool, bool]:
    """调用 bundle、source-map 与状态快照 owner validators。

    Args:
        paths: 已通过 containment 与文件类型检查的文件映射。
        payloads: 已通过 strict JSON ingress 的 artifact 对象。

    Returns:
        bundle、source-map 与三份状态快照的有效标志。

    Raises:
        ContractError: owner 返回形状非法时抛出。
        OSError: artifact 读取失败时抛出。
    """

    try:
        bundle_result_bytes = json.dumps(
            inspect_research_template_bundle(paths["technology.bundle.json"]),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("bundle inspection owner result 不是严格 JSON") from exc
    bundle_inspection = _narrow_owner_result(bundle_result_bytes, "bundle inspection")
    bundle_valid = _owner_ok(
        _owner_nested_mapping(bundle_inspection, "validation", "bundle inspection"),
        "bundle validation",
    )
    try:
        source_map_result_bytes = json.dumps(
            validate_monitoring_source_map_payload(
                json.loads(canonical_json_bytes(payloads["technology.monitoring-rules.json"])),
                json.loads(canonical_json_bytes(payloads["technology.source-map.json"])),
            ),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("source-map validation owner result 不是严格 JSON") from exc
    source_map_validation = _narrow_owner_result(source_map_result_bytes, "source-map validation")
    return (
        bundle_valid,
        _owner_ok(source_map_validation, "source-map validation"),
        _status_snapshots_valid(payloads),
    )


def _inspect_monitoring_artifacts(
    paths: dict[str, Path],
    payloads: dict[str, JsonObject],
) -> tuple[bool, str, bool, str, int, tuple[str, ...]]:
    """调用 monitoring owner validator 并收窄安全状态。

    Args:
        paths: 已通过 containment 与文件类型检查的文件映射。
        payloads: 已通过 strict JSON ingress 的 artifact 对象。

    Returns:
        validator、模式、自动化标志、readiness、blocked 数量与未绑定源。

    Raises:
        ContractError: owner 返回形状非法时抛出。
        OSError: monitoring artifact 读取失败时抛出。
    """

    monitoring_path = paths["technology.monitoring-plan.json"]
    try:
        monitoring_result_bytes = json.dumps(
            inspect_monitoring_execution_plan(monitoring_path),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("monitoring inspection owner result 不是严格 JSON") from exc
    monitoring_inspection = _narrow_owner_result(monitoring_result_bytes, "monitoring inspection")
    monitoring_valid = _owner_ok(
        _owner_nested_mapping(
            monitoring_inspection,
            "validation",
            "monitoring inspection",
        ),
        "monitoring validation",
    )
    execution_mode = _owner_string(
        monitoring_inspection,
        "execution_mode",
        "monitoring inspection",
    )
    monitoring_payload = payloads["technology.monitoring-plan.json"]
    automated = _owner_bool(
        monitoring_payload,
        "automated_execution_allowed",
        "monitoring plan",
    )
    readiness_payload = _owner_nested_mapping(
        monitoring_payload,
        "readiness",
        "monitoring plan",
    )
    return (
        monitoring_valid,
        execution_mode,
        automated,
        _owner_string(readiness_payload, "status", "monitoring plan.readiness"),
        _owner_nonnegative_int(
            readiness_payload,
            "blocked_task_count",
            "monitoring plan.readiness",
        ),
        _monitoring_unbound_sources(monitoring_payload),
    )


def build_source_inventory_from_repositories(request: RepositoryInventoryRequest) -> SourceInventory:
    """仅通过三个 Fins 仓储 Protocol 构建严格源清单。

    Args:
        request: 三个仓储 Protocol 与清单元数据的严格 frozen 请求。

    Returns:
        按日期/form/document_id 排序的严格源清单。

    Raises:
        ContractError: owner meta、主文件或指纹不闭合时抛出。
        OSError: 仓储读取失败时抛出。
    """

    documents: list[SourceDocument] = []
    for source_kind in (SourceKind.FILING, SourceKind.MATERIAL):
        document_ids = request.source_repository.list_source_document_ids(request.ticker, source_kind)
        if len(document_ids) != len(set(document_ids)):
            raise ContractError(f"repository {source_kind.value} document ids 存在重复")
        for document_id in sorted(document_ids):
            source_meta: JsonValue = request.source_repository.get_source_meta(
                request.ticker,
                document_id,
                source_kind,
            )
            try:
                processed_meta: JsonValue | None = request.processed_repository.get_processed_meta(
                    request.ticker,
                    document_id,
                )
            except FileNotFoundError:
                processed_meta = None
            primary_meta = request.source_repository.get_primary_file(
                request.ticker,
                document_id,
                source_kind,
            )
            primary_name = PurePosixPath(primary_meta.uri.replace("\\", "/")).name
            if not primary_name:
                raise ContractError(f"repository primary filename 为空: {document_id}")
            primary_bytes = request.blob_repository.read_file_bytes(
                request.source_repository.get_source_handle(
                    request.ticker,
                    document_id,
                    source_kind,
                ),
                primary_name,
            )
            primary_sha256 = hashlib.sha256(primary_bytes).hexdigest()
            if primary_meta.sha256 is not None and primary_meta.sha256 != primary_sha256:
                raise ContractError(f"repository primary SHA-256 不闭合: {document_id}")
            documents.append(
                _source_document_from_owner(
                    document_id=document_id,
                    source_kind=source_kind,
                    source_meta=source_meta,
                    processed_meta=processed_meta,
                    primary_sha256=primary_sha256,
                )
            )
    ordered = tuple(sorted(documents, key=lambda item: (item.filing_date, item.form, item.document_id)))
    ordered_ids = [item.document_id for item in ordered]
    if len(ordered_ids) != len(set(ordered_ids)):
        raise ContractError("repository filing/material document_id 冲突")
    return SourceInventory(
        fixture_id=request.fixture_id,
        ticker=request.ticker,
        company=request.company,
        as_of=request.as_of,
        live_freshness_claimed=request.live_freshness_claimed,
        source_windows=request.source_windows,
        latest_discovery=tuple(sorted(request.latest_discovery)),
        documents=ordered,
    )


def evaluate_acceptance(inputs: AcceptanceInputs, *, evaluated_at: datetime) -> EvaluationResult:
    """执行全部确定性 hard gates 与人工 rubric 三态聚合。

    Args:
        inputs: 已严格解析的完整验收输入。
        evaluated_at: 显式注入的固定验证时间。

    Returns:
        字节稳定、无 stdout 副作用的三态结果。

    Raises:
        ContractError: evaluated_at 不带时区或 evaluator 自身 receipt 泄漏敏感形状时抛出。
    """

    format_utc(evaluated_at)
    findings: list[Finding] = []
    findings.extend(_evaluate_identity_and_models(inputs))
    findings.extend(_evaluate_run_governance(inputs))
    findings.extend(_evaluate_inventory_and_price(inputs))
    findings.extend(_evaluate_report_and_citations(inputs))
    findings.extend(_evaluate_research_artifacts(inputs.research_artifacts))
    phase_payloads: tuple[JsonValue, ...] = tuple(receipt.to_json() for receipt in inputs.runtime.phase_receipts)
    findings.extend(_evaluate_acceptance_owned_outputs((*inputs.acceptance_owned_outputs, *phase_payloads)))
    manual_findings, manual_pending = _evaluate_manual_review(inputs.contract, inputs.quality_review)
    findings.extend(manual_findings)
    ordered_findings = tuple(sorted(findings, key=lambda item: (item.gate, item.code, item.locator or "")))
    gate_rows = _gate_statuses(
        inputs.contract.hard_gates,
        ordered_findings,
        manual_pending=manual_pending,
    )
    if ordered_findings:
        verdict: Verdict = "FAIL"
    elif manual_pending:
        verdict = "PENDING_MANUAL_REVIEW"
    else:
        verdict = "PASS"
    residuals = _build_residuals(inputs)
    result = EvaluationResult(
        verdict=verdict,
        total_score=inputs.quality_review.total_score,
        dimension_scores=tuple((item.name, item.score) for item in inputs.quality_review.dimensions),
        hard_gates=gate_rows,
        findings=ordered_findings,
        artifacts=inputs.research_artifacts.references,
        residuals=residuals,
        evaluated_at=evaluated_at,
    )
    receipt_payload = result.to_json()
    leaked = _sensitive_strings(receipt_payload, "acceptance-receipt")
    if leaked:
        raise ContractError("evaluator 生成的 acceptance receipt 命中敏感形状")
    return result


def _evaluate_identity_and_models(inputs: AcceptanceInputs) -> list[Finding]:
    """验证 AAPL/technology/DeepSeek+MiMo 身份闭包。

    Args:
        inputs: 完整严格 evaluator 输入。

    Returns:
        身份与模型职责 findings。

    Raises:
        本函数不显式抛出异常。
    """

    findings = _evaluate_target_identity(inputs)
    findings.extend(_evaluate_model_identity(inputs))
    return findings


def _evaluate_target_identity(inputs: AcceptanceInputs) -> list[Finding]:
    """验证 AAPL、公司与 technology 模板选择闭包。

    Args:
        inputs: 完整严格 evaluator 输入。

    Returns:
        目标与模板 findings。

    Raises:
        本函数不显式抛出异常。
    """

    findings: list[Finding] = []
    contract = inputs.contract
    manifest = inputs.write_manifest
    summary = inputs.run_summary
    inventory = inputs.inventory
    if not all((contract.target.ticker == _EXPECTED_TICKER, inventory.ticker == _EXPECTED_TICKER)):
        findings.append(_high("identity.ticker", "source_price_closed", "ticker 必须闭合为 AAPL"))
    if not all(
        (
            contract.target.company in _EXPECTED_COMPANIES,
            inventory.company in _EXPECTED_COMPANIES,
        )
    ):
        findings.append(_high("identity.company", "source_price_closed", "公司名必须闭合为 Apple/Apple Inc."))
    if not all((manifest.ticker == _EXPECTED_TICKER, summary.ticker == _EXPECTED_TICKER)):
        findings.append(_high("identity.owner_ticker", "run_summary_passed", "owner artifacts ticker 不闭合"))
    if manifest.company not in _EXPECTED_COMPANIES:
        findings.append(_high("identity.manifest_company", "run_summary_passed", "write manifest 公司名不闭合"))
    if not all(
        (
            contract.target.research_template == _EXPECTED_TEMPLATE,
            manifest.resolved_template == _EXPECTED_TEMPLATE,
        )
    ):
        findings.append(_high("identity.template", "research_artifacts_valid", "resolved template 必须为 technology"))
    if not _template_provenance_ok(manifest.requested_template, manifest.selection_mode):
        findings.append(
            _high(
                "identity.template_provenance",
                "research_artifacts_valid",
                "template requested/resolved/selection provenance 不闭合",
            )
        )
    return findings


def _evaluate_model_identity(inputs: AcceptanceInputs) -> list[Finding]:
    """验证 DeepSeek 主写、MiMo 审计与禁用 fallback 闭包。

    Args:
        inputs: 完整严格 evaluator 输入。

    Returns:
        模型职责 findings。

    Raises:
        本函数不显式抛出异常。
    """

    findings: list[Finding] = []
    contract = inputs.contract
    manifest = inputs.write_manifest
    summary = inputs.run_summary
    roles = contract.model_roles
    if not all(
        (
            roles.primary == _EXPECTED_PRIMARY_MODEL,
            manifest.primary_model == _EXPECTED_PRIMARY_MODEL,
        )
    ):
        findings.append(_high("models.primary", "dual_model_roles_closed", "主写模型必须为 deepseek-v4-pro"))
    if not all(
        (
            roles.audit == _EXPECTED_AUDIT_MODEL,
            manifest.audit_model == _EXPECTED_AUDIT_MODEL,
        )
    ):
        findings.append(_high("models.audit", "dual_model_roles_closed", "审计模型必须为 mimo-v2.5-pro-thinking"))
    if not all(
        (
            summary.primary_models == (_EXPECTED_PRIMARY_MODEL,),
            summary.audit_models == (_EXPECTED_AUDIT_MODEL,),
        )
    ):
        findings.append(_high("models.summary_roles", "dual_model_roles_closed", "run summary 模型角色不闭合"))
    if not manifest.fallback_disabled:
        findings.append(_high("models.fallback", "dual_model_roles_closed", "验收运行不得启用 fallback"))
    return findings


def _template_provenance_ok(requested_template: str, selection_mode: str) -> bool:
    """判断模板请求与选择模式是否形成允许的 provenance。

    Args:
        requested_template: owner 记录的模板请求。
        selection_mode: owner 记录的选择模式。

    Returns:
        named technology 或 auto 选择闭合时为真。

    Raises:
        本函数不显式抛出异常。
    """

    named_ok = requested_template == _EXPECTED_TEMPLATE and selection_mode == "named"
    auto_ok = requested_template == "auto" and selection_mode.startswith("auto")
    return named_ok or auto_ok


def _evaluate_run_governance(inputs: AcceptanceInputs) -> list[Finding]:
    """验证 run summary、audit、usage、预算与总 wall-clock。

    Args:
        inputs: 完整严格 evaluator 输入。

    Returns:
        运行治理 findings。

    Raises:
        本函数不显式抛出异常。
    """

    findings = _evaluate_run_summary_receipt(inputs)
    findings.extend(_evaluate_budget_receipt(inputs))
    findings.extend(_evaluate_wall_clock(inputs.runtime))
    return findings


def _evaluate_run_summary_receipt(inputs: AcceptanceInputs) -> list[Finding]:
    """验证 owner run summary、audit 与 usage 闭包。

    Args:
        inputs: 完整严格 evaluator 输入。

    Returns:
        run summary、audit 与 usage findings。

    Raises:
        本函数不显式抛出异常。
    """

    summary = inputs.run_summary
    approved = inputs.runtime.approved_budget
    findings: list[Finding] = []
    summary_closed = all(
        (
            summary.schema_version == "write_run_summary_v3",
            summary.gate_status == "passed",
            summary.publication_status == "published",
            summary.failed_count == 0,
            summary.chapters_closed,
            summary.chapter_count > 0,
        )
    )
    if not summary_closed:
        findings.append(
            _high("run_summary.not_passed", "run_summary_passed", "write run summary 未完整 published/pass")
        )
    audit_closed = all(
        (
            summary.audit_required,
            summary.audit_failed_count == 0,
            summary.audit_skipped_count == 0,
            summary.gate_blocked_count == 0,
        )
    )
    if not audit_closed:
        findings.append(_high("audit.incomplete", "audit_complete", "required chapter audit 存在失败、跳过或 blocked"))
    usage_closed = all(
        (
            summary.usage_status == "complete",
            summary.request_count > 0,
            summary.total_tokens > 0,
        )
    )
    if not usage_closed:
        findings.append(_high("usage.incomplete", "dual_model_roles_closed", "model usage 必须完整且非空"))
    if not all(
        (
            summary.cost_status == "complete",
            summary.cost_currency == approved.budget_currency,
        )
    ):
        findings.append(_high("usage.cost_coverage", "dual_model_roles_closed", "模型定价 coverage 或币种不闭合"))
    return findings


def _evaluate_budget_receipt(inputs: AcceptanceInputs) -> list[Finding]:
    """验证批准预算、owner 预算摘要与实际用量闭包。

    Args:
        inputs: 完整严格 evaluator 输入。

    Returns:
        预算状态、批准值漂移与超限 findings。

    Raises:
        本函数不显式抛出异常。
    """

    findings: list[Finding] = []
    summary = inputs.run_summary
    approved = inputs.runtime.approved_budget
    budget = summary.budget
    budget_closed = all(
        (
            budget.enabled,
            budget.status == "within_budget",
            not budget.block_present,
            budget.active_reservation_count == 0,
            budget.usage_status == "complete",
            budget.cost_status == "complete",
        )
    )
    if not budget_closed:
        findings.append(_high("budget.blocked", "budget_within_limits", "预算 receipt 未处于完整 within_budget"))
    approval_closed = all(
        (
            budget.max_model_requests == approved.max_model_requests,
            budget.max_total_tokens == approved.max_total_tokens,
            budget.max_estimated_cost == approved.max_estimated_cost,
            budget.budget_currency == approved.budget_currency,
        )
    )
    if not approval_closed:
        findings.append(_high("budget.approval_drift", "budget_within_limits", "run budget 与批准预算漂移"))
    within_limits = all(
        (
            budget.model_requests <= approved.max_model_requests,
            budget.total_tokens <= approved.max_total_tokens,
            budget.estimated_cost <= approved.max_estimated_cost,
            budget.currency == approved.budget_currency,
            summary.request_count <= approved.max_model_requests,
            summary.total_tokens <= approved.max_total_tokens,
            summary.known_estimated_cost <= approved.max_estimated_cost,
        )
    )
    if not within_limits:
        findings.append(_high("budget.exceeded", "budget_within_limits", "请求、Token 或成本超过批准上限"))
    return findings


def _evaluate_wall_clock(runtime: RuntimeEvidence) -> list[Finding]:
    """验证整次与阶段 wall-clock receipts。

    Args:
        runtime: 严格预算、总耗时与阶段 receipts。

    Returns:
        超时、partial 与非法 remaining wall findings。

    Raises:
        本函数不显式抛出异常。
    """

    findings: list[Finding] = []
    if runtime.actual_wall_seconds > runtime.max_wall_seconds:
        findings.append(_high("wall_clock.exceeded", "budget_within_limits", "整次运行 wall-clock 超过批准上限"))
    for receipt in runtime.phase_receipts:
        if receipt.remaining_wall_seconds > runtime.max_wall_seconds:
            findings.append(_high("wall_clock.receipt_invalid", "budget_within_limits", "阶段 remaining wall 非法"))
        if receipt.partial_by_timeout or receipt.status == "timeout":
            findings.append(_high("wall_clock.timeout", "budget_within_limits", "阶段发生 timeout/partial_by_timeout"))
    return findings


def _evaluate_inventory_and_price(inputs: AcceptanceInputs) -> list[Finding]:
    """验证显式窗口、as-of、processed、discovery 与价格时效。

    Args:
        inputs: 完整严格 evaluator 输入。

    Returns:
        source/price hard-gate findings。

    Raises:
        ContractError: processed 状态无法 canonical 序列化时抛出。
    """

    inventory = inputs.inventory
    as_of_date = inventory.as_of.date()
    findings = _evaluate_inventory_documents(inventory)
    findings.extend(_evaluate_latest_discovery(inventory))
    findings.extend(
        _evaluate_price_snapshot(
            inputs,
            as_of_date=as_of_date,
        )
    )
    return findings


def _evaluate_inventory_documents(inventory: SourceInventory) -> list[Finding]:
    """验证 SEC 窗口、源日期、ingest 与 processed 状态。

    Args:
        inventory: 严格源清单。

    Returns:
        窗口、文档与 required-form findings。

    Raises:
        ContractError: processed 状态无法 canonical 序列化时抛出。
    """

    findings: list[Finding] = []
    as_of_date = inventory.as_of.date()
    expected_windows = (
        SourceWindow(("10-K",), _subtract_calendar_years(as_of_date, 5), as_of_date),
        SourceWindow(("10-Q",), _subtract_calendar_years(as_of_date, 2), as_of_date),
        SourceWindow(("8-K", "DEF 14A"), _subtract_calendar_years(as_of_date, 2), as_of_date),
    )
    if inventory.source_windows != expected_windows:
        findings.append(_high("inventory.windows", "source_price_closed", "三组 SEC 显式窗口与 as-of policy 不一致"))
    required_forms = {"10-K", "10-Q", "DEF 14A"}
    found_forms: set[str] = set()
    for document in inventory.documents:
        if document.filing_date > as_of_date or document.report_date > as_of_date:
            findings.append(
                _high("inventory.future_source", "source_price_closed", "源文档日期晚于 as-of", document.document_id)
            )
        if not document.ingest_complete:
            findings.append(
                _high(
                    "inventory.ingest_incomplete",
                    "source_price_closed",
                    "源文档 ingest_complete=false",
                    document.document_id,
                )
            )
        if (
            not document.processed.exists
            or not document.processed.parser_version
            or not document.processed.quality
            or not document.processed.schema_version
            or not document.processed.source_fingerprint
        ):
            findings.append(
                _high(
                    "inventory.processed_missing",
                    "source_price_closed",
                    "必需 processed 状态不完整",
                    document.document_id,
                )
            )
        if document.processed.reprocess_required:
            findings.append(
                _high("inventory.reprocess_required", "source_price_closed", "文档需要 reprocess", document.document_id)
            )
        if canonical_json_sha256(document.processed.to_json()) != document.processed_state_fingerprint:
            findings.append(
                _high(
                    "inventory.processed_fingerprint",
                    "source_price_closed",
                    "processed 状态指纹漂移",
                    document.document_id,
                )
            )
        if document.source_kind == "filing":
            found_forms.add(document.form)
    findings.extend(
        _high("inventory.required_form", "source_price_closed", f"显式窗口缺少 {missing_form}")
        for missing_form in sorted(required_forms - found_forms)
    )
    return findings


def _evaluate_latest_discovery(inventory: SourceInventory) -> list[Finding]:
    """验证必需 SEC form 的最新 accession discovery 闭包。

    Args:
        inventory: 严格源清单。

    Returns:
        latest discovery findings。

    Raises:
        本函数不显式抛出异常。
    """

    findings: list[Finding] = []
    required_forms = {"10-K", "10-Q", "DEF 14A"}
    latest_by_form = dict(inventory.latest_discovery)
    for form in sorted(required_forms):
        candidates = [item for item in inventory.documents if item.source_kind == "filing" and item.form == form]
        if not candidates:
            continue
        latest = max(candidates, key=lambda item: (item.filing_date, item.document_id))
        if latest.accession is None or latest_by_form.get(form) != latest.accession:
            findings.append(
                _high("inventory.latest_discovery", "source_price_closed", f"{form} 最新 accession 与 discovery 不闭合")
            )
    return findings


def _evaluate_price_snapshot(inputs: AcceptanceInputs, *, as_of_date: date) -> list[Finding]:
    """验证价格 future/max-age/contract/material 闭包。

    Args:
        inputs: 完整严格 evaluator 输入。
        as_of_date: 清单 as-of 的日期部分。

    Returns:
        价格相关 findings。

    Raises:
        本函数不显式抛出异常。
    """

    findings: list[Finding] = []
    inventory = inputs.inventory
    price = inputs.price_snapshot
    if price.captured_at > inventory.as_of or price.market_date > as_of_date:
        findings.append(_high("price.future", "source_price_closed", "价格快照时间晚于 as-of"))
    max_age = timedelta(days=price.max_age_days)
    if inventory.as_of - price.captured_at > max_age or as_of_date - price.market_date > max_age:
        findings.append(_high("price.stale", "source_price_closed", "价格快照超过 max_age_days"))
    reference = inputs.contract.valuation_reference_price
    if (price.price, price.currency, price.market_date) != (
        reference.price,
        reference.currency,
        reference.market_date,
    ):
        findings.append(_high("price.contract_mismatch", "source_price_closed", "价格快照与 contract reference 不一致"))
    material = inventory.document_by_id(reference.material_document_id)
    if material is None or material.source_kind != "material" or material.form != "MATERIAL_OTHER":
        findings.append(_high("price.material_missing", "source_price_closed", "price material 未闭合到源清单"))
    return findings


def _evaluate_report_and_citations(inputs: AcceptanceInputs) -> list[Finding]:
    """验证报告主题、四段 evidence、source-list 与唯一估值参考价。

    Args:
        inputs: 完整严格 evaluator 输入。

    Returns:
        报告结构、质量与 citation closure findings。

    Raises:
        ContractError: 报告内引用 JSON 无法严格解析时由本函数收敛为 finding。
    """

    sections = _markdown_sections(inputs.report_text)
    source_section = _find_section(sections, (_SOURCE_LIST_HEADING,))
    if source_section is None:
        return [_high("report.source_list_missing", "source_price_closed", "报告缺少最终来源清单")]
    as_of_date = inputs.inventory.as_of.date()
    source_entries, source_errors = _parse_evidence_lines(source_section[1], as_of_date)
    findings = [
        _high("report.source_list_quality", "source_price_closed", message, "report#来源清单")
        for message in source_errors
    ]
    source_ids = {entry[0] for entry in source_entries}
    inventory_ids = {item.document_id for item in inputs.inventory.documents}
    if source_ids != inventory_ids:
        findings.append(
            _high("report.source_list_closure", "source_price_closed", "来源清单与 source inventory 不完全闭合")
        )
    topic_findings, body_evidence_ids = _evaluate_topic_evidence(
        sections,
        inputs.contract.required_topics,
        as_of_date=as_of_date,
    )
    findings.extend(topic_findings)
    if not body_evidence_ids <= source_ids:
        findings.append(_high("report.citation_closure", "source_price_closed", "章节 evidence 未闭合到最终来源清单"))
    if not body_evidence_ids <= inventory_ids:
        findings.append(
            _high("report.inventory_closure", "source_price_closed", "章节 evidence 未闭合到 source inventory")
        )
    findings.extend(_evaluate_report_reference(inputs))
    findings.extend(_evaluate_manifest_evidence(inputs, inventory_ids=inventory_ids))
    return findings


def _evaluate_topic_evidence(
    sections: tuple[tuple[str, str], ...],
    required_topics: tuple[str, ...],
    *,
    as_of_date: date,
) -> tuple[list[Finding], set[str]]:
    """验证所有实质章节及其四段 evidence。

    Args:
        sections: 已解析的 Markdown 二级章节。
        required_topics: contract 要求的主题名称。
        as_of_date: 引用发布日期上限。

    Returns:
        主题 findings 与正文引用 document IDs。

    Raises:
        本函数不显式抛出异常。
    """

    findings: list[Finding] = []
    body_evidence_ids: set[str] = set()
    for topic in required_topics:
        aliases = _TOPIC_HEADINGS.get(topic, (topic.replace("_", " "),))
        section = _find_section(sections, aliases)
        if section is None:
            findings.append(_high(f"report.topic.{topic}", "source_price_closed", f"报告缺少 {topic} 实质章节"))
            continue
        evidence_text = _evidence_subsection(section[1])
        if evidence_text is None:
            findings.append(_high(f"report.evidence_section.{topic}", "source_price_closed", f"{topic} 缺少证据与出处"))
            continue
        evidence, errors = _parse_evidence_lines(evidence_text, as_of_date)
        if not evidence:
            findings.append(_high(f"report.evidence_empty.{topic}", "source_price_closed", f"{topic} evidence 为空"))
        findings.extend(
            _high(
                f"report.acceptance_quality.{topic}",
                "source_price_closed",
                message,
                f"report#{topic}",
            )
            for message in errors
        )
        body_evidence_ids.update(entry[0] for entry in evidence)
    return findings, body_evidence_ids


def _evaluate_report_reference(inputs: AcceptanceInputs) -> list[Finding]:
    """验证报告中唯一且精确的估值参考价格记录。

    Args:
        inputs: 完整严格 evaluator 输入。

    Returns:
        参考价格数量、schema 与一致性 findings。

    Raises:
        ContractError: 错误 schema 被收敛为 finding，不向外传播。
    """

    reference_records: list[str] = []
    for line in inputs.report_text.splitlines():
        normalized = line.strip()
        if normalized.startswith(_REFERENCE_PREFIX):
            reference_records.append(normalized[len(_REFERENCE_PREFIX) :].strip())
    if len(reference_records) != 1:
        return [_high("report.valuation_reference_count", "source_price_closed", "估值参考价格记录必须唯一")]
    try:
        reference_payload = parse_json_bytes(
            reference_records[0].encode("utf-8"),
            label="valuation_reference_price",
        )
        reference = _strict_reference_price(reference_payload)
        expected = inputs.contract.valuation_reference_price
        expected_record = (
            expected.price,
            expected.currency,
            expected.market_date,
            expected.material_document_id,
        )
        if reference != expected_record:
            return [
                _high(
                    "report.valuation_reference_mismatch",
                    "source_price_closed",
                    "报告估值价格/币种/日期/material 不一致",
                )
            ]
    except ContractError as exc:
        return [_high("report.valuation_reference_schema", "source_price_closed", _safe_contract_message(exc))]
    return []


def _evaluate_manifest_evidence(
    inputs: AcceptanceInputs,
    *,
    inventory_ids: set[str],
) -> list[Finding]:
    """验证生产 write manifest 的四段 evidence 与清单闭包。

    Args:
        inputs: 完整严格 evaluator 输入。
        inventory_ids: 严格源清单 document IDs。

    Returns:
        manifest evidence findings。

    Raises:
        本函数不显式抛出异常。
    """

    findings: list[Finding] = []
    manifest_ids: set[str] = set()
    for title, evidence_items in inputs.write_manifest.chapter_evidence:
        if not evidence_items:
            findings.append(
                _high("manifest.evidence_missing", "audit_complete", "write manifest 章节 evidence 为空", title)
            )
        for evidence in evidence_items:
            parts = tuple(part.strip() for part in evidence.split(" | "))
            if len(parts) != len(inputs.contract.required_evidence_parts) or any(not part for part in parts):
                findings.append(
                    _high(
                        "manifest.evidence_structure",
                        "audit_complete",
                        "生产结构层 evidence 不是四段非空",
                        title,
                    )
                )
                continue
            manifest_ids.add(parts[0])
    if not manifest_ids <= inventory_ids:
        findings.append(
            _high("manifest.evidence_inventory", "audit_complete", "manifest evidence 未闭合到 source inventory")
        )
    return findings


def _evaluate_research_artifacts(inspection: ResearchArtifactInspection) -> list[Finding]:
    """验证 13 产物、workbook/report 与 monitoring 安全状态。

    Args:
        inspection: 只读研究产物检查结果。

    Returns:
        研究 artifact hard-gate findings。

    Raises:
        本函数不显式抛出异常。
    """

    findings: list[Finding] = []
    if not inspection.inventory_ok or inspection.issues:
        findings.append(
            _high(
                "artifacts.inventory",
                "research_artifacts_valid",
                "研究 artifact 缺失、越界、symlink 或绑定摘要漂移",
            )
        )
    if not inspection.bundle_valid or not inspection.source_map_valid or not inspection.status_snapshots_valid:
        findings.append(_high("artifacts.validators", "research_artifacts_valid", "bundle/source-map validator 未通过"))
    if not inspection.workbook_valid:
        findings.append(_high("workbook.invalid", "workbook_progress_valid", "research workbook validator 未通过"))
    if not inspection.progress_current:
        findings.append(_high("workbook.stale", "workbook_progress_valid", "research progress report stale"))
    if not inspection.progress_untampered:
        findings.append(_high("workbook.tampered", "workbook_progress_valid", "research progress report 被篡改"))
    if (
        not inspection.monitoring_valid
        or inspection.monitoring_execution_mode != "dry_run"
        or inspection.automated_execution_allowed
    ):
        findings.append(
            _high("monitoring.unsafe", "monitoring_safe", "monitoring 必须 validator-pass/dry_run/automation=false")
        )
    return findings


def _evaluate_acceptance_owned_outputs(payloads: tuple[JsonValue, ...]) -> list[Finding]:
    """只扫描验收自有输出，不读取或改写生产 artifact 原文。

    Args:
        payloads: phase receipt、acceptance receipt 或 baseline 等自有 JSON。

    Returns:
        secret/header/cookie/home-path findings。

    Raises:
        本函数不显式抛出异常。
    """

    return [
        _high(
            "sanitizer.sensitive_shape",
            "acceptance_outputs_sanitized",
            "验收自有输出命中 secret/header/cookie/绝对 home 路径",
            locator,
        )
        for index, payload in enumerate(payloads)
        for locator in _sensitive_strings(payload, f"acceptance-owned[{index}]")
    ]


def _evaluate_manual_review(
    contract: AcceptanceContract,
    review: QualityReview,
) -> tuple[list[Finding], bool]:
    """验证人工 rubric 完整性、计分闭包、阈值与三态。

    Args:
        contract: 100 分与分项阈值 contract。
        review: 完整或待填写的人工 rubric。

    Returns:
        人工复核 findings 与无错误 pending 标志。

    Raises:
        本函数不显式抛出异常。
    """

    pending = not review.is_complete
    findings, dimension_total, dimension_max_total = _evaluate_rubric_dimensions(contract, review)
    findings.extend(
        _evaluate_rubric_totals(
            contract,
            review,
            dimension_total=dimension_total,
            dimension_max_total=dimension_max_total,
        )
    )
    findings.extend(_evaluate_manual_finding_counts(review))
    findings.extend(
        _evaluate_manual_status(
            review,
            pending=pending,
            has_failures=bool(findings),
        )
    )
    findings.extend(_evaluate_reviewer_metadata(review))
    return findings, pending and not findings


def _evaluate_rubric_dimensions(
    contract: AcceptanceContract,
    review: QualityReview,
) -> tuple[list[Finding], int, int]:
    """验证各 rubric 维度的子项、上限与最低分。

    Args:
        contract: 评分阈值 contract。
        review: 人工质量复核。

    Returns:
        维度 findings、已评分合计与维度上限合计。

    Raises:
        本函数不显式抛出异常。
    """

    findings: list[Finding] = []
    dimension_total = 0
    dimension_max_total = 0
    for dimension in review.dimensions:
        item_scores = [item.score for item in dimension.items]
        item_max_total = sum(item.max_score for item in dimension.items)
        if item_max_total != dimension.max_score:
            findings.append(_high("rubric.dimension_max", "manual_review_passed", f"{dimension.name} max_score 不闭合"))
        if dimension.score is not None:
            if any(score is None for score in item_scores):
                findings.append(
                    _high("rubric.partial_dimension", "manual_review_passed", f"{dimension.name} 部分评分却声明维度分")
                )
            elif sum(score for score in item_scores if score is not None) != dimension.score:
                findings.append(
                    _high("rubric.dimension_score", "manual_review_passed", f"{dimension.name} 子项计分不闭合")
                )
            minimum = contract.score_contract.minimum_for(dimension.name)
            if minimum is None:
                findings.append(
                    _high("rubric.unknown_dimension", "manual_review_passed", f"未知评分维度 {dimension.name}")
                )
            elif dimension.score < minimum:
                findings.append(
                    _high("rubric.dimension_threshold", "manual_review_passed", f"{dimension.name} 低于最低分")
                )
            dimension_total += dimension.score
        dimension_max_total += dimension.max_score
    return findings, dimension_total, dimension_max_total


def _evaluate_rubric_totals(
    contract: AcceptanceContract,
    review: QualityReview,
    *,
    dimension_total: int,
    dimension_max_total: int,
) -> list[Finding]:
    """验证 rubric 总上限、总分合计与 85 分阈值。

    Args:
        contract: 评分阈值 contract。
        review: 人工质量复核。
        dimension_total: 已评分维度合计。
        dimension_max_total: 维度上限合计。

    Returns:
        总分闭包 findings。

    Raises:
        本函数不显式抛出异常。
    """

    findings: list[Finding] = []
    if dimension_max_total != contract.score_contract.total_points:
        findings.append(_high("rubric.total_max", "manual_review_passed", "rubric 总分上限不等于 contract 100 分"))
    if review.total_score is not None:
        if review.total_score != dimension_total:
            findings.append(_high("rubric.total_score", "manual_review_passed", "rubric total_score 与维度合计不闭合"))
        if review.total_score < contract.score_contract.minimum_total_score:
            findings.append(_high("rubric.total_threshold", "manual_review_passed", "rubric 总分低于 85 分阈值"))
    return findings


def _evaluate_manual_finding_counts(review: QualityReview) -> list[Finding]:
    """验证人工 findings 的计数与开放严重问题闭包。

    Args:
        review: 人工质量复核。

    Returns:
        finding_counts 与 open finding findings。

    Raises:
        本函数不显式抛出异常。
    """

    findings: list[Finding] = []
    actual_counts = {
        "high": sum(item.severity == "high" for item in review.findings),
        "medium": sum(item.severity == "medium" for item in review.findings),
        "low": sum(item.severity == "low" for item in review.findings),
    }
    if actual_counts != {
        "high": review.finding_counts.high,
        "medium": review.finding_counts.medium,
        "low": review.finding_counts.low,
    }:
        findings.append(_high("rubric.finding_counts", "manual_review_passed", "人工 finding_counts 不闭合"))
    if (
        any(item.status == "open" for item in review.findings)
        or review.finding_counts.high
        or review.finding_counts.medium
    ):
        findings.append(
            _high("rubric.open_findings", "manual_review_passed", "人工复核仍有 open 或 High/Medium finding")
        )
    return findings


def _evaluate_manual_status(
    review: QualityReview,
    *,
    pending: bool,
    has_failures: bool,
) -> list[Finding]:
    """验证三态人工 status 与 rubric 完整性和错误状态一致。

    Args:
        review: 人工质量复核。
        pending: rubric 是否尚未完成。
        has_failures: 前置人工 rubric 检查是否已有失败。

    Returns:
        status 不一致 findings。

    Raises:
        本函数不显式抛出异常。
    """

    if pending:
        if review.status != "PENDING_MANUAL_REVIEW":
            return [
                _high("rubric.pending_status", "manual_review_passed", "未完成 rubric 必须标为 PENDING_MANUAL_REVIEW")
            ]
    elif has_failures:
        if review.status != "FAIL":
            return [_high("rubric.fail_status", "manual_review_passed", "不达标的完整 rubric 必须标为 FAIL")]
    elif review.status != "PASS":
        return [_high("rubric.pass_status", "manual_review_passed", "完整达标 rubric 必须标为 PASS")]
    return []


def _evaluate_reviewer_metadata(review: QualityReview) -> list[Finding]:
    """验证 reviewer 稳定标签与 evidence paths 不含 PII/秘密形状。

    Args:
        review: 人工质量复核。

    Returns:
        reviewer PII findings。

    Raises:
        本函数不显式抛出异常。
    """

    reviewer_payload: JsonObject = {
        "reviewer_role": review.reviewer_role,
        "reviewer_id_label": review.reviewer_id_label,
        "evidence_paths": [
            path for dimension in review.dimensions for item in dimension.items for path in item.evidence_paths
        ],
    }
    if _sensitive_strings(reviewer_payload, "quality-review") or any(
        "@" in value for value in (review.reviewer_role, review.reviewer_id_label) if value is not None
    ):
        return [
            _high("rubric.reviewer_pii", "manual_review_passed", "reviewer 标签或 evidence path 含个人标识或敏感形状")
        ]
    return []


def _source_document_from_owner(
    *,
    document_id: str,
    source_kind: SourceKind,
    source_meta: JsonValue,
    processed_meta: JsonValue | None,
    primary_sha256: str,
) -> SourceDocument:
    """在单一 ingress 把 source/processed owner meta 收窄为 frozen dataclass。

    Args:
        document_id: 仓储文档 ID。
        source_kind: filing 或 material 来源枚举。
        source_meta: source repository 宽载荷。
        processed_meta: processed repository 宽载荷或缺失标记。
        primary_sha256: blob repository 读取字节的摘要。

    Returns:
        不再传播 owner 宽类型的源文档。

    Raises:
        ContractError: owner meta 字段、日期、类型或指纹非法时抛出。
    """

    source = _owner_mapping(source_meta, f"source_meta[{document_id}]")
    owner_document_id = _owner_optional_string(source, "document_id", f"source_meta[{document_id}]")
    if owner_document_id is not None and owner_document_id != document_id:
        raise ContractError(f"source meta document_id 不一致: {document_id}")
    filing_date = _owner_required_date(source, "filing_date", f"source_meta[{document_id}]")
    report_date = _owner_optional_date(source, "report_date", f"source_meta[{document_id}]") or filing_date
    if processed_meta is None:
        processed = ProcessedState(
            exists=False,
            parser_version="",
            quality="",
            reprocess_required=False,
            schema_version="",
            source_fingerprint="",
        )
    else:
        processed_owner = _owner_mapping(processed_meta, f"processed_meta[{document_id}]")
        processed = ProcessedState(
            exists=True,
            parser_version=_owner_required_string(processed_owner, "parser_version", f"processed_meta[{document_id}]"),
            quality=_owner_required_string(processed_owner, "quality", f"processed_meta[{document_id}]"),
            reprocess_required=_owner_required_bool(
                processed_owner, "reprocess_required", f"processed_meta[{document_id}]"
            ),
            schema_version=_owner_required_string(processed_owner, "schema_version", f"processed_meta[{document_id}]"),
            source_fingerprint=_owner_required_sha256(
                processed_owner, "source_fingerprint", f"processed_meta[{document_id}]"
            ),
        )
    form = _owner_required_string(source, "form_type", f"source_meta[{document_id}]")
    fiscal_year = _owner_optional_int(source, "fiscal_year", f"source_meta[{document_id}]")
    fiscal_period = _owner_optional_string(source, "fiscal_period", f"source_meta[{document_id}]")
    accession = _owner_optional_string(source, "accession_number", f"source_meta[{document_id}]")
    if accession is None and source_kind == SourceKind.FILING:
        accession = _owner_optional_string(source, "internal_document_id", f"source_meta[{document_id}]")
    return SourceDocument(
        document_id=document_id,
        source_kind="filing" if source_kind == SourceKind.FILING else "material",
        form=form,
        filing_date=filing_date,
        report_date=report_date,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        accession=accession,
        source_locator=f"{source_kind.value}:{document_id}",
        primary_file_sha256=primary_sha256,
        ingest_complete=_owner_required_bool(source, "ingest_complete", f"source_meta[{document_id}]"),
        processed=processed,
        processed_state_fingerprint=canonical_json_sha256(processed.to_json()),
    )


def _markdown_sections(report: str) -> tuple[tuple[str, str], ...]:
    """按二级 Markdown 标题切分报告。

    Args:
        report: 待分析 Markdown 报告。

    Returns:
        保持原顺序的标题/正文元组。

    Raises:
        本函数不显式抛出异常。
    """

    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []
    for line in report.splitlines():
        if line.startswith("## "):
            if current_heading:
                sections.append((current_heading, "\n".join(current_lines)))
            current_heading = line.removeprefix("## ").strip()
            current_lines = []
        elif current_heading:
            current_lines.append(line)
    if current_heading:
        sections.append((current_heading, "\n".join(current_lines)))
    return tuple(sections)


def _find_section(
    sections: tuple[tuple[str, str], ...],
    aliases: tuple[str, ...],
) -> tuple[str, str] | None:
    """按大小写不敏感的精确别名查找唯一二级章节。

    Args:
        sections: 已切分的二级章节。
        aliases: 标题允许精确等于的别名。

    Returns:
        唯一匹配章节；不存在或重复时返回 ``None``。

    Raises:
        本函数不显式抛出异常。
    """

    normalized = frozenset(alias.strip().casefold() for alias in aliases)
    matches = tuple((heading, body) for heading, body in sections if heading.strip().casefold() in normalized)
    if len(matches) != 1:
        return None
    return matches[0]


def _evidence_subsection(section_body: str) -> str | None:
    """提取一个实质章节的证据与出处三级小节。

    Args:
        section_body: 二级章节正文。

    Returns:
        证据小节正文；缺失或实质正文为空时返回 ``None``。

    Raises:
        本函数不显式抛出异常。
    """

    marker = f"### {_EVIDENCE_HEADING}"
    before, separator, after = section_body.partition(marker)
    if not separator or not before.strip():
        return None
    return after.split("### ", maxsplit=1)[0]


def _parse_evidence_lines(
    text: str,
    as_of_date: date,
) -> tuple[tuple[tuple[str, str, date, str], ...], tuple[str, ...]]:
    """解析并验证四段非空 evidence 行。

    Args:
        text: 证据小节或来源清单文本。
        as_of_date: 固定验收日期上界。

    Returns:
        合法 evidence 元组与质量错误文本元组。

    Raises:
        本函数把格式与日期错误收敛到返回值，不显式抛出异常。
    """

    entries: list[tuple[str, str, date, str]] = []
    errors: list[str] = []
    for line in text.splitlines():
        if not line.startswith("- "):
            continue
        parts = tuple(part.strip() for part in line.removeprefix("- ").split(" | "))
        if len(parts) != _EVIDENCE_PART_COUNT or any(not part for part in parts):
            errors.append("evidence 必须为 来源 | 类型/标识 | 日期 | 定位 四段非空")
            continue
        try:
            evidence_date = date.fromisoformat(parts[2])
        except ValueError:
            errors.append("evidence 日期必须是 YYYY-MM-DD")
            continue
        if evidence_date > as_of_date:
            errors.append("evidence 日期晚于 as-of")
        if parts[3].strip().lower() in _TEMPLATE_LOCATORS or len(parts[3].strip()) < _MIN_EVIDENCE_LOCATOR_LENGTH:
            errors.append("evidence 定位不得是模板化占位")
        entries.append((parts[0], parts[1], evidence_date, parts[3]))
    return tuple(entries), tuple(errors)


def _strict_reference_price(payload: JsonValue) -> tuple[Decimal, str, date, str]:
    """严格解析报告唯一估值参考价格。

    Args:
        payload: 未信任 valuation reference JSON。

    Returns:
        精确 Decimal 价格、币种、market date 与 material ID。

    Raises:
        ContractError: schema、价格、币种、日期或 material ID 非法时抛出。
    """

    if not isinstance(payload, dict):
        raise ContractError("valuation_reference_price 必须是对象")
    expected = {"price", "currency", "market_date", "material_document_id"}
    if set(payload) != expected:
        raise ContractError("valuation_reference_price schema 不闭合")
    price_raw = payload["price"]
    if not isinstance(price_raw, str):
        raise ContractError("valuation_reference_price.price 必须是精确十进制字符串")
    try:
        price = Decimal(price_raw)
    except InvalidOperation as exc:
        raise ContractError("valuation_reference_price.price 非法") from exc
    if not price.is_finite() or price <= 0:
        raise ContractError("valuation_reference_price.price 必须是正有限数")
    currency = payload["currency"]
    market_date_raw = payload["market_date"]
    material_id = payload["material_document_id"]
    if not isinstance(currency, str) or not currency.strip():
        raise ContractError("valuation_reference_price.currency 必须非空")
    if not isinstance(market_date_raw, str):
        raise ContractError("valuation_reference_price.market_date 必须是字符串")
    if not isinstance(material_id, str) or not material_id.strip():
        raise ContractError("valuation_reference_price.material_document_id 必须非空")
    try:
        market_date = date.fromisoformat(market_date_raw)
    except ValueError as exc:
        raise ContractError("valuation_reference_price.market_date 非法") from exc
    return price, currency, market_date, material_id


def _gate_statuses(
    hard_gates: tuple[str, ...],
    findings: tuple[Finding, ...],
    *,
    manual_pending: bool,
) -> tuple[tuple[str, GateStatus], ...]:
    """把 findings 与人工 pending 聚合为每个 hard gate 状态。

    Args:
        hard_gates: contract 固定 hard gate 顺序。
        findings: 已排序 findings。
        manual_pending: 人工 rubric 是否仅等待填写。

    Returns:
        每个 hard gate 的 passed/pending/failed 状态。

    Raises:
        本函数不显式抛出异常。
    """

    rows: list[tuple[str, GateStatus]] = []
    for gate in hard_gates:
        if any(item.gate == gate for item in findings):
            status: GateStatus = "failed"
        elif gate == "manual_review_passed" and manual_pending:
            status = "pending"
        else:
            status = "passed"
        rows.append((gate, status))
    return tuple(rows)


def _build_residuals(inputs: AcceptanceInputs) -> tuple[str, ...]:
    """生成不含绝对路径的 monitoring/workbook residual。

    Args:
        inputs: 完整 evaluator 输入。

    Returns:
        按文本排序的 residual 元组。

    Raises:
        本函数不显式抛出异常。
    """

    inspection = inputs.research_artifacts
    residuals = [
        f"workbook_completion_status={inspection.workbook_completion_status}",
        f"workbook_open_item_count={inspection.workbook_open_item_count}",
        f"monitoring_readiness={inspection.monitoring_readiness}",
        f"monitoring_blocked_task_count={inspection.monitoring_blocked_task_count}",
    ]
    residuals.extend(f"monitoring_unbound_source={source}" for source in inspection.monitoring_unbound_sources)
    if not any(document.source_kind == "filing" and document.form == "8-K" for document in inputs.inventory.documents):
        residuals.append("optional_8k_absent")
    residuals.append("user_workspace_custom_templates_not_part_of_acceptance")
    return tuple(sorted(residuals))


def _sensitive_strings(payload: JsonValue, locator: str) -> tuple[str, ...]:
    """递归定位验收自有 JSON 中的敏感 key/value 形状。

    Args:
        payload: 仅限 acceptance-owned 的严格 JSON 值。
        locator: 当前 JSON 路径标签。

    Returns:
        命中敏感形状的 JSON locator 元组。

    Raises:
        本函数不显式抛出异常。
    """

    matches: list[str] = []
    if isinstance(payload, str):
        if any(pattern.search(payload) for pattern in (*_SECRET_PATTERNS, *_HOME_PATH_PATTERNS)):
            matches.append(locator)
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            matches.extend(_sensitive_strings(item, f"{locator}[{index}]"))
    elif isinstance(payload, dict):
        for key, item in payload.items():
            child = f"{locator}.{key}"
            if key.strip().lower() in _SENSITIVE_KEYS:
                matches.append(child)
            matches.extend(_sensitive_strings(item, child))
    return tuple(matches)


def _narrow_owner_result(payload: bytes, label: str) -> JsonObject:
    """把 owner validator 宽返回在单一边界收窄为严格 JSON 对象。

    Args:
        payload: owner 结果序列化后的 JSON 字节。
        label: 错误上下文标签。

    Returns:
        严格 JSON 顶层对象。

    Raises:
        ContractError: JSON 非法或顶层不是对象时抛出。
    """

    parsed = parse_json_bytes(payload, label=label)
    if not isinstance(parsed, dict):
        raise ContractError(f"{label} 顶层必须是对象")
    return parsed


def _owner_ok(payload: JsonObject, label: str) -> bool:
    """读取 owner validator 的 ok 布尔值。

    Args:
        payload: 已收窄 owner validation 对象。
        label: 错误上下文标签。

    Returns:
        精确 ``ok`` 布尔值。

    Raises:
        ContractError: ``ok`` 缺失或不是 bool 时抛出。
    """

    return _owner_bool(payload, "ok", label)


def _owner_nested_mapping(payload: JsonObject, key: str, label: str) -> JsonObject:
    """读取 owner 返回中的嵌套对象。

    Args:
        payload: 已收窄 owner JSON 对象。
        key: 嵌套字段名。
        label: 错误上下文标签。

    Returns:
        嵌套 JSON 对象。

    Raises:
        ContractError: 字段缺失或不是对象时抛出。
    """

    value = payload.get(key)
    if not isinstance(value, dict):
        raise ContractError(f"{label}.{key} 必须是对象")
    return value


def _owner_mapping(payload: JsonValue, label: str) -> JsonObject:
    """在 repository ingress 收窄 owner meta 对象。

    Args:
        payload: repository 返回宽载荷。
        label: 错误上下文标签。

    Returns:
        严格 JSON 对象。

    Raises:
        ContractError: 顶层不是对象时抛出。
    """

    if not isinstance(payload, dict):
        raise ContractError(f"{label} 必须是对象")
    return payload


def _owner_bool(payload: JsonObject, key: str, label: str) -> bool:
    """读取 owner 布尔字段并拒绝 truthiness 兼容。

    Args:
        payload: 已收窄 owner JSON 对象。
        key: 字段名。
        label: 错误上下文标签。

    Returns:
        精确布尔值。

    Raises:
        ContractError: 字段缺失或不是 bool 时抛出。
    """

    value = payload.get(key)
    if not isinstance(value, bool):
        raise ContractError(f"{label}.{key} 必须是 bool")
    return value


def _owner_required_bool(payload: JsonObject, key: str, label: str) -> bool:
    """读取 repository meta 必填布尔字段。

    Args:
        payload: 已收窄 repository meta。
        key: 必填字段名。
        label: 错误上下文标签。

    Returns:
        精确布尔值。

    Raises:
        ContractError: 字段缺失或不是 bool 时抛出。
    """

    if key not in payload:
        raise ContractError(f"{label} 缺少 {key}")
    return _owner_bool(payload, key, label)


def _owner_string(payload: JsonObject, key: str, label: str) -> str:
    """读取 owner 必填非空字符串。

    Args:
        payload: 已收窄 owner JSON 对象。
        key: 字段名。
        label: 错误上下文标签。

    Returns:
        去空白后的非空字符串。

    Raises:
        ContractError: 字段缺失、不是字符串或为空时抛出。
    """

    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label}.{key} 必须是非空字符串")
    return value.strip()


def _owner_required_string(payload: JsonObject, key: str, label: str) -> str:
    """读取 repository meta 必填非空字符串。

    Args:
        payload: 已收窄 repository meta。
        key: 必填字段名。
        label: 错误上下文标签。

    Returns:
        去空白后的非空字符串。

    Raises:
        ContractError: 字段缺失、不是字符串或为空时抛出。
    """

    if key not in payload:
        raise ContractError(f"{label} 缺少 {key}")
    return _owner_string(payload, key, label)


def _owner_optional_string(payload: JsonObject, key: str, label: str) -> str | None:
    """读取 repository meta 可选非空字符串。

    Args:
        payload: 已收窄 repository meta。
        key: 可选字段名。
        label: 错误上下文标签。

    Returns:
        非空字符串或 ``None``。

    Raises:
        ContractError: 非空值不是字符串或为空时抛出。
    """

    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label}.{key} 必须是非空字符串或 null")
    return value.strip()


def _owner_nonnegative_int(payload: JsonObject, key: str, label: str) -> int:
    """读取 owner 非负整数并拒绝 bool-as-int。

    Args:
        payload: 已收窄 owner JSON 对象。
        key: 字段名。
        label: 错误上下文标签。

    Returns:
        非负整数。

    Raises:
        ContractError: 字段缺失、非整数、为 bool 或小于零时抛出。
    """

    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{label}.{key} 必须是非负整数")
    return value


def _owner_optional_int(payload: JsonObject, key: str, label: str) -> int | None:
    """读取 repository meta 可选整数并拒绝 bool-as-int。

    Args:
        payload: 已收窄 repository meta。
        key: 可选字段名。
        label: 错误上下文标签。

    Returns:
        整数或 ``None``。

    Raises:
        ContractError: 非空值不是整数或是 bool 时抛出。
    """

    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{label}.{key} 必须是整数或 null")
    return value


def _owner_required_sha256(payload: JsonObject, key: str, label: str) -> str:
    """读取 repository meta 必填 SHA-256。

    Args:
        payload: 已收窄 repository meta。
        key: 必填字段名。
        label: 错误上下文标签。

    Returns:
        64 位小写十六进制摘要。

    Raises:
        ContractError: 字段缺失或摘要非法时抛出。
    """

    value = _owner_required_string(payload, key, label)
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ContractError(f"{label}.{key} 必须是小写 SHA-256")
    return value


def _owner_required_date(payload: JsonObject, key: str, label: str) -> date:
    """读取 repository meta 必填 ISO 日期。

    Args:
        payload: 已收窄 repository meta。
        key: 必填字段名。
        label: 错误上下文标签。

    Returns:
        ISO 日期。

    Raises:
        ContractError: 字段缺失或日期格式非法时抛出。
    """

    value = _owner_required_string(payload, key, label)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{label}.{key} 必须是 YYYY-MM-DD") from exc


def _owner_optional_date(payload: JsonObject, key: str, label: str) -> date | None:
    """读取 repository meta 可选 ISO 日期。

    Args:
        payload: 已收窄 repository meta。
        key: 可选字段名。
        label: 错误上下文标签。

    Returns:
        ISO 日期或 ``None``。

    Raises:
        ContractError: 非空值不是合法 ISO 日期时抛出。
    """

    value = _owner_optional_string(payload, key, label)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{label}.{key} 必须是 YYYY-MM-DD 或 null") from exc


def _workbook_completion(payload: JsonObject) -> tuple[str, int]:
    """读取 workbook summary 的真实 completion/open count。

    Args:
        payload: 严格 research workbook JSON。

    Returns:
        completion status 与 open item count。

    Raises:
        ContractError: summary、状态或 open count 非法时抛出。
    """

    summary = _owner_nested_mapping(payload, "summary", "research workbook")
    completion = _owner_string(payload, "completion_status", "research workbook")
    open_count = _owner_nonnegative_int(summary, "open_item_count", "research workbook.summary")
    return completion, open_count


def _status_snapshots_valid(payloads: dict[str, JsonObject]) -> bool:
    """验证三个派生状态快照与当前 13 产物健康状态一致。

    Args:
        payloads: 已通过 strict JSON ingress 的 artifact 对象。

    Returns:
        monitoring/workbook/report 三个 snapshot 均健康时返回 ``True``。

    Raises:
        ContractError: snapshot JSON 或必需 summary 字段类型非法时抛出。
        本函数不显式抛出其它异常。
    """

    monitoring = payloads["monitoring-status.json"]
    workbook = payloads["research-workbook-status.json"]
    report = payloads["research-workbook-report-status.json"]
    monitoring_summary = _owner_nested_mapping(monitoring, "summary", "monitoring status")
    workbook_summary = _owner_nested_mapping(workbook, "summary", "workbook status")
    report_summary = _owner_nested_mapping(report, "summary", "workbook report status")
    monitoring_ok = (
        _owner_string(monitoring, "overall_status", "monitoring status") in {"blocked", "ready_for_review"}
        and _owner_nonnegative_int(monitoring_summary, "invalid_plan_count", "monitoring status.summary") == 0
        and _owner_nonnegative_int(monitoring_summary, "valid_plan_count", "monitoring status.summary") >= 1
    )
    workbook_ok = (
        _owner_string(workbook, "overall_status", "workbook status") in {"not_started", "in_progress", "complete"}
        and _owner_nonnegative_int(workbook_summary, "invalid_workbook_count", "workbook status.summary") == 0
        and _owner_nonnegative_int(workbook_summary, "valid_workbook_count", "workbook status.summary") >= 1
    )
    report_ok = (
        _owner_string(report, "overall_status", "workbook report status") == "current"
        and _owner_nonnegative_int(report_summary, "invalid_report_count", "workbook report status.summary") == 0
        and _owner_nonnegative_int(report_summary, "stale_report_count", "workbook report status.summary") == 0
        and _owner_nonnegative_int(report_summary, "tampered_report_count", "workbook report status.summary") == 0
    )
    return monitoring_ok and workbook_ok and report_ok


def _monitoring_unbound_sources(payload: JsonObject) -> tuple[str, ...]:
    """从 monitoring tasks 提取未绑定 candidate source residual。

    Args:
        payload: 严格 monitoring plan JSON。

    Returns:
        排序去重后的未绑定 source 名称。

    Raises:
        ContractError: tasks、状态或 source 数组非法时抛出。
    """

    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise ContractError("monitoring plan.tasks 必须是数组")
    unbound: set[str] = set()
    for index, task_value in enumerate(tasks):
        if not isinstance(task_value, dict):
            raise ContractError(f"monitoring plan.tasks[{index}] 必须是对象")
        status = _owner_string(task_value, "status", f"monitoring plan.tasks[{index}]")
        candidates = task_value.get("data_source_candidates")
        bound = task_value.get("bound_data_sources")
        if not isinstance(candidates, list) or not isinstance(bound, list):
            raise ContractError(f"monitoring plan.tasks[{index}] source lists 必须是数组")
        candidate_names = _strict_string_list(candidates, f"monitoring plan.tasks[{index}].data_source_candidates")
        bound_names = set(_strict_string_list(bound, f"monitoring plan.tasks[{index}].bound_data_sources"))
        if status == "blocked_unbound_sources":
            unbound.update(name for name in candidate_names if name not in bound_names)
    return tuple(sorted(unbound))


def _strict_string_list(payload: list[JsonValue], label: str) -> tuple[str, ...]:
    """收窄 owner 返回的字符串数组。

    Args:
        payload: 已确认是数组的 owner JSON 值。
        label: 错误上下文标签。

    Returns:
        非空字符串元组。

    Raises:
        ContractError: 任一元素不是非空字符串时抛出。
    """

    values: list[str] = []
    for index, item in enumerate(payload):
        if not isinstance(item, str) or not item.strip():
            raise ContractError(f"{label}[{index}] 必须是非空字符串")
        values.append(item.strip())
    return tuple(values)


def _expected_hash_pairs(pairs: tuple[tuple[str, str], ...]) -> dict[str, str]:
    """验证 artifact 绑定摘要列表并转为唯一映射。

    Args:
        pairs: artifact 文件名与已绑定 SHA-256 元组。

    Returns:
        唯一 locator 到摘要的映射。

    Raises:
        ContractError: locator、SHA-256 非法或 locator 重复时抛出。
    """

    result: dict[str, str] = {}
    for locator, digest in pairs:
        if not _is_safe_artifact_name(locator):
            raise ContractError(f"expected artifact locator 非法: {locator}")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ContractError(f"expected artifact SHA-256 非法: {locator}")
        if locator in result:
            raise ContractError(f"expected artifact locator 重复: {locator}")
        result[locator] = digest
    return result


def _is_safe_artifact_name(name: str) -> bool:
    """判断 locator 是否为单层安全文件名。

    Args:
        name: 待验证 artifact locator。

    Returns:
        locator 非空、相对、单层且无反斜线/``..`` 时返回 ``True``。

    Raises:
        本函数不显式抛出异常。
    """

    pure = PurePosixPath(name)
    return bool(
        name and not pure.is_absolute() and len(pure.parts) == 1 and ".." not in pure.parts and "\\" not in name
    )


def _require_bounded_directory(path: Path, label: str) -> Path:
    """验证只读输入根是现存非 symlink 目录。

    Args:
        path: 待验证目录。
        label: 错误上下文标签。

    Returns:
        解析后的绝对目录路径。

    Raises:
        ContractError: 路径缺失、不是目录或为 symlink 时抛出。
    """

    if path.is_symlink() or not path.is_dir():
        raise ContractError(f"{label} 必须是现存非 symlink 目录")
    return path.resolve()


def _bounded_file(root: Path, name: str, label: str) -> Path:
    """解析一个不得越过已验证 root 的普通文件。

    Args:
        root: 已验证精确根目录。
        name: 单层文件名。
        label: 错误上下文标签。

    Returns:
        root 内普通非 symlink 文件路径。

    Raises:
        ContractError: locator 非法、文件缺失、为 symlink 或越界时抛出。
    """

    if not _is_safe_artifact_name(name):
        raise ContractError(f"{label} locator 非法")
    candidate = root / name
    if candidate.is_symlink() or not candidate.is_file() or candidate.resolve().parent != root:
        raise ContractError(f"{label} 必须是 root 内普通非 symlink 文件")
    return candidate


def _positive_runtime_int(value: int, label: str) -> int:
    """验证 runtime 正整数并拒绝 bool-as-int。

    Args:
        value: 待验证 runtime 整数。
        label: 错误上下文标签。

    Returns:
        原正整数。

    Raises:
        ContractError: 值为 bool 或不大于零时抛出。
    """

    if isinstance(value, bool) or value <= 0:
        raise ContractError(f"{label} 必须是正整数")
    return value


def _nonnegative_runtime_float(value: float, label: str) -> float:
    """验证 runtime 非负有限数并拒绝 bool-as-int。

    Args:
        value: 待验证 runtime 数值。
        label: 错误上下文标签。

    Returns:
        原非负有限数。

    Raises:
        ContractError: 值为 bool、非有限或小于零时抛出。
    """

    if isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ContractError(f"{label} 必须是非负有限数")
    return value


def _subtract_calendar_years(value: date, years: int) -> date:
    """按日历年回退日期，并把闰日 clamp 到二月末。

    Args:
        value: 原日期。
        years: 需要回退的完整日历年数。

    Returns:
        回退后的日期；闰日目标年无二月二十九日时返回二月二十八日。

    Raises:
        本函数只收敛闰日 ``ValueError``，不显式抛出异常。
    """

    target_year = value.year - years
    try:
        return value.replace(year=target_year)
    except ValueError:
        return value.replace(year=target_year, day=28)


def _high(code: str, gate: str, message: str, locator: str | None = None) -> Finding:
    """构造一个 deterministic hard-gate finding。

    Args:
        code: 稳定 finding code。
        gate: 对应 hard gate 名称。
        message: 脱敏说明。
        locator: 可选相对输入定位。

    Returns:
        high severity finding。

    Raises:
        本函数不显式抛出异常。
    """

    return Finding(code=code, gate=gate, severity="high", message=message, locator=locator)


def _safe_contract_message(exc: ContractError) -> str:
    """把 contract 异常压缩为不含换行的安全摘要。

    Args:
        exc: 已知 contract 异常。

    Returns:
        最长 240 字符的单行错误摘要。

    Raises:
        本函数不显式抛出异常。
    """

    return str(exc).replace("\n", " ")[:240]


__all__ = [
    "AcceptanceInputs",
    "ArtifactReference",
    "EvaluationResult",
    "Finding",
    "ResearchArtifactInspection",
    "RuntimeEvidence",
    "build_source_inventory_from_repositories",
    "evaluate_acceptance",
    "inspect_research_artifacts",
    "load_fixture_inputs",
]
