"""旧 workspace 显式导入的纯 domain 契约（S15-CTRL-06）。

本模块是 workspace import 的唯一 strict DTO / canonical / fingerprint
owner，定义：

- 七个稳定错误类别（``WorkspaceImportError`` 子类），错误消息只含
  固定 safe code，绝不包含 DSN、absolute path、候选值或原文；
- frozen slots DTO：``LegacySecurityMapping`` / ``LegacyBundleReference`` /
  ``VerifiedLegacyCompany`` / ``VerifiedLegacySourceDefinition`` /
  ``VerifiedResearchBundleLocator`` / ``WorkspaceImportRequest`` /
  ``WorkspaceImportReceipt``，以及 fingerprint 输入投影
  （``FingerprintCompanyProjection`` 等）；
- UUIDv5 唯一 ID 算法：namespace 为标准库 ``NAMESPACE_URL``，name
  前缀固定（见各 ``derive_*`` 函数）；
- canonical ticker 分类与 market consistency gate：HK 必须
  ``XHKG/HKD/HK``，CN SSE/SZSE 必须分别 ``XSHG``/``XSHE`` 且
  ``CNY/CN``，US 只做 MIC 4 位大写语义验证、禁止默认猜
  ``XNAS``/``XNYS``；
- ``source_root_fingerprint`` / ``staged_payload_sha256`` 的 canonical
  SHA-256 计算。

设计约束：

- 本模块为纯 domain 层，只依赖标准库与
  ``dayu.investment.domain`` 的 pure identifiers / closed values，
  禁止 import ``dayu.fins.*``、CLI、Service、ORM；
- 所有集合在构造期 defensive-copy 为 tuple；canonical JSON 只含
  scalar / tuple / mapping，不含 ORM、Path、session、absolute path、
  raw bytes、Fins 宽 dict；
- 禁止 ``Any`` / ``object`` / ``cast`` / ``ignore`` / ``getattr`` /
  ``hasattr`` 与宽 ``dict`` 穿透；不接受 caller-supplied UUID；
- Fins owner types 到 pure DTO 的收窄只发生在
  ``dayu.cli.workspace_migrations.platform_import``。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Literal, TypeAlias
from uuid import NAMESPACE_URL, UUID, uuid5

from dayu.investment.domain.identifiers import (
    CompanyId,
    SecurityId,
    TenantId,
)
from dayu.investment.domain.source import (
    SecurityType,
    SourceDefinitionId,
    SourceKind,
)

WORKSPACE_IMPORT_SCHEMA_VERSION: int = 1
"""当前 manifest schema version（精确固定值）。"""

WORKSPACE_IMPORT_MIGRATION_ID: str = "legacy-workspace-import-v1"
"""当前 migration id（精确固定值）。"""

LEGACY_REPOSITORY_KEY: str = "legacy-workspace"
"""locator 当前 closed repository key（有意不预留宽值）。"""

LEGACY_FINS_FILING_SOURCE_KEY: str = "legacy.fins.filing"
"""legacy Fins filing source root 派生的全局 source definition key。"""

LEGACY_FINS_MATERIAL_SOURCE_KEY: str = "legacy.fins.material"
"""legacy Fins material source root 派生的全局 source definition key。"""

_CANONICAL_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_MIC_PATTERN = re.compile(r"^[A-Z]{4}$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
_COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")
_HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_US_TICKER_PATTERN = re.compile(r"^[A-Z]+(?:-[A-Z0-9]+)?$")
_MAX_US_SYMBOL_LENGTH = 8
_RELATIVE_LOCATOR_PATTERN = re.compile(r"^[^/][^/]*(?:/[^/]+)*$")

_UUIDV5_COMPANY_PREFIX = "dayu:workspace-import:v1:company:"
_UUIDV5_SECURITY_PREFIX = "dayu:workspace-import:v1:security:"
_UUIDV5_SOURCE_PREFIX = "dayu:workspace-import:v1:source:"
_UUIDV5_MARKER_PREFIX = "dayu:workspace-import:v1:marker:"
_UUIDV5_BUNDLE_PREFIX = "dayu:workspace-import:v1:bundle:"


class WorkspaceImportError(RuntimeError):
    """workspace import 失败稳定错误基类。

    消息只含固定 safe code，绝不包含 DSN、absolute path、候选值或原文。
    """

    error_code: ClassVar[str] = "workspace_import_error"

    def __init__(self) -> None:
        """以固定 safe code 作为消息构造错误。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(self.error_code)


class WorkspaceImportUsageError(WorkspaceImportError):
    """import mode 参数/租户使用非法。"""

    error_code: ClassVar[str] = "workspace_import_usage"


class WorkspaceImportManifestInvalidError(WorkspaceImportError):
    """operator manifest 结构非法。"""

    error_code: ClassVar[str] = "workspace_import_manifest_invalid"


class WorkspaceImportOwnerInvalidError(WorkspaceImportError):
    """Fins/bundle owner 数据或校验非法。"""

    error_code: ClassVar[str] = "workspace_import_owner_invalid"


class WorkspaceImportIdentityInconsistentError(WorkspaceImportError):
    """MIC/ticker/market/currency/country 等身份事实不一致。"""

    error_code: ClassVar[str] = "workspace_import_identity_inconsistent"


class WorkspaceImportSchemaUnavailableError(WorkspaceImportError):
    """平台 schema（0002 两表）不可用。"""

    error_code: ClassVar[str] = "workspace_import_schema_unavailable"


class WorkspaceImportDriftError(WorkspaceImportError):
    """marker/row 与 intended projection 不一致（drift）。"""

    error_code: ClassVar[str] = "workspace_import_drift"


class WorkspaceImportRepositoryFailureError(WorkspaceImportError):
    """数据库事务/连接/约束失败。"""

    error_code: ClassVar[str] = "workspace_import_repository_failure"


def _validate_nonblank(value: str, label: str) -> str:
    """校验文本非空且无首尾空白。

    Args:
        value: 待校验的文本。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的原文。

    Raises:
        ValueError: 值为空、仅空白或含首尾空白时抛出。
    """

    if not value or value != value.strip():
        raise ValueError(f"{label} 必须非空且无首尾空白")
    return value


def _validate_pattern(value: str, pattern: re.Pattern[str], label: str) -> str:
    """校验文本符合固定形态。

    Args:
        value: 待校验的文本。
        pattern: 目标正则。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的原文。

    Raises:
        ValueError: 文本不符合形态时抛出。
    """

    if pattern.fullmatch(value) is None:
        raise ValueError(f"{label} 形态非法")
    return value


def _validate_canonical_uuid(value: str, label: str) -> str:
    """校验 canonical UUID 字符串形态。

    Args:
        value: 待校验的 UUID 字符串。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的小写连字符 UUID 字符串。

    Raises:
        ValueError: 值不是小写连字符 ``8-4-4-4-12`` UUID，或
            ``str(UUID(value)) != value`` 时抛出。
    """

    if _CANONICAL_UUID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} 必须是规范小写 UUID（8-4-4-4-12）")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise ValueError(f"{label} 必须是规范小写 UUID（8-4-4-4-12）") from None
    if str(parsed) != value or parsed.int == 0:
        raise ValueError(f"{label} 必须是规范小写 UUID（8-4-4-4-12）")
    return value


def _validate_sha256_hex(value: str, label: str) -> str:
    """校验 64 位小写 SHA-256 十六进制字符串。

    Args:
        value: 待校验的摘要。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的原文。

    Raises:
        ValueError: 摘要不是 64 位小写 hex 时抛出。
    """

    return _validate_pattern(value, _HEX_64_PATTERN, label)


def _validate_relative_locator(value: str, label: str) -> str:
    """校验 POSIX relative locator 形态。

    规则：非空、无首尾空白、不以 ``/`` 开头、无 ``..`` 段、不含
    ``\\\\`` 或空白段。

    Args:
        value: 待校验的 locator。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的原文。

    Raises:
        ValueError: locator 不满足 POSIX relative 规则时抛出。
    """

    _validate_nonblank(value, label)
    if "\\" in value or ".." in value.split("/"):
        raise ValueError(f"{label} 必须是 POSIX relative locator")
    if _RELATIVE_LOCATOR_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} 必须是 POSIX relative locator")
    return value


class CanonicalTickerMarket(Enum):
    """canonical ticker 分类结果。

    与 ``dayu.fins.ticker_normalization`` 的 canonical 形态规则一致，
    但本模块只接受已经 canonical 的输入（manifest 与 owner ticker 均
    必须先证明已 canonical，再做 exact 比较）。
    """

    US = "US"
    HK = "HK"
    CN_SSE = "CN_SSE"
    CN_SZSE = "CN_SZSE"


def classify_canonical_ticker(ticker: str) -> CanonicalTickerMarket:
    """对已 canonical 的 ticker 做市场分类。

    规则（对应 ``normalize_ticker`` 的 canonical 输出形态）：

    - 港股：纯数字，去除前导零后长度 1-4 时等于 ``zfill(4)``，或长度
      5 时保持原样；
    - 沪股：6 位纯数字且首位为 ``6``；
    - 深股：6 位纯数字且首位为 ``0`` 或 ``3``；
    - 美股：大写字母（可带一个 ``-`` 分节），长度不超过 8。

    Args:
        ticker: 已 canonical 的 ticker。

    Returns:
        市场分类结果。

    Raises:
        ValueError: ticker 不是任何市场的 canonical 形态时抛出。
    """

    if not ticker or ticker != ticker.strip():
        raise ValueError("ticker 必须非空且无首尾空白")
    if ticker.isdigit():
        if len(ticker) == 6:
            if ticker[0] == "6":
                return CanonicalTickerMarket.CN_SSE
            if ticker[0] in ("0", "3"):
                return CanonicalTickerMarket.CN_SZSE
            raise ValueError("ticker 不是 canonical 形态")
        stripped = ticker.lstrip("0") or "0"
        if len(stripped) <= 4:
            if ticker == stripped.zfill(4):
                return CanonicalTickerMarket.HK
            raise ValueError("ticker 不是 canonical 形态")
        if len(stripped) == 5 and ticker == stripped:
            return CanonicalTickerMarket.HK
        raise ValueError("ticker 不是 canonical 形态")
    if (
        _US_TICKER_PATTERN.fullmatch(ticker) is not None
        and len(ticker) <= _MAX_US_SYMBOL_LENGTH
    ):
        return CanonicalTickerMarket.US
    raise ValueError("ticker 不是 canonical 形态")


def _market_label_for(market: CanonicalTickerMarket) -> str:
    """返回分类结果的 market 标签（``US`` / ``HK`` / ``CN``）。

    Args:
        market: 市场分类。

    Returns:
        与 ``CompanyMeta.market`` 比较用的稳定标签。

    Raises:
        无。
    """

    if market is CanonicalTickerMarket.US:
        return "US"
    if market is CanonicalTickerMarket.HK:
        return "HK"
    return "CN"


def _validate_market_consistency(
    *,
    market: CanonicalTickerMarket,
    company_meta_market: str,
    exchange_mic: str,
    currency: str,
    country_code: str | None,
) -> None:
    """执行 manifest/owner 的 market consistency gate。

    规则（S15-CTRL-05）：

    - HK 必须 ``XHKG/HKD/HK``；
    - CN SSE/SZSE 必须分别 ``XSHG``/``XSHE`` 且 ``CNY/CN``；
    - US 只要求 MIC 4 位大写、currency 3 位大写、country code 可空则
      2 位大写，MIC 由 manifest 明示且禁止默认猜 ``XNAS``/``XNYS``；
    - ``CompanyMeta.market`` 必须与 ticker 分类的 market 标签一致。

    Args:
        market: ticker 分类结果。
        company_meta_market: ``CompanyMeta.market`` raw 值。
        exchange_mic: manifest 明示的 MIC。
        currency: manifest 明示的货币。
        country_code: manifest 明示的国家码（可空）。

    Returns:
        无。

    Raises:
        WorkspaceImportIdentityInconsistentError: 任一规则违反时抛出。
    """

    expected_market_label = _market_label_for(market)
    if company_meta_market != expected_market_label:
        raise WorkspaceImportIdentityInconsistentError()
    if market is CanonicalTickerMarket.HK:
        if (
            exchange_mic != "XHKG"
            or currency != "HKD"
            or country_code != "HK"
        ):
            raise WorkspaceImportIdentityInconsistentError()
        return
    if market is CanonicalTickerMarket.CN_SSE:
        if (
            exchange_mic != "XSHG"
            or currency != "CNY"
            or country_code != "CN"
        ):
            raise WorkspaceImportIdentityInconsistentError()
        return
    if market is CanonicalTickerMarket.CN_SZSE:
        if (
            exchange_mic != "XSHE"
            or currency != "CNY"
            or country_code != "CN"
        ):
            raise WorkspaceImportIdentityInconsistentError()
        return
    if _MIC_PATTERN.fullmatch(exchange_mic) is None:
        raise WorkspaceImportIdentityInconsistentError()
    if _CURRENCY_PATTERN.fullmatch(currency) is None:
        raise WorkspaceImportIdentityInconsistentError()
    if country_code is not None and _COUNTRY_CODE_PATTERN.fullmatch(country_code) is None:
        raise WorkspaceImportIdentityInconsistentError()


def derive_company_id(legacy_company_id: str) -> str:
    """按 UUIDv5 派生公司标识。

    Args:
        legacy_company_id: owner inventory 已验证的 raw company id。

    Returns:
        canonical 小写 UUID 字符串。

    Raises:
        ValueError: ``legacy_company_id`` 为空或含首尾空白时抛出。
    """

    _validate_nonblank(legacy_company_id, "legacy_company_id")
    return str(uuid5(NAMESPACE_URL, f"{_UUIDV5_COMPANY_PREFIX}{legacy_company_id}"))


def derive_security_id(exchange_mic: str, ticker: str) -> str:
    """按 UUIDv5 派生证券标识。

    Args:
        exchange_mic: 4 位大写 MIC。
        ticker: canonical 大写 ticker。

    Returns:
        canonical 小写 UUID 字符串。

    Raises:
        ValueError: MIC 或 ticker 形态非法时抛出。
    """

    _validate_pattern(exchange_mic, _MIC_PATTERN, "交易所 MIC")
    classify_canonical_ticker(ticker)
    return str(uuid5(NAMESPACE_URL, f"{_UUIDV5_SECURITY_PREFIX}{exchange_mic}:{ticker}"))


def derive_source_definition_id(source_key: str) -> str:
    """按 UUIDv5 派生数据源定义标识。

    Args:
        source_key: 数据源唯一键。

    Returns:
        canonical 小写 UUID 字符串。

    Raises:
        ValueError: ``source_key`` 为空或含首尾空白时抛出。
    """

    _validate_nonblank(source_key, "数据源键")
    return str(uuid5(NAMESPACE_URL, f"{_UUIDV5_SOURCE_PREFIX}{source_key}"))


def derive_workspace_import_marker_id(tenant_id: TenantId, migration_id: str) -> str:
    """按 UUIDv5 派生 import marker 标识。

    Args:
        tenant_id: 租户标识。
        migration_id: migration id（精确固定值）。

    Returns:
        canonical 小写 UUID 字符串。

    Raises:
        TypeError: ``tenant_id`` 不是 ``TenantId`` 时抛出。
        ValueError: migration id 为空或含首尾空白时抛出。
    """

    if not isinstance(tenant_id, TenantId):
        raise TypeError("tenant_id 必须是 TenantId")
    _validate_nonblank(migration_id, "migration_id")
    return str(uuid5(NAMESPACE_URL, f"{_UUIDV5_MARKER_PREFIX}{tenant_id.value}:{migration_id}"))


def derive_bundle_locator_id(
    tenant_id: TenantId,
    exchange_mic: str,
    ticker: str,
    template_name: str,
) -> str:
    """按 UUIDv5 派生 research bundle locator 标识。

    Args:
        tenant_id: 租户标识。
        exchange_mic: 4 位大写 MIC。
        ticker: canonical 大写 ticker。
        template_name: 研究模板名。

    Returns:
        canonical 小写 UUID 字符串。

    Raises:
        TypeError: ``tenant_id`` 不是 ``TenantId`` 时抛出。
        ValueError: 任一 name component 形态非法时抛出。
    """

    if not isinstance(tenant_id, TenantId):
        raise TypeError("tenant_id 必须是 TenantId")
    _validate_pattern(exchange_mic, _MIC_PATTERN, "交易所 MIC")
    classify_canonical_ticker(ticker)
    _validate_nonblank(template_name, "模板名")
    return str(
        uuid5(
            NAMESPACE_URL,
            f"{_UUIDV5_BUNDLE_PREFIX}{tenant_id.value}:{exchange_mic}:{ticker}:{template_name}",
        )
    )


@dataclass(frozen=True, slots=True)
class LegacySecurityMapping:
    """legacy 公司对应的单一证券映射（manifest 显式 operator mapping）。

    Args:
        security_id: 派生的证券标识（UUIDv5）。
        company_id: 派生的公司标识（UUIDv5）。
        ticker: canonical 大写 ticker。
        exchange_mic: 4 位大写 MIC。
        security_type: 证券类型 closed enum。
        currency: 3 位大写货币。
        isin: 可空 ISIN。
        is_active: 是否活跃。
    """

    security_id: SecurityId
    company_id: CompanyId
    ticker: str
    exchange_mic: str
    security_type: SecurityType
    currency: str
    isin: str | None
    is_active: bool

    def __post_init__(self) -> None:
        """构造期严格校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 标识/枚举/bool 类型非法时抛出。
            ValueError: 文本字段违反规则时抛出。
        """

        if not isinstance(self.security_id, SecurityId):
            raise TypeError("security_id 必须是 SecurityId")
        if not isinstance(self.company_id, CompanyId):
            raise TypeError("company_id 必须是 CompanyId")
        if not isinstance(self.security_type, SecurityType):
            raise TypeError("security_type 必须是 SecurityType")
        if not isinstance(self.is_active, bool):
            raise TypeError("is_active 必须是 bool")
        _validate_pattern(self.exchange_mic, _MIC_PATTERN, "交易所 MIC")
        classify_canonical_ticker(self.ticker)
        _validate_pattern(self.currency, _CURRENCY_PATTERN, "货币代码")
        if self.isin is not None:
            _validate_nonblank(self.isin, "ISIN")


@dataclass(frozen=True, slots=True)
class LegacyBundleReference:
    """manifest 声明的单个 research bundle 引用。

    Args:
        template_name: 研究模板名。
        relative_locator: 相对 source root 的 POSIX relative locator。
    """

    template_name: str
    relative_locator: str

    def __post_init__(self) -> None:
        """构造期严格校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 模板名或 locator 形态非法时抛出。
        """

        _validate_nonblank(self.template_name, "模板名")
        _validate_relative_locator(self.relative_locator, "bundle relative locator")


@dataclass(frozen=True, slots=True)
class VerifiedLegacyCompany:
    """已交叉验证的 legacy 公司 + 证券 + bundle 引用。

    ``legacy_company_id`` 精确使用 owner inventory 已验证的 raw value，
    不做任何 normalization 或别名映射。

    Args:
        company_id: 派生的公司标识（UUIDv5）。
        legacy_company_id: owner inventory raw company id。
        company_name: ``CompanyMeta.company_name`` raw 值。
        market: ``CompanyMeta.market`` raw 值。
        lei: manifest 明示的 LEI（可空）。
        country_code: manifest 明示的国家码（可空）。
        security: 唯一证券映射。
        bundles: bundle 引用 tuple（构造期 defensive-copy）。
    """

    company_id: CompanyId
    legacy_company_id: str
    company_name: str
    market: str
    lei: str | None
    country_code: str | None
    security: LegacySecurityMapping
    bundles: tuple[LegacyBundleReference, ...]

    def __post_init__(self) -> None:
        """构造期严格校验并防御性冻结 bundles。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ``company_id`` 或 ``security`` 类型非法时抛出。
            ValueError: 文本字段或 bundles 集合违反规则时抛出。
        """

        if not isinstance(self.company_id, CompanyId):
            raise TypeError("company_id 必须是 CompanyId")
        if not isinstance(self.security, LegacySecurityMapping):
            raise TypeError("security 必须是 LegacySecurityMapping")
        if not isinstance(self.bundles, tuple):
            raise TypeError("bundles 必须是 tuple")
        if self.security.company_id != self.company_id:
            raise ValueError("security 的 company_id 必须与公司一致")
        _validate_nonblank(self.legacy_company_id, "legacy_company_id")
        _validate_nonblank(self.company_name, "公司名称")
        _validate_nonblank(self.market, "市场")
        if self.lei is not None:
            _validate_nonblank(self.lei, "LEI")
        if self.country_code is not None:
            _validate_pattern(self.country_code, _COUNTRY_CODE_PATTERN, "国家码")
        object.__setattr__(self, "bundles", tuple(self.bundles))


@dataclass(frozen=True, slots=True)
class VerifiedLegacySourceDefinition:
    """由 source root presence 派生的全局数据源定义。

    Args:
        source_definition_id: 派生的数据源定义标识（UUIDv5）。
        source_key: 数据源唯一键（如 ``legacy.fins.filing``）。
        source_kind: 数据源种类 closed enum。
        display_name: 显示名。
        enabled_by_default: 是否默认启用。
    """

    source_definition_id: SourceDefinitionId
    source_key: str
    source_kind: SourceKind
    display_name: str
    enabled_by_default: bool

    def __post_init__(self) -> None:
        """构造期严格校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 标识/枚举/bool 类型非法时抛出。
            ValueError: 文本字段违反规则时抛出。
        """

        if not isinstance(self.source_definition_id, SourceDefinitionId):
            raise TypeError("source_definition_id 必须是 SourceDefinitionId")
        if not isinstance(self.source_kind, SourceKind):
            raise TypeError("source_kind 必须是 SourceKind")
        if not isinstance(self.enabled_by_default, bool):
            raise TypeError("enabled_by_default 必须是 bool")
        _validate_nonblank(self.source_key, "数据源键")
        _validate_nonblank(self.display_name, "数据源显示名")


@dataclass(frozen=True, slots=True)
class VerifiedResearchBundleLocator:
    """已验证的 research bundle locator 记录。

    Args:
        locator_id: 派生的 locator 标识（UUIDv5）。
        security_id: 关联证券标识。
        template_name: 研究模板名。
        repository_key: 当前 closed 值 ``legacy-workspace``。
        relative_locator: 相对 source root 的 POSIX locator。
        bundle_sha256: descriptor 文件 SHA-256。
        artifact_manifest_sha256: closure 其余条目 canonical JSON SHA-256。
    """

    locator_id: str
    security_id: SecurityId
    template_name: str
    repository_key: str
    relative_locator: str
    bundle_sha256: str
    artifact_manifest_sha256: str

    def __post_init__(self) -> None:
        """构造期严格校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ``security_id`` 类型非法时抛出。
            ValueError: 字段形态违反规则时抛出。
        """

        _validate_canonical_uuid(self.locator_id, "locator 标识")
        if not isinstance(self.security_id, SecurityId):
            raise TypeError("security_id 必须是 SecurityId")
        _validate_nonblank(self.template_name, "模板名")
        if self.repository_key != LEGACY_REPOSITORY_KEY:
            raise ValueError("repository_key 必须是 legacy-workspace")
        _validate_relative_locator(self.relative_locator, "bundle relative locator")
        _validate_sha256_hex(self.bundle_sha256, "bundle_sha256")
        _validate_sha256_hex(self.artifact_manifest_sha256, "artifact_manifest_sha256")


@dataclass(frozen=True, slots=True)
class WorkspaceImportRequest:
    """最终纯 workspace import 请求（fingerprint 后不可变）。

    Args:
        schema_version: 固定为 1。
        migration_id: 固定为 ``legacy-workspace-import-v1``。
        companies: 已验证公司 tuple。
        source_definitions: 派生数据源定义 tuple。
        locators: 已验证 bundle locator tuple。
        source_root_fingerprint: source root canonical SHA-256。
        staged_payload_sha256: 本请求 canonical payload SHA-256。
    """

    schema_version: int
    migration_id: str
    companies: tuple[VerifiedLegacyCompany, ...]
    source_definitions: tuple[VerifiedLegacySourceDefinition, ...]
    locators: tuple[VerifiedResearchBundleLocator, ...]
    source_root_fingerprint: str
    staged_payload_sha256: str

    def __post_init__(self) -> None:
        """构造期严格校验并防御性冻结集合。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 版本/迁移 id/指纹/集合违反规则时抛出。
        """

        if type(self.schema_version) is not int or self.schema_version != WORKSPACE_IMPORT_SCHEMA_VERSION:
            raise ValueError("schema_version 必须精确为 1")
        if self.migration_id != WORKSPACE_IMPORT_MIGRATION_ID:
            raise ValueError("migration_id 必须精确为 legacy-workspace-import-v1")
        if not isinstance(self.companies, tuple):
            raise TypeError("companies 必须是 tuple")
        if not isinstance(self.source_definitions, tuple):
            raise TypeError("source_definitions 必须是 tuple")
        if not isinstance(self.locators, tuple):
            raise TypeError("locators 必须是 tuple")
        _validate_sha256_hex(self.source_root_fingerprint, "source_root_fingerprint")
        _validate_sha256_hex(self.staged_payload_sha256, "staged_payload_sha256")
        object.__setattr__(self, "companies", tuple(self.companies))
        object.__setattr__(self, "source_definitions", tuple(self.source_definitions))
        object.__setattr__(self, "locators", tuple(self.locators))


@dataclass(frozen=True, slots=True)
class WorkspaceImportReceipt:
    """repository 发布的纯结果收据（不泄漏 ORM/session/DSN）。

    Args:
        marker_id: 已提交 marker 标识。
        migration_id: migration id。
        status: ``committed`` 或 ``no_op``。
        company_count: marker 记录的公司数。
        security_count: marker 记录的证券数。
        source_definition_count: marker 记录的数据源定义数。
        bundle_count: marker 记录的 bundle locator 数。
        source_root_fingerprint: marker 记录的 fingerprint。
        staged_payload_sha256: marker 记录的 payload hash。
    """

    marker_id: str
    migration_id: str
    status: Literal["committed", "no_op"]
    company_count: int
    security_count: int
    source_definition_count: int
    bundle_count: int
    source_root_fingerprint: str
    staged_payload_sha256: str

    def __post_init__(self) -> None:
        """构造期严格校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 字段形态违反规则时抛出。
        """

        _validate_canonical_uuid(self.marker_id, "marker 标识")
        if self.migration_id != WORKSPACE_IMPORT_MIGRATION_ID:
            raise ValueError("migration_id 必须精确为 legacy-workspace-import-v1")
        if self.status not in ("committed", "no_op"):
            raise ValueError("status 必须是 committed 或 no_op")
        for count in (
            self.company_count,
            self.security_count,
            self.source_definition_count,
            self.bundle_count,
        ):
            if type(count) is not int or count < 0:
                raise ValueError("counts 必须为非负 int")
        _validate_sha256_hex(self.source_root_fingerprint, "source_root_fingerprint")
        _validate_sha256_hex(self.staged_payload_sha256, "staged_payload_sha256")


@dataclass(frozen=True, slots=True)
class FingerprintCompanyProjection:
    """fingerprint 使用的完整 verified CompanyMeta 投影。

    Args:
        company_id: ``CompanyMeta.company_id`` raw 值。
        company_name: ``CompanyMeta.company_name`` raw 值。
        ticker: ``CompanyMeta.ticker`` raw 值。
        market: ``CompanyMeta.market`` raw 值。
        resolver_version: ``CompanyMeta.resolver_version`` raw 值。
        updated_at: ``CompanyMeta.updated_at`` raw 值。
        aliases: ``CompanyMeta.ticker_aliases`` 规范化 tuple。
    """

    company_id: str
    company_name: str
    ticker: str
    market: str
    resolver_version: str
    updated_at: str
    aliases: tuple[str, ...]

    def __post_init__(self) -> None:
        """构造期严格校验并防御性冻结 aliases。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 文本字段违反规则时抛出。
        """

        _validate_nonblank(self.company_id, "company_id")
        _validate_nonblank(self.company_name, "公司名称")
        _validate_nonblank(self.ticker, "ticker")
        _validate_nonblank(self.market, "市场")
        _validate_nonblank(self.resolver_version, "resolver_version")
        _validate_nonblank(self.updated_at, "updated_at")
        if not isinstance(self.aliases, tuple):
            raise TypeError("aliases 必须是 tuple")
        object.__setattr__(self, "aliases", tuple(self.aliases))


@dataclass(frozen=True, slots=True)
class FingerprintSourceRootPresence:
    """fingerprint 使用的 source root presence 投影。

    Args:
        legacy_company_id: owner inventory raw company id。
        source_key: 派生数据源键。
        present: 对应 storage root 是否存在。
    """

    legacy_company_id: str
    source_key: str
    present: bool

    def __post_init__(self) -> None:
        """构造期严格校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ``present`` 不是 bool 时抛出。
            ValueError: 字段违反规则时抛出。
        """

        _validate_nonblank(self.legacy_company_id, "legacy_company_id")
        _validate_nonblank(self.source_key, "数据源键")
        if not isinstance(self.present, bool):
            raise TypeError("present 必须是 bool")


@dataclass(frozen=True, slots=True)
class FingerprintClosureFile:
    """fingerprint 使用的 bundle closure 文件投影。

    Args:
        role: closure 角色。
        relative_locator: POSIX relative locator。
        size_bytes: 文件字节数。
        sha256: 文件 SHA-256。
    """

    role: str
    relative_locator: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        """构造期严格校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 字段形态违反规则时抛出。
        """

        _validate_nonblank(self.role, "closure 角色")
        _validate_relative_locator(self.relative_locator, "closure relative locator")
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise ValueError("size_bytes 必须为非负 int")
        _validate_sha256_hex(self.sha256, "closure sha256")


@dataclass(frozen=True, slots=True)
class FingerprintBundleClosure:
    """fingerprint 使用的 bundle closure 投影。

    Args:
        template: 研究模板名。
        target_ticker: closure 的规范 target ticker。
        target_company_name: closure 的 target 公司名称。
        descriptor_sha256: descriptor 文件 SHA-256。
        files: closure 文件投影 tuple。
        artifact_manifest_sha256: closure artifact manifest SHA-256。
    """

    template: str
    target_ticker: str
    target_company_name: str
    descriptor_sha256: str
    files: tuple[FingerprintClosureFile, ...]
    artifact_manifest_sha256: str

    def __post_init__(self) -> None:
        """构造期严格校验并防御性冻结 files。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 字段形态违反规则时抛出。
        """

        _validate_nonblank(self.template, "模板名")
        _validate_nonblank(self.target_ticker, "target ticker")
        _validate_nonblank(self.target_company_name, "target 公司名称")
        _validate_sha256_hex(self.descriptor_sha256, "descriptor_sha256")
        if not isinstance(self.files, tuple):
            raise TypeError("files 必须是 tuple")
        _validate_sha256_hex(self.artifact_manifest_sha256, "artifact_manifest_sha256")
        object.__setattr__(self, "files", tuple(self.files))


def build_verified_company(
    *,
    legacy_company_id: str,
    company_name: str,
    company_meta_market: str,
    lei: str | None,
    country_code: str | None,
    ticker: str,
    exchange_mic: str,
    security_type: SecurityType,
    currency: str,
    isin: str | None,
    is_active: bool,
    bundles: tuple[LegacyBundleReference, ...],
) -> VerifiedLegacyCompany:
    """构造已验证公司 DTO 并执行 market consistency gate。

    同时完成 ticker canonical 证明、MIC/currency/country 与
    ``CompanyMeta.market`` 的一致性校验，并派生公司/证券 UUIDv5 ID。

    Args:
        legacy_company_id: owner inventory raw company id。
        company_name: ``CompanyMeta.company_name``。
        company_meta_market: ``CompanyMeta.market``。
        lei: manifest 明示的 LEI（可空）。
        country_code: manifest 明示的国家码（可空）。
        ticker: manifest ticker（必须已 canonical）。
        exchange_mic: manifest 明示的 MIC。
        security_type: manifest 明示的证券类型。
        currency: manifest 明示的货币。
        isin: manifest 明示的 ISIN（可空）。
        is_active: manifest 明示的活跃标记。
        bundles: bundle 引用 tuple。

    Returns:
        已验证公司 DTO。

    Raises:
        WorkspaceImportIdentityInconsistentError: ticker 非 canonical、
            MIC/currency/country/market 不一致时抛出。
        ValueError: 其余字段形态违反规则时抛出。
    """

    _validate_nonblank(legacy_company_id, "legacy_company_id")
    _validate_nonblank(company_name, "公司名称")
    _validate_nonblank(company_meta_market, "市场")
    try:
        market = classify_canonical_ticker(ticker)
    except ValueError:
        raise WorkspaceImportIdentityInconsistentError() from None
    _validate_market_consistency(
        market=market,
        company_meta_market=company_meta_market,
        exchange_mic=exchange_mic,
        currency=currency,
        country_code=country_code,
    )
    company_id = CompanyId(derive_company_id(legacy_company_id))
    security_id = SecurityId(derive_security_id(exchange_mic, ticker))
    if not isinstance(is_active, bool):
        raise TypeError("is_active 必须是 bool")
    if not isinstance(security_type, SecurityType):
        raise TypeError("security_type 必须是 SecurityType")
    if lei is not None:
        _validate_nonblank(lei, "LEI")
    security = LegacySecurityMapping(
        security_id=security_id,
        company_id=company_id,
        ticker=ticker,
        exchange_mic=exchange_mic,
        security_type=security_type,
        currency=currency,
        isin=isin,
        is_active=is_active,
    )
    return VerifiedLegacyCompany(
        company_id=company_id,
        legacy_company_id=legacy_company_id,
        company_name=company_name,
        market=company_meta_market,
        lei=lei,
        country_code=country_code,
        security=security,
        bundles=tuple(bundles),
    )


def build_verified_source_definition(
    *,
    source_key: str,
    source_kind: SourceKind,
    display_name: str,
    enabled_by_default: bool,
) -> VerifiedLegacySourceDefinition:
    """构造已验证数据源定义 DTO 并派生 UUIDv5 ID。

    Args:
        source_key: 数据源唯一键。
        source_kind: 数据源种类。
        display_name: 显示名。
        enabled_by_default: 是否默认启用。

    Returns:
        已验证数据源定义 DTO。

    Raises:
        ValueError: 字段形态违反规则时抛出。
    """

    source_definition_id = SourceDefinitionId(derive_source_definition_id(source_key))
    return VerifiedLegacySourceDefinition(
        source_definition_id=source_definition_id,
        source_key=source_key,
        source_kind=source_kind,
        display_name=display_name,
        enabled_by_default=enabled_by_default,
    )


def build_verified_bundle_locator(
    *,
    tenant_id: TenantId,
    exchange_mic: str,
    ticker: str,
    template_name: str,
    relative_locator: str,
    bundle_sha256: str,
    artifact_manifest_sha256: str,
) -> VerifiedResearchBundleLocator:
    """构造已验证 bundle locator DTO 并派生 UUIDv5 ID。

    Args:
        tenant_id: 目标租户标识。
        exchange_mic: 4 位大写 MIC。
        ticker: canonical 大写 ticker。
        template_name: 研究模板名。
        relative_locator: 相对 source root 的 POSIX locator。
        bundle_sha256: descriptor 文件 SHA-256。
        artifact_manifest_sha256: closure artifact manifest SHA-256。

    Returns:
        已验证 bundle locator DTO。

    Raises:
        TypeError: ``tenant_id`` 不是 ``TenantId`` 时抛出。
        ValueError: 字段形态违反规则时抛出。
    """

    locator_id = derive_bundle_locator_id(tenant_id, exchange_mic, ticker, template_name)
    security_id = SecurityId(derive_security_id(exchange_mic, ticker))
    return VerifiedResearchBundleLocator(
        locator_id=locator_id,
        security_id=security_id,
        template_name=template_name,
        repository_key=LEGACY_REPOSITORY_KEY,
        relative_locator=relative_locator,
        bundle_sha256=bundle_sha256,
        artifact_manifest_sha256=artifact_manifest_sha256,
    )


WorkspaceImportJsonValue: TypeAlias = (
    str | int | bool | None | tuple["WorkspaceImportJsonValue", ...] | Mapping[str, "WorkspaceImportJsonValue"]
)
"""canonical JSON 值：只允许 scalar / tuple / mapping。"""


def _validate_canonical_value(value: WorkspaceImportJsonValue) -> None:
    """递归校验 canonical JSON 值的类型白名单。

    Args:
        value: 待校验的值。

    Returns:
        无。

    Raises:
        ValueError: 值含 list、float、非字符串 key 或其它非法类型时抛出。
    """

    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, tuple):
        for item in value:
            _validate_canonical_value(item)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("canonical JSON 只允许字符串 key")
            _validate_canonical_value(item)
        return
    raise ValueError("canonical JSON 只允许 scalar/tuple/mapping")


def _canonical_sha256(*values: WorkspaceImportJsonValue) -> str:
    """对给定值做 canonical JSON 编码并计算 SHA-256。

    编码规则：``json.dumps`` 关闭多余空白（``,``/``:`` 分隔）、
    递归 ``sort_keys=True``、``ensure_ascii=False``；tuple 编码为 JSON
    array、mapping 编码为 JSON object。

    Args:
        values: 参与哈希的 canonical 值（固定字段顺序）。

    Returns:
        64 位小写 SHA-256 十六进制摘要。

    Raises:
        ValueError: 任一值含非法类型时抛出。
    """

    for value in values:
        _validate_canonical_value(value)
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_source_root_fingerprint(
    *,
    companies: tuple[VerifiedLegacyCompany, ...],
    company_projections: tuple[FingerprintCompanyProjection, ...],
    source_root_presence: tuple[FingerprintSourceRootPresence, ...],
    bundle_closures: tuple[FingerprintBundleClosure, ...],
) -> str:
    """计算 ``source_root_fingerprint``。

    覆盖：normalized manifest semantics（由已验证公司投影）、完整
    verified CompanyMeta projections（含 updated_at/aliases）、derived
    source-root presence 与 sorted bundle closure。所有输入先按稳定键
    排序，再整体 canonical SHA-256。

    Args:
        companies: 已验证公司 tuple。
        company_projections: 完整 CompanyMeta 投影 tuple。
        source_root_presence: source root presence tuple。
        bundle_closures: bundle closure 投影 tuple。

    Returns:
        64 位小写 SHA-256 十六进制摘要。

    Raises:
        ValueError: 任一投影形态非法时抛出。
    """

    sorted_companies = tuple(
        sorted(companies, key=lambda company: company.legacy_company_id)
    )
    manifest_semantics: tuple[WorkspaceImportJsonValue, ...] = tuple(
        (
            company.legacy_company_id,
            company.country_code,
            company.lei,
            (
                company.security.ticker,
                company.security.exchange_mic,
                company.security.security_type.value,
                company.security.currency,
                company.security.isin,
                company.security.is_active,
            ),
            tuple(
                (reference.template_name, reference.relative_locator)
                for reference in sorted(
                    company.bundles,
                    key=lambda reference: reference.template_name,
                )
            ),
        )
        for company in sorted_companies
    )
    sorted_projections = tuple(
        sorted(company_projections, key=lambda projection: projection.company_id)
    )
    projection_values: tuple[WorkspaceImportJsonValue, ...] = tuple(
        (
            projection.company_id,
            projection.company_name,
            projection.ticker,
            projection.market,
            projection.resolver_version,
            projection.updated_at,
            projection.aliases,
        )
        for projection in sorted_projections
    )
    sorted_presence = tuple(
        sorted(
            source_root_presence,
            key=lambda presence: (presence.legacy_company_id, presence.source_key),
        )
    )
    presence_values: tuple[WorkspaceImportJsonValue, ...] = tuple(
        (presence.legacy_company_id, presence.source_key, presence.present)
        for presence in sorted_presence
    )
    sorted_closures = tuple(
        sorted(
            bundle_closures,
            key=lambda closure: (closure.target_ticker, closure.template),
        )
    )
    closure_values: tuple[WorkspaceImportJsonValue, ...] = tuple(
        (
            closure.template,
            closure.target_ticker,
            closure.target_company_name,
            closure.descriptor_sha256,
            tuple(
                (file.role, file.relative_locator, file.size_bytes, file.sha256)
                for file in sorted(
                    closure.files,
                    key=lambda file: (file.role, file.relative_locator, file.size_bytes, file.sha256),
                )
            ),
            closure.artifact_manifest_sha256,
        )
        for closure in sorted_closures
    )
    return _canonical_sha256(
        ("workspace-import:source-root-fingerprint:v1",),
        manifest_semantics,
        projection_values,
        presence_values,
        closure_values,
    )


def _request_payload_sha256(
    *,
    schema_version: int,
    migration_id: str,
    companies: tuple[VerifiedLegacyCompany, ...],
    source_definitions: tuple[VerifiedLegacySourceDefinition, ...],
    locators: tuple[VerifiedResearchBundleLocator, ...],
    source_root_fingerprint: str,
) -> str:
    """计算最终请求 canonical payload 的 SHA-256（内部实现）。

    payload 覆盖除 ``staged_payload_sha256`` 自身外的全部 request-owned
    字段（避免自引用）。

    Args:
        schema_version: schema version。
        migration_id: migration id。
        companies: 已验证公司 tuple。
        source_definitions: 派生数据源定义 tuple。
        locators: 已验证 bundle locator tuple。
        source_root_fingerprint: source root fingerprint。

    Returns:
        64 位小写 SHA-256 十六进制摘要。

    Raises:
        ValueError: 任一投影形态非法时抛出。
    """

    companies_payload: tuple[WorkspaceImportJsonValue, ...] = tuple(
        (
            company.legacy_company_id,
            company.company_name,
            company.market,
            company.lei,
            company.country_code,
            (
                company.security.security_id.value,
                company.security.ticker,
                company.security.exchange_mic,
                company.security.security_type.value,
                company.security.currency,
                company.security.isin,
                company.security.is_active,
            ),
            tuple(
                (reference.template_name, reference.relative_locator)
                for reference in sorted(
                    company.bundles,
                    key=lambda reference: reference.template_name,
                )
            ),
        )
        for company in sorted(companies, key=lambda company: company.legacy_company_id)
    )
    source_definitions_payload: tuple[WorkspaceImportJsonValue, ...] = tuple(
        (
            definition.source_key,
            definition.source_kind.value,
            definition.display_name,
            definition.enabled_by_default,
        )
        for definition in sorted(
            source_definitions,
            key=lambda definition: definition.source_key,
        )
    )
    locators_payload: tuple[WorkspaceImportJsonValue, ...] = tuple(
        (
            locator.locator_id,
            locator.security_id.value,
            locator.template_name,
            locator.repository_key,
            locator.relative_locator,
            locator.bundle_sha256,
            locator.artifact_manifest_sha256,
        )
        for locator in sorted(
            locators,
            key=lambda locator: (locator.security_id.value, locator.template_name),
        )
    )
    return _canonical_sha256(
        ("workspace-import:staged-payload:v1",),
        schema_version,
        migration_id,
        companies_payload,
        source_definitions_payload,
        locators_payload,
        source_root_fingerprint,
    )


def compute_staged_payload_sha256(request: WorkspaceImportRequest) -> str:
    """计算 ``staged_payload_sha256``（对外校验入口）。

    Args:
        request: 已持有 source_root_fingerprint 的请求。

    Returns:
        64 位小写 SHA-256 十六进制摘要。

    Raises:
        ValueError: request 形态非法时抛出。
    """

    return _request_payload_sha256(
        schema_version=request.schema_version,
        migration_id=request.migration_id,
        companies=request.companies,
        source_definitions=request.source_definitions,
        locators=request.locators,
        source_root_fingerprint=request.source_root_fingerprint,
    )


def build_workspace_import_request(
    *,
    migration_id: str,
    companies: tuple[VerifiedLegacyCompany, ...],
    source_definitions: tuple[VerifiedLegacySourceDefinition, ...],
    locators: tuple[VerifiedResearchBundleLocator, ...],
    company_projections: tuple[FingerprintCompanyProjection, ...],
    source_root_presence: tuple[FingerprintSourceRootPresence, ...],
    bundle_closures: tuple[FingerprintBundleClosure, ...],
) -> WorkspaceImportRequest:
    """构造带完整 fingerprint 的最终 import 请求。

    先计算 ``source_root_fingerprint``，再对最终 payload 计算
    ``staged_payload_sha256``，最后构造不可变请求。

    Args:
        migration_id: migration id（必须精确固定值）。
        companies: 已验证公司 tuple。
        source_definitions: 派生数据源定义 tuple。
        locators: 已验证 bundle locator tuple。
        company_projections: 完整 CompanyMeta 投影 tuple。
        source_root_presence: source root presence tuple。
        bundle_closures: bundle closure 投影 tuple。

    Returns:
        携带两个 fingerprint 的不可变请求。

    Raises:
        WorkspaceImportManifestInvalidError: migration id 非精确固定值时
            抛出。
        ValueError: 任一投影形态非法时抛出。
    """

    if migration_id != WORKSPACE_IMPORT_MIGRATION_ID:
        raise WorkspaceImportManifestInvalidError()
    source_root_fingerprint = compute_source_root_fingerprint(
        companies=tuple(companies),
        company_projections=tuple(company_projections),
        source_root_presence=tuple(source_root_presence),
        bundle_closures=tuple(bundle_closures),
    )
    staged_payload_sha256 = _request_payload_sha256(
        schema_version=WORKSPACE_IMPORT_SCHEMA_VERSION,
        migration_id=migration_id,
        companies=tuple(companies),
        source_definitions=tuple(source_definitions),
        locators=tuple(locators),
        source_root_fingerprint=source_root_fingerprint,
    )
    return WorkspaceImportRequest(
        schema_version=WORKSPACE_IMPORT_SCHEMA_VERSION,
        migration_id=migration_id,
        companies=tuple(companies),
        source_definitions=tuple(source_definitions),
        locators=tuple(locators),
        source_root_fingerprint=source_root_fingerprint,
        staged_payload_sha256=staged_payload_sha256,
    )


__all__ = [
    "CanonicalTickerMarket",
    "classify_canonical_ticker",
    "FingerprintBundleClosure",
    "FingerprintClosureFile",
    "FingerprintCompanyProjection",
    "FingerprintSourceRootPresence",
    "LEGACY_FINS_FILING_SOURCE_KEY",
    "LEGACY_FINS_MATERIAL_SOURCE_KEY",
    "LEGACY_REPOSITORY_KEY",
    "LegacyBundleReference",
    "LegacySecurityMapping",
    "VerifiedLegacyCompany",
    "VerifiedLegacySourceDefinition",
    "VerifiedResearchBundleLocator",
    "WORKSPACE_IMPORT_MIGRATION_ID",
    "WORKSPACE_IMPORT_SCHEMA_VERSION",
    "WorkspaceImportDriftError",
    "WorkspaceImportError",
    "WorkspaceImportIdentityInconsistentError",
    "WorkspaceImportManifestInvalidError",
    "WorkspaceImportOwnerInvalidError",
    "WorkspaceImportReceipt",
    "WorkspaceImportRepositoryFailureError",
    "WorkspaceImportRequest",
    "WorkspaceImportSchemaUnavailableError",
    "WorkspaceImportUsageError",
    "WorkspaceImportJsonValue",
    "build_verified_bundle_locator",
    "build_verified_company",
    "build_verified_source_definition",
    "build_workspace_import_request",
    "compute_source_root_fingerprint",
    "compute_staged_payload_sha256",
    "derive_bundle_locator_id",
    "derive_company_id",
    "derive_security_id",
    "derive_source_definition_id",
    "derive_workspace_import_marker_id",
]
