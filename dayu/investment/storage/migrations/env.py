"""Alembic 迁移运行环境。

职责：

- 只从环境变量 ``DAYU_PLATFORM_POSTGRES_DSN`` 读取 bootstrap DSN，
  ``alembic.ini`` 不保存任何 DSN/credential；engine 显式关闭 SQL
  参数回显，失败诊断不打印 DSN/password；
- 在任何 DDL 之前，以 bootstrap connection 查询 ``pg_roles`` 并要求
  ``current_user`` 的 ``rolsuper IS TRUE``；``CREATEROLE``、
  ``BYPASSRLS`` membership、object ownership 或同名预置 role 均不能
  替代；预检不通过立即抛 ``PlatformMigrationAdmissionError``，事务中
  零 schema/table/role/seed/grant side effect；
- 以 bootstrap-owned 默认 schema（``public``）承载 Alembic version
  table，避免 downgrade 删除自身 version truth；
- 不注册 ``sqlalchemy.engine`` logger，防止 SQL 参数/secret 回显。

本模块属于 SQL storage implementation 层，允许依赖 SQLAlchemy /
psycopg / Alembic 与 ``dayu.investment`` 纯层。
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from dayu.investment.config import DAYU_PLATFORM_POSTGRES_DSN_ENV
from dayu.investment.storage.db import PlatformBase, PlatformMigrationAdmissionError

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = PlatformBase.metadata


def _load_bootstrap_dsn() -> str:
    """读取并校验 bootstrap DSN 环境变量。

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


def _admission_preflight(engine: Engine) -> None:
    """以 bootstrap connection 完成 superuser admission 预检。

    在构造 metadata 之后、执行任何 DDL 之前调用：查询 ``pg_roles``，
    要求 ``current_user`` 的 ``rolsuper IS TRUE``。``CREATEROLE`` /
    ``BYPASSRLS`` membership / object ownership 均不能替代，同名预置
    role 也不构成通过条件。

    Args:
        engine: bootstrap engine。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: 当前连接角色不是 superuser
            时抛出；消息不包含 DSN 或 credential。
    """

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).fetchone()
        conn.rollback()
    if row is None or row[0] is not True:
        raise PlatformMigrationAdmissionError(
            "平台迁移要求 bootstrap 连接使用 PostgreSQL SUPERUSER，"
            "拒绝在非 superuser 下执行任何 DDL"
        )


def run_migrations_offline() -> None:
    """离线迁移模式入口（不支持）。

    ``dayu_platform`` 迁移依赖真实 bootstrap 连接完成 superuser
    admission 预检与 transactional DDL，因此拒绝 ``--sql`` 离线模式。

    Args:
        无。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: 恒抛，说明本迁移不支持离线模式。
    """

    raise PlatformMigrationAdmissionError(
        "dayu_platform 迁移要求真实 bootstrap 连接执行 superuser admission，"
        "不支持 --sql 离线模式"
    )


def _run_migrations_on_connection(connection: Connection) -> None:
    """在给定连接上运行迁移。

    Args:
        connection: 已通过 admission 预检的 bootstrap 连接。

    Returns:
        无。

    Raises:
        无（迁移失败由 Alembic 传播并回滚事务）。
    """

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线迁移模式入口。

    读取 bootstrap DSN -> 创建关闭回显的 engine -> superuser admission
    预检 -> 单事务运行全部迁移。

    Args:
        无。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: DSN 缺失或 admission 预检不
            通过时抛出。
    """

    dsn = _load_bootstrap_dsn()
    engine = create_engine(dsn, echo=False)
    _admission_preflight(engine)
    with engine.connect() as connection:
        _run_migrations_on_connection(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
