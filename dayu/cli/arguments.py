"""定义 Dayu CLI 参数的运行时类型与命令分派协议。

本模块只依赖 Python 标准库，集中提供 argparse 解析结果的稳定运行时身份，以及
research-template 与 write selector 所需的最小静态字段边界。
"""

from __future__ import annotations

import argparse
from typing import Protocol


class ResearchTemplateDispatchArguments(Protocol):
    """声明 research-template selector 读取的消费方最小字段。"""

    research_template_action: str


class WriteDispatchArguments(Protocol):
    """声明 write 分派 predicate 读取的消费方最小字段。"""

    revalidate_write_model_configuration_manual_recovery_incident_dossier: bool
    inspect_write_model_configuration_manual_recovery_incident: bool
    audit_write_model_configuration_manual_recovery_history: bool
    revalidate_write_model_configuration_manual_recovery_gate_verification: bool
    verify_write_model_configuration_manual_recovery_gate: bool
    check_write_model_configuration_manual_recovery_gate: bool
    revoke_write_model_configuration_manual_recovery_clearance: bool
    restart_write_model_configuration_manual_recovery_after_clearance_revocation: bool
    clear_write_model_configuration_manual_recovery: bool
    verify_write_model_configuration_manual_recovery: bool
    recover_write_model_configuration: bool
    apply_write_model_configuration: bool
    rollback_write_model_configuration: bool
    summary: bool
    preflight_only: bool
    reprice_costs: bool
    challenger_config_manual_recovery_receipt_input: str | None
    challenger_config_manual_recovery_plan_output: str | None
    challenger_config_manual_recovery_approval_output: str | None
    routing_challenger_run_approval_input: str | None


class DayuCliArguments(argparse.Namespace):
    """声明 argparse 写入字段并提供稳定的运行时类型身份。"""

    research_template_action: str
    revalidate_write_model_configuration_manual_recovery_incident_dossier: bool
    inspect_write_model_configuration_manual_recovery_incident: bool
    audit_write_model_configuration_manual_recovery_history: bool
    revalidate_write_model_configuration_manual_recovery_gate_verification: bool
    verify_write_model_configuration_manual_recovery_gate: bool
    check_write_model_configuration_manual_recovery_gate: bool
    revoke_write_model_configuration_manual_recovery_clearance: bool
    restart_write_model_configuration_manual_recovery_after_clearance_revocation: bool
    clear_write_model_configuration_manual_recovery: bool
    verify_write_model_configuration_manual_recovery: bool
    recover_write_model_configuration: bool
    apply_write_model_configuration: bool
    rollback_write_model_configuration: bool
    summary: bool
    preflight_only: bool
    reprice_costs: bool
    challenger_config_manual_recovery_receipt_input: str | None
    challenger_config_manual_recovery_plan_output: str | None
    challenger_config_manual_recovery_approval_output: str | None
    routing_challenger_run_approval_input: str | None
