"""写作服务实现。"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
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
from dayu.services.write_model_challenger_preflight_approval import (
    WriteModelPreflightApprovalBlockedError,
    build_write_model_challenger_preflight_approval,
    format_write_model_challenger_preflight_approval_report,
    load_write_model_challenger_preflight_approval_request,
    persist_write_model_challenger_preflight_approval,
)
from dayu.services.write_model_challenger_promotion import (
    WriteModelChallengerPromotionBlockedError,
    build_write_model_challenger_promotion_proposal,
    format_write_model_challenger_promotion_report,
    format_write_model_challenger_promotion_verification_report,
    load_write_model_challenger_promotion_proposal,
    persist_write_model_challenger_promotion_proposal,
    verify_write_model_challenger_promotion_proposal,
)
from dayu.services.write_model_challenger_proposal import (
    load_write_model_challenger_proposal,
    persist_write_model_challenger_proposal,
)
from dayu.services.write_model_challenger_verification import (
    format_write_model_challenger_verification_report,
    verify_write_model_challenger_proposal,
)
from dayu.services.write_model_configuration_change import (
    WriteModelConfigurationChangeBlockedError,
    build_write_model_configuration_change_approval,
    build_write_model_configuration_change_request,
    format_write_model_configuration_change_approval_report,
    format_write_model_configuration_change_approval_verification_report,
    format_write_model_configuration_change_request_report,
    format_write_model_configuration_change_request_verification_report,
    load_write_model_configuration_change_approval,
    load_write_model_configuration_change_approval_request,
    load_write_model_configuration_change_request,
    persist_write_model_configuration_change_approval,
    persist_write_model_configuration_change_request,
    verify_write_model_configuration_change_approval,
    verify_write_model_configuration_change_request,
)
from dayu.services.write_model_health import (
    build_write_model_health_trend,
    format_write_model_health_report,
)
from dayu.services.write_run_comparison import (
    format_write_run_comparison_report,
    load_write_run_comparison,
    resolve_write_run_comparison_for_report,
)

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
        """打印写作流水线报告。"""

        exit_code = print_write_report(output_dir, model_catalog=model_catalog)
        if exit_code == 2:
            return exit_code
        approval_requested = (
            routing_preflight_approval_request is not None
            or routing_preflight_approval_output is not None
        )
        proposal_requested = (
            routing_proposal_input is not None
            or routing_proposal_output is not None
            or approval_requested
        )
        if proposal_requested and routing_history_root is None:
            print(
                "  [警告] Challenger 提案操作需要提供模型路由历史目录"
            )
            return 2
        if (
            routing_proposal_input is not None
            and routing_proposal_output is not None
        ):
            print("  [警告] Challenger 提案输入与输出不能同时使用")
            return 2
        if (
            challenger_promotion_proposal_input is not None
            and challenger_promotion_proposal_output is not None
        ):
            print(
                "  [warning] Challenger promotion proposal input and "
                "output cannot be used together"
            )
            return 2
        config_change_approval_issuance = (
            challenger_config_change_approval_request is not None
            or challenger_config_change_approval_output is not None
        )
        if (
            challenger_config_change_request_input is not None
            and challenger_config_change_request_output is not None
        ):
            print(
                "  [warning] configuration change request input and "
                "output cannot be used together"
            )
            return 2
        if (
            challenger_config_change_approval_request is None
            and challenger_config_change_approval_output is not None
        ) or (
            challenger_config_change_approval_request is not None
            and challenger_config_change_approval_output is None
        ):
            print(
                "  [warning] configuration change approval request and "
                "output must be provided together"
            )
            return 2
        if (
            challenger_config_change_request_output is not None
            and challenger_promotion_proposal_input is None
        ):
            print(
                "  [warning] configuration change request export "
                "requires a promotion proposal input"
            )
            return 2
        if (
            config_change_approval_issuance
            and challenger_config_change_request_input is None
        ):
            print(
                "  [warning] configuration change approval issuance "
                "requires a configuration change request input"
            )
            return 2
        if (
            challenger_config_change_approval_input is not None
            and (
                challenger_config_change_request_input is not None
                or challenger_config_change_request_output is not None
                or config_change_approval_issuance
            )
        ):
            print(
                "  [warning] configuration change approval verification "
                "cannot be combined with request or issuance operations"
            )
            return 2
        if (
            routing_preflight_approval_request is None
            and routing_preflight_approval_output is not None
        ) or (
            routing_preflight_approval_request is not None
            and routing_preflight_approval_output is None
        ):
            print(
                "  [warning] preflight approval request and output "
                "must be provided together"
            )
            return 2
        if approval_requested and routing_proposal_input is None:
            print(
                "  [warning] preflight approval requires a verified "
                "Challenger proposal input"
            )
            return 2
        try:
            resolved_comparison = resolve_write_run_comparison_for_report(
                output_dir,
                model_catalog=model_catalog,
            )
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            print(f"  [警告] Challenger 成本重估失败，尝试显示持久化比较: {exc}")
            try:
                _comparison_path, comparison = load_write_run_comparison(output_dir)
            except (FileNotFoundError, OSError, TypeError, ValueError) as load_exc:
                print(
                    "  [警告] challenger_comparison.json 不可读，已忽略: "
                    f"{load_exc}"
                )
                resolved_comparison = None
            else:
                resolved_comparison = (comparison, False)
        if resolved_comparison is not None:
            comparison, repriced = resolved_comparison
            for line in format_write_run_comparison_report(
                comparison,
                repriced=repriced,
            ):
                print(line)
        if challenger_promotion_proposal_output is not None:
            try:
                promotion_proposal = (
                    build_write_model_challenger_promotion_proposal(
                        output_dir
                    )
                )
                promotion_path = (
                    persist_write_model_challenger_promotion_proposal(
                        promotion_proposal,
                        challenger_promotion_proposal_output,
                    )
                )
            except WriteModelChallengerPromotionBlockedError as exc:
                print(
                    "  [warning] Challenger promotion proposal "
                    f"blocked: {exc}"
                )
                return 4
            except (
                FileExistsError,
                FileNotFoundError,
                OSError,
                TypeError,
                ValueError,
            ) as exc:
                print(
                    "  [warning] Challenger promotion proposal "
                    f"export failed: {exc}"
                )
                return 2
            print(
                "  Challenger promotion proposal receipt: "
                f"{promotion_path}"
            )
            for line in format_write_model_challenger_promotion_report(
                promotion_proposal
            ):
                print(line)
        if challenger_promotion_proposal_input is not None:
            try:
                promotion_path, promotion_receipt = (
                    load_write_model_challenger_promotion_proposal(
                        challenger_promotion_proposal_input
                    )
                )
                promotion_verification = (
                    verify_write_model_challenger_promotion_proposal(
                        promotion_receipt
                    )
                )
            except (
                FileNotFoundError,
                OSError,
                TypeError,
                ValueError,
            ) as exc:
                print(
                    "  [warning] Challenger promotion proposal "
                    f"verification failed: {exc}"
                )
                return 2
            print(
                "  Challenger promotion proposal receipt: "
                f"{promotion_path}"
            )
            for line in (
                format_write_model_challenger_promotion_verification_report(
                    promotion_verification
                )
            ):
                print(line)
            if promotion_verification.get("status") != "current":
                return 4
        if challenger_config_change_request_output is not None:
            if challenger_promotion_proposal_input is None:
                raise ValueError(
                    "challenger_config_change_request_output 已提供，"
                    "但 challenger_promotion_proposal_input 为 None，"
                    "无法构建配置变更请求"
                )
            try:
                config_change_request = (
                    build_write_model_configuration_change_request(
                        challenger_promotion_proposal_input
                    )
                )
                config_change_request_path = (
                    persist_write_model_configuration_change_request(
                        config_change_request,
                        challenger_config_change_request_output,
                    )
                )
            except WriteModelConfigurationChangeBlockedError as exc:
                print(
                    "  [warning] configuration change request blocked: "
                    f"{exc}"
                )
                return 4
            except (
                FileExistsError,
                FileNotFoundError,
                OSError,
                TypeError,
                ValueError,
            ) as exc:
                print(
                    "  [warning] configuration change request export "
                    f"failed: {exc}"
                )
                return 2
            print(
                "  Configuration change request receipt: "
                f"{config_change_request_path}"
            )
            for line in (
                format_write_model_configuration_change_request_report(
                    config_change_request
                )
            ):
                print(line)
        if challenger_config_change_request_input is not None:
            try:
                config_change_request_path, config_change_request = (
                    load_write_model_configuration_change_request(
                        challenger_config_change_request_input
                    )
                )
                config_change_request_verification = (
                    verify_write_model_configuration_change_request(
                        config_change_request
                    )
                )
            except (
                FileNotFoundError,
                OSError,
                TypeError,
                ValueError,
            ) as exc:
                print(
                    "  [warning] configuration change request "
                    f"verification failed: {exc}"
                )
                return 2
            print(
                "  Configuration change request receipt: "
                f"{config_change_request_path}"
            )
            for line in (
                format_write_model_configuration_change_request_verification_report(
                    config_change_request_verification
                )
            ):
                print(line)
            if (
                config_change_request_verification.get("status")
                != "current"
            ):
                return 4
            if config_change_approval_issuance:
                if challenger_config_change_approval_request is None:
                    raise ValueError(
                        "config_change_approval_issuance 为 True，"
                        "但 challenger_config_change_approval_request 为 None，"
                        "无法签发配置变更批准"
                    )
                if challenger_config_change_approval_output is None:
                    raise ValueError(
                        "config_change_approval_issuance 为 True，"
                        "但 challenger_config_change_approval_output 为 None，"
                        "无法持久化配置变更批准"
                    )
                try:
                    approval_request_path, approval_request = (
                        load_write_model_configuration_change_approval_request(
                            challenger_config_change_approval_request
                        )
                    )
                    config_change_approval = (
                        build_write_model_configuration_change_approval(
                            approval_request=approval_request,
                            configuration_change_request_path=(
                                config_change_request_path
                            ),
                            configuration_change_request=(
                                config_change_request
                            ),
                            now=datetime.now(UTC),
                        )
                    )
                    config_change_approval_path = (
                        persist_write_model_configuration_change_approval(
                            config_change_approval,
                            challenger_config_change_approval_output,
                        )
                    )
                except WriteModelConfigurationChangeBlockedError as exc:
                    print(
                        "  [warning] configuration change approval "
                        f"blocked: {exc}"
                    )
                    return 4
                except (
                    FileExistsError,
                    FileNotFoundError,
                    OSError,
                    TypeError,
                    ValueError,
                ) as exc:
                    print(
                        "  [warning] configuration change approval "
                        f"issuance failed: {exc}"
                    )
                    return 2
                print(
                    "  Configuration change approval request: "
                    f"{approval_request_path}"
                )
                print(
                    "  Configuration change approval receipt: "
                    f"{config_change_approval_path}"
                )
                for line in (
                    format_write_model_configuration_change_approval_report(
                        config_change_approval
                    )
                ):
                    print(line)
        if challenger_config_change_approval_input is not None:
            try:
                config_change_approval_path, config_change_approval = (
                    load_write_model_configuration_change_approval(
                        challenger_config_change_approval_input
                    )
                )
                config_change_approval_verification = (
                    verify_write_model_configuration_change_approval(
                        config_change_approval,
                        now=datetime.now(UTC),
                    )
                )
            except (
                FileNotFoundError,
                OSError,
                TypeError,
                ValueError,
            ) as exc:
                print(
                    "  [warning] configuration change approval "
                    f"verification failed: {exc}"
                )
                return 2
            print(
                "  Configuration change approval receipt: "
                f"{config_change_approval_path}"
            )
            for line in (
                format_write_model_configuration_change_approval_verification_report(
                    config_change_approval_verification
                )
            ):
                print(line)
            if config_change_approval_verification.get(
                "status"
            ) != "approved":
                return 4
        if routing_history_root is not None:
            try:
                health_trend = build_write_model_health_trend(
                    routing_history_root,
                    model_catalog=model_catalog,
                )
            except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
                print(f"  [警告] 模型健康趋势不可用: {exc}")
                if proposal_requested:
                    return 2
            else:
                for line in format_write_model_health_report(health_trend):
                    print(line)
                proposal: Mapping[str, object] | None = None
                if proposal_requested:
                    raw_proposal = health_trend.get(
                        "challenger_proposal"
                    )
                    proposal = (
                        raw_proposal
                        if isinstance(raw_proposal, Mapping)
                        else None
                    )
                    if not isinstance(proposal, Mapping):
                        print(
                            "  [警告] 模型健康趋势未生成可用的 "
                            "Challenger 提案"
                        )
                        return 2
                if routing_proposal_output is not None:
                    if proposal is None:
                        raise ValueError(
                            "routing_proposal_output 已提供，"
                            "但 proposal 为 None，"
                            "无法持久化 Challenger 提案"
                        )
                    try:
                        proposal_path = (
                            persist_write_model_challenger_proposal(
                                proposal,
                                routing_proposal_output,
                                overwrite=overwrite_routing_proposal,
                            )
                        )
                    except (
                        FileExistsError,
                        OSError,
                        TypeError,
                        ValueError,
                    ) as exc:
                        print(f"  [警告] Challenger 提案导出失败: {exc}")
                        return 2
                    print(f"  Challenger 提案凭据: {proposal_path}")
                if routing_proposal_input is not None:
                    if proposal is None:
                        raise ValueError(
                            "routing_proposal_input 已提供，"
                            "但 proposal 为 None，"
                            "无法加载 Challenger 提案进行验证"
                        )
                    try:
                        proposal_path, receipt = (
                            load_write_model_challenger_proposal(
                                routing_proposal_input
                            )
                        )
                        verification = (
                            verify_write_model_challenger_proposal(
                                receipt,
                                proposal,
                            )
                        )
                    except (
                        FileNotFoundError,
                        OSError,
                        TypeError,
                        ValueError,
                    ) as exc:
                        print(f"  [警告] Challenger 提案验证失败: {exc}")
                        return 2
                    print(f"  Challenger 提案凭据: {proposal_path}")
                    for line in (
                        format_write_model_challenger_verification_report(
                            verification
                        )
                    ):
                        print(line)
                    if verification.get("status") != "current":
                        return 4
                    if approval_requested:
                        if routing_preflight_approval_request is None:
                            raise ValueError(
                                "approval_requested 为 True，"
                                "但 routing_preflight_approval_request 为 None，"
                                "无法加载预检批准请求"
                            )
                        if routing_preflight_approval_output is None:
                            raise ValueError(
                                "approval_requested 为 True，"
                                "但 routing_preflight_approval_output 为 None，"
                                "无法持久化预检批准"
                            )
                        try:
                            request_path, approval_request = (
                                load_write_model_challenger_preflight_approval_request(
                                    routing_preflight_approval_request
                                )
                            )
                            approval = (
                                build_write_model_challenger_preflight_approval(
                                    request=approval_request,
                                    proposal_receipt=receipt,
                                    current_proposal=proposal,
                                    now=datetime.now(UTC),
                                )
                            )
                            approval_path = (
                                persist_write_model_challenger_preflight_approval(
                                    approval,
                                    routing_preflight_approval_output,
                                )
                            )
                        except WriteModelPreflightApprovalBlockedError as exc:
                            print(
                                "  [warning] Challenger preflight approval "
                                f"blocked: {exc}"
                            )
                            return 4
                        except (
                            FileExistsError,
                            FileNotFoundError,
                            OSError,
                            TypeError,
                            ValueError,
                        ) as exc:
                            print(
                                "  [warning] Challenger preflight approval "
                                f"failed: {exc}"
                            )
                            return 2
                        print(
                            "  Challenger preflight approval request: "
                            f"{request_path}"
                        )
                        print(
                            "  Challenger preflight approval receipt: "
                            f"{approval_path}"
                        )
                        for line in (
                            format_write_model_challenger_preflight_approval_report(
                                approval
                            )
                        ):
                            print(line)
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

