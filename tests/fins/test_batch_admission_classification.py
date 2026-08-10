"""batch admission 分类 completeness gate（S14-CTRL-12）。

AST gate：枚举 storage core 全部 ``_execute_with_auto_batch`` 调用点并断言
每个显式传 ``BatchAdmission`` 分类字面量；断言公开写入口集合与分类表一一
对应；并抓直接 put/delete/write-json 绕过（``replace_source_meta`` 旧行为
即典型实例）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dayu.fins.storage._fs_storage_infra import BatchAdmission

_STORAGE_CORE_DIR = Path("dayu/fins/storage")
_CORE_FILES = (
    "_fs_company_meta_core.py",
    "_fs_maintenance_core.py",
    "_fs_processed_core.py",
    "_fs_source_document_core.py",
    "_fs_blob_core.py",
    "_fs_storage_infra.py",
)

_ALLOWED_ADMISSIONS = frozenset({"EXPLICIT_REQUIRED", "AUTO_ATOMIC_ALLOWED"})

# 公开写入口 -> 分类（对应 S14-CTRL-12 exhaustive 表）。
# 以"公开方法是否在 _execute_with_auto_batch 之外直接调用写原语"为真源。
_EXPECTED_CLASSIFICATION = {
    "_fs_company_meta_core.py": {
        "upsert_company_meta": "AUTO_ATOMIC_ALLOWED",
    },
    "_fs_maintenance_core.py": {
        "save_download_rejection_registry": "AUTO_ATOMIC_ALLOWED",
        "store_rejected_filing_file": "EXPLICIT_REQUIRED",
        "upsert_rejected_filing_artifact": "AUTO_ATOMIC_ALLOWED",
        "clear_filing_documents": "AUTO_ATOMIC_ALLOWED",
        "cleanup_stale_filing_documents": "AUTO_ATOMIC_ALLOWED",
    },
    "_fs_processed_core.py": {
        "create_processed": "AUTO_ATOMIC_ALLOWED",
        "update_processed": "AUTO_ATOMIC_ALLOWED",
        "delete_processed": "AUTO_ATOMIC_ALLOWED",
        "mark_processed_reprocess_required": "AUTO_ATOMIC_ALLOWED",
        "clear_processed_documents": "AUTO_ATOMIC_ALLOWED",
    },
    "_fs_source_document_core.py": {
        "create_material": "AUTO_ATOMIC_ALLOWED",
        "update_material": "AUTO_ATOMIC_ALLOWED",
        "delete_material": "AUTO_ATOMIC_ALLOWED",
        "restore_material": "AUTO_ATOMIC_ALLOWED",
        "create_filing": "AUTO_ATOMIC_ALLOWED",
        "update_filing": "AUTO_ATOMIC_ALLOWED",
        "delete_filing": "AUTO_ATOMIC_ALLOWED",
        "restore_filing": "AUTO_ATOMIC_ALLOWED",
        "reset_source_document": "AUTO_ATOMIC_ALLOWED",
        "replace_source_meta": "AUTO_ATOMIC_ALLOWED",
    },
    "_fs_blob_core.py": {
        "delete_entry": "EXPLICIT_REQUIRED",
        "store_file": "EXPLICIT_REQUIRED",
    },
    "_fs_storage_infra.py": {
        "upsert_filing_manifest": "AUTO_ATOMIC_ALLOWED",
        "upsert_material_manifest": "AUTO_ATOMIC_ALLOWED",
        "upsert_processed_manifest": "AUTO_ATOMIC_ALLOWED",
    },
}

_WRITE_PRIMITIVES = frozenset(
    {
        "put_object",
        "delete_object",
        "delete_object_idempotent",
        "stage_publish",
        "publish_staged",
        "write_json",
    }
)


def _parse_module(filename: str) -> ast.Module:
    """解析 storage core 模块 AST。"""

    return ast.parse((_STORAGE_CORE_DIR / filename).read_text(encoding="utf-8"))


def _collect_auto_batch_call_sites(tree: ast.Module) -> list[tuple[int, str]]:
    """收集全部 _execute_with_auto_batch 调用点（行号, 分类或空）。"""

    sites: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "_execute_with_auto_batch":
            continue
        admission = ""
        for kw in node.keywords:
            if kw.arg == "admission" and isinstance(kw.value, ast.Attribute):
                admission = kw.value.attr
        sites.append((node.lineno, admission))
    return sites


def _collect_public_writer_methods(tree: ast.Module) -> list[str]:
    """收集含写副作用（写原语或 auto-batch 调用）的公开方法名。"""

    writers: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name.startswith("_"):
                continue
            body_calls = list(ast.walk(item))
            has_auto_batch = any(
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)
                and c.func.attr == "_execute_with_auto_batch"
                for c in body_calls
            )
            has_write_primitive = any(
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)
                and c.func.attr in _WRITE_PRIMITIVES
                for c in body_calls
            )
            if has_auto_batch or has_write_primitive:
                writers.append(item.name)
    return writers


@pytest.mark.parametrize("filename", _CORE_FILES)
def test_all_auto_batch_call_sites_have_admission(filename: str) -> None:
    """每个 _execute_with_auto_batch 调用点显式传合法分类。"""

    tree = _parse_module(filename)
    sites = _collect_auto_batch_call_sites(tree)
    assert sites, f"{filename} 应存在 auto-batch 调用点"
    for lineno, admission in sites:
        assert admission in _ALLOWED_ADMISSIONS, (
            f"{filename}:{lineno} 缺少或含未知 admission 分类: {admission or 'MISSING'}"
        )


def test_public_writers_match_classification_table() -> None:
    """公开写入口集合与分类表一一对应（完整性）。"""

    expected = _EXPECTED_CLASSIFICATION
    for filename in _CORE_FILES:
        tree = _parse_module(filename)
        public_writers = set(_collect_public_writer_methods(tree))
        classified = set(expected[filename])
        unclassified = public_writers - classified
        assert not unclassified, (
            f"{filename} 存在未分类公开写入口: {sorted(unclassified)}"
        )


def test_replace_source_meta_inside_auto_batch() -> None:
    """replace_source_meta 必须在 _execute_with_auto_batch 内（防绕过）。"""

    tree = _parse_module("_fs_source_document_core.py")
    public = _collect_public_writer_methods(tree)
    assert "replace_source_meta" in public


def test_no_direct_write_primitive_outside_auto_batch() -> None:
    """公开方法不得在 _execute_with_auto_batch 外直接写 meta/FileStore。

    EXPLICIT_REQUIRED blob 原语（``store_file``/``store_rejected_filing_file``/
    ``delete_entry``）直接写是预期模式（由 producer 显式 begin），排除在
    绕过判定之外。
    """

    explicit_blob_primitives = frozenset(
        {
            "store_file",
            "store_rejected_filing_file",
            "delete_entry",
        }
    )
    for filename in _CORE_FILES:
        tree = _parse_module(filename)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name.startswith("_") or node.name in explicit_blob_primitives:
                continue
            body_calls = list(ast.walk(node))
            calls_auto_batch = any(
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)
                and c.func.attr == "_execute_with_auto_batch"
                for c in body_calls
            )
            if calls_auto_batch:
                continue
            direct_writes = [
                c
                for c in body_calls
                if isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)
                and c.func.attr in _WRITE_PRIMITIVES
            ]
            assert not direct_writes, (
                f"{filename}:{node.lineno} 公开方法 {node.name} 在 auto-batch 外直接写原语"
            )


def test_enum_members_exact() -> None:
    """BatchAdmission 仅两个成员且名称精确。"""

    assert {member.name for member in BatchAdmission} == {
        "EXPLICIT_REQUIRED",
        "AUTO_ATOMIC_ALLOWED",
    }
