"""``DayuCliArgumentParser`` 输出脱敏回归测试。

验证 error / usage / help / prog 输出中对 secret-shaped 字符串（``sk-`` 前缀）
的脱敏行为。所有测试仅使用显然虚构的 secret-shaped 值。
"""

from __future__ import annotations

import pytest

from dayu.cli.arg_parsing import DayuCliArgumentParser
from dayu.redaction import REDACTED_SECRET, redact_secret_shapes

# ---------------------------------------------------------------------------
# 虚构的 secret-shaped 测试值（仅用于测试，非真实密钥）
# ---------------------------------------------------------------------------

_SECRET_LIKE_VALUE = "sk-test-secret-key-with-enough-chars-12345"
"""虚构的 secret-shaped 值，长度 ≥20 字符，符合 ``sk-`` 前缀模式。"""


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _make_parser(
    prog: str = "dayu",
    description: str | None = None,
    epilog: str | None = None,
) -> DayuCliArgumentParser:
    """创建一个最小化的 ``DayuCliArgumentParser`` 供测试使用。

    参数:
        prog: 程序名。
        description: 描述文本。
        epilog: 结语文本。

    返回值:
        已配置的解析器实例。
    """
    if description is not None and epilog is not None:
        parser = DayuCliArgumentParser(prog=prog, description=description, epilog=epilog)
    elif description is not None:
        parser = DayuCliArgumentParser(prog=prog, description=description)
    elif epilog is not None:
        parser = DayuCliArgumentParser(prog=prog, epilog=epilog)
    else:
        parser = DayuCliArgumentParser(prog=prog)
    parser.add_argument("--name", type=str, help="测试参数")
    return parser


# ---------------------------------------------------------------------------
# format_usage 脱敏
# ---------------------------------------------------------------------------


class TestFormatUsageRedaction:
    """验证 ``format_usage()`` 对 secret-shaped 值的脱敏。"""

    def test_usage_redacts_secret_in_prog(self) -> None:
        """prog 中包含 secret-shaped 值时 usage 应脱敏。"""
        parser = _make_parser(prog=f"myapp --key={_SECRET_LIKE_VALUE}")
        usage = parser.format_usage()
        assert _SECRET_LIKE_VALUE not in usage
        assert REDACTED_SECRET in usage

    def test_usage_no_secret_unchanged(self) -> None:
        """无 secret-shaped 值时 usage 应保持不变。"""
        parser = _make_parser(prog="python -m dayu.cli")
        usage = parser.format_usage()
        assert "python -m dayu.cli" in usage
        assert REDACTED_SECRET not in usage


# ---------------------------------------------------------------------------
# format_help 脱敏
# ---------------------------------------------------------------------------


class TestFormatHelpRedaction:
    """验证 ``format_help()`` 对 secret-shaped 值的脱敏。"""

    def test_help_redacts_secret_in_description(self) -> None:
        """description 中包含 secret-shaped 值时 help 应脱敏。"""
        parser = _make_parser(description=f"工具描述 {_SECRET_LIKE_VALUE}")
        help_text = parser.format_help()
        assert _SECRET_LIKE_VALUE not in help_text
        assert REDACTED_SECRET in help_text

    def test_help_no_secret_unchanged(self) -> None:
        """无 secret-shaped 值时 help 应保持不变。"""
        parser = _make_parser(description="公司财报分析工具")
        help_text = parser.format_help()
        assert "公司财报分析工具" in help_text
        assert REDACTED_SECRET not in help_text

    def test_help_redacts_secret_in_epilog(self) -> None:
        """epilog 中包含 secret-shaped 值时 help 应脱敏。"""
        parser = _make_parser(epilog=f"API 密钥: {_SECRET_LIKE_VALUE}")
        help_text = parser.format_help()
        assert _SECRET_LIKE_VALUE not in help_text
        assert REDACTED_SECRET in help_text


# ---------------------------------------------------------------------------
# error 脱敏（使用 capsys）
# ---------------------------------------------------------------------------


class TestErrorRedaction:
    """验证 ``error()`` 对 secret-shaped 值的脱敏。"""

    def test_error_redacts_secret_in_message(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """错误消息中的 secret-shaped 值应被脱敏，退出码为 2。"""
        parser = _make_parser(prog="python -m dayu.cli")
        with pytest.raises(SystemExit) as exc_info:
            parser.error(f"unrecognized arguments: {_SECRET_LIKE_VALUE}")
        assert exc_info.value.code == 2
        stderr_text = capsys.readouterr().err
        assert _SECRET_LIKE_VALUE not in stderr_text
        assert REDACTED_SECRET in stderr_text

    def test_error_no_secret_preserves_message(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """无 secret-shaped 值时错误消息应正常输出，退出码为 2。"""
        parser = _make_parser(prog="python -m dayu.cli")
        with pytest.raises(SystemExit) as exc_info:
            parser.error("unrecognized arguments: --bad-flag")
        assert exc_info.value.code == 2
        stderr_text = capsys.readouterr().err
        assert "unrecognized arguments: --bad-flag" in stderr_text
        assert "python -m dayu.cli" in stderr_text

    def test_error_required_command_shows_help(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """"required: command" 错误应输出完整帮助，退出码为 2。"""
        parser = _make_parser(prog="python -m dayu.cli")
        with pytest.raises(SystemExit) as exc_info:
            parser.error("the following arguments are required: command")
        assert exc_info.value.code == 2
        stderr_text = capsys.readouterr().err
        assert "usage:" in stderr_text.lower()
        assert "错误: 缺少子命令" in stderr_text


# ---------------------------------------------------------------------------
# print_help / print_usage 脱敏（使用 capsys）
# ---------------------------------------------------------------------------


class TestPrintHelpUsageRedaction:
    """验证 ``print_help()`` / ``print_usage()`` 输出脱敏。"""

    def test_print_help_redacts_secret(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """print_help 输出中的 secret-shaped 值应被脱敏。"""
        parser = _make_parser(prog=f"myapp-{_SECRET_LIKE_VALUE}")
        parser.print_help()
        output = capsys.readouterr().out
        assert _SECRET_LIKE_VALUE not in output
        assert REDACTED_SECRET in output

    def test_print_usage_redacts_secret(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """print_usage 输出中的 secret-shaped 值应被脱敏。"""
        parser = _make_parser(prog=f"myapp-{_SECRET_LIKE_VALUE}")
        parser.print_usage()
        output = capsys.readouterr().out
        assert _SECRET_LIKE_VALUE not in output
        assert REDACTED_SECRET in output


# ---------------------------------------------------------------------------
# 覆盖 prog 属性的脱敏
# ---------------------------------------------------------------------------


class TestProgRedaction:
    """验证 prog 属性在输出中的脱敏。"""

    def test_prog_with_secret_redacted_in_usage(self) -> None:
        """包含 secret-shaped 值的 prog 在 usage 输出中应脱敏。"""
        parser = _make_parser(prog=f"cli-tool --token={_SECRET_LIKE_VALUE}")
        usage = parser.format_usage()
        assert _SECRET_LIKE_VALUE not in usage
        assert REDACTED_SECRET in usage

    def test_prog_with_secret_redacted_in_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """包含 secret-shaped 值的 prog 在 error 输出中应脱敏，退出码为 2。"""
        parser = _make_parser(prog=f"cli-tool-{_SECRET_LIKE_VALUE}")
        with pytest.raises(SystemExit) as exc_info:
            parser.error("invalid choice: 'bad' (choose from 'a', 'b')")
        assert exc_info.value.code == 2
        stderr_text = capsys.readouterr().err
        assert _SECRET_LIKE_VALUE not in stderr_text
        assert REDACTED_SECRET in stderr_text


# ---------------------------------------------------------------------------
# 边界输入
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """边界输入行为验证。"""

    def test_empty_string_unchanged(self) -> None:
        """空字符串应原样返回。"""
        assert redact_secret_shapes("") == ""

    def test_short_sk_prefix_not_redacted(self) -> None:
        """短于 20 字符的 ``sk-`` 前缀不应被脱敏。"""
        short = "sk-short"
        assert redact_secret_shapes(short) == short

    def test_sk_prefix_after_slash_is_redacted(self) -> None:
        """``/`` 是单词边界，``sk-`` 前有斜杠时应脱敏。"""
        embedded = f"https://api.example.com/{_SECRET_LIKE_VALUE}"
        result = redact_secret_shapes(embedded)
        assert _SECRET_LIKE_VALUE not in result
        assert REDACTED_SECRET in result

    def test_multiple_secrets_all_redacted(self) -> None:
        """多个 secret-shaped 值应全部被脱敏。"""
        text = f"key1={_SECRET_LIKE_VALUE} key2=sk-another-test-key-with-length-202020"
        result = redact_secret_shapes(text)
        assert _SECRET_LIKE_VALUE not in result
        assert "sk-another-test-key-with-length-202020" not in result
        assert result.count(REDACTED_SECRET) == 2
