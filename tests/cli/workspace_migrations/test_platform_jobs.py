"""``platform_jobs`` workspace-migration 插件测试（Slice 2.1 E）。

覆盖：

- 平台禁用时 no-op（不触碰 bootstrap DSN，不尝试 Alembic）；
- development 平台 no-op；
- production 启用但 bootstrap DSN 缺失/为空时 fail closed
  （``PlatformMigrationAdmissionError``，零手写 DDL）；
- 幂等语义由 Alembic 保证：真实 upgrade->downgrade->upgrade 在
  ``tests/integration/investment/test_platform_migrations_postgres.py``
  的 PG16 lane 覆盖。
"""

from __future__ import annotations

import inspect

import pytest

from dayu.cli.workspace_migrations import platform_jobs
from dayu.cli.workspace_migrations.platform_jobs import migrate_platform_jobs
from dayu.investment.config import (
    DAYU_PLATFORM_AUTH_KEY_ENV,
    DAYU_PLATFORM_ENABLED_ENV,
    DAYU_PLATFORM_OBJECT_STORAGE_ENV,
    DAYU_PLATFORM_POSTGRES_DSN_ENV,
    DAYU_PLATFORM_PROFILE_ENV,
    DAYU_PLATFORM_REDIS_ENV,
)


def _cleanup_platform_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清理平台相关环境变量。

    Args:
        monkeypatch: pytest monkeypatch。

    Returns:
        无。
    """

    for env_name in (
        DAYU_PLATFORM_ENABLED_ENV,
        DAYU_PLATFORM_PROFILE_ENV,
        DAYU_PLATFORM_POSTGRES_DSN_ENV,
        DAYU_PLATFORM_OBJECT_STORAGE_ENV,
        DAYU_PLATFORM_REDIS_ENV,
        DAYU_PLATFORM_AUTH_KEY_ENV,
    ):
        monkeypatch.delenv(env_name, raising=False)


def _enable_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """开启 production 平台所需的最小环境变量名集合。

    Args:
        monkeypatch: pytest monkeypatch。

    Returns:
        无。
    """

    monkeypatch.setenv(DAYU_PLATFORM_ENABLED_ENV, "1")
    monkeypatch.setenv(DAYU_PLATFORM_PROFILE_ENV, "production")
    monkeypatch.setenv(DAYU_PLATFORM_OBJECT_STORAGE_ENV, "DAYU_TEST_OBJECT_STORAGE")
    monkeypatch.setenv(DAYU_PLATFORM_REDIS_ENV, "DAYU_TEST_REDIS")
    monkeypatch.setenv(DAYU_PLATFORM_AUTH_KEY_ENV, "DAYU_TEST_AUTH")


@pytest.mark.unit
def test_platform_jobs_workspace_migration_noops_when_platform_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """平台禁用时 no-op，重复调用均为 False 且零副作用。"""

    _cleanup_platform_env(monkeypatch)
    assert migrate_platform_jobs() is False
    assert migrate_platform_jobs() is False


@pytest.mark.unit
def test_platform_jobs_workspace_migration_noops_for_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """development（in-memory）平台 no-op，不触碰 bootstrap DSN。"""

    _cleanup_platform_env(monkeypatch)
    monkeypatch.setenv(DAYU_PLATFORM_ENABLED_ENV, "1")
    monkeypatch.setenv(DAYU_PLATFORM_PROFILE_ENV, "development")
    monkeypatch.setenv("DAYU_PLATFORM_USE_IN_MEMORY", "1")
    assert migrate_platform_jobs() is False


@pytest.mark.unit
def test_platform_jobs_workspace_migration_fails_without_bootstrap_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """production 启用但 bootstrap DSN 缺失时 fail closed（零手写 DDL）。"""

    from dayu.investment.config import PlatformSettingsError
    from dayu.investment.storage.db import PlatformMigrationAdmissionError

    _cleanup_platform_env(monkeypatch)
    _enable_production(monkeypatch)
    # DSN 环境变量名未配置：严格 settings 校验 fail closed。
    with pytest.raises(PlatformSettingsError):
        migrate_platform_jobs()
    # DSN 环境变量值缺失：DSN 预检 fail closed（防御性，与 settings 校验同源）。
    monkeypatch.setenv(DAYU_PLATFORM_POSTGRES_DSN_ENV, "")
    from dayu.cli.workspace_migrations.platform_jobs import _load_bootstrap_dsn_or_fail

    with pytest.raises(PlatformMigrationAdmissionError):
        _load_bootstrap_dsn_or_fail()


@pytest.mark.unit
def test_platform_jobs_workspace_migration_fails_without_dsn_env_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """production 启用但 DSN 环境变量名未配置时 fail closed。"""

    from dayu.investment.config import PlatformSettingsError

    _cleanup_platform_env(monkeypatch)
    _enable_production(monkeypatch)
    with pytest.raises(PlatformSettingsError):
        migrate_platform_jobs()


@pytest.mark.unit
def test_platform_jobs_workspace_migration_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """production 启用且 bootstrap DSN 就绪时重复执行 ``upgrade head`` 幂等。

    Alembic ``upgrade head`` 自身幂等（重复运行不重复应用 DDL），本测试
    锁定插件 admission 可重复进入 Alembic 边界；真实
    upgrade -> downgrade -> upgrade 由 PG16 lane 的
    ``test_schedule_migration_upgrade_downgrade_and_dirty_database_admission``
    覆盖。
    """

    from unittest.mock import Mock

    _cleanup_platform_env(monkeypatch)
    _enable_production(monkeypatch)
    monkeypatch.setenv(
        DAYU_PLATFORM_POSTGRES_DSN_ENV,
        "postgresql://bootstrap@127.0.0.1:5432/dayu_platform_test",
    )
    upgrade = Mock(return_value=None)
    monkeypatch.setattr("alembic.command.upgrade", upgrade)
    assert migrate_platform_jobs() is True
    assert migrate_platform_jobs() is True
    assert upgrade.call_count == 2
    args, _kwargs = upgrade.call_args
    assert args[1] == "head"


@pytest.mark.unit
def test_platform_jobs_workspace_migration_documents_0005_as_current_head() -> None:
    """插件仍只调用 Alembic head，且文档锁定当前 0005 schema。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 当前 migration head 文档或调用边界漂移时抛出。
    """

    source = inspect.getsource(platform_jobs)
    assert "0005 source connectors health schema" in source
    assert 'command.upgrade(_alembic_config(), "head")' in source
