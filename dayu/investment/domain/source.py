"""投资域 identity/source 严格 DTO 与 closed enum。

本模块是 Slice 1.2 的 frozen strict contract 真源（S12-CTRL-01/05），
定义 identity/source 边界的：

- closed enums：``SecurityType`` / ``SourceKind`` / ``SubscriptionStatus``；
- canonical UUID 强标识：``SourceDefinitionId`` / ``SourceSubscriptionId``，
  复用既有 ``CompanyId`` / ``SecurityId``；
- create/update request 与 read projection 的全部 frozen slots DTO；
- 递归 JSON 值类型（允许 tuple 用于 frozen DTO，拒绝 NaN/Infinity、
  非字符串 key、cycle 与 ``Any``/``object``）。

设计约束：

- 本模块为纯 domain 层，不依赖 Web/Service/Host/Agent/SQLAlchemy；
- 所有文本字段复用 Slice 1.1 check 语义（非空/无首尾空白、MIC 4 位
  大写、currency 3 位大写、country code 可空否则 2 位大写）；
- UUID 唯一 canonical 形态为小写带连字符 ``8-4-4-4-12``，且
  ``str(UUID(value)) == value``；
- 所有 DTO frozen/slots，Mapping 字段防御性复制为只读；
- datetime 必须 aware UTC；bool 不得冒充 int；version 为正整数。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import TypeAlias
from uuid import UUID

from dayu.investment.domain.identifiers import CompanyId, SecurityId, TenantId

_CANONICAL_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_MIC_PATTERN = re.compile(r"^[A-Z]{4}$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
_COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")

JsonScalar: TypeAlias = str | int | float | bool | None
"""JSON 标量：``str/int/finite-float/bool/None``。"""

JsonValue: TypeAlias = JsonScalar | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]
"""递归 JSON 值：允许 tuple（frozen DTO 用）与只读 Mapping。

构造期校验拒绝 NaN/Infinity、非字符串 key 与 ``Any``/``object``。
"""


def _validate_canonical_uuid(value: str, label: str) -> str:
    """校验 canonical UUID 字符串形态。

    Args:
        value: 待校验的 UUID 字符串。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的小写连字符 UUID 字符串。

    Raises:
        ValueError: 值不是小写带连字符 ``8-4-4-4-12`` UUID，或
            ``str(UUID(value)) != value`` 时抛出。
    """

    if _CANONICAL_UUID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} 必须是规范小写 UUID（8-4-4-4-12）")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise ValueError(f"{label} 必须是规范小写 UUID（8-4-4-4-12）") from None
    if str(parsed) != value:
        raise ValueError(f"{label} 必须是规范小写 UUID（8-4-4-4-12）")
    if parsed.int == 0:
        raise ValueError(f"{label} 必须是规范小写 UUID（8-4-4-4-12）")
    return value


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


def _validate_aware_utc(value: datetime, label: str) -> datetime:
    """校验时刻为 aware UTC。

    Args:
        value: 待校验的时刻。
        label: 用于错误消息的中文名称。

    Returns:
        归一化到 UTC 的时刻。

    Raises:
        ValueError: 时刻 naive 或非 UTC 偏移时抛出。
    """

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} 必须是 aware UTC 时刻")
    return value.astimezone(timezone.utc)


def _validate_positive_int(value: int, label: str) -> int:
    """校验为正整数。

    Args:
        value: 待校验的整数。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的整数。

    Raises:
        TypeError: 值不是 ``int`` 时抛出。
        ValueError: 值不为正时抛出。
    """

    if type(value) is not int:
        raise TypeError(f"{label} 必须是 int，禁止 bool 冒充")
    if value <= 0:
        raise ValueError(f"{label} 必须为正整数")
    return value


class SecurityType(Enum):
    """证券类型 closed enum（与 ``securities.security_type`` CHECK 一致）。"""

    EQUITY = "equity"
    ADR = "adr"
    ETF = "etf"
    FUND = "fund"
    BOND = "bond"
    OTHER = "other"


class SourceKind(Enum):
    """数据源种类 closed enum（与 ``source_definitions.source_kind`` CHECK 一致）。"""

    FILING = "filing"
    ANNOUNCEMENT = "announcement"
    INDUSTRY_METRIC = "industry_metric"
    RESEARCH_MATERIAL = "research_material"
    MARKET_PRICE = "market_price"
    FX = "fx"


class SubscriptionStatus(Enum):
    """订阅状态 closed enum（与 ``source_subscriptions.status`` CHECK 一致）。"""

    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class SourceDefinitionId:
    """数据源定义 canonical UUID 强标识。

    Args:
        value: 小写连字符 UUID 字符串。
    """

    value: str

    def __post_init__(self) -> None:
        """构造期校验 canonical UUID。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 值不是规范 UUID 时抛出。
        """

        _validate_canonical_uuid(self.value, "数据源定义标识")

    def __str__(self) -> str:
        """返回原始 UUID 字符串。

        Args:
            无。

        Returns:
            小写连字符 UUID 字符串。

        Raises:
            无。
        """

        return self.value


@dataclass(frozen=True, slots=True)
class SourceSubscriptionId:
    """数据源订阅 canonical UUID 强标识。

    Args:
        value: 小写连字符 UUID 字符串。
    """

    value: str

    def __post_init__(self) -> None:
        """构造期校验 canonical UUID。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 值不是规范 UUID 时抛出。
        """

        _validate_canonical_uuid(self.value, "数据源订阅标识")

    def __str__(self) -> str:
        """返回原始 UUID 字符串。

        Args:
            无。

        Returns:
            小写连字符 UUID 字符串。

        Raises:
            无。
        """

        return self.value


@dataclass(frozen=True, slots=True)
class CompanyCreateRequest:
    """创建公司请求。

    Args:
        company_id: 公司标识（canonical UUID）。
        legal_name: 公司法定名称，非空且无首尾空白。
        lei: 可空 LEI，非空时无首尾空白。
        country_code: 可空国家码，非空时为 2 位大写字母。
    """

    company_id: CompanyId
    legal_name: str
    lei: str | None
    country_code: str | None

    def __post_init__(self) -> None:
        """构造期严格校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ``company_id`` 不是 ``CompanyId`` 时抛出。
            ValueError: 文本字段违反规则时抛出。
        """

        if not isinstance(self.company_id, CompanyId):
            raise TypeError("company_id 必须是 CompanyId")
        _validate_nonblank(self.legal_name, "公司法定名称")
        if self.lei is not None:
            _validate_nonblank(self.lei, "LEI")
        if self.country_code is not None:
            _validate_pattern(self.country_code, _COUNTRY_CODE_PATTERN, "国家码")


@dataclass(frozen=True, slots=True)
class SecurityCreateRequest:
    """创建证券请求。

    Args:
        security_id: 证券标识（canonical UUID）。
        company_id: 所属公司标识。
        ticker: 证券代码，非空且无首尾空白。
        exchange_mic: 交易所 MIC，4 位大写。
        security_type: 证券类型 closed enum。
        currency: 3 位大写货币代码。
        isin: 可空 ISIN，非空时无首尾空白。
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
            TypeError: 标识类型非法或 ``is_active`` 不是 bool 时抛出。
            ValueError: 文本字段违反规则时抛出。
        """

        if not isinstance(self.security_id, SecurityId):
            raise TypeError("security_id 必须是 SecurityId")
        if not isinstance(self.company_id, CompanyId):
            raise TypeError("company_id 必须是 CompanyId")
        if not isinstance(self.security_type, SecurityType):
            raise TypeError("security_type 必须是 SecurityType")
        if not isinstance(self.is_active, bool):
            raise TypeError("is_active 必须是 bool，禁止 int 冒充")
        _validate_nonblank(self.ticker, "证券代码")
        _validate_pattern(self.exchange_mic, _MIC_PATTERN, "交易所 MIC")
        _validate_pattern(self.currency, _CURRENCY_PATTERN, "货币代码")
        if self.isin is not None:
            _validate_nonblank(self.isin, "ISIN")


@dataclass(frozen=True, slots=True)
class CompanySecurityRegistration:
    """公司+证券原子注册请求。

    ``company.company_id`` 必须与 ``security.company_id`` 相同。

    Args:
        company: 公司创建请求。
        security: 证券创建请求。
    """

    company: CompanyCreateRequest
    security: SecurityCreateRequest

    def __post_init__(self) -> None:
        """构造期校验公司/证券 company_id 一致。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 任一请求类型非法时抛出。
            ValueError: 两侧 ``company_id`` 不一致时抛出。
        """

        if not isinstance(self.company, CompanyCreateRequest):
            raise TypeError("company 必须是 CompanyCreateRequest")
        if not isinstance(self.security, SecurityCreateRequest):
            raise TypeError("security 必须是 SecurityCreateRequest")
        if self.company.company_id != self.security.company_id:
            raise ValueError("company 与 security 的 company_id 必须相同")


@dataclass(frozen=True, slots=True)
class CompanyProjection:
    """公司读取投影。

    Args:
        company_id: 公司标识。
        legal_name: 公司法定名称。
        lei: 可空 LEI。
        country_code: 可空国家码。
        created_at: aware UTC 创建时刻。
        updated_at: aware UTC 更新时刻。
        version: 正整数乐观版本。
    """

    company_id: CompanyId
    legal_name: str
    lei: str | None
    country_code: str | None
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        """构造期严格校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 标识类型非法时抛出。
            ValueError: 文本/时刻/版本违反规则时抛出。
        """

        if not isinstance(self.company_id, CompanyId):
            raise TypeError("company_id 必须是 CompanyId")
        _validate_nonblank(self.legal_name, "公司法定名称")
        if self.lei is not None:
            _validate_nonblank(self.lei, "LEI")
        if self.country_code is not None:
            _validate_pattern(self.country_code, _COUNTRY_CODE_PATTERN, "国家码")
        object.__setattr__(self, "created_at", _validate_aware_utc(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _validate_aware_utc(self.updated_at, "updated_at"))
        _validate_positive_int(self.version, "version")


@dataclass(frozen=True, slots=True)
class SecurityProjection:
    """证券读取投影。

    Args:
        security_id: 证券标识。
        company_id: 所属公司标识。
        ticker: 证券代码。
        exchange_mic: 交易所 MIC。
        security_type: 证券类型。
        currency: 货币代码。
        isin: 可空 ISIN。
        is_active: 是否活跃。
        created_at: aware UTC 创建时刻。
        updated_at: aware UTC 更新时刻。
        version: 正整数乐观版本。
    """

    security_id: SecurityId
    company_id: CompanyId
    ticker: str
    exchange_mic: str
    security_type: SecurityType
    currency: str
    isin: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        """构造期严格校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 标识/枚举/bool 类型非法时抛出。
            ValueError: 文本/时刻/版本违反规则时抛出。
        """

        if not isinstance(self.security_id, SecurityId):
            raise TypeError("security_id 必须是 SecurityId")
        if not isinstance(self.company_id, CompanyId):
            raise TypeError("company_id 必须是 CompanyId")
        if not isinstance(self.security_type, SecurityType):
            raise TypeError("security_type 必须是 SecurityType")
        if not isinstance(self.is_active, bool):
            raise TypeError("is_active 必须是 bool")
        _validate_nonblank(self.ticker, "证券代码")
        _validate_pattern(self.exchange_mic, _MIC_PATTERN, "交易所 MIC")
        _validate_pattern(self.currency, _CURRENCY_PATTERN, "货币代码")
        if self.isin is not None:
            _validate_nonblank(self.isin, "ISIN")
        object.__setattr__(self, "created_at", _validate_aware_utc(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _validate_aware_utc(self.updated_at, "updated_at"))
        _validate_positive_int(self.version, "version")


@dataclass(frozen=True, slots=True)
class RegisteredCompanySecurity:
    """公司+证券注册结果投影。

    Args:
        company: 公司投影。
        security: 证券投影。
    """

    company: CompanyProjection
    security: SecurityProjection

    def __post_init__(self) -> None:
        """构造期校验类型与 company_id 一致。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 任一投影类型非法时抛出。
            ValueError: 两侧 ``company_id`` 不一致时抛出。
        """

        if not isinstance(self.company, CompanyProjection):
            raise TypeError("company 必须是 CompanyProjection")
        if not isinstance(self.security, SecurityProjection):
            raise TypeError("security 必须是 SecurityProjection")
        if self.company.company_id != self.security.company_id:
            raise ValueError("company 与 security 的 company_id 必须相同")


@dataclass(frozen=True, slots=True)
class SourceDefinitionCreateRequest:
    """创建数据源定义请求。

    Args:
        source_definition_id: 数据源定义标识（canonical UUID）。
        source_key: 数据源唯一键，非空且无首尾空白。
        source_kind: 数据源种类 closed enum。
        display_name: 显示名，非空且无首尾空白。
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
class SourceDefinitionProjection:
    """数据源定义读取投影。

    Args:
        source_definition_id: 数据源定义标识。
        source_key: 数据源唯一键。
        source_kind: 数据源种类。
        display_name: 显示名。
        enabled_by_default: 是否默认启用。
        created_at: aware UTC 创建时刻。
        updated_at: aware UTC 更新时刻。
        version: 正整数乐观版本。
    """

    source_definition_id: SourceDefinitionId
    source_key: str
    source_kind: SourceKind
    display_name: str
    enabled_by_default: bool
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        """构造期严格校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 标识/枚举/bool 类型非法时抛出。
            ValueError: 文本/时刻/版本违反规则时抛出。
        """

        if not isinstance(self.source_definition_id, SourceDefinitionId):
            raise TypeError("source_definition_id 必须是 SourceDefinitionId")
        if not isinstance(self.source_kind, SourceKind):
            raise TypeError("source_kind 必须是 SourceKind")
        if not isinstance(self.enabled_by_default, bool):
            raise TypeError("enabled_by_default 必须是 bool")
        _validate_nonblank(self.source_key, "数据源键")
        _validate_nonblank(self.display_name, "数据源显示名")
        object.__setattr__(self, "created_at", _validate_aware_utc(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _validate_aware_utc(self.updated_at, "updated_at"))
        _validate_positive_int(self.version, "version")


def _validate_optional_target(
    company_id: CompanyId | None,
    security_id: SecurityId | None,
) -> None:
    """校验订阅目标至多一个非空。

    Args:
        company_id: 可空公司标识。
        security_id: 可空证券标识。

    Returns:
        无。

    Raises:
        TypeError: 任一标识类型非法时抛出。
        ValueError: 两者同时非空时抛出。
    """

    if company_id is not None and not isinstance(company_id, CompanyId):
        raise TypeError("company_id 必须是 CompanyId 或 None")
    if security_id is not None and not isinstance(security_id, SecurityId):
        raise TypeError("security_id 必须是 SecurityId 或 None")
    if company_id is not None and security_id is not None:
        raise ValueError("company_id 与 security_id 至多一个非空")


@dataclass(frozen=True, slots=True)
class SourceSubscriptionCreateRequest:
    """创建数据源订阅请求。

    Args:
        subscription_id: 订阅标识（canonical UUID）。
        source_definition_id: 数据源定义标识。
        company_id: 可空公司目标。
        security_id: 可空证券目标；与 company_id 至多一个非空。
        status: 订阅状态 closed enum。
        config: 递归 JSON 配置映射。
    """

    subscription_id: SourceSubscriptionId
    source_definition_id: SourceDefinitionId
    company_id: CompanyId | None
    security_id: SecurityId | None
    status: SubscriptionStatus
    config: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        """构造期严格校验并防御性冻结 config。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 标识/枚举类型非法时抛出。
            ValueError: 目标互斥或 JSON 非法时抛出。
        """

        if not isinstance(self.subscription_id, SourceSubscriptionId):
            raise TypeError("subscription_id 必须是 SourceSubscriptionId")
        if not isinstance(self.source_definition_id, SourceDefinitionId):
            raise TypeError("source_definition_id 必须是 SourceDefinitionId")
        if not isinstance(self.status, SubscriptionStatus):
            raise TypeError("status 必须是 SubscriptionStatus")
        _validate_optional_target(self.company_id, self.security_id)
        if not isinstance(self.config, Mapping):
            raise TypeError("config 必须是 Mapping")
        object.__setattr__(self, "config", _deep_freeze(self.config, "config"))


@dataclass(frozen=True, slots=True)
class SourceSubscriptionUpdateRequest:
    """更新数据源订阅请求（target/source/id 不可变）。

    Args:
        status: 订阅状态 closed enum。
        config: 递归 JSON 配置映射。
    """

    status: SubscriptionStatus
    config: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        """构造期严格校验并防御性冻结 config。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 状态或 config 类型非法时抛出。
            ValueError: JSON 非法时抛出。
        """

        if not isinstance(self.status, SubscriptionStatus):
            raise TypeError("status 必须是 SubscriptionStatus")
        if not isinstance(self.config, Mapping):
            raise TypeError("config 必须是 Mapping")
        object.__setattr__(self, "config", _deep_freeze(self.config, "config"))


@dataclass(frozen=True, slots=True)
class SourceSubscriptionProjection:
    """数据源订阅读取投影。

    Args:
        subscription_id: 订阅标识。
        tenant_id: 所属租户。
        source_definition_id: 数据源定义标识。
        company_id: 可空公司目标。
        security_id: 可空证券目标。
        status: 订阅状态。
        config: 递归 JSON 配置映射。
        created_at: aware UTC 创建时刻。
        updated_at: aware UTC 更新时刻。
        version: 正整数乐观版本。
    """

    subscription_id: SourceSubscriptionId
    tenant_id: TenantId
    source_definition_id: SourceDefinitionId
    company_id: CompanyId | None
    security_id: SecurityId | None
    status: SubscriptionStatus
    config: Mapping[str, JsonValue]
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        """构造期严格校验并防御性冻结 config。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 标识/枚举类型非法时抛出。
            ValueError: 文本/时刻/版本/JSON 违反规则时抛出。
        """

        if not isinstance(self.subscription_id, SourceSubscriptionId):
            raise TypeError("subscription_id 必须是 SourceSubscriptionId")
        if not isinstance(self.tenant_id, TenantId):
            raise TypeError("tenant_id 必须是 TenantId")
        if not isinstance(self.source_definition_id, SourceDefinitionId):
            raise TypeError("source_definition_id 必须是 SourceDefinitionId")
        if not isinstance(self.status, SubscriptionStatus):
            raise TypeError("status 必须是 SubscriptionStatus")
        _validate_optional_target(self.company_id, self.security_id)
        if not isinstance(self.config, Mapping):
            raise TypeError("config 必须是 Mapping")
        object.__setattr__(self, "config", _deep_freeze(self.config, "config"))
        object.__setattr__(self, "created_at", _validate_aware_utc(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _validate_aware_utc(self.updated_at, "updated_at"))
        _validate_positive_int(self.version, "version")


def _deep_freeze(value: JsonValue, label: str) -> JsonValue:
    """递归校验并构造 JSON 值的深度不可变副本。

    规则：

    - Mapping 递归复制为 ``MappingProxyType``（嵌套 Mapping 同样递归
      冻结），不保留 caller 的任何可变引用；
    - tuple 递归复制为新 tuple；拒绝 list；
    - 拒绝 cycle、非字符串 key、NaN/Infinity 与非法值类型。

    Args:
        value: 待冻结的 JSON 值。
        label: 用于错误消息的中文名称。

    Returns:
        深度不可变的 JSON 值副本。

    Raises:
        ValueError: 存在非法 key、NaN/Infinity、cycle、list 或非法
            值类型时抛出。
    """

    return _deep_freeze_value(value, label, set())


def _deep_freeze_value(value: JsonValue, label: str, seen: set[int]) -> JsonValue:
    """递归冻结 JSON 值的内部实现。

    Args:
        value: 待冻结的 JSON 值。
        label: 用于错误消息的中文名称。
        seen: 已访问对象 id 集合（cycle 检测）。

    Returns:
        深度不可变的 JSON 值副本。

    Raises:
        ValueError: 值类型非法、非有限 float、非字符串 key、cycle
            或 list 时抛出。
    """

    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{label} 拒绝 NaN 或 Infinity")
        return value
    if isinstance(value, tuple):
        if id(value) in seen:
            raise ValueError(f"{label} 拒绝循环引用")
        seen.add(id(value))
        frozen_items = tuple(
            _deep_freeze_value(item, label, seen) for item in value
        )
        seen.discard(id(value))
        return frozen_items
    if isinstance(value, list):
        raise ValueError(f"{label} 拒绝 list，只允许 tuple")
    if isinstance(value, Mapping):
        if id(value) in seen:
            raise ValueError(f"{label} 拒绝循环引用")
        seen.add(id(value))
        frozen_mapping = {
            key: _deep_freeze_value(item, label, seen)
            for key, item in value.items()
        }
        seen.discard(id(value))
        for key in frozen_mapping:
            if not isinstance(key, str):
                raise ValueError(f"{label} 只允许字符串 key")
        return MappingProxyType(frozen_mapping)
    raise ValueError(f"{label} 含非法 JSON 值类型")


__all__ = [
    "CompanyCreateRequest",
    "CompanyProjection",
    "CompanySecurityRegistration",
    "JsonScalar",
    "JsonValue",
    "RegisteredCompanySecurity",
    "SecurityCreateRequest",
    "SecurityProjection",
    "SecurityType",
    "SourceDefinitionCreateRequest",
    "SourceDefinitionId",
    "SourceDefinitionProjection",
    "SourceKind",
    "SourceSubscriptionCreateRequest",
    "SourceSubscriptionId",
    "SourceSubscriptionProjection",
    "SourceSubscriptionUpdateRequest",
    "SubscriptionStatus",
]
