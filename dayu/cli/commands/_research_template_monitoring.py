"""提供研究模板的监控计划、状态与调度清单操作。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dayu.cli.commands._research_template_bundle import inspect_research_template_bundle
from dayu.cli.commands._research_template_core import validate_monitoring_source_map_payload
from dayu.cli.commands._research_template_helpers import (
    _TEMPLATE_DIR_NAME,
    _as_str_list,
    _discover_research_artifact_paths,
    _identifier_component,
    _load_json_object,
    _normalize_research_target,
    _scheduler_state_from_plan_inspection,
    _sha256_file,
)


def build_monitoring_execution_plan(bundle_path: Path) -> dict[str, object]:
    """从健康 Bundle 的规则与 source-map 构建禁用自动执行的 dry-run 监控计划。

    Args:
        bundle_path: 用于生成监控计划的 Bundle 描述符路径。

    Returns:
        包含研究目标、输入指纹、readiness 和逐变量监控任务的计划载荷。

    Raises:
        OSError: 当 Bundle、规则、source-map 或引用产物无法读取或计算指纹时。
        ValueError: 当 Bundle 不健康、产物映射无效或规则/source-map 不一致时。
    """

    resolved_bundle_path = bundle_path.resolve()
    inspection = inspect_research_template_bundle(resolved_bundle_path)
    bundle_validation = inspection.get("validation")
    if not isinstance(bundle_validation, dict) or bundle_validation.get("ok") is not True:
        errors = bundle_validation.get("errors", []) if isinstance(bundle_validation, dict) else []
        detail = "; ".join(_as_str_list(errors)) or "bundle validation failed"
        raise ValueError(f"cannot build monitoring plan from unhealthy bundle: {detail}")

    bundle_payload = _load_json_object(resolved_bundle_path)
    artifacts = bundle_payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("bundle artifacts must be an object")
    rules_path = Path(str(artifacts["monitoring_rules"])).resolve()
    source_map_path = Path(str(artifacts["source_map"])).resolve()
    rules_payload = _load_json_object(rules_path)
    source_map_payload = _load_json_object(source_map_path)
    source_validation = validate_monitoring_source_map_payload(rules_payload, source_map_payload)
    if source_validation.get("ok") is not True:
        detail = "; ".join(_as_str_list(source_validation.get("errors"))) or "source-map validation failed"
        raise ValueError(f"cannot build monitoring plan: {detail}")

    sources_by_name: dict[str, dict[str, object]] = {}
    data_sources = source_map_payload.get("data_sources", [])
    if isinstance(data_sources, list):
        for source in data_sources:
            if not isinstance(source, dict):
                continue
            source_name = str(source.get("source", "") or "")
            if source_name:
                sources_by_name[source_name] = source

    template = str(bundle_payload.get("template", "") or "")
    research_target = bundle_payload.get("research_target")
    if not isinstance(research_target, dict):
        research_target = {}
    target = _normalize_research_target(
        ticker=str(research_target.get("ticker", "") or ""),
        company=str(research_target.get("company", "") or ""),
    )
    task_prefix = _identifier_component(target["ticker"])
    task_namespace = f"{task_prefix}-{template}" if task_prefix else template
    tasks: list[dict[str, object]] = []
    variables = rules_payload.get("variables", [])
    if isinstance(variables, list):
        for index, variable in enumerate(variables, start=1):
            if not isinstance(variable, dict):
                continue
            candidates = _as_str_list(variable.get("data_source_candidates"))
            bound_sources = [
                source_name
                for source_name in candidates
                if sources_by_name.get(source_name, {}).get("binding_status") == "bound"
            ]
            task_status = "ready_for_review" if bound_sources else "blocked_unbound_sources"
            tasks.append(
                {
                    "task_id": f"{task_namespace}-monitor-{index:03d}",
                    "variable": str(variable.get("name", "") or ""),
                    "status": task_status,
                    "evidence_required": bool(variable.get("evidence_required", True)),
                    "data_source_candidates": candidates,
                    "bound_data_sources": bound_sources,
                    "blocking_reasons": [] if bound_sources else ["no candidate data source is bound"],
                }
            )

    ready_task_count = sum(task.get("status") == "ready_for_review" for task in tasks)
    blocked_task_count = len(tasks) - ready_task_count
    if not tasks:
        readiness_status = "blocked_no_tasks"
        blocking_reasons = ["monitoring rules contain no variables"]
    elif blocked_task_count:
        readiness_status = "blocked_unbound_sources"
        blocking_reasons = [f"{blocked_task_count} monitoring tasks have no bound data source"]
    else:
        readiness_status = "ready_for_review"
        blocking_reasons = []

    return {
        "schema_version": 1,
        "plan_type": "research_monitoring_execution_plan",
        "template": template,
        "research_target": target,
        "bundle_file": str(resolved_bundle_path),
        "execution_mode": "dry_run",
        "cadence": str(rules_payload.get("cadence", "") or ""),
        "automated_execution_allowed": False,
        "input_files": {
            "monitoring_rules": str(rules_path),
            "source_map": str(source_map_path),
        },
        "input_fingerprints": {
            "monitoring_rules": _sha256_file(rules_path),
            "source_map": _sha256_file(source_map_path),
        },
        "readiness": {
            "status": readiness_status,
            "task_count": len(tasks),
            "ready_task_count": ready_task_count,
            "blocked_task_count": blocked_task_count,
            "blocking_reasons": blocking_reasons,
        },
        "source_validation": source_validation,
        "tasks": tasks,
    }


def validate_monitoring_execution_plan(payload: dict[str, object]) -> dict[str, object]:
    """校验监控计划 schema、安全开关、输入指纹、任务唯一性与真实绑定状态。

    Args:
        payload: 待验证的监控执行计划或调度清单载荷。

    Returns:
        包含 ``ok``、错误、警告、readiness 状态和任务计数的验证结果。

    Raises:
        OSError: 当存在的规则或 source-map 文件无法读取或计算指纹时。
    """

    errors: list[str] = []
    warnings: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if payload.get("plan_type") != "research_monitoring_execution_plan":
        errors.append("plan_type must be research_monitoring_execution_plan")
    if payload.get("execution_mode") != "dry_run":
        errors.append("execution_mode must be dry_run")
    if payload.get("automated_execution_allowed") is not False:
        errors.append("automated_execution_allowed must be false")

    template = str(payload.get("template", "") or "")
    if not template:
        errors.append("template is required")
    research_target = payload.get("research_target")
    if not isinstance(research_target, dict):
        errors.append("research_target must be an object")
    else:
        for key in ("ticker", "company"):
            if not isinstance(research_target.get(key), str):
                errors.append(f"research_target.{key} must be a string")
    bundle_file = str(payload.get("bundle_file", "") or "")
    if not bundle_file:
        errors.append("bundle_file is required")
    elif not Path(bundle_file).is_file():
        errors.append(f"bundle_file does not exist: {bundle_file}")

    input_files = payload.get("input_files")
    fingerprints = payload.get("input_fingerprints")
    if not isinstance(input_files, dict):
        errors.append("input_files must be an object")
        input_files = {}
    if not isinstance(fingerprints, dict):
        errors.append("input_fingerprints must be an object")
        fingerprints = {}
    for key in ("monitoring_rules", "source_map"):
        path_raw = input_files.get(key)
        fingerprint_raw = fingerprints.get(key)
        if not isinstance(path_raw, str) or not path_raw.strip():
            errors.append(f"input_files.{key} must be a non-empty path")
            continue
        path = Path(path_raw)
        if not path.is_file():
            errors.append(f"input_files.{key} does not exist: {path_raw}")
            continue
        if not isinstance(fingerprint_raw, str) or len(fingerprint_raw) != 64:
            errors.append(f"input_fingerprints.{key} must be a SHA-256 hex digest")
        elif _sha256_file(path) != fingerprint_raw:
            errors.append(f"input_files.{key} changed after plan generation")

    # Recompute the genuinely-bound source names from the authentic source-map so
    # a plan cannot claim a task is ready_for_review (or that an unbindable
    # external placeholder is bound) that the source-map does not actually
    # support. Only enforced when the source-map is present and its fingerprint
    # matches (i.e. the plan's declared inputs are authentic); a
    # missing/changed source-map is already reported above.
    genuinely_bound_sources: set[str] | None = None
    source_map_raw = input_files.get("source_map")
    source_map_fp = fingerprints.get("source_map")
    if (
        isinstance(source_map_raw, str)
        and source_map_raw.strip()
        and Path(source_map_raw).is_file()
        and isinstance(source_map_fp, str)
        and len(source_map_fp) == 64
        and _sha256_file(Path(source_map_raw)) == source_map_fp
    ):
        try:
            source_map_payload = _load_json_object(Path(source_map_raw))
        except (OSError, ValueError):
            source_map_payload = {}
        genuinely_bound_sources = set()
        data_sources = source_map_payload.get("data_sources")
        if isinstance(data_sources, list):
            for source in data_sources:
                if not isinstance(source, dict):
                    continue
                if str(source.get("binding_status", "") or "") != "bound":
                    continue
                source_name = str(source.get("source", "") or "")
                if source_name:
                    genuinely_bound_sources.add(source_name)

    task_statuses: list[str] = []
    task_ids: set[str] = set()
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        errors.append("tasks must be a list")
        tasks = []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"tasks[{index}] must be an object")
            continue
        task_id = str(task.get("task_id", "") or "")
        if not task_id:
            errors.append(f"tasks[{index}].task_id is required")
        elif task_id in task_ids:
            errors.append(f"duplicate task_id: {task_id}")
        task_ids.add(task_id)
        status = str(task.get("status", "") or "")
        if status not in {"ready_for_review", "blocked_unbound_sources"}:
            errors.append(f"tasks[{index}].status is invalid: {status!r}")
        task_statuses.append(status)
        bound_sources = _as_str_list(task.get("bound_data_sources"))
        if status == "ready_for_review" and not bound_sources:
            errors.append(f"tasks[{index}] is ready_for_review without a bound data source")
        if status == "blocked_unbound_sources" and bound_sources:
            errors.append(f"tasks[{index}] is blocked despite having a bound data source")
        if genuinely_bound_sources is not None:
            forged = [source for source in bound_sources if source not in genuinely_bound_sources]
            if forged:
                errors.append(
                    f"tasks[{index}] claims bound data sources not bound in the source-map: {', '.join(sorted(forged))}"
                )
            candidates = _as_str_list(task.get("data_source_candidates"))
            expected_bound = sorted(source for source in candidates if source in genuinely_bound_sources)
            if status == "ready_for_review" and not expected_bound:
                errors.append(
                    f"tasks[{index}] is ready_for_review but no candidate data source is bound in the source-map"
                )

    ready_count = sum(status == "ready_for_review" for status in task_statuses)
    blocked_count = sum(status == "blocked_unbound_sources" for status in task_statuses)
    readiness = payload.get("readiness")
    if not isinstance(readiness, dict):
        errors.append("readiness must be an object")
    else:
        expected_status = (
            "blocked_no_tasks" if not tasks else "blocked_unbound_sources" if blocked_count else "ready_for_review"
        )
        if readiness.get("status") != expected_status:
            errors.append(f"readiness.status must be {expected_status}")
        expected_counts = {
            "task_count": len(tasks),
            "ready_task_count": ready_count,
            "blocked_task_count": blocked_count,
        }
        for key, expected in expected_counts.items():
            if readiness.get(key) != expected:
                errors.append(f"readiness.{key} must be {expected}")

    source_validation = payload.get("source_validation")
    if not isinstance(source_validation, dict) or source_validation.get("ok") is not True:
        errors.append("source_validation.ok must be true")

    return {
        "ok": not errors,
        "template": template,
        "errors": errors,
        "warnings": warnings,
        "task_count": len(tasks),
        "ready_task_count": ready_count,
        "blocked_task_count": blocked_count,
    }


def inspect_monitoring_execution_plan(plan_path: Path) -> dict[str, object]:
    """读取一个持久化监控计划并验证其输入新鲜度与安全约束。

    Args:
        plan_path: 待检查的持久化监控执行计划路径。

    Returns:
        包含计划路径、模板、研究目标、readiness 与验证报告的检查结果。

    Raises:
        OSError: 当计划引用的存在文件无法读取并计算指纹时。
    """

    resolved_path = plan_path.resolve()
    try:
        payload = _load_json_object(resolved_path)
    except (OSError, ValueError) as exc:
        return {
            "monitoring_plan_file": str(resolved_path),
            "validation": {
                "ok": False,
                "template": "",
                "errors": [f"unable to load monitoring plan: {exc}"],
                "warnings": [],
                "task_count": 0,
                "ready_task_count": 0,
                "blocked_task_count": 0,
            },
        }
    return {
        "monitoring_plan_file": str(resolved_path),
        "template": str(payload.get("template", "") or ""),
        "research_target": payload.get("research_target", {}),
        "cadence": str(payload.get("cadence", "") or ""),
        "execution_mode": str(payload.get("execution_mode", "") or ""),
        "readiness": payload.get("readiness", {}),
        "validation": validate_monitoring_execution_plan(payload),
    }


def discover_monitoring_execution_plans(
    workspace_root: Path,
    *,
    recursive: bool = False,
) -> tuple[dict[str, object], ...]:
    """发现标准工作区中的监控计划，并逐个生成容错检查结果。

    Args:
        workspace_root: 包含标准模板 assets 目录的研究工作区根目录。
        recursive: 是否递归包含 ticker 等子工作区。

    Returns:
        按路径排序的监控计划检查结果元组。

    Raises:
        OSError: 当工作区 glob 遍历或计划引用文件指纹计算失败时。
    """

    paths = _discover_research_artifact_paths(workspace_root, "*.monitoring-plan.json", recursive=recursive)
    return tuple(inspect_monitoring_execution_plan(path) for path in paths)


def build_monitoring_status_snapshot(workspace_root: Path, *, recursive: bool = False) -> dict[str, object]:
    """聚合工作区内监控计划状态，并按无效、阻塞和待复核优先级生成快照。

    Args:
        workspace_root: 包含标准模板 assets 目录的研究工作区根目录。
        recursive: 是否递归包含 ticker 等子工作区。

    Returns:
        包含总体状态、各状态计数、目标摘要和计划详情的确定性快照。

    Raises:
        OSError: 当工作区遍历或计划引用文件无法读取时。
    """

    resolved_workspace = workspace_root.resolve()
    plans = discover_monitoring_execution_plans(resolved_workspace, recursive=recursive)
    valid_count = 0
    invalid_count = 0
    ready_plan_count = 0
    blocked_plan_count = 0
    task_count = 0
    ready_task_count = 0
    blocked_task_count = 0
    targeted_plan_count = 0
    untargeted_plan_count = 0
    target_companies: dict[str, str] = {}
    target_counters: dict[str, dict[str, int]] = {}
    for plan in plans:
        research_target = plan.get("research_target")
        ticker = str(research_target.get("ticker", "") or "") if isinstance(research_target, dict) else ""
        company = str(research_target.get("company", "") or "") if isinstance(research_target, dict) else ""
        target_counter: dict[str, int] | None = None
        if ticker:
            targeted_plan_count += 1
            target_companies.setdefault(ticker, company)
            target_counter = target_counters.setdefault(
                ticker,
                {
                    "plan_count": 0,
                    "valid_plan_count": 0,
                    "invalid_plan_count": 0,
                    "ready_for_review_plan_count": 0,
                    "blocked_plan_count": 0,
                },
            )
            target_counter["plan_count"] += 1
        else:
            untargeted_plan_count += 1
        validation = plan.get("validation")
        if not isinstance(validation, dict) or validation.get("ok") is not True:
            invalid_count += 1
            if target_counter is not None:
                target_counter["invalid_plan_count"] += 1
            continue
        valid_count += 1
        if target_counter is not None:
            target_counter["valid_plan_count"] += 1
        readiness = plan.get("readiness")
        readiness_status = str(readiness.get("status", "") or "") if isinstance(readiness, dict) else ""
        if readiness_status == "ready_for_review":
            ready_plan_count += 1
            if target_counter is not None:
                target_counter["ready_for_review_plan_count"] += 1
        else:
            blocked_plan_count += 1
            if target_counter is not None:
                target_counter["blocked_plan_count"] += 1
        task_count += int(validation.get("task_count", 0) or 0)
        ready_task_count += int(validation.get("ready_task_count", 0) or 0)
        blocked_task_count += int(validation.get("blocked_task_count", 0) or 0)

    if not plans:
        overall_status = "no_plans"
    elif invalid_count:
        overall_status = "unhealthy"
    elif blocked_plan_count:
        overall_status = "blocked"
    else:
        overall_status = "ready_for_review"
    targets = []
    for ticker in sorted(target_counters):
        counters = target_counters[ticker]
        if counters["invalid_plan_count"]:
            target_status = "unhealthy"
        elif counters["blocked_plan_count"]:
            target_status = "blocked"
        else:
            target_status = "ready_for_review"
        targets.append(
            {
                "ticker": ticker,
                "company": target_companies[ticker],
                "overall_status": target_status,
                **counters,
            }
        )
    return {
        "schema_version": 1,
        "snapshot_type": "research_monitoring_status",
        "workspace_root": str(resolved_workspace),
        "scan_scope": "recursive" if recursive else "workspace",
        "overall_status": overall_status,
        "summary": {
            "plan_count": len(plans),
            "valid_plan_count": valid_count,
            "invalid_plan_count": invalid_count,
            "ready_for_review_plan_count": ready_plan_count,
            "blocked_plan_count": blocked_plan_count,
            "task_count": task_count,
            "ready_task_count": ready_task_count,
            "blocked_task_count": blocked_task_count,
            "targeted_plan_count": targeted_plan_count,
            "untargeted_plan_count": untargeted_plan_count,
            "target_count": len(targets),
        },
        "targets": targets,
        "plans": list(plans),
    }


def write_monitoring_status_snapshot(
    workspace_root: Path,
    *,
    output_path: Path | None = None,
    recursive: bool = False,
    overwrite: bool = False,
) -> Path:
    """构建并写入工作区级 monitoring-status JSON 快照。

    Args:
        workspace_root: 包含标准模板 assets 目录的研究工作区根目录。
        output_path: 可选自定义输出路径；为空时使用标准 monitoring 文件名。
        recursive: 是否递归包含 ticker 等子工作区。
        overwrite: 目标文件存在时是否允许覆盖。

    Returns:
        实际写入的状态快照绝对路径。

    Raises:
        FileExistsError: 当目标已存在且 ``overwrite`` 为 false 时。
        OSError: 当工作区遍历、目录创建或快照文件写入失败时。
    """

    resolved_workspace = workspace_root.resolve()
    payload = build_monitoring_status_snapshot(resolved_workspace, recursive=recursive)
    target_path = output_path or resolved_workspace / "assets" / _TEMPLATE_DIR_NAME / "monitoring-status.json"
    target_path = target_path.resolve()
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"{target_path} already exists; pass --overwrite to replace it")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target_path


def build_monitoring_scheduler_manifest(
    workspace_root: Path,
    *,
    recursive: bool = False,
    timezone: str = "UTC",
) -> dict[str, object]:
    """把已发现监控计划转换为平台无关、默认禁用的调度作业清单。

    Args:
        workspace_root: 包含标准模板 assets 目录的研究工作区根目录。
        recursive: 是否递归包含 ticker 等子工作区。
        timezone: 写入调度清单的非空时区标识。

    Returns:
        包含 timezone、禁用作业、状态计数和安全摘要的调度 manifest。

    Raises:
        ValueError: 当 timezone 为空时。
        OSError: 当工作区遍历、计划检查或计划文件指纹计算失败时。
    """

    resolved_workspace = workspace_root.resolve()
    normalized_timezone = timezone.strip()
    if not normalized_timezone:
        raise ValueError("scheduler timezone is required")
    plans = discover_monitoring_execution_plans(resolved_workspace, recursive=recursive)
    jobs: list[dict[str, object]] = []
    seen_job_ids: set[str] = set()
    invalid_count = 0
    blocked_count = 0
    ready_count = 0
    for plan in plans:
        plan_path = Path(str(plan["monitoring_plan_file"])).resolve()
        validation = plan.get("validation")
        is_valid = isinstance(validation, dict) and validation.get("ok") is True
        readiness = plan.get("readiness")
        readiness_status = str(readiness.get("status", "") or "") if isinstance(readiness, dict) else ""
        if not is_valid:
            state = "invalid_plan"
            invalid_count += 1
        elif readiness_status == "ready_for_review":
            state = "ready_for_review"
            ready_count += 1
        else:
            state = readiness_status or "blocked_unknown"
            blocked_count += 1
        research_target = plan.get("research_target")
        target = (
            _normalize_research_target(
                ticker=str(research_target.get("ticker", "") or ""),
                company=str(research_target.get("company", "") or ""),
            )
            if isinstance(research_target, dict)
            else {"ticker": "", "company": ""}
        )
        template = str(plan.get("template", "") or "unknown")
        namespace = _identifier_component(target["ticker"] or template) or "unknown"
        candidate_job_id = f"{namespace}-{template}-monitoring"
        job_id = candidate_job_id
        if job_id in seen_job_ids:
            path_suffix = hashlib.sha256(str(plan_path).encode("utf-8")).hexdigest()[:8]
            job_id = f"{candidate_job_id}-{path_suffix}"
        seen_job_ids.add(job_id)
        cadence = str(plan.get("cadence", "") or "manual")
        jobs.append(
            {
                "job_id": job_id,
                "enabled": False,
                "eligible_for_manual_activation": state == "ready_for_review",
                "state": state,
                "research_target": target,
                "template": template,
                "monitoring_plan_file": str(plan_path),
                "monitoring_plan_fingerprint": _sha256_file(plan_path) if plan_path.is_file() else "",
                "trigger": {
                    "type": "cadence",
                    "cadence": cadence,
                    "timezone": normalized_timezone,
                    "binding_status": "unbound",
                },
                "action": {
                    "type": "command_argv",
                    "argv": [
                        "dayu-cli",
                        "research-template",
                        "validate-monitoring-plan",
                        "--plan",
                        str(plan_path),
                    ],
                },
            }
        )
    return {
        "schema_version": 1,
        "manifest_type": "research_monitoring_scheduler",
        "workspace_root": str(resolved_workspace),
        "scan_scope": "recursive" if recursive else "workspace",
        "timezone": normalized_timezone,
        "activation_policy": {
            "manual_approval_required": True,
            "automated_provider_execution_allowed": False,
            "scheduler_binding_status": "unbound",
        },
        "summary": {
            "job_count": len(jobs),
            "enabled_job_count": 0,
            "manual_activation_candidate_count": ready_count,
            "ready_for_review_job_count": ready_count,
            "blocked_job_count": blocked_count,
            "invalid_job_count": invalid_count,
        },
        "jobs": jobs,
    }


def validate_monitoring_scheduler_manifest(payload: dict[str, object]) -> dict[str, object]:
    """校验调度清单的禁用安全约束、作业唯一性和引用计划新鲜度。

    Args:
        payload: 待验证的监控执行计划或调度清单载荷。

    Returns:
        包含 ``ok``、错误、警告与作业状态计数的验证结果。

    Raises:
        OSError: 当引用计划存在但无法读取或计算 SHA-256 时。
    """

    errors: list[str] = []
    warnings: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if payload.get("manifest_type") != "research_monitoring_scheduler":
        errors.append("manifest_type must be research_monitoring_scheduler")
    timezone = str(payload.get("timezone", "") or "")
    if not timezone:
        errors.append("timezone is required")

    policy = payload.get("activation_policy")
    if not isinstance(policy, dict):
        errors.append("activation_policy must be an object")
    else:
        if policy.get("manual_approval_required") is not True:
            errors.append("activation_policy.manual_approval_required must be true")
        if policy.get("automated_provider_execution_allowed") is not False:
            errors.append("activation_policy.automated_provider_execution_allowed must be false")
        if policy.get("scheduler_binding_status") != "unbound":
            errors.append("activation_policy.scheduler_binding_status must be unbound")

    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        errors.append("jobs must be a list")
        jobs = []
    seen_job_ids: set[str] = set()
    enabled_count = 0
    ready_count = 0
    blocked_count = 0
    invalid_count = 0
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            errors.append(f"jobs[{index}] must be an object")
            continue
        job_id = str(job.get("job_id", "") or "")
        if not job_id:
            errors.append(f"jobs[{index}].job_id is required")
        elif job_id in seen_job_ids:
            errors.append(f"duplicate job_id: {job_id}")
        seen_job_ids.add(job_id)
        if job.get("enabled") is not False:
            errors.append(f"jobs[{index}].enabled must be false")
            enabled_count += 1

        state = str(job.get("state", "") or "")
        if state == "ready_for_review":
            ready_count += 1
        elif state == "invalid_plan":
            invalid_count += 1
        else:
            blocked_count += 1
        expected_eligibility = state == "ready_for_review"
        if job.get("eligible_for_manual_activation") is not expected_eligibility:
            errors.append(f"jobs[{index}].eligible_for_manual_activation must be {str(expected_eligibility).lower()}")

        plan_raw = job.get("monitoring_plan_file")
        plan_path: Path | None = None
        if not isinstance(plan_raw, str) or not plan_raw.strip():
            errors.append(f"jobs[{index}].monitoring_plan_file must be a non-empty path")
        else:
            plan_path = Path(plan_raw)
            if not plan_path.is_file():
                errors.append(f"jobs[{index}].monitoring_plan_file does not exist: {plan_raw}")
            else:
                fingerprint = job.get("monitoring_plan_fingerprint")
                if not isinstance(fingerprint, str) or len(fingerprint) != 64:
                    errors.append(f"jobs[{index}].monitoring_plan_fingerprint must be a SHA-256 hex digest")
                elif _sha256_file(plan_path) != fingerprint:
                    errors.append(f"jobs[{index}].monitoring_plan_file changed after scheduler export")
                inspection = inspect_monitoring_execution_plan(plan_path)
                expected_state = _scheduler_state_from_plan_inspection(inspection)
                if state != expected_state:
                    errors.append(f"jobs[{index}].state must be {expected_state}")
                if str(job.get("template", "") or "") != str(inspection.get("template", "") or ""):
                    errors.append(f"jobs[{index}].template does not match monitoring plan")

        trigger = job.get("trigger")
        if not isinstance(trigger, dict):
            errors.append(f"jobs[{index}].trigger must be an object")
        else:
            if trigger.get("type") != "cadence":
                errors.append(f"jobs[{index}].trigger.type must be cadence")
            if not str(trigger.get("cadence", "") or ""):
                errors.append(f"jobs[{index}].trigger.cadence is required")
            if trigger.get("timezone") != timezone:
                errors.append(f"jobs[{index}].trigger.timezone must match manifest timezone")
            if trigger.get("binding_status") != "unbound":
                errors.append(f"jobs[{index}].trigger.binding_status must be unbound")

        action = job.get("action")
        if not isinstance(action, dict):
            errors.append(f"jobs[{index}].action must be an object")
        else:
            expected_argv = (
                [
                    "dayu-cli",
                    "research-template",
                    "validate-monitoring-plan",
                    "--plan",
                    str(plan_path),
                ]
                if plan_path is not None
                else []
            )
            if action.get("type") != "command_argv":
                errors.append(f"jobs[{index}].action.type must be command_argv")
            if action.get("argv") != expected_argv:
                errors.append(f"jobs[{index}].action.argv must match the safe validation command")

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
    else:
        expected_summary = {
            "job_count": len(jobs),
            "enabled_job_count": enabled_count,
            "manual_activation_candidate_count": ready_count,
            "ready_for_review_job_count": ready_count,
            "blocked_job_count": blocked_count,
            "invalid_job_count": invalid_count,
        }
        for key, expected in expected_summary.items():
            if summary.get(key) != expected:
                errors.append(f"summary.{key} must be {expected}")
    if enabled_count:
        errors.append("scheduler manifest must not contain enabled jobs")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "job_count": len(jobs),
        "ready_for_review_job_count": ready_count,
        "blocked_job_count": blocked_count,
        "invalid_job_count": invalid_count,
    }


def inspect_monitoring_scheduler_manifest(manifest_path: Path) -> dict[str, object]:
    """读取一个持久化调度清单并验证安全约束及计划引用。

    Args:
        manifest_path: 待检查的持久化调度清单路径。

    Returns:
        包含清单路径、timezone、作业数、验证结果和载荷的检查报告。

    Raises:
        OSError: 当调度清单或其引用计划无法读取时。
    """

    resolved_path = manifest_path.resolve()
    try:
        payload = _load_json_object(resolved_path)
    except (OSError, ValueError) as exc:
        return {
            "scheduler_manifest_file": str(resolved_path),
            "validation": {
                "ok": False,
                "errors": [f"unable to load scheduler manifest: {exc}"],
                "warnings": [],
                "job_count": 0,
                "ready_for_review_job_count": 0,
                "blocked_job_count": 0,
                "invalid_job_count": 0,
            },
        }
    return {
        "scheduler_manifest_file": str(resolved_path),
        "timezone": str(payload.get("timezone", "") or ""),
        "validation": validate_monitoring_scheduler_manifest(payload),
    }


def write_monitoring_scheduler_manifest(
    workspace_root: Path,
    *,
    recursive: bool = False,
    timezone: str = "UTC",
    output_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """构建并写入平台无关的 monitoring-scheduler JSON 清单。

    Args:
        workspace_root: 包含标准模板 assets 目录的研究工作区根目录。
        recursive: 是否递归包含 ticker 等子工作区。
        timezone: 写入调度清单的非空时区标识。
        output_path: 可选自定义输出路径；为空时使用标准 monitoring 文件名。
        overwrite: 目标文件存在时是否允许覆盖。

    Returns:
        实际写入的调度清单绝对路径。

    Raises:
        ValueError: 当 timezone 为空时。
        FileExistsError: 当目标已存在且 ``overwrite`` 为 false 时。
        OSError: 当计划发现、目录创建或清单写入失败时。
    """

    resolved_workspace = workspace_root.resolve()
    payload = build_monitoring_scheduler_manifest(
        resolved_workspace,
        recursive=recursive,
        timezone=timezone,
    )
    target_path = output_path or resolved_workspace / "assets" / _TEMPLATE_DIR_NAME / "monitoring-scheduler.json"
    target_path = target_path.resolve()
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"{target_path} already exists; pass --overwrite to replace it")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target_path


def write_monitoring_execution_plan(
    bundle_path: Path,
    *,
    output_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """从 Bundle 构建并写入相邻的 dry-run 监控执行计划。

    Args:
        bundle_path: 用于生成监控计划的 Bundle 描述符路径。
        output_path: 可选自定义输出路径；为空时使用标准 monitoring 文件名。
        overwrite: 目标文件存在时是否允许覆盖。

    Returns:
        实际写入的监控计划绝对路径。

    Raises:
        ValueError: 当 Bundle 或监控输入不健康时。
        FileExistsError: 当目标已存在且 ``overwrite`` 为 false 时。
        OSError: 当 Bundle/输入读取、目录创建或计划写入失败时。
    """

    resolved_bundle_path = bundle_path.resolve()
    payload = build_monitoring_execution_plan(resolved_bundle_path)
    template = str(payload["template"])
    target_path = output_path or resolved_bundle_path.parent / f"{template}.monitoring-plan.json"
    target_path = target_path.resolve()
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"{target_path} already exists; pass --overwrite to replace it")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target_path
