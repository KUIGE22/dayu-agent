"""``dayu-cli platform`` parser、lifecycle 与真实子进程信号测试。"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from dayu.cli.arg_parsing import parse_arguments
from dayu.cli.arguments import DayuCliArguments
from dayu.cli.commands import platform as platform_command
from dayu.cli.commands.platform import run_platform_command
from dayu.execution.options import ExecutionOptions
from dayu.host.process_intake import ProcessIntakeGate
from dayu.host.scheduler import SchedulerGatewayProtocol
from dayu.host.worker import WorkerJobGatewayProtocol
from dayu.investment.config import (
    PlatformDeploymentProfile,
    PlatformQueueAdmissionKind,
    PlatformQueueMode,
    PlatformQueueSettings,
    PlatformSettingsError,
)
from dayu.investment.domain.identifiers import TenantScope
from dayu.investment.domain.jobs import (
    JobAttemptReceipt,
    JobCancellationSignalProtocol,
    JobClaim,
    JobCompletion,
    JobFailure,
    JobLeaseHandle,
    JobRecoveryResult,
)
from dayu.investment.domain.schedules import ScheduleMaterializationResult
from tests.application.test_platform_scheduler import (
    _occurrence,
    _page,
    _RecordingSchedulerGateway,
    _unavailable_result,
)
from tests.application.test_platform_scheduler import (
    _scope as _scheduler_scope,
)
from tests.application.test_platform_scheduler import (
    _settings as _scheduler_settings,
)
from tests.application.test_platform_worker import (
    WORKER_ID,
    _claim,
    _document,
    _FakeGateway,
)
from tests.application.test_platform_worker import (
    _settings as _worker_settings,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
_TENANT_ID = "11111111-1111-4111-8111-111111111111"
_SUBPROCESS_TIMEOUT_SECONDS = 10.0
_READY_POLL_SECONDS = 0.01
_SECOND_SIGNAL_DELAY_SECONDS = 0.15
_WORKER_ENTRY_SCRIPT = (
    "from tests.cli.test_platform_command import "
    "_run_worker_subprocess_entry; "
    "raise SystemExit(_run_worker_subprocess_entry())"
)
_SCHEDULER_ENTRY_SCRIPT = (
    "from tests.cli.test_platform_command import "
    "_run_scheduler_subprocess_entry; "
    "raise SystemExit(_run_scheduler_subprocess_entry())"
)


class _PostgresOnlyAdmission:
    """subprocess harness 使用的 closed POSTGRES_ONLY admission。"""

    kind = PlatformQueueAdmissionKind.POSTGRES_ONLY
    subscriber_factory = None
    redis_client = None


class _UnitAdmission:
    """parent-process unit tests 使用的可编程 admission。"""

    def __init__(self, kind: PlatformQueueAdmissionKind) -> None:
        """保存 admission kind 与空 Redis refs。

        Args:
            kind: 待覆盖的 closed admission kind。

        Returns:
            无。

        Raises:
            无。
        """

        self.kind = kind
        self.subscriber_factory = None
        self.redis_client = None


class _UnitPreparedRuntime:
    """不写文件的 parent-process prepared runtime double。"""

    def __init__(
        self,
        *,
        kind: PlatformQueueAdmissionKind = PlatformQueueAdmissionKind.POSTGRES_ONLY,
        close_fails: bool = False,
    ) -> None:
        """构造 direct gateway refs 与匹配 queue settings。

        Args:
            kind: POSTGRES_ONLY/REDIS/NOT_REQUIRED 测试 kind。
            close_fails: ``close`` 是否注入程序错误。

        Returns:
            无。

        Raises:
            无。
        """

        self.job_service: WorkerJobGatewayProtocol = _FakeGateway(gate=ProcessIntakeGate())
        self.schedule_service: SchedulerGatewayProtocol = _RecordingSchedulerGateway()
        self.queue_admission = _UnitAdmission(kind)
        mode = (
            PlatformQueueMode.EVENT_ASSISTED
            if kind is PlatformQueueAdmissionKind.REDIS
            else PlatformQueueMode.POSTGRES_POLLING
        )
        self.queue_settings = PlatformQueueSettings(mode=mode)
        self.close_calls = 0
        self._close_fails = close_fails

    def close(self) -> None:
        """记录 close，并按配置注入安全收口分支。

        Args:
            无。

        Returns:
            无。

        Raises:
            RuntimeError: ``close_fails`` 启用时抛出。
        """

        self.close_calls += 1
        if self._close_fails:
            raise RuntimeError("close-secret-detail")


class _UnitPlatformProcess:
    """parent-process signal/run 收口使用的最小 process double。"""

    def __init__(self, *, exit_code: int = 0, run_fails: bool = False) -> None:
        """初始化 stop/run 计数与结果。

        Args:
            exit_code: ``run`` 正常返回值。
            run_fails: 是否注入未分类 runtime exception。

        Returns:
            无。

        Raises:
            无。
        """

        self.exit_code = exit_code
        self.run_fails = run_fails
        self.stop_calls = 0
        self.run_calls = 0

    def request_stop(self) -> None:
        """记录 soft-stop 请求。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.stop_calls += 1

    async def run(self) -> int:
        """返回 closed code 或注入 runtime exception。

        Args:
            无。

        Returns:
            配置的 exit code。

        Raises:
            RuntimeError: ``run_fails`` 启用时抛出。
        """

        self.run_calls += 1
        if self.run_fails:
            raise RuntimeError("runtime-secret-detail")
        return self.exit_code


def _event_path() -> Path:
    """读取当前 subprocess 唯一事件文件路径。

    Args:
        无。

    Returns:
        父进程预先分配的事件文件路径。

    Raises:
        KeyError: harness 未注入 ``DAYU_TEST_PLATFORM_EVENT_PATH`` 时抛出。
    """

    return Path(os.environ["DAYU_TEST_PLATFORM_EVENT_PATH"])


def _ready_path() -> Path:
    """读取当前 subprocess 唯一 ready 文件路径。

    Args:
        无。

    Returns:
        父进程预先分配的 ready 文件路径。

    Raises:
        KeyError: harness 未注入 ``DAYU_TEST_PLATFORM_READY_PATH`` 时抛出。
    """

    return Path(os.environ["DAYU_TEST_PLATFORM_READY_PATH"])


def _result_path() -> Path:
    """读取当前 subprocess 唯一结果文件路径。

    Args:
        无。

    Returns:
        父进程预先分配的结果文件路径。

    Raises:
        KeyError: harness 未注入 ``DAYU_TEST_PLATFORM_RESULT_PATH`` 时抛出。
    """

    return Path(os.environ["DAYU_TEST_PLATFORM_RESULT_PATH"])


def _append_event(event: str) -> None:
    """立即追加一条不含业务数据的 subprocess lifecycle 事件。

    Args:
        event: allowlist 测试事件名。

    Returns:
        无。

    Raises:
        OSError: 事件文件无法写入时抛出。
    """

    with _event_path().open("a", encoding="utf-8") as stream:
        stream.write(f"{event}\n")
        stream.flush()


def _mark_ready() -> None:
    """原子性要求不高地写入 subprocess 信号就绪标记。

    Args:
        无。

    Returns:
        无。

    Raises:
        OSError: ready 文件无法写入时抛出。
    """

    _ready_path().write_text("ready\n", encoding="utf-8")


class _SubprocessWorkerGateway(_FakeGateway):
    """在真实 subprocess 内驱动 cooperative/noncooperative handler。"""

    def __init__(self, *, cooperative: bool) -> None:
        """准备唯一 claim 与 handler 模式。

        Args:
            cooperative: 首信号后是否在 grace 内自然完成 handler。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(gate=ProcessIntakeGate())
        self.claim_results.append(_claim())
        self._cooperative = cooperative

    async def execute_claim(
        self,
        scope: TenantScope,
        claim: JobClaim,
        cancellation: JobCancellationSignalProtocol,
    ) -> JobCompletion | JobFailure:
        """启动真实 Worker handler task，并按 case 收敛或保持非协作。

        Args:
            scope: Worker 的 tenant scope。
            claim: 当前真实 ``JobClaim``。
            cancellation: Worker-owned cooperative cancellation signal。

        Returns:
            cooperative case 返回安全 completion。

        Raises:
            asyncio.CancelledError: cooperative task 被外层取消时传播；
                noncooperative case 则继续等待第二个 OS signal。
        """

        self.execute_calls.append((scope, claim, cancellation))
        cancellation.is_cancel_requested()
        _append_event("handler_started")
        _mark_ready()
        if self._cooperative:
            await asyncio.sleep(0.3)
            return JobCompletion(_document())
        while True:
            try:
                await asyncio.sleep(60.0)
            except asyncio.CancelledError:
                continue

    def complete(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        completion: JobCompletion,
    ) -> JobAttemptReceipt:
        """在真实 terminal 调用前记录 allowlist 事件。

        Args:
            scope: Worker tenant scope。
            lease: 当前 attempt lease。
            completion: handler completion。

        Returns:
            fake Service 的 closed receipt。

        Raises:
            无。
        """

        _append_event("complete")
        return super().complete(scope, lease, completion)

    def fail(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        failure: JobFailure,
    ) -> JobRecoveryResult:
        """在真实 failure 调用前记录 allowlist 事件。

        Args:
            scope: Worker tenant scope。
            lease: 当前 attempt lease。
            failure: handler failure。

        Returns:
            fake Service 的 closed recovery result。

        Raises:
            无。
        """

        _append_event("fail")
        return super().fail(scope, lease, failure)


class _SubprocessSchedulerGateway(_RecordingSchedulerGateway):
    """在真实 subprocess 内阻塞当前 materialization 的 Scheduler gateway。"""

    def materialize_occurrence(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
    ) -> ScheduleMaterializationResult:
        """让首信号落在已派发 materialization 内并随后完整收口。

        Args:
            scope: Scheduler tenant scope。
            occurrence_id: 当前 occurrence UUID。

        Returns:
            父 fake 提供的 closed unavailable result。

        Raises:
            ScheduleInvariantError: 父 fake 缺少结果时抛出。
        """

        _append_event("materialize_started")
        _mark_ready()
        time.sleep(0.3)
        result = super().materialize_occurrence(scope, occurrence_id)
        _append_event("materialize_finished")
        return result


class _SubprocessWorkerPreparedRuntime:
    """真实 Worker subprocess 的最小 prepared runtime double。"""

    def __init__(self, *, cooperative: bool) -> None:
        """构造 real Host Worker 所需的 direct refs。

        Args:
            cooperative: handler 是否在 soft grace 内自然完成。

        Returns:
            无。

        Raises:
            无。
        """

        self.job_service: WorkerJobGatewayProtocol = _SubprocessWorkerGateway(cooperative=cooperative)
        self.schedule_service: SchedulerGatewayProtocol = _RecordingSchedulerGateway()
        self.queue_admission = _PostgresOnlyAdmission()
        self.queue_settings = _worker_settings(shutdown_grace_seconds=2.0)
        self._close_calls = 0

    def close(self) -> None:
        """记录 CLI 对 prepared runtime 的 exact-once close。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 事件文件无法写入时抛出。
        """

        self._close_calls += 1
        _append_event("close")
        _result_path().write_text(
            json.dumps({"close_calls": self._close_calls}),
            encoding="utf-8",
        )


class _SubprocessSchedulerPreparedRuntime:
    """真实 Scheduler subprocess 的最小 prepared runtime double。"""

    def __init__(self) -> None:
        """构造一个含当前 durable occurrence 的 gateway。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        occurrence = _occurrence()
        self.job_service: WorkerJobGatewayProtocol = _FakeGateway(gate=ProcessIntakeGate())
        self.schedule_service: SchedulerGatewayProtocol = _SubprocessSchedulerGateway(
            replay_pages=(_page(occurrence),),
            materialization_results=(_unavailable_result(occurrence),),
        )
        self.queue_admission = _PostgresOnlyAdmission()
        self.queue_settings = _scheduler_settings(poll_seconds=60.0)
        self._close_calls = 0

    def close(self) -> None:
        """持久化 scheduler 调用计数并记录 exact-once close。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 结果文件无法写入时抛出。
        """

        self._close_calls += 1
        _append_event("close")
        gateway = self.schedule_service
        if not isinstance(gateway, _SubprocessSchedulerGateway):
            raise TypeError("scheduler subprocess gateway identity 漂移")
        _result_path().write_text(
            json.dumps(
                {
                    "close_calls": self._close_calls,
                    "replay_calls": len(gateway.replay_calls),
                    "due_calls": len(gateway.due_calls),
                    "materialize_calls": len(gateway.materialize_calls),
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )


def _prepare_worker_subprocess_runtime(
    *,
    workspace_root: Path,
    config_root: Path | None,
    execution_options: ExecutionOptions | None,
    runtime_label: str,
    log_module: str,
) -> _SubprocessWorkerPreparedRuntime:
    """替代外部 infra admission，只保留真实 CLI + Host loop。

    Args:
        workspace_root: CLI 传入 workspace。
        config_root: CLI 传入可空 config。
        execution_options: CLI 固定传入 ``None``。
        runtime_label: 最终 Worker process id。
        log_module: platform 安全日志模块。

    Returns:
        subprocess 专属 prepared runtime。

    Raises:
        KeyError: harness 未设置 handler 模式时抛出。
    """

    del workspace_root, config_root, execution_options, log_module
    if runtime_label != WORKER_ID:
        raise ValueError("worker runtime label 漂移")
    cooperative = os.environ["DAYU_TEST_PLATFORM_HANDLER_MODE"] == "cooperative"
    return _SubprocessWorkerPreparedRuntime(cooperative=cooperative)


def _prepare_scheduler_subprocess_runtime(
    *,
    workspace_root: Path,
    config_root: Path | None,
    execution_options: ExecutionOptions | None,
    runtime_label: str,
    log_module: str,
) -> _SubprocessSchedulerPreparedRuntime:
    """替代外部 infra admission，只保留真实 CLI + Scheduler loop。

    Args:
        workspace_root: CLI 传入 workspace。
        config_root: CLI 传入可空 config。
        execution_options: CLI 固定传入 ``None``。
        runtime_label: 最终 Scheduler process id。
        log_module: platform 安全日志模块。

    Returns:
        subprocess 专属 scheduler prepared runtime。

    Raises:
        ValueError: runtime label 漂移时抛出。
    """

    del workspace_root, config_root, execution_options, log_module
    if runtime_label != "scheduler-test":
        raise ValueError("scheduler runtime label 漂移")
    return _SubprocessSchedulerPreparedRuntime()


def _platform_arguments(action: str) -> DayuCliArguments:
    """构造 subprocess 直接进入 command runner 的完整 argparse namespace。

    Args:
        action: ``worker`` 或 ``scheduler``。

    Returns:
        带全部 platform/global 字段的 ``DayuCliArguments``。

    Raises:
        无。
    """

    return DayuCliArguments(
        command="platform",
        platform_action=action,
        tenant_id=(str(_scheduler_scope().tenant_id) if action == "scheduler" else _TENANT_ID),
        worker_id=WORKER_ID if action == "worker" else None,
        scheduler_id="scheduler-test" if action == "scheduler" else None,
        base="./workspace",
        config=None,
        log_level="error",
        debug=False,
        verbose=False,
        info=False,
        quiet=False,
    )


def _run_worker_subprocess_entry() -> int:
    """在子进程内运行真实 CLI Worker lifecycle。

    Args:
        无。

    Returns:
        ``run_platform_command`` 的 closed exit code。

    Raises:
        BaseException: command runner 未收口的终止原样传播。
    """

    with patch(
        "dayu.cli.commands.platform.prepare_platform_queue_runtime_dependencies",
        side_effect=_prepare_worker_subprocess_runtime,
    ):
        return run_platform_command(_platform_arguments("worker"))


def _run_scheduler_subprocess_entry() -> int:
    """在子进程内运行真实 CLI Scheduler lifecycle。

    Args:
        无。

    Returns:
        ``run_platform_command`` 的 closed exit code。

    Raises:
        BaseException: command runner 未收口的终止原样传播。
    """

    with patch(
        "dayu.cli.commands.platform.prepare_platform_queue_runtime_dependencies",
        side_effect=_prepare_scheduler_subprocess_runtime,
    ):
        return run_platform_command(_platform_arguments("scheduler"))


def _start_signal_subprocess(
    *,
    script: str,
    tmp_path: Path,
    handler_mode: str,
) -> tuple[subprocess.Popen[str], Path, Path, Path]:
    """启动一个 owned、可观测的真实 Python subprocess。

    Args:
        script: 固定 child entry script。
        tmp_path: pytest-owned 临时目录。
        handler_mode: cooperative/noncooperative harness mode。

    Returns:
        child process 与 ready/event/result 三条路径。

    Raises:
        OSError: 子进程无法创建时抛出。
    """

    ready_path = tmp_path / "ready"
    event_path = tmp_path / "events.log"
    result_path = tmp_path / "result.json"
    environment = os.environ.copy()
    environment.update(
        {
            "DAYU_TEST_PLATFORM_READY_PATH": str(ready_path),
            "DAYU_TEST_PLATFORM_EVENT_PATH": str(event_path),
            "DAYU_TEST_PLATFORM_RESULT_PATH": str(result_path),
            "DAYU_TEST_PLATFORM_HANDLER_MODE": handler_mode,
            "PYTHONUNBUFFERED": "1",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=_REPOSITORY_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return process, ready_path, event_path, result_path


def _wait_until_ready(process: subprocess.Popen[str], ready_path: Path) -> None:
    """bounded 等待 child 到达真实 handler/materialization barrier。

    Args:
        process: owned child process。
        ready_path: child barrier 文件。

    Returns:
        无。

    Raises:
        AssertionError: child 提前退出或 timeout 时抛出。
    """

    deadline = time.monotonic() + _SUBPROCESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if ready_path.exists():
            return
        return_code = process.poll()
        if return_code is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(f"subprocess 在 ready 前退出: {return_code}; {stdout!r}; {stderr!r}")
        time.sleep(_READY_POLL_SECONDS)
    raise AssertionError("subprocess ready barrier timeout")


def _finish_owned_process(
    process: subprocess.Popen[str],
) -> tuple[int, str, str]:
    """bounded 收集 child，并在超时后只终止当前 owned process。

    Args:
        process: 当前测试创建的 owned child。

    Returns:
        ``(returncode, stdout, stderr)``。

    Raises:
        AssertionError: child 未在 timeout 内退出时抛出。
    """

    try:
        stdout, stderr = process.communicate(timeout=_SUBPROCESS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.communicate()
        raise AssertionError("owned subprocess 未在 bounded timeout 内退出") from exc
    return process.returncode, stdout, stderr


def _cleanup_owned_process(process: subprocess.Popen[str]) -> None:
    """失败路径只清理本测试创建且仍存活的 child。

    Args:
        process: owned child process。

    Returns:
        无。

    Raises:
        subprocess.TimeoutExpired: kill 后 child 仍不退出时抛出。
    """

    if process.poll() is None:
        process.kill()
        process.wait(timeout=_SUBPROCESS_TIMEOUT_SECONDS)


@pytest.mark.unit
def test_platform_cli_requires_action_and_canonical_tenant_without_echoing_secret_env_values(
    tmp_path: Path,
) -> None:
    """action/tenant 在 startup 前 fail，且 stderr 不泄漏环境 secret 值。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        subprocess.TimeoutExpired: parser subprocess 超时由 harness 抛出。
    """

    secret_value = "sk-platform-parser-secret-canary"
    environment = os.environ.copy()
    environment.update(
        {
            "DAYU_PLATFORM_REDIS_URL": secret_value,
            "DAYU_PLATFORM_POSTGRES_DSN": secret_value,
            "DAYU_PLATFORM_AUTH_KEY": secret_value,
        }
    )
    cases = (
        [sys.executable, "-m", "dayu.cli", "platform"],
        [
            sys.executable,
            "-m",
            "dayu.cli",
            "platform",
            "worker",
            "--tenant-id",
            "11111111-1111-4111-8111-11111111111A",
            "--base",
            str(tmp_path),
        ],
    )
    for command in cases:
        completed = subprocess.run(
            command,
            cwd=_REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
        combined_output = completed.stdout + completed.stderr
        assert completed.returncode == 2
        assert secret_value not in combined_output


@pytest.mark.unit
def test_platform_parser_exposes_only_typed_worker_and_scheduler_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """parser 仅接受两个 action，并填充 action-specific typed id 字段。

    Args:
        monkeypatch: pytest argv patch 工具。

    Returns:
        无。

    Raises:
        无。
    """

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dayu-cli",
            "platform",
            "worker",
            "--tenant-id",
            _TENANT_ID,
            "--worker-id",
            WORKER_ID,
        ],
    )
    worker_args = parse_arguments()
    assert worker_args.command == "platform"
    assert worker_args.platform_action == "worker"
    assert worker_args.tenant_id == _TENANT_ID
    assert worker_args.worker_id == WORKER_ID
    assert worker_args.scheduler_id is None

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dayu-cli",
            "platform",
            "scheduler",
            "--tenant-id",
            _TENANT_ID,
            "--scheduler-id",
            "scheduler-test",
        ],
    )
    scheduler_args = parse_arguments()
    assert scheduler_args.platform_action == "scheduler"
    assert scheduler_args.scheduler_id == "scheduler-test"
    assert scheduler_args.worker_id is None


@pytest.mark.unit
def test_platform_admission_failure_returns_safe_exit_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """pre-loop 未分类 admission 错误固定为 exit 2 且不回显异常正文。

    Args:
        capsys: pytest 标准流捕获器。

    Returns:
        无。

    Raises:
        无。
    """

    secret_value = "postgresql://secret-value"
    with patch(
        "dayu.cli.commands.platform.prepare_platform_queue_runtime_dependencies",
        side_effect=RuntimeError(secret_value),
    ):
        exit_code = run_platform_command(_platform_arguments("worker"))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert secret_value not in captured.out
    assert secret_value not in captured.err
    assert "platform 配置或启动准入失败" in captured.err


@pytest.mark.unit
@pytest.mark.parametrize(
    ("action", "expected_process_type"),
    (("worker", "worker"), ("scheduler", "scheduler")),
)
def test_platform_command_builds_typed_process_runs_and_closes_once(
    action: str,
    expected_process_type: str,
) -> None:
    """两个 action 都只用 prepared direct refs，并在正常返回后 close 一次。

    Args:
        action: worker/scheduler action。
        expected_process_type: 预期被调用的 concrete Host constructor。

    Returns:
        无。

    Raises:
        无。
    """

    prepared = _UnitPreparedRuntime()
    process = _UnitPlatformProcess(exit_code=0)
    worker_constructor = patch(
        "dayu.cli.commands.platform.PlatformWorker",
        return_value=process,
    )
    scheduler_constructor = patch(
        "dayu.cli.commands.platform.PlatformScheduler",
        return_value=process,
    )
    with (
        patch(
            "dayu.cli.commands.platform.prepare_platform_queue_runtime_dependencies",
            return_value=prepared,
        ) as prepare,
        worker_constructor as worker,
        scheduler_constructor as scheduler,
    ):
        exit_code = run_platform_command(_platform_arguments(action))

    assert exit_code == 0
    assert process.run_calls == 1
    assert prepared.close_calls == 1
    prepare.assert_called_once()
    if expected_process_type == "worker":
        worker.assert_called_once()
        scheduler.assert_not_called()
    else:
        scheduler.assert_called_once()
        worker.assert_not_called()


@pytest.mark.unit
def test_platform_command_generates_safe_worker_identity_and_passes_config_path(
    tmp_path: Path,
) -> None:
    """缺省 Worker id 生成 12hex 标签，并把最终值传入唯一 startup wrapper。

    Args:
        tmp_path: config path 输入。

    Returns:
        无。

    Raises:
        无。
    """

    prepared = _UnitPreparedRuntime()
    process = _UnitPlatformProcess()
    args = _platform_arguments("worker")
    args.worker_id = None
    args.base = str(tmp_path / "workspace")
    args.config = str(tmp_path / "config")
    with (
        patch(
            "dayu.cli.commands.platform.prepare_platform_queue_runtime_dependencies",
            return_value=prepared,
        ) as prepare,
        patch("dayu.cli.commands.platform.PlatformWorker", return_value=process),
    ):
        assert run_platform_command(args) == 0

    call = prepare.call_args
    runtime_label = call.kwargs["runtime_label"]
    assert isinstance(runtime_label, str)
    assert runtime_label.startswith("worker_")
    assert len(runtime_label) == len("worker_") + 12
    assert call.kwargs["workspace_root"] == (tmp_path / "workspace").resolve()
    assert call.kwargs["config_root"] == (tmp_path / "config").resolve()


@pytest.mark.unit
def test_platform_cli_does_not_resolve_paths_before_queue_admission() -> None:
    """CLI 只传递 ``Path``；Redis-first startup 前不得自行解析文件系统路径。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    args = _platform_arguments("worker")
    args.base = "relative-workspace"
    args.config = "relative-config"
    with (
        patch(
            "pathlib.Path.resolve",
            side_effect=AssertionError("CLI path resolution happened before admission"),
        ),
        patch(
            "dayu.cli.commands.platform.prepare_platform_queue_runtime_dependencies",
            side_effect=RuntimeError("stop-after-admission-call"),
        ) as prepare,
    ):
        assert run_platform_command(args) == 2

    prepare.assert_called_once()
    assert prepare.call_args.kwargs["workspace_root"] == Path("relative-workspace")
    assert prepare.call_args.kwargs["config_root"] == Path("relative-config")


@pytest.mark.unit
def test_platform_command_runtime_or_close_failure_returns_safe_exit_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """loop 与 close 程序错误都固定 exit1，且不输出异常正文。

    Args:
        capsys: pytest 标准流捕获器。

    Returns:
        无。

    Raises:
        无。
    """

    runtime_prepared = _UnitPreparedRuntime()
    with (
        patch(
            "dayu.cli.commands.platform.prepare_platform_queue_runtime_dependencies",
            return_value=runtime_prepared,
        ),
        patch(
            "dayu.cli.commands.platform.PlatformWorker",
            return_value=_UnitPlatformProcess(run_fails=True),
        ),
    ):
        assert run_platform_command(_platform_arguments("worker")) == 1

    close_prepared = _UnitPreparedRuntime(close_fails=True)
    with (
        patch(
            "dayu.cli.commands.platform.prepare_platform_queue_runtime_dependencies",
            return_value=close_prepared,
        ),
        patch(
            "dayu.cli.commands.platform.PlatformWorker",
            return_value=_UnitPlatformProcess(),
        ),
    ):
        assert run_platform_command(_platform_arguments("worker")) == 1

    captured = capsys.readouterr()
    assert "runtime-secret-detail" not in captured.err
    assert "close-secret-detail" not in captured.err
    assert runtime_prepared.close_calls == 1
    assert close_prepared.close_calls == 1


@pytest.mark.unit
def test_platform_command_preloop_contract_failure_closes_prepared_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """snapshot/constructor fail 在 loop 前固定 exit2 并 close prepared 一次。

    Args:
        capsys: pytest 标准流捕获器。

    Returns:
        无。

    Raises:
        无。
    """

    prepared = _UnitPreparedRuntime()
    with (
        patch(
            "dayu.cli.commands.platform.prepare_platform_queue_runtime_dependencies",
            return_value=prepared,
        ),
        patch(
            "dayu.cli.commands.platform.PlatformWorker",
            side_effect=TypeError("constructor-secret-detail"),
        ),
    ):
        assert run_platform_command(_platform_arguments("worker")) == 2

    assert prepared.close_calls == 1
    assert "constructor-secret-detail" not in capsys.readouterr().err


@pytest.mark.unit
def test_platform_command_rejects_incomplete_or_cross_action_namespace_before_startup(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """缺字段、非 canonical tenant 与跨 action id 均在 startup 前拒绝。

    Args:
        capsys: pytest 标准流捕获器。

    Returns:
        无。

    Raises:
        无。
    """

    incomplete = DayuCliArguments()
    invalid_tenant = _platform_arguments("worker")
    invalid_tenant.tenant_id = "not-a-tenant"
    cross_action = _platform_arguments("worker")
    cross_action.scheduler_id = "scheduler-test"
    with patch("dayu.cli.commands.platform.prepare_platform_queue_runtime_dependencies") as prepare:
        assert run_platform_command(incomplete) == 2
        assert run_platform_command(invalid_tenant) == 2
        assert run_platform_command(cross_action) == 2
        prepare.assert_not_called()

    assert "not-a-tenant" not in capsys.readouterr().err


@pytest.mark.unit
def test_platform_signal_manager_soft_then_hard_stop_is_exact() -> None:
    """首回调只 request_stop，第二回调只调用 ``os._exit(1)``。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    process = _UnitPlatformProcess()
    manager = platform_command._PlatformSignalManager(process)
    with patch("dayu.cli.commands.platform.os._exit") as hard_exit:
        manager._handle_signal_in_loop()
        manager._handle_signal_in_loop()

    assert process.stop_calls == 1
    hard_exit.assert_called_once_with(1)


@pytest.mark.unit
def test_platform_admission_profile_mapping_is_closed() -> None:
    """snapshot profile 只接受 REDIS/POSTGRES_ONLY 两种 durable admission。

    Args:
        无。

    Returns:
        无。

    Raises:
        PlatformSettingsError: NOT_REQUIRED case 由断言捕获。
    """

    assert (
        platform_command._profile_from_admission(PlatformQueueAdmissionKind.REDIS)
        is PlatformDeploymentProfile.PRODUCTION
    )
    assert (
        platform_command._profile_from_admission(PlatformQueueAdmissionKind.POSTGRES_ONLY)
        is PlatformDeploymentProfile.INTEGRATION
    )
    with pytest.raises(PlatformSettingsError):
        platform_command._profile_from_admission(PlatformQueueAdmissionKind.NOT_REQUIRED)


@pytest.mark.unit
@pytest.mark.skipif(sys.platform == "win32", reason="Windows SIGTERM 不提供 POSIX soft signal")
def test_platform_worker_subprocess_sigterm_drains_and_closes_exactly_once(
    tmp_path: Path,
) -> None:
    """真实 Worker subprocess 首个 SIGTERM 完成当前 handler 并只 close 一次。

    Args:
        tmp_path: pytest-owned subprocess 文件目录。

    Returns:
        无。

    Raises:
        AssertionError: child timeout 或 lifecycle 事件不闭合时抛出。
    """

    process, ready_path, event_path, result_path = _start_signal_subprocess(
        script=_WORKER_ENTRY_SCRIPT,
        tmp_path=tmp_path,
        handler_mode="cooperative",
    )
    try:
        _wait_until_ready(process, ready_path)
        process.send_signal(signal.SIGTERM)
        return_code, _stdout, stderr = _finish_owned_process(process)
        assert return_code == 0, stderr
        assert event_path.read_text(encoding="utf-8").splitlines() == [
            "handler_started",
            "complete",
            "close",
        ]
        assert json.loads(result_path.read_text(encoding="utf-8")) == {"close_calls": 1}
    finally:
        _cleanup_owned_process(process)


@pytest.mark.unit
@pytest.mark.skipif(sys.platform == "win32", reason="Windows SIGTERM 不提供 POSIX soft signal")
def test_platform_worker_subprocess_second_sigterm_leaves_no_false_terminal(
    tmp_path: Path,
) -> None:
    """真实非协作 Worker 第二 SIGTERM 直接 exit1，不 terminal/close。

    Args:
        tmp_path: pytest-owned subprocess 文件目录。

    Returns:
        无。

    Raises:
        AssertionError: child timeout 或 hard-stop 事件不闭合时抛出。
    """

    process, ready_path, event_path, result_path = _start_signal_subprocess(
        script=_WORKER_ENTRY_SCRIPT,
        tmp_path=tmp_path,
        handler_mode="noncooperative",
    )
    try:
        _wait_until_ready(process, ready_path)
        process.send_signal(signal.SIGTERM)
        time.sleep(_SECOND_SIGNAL_DELAY_SECONDS)
        process.send_signal(signal.SIGTERM)
        return_code, _stdout, stderr = _finish_owned_process(process)
        assert return_code == 1, stderr
        assert event_path.read_text(encoding="utf-8").splitlines() == ["handler_started"]
        assert not result_path.exists()
    finally:
        _cleanup_owned_process(process)


@pytest.mark.unit
@pytest.mark.skipif(sys.platform == "win32", reason="Windows SIGTERM 不提供 POSIX soft signal")
def test_platform_scheduler_subprocess_sigterm_finishes_current_occurrence_without_starting_another_tick(
    tmp_path: Path,
) -> None:
    """真实 Scheduler 首信号让当前 materialization 收口且不开始新 tick。

    Args:
        tmp_path: pytest-owned subprocess 文件目录。

    Returns:
        无。

    Raises:
        AssertionError: child timeout 或 cursor/tick 计数不闭合时抛出。
    """

    process, ready_path, event_path, result_path = _start_signal_subprocess(
        script=_SCHEDULER_ENTRY_SCRIPT,
        tmp_path=tmp_path,
        handler_mode="cooperative",
    )
    try:
        _wait_until_ready(process, ready_path)
        process.send_signal(signal.SIGTERM)
        return_code, _stdout, stderr = _finish_owned_process(process)
        assert return_code == 0, stderr
        assert event_path.read_text(encoding="utf-8").splitlines() == [
            "materialize_started",
            "materialize_finished",
            "close",
        ]
        assert json.loads(result_path.read_text(encoding="utf-8")) == {
            "close_calls": 1,
            "due_calls": 0,
            "materialize_calls": 1,
            "replay_calls": 1,
        }
    finally:
        _cleanup_owned_process(process)
