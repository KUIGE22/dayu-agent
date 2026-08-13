"""Source Sync storage protocol 的纯边界与精确签名测试。"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import UnionType
from typing import get_args, get_origin, get_type_hints
from uuid import UUID

import pytest

from dayu.investment.domain.identifiers import TenantScope
from dayu.investment.domain.source import SourceSubscriptionId
from dayu.investment.domain.source_evidence import SourceSyncAttemptReceipt
from dayu.investment.domain.source_health import (
    SourceHealthProjection,
    SourceHealthReenableRequest,
    SourceHealthSnapshotCursor,
    SourceHealthSnapshotPage,
)
from dayu.investment.domain.source_operation import (
    SourceOperationAcquireDecision,
    SourceOperationAcquireRequest,
    SourceTerminalRecordDecision,
    SourceTerminalRecordRequest,
)
from dayu.investment.domain.source_payload import SourceExecutionBinding
from dayu.investment.storage.source_sync_protocols import SourceSyncRepositoryProtocol

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXACT_METHODS = (
    "get_executable_binding",
    "acquire_operation",
    "record_terminal",
    "get_source_receipt",
    "get_health",
    "list_health_snapshots",
    "reenable_health",
)


def _protocol_method_names() -> tuple[str, ...]:
    """读取协议类直接声明的公开方法名。

    Args:
        无。

    Returns:
        按源码声明顺序排列的方法名。

    Raises:
        无。
    """

    return tuple(
        name
        for name, value in SourceSyncRepositoryProtocol.__dict__.items()
        if not name.startswith("_") and inspect.isfunction(value)
    )


def _assert_union(annotation: type[SourceSyncAttemptReceipt] | UnionType, expected: frozenset[type]) -> None:
    """断言解析后的 PEP 604 union 精确包含给定成员。

    Args:
        annotation: ``typing.get_type_hints`` 解析后的 annotation。
        expected: 期望 union 成员集合。

    Returns:
        无。

    Raises:
        AssertionError: annotation 不是期望 union 时抛出。
    """

    assert get_origin(annotation) is UnionType
    assert frozenset(get_args(annotation)) == expected


@pytest.mark.unit
def test_source_sync_repository_protocol_has_exact_seven_methods_and_pure_annotations() -> None:
    """协议必须只有七方法，且每个 DTO 都解析到唯一纯领域 owner。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    assert _protocol_method_names() == _EXACT_METHODS
    owner_by_type = {
        TenantScope: "dayu.investment.domain.identifiers",
        SourceSubscriptionId: "dayu.investment.domain.source",
        SourceSyncAttemptReceipt: "dayu.investment.domain.source_evidence",
        SourceHealthProjection: "dayu.investment.domain.source_health",
        SourceHealthReenableRequest: "dayu.investment.domain.source_health",
        SourceHealthSnapshotCursor: "dayu.investment.domain.source_health",
        SourceHealthSnapshotPage: "dayu.investment.domain.source_health",
        SourceOperationAcquireDecision: "dayu.investment.domain.source_operation",
        SourceOperationAcquireRequest: "dayu.investment.domain.source_operation",
        SourceTerminalRecordDecision: "dayu.investment.domain.source_operation",
        SourceTerminalRecordRequest: "dayu.investment.domain.source_operation",
        SourceExecutionBinding: "dayu.investment.domain.source_payload",
    }
    for method_name in _EXACT_METHODS:
        hints = get_type_hints(SourceSyncRepositoryProtocol.__dict__[method_name])
        for annotation in hints.values():
            candidates = get_args(annotation) if get_origin(annotation) is UnionType else (annotation,)
            for candidate in candidates:
                if candidate in owner_by_type:
                    assert candidate.__module__ == owner_by_type[candidate]
    all_modules = {
        candidate.__module__
        for method_name in _EXACT_METHODS
        for annotation in get_type_hints(SourceSyncRepositoryProtocol.__dict__[method_name]).values()
        for candidate in (get_args(annotation) if get_origin(annotation) is UnionType else (annotation,))
        if isinstance(candidate, type)
    }
    assert "dayu.investment.domain.source_sync" not in all_modules


@pytest.mark.unit
def test_source_sync_repository_protocol_has_exact_synchronous_signatures_and_parameter_annotations() -> None:
    """七方法必须保持同步、参数顺序、keyword-only limit 与精确返回类型。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    expected_parameters = {
        "get_executable_binding": ("self", "scope", "subscription_id"),
        "acquire_operation": ("self", "scope", "request"),
        "record_terminal": ("self", "scope", "request"),
        "get_source_receipt": ("self", "scope", "source_sync_run_id"),
        "get_health": ("self", "scope", "subscription_id"),
        "list_health_snapshots": ("self", "scope", "subscription_id", "cursor", "limit"),
        "reenable_health": ("self", "scope", "request"),
    }
    expected_returns = {
        "get_executable_binding": SourceExecutionBinding,
        "acquire_operation": SourceOperationAcquireDecision,
        "record_terminal": SourceTerminalRecordDecision,
        "get_health": SourceHealthProjection,
        "list_health_snapshots": SourceHealthSnapshotPage,
        "reenable_health": SourceHealthProjection,
    }
    for method_name in _EXACT_METHODS:
        method = SourceSyncRepositoryProtocol.__dict__[method_name]
        assert inspect.isfunction(method)
        assert not inspect.iscoroutinefunction(method)
        signature = inspect.signature(method)
        assert tuple(signature.parameters) == expected_parameters[method_name]
        assert all(parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values())
        hints = get_type_hints(method)
        assert hints["scope"] is TenantScope
        if method_name in expected_returns:
            assert hints["return"] is expected_returns[method_name]
    assert get_type_hints(SourceSyncRepositoryProtocol.get_executable_binding)["subscription_id"] is SourceSubscriptionId
    assert get_type_hints(SourceSyncRepositoryProtocol.acquire_operation)["request"] is SourceOperationAcquireRequest
    assert get_type_hints(SourceSyncRepositoryProtocol.record_terminal)["request"] is SourceTerminalRecordRequest
    receipt_hints = get_type_hints(SourceSyncRepositoryProtocol.get_source_receipt)
    assert receipt_hints["source_sync_run_id"] is UUID
    _assert_union(receipt_hints["return"], frozenset({SourceSyncAttemptReceipt, type(None)}))
    health_hints = get_type_hints(SourceSyncRepositoryProtocol.get_health)
    assert health_hints["subscription_id"] is SourceSubscriptionId
    list_signature = inspect.signature(SourceSyncRepositoryProtocol.list_health_snapshots)
    assert list_signature.parameters["limit"].kind is inspect.Parameter.KEYWORD_ONLY
    list_hints = get_type_hints(SourceSyncRepositoryProtocol.list_health_snapshots)
    _assert_union(list_hints["cursor"], frozenset({SourceHealthSnapshotCursor, type(None)}))
    assert list_hints["limit"] is int
    assert get_type_hints(SourceSyncRepositoryProtocol.reenable_health)["request"] is SourceHealthReenableRequest


@pytest.mark.unit
def test_legacy_storage_protocols_does_not_reexport_source_sync_repository_protocol() -> None:
    """Legacy storage protocols 与 package root 均不得转发新协议。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    targets = (
        _REPO_ROOT / "dayu" / "investment" / "storage" / "protocols.py",
        _REPO_ROOT / "dayu" / "investment" / "storage" / "__init__.py",
    )
    for target in targets:
        tree = ast.parse(target.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        defined = {node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))}
        assert "SourceSyncRepositoryProtocol" not in imported | defined
