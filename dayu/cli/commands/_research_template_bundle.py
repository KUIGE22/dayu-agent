"""提供研究模板 Bundle 的描述、验证、重绑定与回滚操作。

本模块同时是旧 workspace 显式导入（Slice 1.5）所需 typed strict
closure inspection 的 owner：``inspect_research_template_bundle_closure``
返回 frozen slots 的 closure DTO，只暴露 relative locator / size / hash
与规范 target，不暴露 absolute path / raw bytes / 宽 dict。
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from dayu.cli._research_artifact_content import (
    JsonValue,
    ResearchArtifactContentReader,
    decode_utf8_sig,
    sha256_hex,
    validate_json_object_text,
)
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
    *,
    content_reader: ResearchArtifactContentReader | None = None,
) -> list[str]:
    """从当前规则和 source-map 文件重新计算 Bundle 的监控一致性与绑定批准来源。

    Args:
        template: Bundle 声明的规范模板名。
        rules_path_raw: 描述符中 monitoring_rules 路径的原始值。
        source_map_path_raw: 描述符中 source_map 路径的原始值。
        content_reader: 可选闭包快照 reader；非 None 时内容只来自该
            reader，禁止普通路径重读。

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
    if not _reader_aware_is_regular_file(rules_path, content_reader) or not _reader_aware_is_regular_file(
        source_map_path, content_reader
    ):
        return errors
    try:
        rules_payload = _load_json_object(rules_path, content_reader=content_reader)
        source_map_payload = _load_json_object(source_map_path, content_reader=content_reader)
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
    *,
    content_reader: ResearchArtifactContentReader | None = None,
) -> list[str]:
    """根据 Bundle 模板重新渲染检查单，并与当前文件内容比较。

    Args:
        template: Bundle 声明的规范模板名。
        checklist_path_raw: 描述符中 research_checklist 路径的原始值。
        content_reader: 可选闭包快照 reader；非 None 时内容只来自该
            reader，禁止普通路径重读。

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
    if not _reader_aware_is_regular_file(checklist_path, content_reader):
        return errors
    try:
        definition = load_research_template_definition(template)
        expected_markdown = render_research_checklist_markdown(definition)
        if content_reader is None:
            actual_markdown = checklist_path.read_text(encoding="utf-8")
        else:
            actual_markdown = content_reader.read_bytes(checklist_path).decode("utf-8")
    except (OSError, ValueError) as exc:
        errors.append(f"checklist integrity could not be recomputed: {exc}")
        return errors
    if actual_markdown != expected_markdown:
        errors.append(f"checklist integrity: checklist does not match the bundle template definition for {template!r}")
    return errors


def _reader_aware_is_regular_file(
    path: Path,
    content_reader: ResearchArtifactContentReader | None,
) -> bool:
    """reader 模式只查询快照，None 模式保持原 ``Path.is_file`` 语义。

    Args:
        path: 待查询的路径。
        content_reader: 可选闭包快照 reader。

    Returns:
        该路径是否为 regular 文件。

    Raises:
        无。
    """
    if content_reader is None:
        return path.is_file()
    return content_reader.is_regular_file(path)


def _reader_aware_resolved_path(
    path: Path,
    content_reader: ResearchArtifactContentReader | None,
) -> Path:
    """reader 模式直接使用 descriptor 原始 canonical 路径，避免 ``resolve``。

    Args:
        path: 待解析的路径。
        content_reader: 可选闭包快照 reader。

    Returns:
        None 模式返回 ``path.resolve()``；reader 模式原样返回。

    Raises:
        OSError: None 模式下底层 resolve 失败时抛出。
    """
    if content_reader is None:
        return path.resolve()
    return path


def validate_research_template_bundle_descriptor(
    payload: dict[str, object],
    *,
    content_reader: ResearchArtifactContentReader | None = None,
) -> dict[str, object]:
    """校验 Bundle schema、产物存在性、指纹、工作簿、报告和监控一致性。

    Args:
        payload: 待验证的 Bundle 描述符载荷。
        content_reader: 可选闭包快照 reader；非 None 时 source-tree 的
            ``is_file``/JSON/text/hash、company facets、template selection
            与 workbook report 读取只能来自该 reader，禁止再次以普通
            ``Path`` 打开/读取/``resolve`` 重读 source-tree。package
            research-template assets 仍由原 package owner 读取。为 None
            时保持既有行为与原错误/返回语义。

    Returns:
        包含 ``ok``、错误、警告、模板、产物计数及子验证结果的报告。

    Raises:
        OSError: 当下游工作簿报告检查无法读取引用文件且传播底层错误时。
        ValueError: 当下游工作簿报告检查传播无法收敛的内容错误时。
        ResearchBundleClosureError: reader 模式遇到快照缺失等 fail-closed
            条件时抛出。
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
                if not _reader_aware_is_regular_file(source_path, content_reader):
                    errors.append(f"source_write_manifest.path does not exist: {source_path}")
                else:
                    source_path_for_reads = _reader_aware_resolved_path(source_path, content_reader)
                    try:
                        current_semantics = _build_write_manifest_binding_semantics(
                            source_path_for_reads,
                            content_reader=content_reader,
                        )
                        semantic_matches = _sha256_json_object(current_semantics) == source_semantic_fingerprint
                        if not semantic_matches:
                            errors.append("source_write_manifest semantic fingerprint is stale")
                        if semantic_matches and _sha256_file(
                            source_path_for_reads,
                            content_reader=content_reader,
                        ) != source_file_fingerprint:
                            warnings.append("source_write_manifest file changed without selection drift")
                        current_template, _current_selection = _resolve_template_selection_from_write_manifest(
                            source_path_for_reads,
                            content_reader=content_reader,
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
            elif not _reader_aware_is_regular_file(Path(path_raw), content_reader):
                errors.append(f"artifacts.{key} does not exist: {path_raw}")
        extra_keys = sorted(str(key) for key in artifacts if key not in _BUNDLE_ARTIFACT_KEYS)
        if extra_keys:
            warnings.append(f"unknown artifact entries: {', '.join(extra_keys)}")
        errors.extend(
            _recompute_bundle_monitoring_integrity(
                template,
                artifacts.get("monitoring_rules"),
                artifacts.get("source_map"),
                content_reader=content_reader,
            )
        )
        errors.extend(
            _recompute_bundle_checklist_integrity(
                template,
                artifacts.get("research_checklist"),
                content_reader=content_reader,
            )
        )
        workbook_raw = artifacts.get("research_workbook")
        if (
            isinstance(workbook_raw, str)
            and workbook_raw.strip()
            and _reader_aware_is_regular_file(Path(workbook_raw), content_reader)
        ):
            try:
                workbook_payload = _load_json_object(Path(workbook_raw), content_reader=content_reader)
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
            elif not _reader_aware_is_regular_file(Path(report_raw), content_reader):
                errors.append(f"artifacts.research_progress_report does not exist: {report_raw}")
            elif isinstance(workbook_raw, str) and workbook_raw.strip():
                workbook_report_validation = inspect_research_workbook_report(
                    Path(report_raw),
                    Path(workbook_raw),
                    content_reader=content_reader,
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


@dataclass(frozen=True, slots=True)
class ResearchBundleClosureFile:
    """研究模板 Bundle closure 中的单个文件条目（typed 只读结果）。

    Args:
        role: closure 内稳定角色（``descriptor`` / ``_BUNDLE_ARTIFACT_KEYS``
            之一 / ``source_write_manifest``）。
        relative_locator: 相对 source root 的 POSIX locator。
        size_bytes: 文件字节数。
        sha256: 文件 SHA-256 十六进制摘要。
    """

    role: str
    relative_locator: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ResearchBundleClosureInspection:
    """研究模板 Bundle 的 typed strict closure 检查结果。

    Args:
        template: 描述符声明的规范模板名。
        target_ticker: 描述符 research_target.ticker（规范大写 ticker）。
        target_company_name: 描述符 research_target.company（公司名称，
            不是 legacy company id）。
        descriptor_sha256: 描述符自身文件的 SHA-256。
        files: 按 ``(role, relative_locator, size_bytes, sha256)`` 排序的
            closure 文件条目元组。
        artifact_manifest_sha256: 其余 closure 条目（不含 descriptor）按
            ``(role, relative_locator, size_bytes, sha256)`` 排序后的
            canonical JSON SHA-256。
    """

    template: str
    target_ticker: str
    target_company_name: str
    descriptor_sha256: str
    files: tuple[ResearchBundleClosureFile, ...]
    artifact_manifest_sha256: str


class ResearchBundleClosureError(RuntimeError):
    """Bundle closure 不满足 strict 契约时抛出的稳定 owner 错误。

    消息只含固定类别说明，不回显 absolute path、候选值或原文。
    """


def _require_regular_contained(
    candidate_path: Path,
    resolved_source_root: Path,
) -> Path:
    """要求候选路径为 source root 内非 symlink 的 regular file。

    Args:
        candidate_path: 待校验路径。
        resolved_source_root: 已 resolve 的 source root 边界。

    Returns:
        resolve 后的路径。

    Raises:
        ResearchBundleClosureError: 路径非 regular / 是 symlink、
            FIFO、device，或 resolve 后不 contained 于 source root 时
            抛出。
        OSError: 底层文件系统访问失败时抛出。
    """

    try:
        entry_stat = candidate_path.lstat()
    except OSError as exc:
        raise ResearchBundleClosureError("bundle closure: entry cannot be inspected") from exc
    if not stat.S_ISREG(entry_stat.st_mode):
        raise ResearchBundleClosureError("bundle closure: entry is not a regular file")
    resolved_path = candidate_path.resolve()
    try:
        resolved_path.relative_to(resolved_source_root)
    except ValueError:
        raise ResearchBundleClosureError("bundle closure: entry escapes source root") from None
    return resolved_path


def _open_component_no_follow(
    parent_fd: int,
    component: str,
    *,
    expect_directory: bool,
) -> int:
    """以 no-follow 方式相对父 FD 打开单段路径组件并绑定 identity。

    先相对父 FD 执行 ``stat(follow_symlinks=False)`` 记录
    ``(st_dev, st_ino, st_mode)`` 作为 preflight identity，再以
    ``O_NOFOLLOW`` 打开并 ``fstat`` 对比 exact；preflight 与 open 之间
    的 identity race、类型不符或 symlink 均稳定拒绝，race 时关闭已获取
    的 FD。

    Args:
        parent_fd: 父目录 FD。
        component: 单段路径组件名。
        expect_directory: 该组件是否为中间目录段（否则视为 leaf 文件）。

    Returns:
        已证明 identity exact 且类型匹配的只读 FD（调用方负责关闭）。

    Raises:
        ResearchBundleClosureError: 组件缺失、类型不符、identity race
            或打开失败时抛出。
    """

    expected_type = stat.S_IFDIR if expect_directory else stat.S_IFREG
    try:
        preflight = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise ResearchBundleClosureError("bundle closure: entry cannot be inspected") from exc
    if stat.S_IFMT(preflight.st_mode) != expected_type:
        if expect_directory:
            raise ResearchBundleClosureError("bundle closure: intermediate path is not a directory")
        raise ResearchBundleClosureError("bundle closure: entry is not a regular file")
    flags = (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if expect_directory
        else os.O_RDONLY | os.O_NOFOLLOW
    )
    try:
        opened_fd = os.open(component, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise ResearchBundleClosureError(
            "bundle closure: entry cannot be opened without following"
        ) from exc
    try:
        actual = os.fstat(opened_fd)
    except OSError:
        os.close(opened_fd)
        raise ResearchBundleClosureError("bundle closure: entry cannot be inspected") from None
    if (preflight.st_dev, preflight.st_ino, preflight.st_mode) != (
        actual.st_dev,
        actual.st_ino,
        actual.st_mode,
    ):
        os.close(opened_fd)
        raise ResearchBundleClosureError("bundle closure: entry identity changed during inspection")
    return opened_fd


def _open_relative_no_follow(root_fd: int, components: tuple[str, ...]) -> int:
    """相对唯一 root capability FD 逐段 no-follow 打开并返回 leaf FD。

    每段都经 ``_open_component_no_follow`` 完成 preflight identity →
    no-follow open → ``fstat`` exact；中间目录 FD 在推进时立即关闭，
    任何异常路径（含 ``BaseException``）都会关闭已获取的中间 FD。
    root FD 不在此关闭，由调用方 ExitStack 持有。

    Args:
        root_fd: 已绑定的 source root 目录 FD（本次 inspection 唯一
            capability）。
        components: 相对 source root 的路径组件序列。

    Returns:
        已证明 regular 的只读 leaf FD（调用方负责关闭）。

    Raises:
        ResearchBundleClosureError: 任一段无法以 no-follow 方式打开、
            leaf 不是 regular file 或 identity race 时抛出。
    """

    if not components:
        raise ResearchBundleClosureError("bundle closure: entry is not a file")
    current_fd = root_fd
    try:
        for index, component in enumerate(components):
            is_leaf = index == len(components) - 1
            next_fd = _open_component_no_follow(
                current_fd,
                component,
                expect_directory=not is_leaf,
            )
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
    except BaseException:
        if current_fd != root_fd:
            os.close(current_fd)
        raise
    return current_fd


def _open_source_root_no_follow(resolved_source_root: Path) -> int:
    """从 filesystem root FD 逐段 no-follow 打开 source root 并返回根 FD。

    每段先相对父 FD 执行 ``stat(follow_symlinks=False)`` preflight，再
    ``O_NOFOLLOW`` 打开并 ``fstat`` exact；最终 root FD 与 source-root
    preflight identity exact，作为本次 inspection 唯一 capability 保持
    打开，禁止按 source-root pathname 重开。

    Args:
        resolved_source_root: 已 resolve 的 source root 绝对路径。

    Returns:
        已绑定 identity 的 source root 目录 FD（调用方负责关闭）。

    Raises:
        ResearchBundleClosureError: 任一段无法 no-follow 打开、根路径
            不是目录或 identity race 时抛出。
    """

    try:
        preflight = os.stat(resolved_source_root, follow_symlinks=False)
    except OSError as exc:
        raise ResearchBundleClosureError("bundle closure: source root cannot be inspected") from exc
    if not stat.S_ISDIR(preflight.st_mode):
        raise ResearchBundleClosureError("bundle closure: source root is not a directory")
    try:
        root_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        raise ResearchBundleClosureError("bundle closure: source root cannot be inspected") from exc
    try:
        for component in resolved_source_root.parts[1:]:
            next_fd = _open_component_no_follow(root_fd, component, expect_directory=True)
            os.close(root_fd)
            root_fd = next_fd
        actual = os.fstat(root_fd)
    except BaseException:
        os.close(root_fd)
        raise
    if (preflight.st_dev, preflight.st_ino, preflight.st_mode) != (
        actual.st_dev,
        actual.st_ino,
        actual.st_mode,
    ):
        os.close(root_fd)
        raise ResearchBundleClosureError("bundle closure: source root identity changed during inspection")
    return root_fd


def _read_fd_bytes(fd: int) -> bytes:
    """从已绑定 FD 一次性读取全部字节（不接管 FD 所有权）。

    Args:
        fd: 已绑定且保持打开的只读 FD。

    Returns:
        文件完整字节。

    Raises:
        ResearchBundleClosureError: 读取失败时抛出。
    """

    chunks: list[bytes] = []
    try:
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except OSError as exc:
        raise ResearchBundleClosureError("bundle closure: entry could not be read") from exc


def _canonicalize_member_reference(
    reference_path: Path,
    resolved_source_root: Path,
) -> tuple[str, str, tuple[str, ...]]:
    """对 descriptor reference 做纯词法 canonicalization（零 filesystem I/O）。

    Args:
        reference_path: descriptor 中的原始引用路径。
        resolved_source_root: 已 resolve 的 source root 边界。

    Returns:
        ``(raw canonical absolute string, canonical POSIX relative
        locator, relative path components)`` 三元组。

    Raises:
        ResearchBundleClosureError: 引用非 canonical absolute、含 NUL/
            混合分隔符/lexical ``.``/``..``、逃逸 source root 或 raw 不
            精确等于 ``resolved_source_root / canonical relative locator``
            时抛出。
    """

    raw = str(reference_path)
    if not raw or "\x00" in raw or "\\" in raw or not raw.startswith("/"):
        raise ResearchBundleClosureError("bundle closure: reference path invalid")
    if not Path(raw).is_absolute():
        raise ResearchBundleClosureError("bundle closure: reference path invalid")
    if any(part in (".", "..") for part in Path(raw).parts):
        raise ResearchBundleClosureError("bundle closure: reference path invalid")
    try:
        relative = Path(raw).relative_to(resolved_source_root)
    except ValueError:
        raise ResearchBundleClosureError("bundle closure: reference escapes source root") from None
    relative_locator = relative.as_posix()
    canonical_raw = str(resolved_source_root / relative_locator)
    if raw != canonical_raw:
        raise ResearchBundleClosureError("bundle closure: reference path is not canonical")
    return raw, relative_locator, relative.parts


class _ClosureSnapshotReader:
    """把已绑定 member bytes 提供给 validator 的只读 reader 实现。

    只做 ``str(path)`` exact map lookup，不调用 filesystem；unknown
    key 一律 fail closed。
    """

    def __init__(self, snapshot: Mapping[str, bytes]) -> None:
        self._snapshot = snapshot

    def is_regular_file(self, path: Path) -> bool:
        """返回该路径 key 是否命中快照条目。

        Args:
            path: descriptor reference 的 opaque lookup key。

        Returns:
            命中时返回 True，否则返回 False。

        Raises:
            无。
        """
        return str(path) in self._snapshot

    def read_bytes(self, path: Path) -> bytes:
        """返回该路径 key 对应的 immutable bytes。

        Args:
            path: descriptor reference 的 opaque lookup key。

        Returns:
            快照绑定的文件完整字节。

        Raises:
            ResearchBundleClosureError: 该 key 不在快照中时 fail closed。
        """
        try:
            return self._snapshot[str(path)]
        except KeyError:
            raise ResearchBundleClosureError("bundle closure: snapshot member missing") from None


def _enumerate_closure_reference_paths(
    payload: Mapping[str, JsonValue],
) -> tuple[tuple[str, Path], ...]:
    """枚举 descriptor 中全部 closure 引用路径（纯结构检查，无文件访问）。

    Args:
        payload: 已解析的 bundle descriptor 载荷。

    Returns:
        ``(role, 原始路径)`` 元组序列；含全部 artifact role 与可选的
        ``source_write_manifest``。

    Raises:
        ResearchBundleClosureError: 结构违反 strict closure 契约时抛出。
    """

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ResearchBundleClosureError("bundle closure: artifacts missing")
    artifact_keys = set(artifacts)
    if not artifact_keys.issubset(set(_BUNDLE_ARTIFACT_KEYS)):
        raise ResearchBundleClosureError("bundle closure: unknown artifact key")
    required_keys: set[str] = set(_BUNDLE_ARTIFACT_KEYS)
    required_keys.discard("research_progress_report")
    if not required_keys.issubset(artifact_keys):
        raise ResearchBundleClosureError("bundle closure: required artifact missing")
    references: list[tuple[str, Path]] = []
    for role in sorted(artifact_keys):
        path_raw = artifacts.get(role)
        if not isinstance(path_raw, str) or not path_raw.strip():
            raise ResearchBundleClosureError("bundle closure: artifact path invalid")
        references.append((role, Path(path_raw)))
    source_write_manifest = payload.get("source_write_manifest")
    if source_write_manifest is not None:
        if not isinstance(source_write_manifest, dict):
            raise ResearchBundleClosureError("bundle closure: source manifest invalid")
        manifest_path_raw = source_write_manifest.get("path")
        if not isinstance(manifest_path_raw, str) or not manifest_path_raw.strip():
            raise ResearchBundleClosureError("bundle closure: source manifest path invalid")
        references.append(("source_write_manifest", Path(manifest_path_raw)))
    return tuple(references)


def inspect_research_template_bundle_closure(
    bundle_path: Path,
    source_root: Path,
) -> ResearchBundleClosureInspection:
    """检查研究模板 Bundle 的 strict closure（typed 只读 API）。

    closure exact membership 为：descriptor 自身、
    ``_BUNDLE_ARTIFACT_KEYS`` 中全部 required artifact、存在时的
    optional ``research_progress_report``、存在时的
    ``source_write_manifest.path``；不递归展开 write manifest 指向的
    其它内容。

    descriptor 先以 ``lstat`` 证明 non-symlink regular 且 resolve 后
    contained 于 ``source_root``。随后执行 S15-CTRL-15 的两阶段
    FD acquisition：

    1. 从 filesystem root 逐段 no-follow 打开并绑定唯一 source root
       capability FD（禁止按 pathname 重开）；
    2. descriptor 相对 root FD 逐段 preflight identity → no-follow open
       → ``fstat`` exact，仅从该 FD 读取一次并 strict parse 得到
       immutable payload；
    3. 对 immutable payload 纯词法枚举全部 member reference 并做
       canonical absolute reference canonicalization；
    4. 全部 member 逐段 preflight identity → no-follow open → ``fstat``
       exact 并保持全部 leaf FD 打开；全部 member FD 成功绑定后才从
       各 FD 读取一次，形成供 validator 共用的 immutable bytes
       snapshot；
    5. 复用既有 descriptor validator，且只以快照 reader 消费 member
       bytes（reader lookup 零 filesystem I/O）。

    任意 symlink/escape/non-regular/identity race/root 替换、owner
    validation non-ok 或 source manifest stale 均抛稳定
    ``ResearchBundleClosureError``。root/intermediate/descriptor/member
    FD 以 ``ExitStack`` 在 success/exception/``BaseException`` 路径
    exact close，不落盘临时正文。本函数只读取文件，不修改任何内容。

    Args:
        bundle_path: Bundle 描述符路径。
        source_root: legacy workspace source root（containment 边界）。

    Returns:
        只含 relative locator / size / hash 与规范 target 的 typed
        closure 结果。

    Raises:
        ResearchBundleClosureError: closure 契约任一违反时抛出。
        OSError: 底层文件系统访问失败时抛出。
    """

    resolved_source_root = source_root.resolve()
    resolved_bundle = _require_regular_contained(bundle_path, resolved_source_root)

    with ExitStack() as stack:
        root_fd = _open_source_root_no_follow(resolved_source_root)
        stack.callback(os.close, root_fd)

        descriptor_parts = resolved_bundle.relative_to(resolved_source_root).parts
        descriptor_fd = _open_relative_no_follow(root_fd, descriptor_parts)
        stack.callback(os.close, descriptor_fd)
        descriptor_bytes = _read_fd_bytes(descriptor_fd)
        try:
            payload = json.loads(validate_json_object_text(decode_utf8_sig(descriptor_bytes)))
        except (ValueError, UnicodeError) as exc:
            raise ResearchBundleClosureError("bundle closure: descriptor could not be loaded") from exc

        template = str(payload.get("template", "") or "")
        research_target = payload.get("research_target")
        if not isinstance(research_target, dict):
            raise ResearchBundleClosureError("bundle closure: research_target missing")
        target_ticker = research_target.get("ticker")
        target_company_name = research_target.get("company")
        if not isinstance(target_ticker, str) or not isinstance(target_company_name, str):
            raise ResearchBundleClosureError("bundle closure: research_target invalid")

        reference_paths = _enumerate_closure_reference_paths(payload)
        member_specs: list[tuple[str, str, str, tuple[str, ...]]] = []
        for role, reference_path in reference_paths:
            raw, relative_locator, relative_parts = _canonicalize_member_reference(
                reference_path,
                resolved_source_root,
            )
            member_specs.append((role, raw, relative_locator, relative_parts))

        member_fds: list[int] = []
        for _role, _raw, _relative_locator, relative_parts in member_specs:
            member_fd = _open_relative_no_follow(root_fd, relative_parts)
            stack.callback(os.close, member_fd)
            member_fds.append(member_fd)

        snapshot: dict[str, bytes] = {}
        for (_role, raw, _relative_locator, _relative_parts), member_fd in zip(
            member_specs,
            member_fds,
        ):
            snapshot[raw] = _read_fd_bytes(member_fd)

        validation = validate_research_template_bundle_descriptor(
            payload,
            content_reader=_ClosureSnapshotReader(snapshot),
        )
        if validation.get("ok") is not True:
            raise ResearchBundleClosureError("bundle closure: owner validation failed")

        descriptor_entry = ResearchBundleClosureFile(
            role="descriptor",
            relative_locator=resolved_bundle.relative_to(resolved_source_root).as_posix(),
            size_bytes=len(descriptor_bytes),
            sha256=sha256_hex(descriptor_bytes),
        )
        member_entries = [
            ResearchBundleClosureFile(
                role=role,
                relative_locator=relative_locator,
                size_bytes=len(snapshot[raw]),
                sha256=sha256_hex(snapshot[raw]),
            )
            for (role, raw, relative_locator, _relative_parts) in member_specs
        ]
        entries = [descriptor_entry, *member_entries]

    sorted_entries = tuple(
        sorted(entries, key=lambda item: (item.role, item.relative_locator, item.size_bytes, item.sha256))
    )
    descriptor_entry = next(entry for entry in sorted_entries if entry.role == "descriptor")
    descriptor_sha256 = descriptor_entry.sha256
    artifact_entries = [entry for entry in sorted_entries if entry.role != "descriptor"]
    canonical_manifest = json.dumps(
        [
            [entry.role, entry.relative_locator, entry.size_bytes, entry.sha256]
            for entry in artifact_entries
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    artifact_manifest_sha256 = hashlib.sha256(canonical_manifest.encode("utf-8")).hexdigest()
    return ResearchBundleClosureInspection(
        template=template,
        target_ticker=target_ticker,
        target_company_name=target_company_name,
        descriptor_sha256=descriptor_sha256,
        files=sorted_entries,
        artifact_manifest_sha256=artifact_manifest_sha256,
    )


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
