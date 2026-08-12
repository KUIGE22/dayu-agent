"""`utils.smoke_test_offline_bundle` 模块测试。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar, Sequence

import pytest

from utils import smoke_test_offline_bundle as module

pytestmark = pytest.mark.unit


class _RecordingEnvBuilder:
    """记录虚拟环境构造参数与创建路径的测试替身。"""

    instances: ClassVar[list[_RecordingEnvBuilder]] = []

    def __init__(self, *, with_pip: bool, clear: bool, symlinks: bool) -> None:
        """记录构造参数。

        Args:
            with_pip: 是否引导安装 pip。
            clear: 是否清理既有虚拟环境目录。
            symlinks: 是否使用符号链接。

        Returns:
            无。

        Raises:
            无。
        """

        self.constructor_kwargs = {
            "with_pip": with_pip,
            "clear": clear,
            "symlinks": symlinks,
        }
        self.created_path: Path | None = None
        self.instances.append(self)

    def create(self, env_dir: Path) -> None:
        """记录虚拟环境创建路径而不创建真实环境。

        Args:
            env_dir: 虚拟环境根目录。

        Returns:
            无。

        Raises:
            无。
        """

        self.created_path = env_dir


def test_venv_uses_symlinks_selects_exact_platform_policy() -> None:
    """虚拟环境只在 Windows 使用 copy，其余平台使用 symlink。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 平台策略不符合精确合同返回值时抛出。
    """

    assert module._venv_uses_symlinks("posix") is True
    assert module._venv_uses_symlinks("nt") is False


def test_create_clean_venv_uses_exact_builder_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """干净虚拟环境使用精确构造参数与传入路径。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 临时目录 fixture。

    Returns:
        无。

    Raises:
        AssertionError: builder 构造参数或 create 路径不符合合同时抛出。
    """

    _RecordingEnvBuilder.instances.clear()
    monkeypatch.setattr(module.venv, "EnvBuilder", _RecordingEnvBuilder)
    venv_root = tmp_path / "venv"

    module._create_clean_venv(venv_root)

    assert len(_RecordingEnvBuilder.instances) == 1
    builder = _RecordingEnvBuilder.instances[0]
    assert builder.constructor_kwargs == {
        "with_pip": True,
        "clear": True,
        "symlinks": module._venv_uses_symlinks(os.name),
    }
    assert builder.created_path == venv_root
    assert not venv_root.exists()


def test_run_smoke_checks_temporarily_skips_dayu_web(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """离线包 smoke 暂不验证尚未完成的 Web help。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 临时目录 fixture。

    Returns:
        无。

    Raises:
        AssertionError: smoke 命令集合不符合预期时抛出。
    """

    python_path = tmp_path / ("python.exe" if os.name == "nt" else "python")
    scripts_dir = tmp_path / "Scripts"
    scripts_dir.mkdir()
    command_names: list[str] = []

    def _fake_run_command(command: Sequence[str], *, env: dict[str, str] | None = None) -> None:
        """记录 smoke 命令，不执行真实子进程。

        Args:
            command: 被测代码准备执行的命令。
            env: 可选环境变量覆盖。

        Returns:
            无。

        Raises:
            IndexError: 命令为空时抛出。
        """

        del env
        command_names.append(Path(command[0]).name)

    monkeypatch.setattr(module, "_run_command", _fake_run_command)

    module._run_smoke_checks(python_path, scripts_dir)

    skipped_web_name = "dayu-web.exe" if os.name == "nt" else "dayu-web"
    assert skipped_web_name not in command_names
