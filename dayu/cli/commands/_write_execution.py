"""写作命令执行阶段与运行前体检编排。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from dayu.cli.commands._write_config_helpers import MODULE, _log_write_preflight_result
from dayu.cli.dependency_setup import run_write_pipeline
from dayu.contracts.cancellation import CancelledError
from dayu.log import Log
from dayu.services.contracts import WriteRequest, WriteRunConfig
from dayu.services.write_model_configuration_application import (
    format_write_model_configuration_application_verification_report,
    load_write_model_configuration_application_receipt,
    verify_write_model_configuration_application_receipt,
)
from dayu.services.write_model_configuration_preapplication import (
    WriteModelConfigurationPreapplicationBlockedError,
    build_write_model_configuration_preapplication_plan,
    build_write_scene_model_routing_snapshot,
    format_write_model_configuration_preapplication_plan_report,
    format_write_model_configuration_preapplication_verification_report,
    format_write_scene_model_routing_snapshot_report,
    load_write_model_configuration_preapplication_plan,
    persist_write_model_configuration_preapplication_plan,
    persist_write_scene_model_routing_snapshot,
    verify_write_model_configuration_preapplication_plan,
)
from dayu.services.write_model_configuration_rollback import (
    WriteModelConfigurationRollbackBlockedError,
    build_write_model_configuration_operator_rollback_approval,
    build_write_model_configuration_operator_rollback_plan,
    format_write_model_configuration_operator_rollback_approval_report,
    format_write_model_configuration_operator_rollback_approval_verification_report,
    format_write_model_configuration_operator_rollback_plan_report,
    format_write_model_configuration_operator_rollback_plan_verification_report,
    load_write_model_configuration_operator_rollback_approval,
    load_write_model_configuration_operator_rollback_approval_request,
    load_write_model_configuration_operator_rollback_plan,
    persist_write_model_configuration_operator_rollback_approval,
    persist_write_model_configuration_operator_rollback_plan,
    verify_write_model_configuration_operator_rollback_approval,
    verify_write_model_configuration_operator_rollback_plan,
)
from dayu.services.write_model_configuration_rollback_application import (
    build_write_model_configuration_operator_rollback_retry_plan,
    format_write_model_configuration_operator_rollback_verification_report,
    load_write_model_configuration_operator_rollback_receipt,
    verify_write_model_configuration_operator_rollback_receipt,
)
from dayu.services.write_model_live_smoke_plan import (
    build_write_model_live_smoke_plan,
    persist_write_model_live_smoke_plan,
)
from dayu.services.write_service import WRITE_CANCELLED_EXIT_CODE, WriteService


def _run_write_stage(*, write_config: WriteRunConfig, write_service: WriteService) -> int:
    """运行一次归因或写作阶段，并统一记录退出结果。

    Args:
        write_config: 本次写作或归因的运行配置。
        write_service: 执行写作流水线的服务。

    Returns:
        流水线退出码；协作式取消返回约定取消码，其他未处理失败返回 2。

    Raises:
        Exception: 启动日志等不在阶段内部映射范围的异常会原样传播。
    """

    infer_mode = write_config.infer
    Log.info("公司级 Facet 归因启动..." if infer_mode else "写作流水线启动...", module=MODULE)
    start_time = perf_counter()
    try:
        exit_code = run_write_pipeline(write_config=write_config, write_service=write_service)
        elapsed = perf_counter() - start_time
        if exit_code == 0:
            Log.info(
                ("公司级 Facet 归因完成" if infer_mode else "写作流水线完成")
                + f": exit_code={exit_code}, elapsed={elapsed:.2f}s",
                module=MODULE,
            )
        elif exit_code == WRITE_CANCELLED_EXIT_CODE:
            Log.warn(
                ("公司级 Facet 归因已取消" if infer_mode else "写作模式已取消")
                + f": exit_code={exit_code}, elapsed={elapsed:.2f}s",
                module=MODULE,
            )
        else:
            Log.warn(
                ("公司级 Facet 归因结束但返回非零" if infer_mode else "写作流水线结束但返回非零")
                + f": exit_code={exit_code}, elapsed={elapsed:.2f}s",
                module=MODULE,
            )
        return exit_code
    except CancelledError as exc:
        elapsed = perf_counter() - start_time
        Log.warn(
            ("公司级 Facet 归因已取消" if infer_mode else "写作模式已取消") + f": elapsed={elapsed:.2f}s, reason={exc}",
            module=MODULE,
        )
        return WRITE_CANCELLED_EXIT_CODE
    except Exception as exc:
        elapsed = perf_counter() - start_time
        Log.error(
            ("公司级 Facet 归因执行失败" if infer_mode else "写作模式执行失败")
            + f": elapsed={elapsed:.2f}s, error={exc}",
            module=MODULE,
        )
        return 2


def _run_write_preflight(
    *,
    write_config: WriteRunConfig,
    write_service: WriteService,
    run_label: str = "",
    config_root: str | Path | None = None,
    workspace_dir: str | Path | None = None,
    routing_snapshot_output: str | Path | None = None,
    live_smoke_plan_output: str | Path | None = None,
    configuration_change_approval_input: str | Path | None = None,
    preapplication_plan_output: str | Path | None = None,
    preapplication_plan_input: str | Path | None = None,
    application_receipt_input: str | Path | None = None,
    rollback_plan_output: str | Path | None = None,
    rollback_plan_input: str | Path | None = None,
    rollback_approval_request: str | Path | None = None,
    rollback_approval_output: str | Path | None = None,
    rollback_approval_input: str | Path | None = None,
    rollback_receipt_input: str | Path | None = None,
) -> int:
    """执行无模型运行前体检与可选不可变配置门禁。

    Args:
        write_config: 本次写作的运行配置。
        write_service: 执行运行前体检的写作服务。
        run_label: 写入体检日志的可选运行标签。
        config_root: 用于构建当前路由快照的配置根路径。
        workspace_dir: 构建实时烟雾计划时使用的工作区路径。
        routing_snapshot_output: 可选的路由快照输出路径。
        live_smoke_plan_output: 可选的实时烟雾计划输出路径。
        configuration_change_approval_input: 配置变更批准输入路径。
        preapplication_plan_output: 可选的预应用计划输出路径。
        preapplication_plan_input: 可选的预应用计划验证输入路径。
        application_receipt_input: 可选的配置应用回执输入路径。
        rollback_plan_output: 可选的回滚或重试计划输出路径。
        rollback_plan_input: 可选的回滚计划验证输入路径。
        rollback_approval_request: 可选的回滚批准请求输入路径。
        rollback_approval_output: 可选的回滚批准输出路径。
        rollback_approval_input: 可选的回滚批准验证输入路径。
        rollback_receipt_input: 可选的回滚回执验证输入路径。

    Returns:
        体检和所有请求门禁通过返回 0，输入或文件失败返回 2，
        配置状态过期或门禁阻断返回 4。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    try:
        result = write_service.preflight(WriteRequest(write_config=write_config))
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        Log.error(f"写作运行前体检失败: {exc}", module=MODULE)
        return 2
    _log_write_preflight_result(result, run_label=run_label)
    if not result.ready:
        return 2
    artifact_requested = any(
        value is not None
        for value in (
            routing_snapshot_output,
            live_smoke_plan_output,
            preapplication_plan_output,
            preapplication_plan_input,
            application_receipt_input,
            rollback_plan_output,
            rollback_plan_input,
            rollback_approval_request,
            rollback_approval_output,
            rollback_approval_input,
            rollback_receipt_input,
        )
    )
    if not artifact_requested:
        return 0
    try:
        current_snapshot = build_write_scene_model_routing_snapshot(
            config_root=config_root,
            write_config=write_config,
            preflight_result=result,
        )
        snapshot_path: Path | None = None
        if routing_snapshot_output is not None:
            snapshot_path = persist_write_scene_model_routing_snapshot(
                current_snapshot,
                routing_snapshot_output,
            )
            print(f"  Write routing snapshot: {snapshot_path}")
            for line in format_write_scene_model_routing_snapshot_report(current_snapshot):
                print(line)
        if live_smoke_plan_output is not None:
            if workspace_dir is None:
                raise ValueError("live smoke plan export requires a workspace directory")
            live_smoke_plan = build_write_model_live_smoke_plan(
                workspace_dir=workspace_dir,
                write_config=write_config,
                preflight_result=result,
                routing_snapshot_fingerprint=str(current_snapshot.get("snapshot_fingerprint") or ""),
            )
            live_smoke_path = persist_write_model_live_smoke_plan(
                live_smoke_plan,
                live_smoke_plan_output,
            )
            print(f"  Write live smoke plan: {live_smoke_path}")
        if preapplication_plan_output is not None:
            if snapshot_path is None or configuration_change_approval_input is None:
                raise ValueError("pre-application plan export requires a persisted snapshot and approval input")
            plan = build_write_model_configuration_preapplication_plan(
                approval_path=configuration_change_approval_input,
                routing_snapshot_path=snapshot_path,
                now=datetime.now(UTC),
            )
            plan_path = persist_write_model_configuration_preapplication_plan(
                plan,
                preapplication_plan_output,
            )
            print(f"  Configuration pre-application plan: {plan_path}")
            for line in format_write_model_configuration_preapplication_plan_report(plan):
                print(line)
        if preapplication_plan_input is not None:
            if configuration_change_approval_input is None:
                raise ValueError("pre-application plan verification requires approval input")
            plan_path, plan = load_write_model_configuration_preapplication_plan(preapplication_plan_input)
            verification = verify_write_model_configuration_preapplication_plan(
                plan,
                current_routing_snapshot=current_snapshot,
                expected_approval_path=(configuration_change_approval_input),
                now=datetime.now(UTC),
            )
            print(f"  Configuration pre-application plan: {plan_path}")
            for line in format_write_model_configuration_preapplication_verification_report(verification):
                print(line)
            if verification.get("status") != "current":
                return 4
        if application_receipt_input is not None:
            receipt_path, receipt = load_write_model_configuration_application_receipt(application_receipt_input)
            verification = verify_write_model_configuration_application_receipt(
                receipt,
                current_routing_snapshot=current_snapshot,
            )
            print(f"  Configuration application receipt: {receipt_path}")
            for line in format_write_model_configuration_application_verification_report(verification):
                print(line)
            if verification.get("status") != "current":
                return 4
            if rollback_plan_output is not None:
                rollback_plan = build_write_model_configuration_operator_rollback_plan(
                    application_receipt_path=receipt_path,
                    current_routing_snapshot=current_snapshot,
                    now=datetime.now(UTC),
                )
                persisted_rollback_plan_path = persist_write_model_configuration_operator_rollback_plan(
                    rollback_plan,
                    rollback_plan_output,
                )
                print(f"  Configuration operator rollback plan: {persisted_rollback_plan_path}")
                for line in format_write_model_configuration_operator_rollback_plan_report(rollback_plan):
                    print(line)
            if rollback_plan_input is not None:
                rollback_plan_path, rollback_plan = load_write_model_configuration_operator_rollback_plan(
                    rollback_plan_input
                )
                rollback_plan_verification = verify_write_model_configuration_operator_rollback_plan(
                    rollback_plan,
                    expected_application_receipt_path=receipt_path,
                    current_routing_snapshot=current_snapshot,
                )
                print(f"  Configuration operator rollback plan: {rollback_plan_path}")
                for line in format_write_model_configuration_operator_rollback_plan_verification_report(
                    rollback_plan_verification
                ):
                    print(line)
                if rollback_plan_verification.get("status") != "current":
                    return 4
                if rollback_approval_request is not None:
                    _request_path, approval_request = load_write_model_configuration_operator_rollback_approval_request(
                        rollback_approval_request
                    )
                    rollback_approval = build_write_model_configuration_operator_rollback_approval(
                        approval_request=approval_request,
                        rollback_plan_path=rollback_plan_path,
                        rollback_plan=rollback_plan,
                        current_routing_snapshot=current_snapshot,
                        now=datetime.now(UTC),
                    )
                    assert rollback_approval_output is not None
                    persisted_approval_path = persist_write_model_configuration_operator_rollback_approval(
                        rollback_approval,
                        rollback_approval_output,
                    )
                    print(f"  Configuration rollback approval: {persisted_approval_path}")
                    for line in format_write_model_configuration_operator_rollback_approval_report(rollback_approval):
                        print(line)
                if rollback_approval_input is not None:
                    rollback_approval_path, rollback_approval = (
                        load_write_model_configuration_operator_rollback_approval(rollback_approval_input)
                    )
                    approval_verification = verify_write_model_configuration_operator_rollback_approval(
                        rollback_approval,
                        current_routing_snapshot=current_snapshot,
                        now=datetime.now(UTC),
                    )
                    print(f"  Configuration rollback approval: {rollback_approval_path}")
                    for line in format_write_model_configuration_operator_rollback_approval_verification_report(
                        approval_verification
                    ):
                        print(line)
                    if approval_verification.get("status") != "approved":
                        return 4
        if rollback_receipt_input is not None:
            rollback_receipt_path, rollback_receipt = load_write_model_configuration_operator_rollback_receipt(
                rollback_receipt_input
            )
            rollback_receipt_verification = verify_write_model_configuration_operator_rollback_receipt(
                rollback_receipt,
                current_routing_snapshot=current_snapshot,
            )
            print(f"  Configuration operator rollback receipt: {rollback_receipt_path}")
            for line in format_write_model_configuration_operator_rollback_verification_report(
                rollback_receipt_verification
            ):
                print(line)
            if rollback_receipt_verification.get("status") != "current":
                return 4
            if rollback_plan_output is not None:
                retry_plan = build_write_model_configuration_operator_rollback_retry_plan(
                    rollback_receipt_path=rollback_receipt_path,
                    current_routing_snapshot=current_snapshot,
                    now=datetime.now(UTC),
                )
                persisted_retry_plan_path = persist_write_model_configuration_operator_rollback_plan(
                    retry_plan,
                    rollback_plan_output,
                )
                print(f"  Configuration operator rollback retry plan: {persisted_retry_plan_path}")
                for line in format_write_model_configuration_operator_rollback_plan_report(retry_plan):
                    print(line)
    except WriteModelConfigurationRollbackBlockedError as exc:
        Log.error(
            f"Configuration operator rollback gate blocked: {exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationPreapplicationBlockedError as exc:
        Log.error(
            f"Configuration pre-application gate blocked: {exc}",
            module=MODULE,
        )
        return 4
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Configuration pre-application gate failed: {exc}",
            module=MODULE,
        )
        return 2
    return 0
