"""SQLiteRunRegistry 测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from dayu.host.host_store import HostStore
from dayu.host.pending_turn_store import PendingConversationTurnState, SQLitePendingConversationTurnStore
from dayu.host.run_registry import SQLiteRunRegistry
from dayu.contracts.execution_metadata import ExecutionDeliveryContext
from dayu.contracts.run import ORPHAN_RUN_ERROR_SUMMARY, RunCancelReason, RunState
from dayu.log import Log


@pytest.fixture()
def registry(tmp_path: Path) -> SQLiteRunRegistry:
    """创建一个临时 RunRegistry。"""
    store = HostStore(tmp_path / "test.db")
    store.initialize_schema()
    return SQLiteRunRegistry(store)


class TestRegisterRun:
    """register_run 测试。"""

    @pytest.mark.unit
    def test_schema_does_not_define_ticker_column(self, registry: SQLiteRunRegistry) -> None:
        """新建 schema 的 runs 表不再包含 ticker 列。"""

        conn = registry._host_store.get_connection()
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        assert "ticker" not in columns
        assert "cancel_requested_at" in columns
        assert "cancel_requested_reason" in columns
        assert "cancel_reason" in columns

    @pytest.mark.unit
    def test_register_run_basic(self, registry: SQLiteRunRegistry) -> None:
        """注册 run，状态为 CREATED。"""
        run = registry.register_run(service_type="chat_turn")
        assert run.run_id.startswith("run_")
        assert run.service_type == "chat_turn"
        assert run.state == RunState.CREATED
        assert run.session_id is None
        assert run.started_at is None
        assert run.completed_at is None
        assert run.error_summary is None
        assert run.cancel_requested_at is None
        assert run.cancel_requested_reason is None
        assert run.cancel_reason is None

    @pytest.mark.unit
    def test_register_run_with_all_fields(self, registry: SQLiteRunRegistry) -> None:
        """注册 run 并传入所有可选字段。"""
        run = registry.register_run(
            session_id="sess-1",
            service_type="write_pipeline",
            scene_name="sec_filing",
            metadata={"delivery_channel": "wechat"},
        )
        assert run.session_id == "sess-1"
        assert run.scene_name == "sec_filing"
        assert run.metadata == {"delivery_channel": "wechat"}

    @pytest.mark.unit
    def test_register_run_has_pid(self, registry: SQLiteRunRegistry) -> None:
        """run 记录包含 owner_pid。"""
        import os
        run = registry.register_run(service_type="test")
        assert run.owner_pid == os.getpid()


class TestRunStateTransitions:
    """状态转换测试。"""

    @pytest.mark.unit
    def test_start_run(self, registry: SQLiteRunRegistry) -> None:
        """CREATED → RUNNING 转换。"""
        run = registry.register_run(service_type="test")
        started = registry.start_run(run.run_id)
        assert started.state == RunState.RUNNING
        assert started.started_at is not None

    @pytest.mark.unit
    def test_complete_run(self, registry: SQLiteRunRegistry) -> None:
        """RUNNING → SUCCEEDED 转换。"""
        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        completed = registry.complete_run(run.run_id)
        assert completed.state == RunState.SUCCEEDED
        assert completed.completed_at is not None

    @pytest.mark.unit
    def test_complete_run_allows_owned_orphan_recovery(self, registry: SQLiteRunRegistry) -> None:
        """当前 owner 可把被 cleanup 误判为 orphan 的 UNSETTLED run 修复为成功。"""

        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        registry.mark_unsettled(run.run_id, error_summary=ORPHAN_RUN_ERROR_SUMMARY)

        recovered = registry.complete_run(run.run_id)

        assert recovered.state == RunState.SUCCEEDED
        assert recovered.completed_at is not None
        assert recovered.error_summary is None

    @pytest.mark.unit
    def test_complete_run_rejects_failed_recovery(self, registry: SQLiteRunRegistry) -> None:
        """FAILED 终态不再被允许修复为 SUCCEEDED（仅 UNSETTLED 可被 owner 修复）。"""

        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        registry.fail_run(run.run_id, error_summary="business failure")

        with pytest.raises(ValueError, match="非法状态转换"):
            registry.complete_run(run.run_id)

    @pytest.mark.unit
    def test_mark_unsettled_from_running(self, registry: SQLiteRunRegistry) -> None:
        """RUNNING → UNSETTLED 合法。"""

        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        unsettled = registry.mark_unsettled(run.run_id, error_summary=ORPHAN_RUN_ERROR_SUMMARY)
        assert unsettled.state == RunState.UNSETTLED
        assert unsettled.completed_at is not None
        assert unsettled.error_summary == ORPHAN_RUN_ERROR_SUMMARY

    @pytest.mark.unit
    def test_complete_run_rejects_recovery_when_pid_reused(
        self, registry: SQLiteRunRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同 PID 但 OwnerIdentity 三元组不匹配（PID 复用）时不允许修复 UNSETTLED。"""

        from dayu.host import run_registry as run_registry_module
        from dayu.process_liveness import OwnerIdentity

        # 注册 run 时记录的"原 owner"身份
        original_owner = run_registry_module.current_owner_identity()
        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        registry.mark_unsettled(run.run_id, error_summary=ORPHAN_RUN_ERROR_SUMMARY)

        # 模拟"PID 复用"：当前进程身份的 process_start_time 与持久化记录不一致
        reused_owner = OwnerIdentity(
            pid=original_owner.pid,
            process_start_time=(
                (original_owner.process_start_time or 0.0) + 9999.0
            ),
            boot_id=original_owner.boot_id,
        )
        monkeypatch.setattr(
            run_registry_module, "current_owner_identity", lambda: reused_owner
        )

        with pytest.raises(ValueError, match="非法状态转换"):
            registry.complete_run(run.run_id)

    @pytest.mark.unit
    def test_complete_run_rejects_recovery_when_boot_id_changed(
        self, registry: SQLiteRunRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同 PID 但 boot_id 不同（系统重启）时不允许修复 UNSETTLED。"""

        from dayu.host import run_registry as run_registry_module
        from dayu.process_liveness import OwnerIdentity

        original_owner = run_registry_module.current_owner_identity()
        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        registry.mark_unsettled(run.run_id, error_summary=ORPHAN_RUN_ERROR_SUMMARY)

        rebooted_owner = OwnerIdentity(
            pid=original_owner.pid,
            process_start_time=original_owner.process_start_time,
            boot_id=(original_owner.boot_id or "") + "-rebooted",
        )
        monkeypatch.setattr(
            run_registry_module, "current_owner_identity", lambda: rebooted_owner
        )

        with pytest.raises(ValueError, match="非法状态转换"):
            registry.complete_run(run.run_id)

    @pytest.mark.unit
    def test_unsettled_is_absorbing(self, registry: SQLiteRunRegistry) -> None:
        """UNSETTLED 对非当前 owner / 非 SUCCEEDED 转换都是吸收态。"""

        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        registry.mark_unsettled(run.run_id, error_summary=ORPHAN_RUN_ERROR_SUMMARY)
        # UNSETTLED → FAILED 非法
        with pytest.raises(ValueError, match="非法状态转换"):
            registry.fail_run(run.run_id, error_summary="x")

    @pytest.mark.unit
    def test_fail_run(self, registry: SQLiteRunRegistry) -> None:
        """RUNNING → FAILED 转换。"""
        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        failed = registry.fail_run(run.run_id, error_summary="boom")
        assert failed.state == RunState.FAILED
        assert failed.error_summary == "boom"
        assert failed.completed_at is not None

    @pytest.mark.unit
    def test_mark_cancelled(self, registry: SQLiteRunRegistry) -> None:
        """RUNNING → CANCELLED 转换。"""
        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        registry.request_cancel(run.run_id, cancel_reason=RunCancelReason.TIMEOUT)
        cancelled = registry.mark_cancelled(run.run_id)
        assert cancelled.state == RunState.CANCELLED
        assert cancelled.cancel_requested_reason == RunCancelReason.TIMEOUT
        assert cancelled.cancel_reason == RunCancelReason.USER_CANCELLED

    @pytest.mark.unit
    def test_invalid_transition_raises(self, registry: SQLiteRunRegistry) -> None:
        """非法状态转换抛出 ValueError。"""
        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        registry.complete_run(run.run_id)
        # SUCCEEDED → RUNNING 非法
        with pytest.raises(ValueError, match="非法状态转换"):
            registry.start_run(run.run_id)

    @pytest.mark.unit
    def test_transition_nonexistent_raises(self, registry: SQLiteRunRegistry) -> None:
        """对不存在的 run 做转换抛 KeyError。"""
        with pytest.raises(KeyError, match="run 不存在"):
            registry.start_run("nonexistent")


class TestCancelRequest:
    """request_cancel / is_cancel_requested 测试。"""

    @pytest.mark.unit
    def test_request_cancel_active_run(self, registry: SQLiteRunRegistry) -> None:
        """取消活跃 run 返回 True。"""
        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        assert registry.request_cancel(run.run_id) is True

        updated = registry.get_run(run.run_id)
        assert updated is not None
        assert updated.state == RunState.RUNNING
        assert updated.completed_at is None
        assert updated.cancel_requested_at is not None
        assert updated.cancel_requested_reason == RunCancelReason.USER_CANCELLED
        assert updated.cancel_reason is None

    @pytest.mark.unit
    def test_request_cancel_active_run_with_timeout_reason(self, registry: SQLiteRunRegistry) -> None:
        """取消活跃 run 时可写入 timeout 原因。"""

        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        assert registry.request_cancel(run.run_id, cancel_reason=RunCancelReason.TIMEOUT) is True

        updated = registry.get_run(run.run_id)
        assert updated is not None
        assert updated.cancel_requested_reason == RunCancelReason.TIMEOUT
        assert updated.cancel_reason is None

    @pytest.mark.unit
    def test_request_cancel_terminal_run(self, registry: SQLiteRunRegistry) -> None:
        """取消已完成 run 返回 False。"""
        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        registry.complete_run(run.run_id)
        assert registry.request_cancel(run.run_id) is False

    @pytest.mark.unit
    def test_is_cancel_requested(self, registry: SQLiteRunRegistry) -> None:
        """查询取消状态。"""
        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        assert registry.is_cancel_requested(run.run_id) is False
        registry.request_cancel(run.run_id)
        assert registry.is_cancel_requested(run.run_id) is True

    @pytest.mark.unit
    def test_request_cancel_is_idempotent_and_preserves_first_reason(self, registry: SQLiteRunRegistry) -> None:
        """重复请求取消不应覆盖首次取消原因。"""

        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)

        assert registry.request_cancel(run.run_id, cancel_reason=RunCancelReason.TIMEOUT) is True
        assert registry.request_cancel(run.run_id, cancel_reason=RunCancelReason.USER_CANCELLED) is False

        updated = registry.get_run(run.run_id)
        assert updated is not None
        assert updated.cancel_requested_reason == RunCancelReason.TIMEOUT

    @pytest.mark.unit
    def test_is_cancel_requested_nonexistent(self, registry: SQLiteRunRegistry) -> None:
        """查询不存在的 run 返回 False。"""
        assert registry.is_cancel_requested("nonexistent") is False


class TestQueryAndList:
    """get_run / list_runs / list_active_runs 测试。"""

    @pytest.mark.unit
    def test_get_run_exists(self, registry: SQLiteRunRegistry) -> None:
        """查询存在的 run。"""
        run = registry.register_run(service_type="test")
        fetched = registry.get_run(run.run_id)
        assert fetched is not None
        assert fetched.run_id == run.run_id

    @pytest.mark.unit
    def test_get_run_not_exists(self, registry: SQLiteRunRegistry) -> None:
        """查询不存在的 run 返回 None。"""
        assert registry.get_run("nonexistent") is None

    @pytest.mark.unit
    def test_list_runs_all(self, registry: SQLiteRunRegistry) -> None:
        """列出所有 runs。"""
        registry.register_run(service_type="a")
        registry.register_run(service_type="b")
        assert len(registry.list_runs()) == 2

    @pytest.mark.unit
    def test_list_runs_filter_by_session(self, registry: SQLiteRunRegistry) -> None:
        """按 session_id 过滤。"""
        registry.register_run(session_id="s1", service_type="a")
        registry.register_run(session_id="s2", service_type="b")
        runs = registry.list_runs(session_id="s1")
        assert len(runs) == 1
        assert runs[0].session_id == "s1"

    @pytest.mark.unit
    def test_list_runs_filter_by_state(self, registry: SQLiteRunRegistry) -> None:
        """按状态过滤。"""
        run1 = registry.register_run(service_type="a")
        registry.register_run(service_type="b")
        registry.start_run(run1.run_id)

        running = registry.list_runs(state=RunState.RUNNING)
        assert len(running) == 1
        assert running[0].state == RunState.RUNNING

    @pytest.mark.unit
    def test_list_runs_filter_by_service_type(self, registry: SQLiteRunRegistry) -> None:
        """按 service_type 过滤。"""
        registry.register_run(service_type="chat_turn")
        registry.register_run(service_type="prompt")
        runs = registry.list_runs(service_type="prompt")
        assert len(runs) == 1

    @pytest.mark.unit
    def test_list_active_runs(self, registry: SQLiteRunRegistry) -> None:
        """list_active_runs 只返回活跃 run。"""
        r1 = registry.register_run(service_type="a")
        r2 = registry.register_run(service_type="b")
        registry.start_run(r1.run_id)
        registry.start_run(r2.run_id)
        registry.complete_run(r2.run_id)

        active = registry.list_active_runs()
        assert len(active) == 1
        assert active[0].run_id == r1.run_id

    @pytest.mark.unit
    def test_list_active_runs_for_owner_filters_by_pid(self, registry: SQLiteRunRegistry) -> None:
        """list_active_runs_for_owner 严格按 OwnerIdentity 过滤。"""

        import os as _os
        from dayu.process_liveness import OwnerIdentity, current_owner_identity

        r1 = registry.register_run(service_type="a")
        r2 = registry.register_run(service_type="b")
        registry.start_run(r1.run_id)
        registry.start_run(r2.run_id)

        # r2 改挂到另一个 PID
        conn = registry._host_store.get_connection()
        conn.execute("UPDATE runs SET owner_pid = ? WHERE run_id = ?", (42, r2.run_id))
        conn.commit()

        mine = registry.list_active_runs_for_owner(current_owner_identity())
        other = registry.list_active_runs_for_owner(
            OwnerIdentity(pid=42, process_start_time=None, boot_id=None)
        )

        mine_ids = {run.run_id for run in mine}
        other_ids = {run.run_id for run in other}

        assert r1.run_id in mine_ids
        assert r2.run_id not in mine_ids
        assert other_ids == {r2.run_id}
        # 当前进程身份完整三元组等值，r1 仍归我所有
        assert _os.getpid() == current_owner_identity().pid

    @pytest.mark.unit
    def test_list_active_runs_for_owner_rejects_pid_reuse(
        self, registry: SQLiteRunRegistry
    ) -> None:
        """同 PID 但 ``OwnerIdentity`` 三元组任一字段不一致时不得被识别为当前 owner。"""

        from dayu.process_liveness import OwnerIdentity, current_owner_identity

        r1 = registry.register_run(service_type="a")
        registry.start_run(r1.run_id)

        current = current_owner_identity()

        # 模拟 PID 复用：相同 PID，但 process_start_time / boot_id 都不同
        reused = OwnerIdentity(
            pid=current.pid,
            process_start_time=(
                None
                if current.process_start_time is None
                else current.process_start_time + 9999.0
            ),
            boot_id=(None if current.boot_id is None else current.boot_id + "-reused"),
        )

        # 至少一个字段两侧均非 None 时，应被识别为不同 owner
        if (
            current.process_start_time is not None
            or current.boot_id is not None
        ):
            assert registry.list_active_runs_for_owner(reused) == []
        else:
            # 两端三字段均为 NULL → 退化为仅 PID 匹配，与旧行为一致
            assert {run.run_id for run in registry.list_active_runs_for_owner(reused)} == {r1.run_id}


@pytest.mark.unit
def test_run_registry_emits_lifecycle_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RunRegistry 关键生命周期动作应输出日志。"""

    store = HostStore(tmp_path / "test.db")
    store.initialize_schema()
    registry = SQLiteRunRegistry(store)
    debug_mock = Mock()
    monkeypatch.setattr(Log, "debug", debug_mock)

    run = registry.register_run(service_type="chat_turn", session_id="s1", scene_name="wechat")
    registry.start_run(run.run_id)
    registry.request_cancel(run.run_id, cancel_reason=RunCancelReason.TIMEOUT)
    registry.mark_cancelled(run.run_id, cancel_reason=RunCancelReason.TIMEOUT)

    debug_messages = [call.args[0] for call in debug_mock.call_args_list]

    assert any("注册 run" in message and "owner_pid=" in message and "db_path=" in message for message in debug_messages)
    assert any(
        "run 状态迁移" in message and "to_state=running" in message and "db_path=" in message
        for message in debug_messages
    )
    assert any(
        "run 状态迁移" in message and "to_state=cancelled" in message and "db_path=" in message
        for message in debug_messages
    )
    assert any("登记 run 取消请求" in message for message in debug_messages)


class TestCleanupOrphanRuns:
    """cleanup_orphan_runs 测试。"""

    @pytest.mark.unit
    def test_cleanup_no_orphans(self, registry: SQLiteRunRegistry) -> None:
        """当前进程的 run 不会被清理。"""
        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)
        orphans = registry.cleanup_orphan_runs()
        assert orphans == []

    @pytest.mark.unit
    def test_cleanup_dead_pid_run(self, registry: SQLiteRunRegistry) -> None:
        """owner_pid 不存在的活跃 run 被标记 UNSETTLED（不再写 FAILED）。"""
        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)

        # 篡改 owner_pid 为一个不存在的 PID
        conn = registry._host_store.get_connection()
        conn.execute(
            "UPDATE runs SET owner_pid = ?, started_at = ?, created_at = ? WHERE run_id = ?",
            (
                999999,
                (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                run.run_id,
            ),
        )
        conn.commit()

        orphans = registry.cleanup_orphan_runs()
        assert run.run_id in orphans

        updated = registry.get_run(run.run_id)
        assert updated is not None
        assert updated.state == RunState.UNSETTLED
        assert "orphan" in (updated.error_summary or "")

    @pytest.mark.unit
    def test_cleanup_recent_dead_pid_run_is_deferred(self, registry: SQLiteRunRegistry) -> None:
        """启动恢复不会立即清理刚开始执行的 dead-pid run。"""

        run = registry.register_run(service_type="test")
        registry.start_run(run.run_id)

        conn = registry._host_store.get_connection()
        conn.execute(
            "UPDATE runs SET owner_pid = ? WHERE run_id = ?",
            (999999, run.run_id),
        )
        conn.commit()

        orphans = registry.cleanup_orphan_runs()
        updated = registry.get_run(run.run_id)

        assert orphans == []
        assert updated is not None
        assert updated.state == RunState.RUNNING

    @pytest.mark.unit
    def test_cleanup_orphan_run_keeps_pending_turn_truth_source(self, tmp_path: Path) -> None:
        """orphan 清理不能破坏 pending turn 作为恢复真源。"""

        host_store = HostStore(tmp_path / "test.db")
        host_store.initialize_schema()
        registry = SQLiteRunRegistry(host_store)
        pending_turn_store = SQLitePendingConversationTurnStore(host_store)
        run = registry.register_run(session_id="s1", service_type="chat_turn", scene_name="interactive")
        registry.start_run(run.run_id)
        pending_turn = pending_turn_store.upsert_pending_turn(
            session_id="s1",
            scene_name="interactive",
            user_text="未交付问题",
            source_run_id=run.run_id,
            resumable=True,
            state=PendingConversationTurnState.ACCEPTED_BY_HOST,
        )

        conn = host_store.get_connection()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn.execute(
            "UPDATE runs SET owner_pid = ?, started_at = ?, created_at = ? WHERE run_id = ?",
            (999999, old_time, old_time, run.run_id),
        )
        conn.commit()

        orphan_ids = registry.cleanup_orphan_runs()
        persisted = pending_turn_store.get_pending_turn(pending_turn.pending_turn_id)

        assert orphan_ids == [run.run_id]
        assert persisted is not None
        assert persisted.pending_turn_id == pending_turn.pending_turn_id
        assert persisted.source_run_id == run.run_id


class TestRegisterRunSessionBarrier:
    """``register_run`` 在 session 屏障下的拒绝测试（``#117`` 设计 §3.3）。"""

    @pytest.mark.unit
    def test_register_run_blocked_when_session_clearing(self, tmp_path: Path) -> None:
        """``CLEARING`` 期间 ``register_run`` 抛 ``SessionClearingError``。"""

        from dayu.host.protocols import SessionClearingError
        from dayu.host.session_registry import SQLiteSessionRegistry
        from dayu.contracts.session import SessionSource

        store = HostStore(tmp_path / "test.db")
        store.initialize_schema()
        session_registry = SQLiteSessionRegistry(store)
        run_registry = SQLiteRunRegistry(store, session_activity=session_registry)

        session = session_registry.create_session(SessionSource.CLI, session_id="s1")
        session_registry.begin_clearing(session.session_id)

        with pytest.raises(SessionClearingError):
            run_registry.register_run(session_id=session.session_id, service_type="chat_turn")

    @pytest.mark.unit
    def test_register_run_blocked_when_session_clearing_failed(self, tmp_path: Path) -> None:
        """``CLEARING_FAILED`` 持久锁定下 ``register_run`` 抛 ``SessionClearingFailedError``。"""

        from dayu.host.protocols import SessionClearingFailedError
        from dayu.host.session_registry import SQLiteSessionRegistry
        from dayu.contracts.session import SessionSource

        store = HostStore(tmp_path / "test.db")
        store.initialize_schema()
        session_registry = SQLiteSessionRegistry(store)
        run_registry = SQLiteRunRegistry(store, session_activity=session_registry)

        session = session_registry.create_session(SessionSource.CLI, session_id="s2")
        session_registry.begin_clearing(session.session_id)
        session_registry.mark_clearing_failed(session.session_id)

        with pytest.raises(SessionClearingFailedError):
            run_registry.register_run(session_id=session.session_id, service_type="chat_turn")

    @pytest.mark.unit
    def test_register_run_blocked_when_session_closed(self, tmp_path: Path) -> None:
        """``CLOSED`` 状态下 ``register_run`` 抛 ``SessionClosedError``。"""

        from dayu.host.protocols import SessionClosedError
        from dayu.host.session_registry import SQLiteSessionRegistry
        from dayu.contracts.session import SessionSource

        store = HostStore(tmp_path / "test.db")
        store.initialize_schema()
        session_registry = SQLiteSessionRegistry(store)
        run_registry = SQLiteRunRegistry(store, session_activity=session_registry)

        session = session_registry.create_session(SessionSource.CLI, session_id="s3")
        session_registry.close_session(session.session_id)

        with pytest.raises(SessionClosedError):
            run_registry.register_run(session_id=session.session_id, service_type="chat_turn")

    @pytest.mark.unit
    def test_register_run_passes_when_session_active(self, tmp_path: Path) -> None:
        """``ACTIVE`` 状态正常注册。"""

        from dayu.host.session_registry import SQLiteSessionRegistry
        from dayu.contracts.session import SessionSource

        store = HostStore(tmp_path / "test.db")
        store.initialize_schema()
        session_registry = SQLiteSessionRegistry(store)
        run_registry = SQLiteRunRegistry(store, session_activity=session_registry)

        session = session_registry.create_session(SessionSource.CLI, session_id="s4")
        run = run_registry.register_run(
            session_id=session.session_id, service_type="chat_turn"
        )
        assert run.session_id == session.session_id

    @pytest.mark.unit
    def test_register_run_no_barrier_when_session_id_none(self, tmp_path: Path) -> None:
        """``session_id`` 为 ``None`` 时跳过屏障校验（无 session 归属的 run 不受屏障约束）。"""

        from dayu.host.session_registry import SQLiteSessionRegistry

        store = HostStore(tmp_path / "test.db")
        store.initialize_schema()
        session_registry = SQLiteSessionRegistry(store)
        run_registry = SQLiteRunRegistry(store, session_activity=session_registry)

        run = run_registry.register_run(service_type="maintenance")
        assert run.session_id is None


def _reserved_run_id(seed: int) -> str:
    """构造确定性 reserved run ID（``run_`` + 32 位小写 hex）。

    Args:
        seed: 填充 hex 用的种子整数。

    Returns:
        合法 reserved run ID。
    """

    return f"run_{seed:032x}"


class TestEnsureReservedRun:
    """``ensure_reserved_run`` 的 reserved identity 契约测试。

    并发用例使用两个独立 SQLite 连接（thread-local）+ thread barrier，
    不使用 mock 模拟锁语义。
    """

    @pytest.mark.unit
    def test_ensure_reserved_run_creates_once(self, registry: SQLiteRunRegistry) -> None:
        """首次 ensure 返回 ``created=True`` 且 record 状态为 CREATED。"""

        run_id = _reserved_run_id(1)
        result = registry.ensure_reserved_run(
            reserved_run_id=run_id,
            session_id="sess-r1",
            service_type="durable_job",
            scene_name="job_scene",
            metadata={"delivery_channel": "cli"},
        )
        assert result.created is True
        assert result.record.run_id == run_id
        assert result.record.state == RunState.CREATED
        assert result.record.session_id == "sess-r1"
        assert result.record.service_type == "durable_job"
        assert result.record.scene_name == "job_scene"
        assert result.record.metadata == {"delivery_channel": "cli"}

    @pytest.mark.unit
    def test_ensure_reserved_run_returns_exact_existing_record(self, registry: SQLiteRunRegistry) -> None:
        """同身份重复 ensure 返回精确既有 record 且 ``created=False``。"""

        run_id = _reserved_run_id(2)
        first = registry.ensure_reserved_run(
            reserved_run_id=run_id,
            session_id="sess-r2",
            service_type="durable_job",
            scene_name="job_scene",
            metadata={"delivery_channel": "cli"},
        )
        second = registry.ensure_reserved_run(
            reserved_run_id=run_id,
            session_id="sess-r2",
            service_type="durable_job",
            scene_name="job_scene",
            metadata={"delivery_channel": "cli"},
        )
        assert first.created is True
        assert second.created is False
        assert second.record == first.record

    @pytest.mark.unit
    def test_ensure_reserved_run_rejects_invalid_32_hex_before_sqlite_write(self, registry: SQLiteRunRegistry) -> None:
        """非法 reserved ID 在写事务开启前抛 ValueError，零 SQLite side effect。"""

        conn = registry._host_store.get_connection()
        before = conn.execute("SELECT count(*) FROM runs").fetchone()[0]
        for invalid in (
            "run_1234",
            "run_" + "z" * 32,
            "run_" + "A" * 32,
            "run_" + "1" * 31,
            "run_" + "1" * 33,
            "RUN_" + "1" * 32,
            "xun_" + "1" * 32,
            "run_" + "1" * 31 + "g",
        ):
            with pytest.raises(ValueError, match="invalid_reserved_run_id"):
                registry.ensure_reserved_run(
                    reserved_run_id=invalid,
                    session_id=None,
                    service_type="durable_job",
                    scene_name=None,
                    metadata=None,
                )
        after = conn.execute("SELECT count(*) FROM runs").fetchone()[0]
        assert after == before

    @pytest.mark.unit
    def test_ensure_reserved_run_conflicting_identity_fails_closed(self, registry: SQLiteRunRegistry) -> None:
        """identity 任一字段不同抛 ``ReservedRunIdentityConflictError`` 并携带既有 record。"""

        from dayu.host.protocols import ReservedRunIdentityConflictError

        run_id = _reserved_run_id(3)
        registry.ensure_reserved_run(
            reserved_run_id=run_id,
            session_id="sess-r3",
            service_type="durable_job",
            scene_name="job_scene",
            metadata={"delivery_channel": "cli"},
        )
        with pytest.raises(ReservedRunIdentityConflictError) as excinfo:
            registry.ensure_reserved_run(
                reserved_run_id=run_id,
                session_id="sess-other",
                service_type="durable_job",
                scene_name="job_scene",
                metadata={"delivery_channel": "cli"},
            )
        assert excinfo.value.record.run_id == run_id
        assert excinfo.value.record.session_id == "sess-r3"
        assert excinfo.value.args == ("reserved_run_identity_conflict",)

        with pytest.raises(ReservedRunIdentityConflictError) as excinfo2:
            registry.ensure_reserved_run(
                reserved_run_id=run_id,
                session_id="sess-r3",
                service_type="different_service",
                scene_name="job_scene",
                metadata={"delivery_channel": "cli"},
            )
        assert excinfo2.value.args == ("reserved_run_identity_conflict",)

        with pytest.raises(ReservedRunIdentityConflictError) as excinfo3:
            registry.ensure_reserved_run(
                reserved_run_id=run_id,
                session_id="sess-r3",
                service_type="durable_job",
                scene_name="job_scene",
                metadata={"delivery_channel": "wechat"},
            )
        assert excinfo3.value.args == ("reserved_run_identity_conflict",)

    @pytest.mark.unit
    def test_ensure_reserved_run_normalizes_metadata_before_compare(self, registry: SQLiteRunRegistry) -> None:
        """metadata 先规范化再比较：非法键与空值被剥离，合法键保留后视为同一身份。"""

        from dayu.contracts.execution_metadata import normalize_execution_delivery_context

        run_id = _reserved_run_id(4)
        raw_metadata: dict[str, str] = {
            "delivery_channel": "cli",
            "unknown_key": "dropped",
            "delivery_target": "",
        }
        normalized = normalize_execution_delivery_context(raw_metadata)
        assert normalized == {"delivery_channel": "cli"}
        first = registry.ensure_reserved_run(
            reserved_run_id=run_id,
            session_id=None,
            service_type="durable_job",
            scene_name=None,
            metadata=normalized,
        )
        second_metadata: ExecutionDeliveryContext = {"delivery_channel": "cli"}
        second = registry.ensure_reserved_run(
            reserved_run_id=run_id,
            session_id=None,
            service_type="durable_job",
            scene_name=None,
            metadata=second_metadata,
        )
        assert first.created is True
        assert second.created is False
        assert second.record.metadata == {"delivery_channel": "cli"}

    @pytest.mark.unit
    def test_ensure_reserved_run_rejects_unknown_metadata_keys(self, registry: SQLiteRunRegistry) -> None:
        """未知 metadata 键在规范化时被剥离，不影响身份比较。"""

        from dayu.contracts.execution_metadata import normalize_execution_delivery_context

        run_id = _reserved_run_id(8)
        raw_metadata: dict[str, str] = {
            "delivery_channel": "cli",
            "unknown_key": "dropped",
            "delivery_target": "",
        }
        normalized = normalize_execution_delivery_context(raw_metadata)
        assert normalized == {"delivery_channel": "cli"}
        result = registry.ensure_reserved_run(
            reserved_run_id=run_id,
            session_id=None,
            service_type="durable_job",
            scene_name=None,
            metadata=normalized,
        )
        assert result.created is True
        assert result.record.metadata == {"delivery_channel": "cli"}

    @pytest.mark.unit
    def test_ensure_reserved_run_conflicting_normalized_metadata_fails_closed(
        self, registry: SQLiteRunRegistry
    ) -> None:
        """规范化后仍不同的 metadata（如 ``filtered`` 布尔差异）视为 identity 冲突。"""

        from dayu.host.protocols import ReservedRunIdentityConflictError

        run_id = _reserved_run_id(4)
        registry.ensure_reserved_run(
            reserved_run_id=run_id,
            session_id=None,
            service_type="durable_job",
            scene_name=None,
            metadata={"delivery_channel": "cli"},
        )
        with pytest.raises(ReservedRunIdentityConflictError):
            registry.ensure_reserved_run(
                reserved_run_id=run_id,
                session_id=None,
                service_type="durable_job",
                scene_name=None,
                metadata={"delivery_channel": "cli", "filtered": False},
            )

    @pytest.mark.unit
    def test_ensure_reserved_run_concurrent_same_identity_returns_one_created(
        self, tmp_path: Path
    ) -> None:
        """两个独立连接并发 ensure 同一身份时恰好一个 ``created=True``。"""

        import threading

        store = HostStore(tmp_path / "concurrent.db")
        store.initialize_schema()
        registry = SQLiteRunRegistry(store)
        run_id = _reserved_run_id(5)
        barrier = threading.Barrier(2)
        results: list[bool] = []
        errors: list[str] = []
        results_lock = threading.Lock()

        def worker() -> None:
            barrier.wait()
            try:
                result = registry.ensure_reserved_run(
                    reserved_run_id=run_id,
                    session_id=None,
                    service_type="durable_job",
                    scene_name=None,
                    metadata=None,
                )
            except Exception as exc:  # pragma: no cover - 记录失败便于断言
                with results_lock:
                    errors.append(f"error:{type(exc).__name__}")
                return
            with results_lock:
                results.append(result.created)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        assert sorted(results) == [False, True]

    @pytest.mark.unit
    def test_ensure_reserved_run_concurrent_conflicting_identity_fails_closed(
        self, tmp_path: Path
    ) -> None:
        """两个独立连接并发 ensure 冲突身份时一个成功、另一个抛 identity conflict。"""

        import threading

        from dayu.host.protocols import ReservedRunIdentityConflictError

        store = HostStore(tmp_path / "concurrent-conflict.db")
        store.initialize_schema()
        registry = SQLiteRunRegistry(store)
        run_id = _reserved_run_id(6)
        barrier = threading.Barrier(2)
        outcomes: list[str | bool] = []
        outcomes_lock = threading.Lock()

        def worker(session_id: str) -> None:
            barrier.wait()
            try:
                result = registry.ensure_reserved_run(
                    reserved_run_id=run_id,
                    session_id=session_id,
                    service_type="durable_job",
                    scene_name=None,
                    metadata=None,
                )
            except ReservedRunIdentityConflictError as exc:
                with outcomes_lock:
                    outcomes.append(exc.args[0])
                return
            with outcomes_lock:
                outcomes.append(result.created)

        threads = [
            threading.Thread(target=worker, args=("sess-a",)),
            threading.Thread(target=worker, args=("sess-b",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert True in outcomes
        assert "reserved_run_identity_conflict" in outcomes

    @pytest.mark.unit
    def test_random_and_reserved_run_id_formats_are_both_gettable_and_listable(
        self, registry: SQLiteRunRegistry
    ) -> None:
        """随机 12-hex 与 reserved 32-hex 两种 ID 均可 get/list，且不被长度区分对待。"""

        random_run = registry.register_run(service_type="chat_turn")
        reserved_run = registry.ensure_reserved_run(
            reserved_run_id=_reserved_run_id(7),
            session_id=None,
            service_type="durable_job",
            scene_name=None,
            metadata=None,
        ).record
        assert registry.get_run(random_run.run_id) is not None
        assert registry.get_run(reserved_run.run_id) is not None
        run_ids = {run.run_id for run in registry.list_runs()}
        assert {random_run.run_id, reserved_run.run_id} <= run_ids

    @pytest.mark.unit
    def test_random_register_run_path_bytes_and_behavior_are_unchanged(
        self, registry: SQLiteRunRegistry
    ) -> None:
        """随机 register_run 路径的 ID 形态、长度与状态行为逐字不变。"""

        run = registry.register_run(service_type="chat_turn")
        assert run.run_id.startswith("run_")
        assert len(run.run_id) == len("run_") + 12
        assert all(ch in "0123456789abcdef" for ch in run.run_id[4:])
        assert run.state == RunState.CREATED

