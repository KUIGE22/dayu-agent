"""``dayu-cli init`` 的旧平台库 Alembic upgrade 插件（Slice 2.1 E）。

``migrate_platform_jobs()`` 是显式、幂等的旧平台库 Alembic upgrade
action，只做一件事：在平台启用且为 production 时，以既有 bootstrap
DSN 环境变量（``DAYU_PLATFORM_POSTGRES_DSN``）把旧平台库升级到最新
Alembic head（包含 0003 durable jobs schema）。

约束：

- 平台禁用或非 production（development in-memory）时 no-op，不触碰
  workspace 业务文件；
- 平台启用时只使用既有 bootstrap DSN 环境变量，缺失即 fail closed，
  绝不手写 DDL；
- 通过 Alembic ``command.upgrade`` 编程调用，复用仓库 ``alembic.ini``
  与 ``dayu.investment.storage.migrations``：env.py 负责 superuser
  admission 预检与事务性 DDL；
- 任何 admission/迁移失败原样上抛（fail closed），由 ``dayu-cli init``
  显式失败。
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from dayu.investment.config import (
    DAYU_PLATFORM_POSTGRES_DSN_ENV,
    PlatformDeploymentProfile,
    load_platform_settings,
)
from dayu.investment.storage.db import PlatformMigrationAdmissionError

_ALEMBIC_INI_PATH = Path(__file__).resolve().parents[3] / "alembic.ini"
"""仓库根目录的 Alembic 配置文件路径。"""

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "dayu" / "investment" / "storage" / "migrations"
"""平台迁移脚本目录。"""


def _alembic_config() -> Config:
    """构造指向平台迁移脚本的 Alembic Config。

    Args:
        无。

    Returns:
        只读迁移脚本位置、不携带 DSN 的 ``Config``。

    Raises:
        无。
    """

    config = Config(str(_ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return config


def _load_bootstrap_dsn_or_fail() -> str:
    """读取并校验 bootstrap DSN 环境变量值。

    Args:
        无。

    Returns:
        bootstrap DSN 字符串。

    Raises:
        PlatformMigrationAdmissionError: 环境变量缺失或值为空时抛出，
            消息只报告环境变量名，不回显任何 credential。
    """

    dsn = os.environ.get(DAYU_PLATFORM_POSTGRES_DSN_ENV, "").strip()
    if not dsn:
        raise PlatformMigrationAdmissionError(
            f"缺少环境变量 {DAYU_PLATFORM_POSTGRES_DSN_ENV}，无法执行平台迁移"
        )
    return dsn


def migrate_platform_jobs() -> bool:
    """幂等地把旧平台库升级到最新 Alembic head。

    平台禁用或非 production 时返回 ``False`` 且零副作用；production
    启用时以既有 bootstrap DSN 环境变量运行 ``upgrade head`` 并返回
    ``True``（Alembic 自身幂等，重复运行不重复应用）。不读写 workspace
    业务文件。

    Args:
        无。

    Returns:
        本调用是否实际执行了平台库升级尝试。

    Raises:
        PlatformMigrationAdmissionError: bootstrap DSN 缺失/为空或
            superuser admission 预检不通过时抛出（fail closed）。
        PlatformSettingsError: 平台环境变量设置违反严格规则时抛出。
        Exception: Alembic 迁移失败时原样抛出。
    """

    settings = load_platform_settings(os.environ)
    if not settings.enabled:
        return False
    if settings.profile is not PlatformDeploymentProfile.PRODUCTION:
        return False
    _load_bootstrap_dsn_or_fail()
    command.upgrade(_alembic_config(), "head")
    return True


__all__ = ["migrate_platform_jobs"]
