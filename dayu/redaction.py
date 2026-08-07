"""输出脱敏模块。

提供 secret-shaped 字符串的检测与脱敏原语，以及一个
在所有公开输出路径（usage、help、error）中自动脱敏的
argparse 解析器基类。

模块职责：
- 定义 secret-shaped 字符串的正则模式。
- 提供检测与替换函数。
- 提供 ``RedactingArgumentParser`` 供解析器继承。

本模块是轻量叶模块——不依赖任何 dayu 子包，
可被 ``utils/`` 工具脚本安全导入而不触发 CLI/Engine 等重型初始化。
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import NoReturn

# ---------------------------------------------------------------------------
# 共享脱敏原语
# ---------------------------------------------------------------------------

SECRET_KEY_PATTERN = re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}")
"""匹配 secret-shaped 字符串（``sk-`` 前缀 + ≥20 位字母数字/连字符）。"""

REDACTED_SECRET = "<redacted>"
"""脱敏替换文本。"""


def has_secret_shapes(text: str) -> bool:
    """检测文本中是否包含 secret-shaped 字符串。

    参数:
        text: 待检查文本。

    返回值:
        命中共享 secret-key 形状时返回 ``True``。

    异常:
        无。
    """

    return SECRET_KEY_PATTERN.search(text) is not None


def redact_secret_shapes(text: str) -> str:
    """替换文本中的全部 secret-shaped 值并保留其余诊断上下文。

    参数:
        text: 可能包含敏感形状的报告文本。

    返回值:
        所有命中均替换为 ``<redacted>`` 的文本。

    异常:
        无。
    """

    return SECRET_KEY_PATTERN.sub(REDACTED_SECRET, text)


# ---------------------------------------------------------------------------
# 脱敏 argparse 解析器
# ---------------------------------------------------------------------------


class RedactingArgumentParser(argparse.ArgumentParser):
    """通过公开扩展点净化 argparse 输出中的 secret-shaped 值。

    重写 ``format_usage()``、``format_help()`` 与 ``error()``
    三个公开扩展点，确保 help、usage、error 等全部输出路径
    中的 secret-shaped 值均被脱敏。
    """

    def format_usage(self) -> str:
        """返回脱敏后的 usage 文本。

        参数:
            无。

        返回值:
            已净化 secret-shaped 值的 usage 字符串。

        异常:
            无。
        """
        return redact_secret_shapes(super().format_usage())

    def format_help(self) -> str:
        """返回脱敏后的帮助文本。

        参数:
            无。

        返回值:
            已净化 secret-shaped 值的帮助字符串。

        异常:
            无。
        """
        return redact_secret_shapes(super().format_help())

    def error(self, message: str) -> NoReturn:
        """用脱敏后的错误消息保留 argparse 标准失败流程。

        与父类行为一致：先输出 usage 到 stderr，再以退出码 ``2``
        终止；prog 与 message 均通过 ``redact_secret_shapes`` 脱敏。

        参数:
            message: argparse 根据原始命令行参数生成的错误说明。

        返回值:
            永不返回。

        异常:
            SystemExit: 通过 ``self.exit(2, ...)`` 保持标准退出码 ``2``。
        """
        self.print_usage(sys.stderr)
        args = {"prog": redact_secret_shapes(self.prog), "message": redact_secret_shapes(message)}
        self.exit(2, f"{args['prog']}: error: {args['message']}\n")
