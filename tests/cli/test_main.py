"""``dayu.cli.main`` 顶层 KeyboardInterrupt 收口测试。"""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from dayu.cli.main import main
from dayu.process_lifecycle.exit_codes import EXIT_CODE_SIGINT


@pytest.mark.unit
def test_main_returns_exit_code_sigint_on_keyboard_interrupt() -> None:
    """非交互式命令触发 KeyboardInterrupt 时，``main`` 应收口并返回退出码 130。

    sync 信号 handler 在 ``settle_active_runs`` 后 raise KeyboardInterrupt 或
    SystemExit；该测试覆盖在信号 handler 注册之前 KeyboardInterrupt 已抛到
    顶层、由 ``main`` 顶层兜底返回 EXIT_CODE_SIGINT 的边缘场景。
    """

    def _fake_parse() -> argparse.Namespace:
        return argparse.Namespace(command="download", ticker="MCO")

    with (
        patch("dayu.cli.main.parse_arguments", side_effect=_fake_parse),
        patch("dayu.cli.main.configure_standard_streams_for_console_output"),
        patch(
            "dayu.cli.commands.fins.run_fins_command",
            side_effect=KeyboardInterrupt,
        ),
    ):
        result = main()

    assert result == EXIT_CODE_SIGINT


@pytest.mark.unit
def test_main_lazily_dispatches_platform_command() -> None:
    """命中 platform 后才导入并调用专属 runner。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    args = argparse.Namespace(command="platform")
    with (
        patch("dayu.cli.main.parse_arguments", return_value=args),
        patch("dayu.cli.main.configure_standard_streams_for_console_output"),
        patch(
            "dayu.cli.commands.platform.run_platform_command",
            return_value=17,
        ) as runner,
    ):
        result = main()

    assert result == 17
    runner.assert_called_once_with(args)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("command", "runner_path"),
    (
        ("init", "dayu.cli.commands.init.run_init_command"),
        ("download", "dayu.cli.commands.fins.run_fins_command"),
        ("sessions", "dayu.cli.commands.host.run_host_command"),
        (
            "research-template",
            "dayu.cli.commands.research_template.run_research_template_command",
        ),
        ("interactive", "dayu.cli.commands.interactive.run_interactive_command"),
        ("prompt", "dayu.cli.commands.prompt.run_prompt_command"),
        ("conv", "dayu.cli.commands.conv.run_conv_command"),
        ("write", "dayu.cli.commands.write.run_write_command"),
    ),
)
def test_main_preserves_existing_lazy_dispatch_branches(
    command: str,
    runner_path: str,
) -> None:
    """新增 platform 分支不改变既有命令的按需分派。

    Args:
        command: 顶层命令名。
        runner_path: 既有 command runner import path。

    Returns:
        无。

    Raises:
        无。
    """

    args = argparse.Namespace(command=command)
    with (
        patch("dayu.cli.main.parse_arguments", return_value=args),
        patch("dayu.cli.main.configure_standard_streams_for_console_output"),
        patch(runner_path, return_value=23) as runner,
    ):
        result = main()

    assert result == 23
    runner.assert_called_once_with(args)
