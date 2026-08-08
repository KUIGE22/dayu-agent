"""写作报告的门禁、导出、验证与健康趋势子流程。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

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


def _validate_print_report_gate_conditions(
    *,
    routing_preflight_approval_request: str | Path | None,
    routing_preflight_approval_output: str | Path | None,
    routing_proposal_input: str | Path | None,
    routing_proposal_output: str | Path | None,
    routing_history_root: str | Path | None,
    challenger_promotion_proposal_input: str | Path | None,
    challenger_promotion_proposal_output: str | Path | None,
    challenger_config_change_request_input: str | Path | None,
    challenger_config_change_request_output: str | Path | None,
    challenger_config_change_approval_request: str | Path | None,
    challenger_config_change_approval_output: str | Path | None,
    challenger_config_change_approval_input: str | Path | None,
) -> int | None:
    """验证报告附加操作的互斥和依赖条件。

    Args:
        routing_preflight_approval_request: 预检批准请求路径。
        routing_preflight_approval_output: 预检批准输出路径。
        routing_proposal_input: Challenger 提案输入路径。
        routing_proposal_output: Challenger 提案输出路径。
        routing_history_root: 模型路由历史目录。
        challenger_promotion_proposal_input: 晋升提案输入路径。
        challenger_promotion_proposal_output: 晋升提案输出路径。
        challenger_config_change_request_input: 配置变更请求输入路径。
        challenger_config_change_request_output: 配置变更请求输出路径。
        challenger_config_change_approval_request: 配置变更批准请求路径。
        challenger_config_change_approval_output: 配置变更批准输出路径。
        challenger_config_change_approval_input: 配置变更批准输入路径。

    Returns:
        校验通过时返回 ``None``；非法组合打印警告并返回 ``2``。

    Raises:
        本函数不显式抛出异常。
    """

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
        print("  [警告] Challenger 提案操作需要提供模型路由历史目录")
        return 2
    if routing_proposal_input is not None and routing_proposal_output is not None:
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
    return None


def _print_repriced_comparison(
    output_dir: str | Path,
    model_catalog: Mapping[str, Mapping[str, object]] | None,
) -> None:
    """打印按当前模型目录重估的运行比较，失败时回退持久化结果。

    Args:
        output_dir: 写作输出目录。
        model_catalog: 可选的当前模型目录。

    Returns:
        无；成本重估或回退读取失败只打印警告并继续。

    Raises:
        底层比较格式化或输出产生且未被本函数捕获的异常。
    """

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


def _handle_promotion_proposal_export(
    output_dir: str | Path,
    challenger_promotion_proposal_output: str | Path | None,
) -> int:
    """按需构建、持久化并打印 Challenger 晋升提案。

    Args:
        output_dir: 写作输出目录。
        challenger_promotion_proposal_output: 晋升提案输出路径。

    Returns:
        未请求或成功时返回 ``0``；输入输出失败返回 ``2``；策略阻断返回 ``4``。

    Raises:
        底层报告格式化或输出产生且未被本函数捕获的异常。
    """

    if challenger_promotion_proposal_output is None:
        return 0
    try:
        promotion_proposal = build_write_model_challenger_promotion_proposal(output_dir)
        promotion_path = persist_write_model_challenger_promotion_proposal(
            promotion_proposal,
            challenger_promotion_proposal_output,
        )
    except WriteModelChallengerPromotionBlockedError as exc:
        print("  [warning] Challenger promotion proposal " f"blocked: {exc}")
        return 4
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print("  [warning] Challenger promotion proposal " f"export failed: {exc}")
        return 2
    print("  Challenger promotion proposal receipt: " f"{promotion_path}")
    for line in format_write_model_challenger_promotion_report(promotion_proposal):
        print(line)
    return 0


def _handle_promotion_proposal_verification(
    challenger_promotion_proposal_input: str | Path | None,
) -> int:
    """按需加载、验证并打印 Challenger 晋升提案。

    Args:
        challenger_promotion_proposal_input: 晋升提案输入路径。

    Returns:
        未请求或当前有效时返回 ``0``；读取验证失败返回 ``2``；状态失效返回 ``4``。

    Raises:
        底层报告格式化或输出产生且未被本函数捕获的异常。
    """

    if challenger_promotion_proposal_input is None:
        return 0
    try:
        promotion_path, promotion_receipt = (
            load_write_model_challenger_promotion_proposal(
                challenger_promotion_proposal_input
            )
        )
        promotion_verification = verify_write_model_challenger_promotion_proposal(
            promotion_receipt
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        print(
            "  [warning] Challenger promotion proposal "
            f"verification failed: {exc}"
        )
        return 2
    print("  Challenger promotion proposal receipt: " f"{promotion_path}")
    for line in format_write_model_challenger_promotion_verification_report(
        promotion_verification
    ):
        print(line)
    if promotion_verification.get("status") != "current":
        return 4
    return 0


def _handle_config_change_request_export(
    challenger_config_change_request_output: str | Path | None,
    challenger_promotion_proposal_input: str | Path | None,
) -> int:
    """按需从已验证的晋升提案导出配置变更请求。

    Args:
        challenger_config_change_request_output: 配置变更请求输出路径。
        challenger_promotion_proposal_input: 晋升提案输入路径。

    Returns:
        未请求或成功时返回 ``0``；输入输出失败返回 ``2``；策略阻断返回 ``4``。

    Raises:
        ValueError: 已请求导出但缺少晋升提案输入。
        其他底层报告格式化或输出产生且未被本函数捕获的异常。
    """

    if challenger_config_change_request_output is None:
        return 0
    if challenger_promotion_proposal_input is None:
        raise ValueError(
            "challenger_config_change_request_output 已提供，"
            "但 challenger_promotion_proposal_input 为 None，"
            "无法构建配置变更请求"
        )
    try:
        config_change_request = build_write_model_configuration_change_request(
            challenger_promotion_proposal_input
        )
        config_change_request_path = persist_write_model_configuration_change_request(
            config_change_request,
            challenger_config_change_request_output,
        )
    except WriteModelConfigurationChangeBlockedError as exc:
        print("  [warning] configuration change request blocked: " f"{exc}")
        return 4
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print("  [warning] configuration change request export " f"failed: {exc}")
        return 2
    print("  Configuration change request receipt: " f"{config_change_request_path}")
    for line in format_write_model_configuration_change_request_report(
        config_change_request
    ):
        print(line)
    return 0


def _handle_config_change_request_verification(
    challenger_config_change_request_input: str | Path | None,
) -> int:
    """按需加载、验证并打印配置变更请求。

    Args:
        challenger_config_change_request_input: 配置变更请求输入路径。

    Returns:
        未请求或当前有效时返回 ``0``；读取验证失败返回 ``2``；状态失效返回 ``4``。

    Raises:
        底层报告格式化或输出产生且未被本函数捕获的异常。
    """

    if challenger_config_change_request_input is None:
        return 0
    try:
        config_change_request_path, config_change_request = (
            load_write_model_configuration_change_request(
                challenger_config_change_request_input
            )
        )
        config_change_request_verification = (
            verify_write_model_configuration_change_request(config_change_request)
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        print(
            "  [warning] configuration change request "
            f"verification failed: {exc}"
        )
        return 2
    print("  Configuration change request receipt: " f"{config_change_request_path}")
    for line in format_write_model_configuration_change_request_verification_report(
        config_change_request_verification
    ):
        print(line)
    if config_change_request_verification.get("status") != "current":
        return 4
    return 0


def _handle_config_change_approval(
    challenger_config_change_approval_request: str | Path | None,
    challenger_config_change_approval_output: str | Path | None,
    challenger_config_change_approval_input: str | Path | None,
    challenger_config_change_request_input: str | Path | None,
) -> int:
    """按需签发或验证配置变更批准。

    Args:
        challenger_config_change_approval_request: 人工批准请求路径。
        challenger_config_change_approval_output: 签发批准输出路径。
        challenger_config_change_approval_input: 待验证批准输入路径。
        challenger_config_change_request_input: 配置变更请求输入路径。

    Returns:
        未请求或批准有效时返回 ``0``；读取验证失败返回 ``2``；策略或状态阻断返回
        ``4``。

    Raises:
        ValueError: 批准签发参数不满足已通过门禁的内部不变量。
        其他底层报告格式化或输出产生且未被本函数捕获的异常。
    """

    config_change_approval_issuance = (
        challenger_config_change_approval_request is not None
        or challenger_config_change_approval_output is not None
    )
    if config_change_approval_issuance:
        if challenger_config_change_request_input is None:
            raise ValueError(
                "config_change_approval_issuance 为 True，"
                "但 challenger_config_change_request_input 为 None，"
                "无法签发配置变更批准"
            )
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
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
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
        if config_change_request_verification.get("status") != "current":
            return 4
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
            config_change_approval = build_write_model_configuration_change_approval(
                approval_request=approval_request,
                configuration_change_request_path=config_change_request_path,
                configuration_change_request=config_change_request,
                now=datetime.now(UTC),
            )
            config_change_approval_path = (
                persist_write_model_configuration_change_approval(
                    config_change_approval,
                    challenger_config_change_approval_output,
                )
            )
        except WriteModelConfigurationChangeBlockedError as exc:
            print("  [warning] configuration change approval " f"blocked: {exc}")
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
        print("  Configuration change approval request: " f"{approval_request_path}")
        print("  Configuration change approval receipt: " f"{config_change_approval_path}")
        for line in format_write_model_configuration_change_approval_report(
            config_change_approval
        ):
            print(line)
    if challenger_config_change_approval_input is None:
        return 0
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
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        print(
            "  [warning] configuration change approval "
            f"verification failed: {exc}"
        )
        return 2
    print("  Configuration change approval receipt: " f"{config_change_approval_path}")
    for line in format_write_model_configuration_change_approval_verification_report(
        config_change_approval_verification
    ):
        print(line)
    if config_change_approval_verification.get("status") != "approved":
        return 4
    return 0


def _handle_health_trend_and_proposal_and_preflight(
    output_dir: str | Path,
    routing_history_root: str | Path | None,
    model_catalog: Mapping[str, Mapping[str, object]] | None,
    routing_proposal_output: str | Path | None,
    routing_proposal_input: str | Path | None,
    overwrite_routing_proposal: bool,
    routing_preflight_approval_request: str | Path | None,
    routing_preflight_approval_output: str | Path | None,
) -> int:
    """处理健康趋势、Challenger 提案及预检批准。

    Args:
        output_dir: 写作输出目录。
        routing_history_root: 模型路由历史目录。
        model_catalog: 可选的当前模型目录。
        routing_proposal_output: Challenger 提案输出路径。
        routing_proposal_input: Challenger 提案输入路径。
        overwrite_routing_proposal: 是否覆盖既有提案输出。
        routing_preflight_approval_request: 预检批准请求路径。
        routing_preflight_approval_output: 预检批准输出路径。

    Returns:
        未请求或成功时返回 ``0``；输入输出失败返回 ``2``；策略或状态阻断返回 ``4``。

    Raises:
        ValueError: 已通过门禁的提案或批准参数缺少内部必需值。
        其他底层报告格式化或输出产生且未被本函数捕获的异常。
    """

    approval_requested = (
        routing_preflight_approval_request is not None
        or routing_preflight_approval_output is not None
    )
    proposal_requested = (
        routing_proposal_input is not None
        or routing_proposal_output is not None
        or approval_requested
    )
    if routing_history_root is None:
        return 0
    try:
        health_trend = build_write_model_health_trend(
            routing_history_root,
            model_catalog=model_catalog,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        print(f"  [警告] 模型健康趋势不可用: {exc}")
        if proposal_requested:
            return 2
        return 0
    for line in format_write_model_health_report(health_trend):
        print(line)
    proposal: Mapping[str, object] | None = None
    if proposal_requested:
        raw_proposal = health_trend.get("challenger_proposal")
        proposal = raw_proposal if isinstance(raw_proposal, Mapping) else None
        if not isinstance(proposal, Mapping):
            print("  [警告] 模型健康趋势未生成可用的 Challenger 提案")
            return 2
    if routing_proposal_output is not None:
        if proposal is None:
            raise ValueError(
                "routing_proposal_output 已提供，"
                "但 proposal 为 None，"
                "无法持久化 Challenger 提案"
            )
        try:
            proposal_path = persist_write_model_challenger_proposal(
                proposal,
                routing_proposal_output,
                overwrite=overwrite_routing_proposal,
            )
        except (FileExistsError, OSError, TypeError, ValueError) as exc:
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
            proposal_path, receipt = load_write_model_challenger_proposal(
                routing_proposal_input
            )
            verification = verify_write_model_challenger_proposal(
                receipt,
                proposal,
            )
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            print(f"  [警告] Challenger 提案验证失败: {exc}")
            return 2
        print(f"  Challenger 提案凭据: {proposal_path}")
        for line in format_write_model_challenger_verification_report(verification):
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
                approval = build_write_model_challenger_preflight_approval(
                    request=approval_request,
                    proposal_receipt=receipt,
                    current_proposal=proposal,
                    now=datetime.now(UTC),
                )
                approval_path = persist_write_model_challenger_preflight_approval(
                    approval,
                    routing_preflight_approval_output,
                )
            except WriteModelPreflightApprovalBlockedError as exc:
                print("  [warning] Challenger preflight approval " f"blocked: {exc}")
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
            print("  Challenger preflight approval request: " f"{request_path}")
            print("  Challenger preflight approval receipt: " f"{approval_path}")
            for line in format_write_model_challenger_preflight_approval_report(
                approval
            ):
                print(line)
    return 0
