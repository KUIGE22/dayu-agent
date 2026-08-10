"""S3 batch admission 分类单元测试（S14-CTRL-12）。

覆盖 ``_execute_with_auto_batch`` 的 per-operation admission 语义：
FS/local 保留 auto-begin；S3 模式 EXPLICIT_REQUIRED 无 active token 稳定
fail-loud、AUTO_ATOMIC_ALLOWED 至多一个短内部 batch、有同-core active token
一律复用。
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import pytest

from dayu.fins.domain.document_models import FileObjectMeta
from dayu.fins.storage._fs_storage_core import FsStorageCore
from dayu.fins.storage._fs_storage_infra import BatchAdmission
from tests.fins.storage_testkit import build_fs_storage_test_context


class _FakeStagedStore:
    """实现 StagedFileStoreProtocol 的窄 fake。"""

    def stage_publish(self, *, operation_id: str, data: BinaryIO) -> FileObjectMeta:
        """写入 staging 并返回元数据。"""

        del operation_id, data
        return FileObjectMeta(
            uri="s3://bucket/.dayu-staging/op/0" * 0 + "s3://bucket/.dayu-staging/op/zero",
            sha256="0" * 64,
            size=0,
        )

    def publish_staged(
        self,
        *,
        staging_key: str,
        final_key: str,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> None:
        """发布 staging 到 final。"""

        del staging_key, final_key, content_type, metadata

    def object_uri(self, key: str) -> str:
        """构造 URI。"""

        return f"s3://bucket/{key}"

    def key_from_uri(self, uri: str) -> str:
        """从 URI 提取 key。"""

        return uri.split("s3://bucket/", 1)[1]

    def delete_object_idempotent(self, key: str) -> None:
        """幂等删除。"""

        del key


def _staged_core(tmp_path: Path) -> FsStorageCore:
    """构造注入 fake staged store 的 core。"""

    context = build_fs_storage_test_context(tmp_path)
    context.core._file_store = _FakeStagedStore()
    return context.core


def _fs_core(tmp_path: Path) -> FsStorageCore:
    """构造 FS 模式 core。"""

    return build_fs_storage_test_context(tmp_path).core


def _noop_operation() -> None:
    """no-op 操作。"""


def _failing_operation() -> None:
    """抛错操作。"""

    raise ValueError("boom")


def test_fs_mode_explicit_required_still_auto_begins(tmp_path: Path) -> None:
    """FS/local 模式 EXPLICIT_REQUIRED 无 active token 仍 auto-begin。"""

    core = _fs_core(tmp_path)
    core._execute_with_auto_batch(
        "AAPL",
        _noop_operation,
        admission=BatchAdmission.EXPLICIT_REQUIRED,
    )
    assert core._active_batches == {}


def test_s3_explicit_required_no_token_fails_loud(tmp_path: Path) -> None:
    """S3 模式 EXPLICIT_REQUIRED 无 active token 稳定抛 s3_write_requires_batch。"""

    core = _staged_core(tmp_path)
    with pytest.raises(RuntimeError, match="s3_write_requires_batch"):
        core._execute_with_auto_batch(
            "AAPL",
            _noop_operation,
            admission=BatchAdmission.EXPLICIT_REQUIRED,
        )
    assert core._active_batches == {}
    assert not (core.batch_root.exists() and any(core.batch_root.iterdir()))


def test_s3_auto_allowed_creates_single_short_batch(tmp_path: Path) -> None:
    """S3 模式 AUTO_ATOMIC_ALLOWED 无 active token 至多一个短内部 batch。"""

    core = _staged_core(tmp_path)
    core._execute_with_auto_batch(
        "AAPL",
        _noop_operation,
        admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
    )
    assert core._active_batches == {}


def test_s3_auto_allowed_rollback_on_operation_failure(tmp_path: Path) -> None:
    """S3 模式 AUTO 方法操作失败 => rollback 收敛零残留。"""

    core = _staged_core(tmp_path)
    with pytest.raises(ValueError, match="boom"):
        core._execute_with_auto_batch(
            "AAPL",
            _failing_operation,
            admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
        )
    assert core._active_batches == {}


def test_s3_active_token_reused_for_explicit_required(tmp_path: Path) -> None:
    """有同-core active token 时 EXPLICIT_REQUIRED 复用同一 token。"""

    core = _staged_core(tmp_path)
    token = core.begin_batch("AAPL")
    try:
        core._execute_with_auto_batch(
            "AAPL",
            _noop_operation,
            admission=BatchAdmission.EXPLICIT_REQUIRED,
        )
        assert core._active_batches["AAPL"] is token
    finally:
        core.rollback_batch(token)


def test_s3_active_token_reused_for_auto_allowed(tmp_path: Path) -> None:
    """有同-core active token 时 AUTO_ATOMIC_ALLOWED 复用同一 token。"""

    core = _staged_core(tmp_path)
    token = core.begin_batch("AAPL")
    try:
        core._execute_with_auto_batch(
            "AAPL",
            _noop_operation,
            admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
        )
        assert core._active_batches["AAPL"] is token
    finally:
        core.rollback_batch(token)


def test_fs_mode_auto_allowed_auto_begins(tmp_path: Path) -> None:
    """FS/local 模式 AUTO_ATOMIC_ALLOWED 保留 auto-begin。"""

    core = _fs_core(tmp_path)
    core._execute_with_auto_batch(
        "AAPL",
        _noop_operation,
        admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
    )
    assert core._active_batches == {}


def test_isinstance_detection_is_staged(tmp_path: Path) -> None:
    """_is_s3_mode 经 isinstance 判定 staged capability。"""

    core = _staged_core(tmp_path)
    assert core._is_s3_mode() is True


def test_fs_mode_not_staged(tmp_path: Path) -> None:
    """FS 模式 _is_s3_mode 为 False。"""

    core = _fs_core(tmp_path)
    assert core._is_s3_mode() is False
