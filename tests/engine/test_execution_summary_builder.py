"""运行摘要构建模块测试。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from dayu.services.contracts import SceneModelConfig
from dayu.services.internal.write_pipeline.execution_summary_builder import ExecutionSummaryBuilder
from dayu.services.internal.write_pipeline.models import ChapterResult

from tests.engine.test_write_pipeline import _build_runner


@pytest.mark.unit
def test_build_summary_collects_failed_chapters(tmp_path: Path) -> None:
    """验证运行摘要会正确聚合失败章节信息。"""

    runner = _build_runner(tmp_path)
    builder = ExecutionSummaryBuilder(write_config=runner._write_config)
    chapter_results = {
        "公司介绍": ChapterResult(
            index=1,
            title="公司介绍",
            status="passed",
            content="ok",
            audit_passed=True,
        ),
        "竞争优势": ChapterResult(
            index=2,
            title="竞争优势",
            status="failed",
            content="",
            audit_passed=False,
            retry_count=2,
            failure_reason="evidence_insufficient",
        ),
    }

    result = builder.build_summary(
        chapter_results,
        output_file=Path("/tmp/report.md"),
        success_predicate=lambda item: bool(item and item.status == "passed"),
    )

    assert result["ticker"] == "AAPL"
    assert result["chapter_count"] == 2
    assert result["failed_count"] == 1
    assert result["failed_chapters"] == [
        {
            "title": "竞争优势",
            "reason": "evidence_insufficient",
            "retry_count": 2,
        }
    ]


@pytest.mark.unit
def test_build_summary_emits_dual_model_quality_receipt(tmp_path: Path) -> None:
    """验证运行摘要会聚合双模型职责、审计轨迹和章节门禁结果。"""

    runner = _build_runner(tmp_path)
    write_config = replace(
        runner._write_config,
        scene_models={
            "write": SceneModelConfig(name="deepseek-v4-pro", temperature=1.3),
            "regenerate": SceneModelConfig(name="deepseek-v4-pro", temperature=1.1),
            "fix": SceneModelConfig(name="deepseek-v4-pro", temperature=0.8),
            "repair": SceneModelConfig(name="deepseek-v4-pro", temperature=0.8),
            "overview": SceneModelConfig(name="deepseek-v4-pro", temperature=1.0),
            "infer": SceneModelConfig(name="mimo-v2.5-pro-thinking", temperature=0.2),
            "decision": SceneModelConfig(name="mimo-v2.5-pro-thinking", temperature=0.6),
            "audit": SceneModelConfig(name="mimo-v2.5-pro-thinking", temperature=0.2),
            "confirm": SceneModelConfig(name="mimo-v2.5-pro-thinking", temperature=0.2),
        },
    )
    builder = ExecutionSummaryBuilder(write_config=write_config)
    chapter_results = {
        "竞争优势": ChapterResult(
            index=2,
            title="竞争优势",
            status="passed",
            content="repaired",
            audit_passed=True,
            retry_count=2,
            process_state={
                "audit_history": [{"phase": "initial"}, {"phase": "rewrite_1"}, {"phase": "rewrite_2"}],
                "confirm_history": [{"entries_count": 2}, {"entries_count": 1}],
                "anchor_rewrite_history": [{"applied": False}, {"applied": True}],
                "final_stage": "complete",
            },
        ),
        "公司介绍": ChapterResult(
            index=1,
            title="公司介绍",
            status="passed",
            content="ok",
            audit_passed=True,
            process_state={
                "audit_history": [{"phase": "initial"}],
                "confirm_history": [],
                "anchor_rewrite_history": [],
                "final_stage": "complete",
            },
        ),
        "风险": ChapterResult(
            index=3,
            title="风险",
            status="failed",
            content="partial",
            # 模拟旧 manifest 中 status 与 audit 标志不一致；运行门禁仍应优先。
            audit_passed=True,
            retry_count=1,
            failure_reason="runtime_failure_after_audit",
            process_state={
                "audit_history": "legacy-invalid-value",
                "confirm_history": [{"entries_count": "invalid"}],
                "anchor_rewrite_history": [None],
                "final_stage": 42,
            },
        ),
    }

    model_usage = {
        "usage_status": "complete",
        "scene_call_count": 2,
        "total_tokens": 1234,
    }
    model_routing = {
        "fallback_switch_count": 1,
        "fallback_call_completed_count": 1,
        "fallback_call_error_count": 0,
        "routes": [
            {
                "scene_name": "write",
                "primary_model_name": "deepseek-v4-pro",
                "fallback_model_name": "mimo-v2.5-pro",
                "trigger_error_types": ["model_circuit_open"],
                "fallback_call_status": "completed",
                "fallback_error_types": [],
                "switch_count": 1,
            }
        ],
    }
    result = builder.build_summary(
        chapter_results,
        output_file=Path("/tmp/report.md"),
        success_predicate=lambda item: bool(item and item.status == "passed" and item.audit_passed),
        model_usage=model_usage,
        model_routing=model_routing,
    )

    assert result["schema_version"] == "write_run_summary_v3"
    assert result["completed_at"].endswith("Z")
    assert result["model_usage"] == model_usage
    assert result["model_routing"] == model_routing
    assert result["gate_status"] == "blocked"
    assert result["model_roles"] == {
        "primary": {
            "model_names": ["deepseek-v4-pro"],
            "scenes": [
                {"scene_name": "write", "model_name": "deepseek-v4-pro", "temperature": 1.3},
                {"scene_name": "regenerate", "model_name": "deepseek-v4-pro", "temperature": 1.1},
                {"scene_name": "fix", "model_name": "deepseek-v4-pro", "temperature": 0.8},
                {"scene_name": "repair", "model_name": "deepseek-v4-pro", "temperature": 0.8},
                {"scene_name": "overview", "model_name": "deepseek-v4-pro", "temperature": 1.0},
            ],
        },
        "audit": {
            "model_names": ["mimo-v2.5-pro-thinking"],
            "scenes": [
                {"scene_name": "infer", "model_name": "mimo-v2.5-pro-thinking", "temperature": 0.2},
                {"scene_name": "decision", "model_name": "mimo-v2.5-pro-thinking", "temperature": 0.6},
                {"scene_name": "audit", "model_name": "mimo-v2.5-pro-thinking", "temperature": 0.2},
                {"scene_name": "confirm", "model_name": "mimo-v2.5-pro-thinking", "temperature": 0.2},
            ],
        },
    }
    assert result["audit"] == {
        "required": True,
        "passed_count": 3,
        "failed_count": 0,
        "skipped_count": 0,
        "gate_blocked_count": 1,
        "first_pass_count": 1,
        "repaired_pass_count": 1,
        "total_retries": 3,
        "audit_attempt_count": 4,
        "confirmation_check_count": 3,
        "anchor_rewrite_count": 1,
    }
    assert [item["title"] for item in result["chapters"]] == ["公司介绍", "竞争优势", "风险"]
    assert [item["outcome"] for item in result["chapters"]] == [
        "passed_first_attempt",
        "passed_after_repair",
        "blocked",
    ]
    assert result["chapters"][1]["audit_attempt_count"] == 3
    assert result["chapters"][1]["confirmation_check_count"] == 3
    assert result["chapters"][1]["anchor_rewrite_count"] == 1
    assert result["chapters"][2]["final_stage"] == "unknown"


@pytest.mark.unit
def test_build_summary_respects_chapter_level_audit_skip(tmp_path: Path) -> None:
    """验证正常模式下显式跳过审计的概览章不会计入审计失败。"""

    runner = _build_runner(tmp_path)
    builder = ExecutionSummaryBuilder(write_config=runner._write_config)
    chapter_results = {
        "投资要点概览": ChapterResult(
            index=0,
            title="投资要点概览",
            status="passed",
            content="overview",
            audit_passed=True,
            process_state={
                "audit_skipped": True,
                "final_stage": "overview_written",
            },
        )
    }

    result = builder.build_summary(
        chapter_results,
        output_file=Path("/tmp/report.md"),
        success_predicate=lambda item: bool(item and item.status == "passed" and item.audit_passed),
    )

    assert result["gate_status"] == "passed"
    assert result["audit"]["required"] is True
    assert result["audit"]["passed_count"] == 0
    assert result["audit"]["failed_count"] == 0
    assert result["audit"]["skipped_count"] == 1
    assert result["audit"]["gate_blocked_count"] == 0
    assert result["chapters"][0]["audit_required"] is False
    assert result["chapters"][0]["outcome"] == "passed_without_audit"


@pytest.mark.unit
def test_build_summary_marks_fast_mode_as_not_audited(tmp_path: Path) -> None:
    """验证 fast 模式通过门禁时不会被误报为审计通过。"""

    runner = _build_runner(tmp_path, fast=True)
    builder = ExecutionSummaryBuilder(write_config=runner._write_config)
    chapter_results = {
        "公司介绍": ChapterResult(
            index=1,
            title="公司介绍",
            status="passed",
            content="draft",
            audit_passed=False,
        )
    }

    result = builder.build_summary(
        chapter_results,
        output_file=Path("/tmp/report.md"),
        success_predicate=lambda item: bool(item and item.status == "passed" and item.content),
    )

    assert result["gate_status"] == "passed"
    assert result["audit"]["required"] is False
    assert result["audit"]["passed_count"] == 0
    assert result["audit"]["first_pass_count"] == 0
    assert result["audit"]["skipped_count"] == 1
    assert result["chapters"][0]["gate_passed"] is True
    assert result["chapters"][0]["audit_required"] is False
    assert result["chapters"][0]["outcome"] == "passed_without_audit"
