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
import os
import re
import sys
from typing import NoReturn

# ---------------------------------------------------------------------------
# 共享脱敏原语
# ---------------------------------------------------------------------------

SECRET_KEY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?:sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35})"
    r"(?![A-Za-z0-9_-])"
)
"""匹配带可靠 provider 前缀的 secret-shaped 字符串。"""

_SECRET_ENV_NAME_PATTERN = re.compile(
    r"(?:[A-Z][A-Z0-9_]*_(?:API_KEY|AUTH_TOKEN|ACCESS_TOKEN)|HF_TOKEN)"
)
"""匹配本进程中承载 provider 凭据的环境变量名。"""

_MIN_DYNAMIC_SECRET_LENGTH = 16
"""动态环境凭据参与检测与替换的最短长度，避免短测试值污染普通文本。"""

_MIN_DYNAMIC_HEX_SECRET_LENGTH = 32
"""仅在环境候选资格判断中接受纯十六进制 token 的最短长度。"""

_DYNAMIC_HEX_SECRET_CHARACTERS = frozenset("0123456789abcdefABCDEF")
"""环境候选资格判断允许的十六进制字符集合，不用于扫描任意文本。"""

REDACTED_SECRET = "<redacted>"
"""脱敏替换文本。"""


def _is_secret_like_environment_value(value: str) -> bool:
    """判断环境变量值是否具备凭据 token 的基本形态。

    资格判断只作用于名称已符合凭据约定的环境变量值，不对待扫描文本执行裸十六进制
    搜索。空白短语与纯字母普通词会被拒绝；至少两类字符组成的 token，或至少 32 位的
    十六进制 token，会进入后续精确值检测。

    参数:
        value: 未经裁剪的原始环境变量值。

    返回值:
        值满足长度、无空白与 token 形态约束时返回 ``True``。

    异常:
        无。
    """

    if len(value) < _MIN_DYNAMIC_SECRET_LENGTH:
        return False
    if any(character.isspace() for character in value):
        return False
    if (
        len(value) >= _MIN_DYNAMIC_HEX_SECRET_LENGTH
        and all(character in _DYNAMIC_HEX_SECRET_CHARACTERS for character in value)
    ):
        return True

    character_classes = (
        any(character.isalpha() for character in value),
        any(character.isdigit() for character in value),
        any(not character.isalnum() for character in value),
    )
    return sum(character_classes) >= 2


def _known_environment_secret_values() -> tuple[str, ...]:
    """收集当前进程中需要精确保护的 provider 凭据值。

    环境变量在每次调用时重新读取，因此同一进程内轮换凭据后无需刷新缓存。只有名称
    具有明确凭据语义且通过 token 资格判断的值才会进入结果；值本身保持原样，以精确
    保护实际配置，同时避免短测试值、空白短语与纯字母普通词污染文本扫描。

    参数:
        无。

    返回值:
        按长度降序排列并去重的当前环境凭据值。

    异常:
        无。
    """

    values = {
        value
        for name, value in os.environ.items()
        if _SECRET_ENV_NAME_PATTERN.fullmatch(name)
        and _is_secret_like_environment_value(value)
    }
    return tuple(sorted(values, key=lambda value: (-len(value), value)))


def has_secret_shapes(text: str) -> bool:
    """检测文本中是否包含 secret-shaped 字符串。

    参数:
        text: 待检查文本。

    返回值:
        命中共享 secret-key 形状时返回 ``True``。

    异常:
        无。
    """

    if SECRET_KEY_PATTERN.search(text) is not None:
        return True
    return any(value in text for value in _known_environment_secret_values())


def redact_secret_shapes(text: str) -> str:
    """替换文本中的全部 secret-shaped 值并保留其余诊断上下文。

    参数:
        text: 可能包含敏感形状的报告文本。

    返回值:
        所有命中均替换为 ``<redacted>`` 的文本。

    异常:
        无。
    """

    redacted = SECRET_KEY_PATTERN.sub(REDACTED_SECRET, text)
    for value in _known_environment_secret_values():
        redacted = redacted.replace(value, REDACTED_SECRET)
    return redacted


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
