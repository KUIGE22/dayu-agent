"""提供研究模板 Bundle、工作区与 Portfolio 的物化操作。"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from dayu.cli.commands._research_template_bundle import (
    inspect_research_template_bundle,
    validate_research_template_bundle_descriptor,
    write_research_template_bundle_descriptor,
)
from dayu.cli.commands._research_template_core import (
    _build_source_write_manifest_binding,
    _resolve_template_path,
    _resolve_template_selection_from_write_manifest,
    compose_research_template,
    copy_research_template,
    materialize_research_checklist,
    validate_monitoring_source_map_payload,
    write_monitoring_rules_payload,
    write_monitoring_source_map_payload,
    write_research_template_package_manifest,
    write_research_template_usage_guide,
)
from dayu.cli.commands._research_template_helpers import (
    _FALLBACK_TEMPLATE_NAME,
    _TEMPLATE_DIR_NAME,
    _build_research_portfolio_preview,
    _identifier_component,
    _load_json_object,
    _normalize_research_target,
    _normalize_template_name,
    _resolve_materialize_research_target,
    _sha256_file,
)
from dayu.cli.commands._research_template_monitoring import (
    inspect_monitoring_execution_plan,
    write_monitoring_execution_plan,
    write_monitoring_status_snapshot,
)
from dayu.cli.commands.research_workbook import (
    validate_research_workbook_payload,
    write_research_workbook_payload,
    write_research_workbook_report,
    write_research_workbook_report_status_snapshot,
    write_research_workbook_status_snapshot,
)


def _materialization_artifact_paths(workspace_root: Path, template: str) -> tuple[Path, ...]:
    """计算指定模板一次完整物化可能创建或覆盖的标准产物集合。

    Args:
        workspace_root: 研究工作区或 Portfolio 输出根目录。
        template: 已规范化的研究模板名。

    Returns:
        按物化/回滚顺序排列的 13 个产物路径元组。

    Raises:
        本函数只进行路径组合，不显式抛出异常。
    """
    artifact_dir = workspace_root.resolve() / "assets" / _TEMPLATE_DIR_NAME
    template_file = (
        artifact_dir / "common.md"
        if template == _FALLBACK_TEMPLATE_NAME
        else artifact_dir / f"common-plus-{template}.md"
    )
    return (
        template_file,
        artifact_dir / f"{template}.research-workbook.json",
        artifact_dir / f"{template}.research-progress.md",
        artifact_dir / f"{template}.monitoring-rules.json",
        artifact_dir / f"{template}.source-map.json",
        artifact_dir / "research-template.manifest.json",
        artifact_dir / f"{template}.research-guide.md",
        artifact_dir / f"{template}.checklist.md",
        artifact_dir / f"{template}.bundle.json",
        artifact_dir / f"{template}.monitoring-plan.json",
        artifact_dir / "monitoring-status.json",
        artifact_dir / "research-workbook-status.json",
        artifact_dir / "research-workbook-report-status.json",
    )


def _snapshot_materialization_artifacts(paths: Iterable[Path]) -> dict[Path, bytes | None]:
    """在物化前读取现有产物字节，并用 ``None`` 标记原本不存在的路径。

    Args:
        paths: 需要在物化前保存原始字节的产物路径序列。

    Returns:
        路径到原始字节或 ``None`` 的快照映射。

    Raises:
        OSError: 当任一已存在产物无法读取时。
    """
    return {path: path.read_bytes() if path.is_file() else None for path in paths}


def _rollback_materialization_artifacts(snapshot: dict[Path, bytes | None]) -> list[str]:
    """按逆序恢复产物快照，并把删除或写回失败收集为错误文本。

    Args:
        snapshot: 物化前的产物字节快照。

    Returns:
        回滚失败的 ``路径: 原因`` 文本列表；空列表表示全部恢复成功。

    Raises:
        本函数捕获每个产物的 ``OSError`` 并返回错误文本，不向调用者传播。
    """
    errors: list[str] = []
    for path, original_bytes in reversed(snapshot.items()):
        try:
            if original_bytes is None:
                if path.exists():
                    path.unlink()
                continue
            if not path.is_file() or path.read_bytes() != original_bytes:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original_bytes)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    return errors


def materialize_research_template_bundle(
    name: str,
    *,
    workspace_root: Path,
    ticker: str = "",
    company: str = "",
    write_manifest_path: Path | None = None,
    overwrite: bool = False,
) -> dict[str, object]:
    """在单一回滚边界内物化模板、工作簿、报告、监控文件、指南、检查单和 Bundle。

    Args:
        name: 待物化的研究模板稳定名称。
        workspace_root: 研究工作区或 Portfolio 输出根目录。
        ticker: 研究目标股票代码。
        company: 研究目标公司名称。
        write_manifest_path: 可选的完成态 write manifest 路径，用于绑定选择真源。
        overwrite: 是否允许覆盖已存在的研究产物。

    Returns:
        包含全部产物路径、研究目标、监控验证和可选来源绑定的物化结果。

    Raises:
        ValueError: 当模板、write-manifest 绑定、监控映射或最终 Bundle 验证无效时。
        FileNotFoundError: 当模板、清单或引用资产不存在时。
        FileExistsError: 当产物已存在且 ``overwrite`` 为 false 时。
        OSError: 当产物读取、目录创建或文件写入失败且回滚成功时，原异常继续传播。
        RuntimeError: 当物化失败且恢复快照也出现一个或多个错误时。
    """

    normalized = _normalize_template_name(name)
    workspace_root = workspace_root.resolve()
    research_target = _normalize_research_target(ticker=ticker, company=company)
    snapshot = _snapshot_materialization_artifacts(_materialization_artifact_paths(workspace_root, normalized))
    try:
        if normalized == _FALLBACK_TEMPLATE_NAME:
            template_path = copy_research_template(normalized, workspace_root=workspace_root, overwrite=overwrite)
        else:
            template_path = compose_research_template(normalized, workspace_root=workspace_root, overwrite=overwrite)
        workbook_path = write_research_workbook_payload(
            normalized,
            workspace_root=workspace_root,
            ticker=research_target["ticker"],
            company=research_target["company"],
            overwrite=overwrite,
        )
        progress_report_path = write_research_workbook_report(
            workbook_path,
            overwrite=overwrite,
        )
        rules_path = write_monitoring_rules_payload(normalized, workspace_root=workspace_root, overwrite=overwrite)
        source_map_path = write_monitoring_source_map_payload(
            normalized, workspace_root=workspace_root, overwrite=overwrite
        )
        manifest_path = write_research_template_package_manifest(workspace_root=workspace_root, overwrite=True)
        guide_path = write_research_template_usage_guide(
            normalized,
            workspace_root=workspace_root,
            template_file=template_path,
            workbook_file=workbook_path,
            progress_report_file=progress_report_path,
            rules_file=rules_path,
            source_map_file=source_map_path,
            manifest_file=manifest_path,
            ticker=research_target["ticker"],
            company=research_target["company"],
            overwrite=overwrite,
        )
        checklist_path = materialize_research_checklist(
            normalized,
            workspace_root=workspace_root,
            overwrite=overwrite,
        )
        validation = validate_monitoring_source_map_payload(
            _load_json_object(rules_path),
            _load_json_object(source_map_path),
        )
        source_write_manifest = (
            _build_source_write_manifest_binding(
                write_manifest_path.resolve(),
                expected_template=normalized,
            )
            if write_manifest_path is not None
            else None
        )
        bundle_path = write_research_template_bundle_descriptor(
            normalized,
            workspace_root=workspace_root,
            template_file=template_path,
            workbook_file=workbook_path,
            progress_report_file=progress_report_path,
            rules_file=rules_path,
            source_map_file=source_map_path,
            manifest_file=manifest_path,
            guide_file=guide_path,
            checklist_file=checklist_path,
            monitoring_validation=validation,
            research_target=research_target,
            source_write_manifest=source_write_manifest,
            overwrite=overwrite,
        )
        bundle_validation = validate_research_template_bundle_descriptor(_load_json_object(bundle_path))
        if not bool(bundle_validation.get("ok")):
            raise ValueError(f"materialized bundle failed validation: {bundle_validation['errors']}")
    except BaseException as exc:
        rollback_errors = _rollback_materialization_artifacts(snapshot)
        if rollback_errors:
            raise RuntimeError(
                f"research materialization failed ({exc}); rollback also failed: {rollback_errors}"
            ) from exc
        raise
    return {
        "template": normalized,
        "research_target": research_target,
        "template_file": str(template_path),
        "workbook_file": str(workbook_path),
        "progress_report_file": str(progress_report_path),
        "rules_file": str(rules_path),
        "source_map_file": str(source_map_path),
        "manifest_file": str(manifest_path),
        "guide_file": str(guide_path),
        "checklist_file": str(checklist_path),
        "bundle_file": str(bundle_path),
        "validation": validation,
        "bundle_validation": bundle_validation,
        "source_write_manifest": source_write_manifest,
    }


def materialize_research_workspace(
    name: str,
    *,
    workspace_root: Path,
    ticker: str = "",
    company: str = "",
    write_manifest_path: Path | None = None,
    overwrite: bool = False,
) -> dict[str, object]:
    """物化完整研究 Bundle，并追加 dry-run 监控计划和三类状态快照。

    Args:
        name: 待物化的研究模板稳定名称。
        workspace_root: 研究工作区或 Portfolio 输出根目录。
        ticker: 研究目标股票代码。
        company: 研究目标公司名称。
        write_manifest_path: 可选的完成态 write manifest 路径，用于绑定选择真源。
        overwrite: 是否允许覆盖已存在的研究产物。

    Returns:
        在 Bundle 结果上扩展监控计划、监控状态、工作簿状态和报告状态的工作区结果。

    Raises:
        ValueError: 当 Bundle、监控计划、工作簿或状态载荷验证失败时。
        FileNotFoundError: 当模板、清单或引用资产不存在时。
        FileExistsError: 当产物已存在且 ``overwrite`` 为 false 时。
        OSError: 当任一产物读写失败且回滚成功时，原异常继续传播。
        RuntimeError: 当工作区物化失败且恢复快照也失败时。
    """

    normalized = _normalize_template_name(name)
    resolved_workspace = workspace_root.resolve()
    snapshot = _snapshot_materialization_artifacts(_materialization_artifact_paths(resolved_workspace, normalized))
    try:
        payload = materialize_research_template_bundle(
            normalized,
            workspace_root=resolved_workspace,
            ticker=ticker,
            company=company,
            write_manifest_path=write_manifest_path,
            overwrite=overwrite,
        )
        plan_path = write_monitoring_execution_plan(
            Path(str(payload["bundle_file"])),
            overwrite=overwrite,
        )
        plan_inspection = inspect_monitoring_execution_plan(plan_path)
        plan_validation = plan_inspection.get("validation")
        if not isinstance(plan_validation, dict) or plan_validation.get("ok") is not True:
            raise ValueError(f"materialized monitoring plan failed validation: {plan_validation}")
        monitoring_status_path = write_monitoring_status_snapshot(
            resolved_workspace,
            overwrite=True,
        )
        workbook_status_path = write_research_workbook_status_snapshot(
            resolved_workspace,
            overwrite=True,
        )
        report_status_path = write_research_workbook_report_status_snapshot(
            resolved_workspace,
            overwrite=True,
        )
        monitoring_status = _load_json_object(monitoring_status_path)
        workbook_status = _load_json_object(workbook_status_path)
        report_status = _load_json_object(report_status_path)
        status_failures = {
            "monitoring": monitoring_status.get("overall_status"),
            "workbook": workbook_status.get("overall_status"),
            "report": report_status.get("overall_status"),
        }
        if any(
            status in {"unhealthy", "no_plans", "no_workbooks", "no_reports"} for status in status_failures.values()
        ):
            raise ValueError(f"materialized workspace status is incomplete or unhealthy: {status_failures}")
        target = payload["research_target"]
        assert isinstance(target, dict)
        guide_path = write_research_template_usage_guide(
            normalized,
            workspace_root=resolved_workspace,
            template_file=Path(str(payload["template_file"])),
            workbook_file=Path(str(payload["workbook_file"])),
            progress_report_file=Path(str(payload["progress_report_file"])),
            rules_file=Path(str(payload["rules_file"])),
            source_map_file=Path(str(payload["source_map_file"])),
            manifest_file=Path(str(payload["manifest_file"])),
            monitoring_plan_file=plan_path,
            monitoring_status_file=monitoring_status_path,
            workbook_status_file=workbook_status_path,
            report_status_file=report_status_path,
            ticker=str(target.get("ticker", "")),
            company=str(target.get("company", "")),
            overwrite=True,
        )
        bundle_validation = validate_research_template_bundle_descriptor(
            _load_json_object(Path(str(payload["bundle_file"])))
        )
        if bundle_validation.get("ok") is not True:
            raise ValueError(f"materialized workspace bundle failed validation: {bundle_validation['errors']}")
        payload.update(
            {
                "guide_file": str(guide_path),
                "monitoring_plan_file": str(plan_path),
                "monitoring_plan_validation": plan_validation,
                "monitoring_status_file": str(monitoring_status_path),
                "monitoring_status": monitoring_status,
                "workbook_status_file": str(workbook_status_path),
                "workbook_status": workbook_status,
                "report_status_file": str(report_status_path),
                "report_status": report_status,
                "bundle_validation": bundle_validation,
            }
        )
        return payload
    except BaseException as exc:
        rollback_errors = _rollback_materialization_artifacts(snapshot)
        if rollback_errors:
            raise RuntimeError(
                f"research workspace materialization failed ({exc}); rollback also failed: {rollback_errors}"
            ) from exc
        raise


def build_research_workspace_refresh_preview(bundle_path: Path) -> dict[str, object]:
    """检查 Bundle、工作簿与监控输入，预览派生产物是否可安全刷新。

    Args:
        bundle_path: 待预览或刷新的 Bundle 描述符路径。

    Returns:
        包含 blockers、当前验证、目标文件和 ``can_refresh`` 的无写入预览。

    Raises:
        OSError: 当 Bundle、工作簿、监控文件或报告无法读取时。
        ValueError: 当引用 JSON 内容无法解析为所需对象时。
    """

    resolved_bundle = bundle_path.resolve()
    inspection = inspect_research_template_bundle(resolved_bundle)
    payload = _load_json_object(resolved_bundle)
    template = str(payload.get("template", "") or "")
    artifacts = payload.get("artifacts")
    blockers: list[str] = []
    if not template:
        blockers.append("bundle template is missing")
    if not isinstance(artifacts, dict):
        blockers.append("bundle artifacts must be an object")
        artifacts = {}
    workbook_raw = artifacts.get("research_workbook")
    if not isinstance(workbook_raw, str) or not Path(workbook_raw).is_file():
        blockers.append("bundle research workbook is missing")
    else:
        try:
            workbook_validation = validate_research_workbook_payload(_load_json_object(Path(workbook_raw)))
            if workbook_validation.get("ok") is not True:
                blockers.append(f"bundle research workbook is invalid: {workbook_validation.get('errors', [])}")
        except (OSError, ValueError) as exc:
            blockers.append(f"bundle research workbook is invalid: {exc}")
    validation = inspection.get("validation")
    validation_errors = validation.get("errors", []) if isinstance(validation, dict) else []
    if isinstance(validation_errors, list):
        blockers.extend(
            str(error) for error in validation_errors if not str(error).startswith("artifacts.research_progress_report")
        )
    artifact_dir = resolved_bundle.parent
    derived_paths = {
        "research_progress_report": artifact_dir / f"{template}.research-progress.md",
        "monitoring_plan": artifact_dir / f"{template}.monitoring-plan.json",
        "monitoring_status": artifact_dir / "monitoring-status.json",
        "workbook_status": artifact_dir / "research-workbook-status.json",
        "report_status": artifact_dir / "research-workbook-report-status.json",
        "usage_guide": Path(str(artifacts.get("usage_guide", artifact_dir / f"{template}.research-guide.md"))),
    }
    return {
        "schema_version": 1,
        "preview_type": "research_workspace_refresh",
        "bundle_file": str(resolved_bundle),
        "template": template,
        "can_refresh": not blockers,
        "blockers": blockers,
        "current_bundle_validation": validation,
        "outputs": {
            key: {"path": str(path.resolve()), "action": "refresh" if path.exists() else "create"}
            for key, path in derived_paths.items()
        },
    }


def write_research_workspace_refresh(bundle_path: Path) -> dict[str, object]:
    """在单一快照边界内刷新报告、Bundle、监控计划、指南与状态文件。

    Args:
        bundle_path: 待预览或刷新的 Bundle 描述符路径。

    Returns:
        包含 ``applied``、刷新后验证和各派生产物路径/载荷的结果。

    Raises:
        ValueError: 当刷新预览存在 blocker 或刷新后 Bundle/计划验证失败时。
        OSError: 当派生产物读写失败且快照恢复成功时，原异常继续传播。
        RuntimeError: 当刷新失败且恢复快照也出现错误时。
    """

    preview = build_research_workspace_refresh_preview(bundle_path)
    if preview.get("can_refresh") is not True:
        raise ValueError(f"research workspace cannot be refreshed: {preview['blockers']}")
    resolved_bundle = Path(str(preview["bundle_file"]))
    payload = _load_json_object(resolved_bundle)
    template = str(payload["template"])
    artifacts = payload["artifacts"]
    assert isinstance(artifacts, dict)
    outputs = preview["outputs"]
    assert isinstance(outputs, dict)
    output_paths = {key: Path(str(value["path"])) for key, value in outputs.items() if isinstance(value, dict)}
    snapshot = _snapshot_materialization_artifacts(output_paths.values())
    try:
        workbook_path = Path(str(artifacts["research_workbook"]))
        report_path = write_research_workbook_report(
            workbook_path,
            output_path=output_paths["research_progress_report"],
            overwrite=True,
        )
        bundle_validation = validate_research_template_bundle_descriptor(payload)
        if bundle_validation.get("ok") is not True:
            raise ValueError(f"bundle remains unhealthy after report refresh: {bundle_validation['errors']}")
        plan_path = write_monitoring_execution_plan(
            resolved_bundle,
            output_path=output_paths["monitoring_plan"],
            overwrite=True,
        )
        plan_inspection = inspect_monitoring_execution_plan(plan_path)
        plan_validation = plan_inspection.get("validation")
        if not isinstance(plan_validation, dict) or plan_validation.get("ok") is not True:
            raise ValueError(f"refreshed monitoring plan failed validation: {plan_validation}")
        workspace_root = resolved_bundle.parent.parent.parent
        # Write the status snapshots to the exact paths the preview computed
        # (derived from resolved_bundle.parent), so they stay inside the snapshot
        # rollback boundary even when the bundle sits at a non-canonical depth.
        # workspace_root still drives the scan for aggregation.
        monitoring_status_path = write_monitoring_status_snapshot(
            workspace_root,
            output_path=output_paths["monitoring_status"],
            overwrite=True,
        )
        workbook_status_path = write_research_workbook_status_snapshot(
            workspace_root,
            output_path=output_paths["workbook_status"],
            overwrite=True,
        )
        report_status_path = write_research_workbook_report_status_snapshot(
            workspace_root,
            output_path=output_paths["report_status"],
            overwrite=True,
        )
        monitoring_status = _load_json_object(monitoring_status_path)
        workbook_status = _load_json_object(workbook_status_path)
        report_status = _load_json_object(report_status_path)
        statuses = {
            "monitoring": monitoring_status,
            "workbook": workbook_status,
            "report": report_status,
        }
        if any(
            status.get("overall_status") in {"unhealthy", "no_plans", "no_workbooks", "no_reports"}
            for status in statuses.values()
        ):
            raise ValueError("refreshed workspace status is incomplete or unhealthy")
        target = payload.get("research_target")
        target = target if isinstance(target, dict) else {}
        guide_path = write_research_template_usage_guide(
            template,
            workspace_root=workspace_root,
            template_file=Path(str(artifacts["write_template"])),
            workbook_file=workbook_path,
            progress_report_file=report_path,
            rules_file=Path(str(artifacts["monitoring_rules"])),
            source_map_file=Path(str(artifacts["source_map"])),
            manifest_file=Path(str(artifacts["package_manifest"])),
            monitoring_plan_file=plan_path,
            monitoring_status_file=monitoring_status_path,
            workbook_status_file=workbook_status_path,
            report_status_file=report_status_path,
            ticker=str(target.get("ticker", "")),
            company=str(target.get("company", "")),
            output_path=output_paths["usage_guide"],
            overwrite=True,
        )
        return {
            **preview,
            "applied": True,
            "bundle_validation": bundle_validation,
            "monitoring_plan_validation": plan_validation,
            "monitoring_status": monitoring_status,
            "workbook_status": workbook_status,
            "report_status": report_status,
            "guide_file": str(guide_path),
        }
    except BaseException as exc:
        rollback_errors = _rollback_materialization_artifacts(snapshot)
        if rollback_errors:
            raise RuntimeError(
                f"research workspace refresh failed ({exc}); rollback also failed: {rollback_errors}"
            ) from exc
        raise


def materialize_research_bundle_from_write_manifest(
    manifest_path: Path,
    *,
    workspace_root: Path,
    overwrite: bool = False,
) -> dict[str, object]:
    """以完成的 write manifest 为模板选择与研究目标真源物化研究工作区。

    Args:
        manifest_path: 作为模板选择真源的完成态 write manifest 路径。
        workspace_root: 研究工作区或 Portfolio 输出根目录。
        overwrite: 是否允许覆盖已存在的研究产物。

    Returns:
        完整工作区物化结果，并附加模板选择来源载荷。

    Raises:
        OSError: 当 write manifest、模板资产或物化产物无法读写时。
        ValueError: 当 manifest 未完成、模板选择无效或物化验证失败时。
        FileNotFoundError: 当 manifest 或选择的模板资产不存在时。
        FileExistsError: 当目标产物存在且 ``overwrite`` 为 false 时。
        RuntimeError: 当物化失败且快照回滚也失败时。
    """

    resolved_manifest = manifest_path.resolve()
    template, selection = _resolve_template_selection_from_write_manifest(resolved_manifest)
    target = _resolve_materialize_research_target(
        ticker_raw=None,
        company_raw=None,
        manifest_raw=str(resolved_manifest),
    )
    payload = materialize_research_workspace(
        template,
        workspace_root=workspace_root.resolve(),
        ticker=target["ticker"],
        company=target["company"],
        write_manifest_path=resolved_manifest,
        overwrite=overwrite,
    )
    payload["selection"] = selection
    return payload


def materialize_research_portfolio(
    portfolio_path: Path,
    *,
    workspace_root: Path,
    overwrite: bool = False,
) -> dict[str, object]:
    """预检 Portfolio 全部目标后逐目标物化隔离工作区，并记录局部失败。

    Args:
        portfolio_path: 待物化或预览的 Portfolio JSON 文件路径。
        workspace_root: 研究工作区或 Portfolio 输出根目录。
        overwrite: 是否允许覆盖已存在的研究产物。

    Returns:
        包含整体 ``ok``、成功/失败计数、逐目标结果、状态快照和报告路径的批处理报告。

    Raises:
        OSError: 当 Portfolio 预检、报告目录创建、汇总报告或状态快照写入失败时。
        ValueError: 当 Portfolio schema、目标、模板或跨目标路径约束无效时。
    """

    resolved_portfolio_path = portfolio_path.resolve()
    resolved_workspace = workspace_root.resolve()
    targets = _prepare_research_portfolio_targets(resolved_portfolio_path)
    preview = _build_research_portfolio_preview(
        resolved_portfolio_path,
        resolved_workspace,
        targets,
        overwrite=overwrite,
    )
    preview_targets = preview.get("targets")
    preview_by_ticker: dict[str, dict[str, object]] = {}
    if isinstance(preview_targets, list):
        for item in preview_targets:
            if isinstance(item, dict):
                preview_by_ticker[str(item.get("ticker", ""))] = item
    results: list[dict[str, object]] = []
    for target in targets:
        ticker = str(target["ticker"])
        company = str(target["company"])
        template = str(target["template"])
        target_workspace = resolved_workspace / str(target["workspace_key"])
        result: dict[str, object] = {
            "ticker": ticker,
            "company": company,
            "template": template,
            "workspace_root": str(target_workspace),
            "selection": target["selection"],
            "write_manifest": target["write_manifest"],
        }
        target_preview = preview_by_ticker[ticker]
        if target_preview.get("action") == "blocked_existing_files":
            existing_files = target_preview.get("existing_files", [])
            result.update(
                {
                    "status": "failed",
                    "error": "existing generated files require --overwrite",
                    "existing_files": existing_files,
                }
            )
            results.append(result)
            continue
        try:
            bundle = materialize_research_workspace(
                template,
                workspace_root=target_workspace,
                ticker=ticker,
                company=company,
                write_manifest_path=(
                    Path(str(target["write_manifest"]))
                    if target["write_manifest"] is not None
                    and isinstance(target["selection"], dict)
                    and target["selection"].get("selection_mode") != "explicit"
                    else None
                ),
                overwrite=overwrite,
            )
            result.update(
                {
                    "status": "success",
                    "bundle_file": bundle["bundle_file"],
                    "workbook_file": bundle["workbook_file"],
                    "monitoring_plan_file": bundle["monitoring_plan_file"],
                    "monitoring_status_file": bundle["monitoring_status_file"],
                    "workbook_status_file": bundle["workbook_status_file"],
                    "report_status_file": bundle["report_status_file"],
                }
            )
        except Exception as exc:  # noqa: BLE001 - isolate one target's failure into the batch report
            # materialize_research_workspace raises OSError/ValueError on normal
            # failures but RuntimeError (rollback-also-failed) or AssertionError
            # on degenerate paths. Recording any of them keeps the batch report
            # honest instead of aborting the whole portfolio with a traceback.
            result.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        results.append(result)

    status_path = write_monitoring_status_snapshot(
        resolved_workspace,
        recursive=True,
        overwrite=True,
    )
    status_payload = _load_json_object(status_path)
    workbook_status_path = write_research_workbook_status_snapshot(
        resolved_workspace,
        recursive=True,
        overwrite=True,
    )
    workbook_status_payload = _load_json_object(workbook_status_path)
    report_status_path = write_research_workbook_report_status_snapshot(
        resolved_workspace,
        recursive=True,
        overwrite=True,
    )
    report_status_payload = _load_json_object(report_status_path)
    success_count = sum(result.get("status") == "success" for result in results)
    failure_count = len(results) - success_count
    report_path = resolved_workspace / "research-portfolio.materialization.json"
    report = {
        "schema_version": 1,
        "report_type": "research_portfolio_materialization",
        "portfolio_file": str(resolved_portfolio_path),
        "portfolio_fingerprint": _sha256_file(resolved_portfolio_path),
        "workspace_root": str(resolved_workspace),
        "report_file": str(report_path.resolve()),
        "ok": failure_count == 0,
        "target_count": len(results),
        "success_count": success_count,
        "failure_count": failure_count,
        "monitoring_status_file": str(status_path),
        "monitoring_status": status_payload,
        "workbook_status_file": str(workbook_status_path),
        "workbook_status": workbook_status_payload,
        "report_status_file": str(report_status_path),
        "report_status": report_status_payload,
        "preview": preview,
        "results": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def build_research_portfolio_preview(
    portfolio_path: Path,
    *,
    workspace_root: Path,
    overwrite: bool = False,
) -> dict[str, object]:
    """解析并预览 Portfolio 所有目标的产物冲突，不创建或修改文件。

    Args:
        portfolio_path: 待物化或预览的 Portfolio JSON 文件路径。
        workspace_root: 研究工作区或 Portfolio 输出根目录。
        overwrite: 是否允许覆盖已存在的研究产物。

    Returns:
        包含目标预览、冲突/新增计数、可应用标志和 Portfolio 指纹的载荷。

    Raises:
        OSError: 当 Portfolio 或已有目标产物无法读取并计算指纹时。
        ValueError: 当 Portfolio schema、目标字段、模板或目标唯一性无效时。
    """

    resolved_portfolio_path = portfolio_path.resolve()
    targets = _prepare_research_portfolio_targets(resolved_portfolio_path)
    return _build_research_portfolio_preview(
        resolved_portfolio_path,
        workspace_root.resolve(),
        targets,
        overwrite=overwrite,
    )


def _resolve_materialize_template_selection(name_raw: object, manifest_raw: object) -> tuple[str, dict[str, object]]:
    """在显式模板名与 write manifest 两种来源中选择唯一物化模板。

    Args:
        name_raw: 命令行显式模板名原始值；可为空。
        manifest_raw: 命令行 write manifest 路径原始值；可为空。

    Returns:
        规范模板名与描述选择模式/依据的载荷。

    Raises:
        ValueError: 当既未提供模板也未提供 manifest，或显式模板名无效时。
        OSError: 当 write manifest 或模板资产无法读取时。
        FileNotFoundError: 当 manifest 选择的模板资产不存在时。
    """
    explicit_name = str(name_raw).strip() if name_raw is not None else ""
    if explicit_name:
        template_name = _normalize_template_name(explicit_name)
        return template_name, {
            "selection_mode": "explicit",
            "selected_template": template_name,
        }

    if manifest_raw is None or not str(manifest_raw).strip():
        raise ValueError("materialize requires a template name or --manifest")

    manifest_path = Path(str(manifest_raw)).resolve()
    return _resolve_template_selection_from_write_manifest(manifest_path)


def _prepare_research_portfolio_targets(portfolio_path: Path) -> list[dict[str, object]]:
    """校验 Portfolio schema、目标唯一性和模板可用性，并生成隔离工作区目标。

    Args:
        portfolio_path: 待物化或预览的 Portfolio JSON 文件路径。

    Returns:
        含 ticker、company、模板、选择依据、目标工作区和标识的规范目标列表。

    Raises:
        OSError: 当 Portfolio、write manifest 或模板资产无法读取时。
        ValueError: 当 targets 为空/畸形、ticker 重复、模板冲突或目标标识无效时。
        FileNotFoundError: 当显式或 manifest 选择的模板资产不存在时。
    """
    payload = _load_json_object(portfolio_path)
    if payload.get("schema_version") != 1:
        raise ValueError("portfolio schema_version must be 1")
    if payload.get("portfolio_type") != "research_monitoring_portfolio":
        raise ValueError("portfolio_type must be research_monitoring_portfolio")
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("portfolio targets must be a non-empty list")

    prepared: list[dict[str, object]] = []
    seen_tickers: set[str] = set()
    seen_workspace_keys: set[str] = set()
    for index, raw_target in enumerate(raw_targets):
        if not isinstance(raw_target, dict):
            raise ValueError(f"portfolio targets[{index}] must be an object")
        manifest_raw = str(raw_target.get("write_manifest", "") or "").strip()
        manifest_path: Path | None = None
        if manifest_raw:
            candidate = Path(manifest_raw)
            manifest_path = (
                (portfolio_path.parent / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
            )
            if not manifest_path.is_file():
                raise ValueError(f"portfolio targets[{index}].write_manifest does not exist: {manifest_path}")

        target = _resolve_materialize_research_target(
            ticker_raw=raw_target.get("ticker"),
            company_raw=raw_target.get("company"),
            manifest_raw=str(manifest_path) if manifest_path is not None else None,
        )
        ticker = target["ticker"]
        if not ticker:
            raise ValueError(f"portfolio targets[{index}] requires ticker or write_manifest config.ticker")
        if ticker in seen_tickers:
            raise ValueError(f"duplicate portfolio ticker: {ticker}")
        workspace_key = _identifier_component(ticker).upper()
        if not workspace_key:
            raise ValueError(f"portfolio targets[{index}] ticker cannot form a workspace directory")
        if workspace_key in seen_workspace_keys:
            raise ValueError(f"portfolio workspace directory collision: {workspace_key}")

        template_raw = str(raw_target.get("template", "") or "").strip()
        if template_raw:
            template = _normalize_template_name(template_raw)
            _resolve_template_path(template)
            selection: dict[str, object] = {
                "selection_mode": "explicit",
                "selected_template": template,
            }
        elif manifest_path is not None:
            template, selection = _resolve_template_selection_from_write_manifest(manifest_path)
        else:
            raise ValueError(f"portfolio targets[{index}] requires template or write_manifest")

        seen_tickers.add(ticker)
        seen_workspace_keys.add(workspace_key)
        prepared.append(
            {
                "ticker": ticker,
                "company": target["company"],
                "template": template,
                "workspace_key": workspace_key,
                "write_manifest": str(manifest_path) if manifest_path is not None else None,
                "selection": selection,
            }
        )
    return prepared
