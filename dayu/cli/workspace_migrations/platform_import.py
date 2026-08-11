"""旧 workspace 显式导入的文件系统 staging adapter（S15-CTRL-07）。

``stage_workspace_import(...)`` 是文件系统 adapter，在任何 DB
engine/session 创建前完成 read-only staging：

1. canonicalize source root，要求 existing real directory；manifest 与
   全部引用路径必须 contained、regular、非 symlink/FIFO/device；
2. 只通过
   ``FsCompanyMetaRepository(source_root, create_directories=False)``
   的 ``scan_company_meta_inventory()`` 读取 ``portfolio/<ticker>/meta.json``，
   禁止自拼/读取 Fins private layout；任何 ``missing_meta`` /
   ``invalid_meta`` fail closed，hidden directory 忽略；available
   inventory 与 manifest company 必须双向 exact-set；
3. 只通过以 ``create_directories=False`` 构造的
   ``FsSourceDocumentRepository.has_source_storage_root()`` 判断 source
   roots presence，派生全局稳定 source definitions；不枚举、读取、
   hash、复制任何 source/processed document、manifest 或 blob bytes；
4. 只消费 bundle owner 的 typed closure result
   （``inspect_research_template_bundle_closure``）并 cross-check
   manifest ``template_name``、canonical ticker、``CompanyMeta.company_name``
   与 owner result exact；adapter 不得自行重读 descriptor；
5. ``source_root_fingerprint`` / ``staged_payload_sha256`` 由 pure
   domain 计算；任何 staging 错误后 DB connect count 必须为 0。

本模块只 import ``dayu.fins.storage`` 的 public read-only repositories
与 bundle owner 的 typed API，不 import Fins internal/write API。
"""

from __future__ import annotations

import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, TypeAlias
from uuid import UUID

from dayu.fins.domain.document_models import (
    CompanyMeta,
    CompanyMetaInventoryEntry,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage import (
    FsCompanyMetaRepository,
    FsSourceDocumentRepository,
)
from dayu.cli.commands._research_template_bundle import (
    ResearchBundleClosureError,
    ResearchBundleClosureInspection,
    inspect_research_template_bundle_closure,
)
from dayu.investment.domain.identifiers import TenantId
from dayu.investment.domain.source import SecurityType, SourceKind as InvestmentSourceKind
from dayu.investment.domain.workspace_import import (
    FingerprintBundleClosure,
    FingerprintClosureFile,
    FingerprintCompanyProjection,
    FingerprintSourceRootPresence,
    LEGACY_FINS_FILING_SOURCE_KEY,
    LEGACY_FINS_MATERIAL_SOURCE_KEY,
    LegacyBundleReference,
    VerifiedLegacyCompany,
    VerifiedLegacySourceDefinition,
    VerifiedResearchBundleLocator,
    WORKSPACE_IMPORT_MIGRATION_ID,
    WORKSPACE_IMPORT_SCHEMA_VERSION,
    WorkspaceImportIdentityInconsistentError,
    WorkspaceImportManifestInvalidError,
    WorkspaceImportOwnerInvalidError,
    WorkspaceImportRequest,
    WorkspaceImportUsageError,
    build_verified_bundle_locator,
    build_verified_company,
    build_verified_source_definition,
    build_workspace_import_request,
    classify_canonical_ticker,
)

ManifestJsonScalar: TypeAlias = str | int | float | bool | None
ManifestJsonValue: TypeAlias = (
    ManifestJsonScalar | list["ManifestJsonValue"] | dict[str, "ManifestJsonValue"]
)
ManifestJsonObject: TypeAlias = dict[str, ManifestJsonValue]
"""strict manifest JSON 递归类型（adapter 边界收窄用）。"""

_COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")


def _reject_duplicate_keys(pairs: list[tuple[str, ManifestJsonValue]]) -> ManifestJsonObject:
    """``json.loads`` 的 ``object_pairs_hook``：拒绝重复 JSON key。

    Args:
        pairs: JSON 对象键值对序列。

    Returns:
        校验通过的字典。

    Raises:
        WorkspaceImportManifestInvalidError: 存在重复 key 时抛出。
    """

    result: ManifestJsonObject = {}
    for key, value in pairs:
        if key in result:
            raise WorkspaceImportManifestInvalidError()
        result[key] = value
    return result


def _reject_nonfinite(_token: str) -> NoReturn:
    """``json.loads`` 的 ``parse_constant``：拒绝 NaN/Infinity。

    Args:
        _token: JSON 常量 token（不使用）。

    Returns:
        永不返回。

    Raises:
        WorkspaceImportManifestInvalidError: 恒抛。
    """

    raise WorkspaceImportManifestInvalidError()


@dataclass(frozen=True, slots=True)
class _ManifestSecurity:
    """strict manifest 中单个证券映射的已收窄原始值。

    Args:
        ticker: 原始 ticker 字符串。
        exchange_mic: 原始 MIC 字符串。
        security_type: 原始证券类型字符串。
        currency: 原始货币字符串。
        isin: 可空 ISIN。
        is_active: 活跃标记。
    """

    ticker: str
    exchange_mic: str
    security_type: str
    currency: str
    isin: str | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class _ManifestBundle:
    """strict manifest 中单个 bundle 引用的已收窄原始值。

    Args:
        template_name: 模板名。
        relative_locator: POSIX relative locator。
    """

    template_name: str
    relative_locator: str


@dataclass(frozen=True, slots=True)
class _ManifestCompany:
    """strict manifest 中单个公司的已收窄原始值。

    Args:
        legacy_company_id: raw legacy company id。
        country_code: 可空国家码。
        lei: 可空 LEI。
        security: 证券映射。
        bundles: bundle 引用 tuple。
    """

    legacy_company_id: str
    country_code: str | None
    lei: str | None
    security: _ManifestSecurity
    bundles: tuple[_ManifestBundle, ...]


def _require_string(value: ManifestJsonValue, label: str) -> str:
    """把 manifest 值收窄为非空字符串。

    Args:
        value: 待校验的值。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的字符串。

    Raises:
        WorkspaceImportManifestInvalidError: 值不是字符串或为空/仅
            空白时抛出。
    """

    if not isinstance(value, str) or not value or value != value.strip():
        raise WorkspaceImportManifestInvalidError()
    return value


def _require_optional_string(value: ManifestJsonValue, label: str) -> str | None:
    """把 manifest 值收窄为可空非空字符串。

    Args:
        value: 待校验的值。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的字符串或 ``None``。

    Raises:
        WorkspaceImportManifestInvalidError: 值非法时抛出。
    """

    if value is None:
        return None
    return _require_string(value, label)


def _require_int(value: ManifestJsonValue, label: str) -> int:
    """把 manifest 值收窄为精确 ``int``（拒绝 bool 冒充）。

    Args:
        value: 待校验的值。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的整数。

    Raises:
        WorkspaceImportManifestInvalidError: 值不是精确 ``int`` 时抛出。
    """

    if type(value) is not int:
        raise WorkspaceImportManifestInvalidError()
    return value


def _require_bool(value: ManifestJsonValue, label: str) -> bool:
    """把 manifest 值收窄为精确 ``bool``。

    Args:
        value: 待校验的值。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的布尔值。

    Raises:
        WorkspaceImportManifestInvalidError: 值不是精确 ``bool`` 时抛出。
    """

    if type(value) is not bool:
        raise WorkspaceImportManifestInvalidError()
    return value


def _require_mapping(value: ManifestJsonValue, label: str) -> ManifestJsonObject:
    """把 manifest 值收窄为对象。

    Args:
        value: 待校验的值。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的字典。

    Raises:
        WorkspaceImportManifestInvalidError: 值不是对象时抛出。
    """

    if not isinstance(value, dict):
        raise WorkspaceImportManifestInvalidError()
    return value


def _require_list(value: ManifestJsonValue, label: str) -> list[ManifestJsonValue]:
    """把 manifest 值收窄为列表。

    Args:
        value: 待校验的值。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的列表。

    Raises:
        WorkspaceImportManifestInvalidError: 值不是列表时抛出。
    """

    if not isinstance(value, list):
        raise WorkspaceImportManifestInvalidError()
    return value


def _require_exact_keys(mapping: ManifestJsonObject, expected: frozenset[str]) -> None:
    """要求对象 key 集合与期望集合精确相等（拒绝 missing/extra key）。

    Args:
        mapping: 待校验的对象。
        expected: 期望的 key 集合。

    Returns:
        无。

    Raises:
        WorkspaceImportManifestInvalidError: key 集合不一致时抛出。
    """

    if set(mapping) != expected:
        raise WorkspaceImportManifestInvalidError()


def _parse_manifest_payload(payload: ManifestJsonObject) -> tuple[_ManifestCompany, ...]:
    """解析并严格校验 operator manifest 结构。

    Args:
        payload: 已解码的 manifest 对象。

    Returns:
        已收窄的公司原始值 tuple。

    Raises:
        WorkspaceImportManifestInvalidError: 结构违反 strict schema 时
            抛出。
    """

    _require_exact_keys(
        payload,
        frozenset({"schema_version", "migration_id", "companies"}),
    )
    schema_version = _require_int(payload["schema_version"], "schema_version")
    if schema_version != WORKSPACE_IMPORT_SCHEMA_VERSION:
        raise WorkspaceImportManifestInvalidError()
    migration_id = _require_string(payload["migration_id"], "migration_id")
    if migration_id != WORKSPACE_IMPORT_MIGRATION_ID:
        raise WorkspaceImportManifestInvalidError()
    companies_raw = _require_list(payload["companies"], "companies")
    companies: list[_ManifestCompany] = []
    seen_company_ids: set[str] = set()
    for company_raw in companies_raw:
        company = _require_mapping(company_raw, "company")
        _require_exact_keys(
            company,
            frozenset({"legacy_company_id", "country_code", "lei", "security", "bundles"}),
        )
        legacy_company_id = _require_string(company["legacy_company_id"], "legacy_company_id")
        if legacy_company_id in seen_company_ids:
            raise WorkspaceImportManifestInvalidError()
        seen_company_ids.add(legacy_company_id)
        country_code = _require_optional_string(company["country_code"], "country_code")
        if country_code is not None and _COUNTRY_CODE_PATTERN.fullmatch(country_code) is None:
            raise WorkspaceImportManifestInvalidError()
        lei = _require_optional_string(company["lei"], "lei")
        security = _parse_manifest_security(
            _require_mapping(company["security"], "security")
        )
        bundles = _parse_manifest_bundles(
            _require_list(company["bundles"], "bundles")
        )
        companies.append(
            _ManifestCompany(
                legacy_company_id=legacy_company_id,
                country_code=country_code,
                lei=lei,
                security=security,
                bundles=bundles,
            )
        )
    return tuple(companies)


def _parse_manifest_security(security_raw: ManifestJsonObject) -> _ManifestSecurity:
    """解析并严格校验 manifest 中的单一证券映射。

    Args:
        security_raw: 已收窄的 security 对象。

    Returns:
        已收窄的证券原始值。

    Raises:
        WorkspaceImportManifestInvalidError: 结构违反 strict schema 时
            抛出。
    """

    _require_exact_keys(
        security_raw,
        frozenset(
            {"ticker", "exchange_mic", "security_type", "currency", "isin", "is_active"}
        ),
    )
    ticker = _require_string(security_raw["ticker"], "ticker")
    exchange_mic = _require_string(security_raw["exchange_mic"], "exchange_mic")
    security_type = _require_string(security_raw["security_type"], "security_type")
    currency = _require_string(security_raw["currency"], "currency")
    isin = _require_optional_string(security_raw["isin"], "isin")
    is_active = _require_bool(security_raw["is_active"], "is_active")
    return _ManifestSecurity(
        ticker=ticker,
        exchange_mic=exchange_mic,
        security_type=security_type,
        currency=currency,
        isin=isin,
        is_active=is_active,
    )


def _parse_manifest_bundles(bundles_raw: list[ManifestJsonValue]) -> tuple[_ManifestBundle, ...]:
    """解析并严格校验 manifest 中的 bundle 引用列表。

    Args:
        bundles_raw: 已收窄的 bundles 列表。

    Returns:
        已收窄的 bundle 引用 tuple。

    Raises:
        WorkspaceImportManifestInvalidError: 结构违反 strict schema 或
            存在重复 template_name 时抛出。
    """

    bundles: list[_ManifestBundle] = []
    seen_templates: set[str] = set()
    for bundle_raw in bundles_raw:
        bundle = _require_mapping(bundle_raw, "bundle")
        _require_exact_keys(bundle, frozenset({"template_name", "relative_locator"}))
        template_name = _require_string(bundle["template_name"], "template_name")
        if template_name in seen_templates:
            raise WorkspaceImportManifestInvalidError()
        seen_templates.add(template_name)
        relative_locator = _require_string(bundle["relative_locator"], "relative_locator")
        _validate_relative_locator(relative_locator)
        bundles.append(
            _ManifestBundle(
                template_name=template_name,
                relative_locator=relative_locator,
            )
        )
    return tuple(bundles)


def _validate_relative_locator(value: str) -> None:
    """校验 POSIX relative locator 形态。

    Args:
        value: 待校验的 locator。

    Returns:
        无。

    Raises:
        WorkspaceImportManifestInvalidError: locator 不是 POSIX relative
            形态时抛出。
    """

    if (
        value.startswith("/")
        or "\\" in value
        or ".." in value.split("/")
        or not value
    ):
        raise WorkspaceImportManifestInvalidError()


def _require_global_identity_uniqueness(
    manifest_companies: tuple[_ManifestCompany, ...],
) -> None:
    """跨 company 建立全局 canonical security/bundle identity 去重。

    在 owner identity cross-check 完成后、任何数据库依赖创建前执行：
    不同 legacy company 不得声明相同 canonical security
    （``exchange_mic+ticker``）、相同 bundle identity
    （``exchange_mic+ticker+template_name``）或相同 repository
    relative locator；重复一律作为 manifest/identity 输入失败收敛，
    禁止延后到 repository drift。

    Args:
        manifest_companies: 已完成收窄的 manifest 公司原始值。

    Returns:
        无。

    Raises:
        WorkspaceImportIdentityInconsistentError: 跨 company 出现重复
            canonical security / bundle identity / relative locator 时
            抛出。
    """

    security_keys: set[tuple[str, str]] = set()
    bundle_keys: set[tuple[str, str, str]] = set()
    locator_keys: set[str] = set()
    for company in manifest_companies:
        security_key = (company.security.exchange_mic, company.security.ticker)
        if security_key in security_keys:
            raise WorkspaceImportIdentityInconsistentError()
        security_keys.add(security_key)
        for bundle in company.bundles:
            bundle_key = (security_key[0], security_key[1], bundle.template_name)
            if bundle_key in bundle_keys:
                raise WorkspaceImportIdentityInconsistentError()
            bundle_keys.add(bundle_key)
            if bundle.relative_locator in locator_keys:
                raise WorkspaceImportIdentityInconsistentError()
            locator_keys.add(bundle.relative_locator)


def _load_strict_manifest(manifest_path: Path) -> tuple[_ManifestCompany, ...]:
    """读取并严格解析 manifest 文件。

    Args:
        manifest_path: 已 resolve 的 manifest 路径。

    Returns:
        已收窄的公司原始值 tuple。

    Raises:
        WorkspaceImportManifestInvalidError: 文件读取/JSON 解析/strict
            schema 违反时抛出。
    """

    try:
        text = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise WorkspaceImportManifestInvalidError() from None
    try:
        raw: ManifestJsonValue = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (ValueError, json.JSONDecodeError):
        raise WorkspaceImportManifestInvalidError() from None
    if not isinstance(raw, dict):
        raise WorkspaceImportManifestInvalidError()
    return _parse_manifest_payload(raw)


def _require_real_file_inside(path: Path, source_root: Path, label: str) -> Path:
    """要求路径为 source root 内非 symlink 的 regular file。

    Args:
        path: 待校验路径。
        source_root: source root（containment 边界）。
        label: 用于错误消息的中文名称。

    Returns:
        resolve 后的路径。

    Raises:
        WorkspaceImportManifestInvalidError: 路径不在 source root 内或
            不是 regular file 时抛出。
    """

    try:
        entry_stat = path.lstat()
    except OSError:
        raise WorkspaceImportManifestInvalidError() from None
    if not stat.S_ISREG(entry_stat.st_mode):
        raise WorkspaceImportManifestInvalidError()
    resolved = path.resolve()
    try:
        resolved.relative_to(source_root)
    except ValueError:
        raise WorkspaceImportManifestInvalidError() from None
    return resolved


def _inventory_companies(
    company_repository: FsCompanyMetaRepository,
) -> dict[str, CompanyMeta]:
    """扫描 Fins company inventory 并返回 ``company_id -> CompanyMeta``。

    Args:
        company_repository: 以 no-create 模式构造的公司仓储。

    Returns:
        raw company id 到 ``CompanyMeta`` 的映射（只含 available 条目）。

    Raises:
        WorkspaceImportOwnerInvalidError: 存在 ``missing_meta`` /
            ``invalid_meta`` 或文件系统访问失败时抛出。
    """

    try:
        inventory = company_repository.scan_company_meta_inventory()
    except OSError:
        raise WorkspaceImportOwnerInvalidError() from None
    companies: dict[str, CompanyMeta] = {}
    for entry in inventory:
        _classify_inventory_entry(entry)
        if entry.status == "available" and entry.company_meta is not None:
            companies[entry.company_meta.company_id] = entry.company_meta
    return companies


def _classify_inventory_entry(entry: CompanyMetaInventoryEntry) -> None:
    """校验单个 inventory 条目状态（missing/invalid fail closed）。

    Args:
        entry: inventory 条目。

    Returns:
        无。

    Raises:
        WorkspaceImportOwnerInvalidError: 条目为 ``missing_meta`` /
            ``invalid_meta`` 时抛出。
    """

    if entry.status in ("missing_meta", "invalid_meta"):
        raise WorkspaceImportOwnerInvalidError()


def _require_manifest_inventory_exact_set(
    manifest_companies: tuple[_ManifestCompany, ...],
    inventory_companies: dict[str, CompanyMeta],
) -> None:
    """双向 exact-set 校验 manifest 与 inventory company。

    Args:
        manifest_companies: 已收窄的 manifest 公司 tuple。
        inventory_companies: inventory 的 ``company_id -> CompanyMeta``。

    Returns:
        无。

    Raises:
        WorkspaceImportOwnerInvalidError: 两侧集合不一致，或
            ``companies=[]`` 但 inventory 非空时抛出。
    """

    manifest_ids = {company.legacy_company_id for company in manifest_companies}
    inventory_ids = set(inventory_companies)
    if manifest_ids != inventory_ids:
        raise WorkspaceImportOwnerInvalidError()


def _has_source_root(
    source_repository: FsSourceDocumentRepository,
    ticker: str,
    source_kind: SourceKind,
) -> bool:
    """判断某公司某类 source storage root 是否存在。

    Args:
        source_repository: 以 no-create 模式构造的源文档仓储。
        ticker: canonical ticker。
        source_kind: 源文档种类。

    Returns:
        root 存在且为目录时返回 ``True``。

    Raises:
        WorkspaceImportOwnerInvalidError: root 路径存在但不是目录或
            文件系统访问失败时抛出。
    """

    try:
        return source_repository.has_source_storage_root(ticker, source_kind)
    except (NotADirectoryError, OSError):
        raise WorkspaceImportOwnerInvalidError() from None


def _require_canonical_uuid(value: str) -> None:
    """校验目标租户是 canonical 小写 UUID。

    Args:
        value: 待校验的 UUID 字符串。

    Returns:
        无。

    Raises:
        WorkspaceImportUsageError: 值不是 canonical UUID 时抛出。
    """

    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise WorkspaceImportUsageError() from None
    if parsed.int == 0 or str(parsed) != value:
        raise WorkspaceImportUsageError()


def stage_workspace_import(
    *,
    source_root: Path,
    manifest_path: Path,
    target_tenant_id: str,
) -> WorkspaceImportRequest:
    """staging 旧 workspace 并构造最终纯 import 请求（read-only）。

    本函数在任何 DB engine/session 创建前完成；任何 staging 错误后
    DB connect count 必须为 0。source tree 在所有状态只读，不搬迁、
    删除、改写或复制任何 Host/Fins 原始字节。

    Args:
        source_root: legacy workspace source root。
        manifest_path: strict operator manifest 路径。
        target_tenant_id: 目标租户 UUID（当前必须为 default）。

    Returns:
        携带两个 fingerprint 的纯 ``WorkspaceImportRequest``。

    Raises:
        WorkspaceImportUsageError: 目标租户不是 canonical UUID 时抛出。
        WorkspaceImportManifestInvalidError: manifest 结构/路径非法时
            抛出。
        WorkspaceImportOwnerInvalidError: Fins/bundle owner 数据非法时
            抛出。
        WorkspaceImportIdentityInconsistentError: ticker/MIC/currency/
            country/market 或 bundle cross-check 不一致时抛出。
    """

    try:
        _require_canonical_uuid(target_tenant_id)
        resolved_source_root = source_root.resolve()
    except OSError:
        raise WorkspaceImportOwnerInvalidError() from None
    if not resolved_source_root.is_dir():
        raise WorkspaceImportOwnerInvalidError()
    resolved_manifest = _require_real_file_inside(
        manifest_path,
        resolved_source_root,
        "manifest",
    )
    manifest_companies = _load_strict_manifest(resolved_manifest)

    company_repository = FsCompanyMetaRepository(
        resolved_source_root,
        create_directories=False,
    )
    inventory_companies = _inventory_companies(company_repository)
    _require_manifest_inventory_exact_set(manifest_companies, inventory_companies)

    source_repository = FsSourceDocumentRepository(
        resolved_source_root,
        create_directories=False,
    )

    tenant_id = TenantId(target_tenant_id)
    verified_companies: list[VerifiedLegacyCompany] = []
    company_projections: list[FingerprintCompanyProjection] = []
    source_root_presence: list[FingerprintSourceRootPresence] = []
    bundle_closures: list[FingerprintBundleClosure] = []
    locators: list[VerifiedResearchBundleLocator] = []
    any_filing_root = False
    any_material_root = False

    for manifest_company in manifest_companies:
        inventory_meta = inventory_companies[manifest_company.legacy_company_id]
        _validate_ticker_identity(
            manifest_ticker=manifest_company.security.ticker,
            inventory_meta=inventory_meta,
        )
        company_projections.append(
            FingerprintCompanyProjection(
                company_id=inventory_meta.company_id,
                company_name=inventory_meta.company_name,
                ticker=inventory_meta.ticker,
                market=inventory_meta.market,
                resolver_version=inventory_meta.resolver_version,
                updated_at=inventory_meta.updated_at,
                aliases=tuple(inventory_meta.ticker_aliases),
            )
        )
        filing_present = _has_source_root(
            source_repository,
            inventory_meta.ticker,
            SourceKind.FILING,
        )
        material_present = _has_source_root(
            source_repository,
            inventory_meta.ticker,
            SourceKind.MATERIAL,
        )
        any_filing_root = any_filing_root or filing_present
        any_material_root = any_material_root or material_present
        source_root_presence.append(
            FingerprintSourceRootPresence(
                legacy_company_id=manifest_company.legacy_company_id,
                source_key=LEGACY_FINS_FILING_SOURCE_KEY,
                present=filing_present,
            )
        )
        source_root_presence.append(
            FingerprintSourceRootPresence(
                legacy_company_id=manifest_company.legacy_company_id,
                source_key=LEGACY_FINS_MATERIAL_SOURCE_KEY,
                present=material_present,
            )
        )
        bundle_references: list[LegacyBundleReference] = []
        for bundle_ref in manifest_company.bundles:
            closure = _inspect_bundle_closure(
                bundle_ref=bundle_ref,
                manifest_company=manifest_company,
                inventory_meta=inventory_meta,
                source_root=resolved_source_root,
            )
            bundle_closures.append(_to_fingerprint_closure(closure))
            locators.append(
                build_verified_bundle_locator(
                    tenant_id=tenant_id,
                    exchange_mic=manifest_company.security.exchange_mic,
                    ticker=manifest_company.security.ticker,
                    template_name=bundle_ref.template_name,
                    relative_locator=bundle_ref.relative_locator,
                    bundle_sha256=closure.descriptor_sha256,
                    artifact_manifest_sha256=closure.artifact_manifest_sha256,
                )
            )
            bundle_references.append(
                LegacyBundleReference(
                    template_name=bundle_ref.template_name,
                    relative_locator=bundle_ref.relative_locator,
                )
            )
        verified_companies.append(
            build_verified_company(
                legacy_company_id=manifest_company.legacy_company_id,
                company_name=inventory_meta.company_name,
                company_meta_market=inventory_meta.market,
                lei=manifest_company.lei,
                country_code=manifest_company.country_code,
                ticker=manifest_company.security.ticker,
                exchange_mic=manifest_company.security.exchange_mic,
                security_type=_security_type_from_raw(manifest_company.security.security_type),
                currency=manifest_company.security.currency,
                isin=manifest_company.security.isin,
                is_active=manifest_company.security.is_active,
                bundles=tuple(bundle_references),
            )
        )

    _require_global_identity_uniqueness(manifest_companies)
    source_definitions = _derive_source_definitions(
        any_filing_root=any_filing_root,
        any_material_root=any_material_root,
    )
    return build_workspace_import_request(
        migration_id=WORKSPACE_IMPORT_MIGRATION_ID,
        companies=tuple(verified_companies),
        source_definitions=tuple(source_definitions),
        locators=tuple(locators),
        company_projections=tuple(company_projections),
        source_root_presence=tuple(source_root_presence),
        bundle_closures=tuple(bundle_closures),
    )


def _validate_ticker_identity(*, manifest_ticker: str, inventory_meta: CompanyMeta) -> None:
    """证明 manifest 与 inventory ticker 各自 canonical 后 exact。

    Args:
        manifest_ticker: manifest 的 ticker。
        inventory_meta: 对应 inventory ``CompanyMeta``。

    Returns:
        无。

    Raises:
        WorkspaceImportIdentityInconsistentError: 任一侧 ticker 非
            canonical 或两侧不一致时抛出。
    """

    try:
        classify_canonical_ticker(manifest_ticker)
        classify_canonical_ticker(inventory_meta.ticker)
    except ValueError:
        raise WorkspaceImportIdentityInconsistentError() from None
    if inventory_meta.ticker != manifest_ticker:
        raise WorkspaceImportIdentityInconsistentError()


def _security_type_from_raw(raw: str) -> SecurityType:
    """把 manifest 的证券类型字符串收窄为 closed enum。

    Args:
        raw: 原始证券类型字符串。

    Returns:
        ``SecurityType`` 枚举值。

    Raises:
        WorkspaceImportManifestInvalidError: 字符串不是合法枚举值时
            抛出。
    """

    try:
        return SecurityType(raw)
    except ValueError:
        raise WorkspaceImportManifestInvalidError() from None


def _inspect_bundle_closure(
    *,
    bundle_ref: _ManifestBundle,
    manifest_company: _ManifestCompany,
    inventory_meta: CompanyMeta,
    source_root: Path,
) -> ResearchBundleClosureInspection:
    """检查单个 bundle closure 并执行 manifest/owner cross-check。

    Args:
        bundle_ref: manifest bundle 引用。
        manifest_company: manifest 公司原始值。
        inventory_meta: 对应 inventory ``CompanyMeta``。
        source_root: source root（containment 边界）。

    Returns:
        owner typed closure 结果。

    Raises:
        WorkspaceImportOwnerInvalidError: closure 检查失败时抛出。
        WorkspaceImportIdentityInconsistentError: template/ticker/
            company-name cross-check 不一致时抛出。
    """

    bundle_path = source_root / bundle_ref.relative_locator
    try:
        closure = inspect_research_template_bundle_closure(bundle_path, source_root)
    except (ResearchBundleClosureError, OSError):
        raise WorkspaceImportOwnerInvalidError() from None
    if closure.template != bundle_ref.template_name:
        raise WorkspaceImportIdentityInconsistentError()
    if closure.target_ticker != manifest_company.security.ticker:
        raise WorkspaceImportIdentityInconsistentError()
    if closure.target_company_name != inventory_meta.company_name:
        raise WorkspaceImportIdentityInconsistentError()
    return closure


def _to_fingerprint_closure(closure: ResearchBundleClosureInspection) -> FingerprintBundleClosure:
    """把 owner typed closure 结果收窄为 fingerprint 投影。

    Args:
        closure: owner closure 结果。

    Returns:
        fingerprint 投影。

    Raises:
        无。
    """

    return FingerprintBundleClosure(
        template=closure.template,
        target_ticker=closure.target_ticker,
        target_company_name=closure.target_company_name,
        descriptor_sha256=closure.descriptor_sha256,
        files=tuple(
            FingerprintClosureFile(
                role=file.role,
                relative_locator=file.relative_locator,
                size_bytes=file.size_bytes,
                sha256=file.sha256,
            )
            for file in closure.files
        ),
        artifact_manifest_sha256=closure.artifact_manifest_sha256,
    )


def _derive_source_definitions(
    *,
    any_filing_root: bool,
    any_material_root: bool,
) -> tuple[VerifiedLegacySourceDefinition, ...]:
    """按 source root presence 派生全局稳定 source definitions。

    Args:
        any_filing_root: 任一 verified company 存在 filing storage root。
        any_material_root: 任一 verified company 存在 material storage root。

    Returns:
        派生数据源定义 tuple。

    Raises:
        无。
    """

    definitions: list[VerifiedLegacySourceDefinition] = []
    if any_filing_root:
        definitions.append(
            build_verified_source_definition(
                source_key=LEGACY_FINS_FILING_SOURCE_KEY,
                source_kind=InvestmentSourceKind.FILING,
                display_name="Legacy Fins Filing",
                enabled_by_default=False,
            )
        )
    if any_material_root:
        definitions.append(
            build_verified_source_definition(
                source_key=LEGACY_FINS_MATERIAL_SOURCE_KEY,
                source_kind=InvestmentSourceKind.RESEARCH_MATERIAL,
                display_name="Legacy Fins Research Material",
                enabled_by_default=False,
            )
        )
    return tuple(definitions)


__all__ = [
    "stage_workspace_import",
]
