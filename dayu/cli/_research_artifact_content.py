"""研究产物内容读取的 neutral 私有 leaf。

只定义 ``ResearchArtifactContentReader`` Protocol、严格递归 JSON 值
类型别名（``JsonValue``）、strict JSON 文本校验 helper
（``validate_json_object_text``）与纯 bytes→UTF-8-SIG text/SHA-256 小
helper，不保存路径、不写文件、不成为 public package export。本 leaf
不得 import bundle/core/workbook/routing owner，owner 模块单向依赖本
leaf。

Protocol 的 ``Path`` 只是原 descriptor reference 的 opaque lookup key，
reader 实现不得对它执行 ``resolve/stat/open``，lookup 必须零 filesystem
I/O。
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NoReturn, Protocol, TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
"""JSON 标量类型别名。"""

JsonValue: TypeAlias = JsonScalar | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
"""递归 JSON 值类型别名。

使用协变容器 ``Sequence`` / ``Mapping`` 表达 JSON 数组与对象，避免
mutable ``list`` / ``dict`` 的类型参数不变性阻碍嵌套 JSON 数据的
赋值；配合 ``validate_json_object_text`` 的运行期严格校验，只表示
标准 JSON 值（不含 NaN/Infinity）。
"""


class ResearchArtifactContentReader(Protocol):
    """闭包安全检查注入的只读内容源。

    ``is_regular_file`` 回答该 key 是否命中已预检的 regular 快照条目；
    ``read_bytes`` 返回该 key 的 immutable bytes；unknown key 必须
    fail closed。实现只做 exact string map lookup，不调用 filesystem。
    """

    def is_regular_file(self, path: Path) -> bool:
        """返回该路径 key 是否命中快照中的 regular 条目。

        Args:
            path: descriptor reference 的 opaque lookup key。

        Returns:
            命中时返回 True，否则返回 False。

        Raises:
            无。
        """
        ...

    def read_bytes(self, path: Path) -> bytes:
        """返回该路径 key 对应的 immutable bytes。

        Args:
            path: descriptor reference 的 opaque lookup key。

        Returns:
            快照绑定的文件完整字节。

        Raises:
            RuntimeError: 该 key 不在快照中时 fail closed。
        """
        ...


def decode_utf8_sig(raw: bytes) -> str:
    """按 UTF-8-SIG 把 bytes 解码为文本（剥离 BOM）。

    Args:
        raw: 待解码的字节。

    Returns:
        解码后的文本。

    Raises:
        UnicodeError: 字节不是合法 UTF-8 时抛出。
    """
    return raw.decode("utf-8-sig")


def _parse_strict_float(raw: str) -> float:
    """把 JSON 数字字面量解析为有限 float，拒绝溢出产生的无穷值。

    Args:
        raw: JSON 数字字面量。

    Returns:
        有限 float 值。

    Raises:
        ValueError: 字面量转换后不是有限值（如 ``1e400`` 溢出为无穷）时抛出。
    """

    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number: {raw}")
    return value


def _reject_non_standard_constant(name: str) -> NoReturn:
    """拒绝 JSON 文本中的非标准常量 ``NaN`` / ``Infinity`` / ``-Infinity``。

    Args:
        name: 非标准 JSON 常量名。

    Returns:
        永不返回。

    Raises:
        ValueError: 恒抛出，表示文本含非标准 JSON 常量。
    """

    raise ValueError(f"non-standard JSON constant: {name}")


def validate_json_object_text(text: str) -> str:
    """strict 校验 JSON 文本：顶层为对象且不含 NaN/Infinity。

    以 ``parse_float`` / ``parse_constant`` 对 JSON 值做运行期严格
    校验：字面量 ``NaN`` / ``Infinity`` / ``-Infinity`` 与溢出为无穷
    的数字一律拒绝，并强制顶层值为对象。校验通过后原样返回同一
    ``text``，调用方对同一 immutable 文本继续执行自己的解析（如
    ``json.loads``），同一文本不存在 TOCTOU 窗口。

    Args:
        text: 待校验的 JSON 文本。

    Returns:
        原样返回传入的 ``text``（校验已通过）。

    Raises:
        ValueError: 文本不是合法 JSON、含非标准常量/无穷数值，或顶层
            值不是对象时抛出。
    """

    payload = json.loads(
        text,
        parse_float=_parse_strict_float,
        parse_constant=_reject_non_standard_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must contain an object")
    return text


def sha256_hex(raw: bytes) -> str:
    """计算 bytes 的 SHA-256 十六进制摘要。

    Args:
        raw: 待哈希的字节。

    Returns:
        64 字符小写 SHA-256 摘要。

    Raises:
        无。
    """
    return hashlib.sha256(raw).hexdigest()
