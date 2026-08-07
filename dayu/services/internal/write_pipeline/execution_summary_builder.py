"""运行摘要构建模块。

该模块只负责从章节结果聚合最终运行摘要，
不承担任何文件读写职责。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from dayu.services.contracts import WriteRunConfig
from dayu.services.internal.write_pipeline.enums import (
    AUDIT_WRITE_SCENES,
    PRIMARY_MODEL_WRITE_SCENES,
    WriteSceneName,
)
from dayu.services.internal.write_pipeline.models import ChapterResult


_SUMMARY_SCHEMA_VERSION = "write_run_summary_v3"


def _utc_timestamp(value: datetime | None = None) -> str:
    """Return a second-precision UTC timestamp for the immutable run receipt."""

    resolved = value or datetime.now(UTC)
    if resolved.tzinfo is None:
        raise ValueError("completed_at must include timezone information")
    return (
        resolved.astimezone(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _dict_entries(value: object) -> list[dict[str, Any]]:
    """Return dictionary entries from a persisted process-state collection."""

    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _non_negative_int(value: object) -> int:
    """Return a safe non-negative integer for persisted counters."""

    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _build_model_role_summary(
    *,
    write_config: WriteRunConfig,
    scene_names: tuple[WriteSceneName, ...],
) -> dict[str, Any]:
    """Build a stable, credential-free model-role summary."""

    scenes: list[dict[str, Any]] = []
    for raw_scene_name in scene_names:
        scene_name = str(raw_scene_name)
        config = write_config.scene_models.get(scene_name)
        if config is None:
            continue
        scenes.append(
            {
                "scene_name": scene_name,
                "model_name": config.name,
                "temperature": config.temperature,
            }
        )
    return {
        "model_names": sorted({str(scene["model_name"]) for scene in scenes}),
        "scenes": scenes,
    }


def _build_chapter_summary(
    result: ChapterResult,
    *,
    gate_passed: bool,
    run_audit_required: bool,
) -> dict[str, Any]:
    """Build one compact chapter quality record from persisted state."""

    process_state = result.process_state if isinstance(result.process_state, dict) else {}
    audit_entries = _dict_entries(process_state.get("audit_history"))
    confirmation_entries = _dict_entries(process_state.get("confirm_history"))
    anchor_rewrite_entries = _dict_entries(process_state.get("anchor_rewrite_history"))
    final_stage_value = process_state.get("final_stage")
    final_stage = (
        final_stage_value.strip()
        if isinstance(final_stage_value, str) and final_stage_value.strip()
        else "unknown"
    )
    retry_count = _non_negative_int(result.retry_count)
    audit_required = run_audit_required and process_state.get("audit_skipped") is not True

    if not gate_passed:
        outcome = "blocked"
    elif not audit_required:
        outcome = "passed_without_audit"
    elif retry_count > 0:
        outcome = "passed_after_repair"
    else:
        outcome = "passed_first_attempt"

    return {
        "index": result.index,
        "title": result.title,
        "status": result.status,
        "audit_required": audit_required,
        "audit_passed": bool(result.audit_passed),
        "gate_passed": gate_passed,
        "outcome": outcome,
        "retry_count": retry_count,
        "failure_reason": result.failure_reason,
        "final_stage": final_stage,
        "audit_attempt_count": len(audit_entries),
        "confirmation_check_count": sum(
            _non_negative_int(entry.get("entries_count")) for entry in confirmation_entries
        ),
        "anchor_rewrite_count": sum(1 for entry in anchor_rewrite_entries if entry.get("applied") is True),
    }


class ExecutionSummaryBuilder:
    """运行摘要构建器。"""

    def __init__(self, *, write_config: WriteRunConfig) -> None:
        """初始化运行摘要构建器。

        Args:
            write_config: 写作运行配置。

        Returns:
            无。

        Raises:
            无。
        """

        self._write_config = write_config

    def build_summary(
        self,
        chapter_results: dict[str, ChapterResult],
        *,
        output_file: Path,
        success_predicate: Callable[[ChapterResult | None], bool],
        model_usage: dict[str, Any] | None = None,
        model_routing: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        completed_at: datetime | None = None,
    ) -> dict[str, Any]:
        """生成运行摘要。

        Args:
            chapter_results: 章节结果映射。
            output_file: 最终报告路径。
            success_predicate: 判断章节是否成功的谓词函数。

        Returns:
            摘要字典。

        Raises:
            无。
        """

        audit_required = not self._write_config.fast
        budget_summary = budget or {
            "enabled": False,
            "status": "disabled",
            "block": None,
        }
        budget_blocked = budget_summary.get("status") == "blocked"
        ordered_results = sorted(chapter_results.values(), key=lambda item: (item.index, item.title))
        chapters = [
            _build_chapter_summary(
                result,
                gate_passed=bool(success_predicate(result)),
                run_audit_required=audit_required,
            )
            for result in ordered_results
        ]
        failed = [
            {
                "title": chapter["title"],
                "reason": chapter["failure_reason"],
                "retry_count": chapter["retry_count"],
            }
            for chapter in chapters
            if not chapter["gate_passed"]
        ]
        auditable_chapters = [chapter for chapter in chapters if chapter["audit_required"]]
        audit_passed_count = sum(1 for chapter in auditable_chapters if chapter["audit_passed"])
        audit_failed_count = sum(1 for chapter in auditable_chapters if not chapter["audit_passed"])
        return {
            "schema_version": _SUMMARY_SCHEMA_VERSION,
            "completed_at": _utc_timestamp(completed_at),
            "ticker": self._write_config.ticker,
            "output_file": str(output_file),
            "gate_status": "blocked" if failed or budget_blocked else "passed",
            "publication_status": (
                "blocked_by_budget" if budget_blocked else "published"
            ),
            "model_roles": {
                "primary": _build_model_role_summary(
                    write_config=self._write_config,
                    scene_names=PRIMARY_MODEL_WRITE_SCENES,
                ),
                "audit": _build_model_role_summary(
                    write_config=self._write_config,
                    scene_names=AUDIT_WRITE_SCENES,
                ),
            },
            "model_usage": model_usage or {},
            "model_routing": (
                model_routing
                if model_routing is not None
                else {
                    "fallback_switch_count": 0,
                    "fallback_call_completed_count": 0,
                    "fallback_call_error_count": 0,
                    "routes": [],
                }
            ),
            "budget": budget_summary,
            "chapter_count": len(chapters),
            "failed_count": len(failed),
            "failed_chapters": failed,
            "audit": {
                "required": audit_required,
                "passed_count": audit_passed_count,
                "failed_count": audit_failed_count,
                "skipped_count": len(chapters) - len(auditable_chapters),
                "gate_blocked_count": sum(
                    1
                    for chapter in auditable_chapters
                    if chapter["audit_passed"] and not chapter["gate_passed"]
                ),
                "first_pass_count": sum(
                    1 for chapter in chapters if chapter["outcome"] == "passed_first_attempt"
                ),
                "repaired_pass_count": sum(
                    1 for chapter in chapters if chapter["outcome"] == "passed_after_repair"
                ),
                "total_retries": sum(int(chapter["retry_count"]) for chapter in chapters),
                "audit_attempt_count": sum(int(chapter["audit_attempt_count"]) for chapter in chapters),
                "confirmation_check_count": sum(
                    int(chapter["confirmation_check_count"]) for chapter in chapters
                ),
                "anchor_rewrite_count": sum(
                    int(chapter["anchor_rewrite_count"]) for chapter in chapters
                ),
            },
            "chapters": chapters,
        }
