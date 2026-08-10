"""投资平台 PostgreSQL 16 integration session fixture。

本 conftest 提供真实 PostgreSQL 16 integration lane 的共享资源：

- session 级创建 Slice-owned 随机 container/network/database/users，
  绑定 ``127.0.0.1`` 随机端口，带唯一 owner label；
- 使用本地已存在的 pinned digest（官方 ``postgres:16.14-bookworm``），
  不在 pytest 内隐式 pull；
- 复用本机已有 Docker CLI，不引入 testcontainers 依赖；
- 只经 Alembic ``upgrade`` 建 schema，禁止 ``create_all()``；
- 成功/失败都在 ``finally`` 收集 bounded/redacted 容器日志后，只按
  已验证 label/name 删除 owned container/network，绝不用 broad glob、
  prune、compose down；
- 绝不连接、停止、修改或清理任何既有 PostgreSQL/pgvector 容器
  （尤其现有 PG17 stack）；
- fixture 不自动设置 tenant；每个 application transaction 必须由测试
  显式 ``SET LOCAL app.tenant_id``，并在提交/回滚后证明设置不泄漏。

随机资源命名统一携带 ``dayu-slice11`` 前缀与随机 suffix，owner label
固定为 ``dayu-slice11.owner``；cleanup 不能以固定端口/容器名判断 owner。
"""

from __future__ import annotations

import logging
import os
import secrets
import socket
import subprocess
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, TypeAlias
from uuid import UUID

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection

from alembic import command
from alembic.config import Config

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"
_MIGRATIONS_DIR = _REPO_ROOT / "dayu" / "investment" / "storage" / "migrations"

_LOGGER = logging.getLogger("dayu-slice11.integration")
"""本 slice integration fixture 的受控日志器（不含任何 credential）。"""

# 官方 postgres:16.14-bookworm 本机（arm64/linux）resolved immutable digest。
# 测试实际按该 digest 启动，避免 tag 漂移。
POSTGRES_16_14_IMAGE = "postgres@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8"

_LABEL_KEY = "dayu-slice11.owner"
_NETWORK_PREFIX = "dayu-slice11-net"
_CONTAINER_PREFIX = "dayu-slice11-pg"

_READY_TIMEOUT_SECONDS = 90
_READY_POLL_INTERVAL_SECONDS = 1
_LOG_TAIL_LINES = 200

# 当前 integration catalog/privilege 查询实际返回的 PostgreSQL 标量值
# 集合；query_all 用它替换宽化的 ``object`` 类型，保证严格类型检查。
PgScalar: TypeAlias = str | int | bool | UUID | None
PgRow: TypeAlias = tuple[PgScalar, ...]


class PlatformIntegrationError(RuntimeError):
    """integration fixture 基础设施失败时抛出的错误。

    消息只报告资源名称与失败类别，绝不包含 DSN、password 或
    credential 明文。
    """


@dataclass(frozen=True)
class PlatformCluster:
    """Slice-owned 临时 PostgreSQL 16 cluster 资源句柄。

    Args:
        suffix: 随机资源后缀，用于命名隔离。
        network_name: 独占 network 名称。
        container_name: 独占容器名称。
        owner_label: 该 cluster 的 owner label 值。
        host_port: 127.0.0.1 上映射的随机端口。
        bootstrap_dsn: bootstrap superuser DSN（指向 ``postgres`` 库）。
        admin_password: 临时 admin/application 密码（仅用于测试）。
    """

    suffix: str
    network_name: str
    container_name: str
    owner_label: str
    host_port: int
    bootstrap_dsn: str
    admin_password: str

    def dsn_for_database(self, database: str, role: str) -> str:
        """构造指定数据库/角色的 DSN。

        Args:
            database: 目标数据库名。
            role: 目标角色名。

        Returns:
            PostgreSQL DSN 字符串（显式 ``+psycopg`` 方言，锁定
            psycopg 3 驱动）。

        Raises:
            无。
        """

        return (
            f"postgresql+psycopg://{role}:{self.admin_password}@127.0.0.1:{self.host_port}/{database}"
        )


@dataclass(frozen=True)
class TemporaryLogin:
    """测试期间创建的临时 LOGIN 角色。

    Args:
        role: 角色名。
        member_of: 所属 group role。
        dsn: 该角色的连接 DSN（指向创建它的数据库）。
    """

    role: str
    member_of: str
    dsn: str


def _random_suffix() -> str:
    """生成随机资源后缀。

    Args:
        无。

    Returns:
        8 位十六进制随机串加进程号，保证并发 worker 隔离。

    Raises:
        无。
    """

    return f"{os.getpid()}-{uuid.uuid4().hex[:8]}"


def _free_loopback_port() -> int:
    """获取一个随机可用的 127.0.0.1 端口。

    Args:
        无。

    Returns:
        未占用的本地端口号。

    Raises:
        OSError: 无法绑定本地端口时抛出。
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_docker(args: list[str]) -> str:
    """执行 docker 命令并返回 stdout。

    Args:
        args: docker 子命令参数列表（不含 ``docker``）。

    Returns:
        命令 stdout 文本。

    Raises:
        PlatformIntegrationError: docker 命令非零退出时抛出，错误消息
            截断且不含 DSN/password。
    """

    completed = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise PlatformIntegrationError(
            f"docker {' '.join(args[:2])} 失败: {completed.stderr.strip()[-500:]}"
        )
    return completed.stdout.strip()


def _image_present() -> bool:
    """检查 pinned digest 镜像是否已在本地。

    Args:
        无。

    Returns:
        镜像存在时返回 True，否则 False。

    Raises:
        无。
    """

    try:
        _run_docker(["image", "inspect", POSTGRES_16_14_IMAGE])
        return True
    except PlatformIntegrationError:
        return False


def _wait_postgres_ready(container_name: str) -> None:
    """bounded 等待容器内 PostgreSQL 可接受连接。

    Args:
        container_name: 待检查容器名。

    Returns:
        无。

    Raises:
        PlatformIntegrationError: 超时仍不可用时抛出，消息不含凭据。
    """

    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        completed = subprocess.run(
            ["docker", "exec", container_name, "pg_isready", "-U", "postgres"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            return
        time.sleep(_READY_POLL_INTERVAL_SECONDS)
    raise PlatformIntegrationError(f"PostgreSQL 容器 {container_name} 未在 {_READY_TIMEOUT_SECONDS}s 内就绪")


def _collect_redacted_logs(cluster: PlatformCluster) -> str:
    """收集容器日志并脱敏（bounded）。

    同时替换 admin password 与 bootstrap DSN 中 URL 编码的 password，
    保证任何失败 diagnostics 都不出现 raw secret。

    Args:
        cluster: 目标 cluster 资源句柄。

    Returns:
        截断且脱敏后的容器日志文本（失败时返回
        ``<logs unavailable>``，不含任何 credential）。

    Raises:
        无。
    """

    try:
        logs = _run_docker(["logs", "--tail", str(_LOG_TAIL_LINES), cluster.container_name])
    except PlatformIntegrationError:
        return "<logs unavailable>"
    redacted = logs.replace(cluster.admin_password, "<redacted>")
    encoded_password = urllib.parse.quote(cluster.admin_password, safe="")
    redacted = redacted.replace(encoded_password, "<redacted>")
    if len(redacted) > 4000:
        return redacted[-4000:]
    return redacted


def _log_redacted_diagnostics(cluster: PlatformCluster) -> None:
    """把 bounded/redacted 容器日志接入受控 pytest diagnostics。

    在 owned cluster 可用的成功与异常清理路径都调用一次；日志只进入
    ``dayu-slice11.integration`` logger（WARNING 级），不打印 DSN/
    password，也不作为测试断言数据源。

    Args:
        cluster: 目标 cluster 资源句柄。

    Returns:
        无。

    Raises:
        无。
    """

    _LOGGER.warning(
        "Slice-11 PG16 容器 %s 结束诊断（bounded/redacted）: %s",
        cluster.container_name,
        _collect_redacted_logs(cluster),
    )


def _start_cluster() -> PlatformCluster:
    """启动 Slice-owned 随机 PostgreSQL 16 容器。

    Args:
        无。

    Returns:
        ``PlatformCluster`` 资源句柄。

    Raises:
        PlatformIntegrationError: 镜像缺失、docker 启动失败或未就绪时
            抛出；任何失败都会在 ``finally`` 清理本函数已创建的资源。
    """

    if not _image_present():
        raise PlatformIntegrationError(
            "本地缺少 pinned digest 镜像，请先手动 docker pull "
            + POSTGRES_16_14_IMAGE.split("@")[0].split("/")[-1]
            + "@" + POSTGRES_16_14_IMAGE.split("@")[1][:19]
        )
    suffix = _random_suffix()
    network_name = f"{_NETWORK_PREFIX}-{suffix}"
    container_name = f"{_CONTAINER_PREFIX}-{suffix}"
    owner_label = f"slice11-{suffix}"
    host_port = _free_loopback_port()
    admin_password = secrets.token_urlsafe(24)

    _run_docker(["network", "create", network_name, "--label", f"{_LABEL_KEY}={owner_label}"])
    try:
        _run_docker(
            [
                "run",
                "--detach",
                "--rm",
                "--name",
                container_name,
                "--network",
                network_name,
                "--label",
                f"{_LABEL_KEY}={owner_label}",
                "--env",
                "POSTGRES_PASSWORD=" + admin_password,
                "--publish",
                f"127.0.0.1:{host_port}:5432",
                POSTGRES_16_14_IMAGE,
            ]
        )
        _wait_postgres_ready(container_name)
    except PlatformIntegrationError:
        _cleanup_cluster(container_name, network_name, owner_label)
        raise
    cluster = PlatformCluster(
        suffix=suffix,
        network_name=network_name,
        container_name=container_name,
        owner_label=owner_label,
        host_port=host_port,
        bootstrap_dsn=(
            f"postgresql+psycopg://postgres:{admin_password}@127.0.0.1:{host_port}/postgres"
        ),
        admin_password=admin_password,
    )
    return cluster


def _cleanup_cluster(container_name: str, network_name: str, owner_label: str) -> None:
    """按已验证 owner 删除本 slice 创建的容器与 network。

    docker inspect 的 label 以 JSON 形式输出（``"key": "value"``），
    因此 owner 匹配使用 JSON 形式片段，避免与 ``--label key=value``
    参数形态混淆；未命中 label 的既有资源一律不动。

    Args:
        container_name: 容器名。
        network_name: network 名。
        owner_label: owner label 值。

    Returns:
        无。

    Raises:
        无（cleanup 失败只静默记录，不掩盖主结果）。
    """

    label_fragment = f'"dayu-slice11.owner": "{owner_label}"'
    for resource_name, kind in ((container_name, "container"), (network_name, "network")):
        try:
            inspect = _run_docker([kind, "inspect", resource_name])
        except PlatformIntegrationError:
            continue
        if label_fragment not in inspect:
            continue
        try:
            if kind == "container":
                _run_docker(["container", "rm", "-f", resource_name])
            else:
                _run_docker(["network", "rm", resource_name])
        except PlatformIntegrationError:
            pass


def _exec_admin_sql(bootstrap_dsn: str, sql: str) -> None:
    """以 bootstrap 连接执行管理 SQL（AUTOCOMMIT）。

    Args:
        bootstrap_dsn: bootstrap superuser DSN。
        sql: 待执行的管理 SQL（如 CREATE DATABASE）。

    Returns:
        无。

    Raises:
        PlatformIntegrationError: 执行失败时抛出，消息不包含凭据。
    """

    engine = create_engine(bootstrap_dsn, echo=False)
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text(sql))
    except Exception as error:
        raise PlatformIntegrationError(
            "管理 SQL 执行失败: " + type(error).__name__
        ) from None
    finally:
        engine.dispose()


def _create_database(bootstrap_dsn: str, database: str) -> None:
    """创建独立随机数据库。

    Args:
        bootstrap_dsn: bootstrap superuser DSN（指向 postgres 库）。
        database: 新数据库名。

    Returns:
        无。

    Raises:
        PlatformIntegrationError: 创建失败时抛出。
    """

    _exec_admin_sql(bootstrap_dsn, f'CREATE DATABASE "{database}"')


def _drop_database(bootstrap_dsn: str, database: str) -> None:
    """删除独立随机数据库（含结尾清理）。

    Args:
        bootstrap_dsn: bootstrap superuser DSN（指向 postgres 库）。
        database: 待删除数据库名。

    Returns:
        无。

    Raises:
        PlatformIntegrationError: 删除失败时抛出。
    """

    _exec_admin_sql(bootstrap_dsn, f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')


def _alembic_config() -> Config:
    """构造指向本仓库迁移脚本的 Alembic Config。

    Args:
        无。

    Returns:
        只读迁移脚本位置、不携带 DSN 的 ``Config``。

    Raises:
        无。
    """

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return cfg


def run_alembic_upgrade(dsn: str) -> None:
    """以给定 DSN 运行 ``upgrade head``。

    Args:
        dsn: bootstrap superuser DSN（目标数据库）。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: admission 预检不通过时抛出。
    """

    previous = os.environ.get("DAYU_PLATFORM_POSTGRES_DSN")
    os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = dsn
    try:
        command.upgrade(_alembic_config(), "head")
    finally:
        if previous is None:
            os.environ.pop("DAYU_PLATFORM_POSTGRES_DSN", None)
        else:
            os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = previous


def run_alembic_downgrade(dsn: str) -> None:
    """以给定 DSN 运行 ``downgrade base``。

    Args:
        dsn: bootstrap superuser DSN（目标数据库）。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: admission 预检不通过时抛出。
    """

    previous = os.environ.get("DAYU_PLATFORM_POSTGRES_DSN")
    os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = dsn
    try:
        command.downgrade(_alembic_config(), "base")
    finally:
        if previous is None:
            os.environ.pop("DAYU_PLATFORM_POSTGRES_DSN", None)
        else:
            os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = previous


def create_temporary_login(
    cluster: PlatformCluster,
    database: str,
    *,
    member_of: str,
    createrole: bool = False,
) -> TemporaryLogin:
    """创建临时 LOGIN 角色（bootstrap superuser）。

    角色自身恒为 ``NOBYPASSRLS``（PostgreSQL 默认）：audit operator
    必须通过 ``dayu_platform_audit`` group membership + ``SET ROLE``
    获得受控 bypass，不能把高权限直接扩散到每个 operator LOGIN。

    Args:
        cluster: 平台 cluster 资源句柄。
        database: 该角色可连接的目标数据库。
        member_of: 所属 group role（如 ``dayu_platform_app``）。
        createrole: 是否授予 ``CREATEROLE``（admission 负例场景）。

    Returns:
        ``TemporaryLogin`` 句柄（含角色名、所属 group 与 DSN）。

    Raises:
        PlatformIntegrationError: 创建失败时抛出。
    """

    role = f"dayu_{member_of}_{_random_suffix()}".replace("-", "")
    options = ["LOGIN", "NOBYPASSRLS"]
    if createrole:
        options.append("CREATEROLE")
    _exec_admin_sql(
        cluster.bootstrap_dsn,
        f'CREATE ROLE "{role}" ' + " ".join(options) + f' PASSWORD \'{cluster.admin_password}\'',
    )
    if member_of:
        # PostgreSQL 16 显式 membership options：INHERIT TRUE、SET TRUE、
        # ADMIN FALSE。不依赖 CREATE ROLE 默认值，也不把 pg_roles.rolinherit
        # 当作 membership option。
        _exec_admin_sql(
            cluster.bootstrap_dsn,
            f'GRANT {member_of} TO "{role}" WITH INHERIT TRUE, SET TRUE, ADMIN FALSE',
        )
    return TemporaryLogin(
        role=role,
        member_of=member_of,
        dsn=cluster.dsn_for_database(database, role),
    )


def drop_temporary_login(cluster: PlatformCluster, login: TemporaryLogin) -> None:
    """删除临时 LOGIN 角色及其 membership。

    Args:
        cluster: 平台 cluster 资源句柄。
        login: 待删除的临时登录。

    Returns:
        无。

    Raises:
        PlatformIntegrationError: 删除失败时抛出。
    """

    _exec_admin_sql(cluster.bootstrap_dsn, f'DROP ROLE IF EXISTS "{login.role}"')


@pytest.fixture(scope="session")
def platform_cluster() -> Iterator[PlatformCluster]:
    """session 级共享的 PostgreSQL 16 临时 cluster。

    Args:
        无。

    Returns:
        ``PlatformCluster`` 资源句柄。

    Raises:
        PlatformIntegrationError: 启动或清理失败时抛出。
    """

    cluster = _start_cluster()
    try:
        yield cluster
    except BaseException:
        _log_redacted_diagnostics(cluster)
        raise
    finally:
        _log_redacted_diagnostics(cluster)
        _cleanup_cluster(cluster.container_name, cluster.network_name, cluster.owner_label)


@pytest.fixture()
def database_name() -> Iterator[str]:
    """生成独立随机数据库名。

    Args:
        无。

    Returns:
        以 ``dayu_slice11_db`` 为前缀的随机数据库名。

    Raises:
        无。
    """

    yield f"dayu_slice11_db_{_random_suffix()}".replace("-", "")


@pytest.fixture()
def lifecycle_database(
    platform_cluster: PlatformCluster,
    database_name: str,
) -> Iterator[Callable[[], str]]:
    """创建并（结束前）删除一个独立随机数据库。

    返回的工厂闭包会在调用时创建数据库并返回库名；fixture 结束前以
    FORCE 删除该库。每个 migration lifecycle 使用独立随机数据库，
    cleanup 与容器/network 分离。

    Args:
        platform_cluster: 共享临时 cluster。
        database_name: 随机数据库名。

    Returns:
        调用后创建数据库并返回库名的工厂函数。

    Raises:
        无。
    """

    def _factory() -> str:
        """创建数据库并返回库名。

        Args:
            无。

        Returns:
            已创建的随机数据库名。

        Raises:
            无。
        """

        _create_database(platform_cluster.bootstrap_dsn, database_name)
        return database_name

    try:
        yield _factory
    finally:
        _drop_database(platform_cluster.bootstrap_dsn, database_name)


def connect_as(engine_or_dsn: Engine | str, autocommit: bool = False) -> Connection:
    """建立测试用数据库连接。

    Args:
        engine_or_dsn: 已有 engine 或 DSN 字符串。
        autocommit: 是否使用 AUTOCOMMIT 隔离级别。

    Returns:
        打开的 ``Connection``。

    Raises:
        无。
    """

    if isinstance(engine_or_dsn, str):
        engine = create_engine(engine_or_dsn, echo=False)
    else:
        engine = engine_or_dsn
    conn = engine.connect()
    if autocommit:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
    return conn


def query_all(conn: Connection, sql: str) -> list[PgRow]:
    """执行只读查询并返回全部行（严格标量类型）。

    Args:
        conn: 打开的连接。
        sql: 只读 SQL 语句。

    Returns:
        查询结果行元组列表；每行元素类型严格限定为
        ``PgScalar = str | int | bool | UUID | None``，不用
        ``object``/``Any`` 宽化。

    Raises:
        无。
    """

    rows = conn.execute(text(sql)).fetchall()
    return [tuple(row) for row in rows]
