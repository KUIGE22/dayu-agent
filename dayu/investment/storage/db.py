"""投资平台 PostgreSQL 存储基础设施。

本模块是 ``dayu.investment.storage`` 的数据库基础设施层，职责严格收敛为：

- 定义平台 schema 常量（``PLATFORM_SCHEMA_NAME``）、RBAC group role
  名称（``PLATFORM_APP_ROLE`` / ``PLATFORM_AUDIT_ROLE``）、租户上下文
  参数名（``TENANT_CONTEXT_SETTING``）与 default organization 种子常量；
- 定义确定性 metadata naming convention（``NAMING_CONVENTION``）与
  ORM 声明基类 ``PlatformBase``；
- 提供 engine / session factory 构造函数；本模块**绝不**调用
  ``metadata.create_all()``，schema 的唯一创建真源是 Alembic migration；
- 定义迁移 admission 失败错误 ``PlatformMigrationAdmissionError``。

安全约束：

- DSN 由调用方经参数传入，本模块不读取环境变量、不记录/回显任何
  credential；engine 构造关闭 SQL 回显并隐藏 bind 参数
  （``echo=False``、``hide_parameters=True``）。
- 生产/导入路径禁止 ``create_all``；migration 由 bootstrap superuser
  执行，application/audit 最小权限矩阵在 migration 内以显式 GRANT 闭合。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

PLATFORM_SCHEMA_NAME = "dayu_platform"
"""平台全部业务对象所在的 schema 名称（bootstrap-owned）。"""

PLATFORM_APP_ROLE = "dayu_platform_app"
"""application 运行期 group role：``NOLOGIN``、无权 bypass RLS、无 DDL。"""

PLATFORM_AUDIT_ROLE = "dayu_platform_audit"
"""审计 group role：``NOLOGIN``、``BYPASSRLS``、只读。"""

TENANT_CONTEXT_SETTING = "app.tenant_id"
"""RLS tenant 上下文的 ``SET LOCAL`` 参数名。"""

DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"
"""首次迁移以幂等固定值创建的 default organization UUID。"""

DEFAULT_ORGANIZATION_SLUG = "default"
"""default organization 的 slug / display name 固定值。"""

NAMING_CONVENTION: Mapping[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""SQLAlchemy 确定性命名约定：约束名完全由表/列推导，迁移可复现。"""


class PlatformBase(DeclarativeBase):
    """投资平台 ORM 声明基类。

    全部 25 张映射表都声明在 ``PLATFORM_SCHEMA_NAME`` schema 内，并共享
    确定性 naming convention；本类自身不携带任何业务字段。
    """

    metadata: ClassVar[MetaData] = MetaData(
        schema=PLATFORM_SCHEMA_NAME,
        naming_convention=NAMING_CONVENTION,
    )


class PlatformMigrationAdmissionError(RuntimeError):
    """迁移准入失败时抛出的错误。

    只在 bootstrap 连接未通过 ``rolsuper`` 预检、或同名 role/schema
    预先存在且不属于本 slice 时抛出；消息绝不包含 DSN、password 或
    其它 credential。
    """


def create_platform_engine(dsn: str) -> Engine:
    """构造平台 PostgreSQL engine。

    Args:
        dsn: PostgreSQL 连接串（bootstrap 或 application DSN，由调用方
            提供；本函数不读取环境变量）。

    Returns:
        关闭 SQL 回显且在 Engine 日志及 DB 异常文本中隐藏 bind 值的
        SQLAlchemy ``Engine``；engine 不会创建 schema。

    Raises:
        无（连接错误由调用方在首次使用 engine 时处理）。
    """

    return create_engine(dsn, echo=False, hide_parameters=True)


def create_platform_session_factory(engine: Engine) -> sessionmaker[Session]:
    """构造平台 session factory。

    Args:
        engine: 平台 PostgreSQL engine。

    Returns:
        绑定到给定 engine 的 ``sessionmaker``，提交后不自动
        ``expire`` 对象（便于事务内取回属性后继续使用）。

    Raises:
        无。
    """

    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


__all__ = [
    "DEFAULT_ORGANIZATION_ID",
    "DEFAULT_ORGANIZATION_SLUG",
    "NAMING_CONVENTION",
    "PLATFORM_APP_ROLE",
    "PLATFORM_AUDIT_ROLE",
    "PLATFORM_SCHEMA_NAME",
    "PlatformBase",
    "PlatformMigrationAdmissionError",
    "TENANT_CONTEXT_SETTING",
    "create_platform_engine",
    "create_platform_session_factory",
]
