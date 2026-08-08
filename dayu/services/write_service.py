"""写作服务实现。"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.host_execution import (
    ConcurrencyAcquirePolicy,
    HostedRunContext,
    HostedRunSpec,
)
from dayu.contracts.infrastructure import WorkspaceResourcesProtocol
from dayu.contracts.session import SessionSource
from dayu.host.protocols import HostedExecutionGatewayProtocol, HostGovernanceProtocol
from dayu.process_lifecycle import RunLifecycleObserver
from dayu.services._write_report import (
    _handle_config_change_approval,
    _handle_config_change_request_export,
    _handle_config_change_request_verification,
    _handle_health_trend_and_proposal_and_preflight,
    _handle_promotion_proposal_export,
    _handle_promotion_proposal_verification,
    _print_repriced_comparison,
    _validate_print_report_gate_conditions,
)
from dayu.services.concurrency_lanes import resolve_hosted_run_concurrency_lane
from dayu.services.contracts import (
    SceneModelConfig,
    WriteModelRole,
    WritePreflightIssue,
    WritePreflightIssueCode,
    WritePreflightResult,
    WritePreflightScene,
    WriteRequest,
    WriteRunConfig,
)
from dayu.services.internal.write_pipeline.artifact_store import _OVERVIEW_CHAPTER_TITLE
from dayu.services.internal.write_pipeline.enums import (
    AUDIT_WRITE_SCENES,
    PRIMARY_MODEL_WRITE_SCENES,
    WriteSceneName,
)
from dayu.services.internal.write_pipeline.execution_options import build_execution_options_with_model_override
from dayu.services.internal.write_pipeline.model_usage_ledger import (
    validate_model_pricing_for_budget,
)
from dayu.services.internal.write_pipeline.pipeline import print_write_report, run_write_pipeline
from dayu.services.internal.write_pipeline.prompt_builder import _DECISION_CHAPTER_TITLE
from dayu.services.protocols import WriteServiceProtocol
from dayu.services.scene_execution_acceptance import SceneExecutionAcceptancePreparer

WRITE_CANCELLED_EXIT_CODE = 130


class WritePreflightError(RuntimeError):
    """写作运行前体检未通过。"""

    def __init__(self, result: WritePreflightResult) -> None:
        """保存结构化体检结果并构造安全错误信息。"""

        self.result = result
        details = "；".join(issue.message for issue in result.issues)
        super().__init__(f"写作运行前体检失败: {details or '未知配置错误'}")


@dataclass
class WriteService(WriteServiceProtocol):
    """写作服务。"""

    host: HostedExecutionGatewayProtocol
    host_governance: HostGovernanceProtocol
    workspace: WorkspaceResourcesProtocol
    scene_execution_acceptance_preparer: SceneExecutionAcceptancePreparer
    company_name_resolver: Callable[[str], str] | None = None
    company_meta_summary_resolver: Callable[[str], dict[str, str]] | None = None
    run_lifecycle_observer: RunLifecycleObserver | None = field(default=None)

    def preflight(self, request: WriteRequest) -> WritePreflightResult:
        """校验本次写作真正可能执行的 scene、模型与环境变量。"""

        main_execution_options = build_execution_options_with_model_override(
            execution_options=request.execution_options,
            model_name=request.write_config.write_model_override_name,
        )
        audit_execution_options = build_execution_options_with_model_override(
            execution_options=request.execution_options,
            model_name=request.write_config.audit_model_override_name,
        )
        required_scenes = _resolve_required_write_scenes(request.write_config)
        signature_scene_names = tuple(dict.fromkeys(PRIMARY_MODEL_WRITE_SCENES + AUDIT_WRITE_SCENES))
        resolved_scene_map: dict[str, WritePreflightScene] = {}
        fallback_scene_map: dict[str, WritePreflightScene] = {}
        issues: list[WritePreflightIssue] = []

        for scene_name in signature_scene_names:
            model_role = _resolve_write_model_role(scene_name)
            scene_execution_options = (
                audit_execution_options if model_role == WriteModelRole.AUDIT else main_execution_options
            )
            try:
                model = self.scene_execution_acceptance_preparer.resolve_scene_model(
                    scene_name,
                    scene_execution_options,
                )
            except (KeyError, RuntimeError, ValueError) as exc:
                issues.append(
                    WritePreflightIssue(
                        code=WritePreflightIssueCode.MODEL_CONFIGURATION,
                        message=f"scene {scene_name} 的模型配置无法解析: {exc}",
                        scene_name=scene_name,
                    )
                )
                continue
            resolved_scene_map[scene_name.value] = WritePreflightScene(
                scene_name=scene_name.value,
                model_role=model_role,
                model_name=model.name,
                temperature=model.temperature,
            )
            configured_fallback_name = (
                request.write_config.audit_fallback_model_name
                if model_role == WriteModelRole.AUDIT
                else request.write_config.write_fallback_model_name
            )
            configured_fallback_name = str(configured_fallback_name or "").strip()
            if not configured_fallback_name or configured_fallback_name == model.name:
                continue
            fallback_execution_options = build_execution_options_with_model_override(
                execution_options=request.execution_options,
                model_name=configured_fallback_name,
            )
            try:
                fallback_model = self.scene_execution_acceptance_preparer.resolve_scene_model(
                    scene_name,
                    fallback_execution_options,
                )
            except (KeyError, RuntimeError, ValueError) as exc:
                issues.append(
                    WritePreflightIssue(
                        code=WritePreflightIssueCode.MODEL_CONFIGURATION,
                        message=(
                            f"scene {scene_name} 的 fallback 模型配置无法解析: {exc}"
                        ),
                        scene_name=scene_name,
                        model_name=configured_fallback_name,
                    )
                )
                continue
            if fallback_model.name == model.name:
                continue
            fallback_scene_map[scene_name.value] = WritePreflightScene(
                scene_name=scene_name.value,
                model_role=model_role,
                model_name=fallback_model.name,
                temperature=fallback_model.temperature,
            )

        resolved_scenes = tuple(
            resolved_scene_map[scene_name.value]
            for scene_name in required_scenes
            if scene_name.value in resolved_scene_map
        )
        signature_scenes = tuple(
            resolved_scene_map[scene_name.value]
            for scene_name in signature_scene_names
            if scene_name.value in resolved_scene_map
        )
        resolved_fallback_scenes = tuple(
            fallback_scene_map[scene_name.value]
            for scene_name in required_scenes
            if scene_name.value in fallback_scene_map
        )
        signature_fallback_scenes = tuple(
            fallback_scene_map[scene_name.value]
            for scene_name in signature_scene_names
            if scene_name.value in fallback_scene_map
        )
        required_models = tuple(
            dict.fromkeys(
                scene.model_name
                for scene in (*resolved_scenes, *resolved_fallback_scenes)
            )
        )
        if request.write_config.write_max_estimated_cost is not None:
            try:
                model_catalog = self.workspace.config_loader.load_llm_models()
            except (OSError, TypeError, ValueError) as exc:
                issues.append(
                    WritePreflightIssue(
                        code=WritePreflightIssueCode.BUDGET_CONFIGURATION,
                        message=f"写作成本预算无法加载模型目录: {exc}",
                    )
                )
            else:
                for model_name in required_models:
                    raw_model_config = model_catalog.get(model_name)
                    if not isinstance(raw_model_config, Mapping):
                        pricing_issue = (
                            f"模型 {model_name} 缺少可审计价格，无法启用写作成本预算"
                        )
                    else:
                        pricing_issue = validate_model_pricing_for_budget(
                            model_name=model_name,
                            model_config=raw_model_config,
                            budget_currency=request.write_config.write_budget_currency,
                        )
                    if pricing_issue is not None:
                        issues.append(
                            WritePreflightIssue(
                                code=WritePreflightIssueCode.BUDGET_CONFIGURATION,
                                message=pricing_issue,
                                model_name=model_name,
                            )
                        )
        environment_models: dict[str, set[str]] = {}
        for model_name in required_models:
            try:
                model_environment_variables = self.workspace.config_loader.collect_model_referenced_env_vars(
                    (model_name,)
                )
            except (KeyError, RuntimeError, ValueError) as exc:
                issues.append(
                    WritePreflightIssue(
                        code=WritePreflightIssueCode.MODEL_CONFIGURATION,
                        message=f"模型 {model_name} 的环境变量配置无法解析: {exc}",
                        model_name=model_name,
                    )
                )
                continue
            for environment_variable in model_environment_variables:
                environment_models.setdefault(environment_variable, set()).add(model_name)

        required_environment_variables = tuple(sorted(environment_models))
        for environment_variable in required_environment_variables:
            if str(os.environ.get(environment_variable) or "").strip():
                continue
            model_names = ", ".join(sorted(environment_models[environment_variable]))
            issues.append(
                WritePreflightIssue(
                    code=WritePreflightIssueCode.MISSING_ENVIRONMENT_VARIABLE,
                    message=f"模型 {model_names} 缺少环境变量: {environment_variable}",
                    model_name=model_names,
                    environment_variable=environment_variable,
                )
            )

        return WritePreflightResult(
            ready=not issues,
            scenes=resolved_scenes,
            signature_scenes=signature_scenes,
            required_environment_variables=required_environment_variables,
            issues=tuple(issues),
            fallback_scenes=resolved_fallback_scenes,
            signature_fallback_scenes=signature_fallback_scenes,
        )

    def run(self, request: WriteRequest) -> int:
        """执行写作流水线。

        Args:
            request: 写作执行请求。

        Returns:
            写作流程退出码；若宿主在同步执行阶段收口为取消，则返回显式取消退出码。

        Raises:
            WritePreflightError: 本次写作所需模型或环境变量未通过体检时抛出。
            RuntimeError: 写作流水线主体抛出的运行时异常会继续向上传播。
        """

        preflight_result = self.preflight(request)
        if not preflight_result.ready:
            raise WritePreflightError(preflight_result)
        prepared_request = replace(
            request,
            write_config=replace(
                request.write_config,
                scene_models={
                    scene.scene_name: SceneModelConfig(
                        name=scene.model_name,
                        temperature=scene.temperature,
                    )
                    for scene in preflight_result.signature_scenes
                },
                scene_fallback_models={
                    scene.scene_name: SceneModelConfig(
                        name=scene.model_name,
                        temperature=scene.temperature,
                    )
                    for scene in preflight_result.signature_fallback_scenes
                },
            ),
        )

        session = self.host.create_session(SessionSource.API)
        spec = HostedRunSpec(
            operation_name="write_pipeline",
            session_id=session.session_id,
            scene_name=WriteSceneName.WRITE,
            business_concurrency_lane=resolve_hosted_run_concurrency_lane("write_pipeline"),
            concurrency_acquire_policy=ConcurrencyAcquirePolicy.unbounded(),
        )
        return self.host.run_operation_sync(
            spec=spec,
            operation=lambda context: self._run_pipeline_with_observer(
                prepared_request,
                host_session_id=session.session_id,
                context=context,
            ),
            on_cancel=lambda: WRITE_CANCELLED_EXIT_CODE,
        )

    def _run_pipeline_with_observer(
        self,
        request: WriteRequest,
        *,
        host_session_id: str,
        context: HostedRunContext,
    ) -> int:
        """在生命周期观察者登记 run_id 之后执行写作流水线。

        本方法负责把当前 ``HostedRunContext`` 的 run_id 暴露给可选的
        ``RunLifecycleObserver``（让进程级协调器能在 Ctrl-C 时触发
        ``host.cancel_run`` → ``CancellationBridge``），同时把
        ``HostedRunContext.cancellation_token`` 透传给写作流水线，让其在
        章节边界主动 ``raise_if_cancelled`` 协作退出。

        Args:
            request: 写作执行请求。
            host_session_id: 当前写作流水线复用的 Host Session。
            context: Host 注入的运行时上下文，承载 run_id 与 token。

        Returns:
            写作流水线退出码。

        Raises:
            RuntimeError: 写作流水线主体抛出的运行时异常会继续向上传播。
        """

        observer = self.run_lifecycle_observer
        if observer is not None and context.run_id:
            observer.register_active_run(context.run_id)
        try:
            return self._run_pipeline(
                request,
                host_session_id=host_session_id,
                cancellation_token=context.cancellation_token,
            )
        finally:
            if observer is not None and context.run_id:
                observer.clear_active_run(context.run_id)

    def _run_pipeline(
        self,
        request: WriteRequest,
        *,
        host_session_id: str,
        cancellation_token: CancellationToken | None = None,
    ) -> int:
        """执行写作流水线主体。"""

        main_execution_options = build_execution_options_with_model_override(
            execution_options=request.execution_options,
            model_name=request.write_config.write_model_override_name,
        )
        audit_execution_options = build_execution_options_with_model_override(
            execution_options=request.execution_options,
            model_name=request.write_config.audit_model_override_name,
        )
        entry_scene = _resolve_pipeline_entry_scene(request.write_config)
        entry_execution_options = (
            audit_execution_options
            if _resolve_write_model_role(entry_scene) == WriteModelRole.AUDIT
            else main_execution_options
        )
        resolved_options = self.scene_execution_acceptance_preparer.resolve_execution_options(
            entry_scene,
            entry_execution_options,
        )

        return run_write_pipeline(
            workspace=self.workspace,
            resolved_options=resolved_options,
            write_config=request.write_config,
            scene_execution_acceptance_preparer=self.scene_execution_acceptance_preparer,
            host_executor=self.host,
            host_governance=self.host_governance,
            host_session_id=host_session_id,
            execution_options=main_execution_options,
            company_name_resolver=self.company_name_resolver,
            company_meta_summary_resolver=self.company_meta_summary_resolver,
            cancellation_token=cancellation_token,
        )

    @staticmethod
    def print_report(
        output_dir: str | Path,
        *,
        model_catalog: Mapping[str, Mapping[str, object]] | None = None,
        routing_history_root: str | Path | None = None,
        routing_proposal_input: str | Path | None = None,
        routing_proposal_output: str | Path | None = None,
        overwrite_routing_proposal: bool = False,
        routing_preflight_approval_request: str | Path | None = None,
        routing_preflight_approval_output: str | Path | None = None,
        challenger_promotion_proposal_input: str | Path | None = None,
        challenger_promotion_proposal_output: str | Path | None = None,
        challenger_config_change_request_input: str | Path | None = None,
        challenger_config_change_request_output: str | Path | None = None,
        challenger_config_change_approval_request: str | Path | None = None,
        challenger_config_change_approval_output: str | Path | None = None,
        challenger_config_change_approval_input: str | Path | None = None,
    ) -> int:
        """打印基础写作报告并按固定顺序执行附加报告子流程。

        Args:
            output_dir: 写作流水线输出目录。
            model_catalog: 可选的当前模型目录，用于成本重估与健康趋势。
            routing_history_root: 模型路由历史目录。
            routing_proposal_input: Challenger 提案输入路径。
            routing_proposal_output: Challenger 提案输出路径。
            overwrite_routing_proposal: 是否覆盖既有 Challenger 提案。
            routing_preflight_approval_request: 预检批准请求路径。
            routing_preflight_approval_output: 预检批准输出路径。
            challenger_promotion_proposal_input: 晋升提案输入路径。
            challenger_promotion_proposal_output: 晋升提案输出路径。
            challenger_config_change_request_input: 配置变更请求输入路径。
            challenger_config_change_request_output: 配置变更请求输出路径。
            challenger_config_change_approval_request: 配置变更批准请求路径。
            challenger_config_change_approval_output: 配置变更批准输出路径。
            challenger_config_change_approval_input: 配置变更批准输入路径。

        Returns:
            成功时返回基础报告退出码；输入输出失败返回 ``2``；策略或状态阻断返回
            ``4``。

        Raises:
            子流程中未被既定错误边界捕获的底层异常。
        """

        exit_code = print_write_report(output_dir, model_catalog=model_catalog)
        if exit_code == 2:
            return exit_code
        gate_exit_code = _validate_print_report_gate_conditions(
            routing_preflight_approval_request=routing_preflight_approval_request,
            routing_preflight_approval_output=routing_preflight_approval_output,
            routing_proposal_input=routing_proposal_input,
            routing_proposal_output=routing_proposal_output,
            routing_history_root=routing_history_root,
            challenger_promotion_proposal_input=challenger_promotion_proposal_input,
            challenger_promotion_proposal_output=challenger_promotion_proposal_output,
            challenger_config_change_request_input=challenger_config_change_request_input,
            challenger_config_change_request_output=challenger_config_change_request_output,
            challenger_config_change_approval_request=challenger_config_change_approval_request,
            challenger_config_change_approval_output=challenger_config_change_approval_output,
            challenger_config_change_approval_input=challenger_config_change_approval_input,
        )
        if gate_exit_code is not None:
            return gate_exit_code

        _print_repriced_comparison(output_dir, model_catalog)

        promotion_export_exit_code = _handle_promotion_proposal_export(
            output_dir,
            challenger_promotion_proposal_output,
        )
        if promotion_export_exit_code != 0:
            return promotion_export_exit_code
        promotion_verification_exit_code = _handle_promotion_proposal_verification(
            challenger_promotion_proposal_input
        )
        if promotion_verification_exit_code != 0:
            return promotion_verification_exit_code

        request_export_exit_code = _handle_config_change_request_export(
            challenger_config_change_request_output,
            challenger_promotion_proposal_input,
        )
        if request_export_exit_code != 0:
            return request_export_exit_code
        config_change_approval_issuance = (
            challenger_config_change_approval_request is not None
            or challenger_config_change_approval_output is not None
        )
        if not config_change_approval_issuance:
            request_verification_exit_code = (
                _handle_config_change_request_verification(
                    challenger_config_change_request_input
                )
            )
            if request_verification_exit_code != 0:
                return request_verification_exit_code
        approval_exit_code = _handle_config_change_approval(
            challenger_config_change_approval_request,
            challenger_config_change_approval_output,
            challenger_config_change_approval_input,
            challenger_config_change_request_input,
        )
        if approval_exit_code != 0:
            return approval_exit_code

        health_exit_code = _handle_health_trend_and_proposal_and_preflight(
            output_dir,
            routing_history_root,
            model_catalog,
            routing_proposal_output,
            routing_proposal_input,
            overwrite_routing_proposal,
            routing_preflight_approval_request,
            routing_preflight_approval_output,
        )
        if health_exit_code != 0:
            return health_exit_code
        return exit_code


def _resolve_write_model_role(scene_name: WriteSceneName) -> WriteModelRole:
    """返回 scene 对应的主写或审核模型职责。"""

    if scene_name in AUDIT_WRITE_SCENES:
        return WriteModelRole.AUDIT
    if scene_name in PRIMARY_MODEL_WRITE_SCENES:
        return WriteModelRole.PRIMARY
    raise ValueError(f"未知写作 scene: {scene_name}")


def _resolve_pipeline_entry_scene(write_config: WriteRunConfig) -> WriteSceneName:
    """返回用于解析流水线基础运行参数的入口 scene。"""

    if write_config.infer:
        return WriteSceneName.INFER
    chapter_filter = write_config.chapter_filter.strip()
    if chapter_filter == _OVERVIEW_CHAPTER_TITLE:
        return WriteSceneName.OVERVIEW
    if chapter_filter == _DECISION_CHAPTER_TITLE:
        return WriteSceneName.DECISION
    return WriteSceneName.WRITE


def _resolve_required_write_scenes(write_config: WriteRunConfig) -> tuple[WriteSceneName, ...]:
    """按本次运行模式列出真正可能创建的 scene。"""

    if write_config.infer:
        return (WriteSceneName.INFER,)

    required_scenes: list[WriteSceneName] = [WriteSceneName.INFER]
    chapter_filter = write_config.chapter_filter.strip()
    if chapter_filter == _OVERVIEW_CHAPTER_TITLE:
        required_scenes.append(WriteSceneName.OVERVIEW)
    elif chapter_filter == _DECISION_CHAPTER_TITLE:
        required_scenes.append(WriteSceneName.DECISION)
    elif chapter_filter:
        required_scenes.append(WriteSceneName.WRITE)
    else:
        required_scenes.extend(
            (
                WriteSceneName.WRITE,
                WriteSceneName.DECISION,
                WriteSceneName.OVERVIEW,
            )
        )

    if not write_config.fast:
        required_scenes.extend(
            (
                WriteSceneName.REGENERATE,
                WriteSceneName.FIX,
                WriteSceneName.REPAIR,
                WriteSceneName.AUDIT,
                WriteSceneName.CONFIRM,
            )
        )
    return tuple(dict.fromkeys(required_scenes))


__all__ = [
    "WRITE_CANCELLED_EXIT_CODE",
    "WritePreflightError",
    "WriteRunConfig",
    "WriteService",
]
