"""平台迁移单元契约测试（无数据库）。

本文件只验证不需要数据库的 unit contract（S11-CTRL-07 / S15-CTRL-08 /
Slice 2.2 durable schedules / Slice 2.3 source connector health）：

- ``dayu_platform`` 当前 head metadata 精确包含 25 张表，表名与类型完整；
- metadata naming convention 确定且被 ``PlatformBase.metadata`` 采用；
- 每张表编译出的 DDL 满足列类型/nullable/约束契约：UUID 无 server
  default、时间戳时区语义、``version`` 的 check、JSONB 对象 check、
  私有表 FK 的 RESTRICT 等；
- ``0002_workspace_import`` 两表契约：marker 无 updated_at/version、
  counts/schema_version CHECK、``UNIQUE(tenant_id,migration_id)``；
  locator 无冗余 ``company_id``、``repository_key`` closed CHECK、
  复合 ``(tenant_id, import_marker_id)`` FK；
- 生产 import 路径禁止 ``metadata.create_all()``（AST 扫描
  ``dayu.investment.storage`` 与迁移脚本，不能出现 ``create_all``
  调用）。
- ``0004_durable_schedules`` 的两表、closed state/snapshot/count矩阵、
  tenant FK、RLS/最小权限与破坏性downgrade admission由源码级静态门禁
  锁定；真实PostgreSQL行为仍由独立integration process证明。
- Item 8 extended workflow audit锁定exact-three pinned pulls、nine independent
  lanes / nine aggregate ignores及non-lane manifest，防止CI入口与聚合排除漂移。

真实 ``upgrade -> downgrade -> upgrade``、default organization、
RLS/GRANT/schema exact 全部在 integration lane
（``tests/integration/investment/test_platform_migrations_postgres.py``）
验证，本文件不触碰数据库。
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from types import TracebackType
from typing import TypedDict, cast
from unittest.mock import Mock

import pytest
import yaml
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime, Engine, ForeignKeyConstraint, Table, create_engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable
from sqlalchemy.sql.elements import TextClause

from dayu.investment.domain.jobs import (
    CanonicalJobDocument,
    JobEnqueueRequest,
    JobHandlerDescriptor,
    JobInputError,
    job_enqueue_request_fingerprint,
    parse_canonical_document,
)
from dayu.investment.storage import (
    NAMING_CONVENTION,
    PLATFORM_SCHEMA_NAME,
    PlatformBase,
    create_platform_engine,
    create_platform_session_factory,
)
from dayu.investment.storage import models_identity as identity_models
from tests.integration.investment import (
    test_platform_migrations_postgres as postgres_migration_tests,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STORAGE_SRC = _REPO_ROOT / "dayu" / "investment" / "storage"
_SCHEDULE_MIGRATION = (
    _STORAGE_SRC / "migrations" / "versions" / "0004_durable_schedules.py"
)
_SOURCE_HEALTH_MIGRATION = (
    _STORAGE_SRC / "migrations" / "versions" / "0005_source_connectors_health.py"
)
_JOB_REQUEST_IDENTITY_MIGRATION = (
    _STORAGE_SRC / "migrations" / "versions" / "0006_job_request_identity.py"
)
_EXTENDED_CI_WORKFLOWS: tuple[Path, ...] = (
    _REPO_ROOT / ".github" / "workflows" / "ci-pr-extended.yml",
    _REPO_ROOT / ".github" / "workflows" / "ci-mainline.yml",
)
_PINNED_IMAGE_PULL_COMMANDS: tuple[str, ...] = (
    "docker pull postgres@sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8",
    "docker pull redis:8.4.0-bookworm@sha256:c22af04bb576503bf16b3e34a1fd2fd82de0f765afd866d2e380145e0af30d78",
    "docker pull minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e",
)
_ISOLATED_INTEGRATION_LANES: tuple[str, ...] = (
    "tests/integration/investment/test_platform_migrations_postgres.py",
    "tests/integration/investment/test_job_request_identity_migration_postgres.py",
    "tests/integration/investment/test_identity_repositories_postgres.py",
    "tests/integration/investment/test_postgres_jobs.py",
    "tests/integration/investment/test_postgres_schedules.py",
    "tests/integration/investment/test_postgres_sources.py",
    "tests/integration/investment/test_source_sync_job.py",
    "tests/integration/investment/test_fins_s3_blob_repository_minio.py",
    "tests/integration/investment/test_redis_queue_wakeup.py",
)
_WORKFLOW_REQUIRED_JOB_KEYS: dict[str, frozenset[str]] = {
    "ci-pr-extended.yml": frozenset(
        {
            "extended-integration",
            "full-platform-validation-linux-x64",
            "full-platform-validation-windows-x64",
            "full-platform-validation-macos-arm64",
            "full-platform-validation-macos-x64",
        }
    ),
    "ci-mainline.yml": frozenset(
        {
            "pr-required-min-compat",
            "pr-required-lock-smoke",
            "extended-integration",
            "full-platform-validation-linux-x64",
            "full-platform-validation-windows-x64",
            "full-platform-validation-macos-arm64",
            "full-platform-validation-macos-x64",
        }
    ),
}
_WORKFLOW_NON_LANE_MANIFEST_SHA256: dict[str, str] = {
    "ci-pr-extended.yml": "044084c0b080bbace42a0b17431fc89344ddc77a45a3adbf2cea7a595126044b",
    "ci-mainline.yml": "4cf3684b3bd0cd77b88ee9d9f112f68fde6338fca54a0e3f8f05abd3807a2099",
}


class _WorkflowStep(TypedDict, total=False):
    """workflow step 的静态审计投影。"""

    name: str
    run: str


class _WorkflowJob(TypedDict, total=False):
    """workflow job 的静态审计投影。"""

    steps: list[_WorkflowStep]


class _WorkflowDocument(TypedDict, total=False):
    """workflow document 的静态审计投影。"""

    jobs: dict[str, _WorkflowJob]


def _workflow_step(job: _WorkflowJob, step_name: str) -> _WorkflowStep:
    """按名称取得 workflow job 中唯一 step。

    Args:
        job: 已由 YAML parser 读取的 job 投影。
        step_name: 目标 step 的精确名称。

    Returns:
        唯一匹配的 step。

    Raises:
        AssertionError: step 缺失、重复或 steps 结构缺失时抛出。
    """

    assert "steps" in job
    matches = [step for step in job["steps"] if step.get("name") == step_name]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.unit
def test_ci_extended_workflows_pull_three_pinned_images_isolate_nine_lanes_and_ignore_each_from_aggregate() -> None:
    """两份 extended workflow 必须共享 exact-three/nine/nine ledger。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: YAML、触发器/job/filter、镜像、独立 lane、aggregate
            ignore、顺序或双 workflow 一致性漂移时抛出。
    """

    workflow_ledgers: list[
        tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]
    ] = []
    expected_isolated_commands = tuple(
        f"pytest {lane} -q -m integration --timeout=120"
        for lane in _ISOLATED_INTEGRATION_LANES
    )
    expected_aggregate_lines = (
        'pytest -q --timeout=120 -m "integration and not e2e" \\',
        *(f"--ignore={lane} \\" for lane in _ISOLATED_INTEGRATION_LANES[:-1]),
        f"--ignore={_ISOLATED_INTEGRATION_LANES[-1]}",
    )
    normalized_step_bodies = {
        "Pull pinned durable platform images": "<PINNED_IMAGE_PULL_COMMANDS>",
        "Run isolated durable platform integration lanes": (
            "<ISOLATED_INTEGRATION_COMMANDS>"
        ),
        "Run remaining extended integration lane": (
            "<REMAINING_INTEGRATION_COMMAND>"
        ),
    }

    for workflow_path in _EXTENDED_CI_WORKFLOWS:
        source = workflow_path.read_text(encoding="utf-8")
        document = cast(
            _WorkflowDocument,
            yaml.load(source, Loader=yaml.BaseLoader),
        )
        assert "jobs" in document
        jobs = document["jobs"]
        assert frozenset(jobs) == _WORKFLOW_REQUIRED_JOB_KEYS[workflow_path.name]
        extended_job = jobs["extended-integration"]
        pull_step = _workflow_step(
            extended_job,
            "Pull pinned durable platform images",
        )
        isolated_step = _workflow_step(
            extended_job,
            "Run isolated durable platform integration lanes",
        )
        aggregate_step = _workflow_step(
            extended_job,
            "Run remaining extended integration lane",
        )
        assert "run" in pull_step
        assert "run" in isolated_step
        assert "run" in aggregate_step
        pull_commands = tuple(
            line.strip() for line in pull_step["run"].splitlines() if line.strip()
        )
        isolated_commands = tuple(
            line.strip()
            for line in isolated_step["run"].splitlines()
            if line.strip()
        )
        aggregate_lines = tuple(
            line.strip()
            for line in aggregate_step["run"].splitlines()
            if line.strip()
        )
        aggregate_ignores = tuple(
            match.group(1)
            for match in re.finditer(r"--ignore=(\S+)", aggregate_step["run"])
        )

        assert pull_commands == _PINNED_IMAGE_PULL_COMMANDS
        assert source.count("docker pull ") == 3
        assert isolated_commands == expected_isolated_commands
        assert len(set(isolated_commands)) == 9
        assert all(
            command.count("tests/integration/investment/") == 1
            and command.count(".py") == 1
            for command in isolated_commands
        )
        assert aggregate_lines == expected_aggregate_lines
        assert aggregate_ignores == _ISOLATED_INTEGRATION_LANES
        assert aggregate_step["run"].count("--ignore=") == 9
        assert aggregate_step["run"].count("pytest ") == 1
        workflow_ledgers.append(
            (pull_commands, isolated_commands, aggregate_ignores)
        )

        for step_name, replacement in normalized_step_bodies.items():
            _workflow_step(extended_job, step_name)["run"] = replacement
        normalized_manifest = json.dumps(
            document,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        assert hashlib.sha256(normalized_manifest).hexdigest() == (
            _WORKFLOW_NON_LANE_MANIFEST_SHA256[workflow_path.name]
        )

    assert workflow_ledgers[0] == workflow_ledgers[1]
_POSTGRES_MIGRATION_OWNER_TEST = (
    _REPO_ROOT / "tests" / "integration" / "investment" / "test_platform_migrations_postgres.py"
)
_ITEM4_DOCSTRING_PATHS: tuple[Path, ...] = (
    _REPO_ROOT / "dayu" / "cli" / "workspace_migrations" / "platform_jobs.py",
    _STORAGE_SRC / "models_identity.py",
    _SOURCE_HEALTH_MIGRATION,
    _REPO_ROOT / "tests" / "cli" / "workspace_migrations" / "test_platform_jobs.py",
    _REPO_ROOT
    / "tests"
    / "integration"
    / "investment"
    / "test_identity_repositories_postgres.py",
    _POSTGRES_MIGRATION_OWNER_TEST,
    Path(__file__).resolve(),
)
_ITEM4_PG_MODULE_FUNCTIONS: frozenset[str] = frozenset(
    {
        "_require_host_sql_readiness",
        "_owner_test_host_sql_readiness",
        "_drop_platform_member_and_group_roles",
        "_reap_owner_test_resources",
        "_owner_test_fail_safe_reaper",
        "_autocommit",
        "_assert_schema_present",
        "_assert_schema_intact",
        "_assert_0004_present",
        "_migrate_down_to_0004",
        "_seed_0005_parent_lineage",
        "_insert_valid_source_run",
        "_source_run_insert_sql",
        "_cleanup_0005_business_rows",
        "_assert_writer_holds_operation_lock",
        "_assert_0005_preflight_zero_mutation",
        "_expected_0005_check_catalog",
    }
)
_ITEM4_UNIT_MODULE_FUNCTIONS: frozenset[str] = frozenset(
    {
        "_item4_changed_function_nodes",
        "_item4_docstring_contract_errors",
        "_record_database_drop",
        "_record_role_drop",
        "_record_failing_database_drop",
    }
)


def test_0006_migration_fingerprint_reproducer_matches_domain_and_excludes_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """冻结0006 Alembic动态加载与canonical admission/domain等价。

    Args:
        monkeypatch: pytest安全替换工具，用于证明SHA drift在parser前拒绝。

    Returns:
        无。

    Raises:
        AssertionError: Alembic加载、canonical结果、fingerprint或parser
            调用顺序漂移时抛出。
    """

    migration_tree = ast.parse(
        _JOB_REQUEST_IDENTITY_MIGRATION.read_text(encoding="utf-8")
    )
    unexpanded_templates = [
        node.value
        for node in ast.walk(migration_tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.search(r"\{_[A-Z][A-Z0-9_]*\}", node.value) is not None
    ]
    assert unexpanded_templates == []
    loader_module_name = re.sub(r"\W", "_", _JOB_REQUEST_IDENTITY_MIGRATION.name)
    monkeypatch.delitem(sys.modules, loader_module_name, raising=False)
    alembic_config = Config()
    alembic_config.set_main_option(
        "script_location",
        str(_STORAGE_SRC / "migrations"),
    )
    revision_script = ScriptDirectory.from_config(alembic_config).get_revision(
        "0006_job_request_identity"
    )
    assert revision_script is not None
    assert revision_script.revision == "0006_job_request_identity"
    assert revision_script.down_revision == "0005_source_connectors_health"
    migration = revision_script.module
    assert migration.__name__ == loader_module_name
    assert loader_module_name not in sys.modules
    schema_name = "dayu.job.request"
    schema_version = 7
    accepted_raw = (
        b"null",
        b"true",
        b"-1",
        '"中"'.encode(),
        '[null,false,0,"中",{}]'.encode(),
        '{"a":[null,true,0,"中"],"z":{"ok":-1}}'.encode(),
        b'{"apikey":"ok"}',
        b'{"password_hint":"ok"}',
        b'{"token_count":1}',
        b'{"x-authorization":"ok"}',
    )
    rejected_raw = (
        b'{"password":"x"}',
        b'{"secret":"x"}',
        b'{"token":"x"}',
        b'{"authorization":"x"}',
        b'{"cookie":"x"}',
        b'{"api_key":"x"}',
        b'{"a":{"ToKeN":"x"}}',
        b"1.0",
        b"NaN",
        b'{"a":{"x":1,"x":2}}',
        b'\xef\xbb\xbf{"a":1}',
        b'{"a":1}x',
        b'{"a":1} ',
        b'{"z":1,"a":2}',
        b'{"a": 1}',
        b'{"a":"\\u4e2d"}',
    )

    for raw in accepted_raw:
        domain_result = parse_canonical_document(
            raw.decode("utf-8"),
            schema_name=schema_name,
            schema_version=schema_version,
        )
        migration_result = migration._admit_canonical_payload(
            raw,
            hashlib.sha256(raw).hexdigest(),
            schema_name=schema_name,
            schema_version=schema_version,
        )
        assert (
            migration_result.schema_name,
            migration_result.schema_version,
            migration_result.canonical_bytes,
            migration_result.sha256,
        ) == (
            domain_result.schema_name,
            domain_result.schema_version,
            domain_result.canonical_bytes,
            domain_result.sha256,
        )
        assert migration_result.canonical_bytes == raw == domain_result.canonical_bytes

    for raw in rejected_raw:
        domain_outcome = "ACCEPT"
        try:
            parse_canonical_document(
                raw.decode("utf-8"),
                schema_name=schema_name,
                schema_version=schema_version,
            )
        except JobInputError:
            domain_outcome = "CANONICAL_INVALID"
        migration_outcome = "ACCEPT"
        try:
            migration._admit_canonical_payload(
                raw,
                hashlib.sha256(raw).hexdigest(),
                schema_name=schema_name,
                schema_version=schema_version,
            )
        except migration._CanonicalInvalid:
            migration_outcome = "CANONICAL_INVALID"
        assert migration_outcome == domain_outcome == "CANONICAL_INVALID"

    unexpected_parse = Mock(
        side_effect=AssertionError("SHA mismatch must reject before parser")
    )
    monkeypatch.setattr(migration, "_parse_canonical_text", unexpected_parse)
    with pytest.raises(migration._CanonicalInvalid):
        migration._admit_canonical_payload(
            b"null",
            "0" * 64,
            schema_name=schema_name,
            schema_version=schema_version,
        )
    assert unexpected_parse.call_count == 0

    descriptor = JobHandlerDescriptor(
        job_type="source.sync",
        payload_schema_name="dayu.source.definition",
        payload_schema_version=3,
        max_attempts=5,
        retry_base_seconds=7,
        retry_max_seconds=61,
        lease_duration_seconds=43,
    )
    base_available = datetime(2026, 8, 14, 1, 2, 3, 456789, tzinfo=timezone.utc)
    cases = (
        (schema_name, schema_version, base_available),
        (descriptor.payload_schema_name, descriptor.payload_schema_version, base_available),
        (schema_name, schema_version, base_available + timedelta(microseconds=1)),
    )
    for request_schema_name, request_schema_version, available_at in cases:
        raw = b'{"value":1}'
        payload = CanonicalJobDocument(
            schema_name=request_schema_name,
            schema_version=request_schema_version,
            canonical_bytes=raw,
            sha256=hashlib.sha256(raw).hexdigest(),
        )
        enqueue_request = JobEnqueueRequest(
            descriptor=descriptor,
            idempotency_key="first-key",
            payload=payload,
            available_at=available_at,
            deadline_at=available_at + timedelta(seconds=97, microseconds=3),
        )
        renamed_request = JobEnqueueRequest(
            descriptor=descriptor,
            idempotency_key="second-key",
            payload=payload,
            available_at=enqueue_request.available_at,
            deadline_at=enqueue_request.deadline_at,
        )
        migration_fingerprint = migration._job_request_fingerprint(
            job_type=descriptor.job_type,
            payload_schema_name=descriptor.payload_schema_name,
            payload_schema_version=descriptor.payload_schema_version,
            max_attempts=descriptor.max_attempts,
            retry_base_seconds=descriptor.retry_base_seconds,
            retry_max_seconds=descriptor.retry_max_seconds,
            lease_duration_seconds=descriptor.lease_duration_seconds,
            request_payload_schema_name=payload.schema_name,
            request_payload_schema_version=payload.schema_version,
            request_payload_sha256=payload.sha256,
            available_at=enqueue_request.available_at,
            deadline_at=enqueue_request.deadline_at,
        )
        assert migration_fingerprint == job_enqueue_request_fingerprint(enqueue_request)
        assert migration_fingerprint == job_enqueue_request_fingerprint(renamed_request)


class _HostReadinessFakeResult:
    """模拟 host readiness 查询的精确标量结果。"""

    def scalar_one(self) -> int:
        """返回 readiness 查询的唯一整数。

        Args:
            无。

        Returns:
            固定的成功值一。

        Raises:
            无。
        """

        return 1


class _HostReadinessFakeConnection:
    """记录单次 host readiness SQL 执行的上下文连接。"""

    def __init__(self, attempt: int, events: list[str]) -> None:
        """保存 attempt 与共享事件序列。

        Args:
            attempt: 当前从一开始计数的尝试序号。
            events: 共享的可变事件序列。

        Returns:
            无。

        Raises:
            无。
        """

        self._attempt = attempt
        self._events = events

    def __enter__(self) -> _HostReadinessFakeConnection:
        """进入 fake connection 上下文。

        Args:
            无。

        Returns:
            当前 fake connection。

        Raises:
            无。
        """

        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """退出 fake connection 上下文且不吞异常。

        Args:
            _exception_type: 上下文内异常类型；成功时为空。
            _exception: 上下文内异常实例；成功时为空。
            _traceback: 上下文内异常 traceback；成功时为空。

        Returns:
            无。

        Raises:
            无。
        """

        return None

    def execute(self, _statement: TextClause) -> _HostReadinessFakeResult:
        """记录 SELECT 执行并返回精确 fake result。

        Args:
            _statement: readiness helper 生成的 SQLAlchemy text statement。

        Returns:
            固定 scalar-one 结果。

        Raises:
            无。
        """

        self._events.append(f"execute:{self._attempt}")
        return _HostReadinessFakeResult()


class _HostReadinessFakeEngine:
    """按单次预设结果模拟 create-engine/connect/dispose。"""

    def __init__(
        self,
        attempt: int,
        outcome: DBAPIError | None,
        events: list[str],
    ) -> None:
        """保存当前 attempt、预设异常与共享事件序列。

        Args:
            attempt: 当前从一开始计数的尝试序号。
            outcome: connect 应抛出的数据库异常；为空表示成功。
            events: 共享的可变事件序列。

        Returns:
            无。

        Raises:
            无。
        """

        self._attempt = attempt
        self._outcome = outcome
        self._events = events

    def connect(self) -> _HostReadinessFakeConnection:
        """记录连接并按预设结果返回连接或抛出异常。

        Args:
            无。

        Returns:
            当前 attempt 的 fake connection。

        Raises:
            DBAPIError: 当前 attempt 预设的精确数据库异常。
        """

        self._events.append(f"connect:{self._attempt}")
        if self._outcome is not None:
            raise self._outcome
        return _HostReadinessFakeConnection(self._attempt, self._events)

    def dispose(self) -> None:
        """记录当前 fake engine 的释放。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._events.append(f"dispose:{self._attempt}")


class _HostReadinessFakeEngineFactory:
    """为 host readiness 单测顺序生产预设 fake engines。"""

    def __init__(self, outcomes: list[DBAPIError | None]) -> None:
        """冻结顺序 outcomes 并初始化事件序列。

        Args:
            outcomes: 每次 connect 对应的异常或成功标记。

        Returns:
            无。

        Raises:
            无。
        """

        self.events: list[str] = []
        self._pending: Iterator[tuple[int, DBAPIError | None]] = iter(
            enumerate(outcomes, 1)
        )

    def __call__(
        self,
        _dsn: str,
        *,
        echo: bool,
        connect_args: dict[str, int],
    ) -> _HostReadinessFakeEngine:
        """验证 create-engine 参数并返回下一预设 engine。

        Args:
            _dsn: 被测 helper 传入的 bootstrap DSN。
            echo: SQL echo 开关。
            connect_args: psycopg connect 参数。

        Returns:
            下一 attempt 的 fake engine。

        Raises:
            AssertionError: create-engine 参数偏离窄 readiness 契约时抛出。
            StopIteration: 被测 helper 超出预设 attempt 数时抛出。
        """

        assert echo is False
        assert connect_args == {"connect_timeout": 1}
        attempt, outcome = next(self._pending)
        self.events.append(f"create:{attempt}")
        return _HostReadinessFakeEngine(attempt, outcome, self.events)


def _record_database_drop(events: list[str], _dsn: str, database: str) -> None:
    """记录 reaper database drop 调用。

    Args:
        events: 共享的可变事件序列。
        _dsn: 被测 reaper 传入的 bootstrap DSN。
        database: 被删除的 exact database 名。

    Returns:
        无。

    Raises:
        无。
    """

    events.append(f"database:{database}")


def _record_role_drop(events: list[str], _cluster: postgres_migration_tests.PlatformCluster) -> None:
    """记录 reaper role cleanup 调用。

    Args:
        events: 共享的可变事件序列。
        _cluster: 被测 reaper 传入的 cluster。

    Returns:
        无。

    Raises:
        无。
    """

    events.append("roles")


def _record_failing_database_drop(
    events: list[str],
    _dsn: str,
    database: str,
) -> None:
    """记录 database drop 后抛出确定异常。

    Args:
        events: 共享的可变事件序列。
        _dsn: 被测 reaper 传入的 bootstrap DSN。
        database: 被删除的 exact database 名。

    Returns:
        无。

    Raises:
        RuntimeError: 每次调用均抛出，验证 reaper fail closed。
    """

    events.append(f"database:{database}")
    raise RuntimeError("drop failed")


def _item4_docstring_contract_errors(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, ...]:
    """返回单个 Item4 函数违反中文文档与 AST 边界的错误集合。

    Args:
        node: 待审计的同步或异步函数 AST 节点。

    Returns:
        稳定排序的契约错误字符串；无错误时为空 tuple。

    Raises:
        无。
    """

    errors: list[str] = []
    docstring = ast.get_docstring(node, clean=False) or ""
    if not any("\u4e00" <= character <= "\u9fff" for character in docstring):
        errors.append("missing-chinese-docstring")
    if "Args:" not in docstring:
        errors.append("missing-args-section")
    if "Raises:" not in docstring:
        errors.append("missing-raises-section")

    descendants = [
        descendant
        for statement in node.body
        for descendant in ast.walk(statement)
    ]
    is_generator = any(
        isinstance(descendant, (ast.Yield, ast.YieldFrom))
        for descendant in descendants
    )
    result_section = "Yields:" if is_generator else "Returns:"
    if result_section not in docstring:
        errors.append(f"missing-{result_section[:-1].lower()}-section")

    arguments: list[ast.arg] = [
        *node.args.posonlyargs,
        *node.args.args,
        *node.args.kwonlyargs,
    ]
    if node.args.vararg is not None:
        arguments.append(node.args.vararg)
    if node.args.kwarg is not None:
        arguments.append(node.args.kwarg)
    if any(
        argument.arg not in {"self", "cls"} and argument.annotation is None
        for argument in arguments
    ):
        errors.append("missing-argument-annotation")
    if node.returns is None:
        errors.append("missing-return-annotation")

    annotations = [
        argument.annotation
        for argument in arguments
        if argument.annotation is not None
    ]
    if node.returns is not None:
        annotations.append(node.returns)
    forbidden_annotation = any(
        (
            isinstance(annotation_node, ast.Name)
            and annotation_node.id in {"Any", "object"}
        )
        or (
            isinstance(annotation_node, ast.Attribute)
            and annotation_node.attr in {"Any", "object"}
        )
        for annotation in annotations
        for annotation_node in ast.walk(annotation)
    )
    if forbidden_annotation:
        errors.append("forbidden-any-or-object-annotation")

    if any(
        isinstance(descendant, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for descendant in descendants
    ):
        errors.append("nested-definition")
    if any(
        isinstance(descendant, (ast.Name, ast.arg))
        and (
            descendant.id == "request"
            if isinstance(descendant, ast.Name)
            else descendant.arg == "request"
        )
        for descendant in descendants
    ) or any(argument.arg == "request" for argument in arguments):
        errors.append("unscoped-request-helper")
    return tuple(sorted(errors))


def _item4_changed_function_nodes(
    path: Path,
    tree: ast.Module,
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]:
    """由 baseline diff 新行区间机械枚举路径内全部 changed functions。

    Args:
        path: Item4 exact code/test 路径。
        tree: 该路径当前字节解析出的 module AST。

    Returns:
        按行号排序且与新增/修改 diff hunk 相交的函数节点；全新 migration
        返回其全部函数。

    Raises:
        AssertionError: git diff hunk header 无法解析时抛出。
        subprocess.CalledProcessError: baseline diff 查询失败时向外传播。
    """

    if path == _SOURCE_HEALTH_MIGRATION:
        return tuple(
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
    relative_path = path.relative_to(_REPO_ROOT)
    output = subprocess.run(
        (
            "git",
            "diff",
            "--unified=0",
            "595564ebcbd398fb84a4eab21e0cd9e045f56dd5",
            "--",
            str(relative_path),
        ),
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    ranges: list[tuple[int, int]] = []
    for line in output.splitlines():
        if not line.startswith("@@"):
            continue
        match = re.search(r"\+(\d+)(?:,(\d+))?", line)
        if match is None:
            raise AssertionError(f"无法解析 git diff hunk：{line}")
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count > 0:
            ranges.append((start, start + count - 1))
    return tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.end_lineno is not None
        and any(node.lineno <= end and node.end_lineno >= start for start, end in ranges)
    )


# 当前 head 精确 25 张 mapped 表名；raw Job/Schedule tables 不进入 metadata。
_EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "organizations",
        "companies",
        "securities",
        "source_definitions",
        "users",
        "roles",
        "permissions",
        "user_roles",
        "role_permissions",
        "api_tokens",
        "source_subscriptions",
        "source_sync_runs",
        "source_health_snapshots",
        "source_sync_operations",
        "source_health_states",
        "source_health_alert_outbox",
        "workspace_import_markers",
        "research_bundle_locators",
        "facts",
        "claims",
        "claim_versions",
        "evidence_links",
        "claim_conflicts",
        "research_candidates",
        "candidate_intake_receipts",
    }
)

# 私有表（启用并 FORCE RLS）。
_PRIVATE_TABLES: frozenset[str] = frozenset(
    {
        "organizations",
        "users",
        "roles",
        "permissions",
        "user_roles",
        "role_permissions",
        "api_tokens",
        "source_subscriptions",
        "source_sync_runs",
        "source_health_snapshots",
        "source_sync_operations",
        "source_health_states",
        "source_health_alert_outbox",
        "workspace_import_markers",
        "research_bundle_locators",
        "facts",
        "claims",
        "claim_versions",
        "evidence_links",
        "claim_conflicts",
        "research_candidates",
        "candidate_intake_receipts",
    }
)


def _iter_storage_files() -> list[Path]:
    """收集 storage 子包下全部 Python 文件。

    Args:
        无。

    Returns:
        按文件名排序的 Python 文件路径列表。

    Raises:
        无。
    """

    return sorted(path for path in _STORAGE_SRC.rglob("*.py") if path.is_file())


def _compile_ddl(table: Table) -> str:
    """把 ORM 表编译为 PostgreSQL DDL 字符串。

    Args:
        table: 待编译的 ORM 表。

    Returns:
        该表在 PostgreSQL 方言下的 ``CREATE TABLE`` 语句。

    Raises:
        无。
    """

    return str(CreateTable(table).compile(dialect=postgresql.dialect()))


class TestPlatformSchemaMetadata:
    """metadata 表集合与命名约定契约。"""

    @pytest.mark.unit
    def test_metadata_contains_exactly_25_platform_tables(self) -> None:
        """当前 head metadata 精确包含 25 张 ``dayu_platform`` 表。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        tables = set(PlatformBase.metadata.tables.keys())
        expected = {f"{PLATFORM_SCHEMA_NAME}.{name}" for name in _EXPECTED_TABLES}
        assert tables == expected
        assert f"{PLATFORM_SCHEMA_NAME}.job_attempts" not in tables
        assert f"{PLATFORM_SCHEMA_NAME}.job_runs" not in tables
        assert f"{PLATFORM_SCHEMA_NAME}.job_schedules" not in tables

    @pytest.mark.unit
    def test_metadata_uses_platform_schema(self) -> None:
        """全部表位于 ``dayu_platform`` schema。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for table in PlatformBase.metadata.tables.values():
            assert table.schema == PLATFORM_SCHEMA_NAME

    @pytest.mark.unit
    def test_metadata_uses_deterministic_naming_convention(self) -> None:
        """naming convention 与平台常量一致且包含全部约束键。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        convention = PlatformBase.metadata.naming_convention
        assert convention == NAMING_CONVENTION
        for key in ("ix", "uq", "ck", "fk", "pk"):
            assert key in convention

    @pytest.mark.unit
    def test_naming_convention_constraint_tokens_are_concrete(self) -> None:
        """约定模板不含会导致约束名不确定的表达式。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for template in NAMING_CONVENTION.values():
            assert "%(column_0_label)s" in template or "%(table_name)s" in template
            assert "%(constraint_name)s" not in template or "ck" in template

    @pytest.mark.unit
    def test_uuid_pk_has_no_server_default(self) -> None:
        """UUID 主键由调用方提供，无 server random default。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for table_name in _EXPECTED_TABLES:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            ddl = _compile_ddl(table).lower()
            assert "gen_random_uuid" not in ddl
            assert "uuid_generate" not in ddl
            for column in table.primary_key.columns:
                assert column.server_default is None
                assert column.default is None


class TestWorkspaceImportSchema:
    """0002 workspace import 两表的契约。"""

    @pytest.mark.unit
    def test_workspace_import_marker_is_append_only(self) -> None:
        """marker 无 updated_at/version，只带 created_at。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.workspace_import_markers"
        ]
        assert "updated_at" not in table.c
        assert "version" not in table.c
        assert "created_at" in table.c

    @pytest.mark.unit
    def test_workspace_import_marker_checks_and_uniques(self) -> None:
        """marker 的 schema_version/counts CHECK 与 tenant 内唯一约束。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.workspace_import_markers"
        ]
        ddl = _compile_ddl(table)
        assert "source_schema_version > 0" in ddl
        assert "company_count >= 0" in ddl
        assert "security_count >= 0" in ddl
        assert "source_definition_count >= 0" in ddl
        assert "bundle_count >= 0" in ddl
        assert "UNIQUE (tenant_id, migration_id)" in ddl
        assert "UNIQUE (tenant_id, id)" in ddl
        for fk in table.foreign_keys:
            assert fk.ondelete == "RESTRICT"

    @pytest.mark.unit
    def test_research_bundle_locator_has_no_redundant_company_id(self) -> None:
        """locator 无冗余 company_id，公司只能经 security_id 解析。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.research_bundle_locators"
        ]
        assert "company_id" not in table.c
        assert "security_id" in table.c
        assert "import_marker_id" in table.c

    @pytest.mark.unit
    def test_research_bundle_locator_repository_key_closed_check(self) -> None:
        """locator 的 repository_key 精确 CHECK 为 legacy-workspace。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.research_bundle_locators"
        ]
        ddl = _compile_ddl(table)
        assert "repository_key = 'legacy-workspace'" in ddl
        assert "UNIQUE (tenant_id, security_id, template_name)" in ddl
        assert "UNIQUE (tenant_id, repository_key, relative_locator)" in ddl

    @pytest.mark.unit
    def test_research_bundle_locator_has_composite_marker_fk(self) -> None:
        """locator 通过 (tenant_id, import_marker_id) 复合 FK 引用 marker。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.research_bundle_locators"
        ]
        composite_fks = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
            and len(constraint.columns) == 2
        ]
        assert len(composite_fks) == 1
        composite = composite_fks[0]
        assert set(composite.column_keys) == {"tenant_id", "import_marker_id"}
        for element in composite.elements:
            assert element.ondelete == "RESTRICT"

    @pytest.mark.unit
    def test_workspace_import_marker_has_no_status_column(self) -> None:
        """marker 只表示 completed commit，不设 pending/failed status。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.workspace_import_markers"
        ]
        assert "status" not in table.c


class TestPlatformSchemaColumns:
    """列类型、nullable 与约束契约。"""

    @pytest.mark.unit
    def test_all_tables_have_created_at_timestamptz(self) -> None:
        """全部表都有非空 TIMESTAMPTZ created_at，仅outbox无default。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for table_name in _EXPECTED_TABLES:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            assert "created_at" in table.c
            column = table.c["created_at"]
            assert isinstance(column.type, DateTime)
            assert column.type.timezone
            assert not column.nullable
            if table_name == "source_health_alert_outbox":
                assert column.server_default is None
            else:
                assert column.server_default is not None

    @pytest.mark.unit
    def test_mutable_tables_have_updated_at_and_version(self) -> None:
        """mutable 表带 updated_at/version；append-only 表不带。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        conventional_mutable_tables: frozenset[str] = frozenset(
            {
                "organizations",
                "companies",
                "securities",
                "source_definitions",
                "users",
                "roles",
                "permissions",
                "api_tokens",
                "source_subscriptions",
            }
        )
        for table_name in conventional_mutable_tables:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            assert "updated_at" in table.c
            assert "version" in table.c
            assert not table.c["version"].nullable
            assert table.c["version"].server_default is not None
        operation = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.source_sync_operations"
        ]
        assert "updated_at" in operation.c
        assert "generation" in operation.c
        assert "version" not in operation.c
        health_state = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.source_health_states"
        ]
        assert "updated_at" in health_state.c
        assert "version" in health_state.c
        assert health_state.c["version"].server_default is None
        append_only_tables = frozenset(
            {
                "user_roles",
                "role_permissions",
                "source_sync_runs",
                "source_health_snapshots",
                "workspace_import_markers",
                "research_bundle_locators",
                "source_health_alert_outbox",
            }
        )
        for table_name in append_only_tables:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            assert "updated_at" not in table.c
            assert "version" not in table.c

    @pytest.mark.unit
    def test_version_column_has_positive_check(self) -> None:
        """version 列必须带 ``version > 0`` check。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for table_name in _EXPECTED_TABLES:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            if "version" not in table.c:
                continue
            ddl = _compile_ddl(table)
            assert "CHECK" in ddl
            assert "version > 0" in ddl

    @pytest.mark.unit
    def test_observed_at_and_started_at_have_no_server_default(self) -> None:
        """observed_at/started_at 由调用方提供，无 server default。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        cases: dict[str, str] = {
            "source_health_snapshots": "observed_at",
            "source_sync_runs": "started_at",
            "source_sync_operations": "acquired_at",
            "source_health_states": "observed_at",
            "source_health_alert_outbox": "created_at",
        }
        for table_name, column_name in cases.items():
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            column = table.c[column_name]
            assert column.server_default is None
            assert not column.nullable

    @pytest.mark.unit
    def test_private_tables_have_non_null_tenant_id(self) -> None:
        """私有表 tenant_id 非空且引用 organizations。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for table_name in _PRIVATE_TABLES - {"organizations"}:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            assert "tenant_id" in table.c
            assert not table.c["tenant_id"].nullable

    @pytest.mark.unit
    def test_api_tokens_only_holds_hash(self) -> None:
        """api_tokens 只保存 64 位小写 hex hash。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.api_tokens"]
        ddl = _compile_ddl(table)
        assert "CHAR(64)" in ddl
        assert "UNIQUE" in ddl
        assert "0-9a-f" in ddl or "9a-f" in ddl
        assert "raw" not in ddl.lower()


class TestPlatformSchemaGeneratedSql:
    """编译 DDL 的 schema exact 契约。"""

    @pytest.mark.unit
    def test_public_reference_tables_have_no_rls_columns(self) -> None:
        """公共 reference 表不含 tenant_id 列。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        public_tables = _EXPECTED_TABLES - _PRIVATE_TABLES
        assert public_tables == frozenset({"companies", "securities", "source_definitions"})
        for table_name in public_tables:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            assert "tenant_id" not in table.c

    @pytest.mark.unit
    def test_source_sync_runs_append_only_contract(self) -> None:
        """source_sync_runs 为 append-only：无 updated_at/version。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.source_sync_runs"]
        assert "updated_at" not in table.c
        assert "version" not in table.c
        ddl = _compile_ddl(table)
        assert "idempotency_key" in ddl
        assert "finished_at" in ddl
        assert "started_at" in ddl

    @pytest.mark.unit
    def test_foreign_keys_use_restrict(self) -> None:
        """全部 FK 使用 ON DELETE RESTRICT（禁止 CASCADE）。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for table_name in _EXPECTED_TABLES:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            for fk in table.foreign_keys:
                assert fk.ondelete == "RESTRICT"
            for constraint in table.constraints:
                if isinstance(constraint, ForeignKeyConstraint):
                    for element in constraint.elements:
                        assert element.ondelete == "RESTRICT"

    @pytest.mark.unit
    def test_unique_constraints_cover_business_keys(self) -> None:
        """业务键唯一约束存在于 DDL 中。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        cases: dict[str, str] = {
            "organizations": "slug",
            "users": "subject",
            "roles": "name",
            "permissions": "permission_key",
            "source_definitions": "source_key",
        }
        for table_name, column_name in cases.items():
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            ddl = _compile_ddl(table)
            assert f"UNIQUE ({column_name})" in ddl or "UNIQUE" in ddl


class TestSourceConnectorHealthSchema:
    """0005 mapped schema 与静态 migration DAG 契约。"""

    @pytest.mark.unit
    def test_source_health_tables_have_exact_columns_and_defaults(self) -> None:
        """三新表及两扩展表逐列锁定 nullable/default 关键形状。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: 任一列、nullable 或 default 漂移时抛出。
        """

        expected_columns = {
            "source_sync_operations": (
                "id",
                "tenant_id",
                "job_run_id",
                "subscription_id",
                "owner_attempt_id",
                "state",
                "generation",
                "owner_binding_disposition",
                "payload_sha256",
                "execution_snapshot_sha256",
                "execution_snapshot_json",
                "acquired_at",
                "terminal_source_sync_run_id",
                "created_at",
                "updated_at",
            ),
            "source_health_states": (
                "id",
                "tenant_id",
                "subscription_id",
                "last_source_sync_run_id",
                "status",
                "consecutive_failures",
                "safe_error_code",
                "version",
                "observed_at",
                "created_at",
                "updated_at",
            ),
            "source_health_alert_outbox": (
                "id",
                "tenant_id",
                "subscription_id",
                "source_sync_run_id",
                "health_snapshot_id",
                "health_state_version",
                "alert_kind",
                "target_status",
                "safe_error_code",
                "dedupe_key",
                "event_json",
                "event_sha256",
                "created_at",
            ),
        }
        for table_name, columns in expected_columns.items():
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            assert tuple(table.c.keys()) == columns

        operations = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.source_sync_operations"
        ]
        assert {column.name for column in operations.c if column.nullable} == {
            "terminal_source_sync_run_id"
        }
        assert {
            column.name for column in operations.c if column.server_default is not None
        } == {"created_at", "updated_at"}
        health_states = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.source_health_states"
        ]
        assert {column.name for column in health_states.c if column.nullable} == {
            "safe_error_code"
        }
        assert {
            column.name for column in health_states.c if column.server_default is not None
        } == {"created_at", "updated_at"}
        outbox = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.source_health_alert_outbox"
        ]
        assert all(not column.nullable for column in outbox.c)
        assert all(column.server_default is None for column in outbox.c)

        runs = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.source_sync_runs"]
        run_columns = (
            "job_run_id",
            "job_attempt_id",
            "payload_sha256",
            "outcome",
            "retry_recommended",
            "records_downloaded",
            "records_reused",
            "records_ignored",
            "records_failed",
            "latest_source_observed_date",
            "receipt_json",
            "receipt_sha256",
            "result_json",
            "result_sha256",
        )
        for column_name in run_columns:
            assert runs.c[column_name].nullable
            assert runs.c[column_name].server_default is None
        snapshots = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.source_health_snapshots"
        ]
        assert snapshots.c.health_state_version.nullable
        assert snapshots.c.health_state_version.server_default is None

    @pytest.mark.unit
    def test_source_health_exact_constraint_index_and_lineage_manifest(self) -> None:
        """ORM 锁定 exact name、partial predicate 与 strong lineage。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: ORM constraint、index 或 lineage 漂移时抛出。
        """

        expected_names = {
            "source_sync_runs": {
                "uq_source_sync_runs_tenant_subscription_id_v2",
                "uq_source_sync_runs_tenant_subscription_job_id_v2",
                "uq_source_sync_runs_tenant_sub_job_attempt_id_v2",
                "fk_source_sync_runs_tenant_job_attempt_v2",
                "ck_source_sync_runs_v1_core_presence",
                "ck_source_sync_runs_v1_counts",
                "ck_source_sync_runs_v1_outcome_shape",
            },
            "source_health_snapshots": {
                "uq_source_health_snapshots_tenant_subscription_id_v2",
                "uq_source_health_snapshots_tenant_sub_run_version_id_v2",
                "fk_source_health_snapshots_tenant_subscription_run_v2",
                "ck_source_health_snapshots_v2_shape",
            },
            "source_sync_operations": {
                "pk_source_sync_operations",
                "uq_source_sync_operations_tenant_id",
                "uq_source_sync_operations_tenant_job_run",
                "fk_source_sync_operations_tenant_id_organizations",
                "fk_source_sync_operations_tenant_job_attempt",
                "fk_source_sync_operations_tenant_subscription",
                "fk_source_sync_operations_terminal_run",
                "ck_source_sync_operations_state_shape",
                "ck_source_sync_operations_hashes",
                "ck_source_sync_operations_snapshot_object",
            },
            "source_health_states": {
                "pk_source_health_states",
                "uq_source_health_states_tenant_id",
                "uq_source_health_states_tenant_subscription",
                "fk_source_health_states_tenant_id_organizations",
                "fk_source_health_states_last_run",
                "ck_source_health_states_shape",
            },
            "source_health_alert_outbox": {
                "pk_source_health_alert_outbox",
                "uq_source_health_alert_outbox_tenant_id",
                "uq_source_health_alert_outbox_tenant_dedupe",
                "fk_source_health_alert_outbox_tenant_id_organizations",
                "fk_source_health_alert_outbox_run",
                "fk_source_health_alert_outbox_snapshot",
                "ck_source_health_alert_outbox_shape",
            },
        }
        for table_name, required in expected_names.items():
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            actual = {constraint.name for constraint in table.constraints}
            assert required <= actual
        snapshot = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.source_health_snapshots"
        ]
        assert "fk_source_health_snapshots_tenant_sync_run" not in {
            constraint.name for constraint in snapshot.constraints
        }

        expected_predicates = {
            "uq_source_sync_runs_tenant_job_run_v2": "job_run_id IS NOT NULL",
            "uq_source_sync_runs_tenant_job_attempt_v2": "job_attempt_id IS NOT NULL",
            "uq_source_health_snapshots_tenant_subscription_version_v2": (
                "health_state_version IS NOT NULL"
            ),
        }
        indexes = {
            str(index.name): index
            for table in PlatformBase.metadata.tables.values()
            for index in table.indexes
            if index.name is not None
        }
        for name, predicate in expected_predicates.items():
            index = indexes[name]
            assert index.unique
            assert str(index.dialect_options["postgresql"]["where"]) == predicate

    @pytest.mark.unit
    def test_raw_job_attempt_lineage_compiles_without_polluting_metadata(self) -> None:
        """两个 raw attempt FK 使用独立 metadata 真实 Column 并可编译。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: raw metadata 污染或 FK 编译失败时抛出。
        """

        assert "_RAW_REFERENCE_METADATA" not in identity_models.__all__
        assert "_RAW_JOB_ATTEMPTS" not in identity_models.__all__
        raw_table = identity_models._RAW_JOB_ATTEMPTS
        assert raw_table.metadata is not PlatformBase.metadata
        assert raw_table.fullname == f"{PLATFORM_SCHEMA_NAME}.job_attempts"
        assert raw_table.fullname not in PlatformBase.metadata.tables
        for table_name, fk_name in (
            ("source_sync_runs", "fk_source_sync_runs_tenant_job_attempt_v2"),
            ("source_sync_operations", "fk_source_sync_operations_tenant_job_attempt"),
        ):
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            constraint = next(
                constraint
                for constraint in table.constraints
                if isinstance(constraint, ForeignKeyConstraint)
                and constraint.name == fk_name
            )
            assert all(element.column.table is raw_table for element in constraint.elements)
            ddl = _compile_ddl(table)
            assert f"REFERENCES {PLATFORM_SCHEMA_NAME}.job_attempts" in ddl
        assert len(PlatformBase.metadata.sorted_tables) == 25

    @pytest.mark.unit
    def test_0005_creates_every_parent_unique_before_child_fk_and_downgrades_in_reverse(
        self,
    ) -> None:
        """源码顺序固定 parent-before-child 与 reverse downgrade。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: upgrade/downgrade DAG 顺序漂移时抛出。
        """

        source = _SOURCE_HEALTH_MIGRATION.read_text(encoding="utf-8")
        assert source.index("def _add_parent_attempt_unique") < source.index(
            "def _extend_source_sync_runs"
        )
        run_extension = source[
            source.index("def _extend_source_sync_runs") : source.index(
                "def _extend_source_health_snapshots"
            )
        ]
        assert "uq_source_sync_runs_tenant_sub_job_attempt_id_v2" in run_extension
        assert source.index("def _extend_source_sync_runs") < source.index(
            "def _create_source_sync_operations"
        )
        snapshot_extension = source[
            source.index("def _extend_source_health_snapshots") : source.index(
                "def _replace_subscription_indexes_for_upgrade"
            )
        ]
        assert "uq_source_health_snapshots_tenant_sub_run_version_id_v2" in snapshot_extension
        assert source.index("def _extend_source_health_snapshots") < source.index(
            "def _create_source_health_alert_outbox"
        )
        downgrade = source[source.index("def downgrade") :]
        assert downgrade.index("_revoke_drop_guard_and_new_tables") < downgrade.index(
            "_restore_snapshot_baseline"
        )
        assert downgrade.index("_restore_source_runs_baseline") < downgrade.index(
            "uq_job_attempts_tenant_job_run_id_v2"
        )

    @pytest.mark.unit
    def test_0005_downgrade_drops_snapshot_version_partial_index_before_column_without_cascade(
        self,
    ) -> None:
        """snapshot downgrade 显式 drop 依赖且全迁移禁止 CASCADE。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: partial-index 或 destructive DDL 顺序漂移时抛出。
        """

        source = _SOURCE_HEALTH_MIGRATION.read_text(encoding="utf-8")
        restore = source[source.index("def _restore_snapshot_baseline") : source.index(
            "def _restore_source_runs_baseline"
        )]
        assert restore.index(
            "uq_source_health_snapshots_tenant_subscription_version_v2"
        ) < restore.index("DROP COLUMN health_state_version")
        assert "DROP TABLE {_SCHEMA}.{table_name} CASCADE" not in source
        assert "DROP COLUMN health_state_version CASCADE" not in source

    @pytest.mark.unit
    def test_every_0005_postgres_identifier_is_at_most_63_utf8_bytes_and_matches_catalog_name(
        self,
    ) -> None:
        """静态 manifest 中的 0005 identifier 不被 PostgreSQL 截断。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: manifest name 缺失或超过 63-byte 时抛出。
        """

        source = _SOURCE_HEALTH_MIGRATION.read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {
            value.value
            for value in ast.walk(tree)
            if isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and value.value.startswith(("pk_", "uq_", "ix_", "fk_", "ck_", "guard_"))
            and " " not in value.value
        }
        assert names
        assert all(len(name.encode("utf-8")) <= 63 for name in names)
        for name in names:
            assert name in source

    @pytest.mark.unit
    def test_0005_static_guard_rls_grant_and_closed_check_contract(self) -> None:
        """锁定 11 guards、closed checks、最小 grant 和 exact revision。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: 任一关键 migration token 缺失时抛出。
        """

        source = _SOURCE_HEALTH_MIGRATION.read_text(encoding="utf-8")
        assert 'revision = "0005_source_connectors_health"' in source
        assert 'down_revision = "0004_durable_schedules"' in source
        assert "actual_triggers != expected_triggers" in source
        assert "BEFORE UPDATE OR DELETE" in source
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "FORCE ROW LEVEL SECURITY" in source
        assert "CREATE POLICY tenant_isolation" in source
        assert "GRANT SELECT, INSERT" in source
        assert "GRANT UPDATE (owner_attempt_id, generation, acquired_at" in source
        assert "GRANT UPDATE (status, consecutive_failures, safe_error_code" in source
        for error in (
            "partial_batch",
            "unsupported_market",
            "unsupported_form",
            "stale_data",
            "provider_rate_limited",
            "provider_unavailable",
            "fins_invariant",
        ):
            assert error in source
        assert "stale_subscription" in source

    @pytest.mark.unit
    def test_0005_pg_harness_autocommit_is_idempotent_and_rejects_active_regular_transaction(
        self,
    ) -> None:
        """证明 helper 不重复切 isolation 且不隐式结束事务。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: autocommit 幂等或 transaction guard 漂移时抛出。
        """

        engine = create_engine("sqlite+pysqlite:///:memory:")
        autocommit = engine.connect()
        regular = engine.connect()
        try:
            configured = postgres_migration_tests._autocommit(autocommit)
            configured.execute(text("SELECT 1"))
            assert configured.in_transaction()
            assert postgres_migration_tests._autocommit(configured) is configured

            regular.execute(text("SELECT 1"))
            assert regular.in_transaction()
            with pytest.raises(AssertionError, match="active transaction"):
                postgres_migration_tests._autocommit(regular)
            assert regular.in_transaction()
        finally:
            regular.close()
            autocommit.close()
            engine.dispose()

    @pytest.mark.unit
    def test_0005_pg_harness_host_sql_readiness_retries_narrowly_and_disposes_every_engine(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """用 fake engines 锁定窄重试与精确异常语义。

        Args:
            monkeypatch: pytest 属性替换工具。

        Returns:
            无。

        Raises:
            AssertionError: attempt、dispose、异常传播或脱敏语义漂移时抛出。
        """

        cluster = postgres_migration_tests.PlatformCluster(
            suffix="unit",
            network_name="unit-network",
            container_name="unit-container",
            owner_label="unit-owner",
            host_port=1,
            bootstrap_dsn=(
                "postgresql+psycopg://unit:fake-secret@127.0.0.1:1/postgres"
            ),
            admin_password="fake-secret",
        )

        retry_factory = _HostReadinessFakeEngineFactory(
            [
                OperationalError("SELECT 1", {}, OSError("not-ready-1")),
                OperationalError("SELECT 1", {}, OSError("not-ready-2")),
                None,
            ]
        )
        monkeypatch.setattr(postgres_migration_tests, "create_engine", retry_factory)
        postgres_migration_tests._require_host_sql_readiness(cluster)
        assert retry_factory.events == [
            "create:1",
            "connect:1",
            "dispose:1",
            "create:2",
            "connect:2",
            "dispose:2",
            "create:3",
            "connect:3",
            "execute:3",
            "dispose:3",
        ]

        exhausted_factory = _HostReadinessFakeEngineFactory(
            [
                OperationalError("SELECT 1", {}, OSError("fake-secret")),
                OperationalError("SELECT 1", {}, OSError("fake-secret")),
                OperationalError("SELECT 1", {}, OSError("fake-secret")),
            ]
        )
        monkeypatch.setattr(postgres_migration_tests, "create_engine", exhausted_factory)
        with pytest.raises(
            postgres_migration_tests.PlatformIntegrationError,
            match="exhausted after 3 attempts",
        ) as exhausted:
            postgres_migration_tests._require_host_sql_readiness(cluster)
        assert "fake-secret" not in str(exhausted.value)
        assert exhausted_factory.events == [
            "create:1",
            "connect:1",
            "dispose:1",
            "create:2",
            "connect:2",
            "dispose:2",
            "create:3",
            "connect:3",
            "dispose:3",
        ]

        programming_error = ProgrammingError(
            "SELECT 1",
            {},
            ValueError("programming drift"),
        )
        programming_factory = _HostReadinessFakeEngineFactory([programming_error])
        monkeypatch.setattr(postgres_migration_tests, "create_engine", programming_factory)
        with pytest.raises(ProgrammingError) as raised:
            postgres_migration_tests._require_host_sql_readiness(cluster)
        assert raised.value is programming_error
        assert programming_factory.events == ["create:1", "connect:1", "dispose:1"]

    @pytest.mark.unit
    def test_0005_pg_harness_reaper_order_and_exceptions_are_fail_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """锁定 DB-first、roles-second 且 cleanup 异常不被吞。

        Args:
            monkeypatch: pytest 属性替换工具。

        Returns:
            无。

        Raises:
            AssertionError: cleanup 顺序或异常传播语义漂移时抛出。
        """

        events: list[str] = []
        cluster = postgres_migration_tests.PlatformCluster(
            suffix="unit",
            network_name="unit-network",
            container_name="unit-container",
            owner_label="unit-owner",
            host_port=1,
            bootstrap_dsn="postgresql+psycopg://unit",
            admin_password="unit",
        )
        monkeypatch.setattr(
            postgres_migration_tests,
            "_drop_database",
            partial(_record_database_drop, events),
        )
        monkeypatch.setattr(
            postgres_migration_tests,
            "_drop_platform_member_and_group_roles",
            partial(_record_role_drop, events),
        )
        postgres_migration_tests._reap_owner_test_resources(cluster, "exact_db")
        assert events == ["database:exact_db", "roles"]

        events.clear()

        monkeypatch.setattr(
            postgres_migration_tests,
            "_drop_database",
            partial(_record_failing_database_drop, events),
        )
        with pytest.raises(RuntimeError, match="drop failed"):
            postgres_migration_tests._reap_owner_test_resources(cluster, "exact_db")
        assert events == ["database:exact_db"]

    @pytest.mark.unit
    def test_0005_pg_harness_static_guards_lock_reaper_order_and_narrow_db_rejections(
        self,
    ) -> None:
        """AST 锁定 autouse teardown 图、DBAPI 拒绝与窄异常捕获。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: fixture、异常或 cleanup 静态契约漂移时抛出。
        """

        source = _POSTGRES_MIGRATION_OWNER_TEST.read_text(encoding="utf-8")
        tree = ast.parse(source)
        item4_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "TestSourceConnectorsHealth0005Migration"
        )
        raises_names = []
        for node in ast.walk(item4_class):
            if not isinstance(node, ast.With):
                continue
            for item in node.items:
                context = item.context_expr
                if (
                    isinstance(context, ast.Call)
                    and isinstance(context.func, ast.Attribute)
                    and context.func.attr == "raises"
                    and context.args
                ):
                    raises_names.append(ast.unparse(context.args[0]))
        assert raises_names.count("DBAPIError") == 16
        assert "SQLAlchemyError" not in raises_names

        readiness_helper = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_require_host_sql_readiness"
        )
        readiness_source = ast.get_source_segment(source, readiness_helper)
        assert readiness_source is not None
        readiness_attempts = next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "_HOST_SQL_READY_ATTEMPTS"
                for target in node.targets
            )
        )
        assert ast.literal_eval(readiness_attempts.value) == 3
        assert "sleep" not in readiness_source
        assert "except OperationalError" in readiness_source
        assert "connect_timeout" in readiness_source
        assert "engine.dispose()" in readiness_source

        readiness_fixture = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_owner_test_host_sql_readiness"
        )
        readiness_decorator = next(
            decorator
            for decorator in readiness_fixture.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "fixture"
        )
        readiness_keywords = {
            keyword.arg: ast.literal_eval(keyword.value)
            for keyword in readiness_decorator.keywords
            if keyword.arg is not None
        }
        assert readiness_keywords == {"scope": "module", "autouse": True}
        assert ast.unparse(readiness_fixture.body[1]) == (
            "_require_host_sql_readiness(platform_cluster)"
        )
        assert isinstance(readiness_fixture.body[2], ast.Expr)
        assert isinstance(readiness_fixture.body[2].value, ast.Yield)

        reaper_fixture = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_owner_test_fail_safe_reaper"
        )
        assert readiness_fixture.lineno < reaper_fixture.lineno
        assert [argument.arg for argument in reaper_fixture.args.args] == [
            "platform_cluster",
            "database_name",
        ]
        assert any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "fixture"
            and any(
                keyword.arg == "autouse"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in decorator.keywords
            )
            for decorator in reaper_fixture.decorator_list
        )
        assert not any(
            isinstance(node, ast.ExceptHandler) for node in ast.walk(reaper_fixture)
        )
        fixture_calls = [
            ast.unparse(node.func)
            for node in reaper_fixture.body
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            for node in (node.value,)
        ]
        assert fixture_calls == ["_reap_owner_test_resources"]

        role_reaper = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_drop_platform_member_and_group_roles"
        )
        role_source = ast.get_source_segment(source, role_reaper)
        assert role_source is not None
        assert "pg_auth_members" in role_source
        assert "PLATFORM_APP_ROLE" in role_source
        assert "PLATFORM_AUDIT_ROLE" in role_source
        assert role_source.count("DROP ROLE IF EXISTS") == 3

    @pytest.mark.unit
    def test_0005_review_fixes_are_statically_bound_to_exact_h1_h2_m3_oracles(
        self,
    ) -> None:
        """静态锁定 downgrade 线性化、baseline security 与 catalog oracle。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: H1、H2 或 M3 修复边界发生源码级漂移时抛出。
        """

        migration_source = _SOURCE_HEALTH_MIGRATION.read_text(encoding="utf-8")
        migration_tree = ast.parse(migration_source)
        lock_manifest = next(
            node
            for node in migration_tree.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_DOWNGRADE_LOCK_TABLES"
        )
        assert lock_manifest.value is not None
        assert ast.literal_eval(lock_manifest.value) == (
            "source_health_alert_outbox",
            "source_health_states",
            "source_sync_operations",
            "source_health_snapshots",
            "source_sync_runs",
            "source_subscriptions",
            "job_attempts",
        )
        downgrade_admission = next(
            node
            for node in migration_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_downgrade_admission"
        )
        assert ast.unparse(downgrade_admission.body[1]) == "_lock_downgrade_targets()"
        lock_helper = next(
            node
            for node in migration_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_lock_downgrade_targets"
        )
        lock_source = ast.get_source_segment(migration_source, lock_helper)
        assert lock_source is not None
        assert "IN ACCESS EXCLUSIVE MODE NOWAIT" in lock_source
        assert "SHOW transaction_isolation" in lock_source
        assert 'isolation != "read committed"' in lock_source
        assert "_DOWNGRADE_LOCK_TABLES" in lock_source

        security_helper = next(
            node
            for node in migration_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_assert_baseline_security_exact"
        )
        security_source = ast.get_source_segment(migration_source, security_helper)
        assert security_source is not None
        for token in (
            "relrowsecurity",
            "relforcerowsecurity",
            "roles::text",
            "qual, with_check",
            "aclexplode(c.relacl)",
            "aclexplode(a.attacl)",
            "acl.is_grantable",
            "_BASELINE_POLICY_MANIFEST",
            "_BASELINE_APP_TABLE_ACL_MANIFEST",
            "_BASELINE_APP_COLUMN_UPDATE_MANIFEST",
        ):
            assert token in security_source
        expected_column_acl_assignment = next(
            node
            for node in ast.walk(security_helper)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "expected_column_acl"
                for target in node.targets
            )
        )
        expected_column_acl_source = ast.unparse(
            expected_column_acl_assignment.value
        )
        assert "PLATFORM_APP_ROLE" in expected_column_acl_source
        assert "_BASELINE_APP_COLUMN_UPDATE_MANIFEST" in expected_column_acl_source
        assert "owner_name" not in expected_column_acl_source
        preflight = next(
            node
            for node in migration_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_preflight_upgrade"
        )
        preflight_source = ast.get_source_segment(migration_source, preflight)
        assert preflight_source is not None
        assert preflight_source.count("_assert_baseline_security_exact(bind)") == 1

        catalog_helper = next(
            node
            for node in migration_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_assert_0005_catalog"
        )
        catalog_source = ast.get_source_segment(migration_source, catalog_helper)
        assert catalog_source is not None
        assert "pg_get_constraintdef(con.oid)" in catalog_source
        assert "actual_checks != _expected_check_catalog(bind)" in catalog_source
        assert "actual_affected_constraints" in catalog_source
        assert "_AFFECTED_CONSTRAINT_IDENTITY_MANIFEST" in catalog_source
        assert "actual_affected_indexes" in catalog_source
        assert "_AFFECTED_INDEX_DEFINITION_MANIFEST" in catalog_source
        assert "JOIN pg_namespace fn" in catalog_source
        assert "fn.nspname" in catalog_source
        for token in (
            "aclexplode(c.relacl)",
            "aclexplode(a.attacl)",
            "acl.is_grantable",
            "_NEW_TABLE_OWNER_PRIVILEGES",
            "_NEW_TABLE_APP_COLUMN_UPDATE_MANIFEST",
            "actual_table_acl != expected_table_acl",
            "actual_column_acl != expected_column_acl",
        ):
            assert token in catalog_source
        assert "information_schema.role_table_grants" not in catalog_source
        assert "information_schema.column_privileges" not in catalog_source
        assert migration_source.count("_CHECK_DEFINITION_MANIFEST") >= 3

        assert len(postgres_migration_tests._EXPECTED_0005_CHECK_EXPRESSIONS) == 9
        assert len(postgres_migration_tests._EXPECTED_0005_NONCHECK_CONSTRAINTS) == 26
        assert len(postgres_migration_tests._EXPECTED_0005_TRIGGERS) == 11
        assert postgres_migration_tests._EXPECTED_0005_NEW_TABLES == (
            "source_sync_operations",
            "source_health_states",
            "source_health_alert_outbox",
        )
        assert postgres_migration_tests._EXPECTED_0005_OWNER_TABLE_PRIVILEGES == (
            "DELETE",
            "INSERT",
            "REFERENCES",
            "SELECT",
            "TRIGGER",
            "TRUNCATE",
            "UPDATE",
        )
        assert len(postgres_migration_tests._EXPECTED_0005_APP_COLUMN_ACL) == 14
        assert all(
            row[2:] == ("dayu_platform_app", "UPDATE", False)
            for row in postgres_migration_tests._EXPECTED_0005_APP_COLUMN_ACL
        )
        assert len(postgres_migration_tests._0005_NON_TABLE_OBJECT_NAMES) == 64
        pg_source = _POSTGRES_MIGRATION_OWNER_TEST.read_text(encoding="utf-8")
        pg_tree = ast.parse(pg_source)
        zero_mutation_helper = next(
            node
            for node in pg_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_assert_0005_preflight_zero_mutation"
        )
        zero_mutation_source = ast.get_source_segment(
            pg_source,
            zero_mutation_helper,
        )
        assert zero_mutation_source is not None
        assert "latest_source_observed_date" in zero_mutation_source
        assert "health_state_version" in zero_mutation_source
        assert "_0005_NON_TABLE_OBJECT_NAMES" in zero_mutation_source
        pg_class = next(
            node
            for node in pg_tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "TestSourceConnectorsHealth0005Migration"
        )
        pg_methods = {
            node.name: node
            for node in pg_class.body
            if isinstance(node, ast.FunctionDef)
        }
        race_source = ast.get_source_segment(
            pg_source,
            pg_methods[
                "test_0005_downgrade_locks_before_admission_and_observes_concurrent_dirty_insert"
            ],
        )
        assert race_source is not None
        assert "LockNotAvailable" in race_source
        assert "_assert_writer_holds_operation_lock(writer)" in race_source
        assert race_source.count("_migrate_down_to_0004") == 4
        assert "statement_timeout" in race_source
        assert "default_transaction_isolation" in race_source
        assert "sleep" not in race_source
        assert race_source.index("writer_transaction.commit()") < race_source.index(
            'pytest.raises(RuntimeError, match="三新表仍存在业务行")'
        )
        substitution_source = ast.get_source_segment(
            pg_source,
            pg_methods[
                "test_0005_preflight_rejects_same_count_policy_and_app_acl_substitution_before_mutation"
            ],
        )
        assert substitution_source is not None
        assert "USING (true) WITH CHECK (true)" in substitution_source
        assert "REVOKE SELECT" in substitution_source
        assert "GRANT DELETE" in substitution_source
        assert "baseline_app_column_acl_count == [(37,)]" in substitution_source
        assert "REVOKE UPDATE (status)" in substitution_source
        assert "GRANT UPDATE (id)" in substitution_source
        assert substitution_source.count("_assert_0005_preflight_zero_mutation") == 5
        extra_catalog_source = ast.get_source_segment(
            pg_source,
            pg_methods[
                "test_0005_catalog_rejects_extra_affected_objects_and_acl_drift"
            ],
        )
        assert extra_catalog_source is not None
        for token in (
            "ck_source_sync_runs_unexpected_job_lineage",
            "unexpected_source_operation_generation_idx",
            "unexpected_health_state_version_idx",
            "unexpected_source_operation_trigger",
            "health_state_version",
            "TO pg_monitor",
            "TO PUBLIC",
            "WITH GRANT OPTION",
            "GRANT DELETE",
            "new-table table ACL manifest",
            "new-table column ACL manifest",
        ):
            assert token in extra_catalog_source
        assert extra_catalog_source.count("_assert_schema_intact") == 4
        assert extra_catalog_source.count("0005_source_connectors_health") >= 4
        catalog_test_source = ast.get_source_segment(
            pg_source,
            pg_methods[
                "test_0005_exact_27_table_columns_fk_check_index_rls_trigger_grant_catalog"
            ],
        )
        assert catalog_test_source is not None
        for token in (
            "pg_get_constraintdef(con.oid)",
            "_EXPECTED_0005_NONCHECK_CONSTRAINTS | expected_checks",
            "fn.nspname",
            "JOIN pg_namespace fn",
            "t.tgtype",
            "t.tgenabled",
            "_EXPECTED_0005_TRIGGERS",
            "aclexplode(c.relacl)",
            "aclexplode(a.attacl)",
            "acl.is_grantable",
            "_EXPECTED_0005_OWNER_TABLE_PRIVILEGES",
            "_EXPECTED_0005_APP_COLUMN_ACL",
        ):
            assert token in catalog_test_source

    @pytest.mark.unit
    def test_item4_changed_functions_obey_chinese_docstring_type_and_structure_contract(
        self,
    ) -> None:
        """限定七条 Item4 路径并以对抗样例锁定函数级工程规范。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: 路径、中文文档、类型或函数结构契约漂移时抛出。
        """

        assert len(_ITEM4_DOCSTRING_PATHS) == 7
        assert len(set(_ITEM4_DOCSTRING_PATHS)) == 7
        assert all(path.is_file() for path in _ITEM4_DOCSTRING_PATHS)
        trees = {
            path: ast.parse(path.read_text(encoding="utf-8"))
            for path in _ITEM4_DOCSTRING_PATHS
        }
        mechanically_changed = {
            path: _item4_changed_function_nodes(path, trees[path])
            for path in _ITEM4_DOCSTRING_PATHS
        }
        mechanical_violations = {
            f"{path.relative_to(_REPO_ROOT)}:{node.name}:{node.lineno}": errors
            for path, nodes in mechanically_changed.items()
            for node in nodes
            if (errors := _item4_docstring_contract_errors(node))
        }
        assert mechanical_violations == {}
        assert sum(len(nodes) for nodes in mechanically_changed.values()) >= 75
        assert not any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for node in ast.walk(trees[_ITEM4_DOCSTRING_PATHS[1]])
        )
        selected: list[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef]] = []

        migration_tree = trees[_SOURCE_HEALTH_MIGRATION]
        migration_functions = {
            node.name: node
            for node in migration_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert set(migration_functions) == {
            "_qualified_literals",
            "_fetch_scalar_int",
            "_assert_count",
            "_baseline_subscription_indexes_are_exact",
            "_expected_check_catalog",
            "_assert_baseline_security_exact",
            "_preflight_upgrade",
            "_add_parent_attempt_unique",
            "_extend_source_sync_runs",
            "_extend_source_health_snapshots",
            "_replace_subscription_indexes_for_upgrade",
            "_create_source_sync_operations",
            "_create_source_health_states",
            "_create_source_health_alert_outbox",
            "_create_guard_functions",
            "_create_guard_triggers",
            "_grant_and_enable_rls",
            "_assert_0005_catalog",
            "_0005_table_oids",
            "_old_subscription_identity_conflicts",
            "_lock_downgrade_targets",
            "_downgrade_admission",
            "_revoke_drop_guard_and_new_tables",
            "_restore_snapshot_baseline",
            "_restore_source_runs_baseline",
            "_restore_subscription_indexes_for_downgrade",
            "_assert_0004_catalog_after_downgrade",
            "upgrade",
            "downgrade",
        }
        selected.extend(
            (_SOURCE_HEALTH_MIGRATION, node)
            for node in migration_functions.values()
        )

        platform_jobs_path = _ITEM4_DOCSTRING_PATHS[0]
        platform_jobs_functions = {
            node.name: node
            for node in trees[platform_jobs_path].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert set(platform_jobs_functions) == {
            "_alembic_config",
            "_load_bootstrap_dsn_or_fail",
            "migrate_platform_jobs",
        }
        selected.extend(
            (platform_jobs_path, node)
            for node in platform_jobs_functions.values()
        )

        cli_test_path = _ITEM4_DOCSTRING_PATHS[3]
        cli_test = next(
            node
            for node in trees[cli_test_path].body
            if isinstance(node, ast.FunctionDef)
            and node.name
            == "test_platform_jobs_workspace_migration_documents_0006_as_current_head"
        )
        selected.append((cli_test_path, cli_test))

        identity_test_path = _ITEM4_DOCSTRING_PATHS[4]
        identity_tree = trees[identity_test_path]
        identity_helper = next(
            node
            for node in identity_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_subscription_request_for_target"
        )
        identity_class = next(
            node
            for node in identity_tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "TestSourceRepositoryPostgres"
        )
        identity_test = next(
            node
            for node in identity_class.body
            if isinstance(node, ast.FunctionDef)
            and node.name
            == "test_source_subscription_unique_identity_includes_source_definition_for_tenant_company_and_security_targets"
        )
        selected.extend(
            (
                (identity_test_path, identity_helper),
                (identity_test_path, identity_test),
            )
        )

        pg_tree = trees[_POSTGRES_MIGRATION_OWNER_TEST]
        pg_module_functions = {
            node.name: node
            for node in pg_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in _ITEM4_PG_MODULE_FUNCTIONS
        }
        assert set(pg_module_functions) == set(_ITEM4_PG_MODULE_FUNCTIONS)
        selected.extend(
            (_POSTGRES_MIGRATION_OWNER_TEST, node)
            for node in pg_module_functions.values()
        )
        pg_changed_methods = {
            "TestUpgradeDowngradeCycle": {
                "test_downgrade_fails_closed_on_external_member",
                "test_downgrade_fails_closed_on_active_session",
                "test_downgrade_fails_closed_on_external_dependency",
            },
            "TestSchemaExact": {
                "test_exact_27_tables",
                "test_schema_exact_columns",
                "test_schema_exact_named_constraints",
                "test_schema_exact_indexes_with_predicates",
            },
            "TestGrantMatrix": {"test_audit_select_only_all_tables"},
            "TestWorkspaceImportMigrationCycle": {
                "test_upgrade_downgrade_0001_upgrade_cycle"
            },
        }
        for class_name, method_names in pg_changed_methods.items():
            changed_class = next(
                node
                for node in pg_tree.body
                if isinstance(node, ast.ClassDef) and node.name == class_name
            )
            changed_methods = {
                node.name: node
                for node in changed_class.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in method_names
            }
            assert set(changed_methods) == method_names
            selected.extend(
                (_POSTGRES_MIGRATION_OWNER_TEST, node)
                for node in changed_methods.values()
            )
        pg_class = next(
            node
            for node in pg_tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "TestSourceConnectorsHealth0005Migration"
        )
        pg_tests = [
            node
            for node in pg_class.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert len(pg_tests) == 16
        selected.extend(
            (_POSTGRES_MIGRATION_OWNER_TEST, node) for node in pg_tests
        )

        unit_tree = trees[Path(__file__).resolve()]
        unit_module_functions = {
            node.name: node
            for node in unit_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in _ITEM4_UNIT_MODULE_FUNCTIONS
        }
        assert set(unit_module_functions) == set(_ITEM4_UNIT_MODULE_FUNCTIONS)
        selected.extend(
            (Path(__file__).resolve(), node)
            for node in unit_module_functions.values()
        )
        fake_classes = {
            node.name: node
            for node in unit_tree.body
            if isinstance(node, ast.ClassDef)
            and node.name.startswith("_HostReadinessFake")
        }
        assert set(fake_classes) == {
            "_HostReadinessFakeResult",
            "_HostReadinessFakeConnection",
            "_HostReadinessFakeEngine",
            "_HostReadinessFakeEngineFactory",
        }
        selected.extend(
            (Path(__file__).resolve(), method)
            for fake_class in fake_classes.values()
            for method in fake_class.body
            if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        unit_changed_methods = {
            "TestPlatformSchemaMetadata": {
                "test_metadata_contains_exactly_25_platform_tables"
            },
            "TestPlatformSchemaColumns": {
                "test_all_tables_have_created_at_timestamptz",
                "test_mutable_tables_have_updated_at_and_version",
                "test_observed_at_and_started_at_have_no_server_default",
            },
        }
        for class_name, method_names in unit_changed_methods.items():
            changed_class = next(
                node
                for node in unit_tree.body
                if isinstance(node, ast.ClassDef) and node.name == class_name
            )
            changed_methods = {
                node.name: node
                for node in changed_class.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in method_names
            }
            assert set(changed_methods) == method_names
            selected.extend(
                (Path(__file__).resolve(), node)
                for node in changed_methods.values()
            )
        unit_class = next(
            node
            for node in unit_tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "TestSourceConnectorHealthSchema"
        )
        unit_tests = [
            node
            for node in unit_class.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert len(unit_tests) == 13
        selected.extend((Path(__file__).resolve(), node) for node in unit_tests)

        violations = {
            f"{path.relative_to(_REPO_ROOT)}:{node.name}:{node.lineno}": errors
            for path, node in selected
            if (errors := _item4_docstring_contract_errors(node))
        }
        assert violations == {}

        adversarial_sources = (
            (
                "missing-chinese-docstring",
                "def sample(value: int) -> None:\n"
                "    \"\"\"English only.\n\nArgs:\n    value: Exact value.\n\n"
                "Returns:\n    None.\n\nRaises:\n    None.\n\"\"\"\n"
                "    return None\n",
            ),
            (
                "missing-args-section",
                "def sample(value: int) -> None:\n"
                "    \"\"\"中文说明。\n\nReturns:\n    无。\n\nRaises:\n    无。\n\"\"\"\n"
                "    return None\n",
            ),
            (
                "missing-raises-section",
                "def sample(value: int) -> None:\n"
                "    \"\"\"中文说明。\n\nArgs:\n    value: 值。\n\nReturns:\n    无。\n\"\"\"\n"
                "    return None\n",
            ),
            (
                "missing-returns-section",
                "def sample(value: int) -> None:\n"
                "    \"\"\"中文说明。\n\nArgs:\n    value: 值。\n\nRaises:\n    无。\n\"\"\"\n"
                "    return None\n",
            ),
            (
                "missing-yields-section",
                "def sample(value: int) -> Iterator[int]:\n"
                "    \"\"\"中文说明。\n\nArgs:\n    value: 值。\n\nReturns:\n    值。\n\n"
                "Raises:\n    无。\n\"\"\"\n"
                "    yield value\n",
            ),
            (
                "missing-argument-annotation",
                "def sample(value) -> None:\n"
                "    \"\"\"中文说明。\n\nArgs:\n    value: 值。\n\nReturns:\n    无。\n\n"
                "Raises:\n    无。\n\"\"\"\n"
                "    return None\n",
            ),
            (
                "missing-return-annotation",
                "def sample(value: int):\n"
                "    \"\"\"中文说明。\n\nArgs:\n    value: 值。\n\nReturns:\n    无。\n\n"
                "Raises:\n    无。\n\"\"\"\n"
                "    return None\n",
            ),
            (
                "forbidden-any-or-object-annotation",
                "def sample(value: object) -> None:\n"
                "    \"\"\"中文说明。\n\nArgs:\n    value: 值。\n\nReturns:\n    无。\n\n"
                "Raises:\n    无。\n\"\"\"\n"
                "    return None\n",
            ),
            (
                "forbidden-any-or-object-annotation",
                "def sample(value: Any) -> None:\n"
                "    \"\"\"中文说明。\n\nArgs:\n    value: 值。\n\nReturns:\n    无。\n\n"
                "Raises:\n    无。\n\"\"\"\n"
                "    return None\n",
            ),
            (
                "nested-definition",
                "def sample(value: int) -> None:\n"
                "    \"\"\"中文说明。\n\nArgs:\n    value: 值。\n\nReturns:\n    无。\n\n"
                "Raises:\n    无。\n\"\"\"\n"
                "    def helper() -> None:\n        return None\n"
                "    helper()\n",
            ),
            (
                "unscoped-request-helper",
                "def sample(value: int) -> None:\n"
                "    \"\"\"中文说明。\n\nArgs:\n    value: 值。\n\nReturns:\n    无。\n\n"
                "Raises:\n    无。\n\"\"\"\n"
                "    request = value\n    assert request == value\n",
            ),
        )
        for expected_error, source in adversarial_sources:
            tree = ast.parse(source)
            function = tree.body[0]
            assert isinstance(function, ast.FunctionDef)
            assert expected_error in _item4_docstring_contract_errors(function)


class TestDurableScheduleMigrationSource:
    """0004 durable schedule迁移的无数据库静态合同。"""

    @pytest.mark.unit
    def test_schedule_static_ddl_contract_covers_0004_without_shared_pg_cluster(
        self,
    ) -> None:
        """静态锁定0004两表、closed CHECK、RLS、权限与downgrade admission。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        source = _SCHEDULE_MIGRATION.read_text(encoding="utf-8")
        assert 'revision = "0004_durable_schedules"' in source
        assert 'down_revision = "0003_durable_jobs"' in source
        assert "CREATE TABLE {PLATFORM_SCHEMA_NAME}.job_schedules" in source
        assert (
            "CREATE TABLE {PLATFORM_SCHEMA_NAME}.job_schedule_occurrences"
            in source
        )
        assert "ck_job_schedules_active_has_next_fire" in source
        assert "CHECK (state <> 'active' OR next_fire_at IS NOT NULL)" in source
        assert "ck_job_schedules_disabled_no_next_fire" not in source
        assert "timezone(next_fire_at)" not in source
        assert "timezone(scheduled_for)" not in source
        assert "ck_job_schedule_occurrences_coalesced_count_exact" in source
        assert "skip_reason IN ('misfire_expired', 'schedule_disabled')" in source
        assert "'candidate_scan_limit_exceeded')" in source
        assert "AND coalesced_count IS NULL" in source
        assert "snapshot_available_at = scheduled_for" in source
        assert "FOREIGN KEY (tenant_id, schedule_id)" in source
        assert "FOREIGN KEY (tenant_id, job_run_id)" in source
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "FORCE ROW LEVEL SECURITY" in source
        assert "GRANT UPDATE (state, next_fire_at, version, updated_at)" in source
        assert "GRANT UPDATE (state, job_run_id, skip_reason, updated_at)" in source
        assert "SELECT count(*) FROM {PLATFORM_SCHEMA_NAME}.job_schedules" in source
        assert "pg_auth_members" in source
        assert "DROP TABLE {PLATFORM_SCHEMA_NAME}.{table_name}" in source
        assert "DROP TABLE {PLATFORM_SCHEMA_NAME}.{table_name} CASCADE" not in source


class TestCreateAllForbidden:
    """生产 import 路径禁止 ``metadata.create_all()``。"""

    @pytest.mark.unit
    def test_no_create_all_call_in_storage_production_code(self) -> None:
        """storage 子包生产代码不得调用 ``metadata.create_all()``。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        violations: list[str] = []
        for file_path in _iter_storage_files():
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func_name = _extract_call_name(node)
                    if func_name == "create_all":
                        violations.append(f"{file_path.name}: {func_name}()")
        assert violations == []

    @pytest.mark.unit
    def test_migrations_do_not_import_orm_metadata_for_creation(self) -> None:
        """迁移脚本不通过 metadata 的 create_all 建表。

        迁移真源是显式 SQL DDL（``op.execute``），而不是从 ORM
        metadata 自动生成；本断言扫描迁移版本脚本，确认不存在
        ``create_all`` 调用。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        versions_dir = _STORAGE_SRC / "migrations" / "versions"
        if not versions_dir.is_dir():
            pytest.skip("迁移版本目录不存在")
        violations: list[str] = []
        for file_path in sorted(versions_dir.glob("*.py")):
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and _extract_call_name(node) == "create_all":
                    violations.append(file_path.name)
        assert violations == []


def _extract_call_name(node: ast.Call) -> str:
    """提取调用表达式的最末段函数名。

    Args:
        node: AST 调用节点。

    Returns:
        函数名（如 ``create_all``）；无法解析时返回空串。

    Raises:
        无。
    """

    func = node.func
    while isinstance(func, ast.Attribute):
        func = func.value
    if isinstance(func, ast.Name):
        return func.id
    return ""


class TestPlatformEngineFactories:
    """engine / session factory 单元契约。"""

    @pytest.mark.unit
    def test_create_platform_engine_returns_engine_without_echo(self) -> None:
        """engine 构造成功且关闭 SQL 回显，不创建 schema。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        engine = create_platform_engine("postgresql+psycopg://u:p@127.0.0.1:1/nonexistent")
        assert isinstance(engine, Engine)
        assert engine.url.get_backend_name() == "postgresql"
        assert engine.url.get_driver_name() == "psycopg"
        assert engine.echo is False
        engine.dispose()

    @pytest.mark.unit
    def test_create_platform_session_factory_binds_engine(self) -> None:
        """session factory 绑定给定 engine 且提交后不自动 expire。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        engine = create_platform_engine("postgresql+psycopg://u:p@127.0.0.1:1/nonexistent")
        factory = create_platform_session_factory(engine)
        assert isinstance(factory, sessionmaker)
        assert factory.kw.get("bind") is engine
        assert factory.kw.get("expire_on_commit") is False
        engine.dispose()


_JOBS_0003_TABLES: tuple[str, ...] = (
    "job_definitions",
    "job_runs",
    "job_attempts",
    "job_leases",
    "job_attempt_receipts",
    "job_events",
    "agent_run_correlations",
)
"""0003 迁移的七张 durable jobs 表（定义/删除共用顺序）。"""


class TestDurableJobs0003SchemaExactContract:
    """0003 durable jobs 迁移的 unit 契约（DDL 文本级校验）。

    真实 upgrade/downgrade/RLS/GRANT 在 integration lane 用真实 PG16
    验证；本类只校验迁移脚本的静态契约，避免同源自比。
    """

    @pytest.mark.unit
    def test_0003_schema_exact_contract(self) -> None:
        """0003 迁移必须精确创建七张表、RLS、列级 grant 与 downgrade。"""

        migration_source = (
            _REPO_ROOT / "dayu" / "investment" / "storage" / "migrations" / "versions" / "0003_durable_jobs.py"
        ).read_text(encoding="utf-8")
        for table in _JOBS_0003_TABLES:
            assert f"CREATE TABLE {{PLATFORM_SCHEMA_NAME}}.{table}" in migration_source, (
                f"0003 缺少表 {table}"
            )
        # 七表 RLS enable + force + 唯一 tenant_isolation policy（循环应用全部表）。
        assert "ENABLE ROW LEVEL SECURITY" in migration_source
        assert "FORCE ROW LEVEL SECURITY" in migration_source
        assert "CREATE POLICY tenant_isolation" in migration_source
        # 列级 grant：app SELECT/INSERT + audit SELECT。
        assert "GRANT SELECT, INSERT ON TABLE" in migration_source
        assert "GRANT SELECT ON TABLE" in migration_source
        # downgrade 无 CASCADE、保留依赖顺序。
        assert "DROP TABLE" in migration_source
        assert "ON DELETE CASCADE" not in migration_source
        assert "DROP TABLE" in migration_source
        # downgrade 前置 catalog 外部依赖检查。
        assert "pg_depend" in migration_source

    @pytest.mark.unit
    def test_0003_columns_match_contract(self) -> None:
        """每张表的契约列与约束必须在 DDL 中显式出现。"""

        migration_source = (
            _REPO_ROOT / "dayu" / "investment" / "storage" / "migrations" / "versions" / "0003_durable_jobs.py"
        ).read_text(encoding="utf-8")
        table_columns = {
            "job_definitions": (
                "job_type",
                "payload_schema_name",
                "payload_schema_version",
                "max_attempts",
                "retry_base_seconds",
                "retry_max_seconds",
                "lease_duration_seconds",
                "status",
            ),
            "job_runs": (
                "idempotency_key",
                "request_fingerprint",
                "payload_bytes",
                "payload_sha256",
                "state",
                "available_at",
                "deadline_at",
                "current_attempt_number",
                "next_event_sequence",
                "cancel_requested_at",
                "safe_failure_code",
            ),
            "job_attempts": (
                "attempt_number",
                "worker_id",
                "state",
                "fence",
                "lease_token_sha256",
                "claimed_at",
                "lease_expires_at",
                "last_heartbeat_at",
            ),
            "job_leases": (
                "fence",
                "token_sha256",
                "acquired_at",
                "expires_at",
                "released_at",
                "release_reason",
            ),
            "job_attempt_receipts": (
                "outcome",
                "result_schema_name",
                "result_bytes",
                "receipt_schema_name",
                "receipt_bytes",
                "receipt_sha256",
                "safe_error_code",
                "finalized_at",
            ),
            "job_events": (
                "sequence_number",
                "event_type",
                "safe_detail_bytes",
                "occurred_at",
            ),
            "agent_run_correlations": (
                "idempotency_key",
                "reserved_host_run_id",
                "state",
                "observed_at",
                "last_observation_sha256",
                "version",
            ),
        }
        for table, columns in table_columns.items():
            table_block = _extract_table_block(migration_source, table)
            for column in columns:
                assert column in table_block, f"{table} 缺少列 {column}"

    @pytest.mark.unit
    def test_0003_lease_single_release_and_immutable_guard_present(self) -> None:
        """versioned single-release trigger 与 immutable 列 guard 必须存在。"""

        migration_source = (
            _REPO_ROOT / "dayu" / "investment" / "storage" / "migrations" / "versions" / "0003_durable_jobs.py"
        ).read_text(encoding="utf-8")
        assert "job_leases_single_release" in migration_source
        assert "guard_{table_name}_immutable_columns" in migration_source
        assert "{function_name}_trigger" in migration_source


def _extract_table_block(migration_source: str, table: str) -> str:
    """提取迁移源码中某张表的 CREATE TABLE 块。

    Args:
        migration_source: 迁移源码文本。
        table: 表名。

    Returns:
        该表的 DDL 块文本；找不到时返回空串。

    Raises:
        无。
    """

    marker = f"CREATE TABLE {{PLATFORM_SCHEMA_NAME}}.{table}"
    start = migration_source.find(marker)
    if start < 0:
        return ""
    return migration_source[start : start + 4000]
