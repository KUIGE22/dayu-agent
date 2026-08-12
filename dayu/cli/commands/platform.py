"""Durable platform Worker/Scheduler 的唯一 CLI 进程入口。

本模块只在 ``main`` 命中 ``platform`` 后延迟导入，负责把 canonical
tenant selector 收敛为 ``TenantScope``，调用唯一 startup composition
wrapper，构造 Host loop，并统一管理安全启动快照、软/硬信号边界、退出码
和 prepared runtime 的幂等关闭。Redis/PG/Host 的具体装配仍只属于
``dayu.services.startup_preparation``。
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import signal
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

from dayu.cli.dependency_setup import setup_loglevel
from dayu.host.process_intake import ProcessIntakeGate
from dayu.host.scheduler import PlatformScheduler
from dayu.host.worker import PlatformWorker
from dayu.investment.config import (
    PlatformDeploymentProfile,
    PlatformQueueAdmissionKind,
    PlatformSettingsError,
    build_queue_startup_snapshot,
)
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.log import Log
from dayu.services.startup_preparation import (
    PreparedPlatformQueueRuntime,
    prepare_platform_queue_runtime_dependencies,
)

if TYPE_CHECKING:
    from dayu.cli.arguments import DayuCliArguments

_MODULE = "APP.PLATFORM"
_CLI_INPUT_EXIT_CODE = 2
_RUNTIME_FAILURE_EXIT_CODE = 1
_GENERATED_ID_HEX_BYTES = 6
_PROCESS_SIGNALS = (signal.SIGINT, signal.SIGTERM)


class _PlatformAction(Enum):
    """CLI 允许的 closed platform action。"""

    WORKER = "worker"
    SCHEDULER = "scheduler"


@runtime_checkable
class _PlatformCommandArguments(Protocol):
    """platform command 消费的 argparse 最小字段边界。"""

    platform_action: str
    tenant_id: str
    worker_id: str | None
    scheduler_id: str | None
    base: str
    config: str | None


class _PlatformProcessProtocol(Protocol):
    """CLI signal/lifecycle 只需要的 Host process 窄端口。"""

    def request_stop(self) -> None:
        """请求停止新 intake 并进入 cooperative drain。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        ...

    async def run(self) -> int:
        """运行 Host process loop。

        Args:
            无。

        Returns:
            closed process exit code。

        Raises:
            BaseException: 未被 Host loop 收口的异常原样传播。
        """

        ...


@dataclass(frozen=True, slots=True)
class _PlatformInvocation:
    """参数解析后、任何 startup 副作用前的 immutable 调用快照。

    Args:
        action: worker 或 scheduler closed action。
        tenant_id: canonical、非零 tenant UUID 字符串。
        scope: 由固定 system ``Principal`` 派生的租户范围。
        process_id: 显式安全标签或本地生成的无 hostname 标签。
        workspace_root: CLI workspace 路径。
        config_root: 可选 CLI config 路径。
    """

    action: _PlatformAction
    tenant_id: str
    scope: TenantScope
    process_id: str
    workspace_root: Path
    config_root: Path | None


class _SynchronousSignalHandlerProtocol(Protocol):
    """标准库同步 signal handler 的可恢复窄签名。"""

    def __call__(
        self,
        signal_number: int,
        frame: FrameType | None,
        /,
    ) -> None:
        """处理一个同步信号。

        Args:
            signal_number: 标准库传入的信号编号。
            frame: 收到信号时的可空 Python frame。

        Returns:
            无。

        Raises:
            BaseException: 原 handler 的既有终止语义原样传播。
        """

        ...


_SynchronousSignalHandler = signal.Handlers | int | None | _SynchronousSignalHandlerProtocol


class _PlatformSignalManager:
    """把首个信号线性化为 soft stop、第二个信号线性化为 OS hard stop。"""

    def __init__(self, process: _PlatformProcessProtocol) -> None:
        """保存唯一 process，并初始化尚未安装的信号状态。

        Args:
            process: 当前 Worker 或 Scheduler 的最小生命周期端口。

        Returns:
            无。

        Raises:
            无。
        """

        self._process = process
        self._loop: asyncio.AbstractEventLoop | None = None
        self._signal_count = 0
        self._loop_signals: set[signal.Signals] = set()
        self._fallback_handlers: dict[
            signal.Signals,
            _SynchronousSignalHandler,
        ] = {}

    def install(self, loop: asyncio.AbstractEventLoop) -> None:
        """在当前 event loop 安装 SIGINT/SIGTERM 处理。

        POSIX ``add_signal_handler`` 的 callback 已在 loop 内执行；不支持
        该 API 的 event loop 使用同步 handler 只投递
        ``call_soon_threadsafe``，真正的 stop/hard-stop 决策仍在 loop 内。

        Args:
            loop: 当前 Host process 所属 event loop。

        Returns:
            无。

        Raises:
            RuntimeError: 同一 manager 被重复安装时抛出。
            ValueError: fallback 信号注册不在主线程时由标准库抛出。
        """

        if self._loop is not None:
            raise RuntimeError("platform signal manager 已安装")
        self._loop = loop
        try:
            for process_signal in _PROCESS_SIGNALS:
                try:
                    loop.add_signal_handler(
                        process_signal,
                        self._handle_signal_in_loop,
                    )
                except NotImplementedError:
                    previous = signal.signal(
                        process_signal,
                        self._forward_signal_to_loop,
                    )
                    self._fallback_handlers[process_signal] = previous
                else:
                    self._loop_signals.add(process_signal)
        except Exception:
            self.uninstall()
            raise

    def uninstall(self) -> None:
        """恢复本 manager 安装的信号处理器。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: fallback handler 不在主线程恢复时由标准库抛出。
        """

        loop = self._loop
        if loop is None:
            return
        for process_signal in self._loop_signals:
            loop.remove_signal_handler(process_signal)
        self._loop_signals.clear()
        for process_signal, previous in self._fallback_handlers.items():
            signal.signal(process_signal, previous)
        self._fallback_handlers.clear()
        self._loop = None

    def _forward_signal_to_loop(
        self,
        _signal_number: int,
        _frame: FrameType | None,
    ) -> None:
        """把同步 signal handler 收窄为 event-loop callback。

        Args:
            _signal_number: 标准库传入的信号编号；closed action 不依赖它。
            _frame: 标准库传入的可空 frame；不进入业务或日志。

        Returns:
            无。

        Raises:
            RuntimeError: event loop 已关闭时由 ``call_soon_threadsafe``
                抛出。
        """

        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._handle_signal_in_loop)

    def _handle_signal_in_loop(self) -> None:
        """在 event loop 内执行首信号 soft stop/第二信号 hard stop。

        Args:
            无。

        Returns:
            无。

        Raises:
            无；第二信号由 ``os._exit(1)`` 直接终止进程。
        """

        self._signal_count += 1
        if self._signal_count == 1:
            self._process.request_stop()
            return
        os._exit(_RUNTIME_FAILURE_EXIT_CODE)


def _canonical_tenant_id(value: str) -> str:
    """在 startup 前再次验证 canonical、非零 tenant selector。

    Args:
        value: argparse 已解析的 tenant 字符串。

    Returns:
        保持原样的 canonical tenant UUID。

    Raises:
        ValueError: 输入不是 exact canonical、非零 UUID 时抛出；消息不
            回显候选值。
    """

    try:
        parsed = UUID(value)
    except (AttributeError, ValueError):
        raise ValueError("tenant selector 非法") from None
    if parsed.int == 0 or str(parsed) != value:
        raise ValueError("tenant selector 非法")
    return value


def _generate_process_id(action: _PlatformAction) -> str:
    """生成不依赖 hostname、环境变量或 secret 的进程标签。

    Args:
        action: worker 或 scheduler action。

    Returns:
        ``worker_<12hex>`` 或 ``scheduler_<12hex>``。

    Raises:
        无。
    """

    return f"{action.value}_{secrets.token_hex(_GENERATED_ID_HEX_BYTES)}"


def _resolve_invocation(args: _PlatformCommandArguments) -> _PlatformInvocation:
    """把 typed CLI 参数收敛成无副作用 invocation。

    Args:
        args: 已通过 argparse 的 platform 参数。

    Returns:
        包含 scope、process id 与路径的 immutable invocation。

    Raises:
        ValueError: action、tenant 或 action-specific id 组合非法时抛出。
    """

    try:
        action = _PlatformAction(args.platform_action)
    except ValueError:
        raise ValueError("platform action 非法") from None
    tenant_id = _canonical_tenant_id(args.tenant_id)
    if action is _PlatformAction.WORKER:
        if args.scheduler_id is not None:
            raise ValueError("worker action 不接受 scheduler id")
        process_id = args.worker_id or _generate_process_id(action)
        user_id = "platform-worker"
    else:
        if args.worker_id is not None:
            raise ValueError("scheduler action 不接受 worker id")
        process_id = args.scheduler_id or _generate_process_id(action)
        user_id = "platform-scheduler"
    principal = Principal(
        tenant_id=TenantId(tenant_id),
        user_id=user_id,
    )
    config_root = Path(args.config).expanduser() if args.config is not None else None
    return _PlatformInvocation(
        action=action,
        tenant_id=tenant_id,
        scope=principal.to_scope(),
        process_id=process_id,
        workspace_root=Path(args.base).expanduser(),
        config_root=config_root,
    )


def _profile_from_admission(
    admission_kind: PlatformQueueAdmissionKind,
) -> PlatformDeploymentProfile:
    """从 closed admission 唯一反解 startup snapshot profile。

    Args:
        admission_kind: startup 已验证的 durable admission kind。

    Returns:
        REDIS 对应 production；POSTGRES_ONLY 对应 integration。

    Raises:
        PlatformSettingsError: platform runtime 意外返回 NOT_REQUIRED 时
            fail closed。
    """

    if admission_kind is PlatformQueueAdmissionKind.REDIS:
        return PlatformDeploymentProfile.PRODUCTION
    if admission_kind is PlatformQueueAdmissionKind.POSTGRES_ONLY:
        return PlatformDeploymentProfile.INTEGRATION
    raise PlatformSettingsError("platform queue runtime admission 非法")


def _record_safe_startup_snapshot(
    invocation: _PlatformInvocation,
    prepared: PreparedPlatformQueueRuntime,
) -> None:
    """构建并记录只含 allowlist 字段的安全启动快照。

    Args:
        invocation: 已验证的 CLI invocation。
        prepared: 唯一 startup composition 返回的 prepared runtime。

    Returns:
        无。

    Raises:
        PlatformSettingsError: admission/profile/settings 或 process label
            不闭合时抛出。
        ValueError: tenant identity 意外漂移时抛出。
    """

    profile = _profile_from_admission(prepared.queue_admission.kind)
    snapshot = build_queue_startup_snapshot(
        profile=profile,
        queue_settings=prepared.queue_settings,
        tenant_id=invocation.tenant_id,
        process_label=invocation.process_id,
    )
    Log.info(
        "platform_queue_startup="
        + json.dumps(
            snapshot,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ),
        module=_MODULE,
    )


def _build_process(
    invocation: _PlatformInvocation,
    prepared: PreparedPlatformQueueRuntime,
    intake_gate: ProcessIntakeGate,
) -> _PlatformProcessProtocol:
    """从 prepared direct refs 构造唯一 Host process loop。

    Args:
        invocation: 已验证 invocation。
        prepared: 唯一 startup wrapper 的 typed 结果。
        intake_gate: CLI signal callback 与 Host loop 共享的入口闸门。

    Returns:
        ``PlatformWorker`` 或 ``PlatformScheduler`` 的窄生命周期视图。

    Raises:
        TypeError: direct Service ref 不满足 Host-local gateway 时抛出。
        ValueError: queue mode 与 Redis references 不闭合时抛出。
    """

    if invocation.action is _PlatformAction.WORKER:
        return PlatformWorker(
            gateway=prepared.job_service,
            scope=invocation.scope,
            worker_id=invocation.process_id,
            settings=prepared.queue_settings,
            intake_gate=intake_gate,
            redis_subscriber_factory=(prepared.queue_admission.subscriber_factory),
            redis_client=prepared.queue_admission.redis_client,
        )
    return PlatformScheduler(
        gateway=prepared.schedule_service,
        scope=invocation.scope,
        settings=prepared.queue_settings,
        intake_gate=intake_gate,
    )


async def _run_platform_process(process: _PlatformProcessProtocol) -> int:
    """安装 loop-owned 信号处理并运行 Host process。

    Args:
        process: 当前 Worker/Scheduler 窄生命周期端口。

    Returns:
        Host process 返回的 closed exit code。

    Raises:
        BaseException: signal 安装或 process loop 的未分类异常原样传播。
    """

    signal_manager = _PlatformSignalManager(process)
    signal_manager.install(asyncio.get_running_loop())
    try:
        return await process.run()
    finally:
        signal_manager.uninstall()


def _close_prepared_runtime(prepared: PreparedPlatformQueueRuntime) -> bool:
    """关闭 prepared runtime，并把关闭异常收窄为 safe runtime failure。

    Args:
        prepared: 唯一 startup composition 的生命周期 owner。

    Returns:
        close 成功为 ``True``；发生程序/adapter 异常为 ``False``。

    Raises:
        无。
    """

    try:
        prepared.close()
    except Exception:
        print("platform runtime 关闭失败", file=sys.stderr)
        return False
    return True


def _run_prepared_process(
    process: _PlatformProcessProtocol,
    prepared: PreparedPlatformQueueRuntime,
) -> int:
    """运行进程并保证非 hard-stop 路径 exact-once 关闭 prepared runtime。

    Args:
        process: 已构造的 Worker/Scheduler loop。
        prepared: 唯一 startup lifecycle owner。

    Returns:
        Host loop exit code；未分类 runtime/close 异常映射为 1。

    Raises:
        KeyboardInterrupt: loop 专用 handler 安装前的中断原样交给
            ``main`` 映射既有 SIGINT code。
        BaseException: ``Exception`` 之外的未知终止原样传播。
    """

    exit_code = _RUNTIME_FAILURE_EXIT_CODE
    close_succeeded = False
    try:
        try:
            exit_code = asyncio.run(_run_platform_process(process))
        except Exception:
            print("platform runtime 执行失败", file=sys.stderr)
            exit_code = _RUNTIME_FAILURE_EXIT_CODE
    finally:
        close_succeeded = _close_prepared_runtime(prepared)
    if not close_succeeded:
        return _RUNTIME_FAILURE_EXIT_CODE
    return exit_code


def run_platform_command(args: DayuCliArguments) -> int:
    """执行唯一 ``platform worker|scheduler`` CLI 入口。

    Args:
        args: argparse 生成的 Dayu CLI 参数。

    Returns:
        graceful drain 为 0；runtime invariant 为 1；CLI/config/admission
        失败为 2。

    Raises:
        KeyboardInterrupt: 专用 loop handler 安装前的 SIGINT 原样交给
            ``main`` 收口。
        BaseException: 非 ``Exception`` 的未知终止原样传播。
    """

    try:
        setup_loglevel(args)
    except Exception:
        print("platform CLI 参数非法", file=sys.stderr)
        return _CLI_INPUT_EXIT_CODE
    if not isinstance(args, _PlatformCommandArguments):
        print("platform CLI 参数不完整", file=sys.stderr)
        return _CLI_INPUT_EXIT_CODE
    try:
        invocation = _resolve_invocation(args)
    except Exception:
        print("platform CLI 参数非法", file=sys.stderr)
        return _CLI_INPUT_EXIT_CODE

    try:
        prepared = prepare_platform_queue_runtime_dependencies(
            workspace_root=invocation.workspace_root,
            config_root=invocation.config_root,
            execution_options=None,
            runtime_label=invocation.process_id,
            log_module=_MODULE,
        )
    except Exception:
        print("platform 配置或启动准入失败", file=sys.stderr)
        return _CLI_INPUT_EXIT_CODE

    process_ready = False
    try:
        _record_safe_startup_snapshot(invocation, prepared)
        process = _build_process(
            invocation,
            prepared,
            ProcessIntakeGate(),
        )
        process_ready = True
    except Exception:
        print("platform 配置或启动准入失败", file=sys.stderr)
        return _CLI_INPUT_EXIT_CODE
    finally:
        if not process_ready:
            _close_prepared_runtime(prepared)

    return _run_prepared_process(process, prepared)


__all__ = ["run_platform_command"]
