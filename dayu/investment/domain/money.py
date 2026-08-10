"""投资域金额、数量与 UTC 时间值工具。

本模块集中定义投资域三类核心值：

- ``Money``：金额值对象，由有限非负 ``Decimal`` 与三位大写货币代码构成；
- ``Quantity``：数量值对象，由有限非负 ``Decimal`` 构成，禁止 ``float``；
- UTC 时间工具：``utc_now`` / ``parse_utc`` / ``to_utc_iso``。

设计约束：

- 所有数值必须是 ``Decimal`` 实例，拒绝 ``float`` / ``bool`` / ``int``；
- ``NaN`` / ``Infinity`` / 负数一律 fail closed；
- 金额的加减与比较要求两侧货币相同，否则 fail closed；
- 本模块只提供值对象语义（构造、校验、同货币算术），业务规则
  （账本分录、费用分摊等）属于后续 slice 的职责。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

_CURRENCY_CODE_PATTERN = re.compile(r"^[A-Z]{3}$")


def _validate_finite_non_negative(value: Decimal, label: str) -> Decimal:
    """校验数值为有限且非负的 Decimal。

    Args:
        value: 待校验的数值。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的原始 ``Decimal``。

    Raises:
        TypeError: ``value`` 不是 ``Decimal`` 实例时抛出。
        ValueError: 数值为 NaN/Infinity 或负数时抛出。
    """

    if not isinstance(value, Decimal):
        raise TypeError(f"{label}必须是 Decimal，禁止 float/bool/int")
    if not value.is_finite():
        raise ValueError(f"{label}必须是有限数值，禁止 NaN 或 Infinity")
    if value < 0:
        raise ValueError(f"{label}必须为非负数")
    return value


def _validate_currency(currency: str) -> str:
    """校验货币代码为三位大写字母。

    Args:
        currency: 待校验的货币代码字符串。

    Returns:
        校验通过的货币代码。

    Raises:
        TypeError: ``currency`` 不是字符串时抛出。
        ValueError: 货币代码为空、非三位或含小写字母时抛出。
    """

    if not isinstance(currency, str):
        raise TypeError("货币代码必须是字符串")
    if not _CURRENCY_CODE_PATTERN.fullmatch(currency):
        raise ValueError("货币代码必须是三位大写字母（ISO 4217 形态）")
    return currency


def _require_same_currency(left: Money, right: Money) -> None:
    """要求两个金额货币相同。

    Args:
        left: 参与运算的左侧金额。
        right: 参与运算的右侧金额。

    Returns:
        无。

    Raises:
        ValueError: 两侧货币代码不同时抛出。
    """

    if left.currency != right.currency:
        raise ValueError(f"货币不同不能运算：{left.currency} vs {right.currency}")


@dataclass(frozen=True)
class Money:
    """金额值对象。

    由有限非负 ``Decimal`` 金额与三位大写货币代码组成；金额不可变，
    任何运算都产生新实例，禁止原地修改。
    """

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        """构造期校验金额与货币。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 金额不是 ``Decimal`` 实例时抛出。
            ValueError: 金额为 NaN/Infinity/负数，或货币代码非法时抛出。
        """

        _validate_finite_non_negative(self.amount, "金额")
        _validate_currency(self.currency)

    def add(self, other: Money) -> Money:
        """与同货币金额相加。

        Args:
            other: 参与相加的另一金额。

        Returns:
            同货币下的金额和。

        Raises:
            ValueError: 两侧货币代码不同时抛出。
        """

        _require_same_currency(self, other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def subtract(self, other: Money) -> Money:
        """与同货币金额相减，结果必须仍为非负。

        Args:
            other: 参与相减的另一金额。

        Returns:
            同货币下的金额差。

        Raises:
            ValueError: 货币代码不同，或相减结果为负数时抛出。
        """

        _require_same_currency(self, other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __lt__(self, other: Money) -> bool:
        """小于比较，要求两侧货币相同。

        Args:
            other: 参与比较的另一金额。

        Returns:
            左侧金额是否小于右侧金额。

        Raises:
            ValueError: 两侧货币代码不同时抛出。
        """

        _require_same_currency(self, other)
        return self.amount < other.amount


@dataclass(frozen=True)
class Quantity:
    """数量值对象。

    由有限非负 ``Decimal`` 构成，禁止使用 ``float``；数量不可变，
    任何运算都产生新实例。
    """

    value: Decimal

    def __post_init__(self) -> None:
        """构造期校验数量。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 数量不是 ``Decimal`` 实例时抛出。
            ValueError: 数量为 NaN/Infinity 或负数时抛出。
        """

        _validate_finite_non_negative(self.value, "数量")

    def add(self, other: Quantity) -> Quantity:
        """与另一数量相加。

        Args:
            other: 参与相加的另一数量。

        Returns:
            相加后的数量。

        Raises:
            无。
        """

        return Quantity(value=self.value + other.value)

    def subtract(self, other: Quantity) -> Quantity:
        """与另一数量相减，结果必须仍为非负。

        Args:
            other: 参与相减的另一数量。

        Returns:
            相减后的数量。

        Raises:
            ValueError: 相减结果为负数时抛出。
        """

        return Quantity(value=self.value - other.value)

    def __lt__(self, other: Quantity) -> bool:
        """小于比较。

        Args:
            other: 参与比较的另一数量。

        Returns:
            当前数量是否小于另一数量。

        Raises:
            无。
        """

        return self.value < other.value


def utc_now() -> datetime:
    """返回当前 UTC 时间。

    Args:
        无。

    Returns:
        带 ``timezone.utc`` 时区信息的当前时刻。

    Raises:
        无。
    """

    return datetime.now(timezone.utc)


def _is_aware_utc_offset(value: datetime) -> bool:
    """判断时刻是否携带有效的 UTC 偏移（aware）。

    ``datetime`` 的 aware 判定要求 ``tzinfo`` 与 ``utcoffset()`` 均非
    ``None``；仅 ``tzinfo`` 非空而偏移为空的输入在语义上仍是 naive，
    不得依赖本机时区换算。

    Args:
        value: 待判断的时刻。

    Returns:
        ``tzinfo`` 与 ``utcoffset()`` 均非 ``None`` 时返回 True，否则
        返回 False。

    Raises:
        无。
    """

    return value.tzinfo is not None and value.utcoffset() is not None


def parse_utc(value: str) -> datetime:
    """把 ISO 8601 字符串解析为带 UTC 时区的时刻。

    Args:
        value: ISO 8601 格式的时间字符串。

    Returns:
        带 ``timezone.utc`` 时区信息的时刻。

    Raises:
        ValueError: 输入无法解析，或 ``tzinfo`` 为 ``None`` /
            ``utcoffset()`` 为 ``None``（naive）时抛出。
    """

    parsed = datetime.fromisoformat(value)
    if not _is_aware_utc_offset(parsed):
        raise ValueError("时间字符串必须携带有效时区偏移，拒绝 naive 输入")
    return parsed.astimezone(timezone.utc)


def to_utc_iso(value: datetime) -> str:
    """把时刻序列化为 UTC ISO 8601 字符串。

    Args:
        value: 待序列化的时刻。

    Returns:
        UTC 时区下的 ISO 8601 字符串（形如 ``2026-08-10T07:46:02+00:00``）。

    Raises:
        ValueError: ``tzinfo`` 为 ``None`` 或 ``utcoffset()`` 为
            ``None``（naive）时抛出。
    """

    if not _is_aware_utc_offset(value):
        raise ValueError("时刻必须携带有效时区偏移，拒绝 naive 输入")
    return value.astimezone(timezone.utc).isoformat()


__all__ = [
    "Money",
    "Quantity",
    "parse_utc",
    "to_utc_iso",
    "utc_now",
]
