"""提供研究模板 Bundle 的描述、验证、重绑定与回滚操作。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from dayu.cli.commands._research_template_core import (
    _build_source_write_manifest_binding,
    _build_write_manifest_binding_semantics,
    _resolve_template_path,
    _resolve_template_selection_from_write_manifest,
    validate_monitoring_source_map_payload,
)
from dayu.cli.commands._research_template_helpers import (
    _BUNDLE_ARTIFACT_KEYS,
    _TEMPLATE_DIR_NAME,
    _discover_research_artifact_paths,
    _load_json_object,
    _normalize_research_target,
    _normalize_template_name,
    _read_template_title,
    _sha256_file,
    _sha256_json_object,
)
from dayu.cli.commands.research_workbook import (
    inspect_research_workbook_report,
    validate_research_workbook_payload,
)
from dayu.cli.research_template_checklist import render_research_checklist_markdown
from dayu.cli.research_template_definitions import load_research_template_definition


def build_research_template_bundle_descriptor(
    name: str,
    *,
    template_file: Path,
    workbook_file: Path,
    progress_report_file: Path | None = None,
    rules_file: Path,
    source_map_file: Path,
    manifest_file: Path,
    guide_file: Path,
    checklist_file: Path,
    monitoring_validation: dict[str, object],
    research_target: dict[str, str] | None = None,
    source_write_manifest: dict[str, object] | None = None,
) -> dict[str, object]:
    """汇集物化产物路径、研究目标和监控验证，构建机器可读 Bundle 描述符。

    Args:
        name: Bundle 所属研究模板的稳定名称。
        template_file: 物化后的研究模板文件路径。
        workbook_file: 物化后的研究工作簿文件路径。
        progress_report_file: 可选研究进度报告文件路径。
        rules_file: 物化后的监控规则文件路径。
        source_map_file: 物化后的监控 source-map 文件路径。
        manifest_file: 物化后的 package manifest 文件路径。
        guide_file: 物化后的使用指南文件路径。
        checklist_file: 物化后的研究检查单文件路径。
        monitoring_validation: 物化时得到的监控规则/source-map 验证快照。
        research_target: 可选的规范化股票代码和公司名称。
        source_write_manifest: 可选的来源 write-manifest 内容与语义指纹绑定。

    Returns:
        包含模板元数据、产物索引、能力声明和可选 write-manifest 绑定的描述符。

    Raises:
        ValueError: 当模板名无效时。
        FileNotFoundError: 当指定模板资产不存在时。
        OSError: 当模板标题文件无法读取时。
    """

    normalized = _normalize_template_name(name)
    template = _resolve_template_path(normalized)
    payload: dict[str, object] = {
        "schema_version": 1,
        "bundle_type": "research_template_bundle",
        "template": normalized,
        "template_title": _read_template_title(template),
        "research_target": _normalize_research_target(
            ticker=(research_target or {}).get("ticker", ""),
            company=(research_target or {}).get("company", ""),
        ),
        "automation_status": "manual_review",
        "artifacts": {
            "write_template": str(template_file.resolve()),
            "research_workbook": str(workbook_file.resolve()),
            "research_checklist": str(checklist_file.resolve()),
            "monitoring_rules": str(rules_file.resolve()),
            "source_map": str(source_map_file.resolve()),
            "package_manifest": str(manifest_file.resolve()),
            "usage_guide": str(guide_file.resolve()),
        },
        "capabilities": {
            "write_report": True,
            "track_research_evidence": True,
            "review_monitoring_rules": True,
            "review_source_bindings": True,
            "automated_monitoring": False,
        },
        "monitoring_validation": monitoring_validation,
    }
    if progress_report_file is not None:
        artifacts = payload["artifacts"]
        assert isinstance(artifacts, dict)
        artifacts["research_progress_report"] = str(progress_report_file.resolve())
    if source_write_manifest is not None:
        payload["source_write_manifest"] = deepcopy(source_write_manifest)
    return payload


def _recompute_bundle_monitoring_integrity(
    template: str,
    rules_path_raw: object,
    source_map_path_raw: object,
) -> list[str]:
    """从当前规则和 source-map 文件重新计算 Bundle 的监控一致性与绑定批准来源。

    Args:
        template: Bundle 声明的规范模板名。
        rules_path_raw: 描述符中 monitoring_rules 路径的原始值。
        source_map_path_raw: 描述符中 source_map 路径的原始值。

    Returns:
        发现的监控一致性错误列表；路径缺失时由外层存在性校验负责。

    Raises:
        本函数把规则/source-map 读取与解析失败转换为错误文本，不显式传播这些异常。
    """

    errors: list[str] = []
    if not isinstance(rules_path_raw, str) or not rules_path_raw.strip():
        return errors
    if not isinstance(source_map_path_raw, str) or not source_map_path_raw.strip():
        return errors
    rules_path = Path(rules_path_raw)
    source_map_path = Path(source_map_path_raw)
    if not rules_path.is_file() or not source_map_path.is_file():
        return errors
    try:
        rules_payload = _load_json_object(rules_path)
        source_map_payload = _load_json_object(source_map_path)
    except (OSError, ValueError) as exc:
        errors.append(f"monitoring integrity could not be recomputed: {exc}")
        return errors
    recomputed = validate_monitoring_source_map_payload(rules_payload, source_map_payload)
    recomputed_errors = recomputed.get("errors")
    if isinstance(recomputed_errors, list):
        errors.extend(f"monitoring integrity: {error}" for error in recomputed_errors)
    recomputed_template = str(recomputed.get("template", "") or "")
    if template and recomputed_template and recomputed_template != template:
        errors.append(
            "monitoring integrity: source-map template mismatch: "
            f"bundle={template!r} source_map={recomputed_template!r}"
        )
    data_sources = source_map_payload.get("data_sources")
    if isinstance(data_sources, list):
        for index, source in enumerate(data_sources):
            if not isinstance(source, dict):
                continue
            if str(source.get("binding_status", "") or "") != "bound":
                continue
            source_name = str(source.get("source", "") or "") or f"index {index}"
            approval = source.get("binding_approval")
            approved_by = ""
            approval_reference = ""
            if isinstance(approval, dict):
                approved_by = str(approval.get("approved_by", "") or "").strip()
                approval_reference = str(approval.get("approval_reference", "") or "").strip()
            if not approved_by or not approval_reference:
                errors.append(f"monitoring integrity: bound source lacks binding_approval provenance: {source_name}")
    return errors


def _recompute_bundle_checklist_integrity(
    template: str,
    checklist_path_raw: object,
) -> list[str]:
    """根据 Bundle 模板重新渲染检查单，并与当前文件内容比较。

    Args:
        template: Bundle 声明的规范模板名。
        checklist_path_raw: 描述符中 research_checklist 路径的原始值。

    Returns:
        检查单模板或内容不一致的错误列表；缺失路径由外层校验负责。

    Raises:
        本函数把模板定义加载和检查单读取失败转换为错误文本，不显式传播这些异常。
    """

    errors: list[str] = []
    if not template:
        return errors
    if not isinstance(checklist_path_raw, str) or not checklist_path_raw.strip():
        return errors
    checklist_path = Path(checklist_path_raw)
    if not checklist_path.is_file():
        return errors
    try:
        definition = load_research_template_definition(template)
        expected_markdown = render_research_checklist_markdown(definition)
        actual_markdown = checklist_path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        errors.append(f"checklist integrity could not be recomputed: {exc}")
        return errors
    if actual_markdown != expected_markdown:
        errors.append(f"checklist integrity: checklist does not match the bundle template definition for {template!r}")
    return errors


def validate_research_template_bundle_descriptor(payload: dict[str, object]) -> dict[str, object]:
    """校验 Bundle schema、产物存在性、指纹、工作簿、报告和监控一致性。

    Args:
        payload: 待验证的 Bundle 描述符载荷。

    Returns:
        包含 ``ok``、错误、警告、模板、产物计数及子验证结果的报告。

    Raises:
        OSError: 当下游工作簿报告检查无法读取引用文件且传播底层错误时。
        ValueError: 当下游工作簿报告检查传播无法收敛的内容错误时。
    """

    errors: list[str] = []
    warnings: list[str] = []
    workbook_validation: dict[str, object] | None = None
    workbook_report_validation: dict[str, object] | None = None
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if payload.get("bundle_type") != "research_template_bundle":
        errors.append("bundle_type must be research_template_bundle")

    template = str(payload.get("template", "") or "")
    if not template:
        errors.append("template is required")
    if payload.get("automation_status") != "manual_review":
        errors.append("automation_status must be manual_review")

    research_target = payload.get("research_target")
    if not isinstance(research_target, dict):
        errors.append("research_target must be an object")
    else:
        for key in ("ticker", "company"):
            if not isinstance(research_target.get(key), str):
                errors.append(f"research_target.{key} must be a string")

    source_write_manifest = payload.get("source_write_manifest")
    if source_write_manifest is not None:
        if not isinstance(source_write_manifest, dict):
            errors.append("source_write_manifest must be an object")
        else:
            source_path_raw = source_write_manifest.get("path")
            source_file_fingerprint = str(source_write_manifest.get("file_fingerprint", "") or "")
            source_semantic_fingerprint = str(source_write_manifest.get("semantic_fingerprint", "") or "")
            selected_template = str(source_write_manifest.get("selected_template", "") or "")
            if not isinstance(source_path_raw, str) or not source_path_raw.strip():
                errors.append("source_write_manifest.path must be a non-empty path")
            else:
                source_path = Path(source_path_raw)
                if not source_path.is_file():
                    errors.append(f"source_write_manifest.path does not exist: {source_path}")
                else:
                    try:
                        current_semantics = _build_write_manifest_binding_semantics(source_path.resolve())
                        semantic_matches = _sha256_json_object(current_semantics) == source_semantic_fingerprint
                        if not semantic_matches:
                            errors.append("source_write_manifest semantic fingerprint is stale")
                        if semantic_matches and _sha256_file(source_path) != source_file_fingerprint:
                            warnings.append("source_write_manifest file changed without selection drift")
                        current_template, _current_selection = _resolve_template_selection_from_write_manifest(
                            source_path.resolve()
                        )
                        if current_template != selected_template or current_template != template:
                            errors.append(
                                "source_write_manifest template mismatch: "
                                f"bundle={template!r} source={current_template!r}"
                            )
                    except (OSError, ValueError) as exc:
                        errors.append(f"source_write_manifest is invalid: {exc}")

    artifacts = payload.get("artifacts")
    artifact_count = 0
    if not isinstance(artifacts, dict):
        errors.append("artifacts must be an object")
    else:
        artifact_count = len(artifacts)
        for key in (item for item in _BUNDLE_ARTIFACT_KEYS if item != "research_progress_report"):
            path_raw = artifacts.get(key)
            if not isinstance(path_raw, str) or not path_raw.strip():
                errors.append(f"artifacts.{key} must be a non-empty path")
            elif not Path(path_raw).is_file():
                errors.append(f"artifacts.{key} does not exist: {path_raw}")
        extra_keys = sorted(str(key) for key in artifacts if key not in _BUNDLE_ARTIFACT_KEYS)
        if extra_keys:
            warnings.append(f"unknown artifact entries: {', '.join(extra_keys)}")
        errors.extend(
            _recompute_bundle_monitoring_integrity(
                template,
                artifacts.get("monitoring_rules"),
                artifacts.get("source_map"),
            )
        )
        errors.extend(
            _recompute_bundle_checklist_integrity(
                template,
                artifacts.get("research_checklist"),
            )
        )
        workbook_raw = artifacts.get("research_workbook")
        if isinstance(workbook_raw, str) and workbook_raw.strip() and Path(workbook_raw).is_file():
            try:
                workbook_payload = _load_json_object(Path(workbook_raw))
                workbook_validation = validate_research_workbook_payload(workbook_payload)
                workbook_errors = workbook_validation.get("errors")
                if isinstance(workbook_errors, list):
                    errors.extend(f"artifacts.research_workbook: {error}" for error in workbook_errors)
                workbook_warnings = workbook_validation.get("warnings")
                if isinstance(workbook_warnings, list):
                    warnings.extend(f"artifacts.research_workbook: {warning}" for warning in workbook_warnings)
                workbook_template = str(workbook_payload.get("template", "") or "")
                if workbook_template != template:
                    errors.append(
                        "artifacts.research_workbook template mismatch: "
                        f"bundle={template!r} workbook={workbook_template!r}"
                    )
                workbook_target = workbook_payload.get("research_target")
                if isinstance(research_target, dict) and workbook_target != research_target:
                    errors.append("artifacts.research_workbook research_target does not match bundle")
            except (OSError, ValueError) as exc:
                errors.append(f"artifacts.research_workbook is invalid JSON: {exc}")
        report_raw = artifacts.get("research_progress_report")
        if report_raw is not None:
            if not isinstance(report_raw, str) or not report_raw.strip():
                errors.append("artifacts.research_progress_report must be a non-empty path")
            elif not Path(report_raw).is_file():
                errors.append(f"artifacts.research_progress_report does not exist: {report_raw}")
            elif isinstance(workbook_raw, str) and workbook_raw.strip():
                workbook_report_validation = inspect_research_workbook_report(
                    Path(report_raw),
                    Path(workbook_raw),
                )
                report_validation = workbook_report_validation.get("validation")
                if isinstance(report_validation, dict):
                    report_errors = report_validation.get("errors")
                    if isinstance(report_errors, list):
                        errors.extend(f"artifacts.research_progress_report: {error}" for error in report_errors)
                    report_warnings = report_validation.get("warnings")
                    if isinstance(report_warnings, list):
                        warnings.extend(f"artifacts.research_progress_report: {warning}" for warning in report_warnings)

    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        errors.append("capabilities must be an object")
    else:
        for key in (
            "write_report",
            "track_research_evidence",
            "review_monitoring_rules",
            "review_source_bindings",
            "automated_monitoring",
        ):
            if not isinstance(capabilities.get(key), bool):
                errors.append(f"capabilities.{key} must be a boolean")

    monitoring_validation = payload.get("monitoring_validation")
    if not isinstance(monitoring_validation, dict):
        errors.append("monitoring_validation must be an object")
    elif monitoring_validation.get("ok") is not True:
        errors.append("monitoring_validation.ok must be true")

    return {
        "ok": not errors,
        "template": template,
        "errors": errors,
        "warnings": warnings,
        "artifact_count": artifact_count,
        "workbook_validation": workbook_validation,
        "workbook_report_validation": workbook_report_validation,
    }


def inspect_research_template_bundle(bundle_path: Path) -> dict[str, object]:
    """读取并验证一个 Bundle 描述符；加载失败时返回结构化错误结果。

    Args:
        bundle_path: 当前 Bundle 描述符路径。

    Returns:
        包含描述符路径、模板摘要、研究目标和验证报告的检查结果。

    Raises:
        本函数把描述符读取和 JSON 解析错误收敛到 ``validation.errors``。
    """

    resolved_path = bundle_path.resolve()
    try:
        payload = _load_json_object(resolved_path)
    except (OSError, ValueError) as exc:
        return {
            "descriptor_file": str(resolved_path),
            "template": "",
            "template_title": "",
            "research_target": {},
            "automation_status": "",
            "validation": {
                "ok": False,
                "template": "",
                "errors": [f"unable to load bundle descriptor: {exc}"],
                "warnings": [],
                "artifact_count": 0,
            },
        }

    return {
        "descriptor_file": str(resolved_path),
        "template": str(payload.get("template", "") or ""),
        "template_title": str(payload.get("template_title", "") or ""),
        "research_target": payload.get("research_target", {}),
        "automation_status": str(payload.get("automation_status", "") or ""),
        "validation": validate_research_template_bundle_descriptor(payload),
    }


def build_research_template_bundle_rebind_preview(bundle_path: Path) -> dict[str, object]:
    """校验 Bundle 与来源 write manifest，并预览刷新绑定后的候选描述符。

    Args:
        bundle_path: 当前 Bundle 描述符路径。

    Returns:
        包含语义/文件指纹前后值、变更标志和候选验证结果的无写入预览。

    Raises:
        OSError: 当 Bundle、write manifest 或模板资产无法读取时。
        ValueError: 当 Bundle 绑定缺失、manifest 选择漂移或候选描述符不健康时。
        FileNotFoundError: 当 manifest 选择的模板资产不存在时。
    """

    _candidate, preview = _prepare_research_template_bundle_rebind(bundle_path)
    return preview


def write_research_template_bundle_rebind(bundle_path: Path) -> dict[str, object]:
    """在保留当前描述符内容寻址备份后刷新 Bundle 的 write-manifest 绑定。

    Args:
        bundle_path: 当前 Bundle 描述符路径。

    Returns:
        包含是否应用、备份路径、新旧指纹和最终验证结果的写入结果。

    Raises:
        OSError: 当 Bundle、manifest、备份或目标描述符无法读写时。
        ValueError: 当候选无效、备份碰撞或写入后验证失败时。
        FileNotFoundError: 当 manifest 选择的模板资产不存在时。
    """

    candidate, preview = _prepare_research_template_bundle_rebind(bundle_path)
    resolved_bundle = Path(str(preview["bundle_file"]))
    if preview["changed"] is not True:
        return {**preview, "applied": False, "backup_file": None}

    original_fingerprint = _sha256_file(resolved_bundle)
    backup_path = resolved_bundle.with_name(f"{resolved_bundle.stem}.before-rebind.{original_fingerprint[:12]}.json")
    if backup_path.exists():
        if not backup_path.is_file() or _sha256_file(backup_path) != original_fingerprint:
            raise ValueError(f"bundle rebind backup collision: {backup_path}")
    else:
        backup_path.write_bytes(resolved_bundle.read_bytes())
    resolved_bundle.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    final_validation = validate_research_template_bundle_descriptor(_load_json_object(resolved_bundle))
    if final_validation.get("ok") is not True:
        raise ValueError(f"rebound bundle failed validation: {final_validation.get('errors', [])}")
    return {
        **preview,
        "applied": True,
        "backup_file": str(backup_path),
        "bundle_fingerprint_after": _sha256_file(resolved_bundle),
        "validation": final_validation,
    }


def _prepare_research_template_bundle_rebind(
    bundle_path: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    """构建并验证 Bundle rebind 候选，同时生成不落盘的差异摘要。

    Args:
        bundle_path: 当前 Bundle 描述符路径。

    Returns:
        候选 Bundle 载荷与 rebind 预览组成的二元组。

    Raises:
        OSError: 当 Bundle、write manifest 或模板资产无法读取时。
        ValueError: 当 Bundle 缺少模板/来源绑定、manifest 漂移或候选不健康时。
        FileNotFoundError: 当 manifest 选择的模板资产不存在时。
    """
    resolved_bundle = bundle_path.resolve()
    payload = _load_json_object(resolved_bundle)
    template = str(payload.get("template", "") or "")
    if not template:
        raise ValueError("bundle template is required")
    source_binding = payload.get("source_write_manifest")
    if not isinstance(source_binding, dict):
        raise ValueError("bundle does not contain a source_write_manifest binding")
    source_path_raw = source_binding.get("path")
    if not isinstance(source_path_raw, str) or not source_path_raw.strip():
        raise ValueError("bundle source_write_manifest.path is required")
    source_path = Path(source_path_raw).resolve()
    refreshed_binding = _build_source_write_manifest_binding(source_path, expected_template=template)
    candidate = deepcopy(payload)
    candidate["source_write_manifest"] = refreshed_binding
    validation = validate_research_template_bundle_descriptor(candidate)
    if validation.get("ok") is not True:
        raise ValueError(f"bundle rebind candidate is unhealthy: {validation.get('errors', [])}")
    return candidate, {
        "bundle_file": str(resolved_bundle),
        "template": template,
        "source_manifest_file": str(source_path),
        "changed": refreshed_binding != source_binding,
        "semantic_fingerprint_before": str(source_binding.get("semantic_fingerprint", "") or ""),
        "semantic_fingerprint_after": str(refreshed_binding["semantic_fingerprint"]),
        "file_fingerprint_before": str(source_binding.get("file_fingerprint", "") or ""),
        "file_fingerprint_after": str(refreshed_binding["file_fingerprint"]),
        "validation": validation,
    }


def build_research_template_bundle_rebind_rollback_preview(
    bundle_path: Path,
    backup_path: Path,
) -> dict[str, object]:
    """验证 rebind 备份的目录、内容寻址文件名、稳定字段与恢复健康度。

    Args:
        bundle_path: 当前 Bundle 描述符路径。
        backup_path: 待验证或恢复的 rebind 内容寻址备份路径。

    Returns:
        包含恢复前后指纹、变更标志和恢复候选验证的无写入预览。

    Raises:
        FileNotFoundError: 当当前 Bundle 或指定备份不存在时。
        OSError: 当 Bundle 或备份无法读取、哈希或解析时。
        ValueError: 当备份目录、文件名、稳定字段或来源绑定不匹配时。
    """

    resolved_bundle = bundle_path.resolve()
    resolved_backup = backup_path.resolve()
    if resolved_backup.parent != resolved_bundle.parent:
        raise ValueError("bundle rebind backup must be in the same directory as the bundle")
    if not resolved_bundle.is_file() or not resolved_backup.is_file():
        raise FileNotFoundError("bundle and rebind backup must both exist")
    backup_fingerprint = _sha256_file(resolved_backup)
    expected_name = f"{resolved_bundle.stem}.before-rebind.{backup_fingerprint[:12]}.json"
    if resolved_backup.name != expected_name:
        raise ValueError(f"bundle rebind backup filename mismatch: expected {expected_name!r}")
    current_payload = _load_json_object(resolved_bundle)
    backup_payload = _load_json_object(resolved_backup)
    for key in ("template", "research_target", "artifacts"):
        if backup_payload.get(key) != current_payload.get(key):
            raise ValueError(f"bundle rebind backup {key} does not match current bundle")
    current_binding = current_payload.get("source_write_manifest")
    backup_binding = backup_payload.get("source_write_manifest")
    if not isinstance(current_binding, dict) or not isinstance(backup_binding, dict):
        raise ValueError("bundle and rebind backup must contain source_write_manifest bindings")
    if backup_binding.get("path") != current_binding.get("path"):
        raise ValueError("bundle rebind backup source manifest path does not match current bundle")
    current_fingerprint = _sha256_file(resolved_bundle)
    restored_validation = validate_research_template_bundle_descriptor(backup_payload)
    return {
        "bundle_file": str(resolved_bundle),
        "backup_file": str(resolved_backup),
        "changed": current_fingerprint != backup_fingerprint,
        "bundle_fingerprint_before": current_fingerprint,
        "bundle_fingerprint_after": backup_fingerprint,
        "restored_validation": restored_validation,
        "restored_will_be_healthy": restored_validation.get("ok") is True,
    }


def write_research_template_bundle_rebind_rollback(
    bundle_path: Path,
    backup_path: Path,
) -> dict[str, object]:
    """保存当前 Bundle 的可重做快照后恢复 rebind 备份的精确字节。

    Args:
        bundle_path: 当前 Bundle 描述符路径。
        backup_path: 待验证或恢复的 rebind 内容寻址备份路径。

    Returns:
        包含应用状态、redo 备份、恢复指纹和恢复后验证结果的报告。

    Raises:
        FileNotFoundError: 当当前 Bundle 或指定备份不存在时。
        OSError: 当 Bundle、备份、redo 快照或目标文件无法读写时。
        ValueError: 当预览无效、redo 碰撞或恢复字节指纹不匹配时。
    """

    preview = build_research_template_bundle_rebind_rollback_preview(bundle_path, backup_path)
    resolved_bundle = Path(str(preview["bundle_file"]))
    resolved_backup = Path(str(preview["backup_file"]))
    if preview["changed"] is not True:
        return {**preview, "applied": False, "redo_backup_file": None}
    current_fingerprint = str(preview["bundle_fingerprint_before"])
    redo_backup_path = resolved_bundle.with_name(
        f"{resolved_bundle.stem}.before-rebind.{current_fingerprint[:12]}.json"
    )
    if redo_backup_path.exists():
        if not redo_backup_path.is_file() or _sha256_file(redo_backup_path) != current_fingerprint:
            raise ValueError(f"bundle rebind redo backup collision: {redo_backup_path}")
    else:
        redo_backup_path.write_bytes(resolved_bundle.read_bytes())
    resolved_bundle.write_bytes(resolved_backup.read_bytes())
    restored_fingerprint = _sha256_file(resolved_bundle)
    if restored_fingerprint != preview["bundle_fingerprint_after"]:
        raise ValueError("bundle rebind rollback did not restore the expected bytes")
    restored_validation = validate_research_template_bundle_descriptor(_load_json_object(resolved_bundle))
    return {
        **preview,
        "applied": True,
        "redo_backup_file": str(redo_backup_path),
        "restored_validation": restored_validation,
        "restored_will_be_healthy": restored_validation.get("ok") is True,
    }


def discover_research_template_bundles(
    workspace_root: Path,
    *,
    recursive: bool = False,
) -> tuple[dict[str, object], ...]:
    """发现标准工作区中的 Bundle 描述符，并逐个返回容错检查结果。

    Args:
        workspace_root: 研究工作区根目录。
        recursive: 是否递归包含 ticker 等子工作区。

    Returns:
        按路径排序的 Bundle 检查结果元组。

    Raises:
        OSError: 当工作区目录 glob 遍历失败时。
    """

    paths = _discover_research_artifact_paths(workspace_root, "*.bundle.json", recursive=recursive)
    return tuple(inspect_research_template_bundle(path) for path in paths)


def write_research_template_bundle_descriptor(
    name: str,
    *,
    workspace_root: Path,
    template_file: Path,
    workbook_file: Path,
    progress_report_file: Path | None = None,
    rules_file: Path,
    source_map_file: Path,
    manifest_file: Path,
    guide_file: Path,
    checklist_file: Path,
    monitoring_validation: dict[str, object],
    research_target: dict[str, str] | None = None,
    source_write_manifest: dict[str, object] | None = None,
    output_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """构建并写入单个物化研究模板的 Bundle 描述符 JSON。

    Args:
        name: Bundle 所属研究模板的稳定名称。
        workspace_root: 研究工作区根目录。
        template_file: 物化后的研究模板文件路径。
        workbook_file: 物化后的研究工作簿文件路径。
        progress_report_file: 可选研究进度报告文件路径。
        rules_file: 物化后的监控规则文件路径。
        source_map_file: 物化后的监控 source-map 文件路径。
        manifest_file: 物化后的 package manifest 文件路径。
        guide_file: 物化后的使用指南文件路径。
        checklist_file: 物化后的研究检查单文件路径。
        monitoring_validation: 物化时得到的监控规则/source-map 验证快照。
        research_target: 可选的规范化股票代码和公司名称。
        source_write_manifest: 可选的来源 write-manifest 内容与语义指纹绑定。
        output_path: 可选自定义描述符输出路径；为空时使用标准 assets 路径。
        overwrite: 目标描述符存在时是否允许覆盖。

    Returns:
        实际写入的 Bundle 描述符绝对路径。

    Raises:
        ValueError: 当模板名无效时。
        FileNotFoundError: 当指定模板资产不存在时。
        FileExistsError: 当目标已存在且 ``overwrite`` 为 false 时。
        OSError: 当模板读取、目录创建或描述符写入失败时。
    """

    normalized = _normalize_template_name(name)
    payload = build_research_template_bundle_descriptor(
        normalized,
        template_file=template_file,
        workbook_file=workbook_file,
        progress_report_file=progress_report_file,
        rules_file=rules_file,
        source_map_file=source_map_file,
        manifest_file=manifest_file,
        guide_file=guide_file,
        checklist_file=checklist_file,
        monitoring_validation=monitoring_validation,
        research_target=research_target,
        source_write_manifest=source_write_manifest,
    )
    target_path = output_path or workspace_root / "assets" / _TEMPLATE_DIR_NAME / f"{normalized}.bundle.json"
    target_path = target_path.resolve()
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"{target_path} already exists; pass --overwrite to replace it")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target_path
