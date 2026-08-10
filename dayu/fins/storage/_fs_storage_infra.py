"""文件系统仓储基础设施层。

提供共享实例状态、批处理事务、路径方法、manifest 操作、handle 辅助等，
作为所有领域 mixin 的唯一基类。
"""

from __future__ import annotations

import os
import shutil
import socket
import typing
import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, TextIO, TypeVar

import dayu.file_lock as file_lock_module
from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    FileObjectMeta,
    FilingManifestItem,
    MaterialManifestItem,
    ProcessedHandle,
    ProcessedManifestItem,
    SourceHandle,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind
from dayu.log import Log

from ._fs_storage_utils import (
    _DOWNLOAD_REJECTIONS_FILENAME,
    _PROCESSED_META_FILENAME,
    _REJECTED_FILINGS_DIRNAME,
    _SOURCE_META_FILENAME,
    _normalize_entry_name,
    _normalize_source_kind,
    _normalize_ticker,
    _read_json_object,
    _source_dir_name,
    _write_json,
)
from .file_store import FileStore
from .local_file_store import LocalFileStore
from .remote_op_journal import (
    RemoteDeleteTarget,
    RemoteOpJournal,
    RemotePublishTarget,
    remove_journal,
    write_journal,
)
from .s3_file_store import StagedFileStoreProtocol

_T = TypeVar("_T")

_DAYU_DIRNAME = ".dayu"
_BATCH_ROOT_DIRNAME = "repo_batches"
_BACKUP_ROOT_DIRNAME = "repo_backups"
_LOCK_ROOT_DIRNAME = "batch_locks"
_RECOVERY_LOCK_FILENAME = "batch_recovery.lock"
_REMOTE_OPS_DIRNAME = "remote_ops"
_JOURNAL_FILENAME = "transaction.json"
_PHASE_STARTED = "started"
_PHASE_BACKED_UP_TARGET = "backed_up_target"
_PHASE_SWAPPED_TARGET = "swapped_target"
_PHASE_COMMITTED = "committed"
_PHASE_ROLLED_BACK = "rolled_back"

_PHASE_STAGED = "staged"
_PHASE_METADATA_COMMITTED = "metadata_committed"
_PHASE_CLEANUP_DONE = "cleanup_done"
_PHASE_CLEANUP_PENDING = "cleanup_pending"

_PUBLISH_STATE_STAGED = "staged"
_PUBLISH_STATE_FINAL_VERIFIED = "final_verified"
_DELETE_STATE_PENDING = "pending"
_DELETE_STATE_REMOTE_DELETED = "remote_deleted"

_STAGING_PREFIX = ".dayu-staging/"

_S3_WRITE_REQUIRES_BATCH = "s3_write_requires_batch"


class BatchAdmission(Enum):
    """S3 模式下写操作的显式 admission 分类。

    ``EXPLICIT_REQUIRED``：必须在 producer 显式 same-core batch 内执行
    （blob 原语如 ``store_file``/``store_rejected_filing_file``/``delete_entry``，
    或正确性依赖随后 metadata 更新的操作）；S3 模式下无 active token 即稳定
    失败 ``s3_write_requires_batch``，零 auto begin。

    ``AUTO_ATOMIC_ALLOWED``：方法自身即完整原子语义单元（metadata-only 或
    完整单-repository destructive）；S3 模式下无 active token 时至多自建一个
    短内部 batch，有 active token 时一律复用。
    """

    EXPLICIT_REQUIRED = "explicit_required"
    AUTO_ATOMIC_ALLOWED = "auto_atomic_allowed"


def _iso_now() -> str:
    """返回当前 UTC ISO8601 时间。

    Args:
        无。

    Returns:
        ISO8601 字符串。

    Raises:
        无。
    """

    return datetime.now(UTC).isoformat()


def _remote_matches_expected(remote: FileObjectMeta, *, sha256: str, size: int) -> bool:
    """判断远端对象是否同时匹配期望的 SHA-256 与 size（唯一内容身份真源）。

    正常模糊 Copy 判定与 startup recovery 都必须共用本真源：仅 SHA 或仅
    size 任一匹配都不足以认定目标就是当前 operation 期望的 bytes（同 size/
    different-SHA 对象可能被误判为已完成发布，S14-CR-03）。

    Args:
        remote: 远端对象元数据。
        sha256: 期望内容 SHA-256。
        size: 期望内容字节数。

    Returns:
        仅当 SHA-256 与 size 同时匹配时返回 ``True``。

    Raises:
        无。
    """

    return str(remote.sha256 or "") == sha256 and int(remote.size or 0) == size


def _parse_backup_directory_name(name: str) -> tuple[str, str] | None:
    """解析备份目录名中的 ticker 与 token。

    Args:
        name: 备份目录名。

    Returns:
        成功时返回 `(ticker, token_id)`，否则返回 `None`。

    Raises:
        无。
    """

    ticker, separator, token_id = name.rpartition(".bak.")
    if not separator or not ticker or not token_id:
        return None
    return ticker, token_id


class _FsStorageInfra:
    """文件系统仓储基础设施基类。

    提供共享状态、批处理事务、路径解析、manifest 操作与 handle 辅助，
    所有领域 mixin 均继承自此类。
    """

    MODULE = "FINS.FS_REPOSITORY"

    def __init__(
        self,
        workspace_root: Path,
        file_store: Optional[FileStore] = None,
        *,
        create_directories: bool = True,
    ) -> None:
        """初始化仓储基础设施。

        Args:
            workspace_root: 工作区根目录。
            file_store: 可选文件存储实现（默认本地文件系统）。
            create_directories: 是否在初始化时创建仓储根目录。

        Returns:
            无。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        self.workspace_root = workspace_root.resolve()
        self.portfolio_root = self.workspace_root / "portfolio"
        self.dayu_root = self.workspace_root / _DAYU_DIRNAME
        self.batch_root = self.dayu_root / _BATCH_ROOT_DIRNAME
        self.backup_root = self.dayu_root / _BACKUP_ROOT_DIRNAME
        self._remote_ops_dir = self.dayu_root / _REMOTE_OPS_DIRNAME
        self._batch_lock_root = self.dayu_root / _LOCK_ROOT_DIRNAME
        self._recovery_lock_path = self.dayu_root / _RECOVERY_LOCK_FILENAME
        self._create_directories = create_directories
        self._batch_recovery_completed = False
        self._active_batches: dict[str, BatchToken] = {}
        self._ticker_lock_streams: dict[str, TextIO] = {}
        self._company_meta_by_ticker: Optional[dict[str, CompanyMeta]] = None
        self._alias_index: Optional[dict[str, list[str]]] = None
        self._file_store = file_store
        if create_directories:
            self.portfolio_root.mkdir(parents=True, exist_ok=True)
            self._ensure_batch_storage_dirs()

    def _is_s3_mode(self) -> bool:
        """判断当前是否运行在 S3 staged 模式。

        Args:
            无。

        Returns:
            若注入的 file store 实现了 ``StagedFileStoreProtocol`` 则返回
            ``True``（即 S3 模式，启用 remote journal 与 staged 语义）。

        Raises:
            无。
        """

        return isinstance(self._file_store, StagedFileStoreProtocol)

    def _staged_store(self) -> StagedFileStoreProtocol:
        """返回收窄为 staged 能力的 file store。

        Args:
            无。

        Returns:
            实现了 ``StagedFileStoreProtocol`` 的 file store。

        Raises:
            RuntimeError: 当前非 S3 模式时抛出。
        """

        if not isinstance(self._file_store, StagedFileStoreProtocol):
            raise RuntimeError("当前 file store 不支持 staged 语义")
        return self._file_store

    def _remote_journal(self, token: BatchToken) -> RemoteOpJournal:
        """读取或初始化当前 operation 的 remote journal。

        Args:
            token: 批处理 token（operation_id = token_id）。

        Returns:
            已持久化的 journal；首次调用时创建空 journal 并写盘。

        Raises:
            OSError: journal 写入失败时抛出。
        """

        from .remote_op_journal import read_journal

        existing = read_journal(self.dayu_root, token.token_id)
        if existing is not None:
            return existing
        journal = RemoteOpJournal(
            operation_id=token.token_id,
            ticker=token.ticker,
            created_at=now_iso8601(),
            owner_pid=str(os.getpid()),
            phase=_PHASE_STAGED,
        )
        write_journal(self.dayu_root, journal)
        return journal

    def _stage_publish(
        self,
        token: BatchToken,
        *,
        final_key: str,
        data: typing.BinaryIO,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """S3 模式下把字节写入 staging 并追加 publish target 到 remote journal。

        Args:
            token: 批处理 token。
            final_key: 最终对象 key。
            data: caller 二进制流。
            content_type: 可选内容类型。
            metadata: 可选扩展元数据。

        Returns:
            最终 key 对应的文件对象元数据（bytes 尚未发布，final 发布在
            ``commit_batch``）。

        Raises:
            OSError: staging 写入或 journal 追加失败时抛出。
        """

        assert isinstance(self._file_store, StagedFileStoreProtocol)
        staged_meta = self._file_store.stage_publish(
            operation_id=token.token_id,
            data=data,
        )
        self._append_publish_target(
            token,
            final_key=final_key,
            staged_meta=staged_meta,
            content_type=content_type,
            metadata=metadata,
        )
        return FileObjectMeta(
            uri=self._file_store.object_uri(final_key),
            etag=str(staged_meta.sha256 or ""),
            last_modified=staged_meta.last_modified,
            size=staged_meta.size,
            content_type=content_type,
            sha256=staged_meta.sha256,
        )

    def _append_publish_target(
        self,
        token: BatchToken,
        *,
        final_key: str,
        staged_meta: FileObjectMeta,
        content_type: Optional[str],
        metadata: Optional[dict[str, str]],
    ) -> None:
        """把 publish target 追加到当前 operation 的 remote journal。

        Args:
            token: 批处理 token。
            final_key: 最终对象 key。
            staged_meta: staging 元数据。
            content_type: 可选内容类型。
            metadata: 可选扩展元数据。

        Returns:
            无。

        Raises:
            OSError: journal 写入失败时抛出。
        """

        from .remote_op_journal import RemoteOpJournal, RemotePublishTarget

        assert isinstance(self._file_store, StagedFileStoreProtocol)
        journal = self._remote_journal(token)
        if any(target.final_key == final_key for target in journal.publish_targets):
            # 同一 operation 内重复发布同一 final key 会让逐 target 状态更新
            # 产生歧义并泄漏 staging，直接拒绝（S14-CTRL-12 overwrite 语义）。
            raise RuntimeError(f"publish final_key 重复: {final_key}")
        pending_delete = [
            target
            for target in journal.delete_targets
            if target.final_key == final_key and target.delete_state == _DELETE_STATE_PENDING
        ]
        if pending_delete:
            # overwrite：reset 记录的旧文件 delete intent 被同 key 新发布
            # 原子取代——旧 bytes 由新发布覆盖，绝不 post-commit 删除新 bytes
            # （S14-CTRL-12/13 same-key replacement）。
            journal = RemoteOpJournal(
                operation_id=journal.operation_id,
                ticker=journal.ticker,
                created_at=journal.created_at,
                owner_pid=journal.owner_pid,
                phase=journal.phase,
                publish_targets=list(journal.publish_targets),
                delete_targets=[
                    target
                    for target in journal.delete_targets
                    if not (
                        target.final_key == final_key
                        and target.delete_state == _DELETE_STATE_PENDING
                    )
                ],
            )
        journal.publish_targets.append(
            RemotePublishTarget(
                final_key=final_key,
                staging_key=self._file_store.key_from_uri(str(staged_meta.uri)),
                sha256=str(staged_meta.sha256 or ""),
                size=int(staged_meta.size or 0),
                content_type=content_type,
                metadata=dict(metadata or {}),
                publish_state=_PUBLISH_STATE_STAGED,
            )
        )
        write_journal(self.dayu_root, journal)

    def _stage_delete_one_key(self, token: BatchToken, final_key: str) -> None:
        """S3 模式 stage-delete helper：记录 delete intent（S14-CTRL-13）。

        对要删 key 先 head 并记录 expected sha/size，再以
        ``action=delete``/``delete_state=pending`` 追加 delete target；
        绝不执行远端删除（remote delete 只在 commit 的 post-swap cleanup 或
        recovery 收敛）。同一 operation 内对同一 key 的重复 delete intent
        幂等收敛（只保留首条 head 记录），保证 journal 内 delete final_key
        唯一（S14-CR-04 target 唯一性真源）。

        Args:
            token: 批处理 token。
            final_key: 最终对象 key。

        Returns:
            无。

        Raises:
            OSError: journal 写入失败时抛出。
        """

        from .s3_file_store import validate_s3_key

        validate_s3_key(final_key)
        # 校验当前为 staged 模式（非 staged 时抛 RuntimeError）。
        self._staged_store()
        file_store = self._file_store
        assert file_store is not None
        journal = self._remote_journal(token)
        if any(
            target.final_key == final_key and target.delete_state == _DELETE_STATE_PENDING
            for target in journal.delete_targets
        ):
            # 同一 operation 内重复 delete intent：幂等收敛，不重复追加
            # （``delete_entry`` 与 inventory diff 可能对同一 key 各自记录）。
            return
        try:
            remote_meta = file_store.stat_object(final_key)
        except FileNotFoundError:
            remote_sha256 = ""
            remote_size = 0
        except OSError:
            remote_sha256 = ""
            remote_size = 0
        else:
            remote_sha256 = str(remote_meta.sha256 or "")
            remote_size = int(remote_meta.size or 0)
        journal.delete_targets.append(
            RemoteDeleteTarget(
                final_key=final_key,
                expected_sha256=remote_sha256,
                expected_size=remote_size,
                delete_state=_DELETE_STATE_PENDING,
            )
        )
        write_journal(self.dayu_root, journal)

    def ensure_batch_recovery(self) -> tuple[str, ...]:
        """确保当前工作区的 batch 孤儿状态已完成一次恢复。

        Args:
            无。

        Returns:
            本次恢复执行的动作摘要。

        Raises:
            OSError: 恢复过程访问文件系统失败时抛出。
        """

        if self._batch_recovery_completed:
            return ()
        actions = self.recover_orphan_batches()
        self._batch_recovery_completed = True
        return actions

    # ========== 批处理事务 ==========

    def begin_batch(self, ticker: str) -> BatchToken:
        """开启批处理事务。

        Args:
            ticker: 股票代码。

        Returns:
            批处理 token。

        Raises:
            RuntimeError: 同一 ticker 已存在活动事务时抛出。
            OSError: 暂存目录准备失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        if normalized_ticker in self._active_batches:
            raise RuntimeError(f"ticker={normalized_ticker} 已存在活动 batch")

        self._ensure_batch_storage_dirs()
        self.ensure_batch_recovery()
        lock_stream = self._acquire_ticker_lock(normalized_ticker)
        token_id = uuid.uuid4().hex
        target_ticker_dir = self._target_ticker_dir(normalized_ticker)
        staging_root_dir = self.batch_root / token_id
        staging_ticker_dir = staging_root_dir / normalized_ticker
        backup_dir = self.backup_root / f"{target_ticker_dir.name}.bak.{token_id}"
        journal_path = staging_root_dir / _JOURNAL_FILENAME
        token = BatchToken(
            token_id=token_id,
            ticker=normalized_ticker,
            target_ticker_dir=target_ticker_dir,
            staging_root_dir=staging_root_dir,
            staging_ticker_dir=staging_ticker_dir,
            backup_dir=backup_dir,
            journal_path=journal_path,
            ticker_lock_path=self._ticker_lock_path(normalized_ticker),
            created_at=now_iso8601(),
        )
        try:
            self._write_batch_journal(token, _PHASE_STARTED)
            if self._is_s3_mode():
                # S3 模式：copytree 只复制 FS metadata/manifest/journal tree。
                # 本地 ticker dir 仅含 meta.json/manifest/.rejections 等元数据目录，
                # blob bytes 不在本地、不参与 copytree；S3 bytes 发布/删除进度由
                # remote journal 逐 target 管理。
                if target_ticker_dir.exists():
                    shutil.copytree(target_ticker_dir, staging_ticker_dir)
                else:
                    self._ensure_ticker_structure(staging_ticker_dir)
                self._remote_journal(token)
            elif target_ticker_dir.exists():
                shutil.copytree(target_ticker_dir, staging_ticker_dir)
            else:
                self._ensure_ticker_structure(staging_ticker_dir)
        except Exception:
            shutil.rmtree(staging_root_dir, ignore_errors=True)
            self._release_ticker_lock(normalized_ticker, stream=lock_stream)
            raise

        self._active_batches[normalized_ticker] = token
        return token

    def commit_batch(self, token: BatchToken) -> None:
        """提交批处理事务。

        Args:
            token: 批处理 token。

        Returns:
            无。

        Raises:
            ValueError: token 非当前活动事务时抛出。
            OSError: 提交失败时抛出。
        """

        current = self._active_batches.get(token.ticker)
        if current is None or current.token_id != token.token_id:
            raise ValueError("无效的 batch token，无法提交")

        if self._is_s3_mode():
            self._commit_s3_batch(token)
            return

        target_dir = token.target_ticker_dir
        staging_dir = token.staging_ticker_dir
        backup_dir = token.backup_dir
        preserved_swapped_target = False

        try:
            # 采用"先备份、再替换"的方式，降低提交中断带来的损坏风险。
            if target_dir.exists():
                shutil.move(str(target_dir), str(backup_dir))
                self._write_batch_journal(token, _PHASE_BACKED_UP_TARGET)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging_dir), str(target_dir))
            self._write_batch_journal(token, _PHASE_SWAPPED_TARGET)
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            self._write_batch_journal(token, _PHASE_COMMITTED)
            self._invalidate_company_meta_caches()
        except Exception:
            if backup_dir.exists() and target_dir.exists() and not staging_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            if backup_dir.exists() and not target_dir.exists():
                shutil.move(str(backup_dir), str(target_dir))
            elif target_dir.exists() and not staging_dir.exists():
                preserved_swapped_target = True

            if preserved_swapped_target:
                self._invalidate_company_meta_caches()
                Log.warn(
                    f"commit_batch 在目标切换后写入 journal 失败，已保留目标目录: ticker={token.ticker}",
                    module=self.MODULE,
                )
            else:
                self._write_batch_journal(token, _PHASE_ROLLED_BACK)
                Log.warn(f"commit_batch 失败，已恢复备份: ticker={token.ticker}", module=self.MODULE)
            raise
        finally:
            self._active_batches.pop(token.ticker, None)
            shutil.rmtree(token.staging_root_dir, ignore_errors=True)
            self._release_ticker_lock(token.ticker)

    def _commit_s3_batch(self, token: BatchToken) -> None:
        """S3 模式下提交批处理事务（S14-CTRL-04 唯一 ordering）。

        commit 顺序（publish/delete 均 post-swap 前不落远端副作用，逐 target
        原子持久）：

        1. 每个 ``action=publish`` target：单次 CopyObject 发布 final；copy 前
           该 target 必须已持久为 ``staged``，copy 后立即原子持久为
           ``final_verified``；copy 响应或 journal 写入模糊时以 head final 的
           digest/size 判定自己的完成（相等幂等置 verified，不相等且 staging
           存在则重试，staging 缺失 fail closed）；
        2. 每个 ``action=delete`` target：先 head 验证 remote 仍匹配 expected
           sha/size——匹配继续、drift 或缺失在 FS swap 前 abort fail closed；
        3. 全部 publish verified 且全部 delete 通过 head 验证后执行既有 FS
           metadata swap；
        4. 顶层 journal 置 ``metadata_committed``；
        5. bounded 重试清理：删除 publish staging keys + 幂等执行 delete
           target 的 remote delete；成功则置 ``cleanup_done`` 并移除 journal，
           失败则置 ``cleanup_pending`` 由 startup recovery 重试。

        Args:
            token: 批处理 token。

        Returns:
            无。

        Raises:
            RuntimeError: publish/delete 状态非法或 fail closed 时抛出。
            OSError: FS swap 或 journal 写入失败时抛出。
        """

        journal = self._remote_journal(token)
        assert isinstance(self._file_store, StagedFileStoreProtocol)
        target_dir = token.target_ticker_dir
        staging_dir = token.staging_ticker_dir
        backup_dir = token.backup_dir
        try:
            for target in journal.publish_targets:
                if target.publish_state == _PUBLISH_STATE_FINAL_VERIFIED:
                    continue
                if target.publish_state != _PUBLISH_STATE_STAGED:
                    raise RuntimeError(f"publish target 状态非法: {target.publish_state}")
                self._publish_one_target(target)
                journal = self._remote_journal(token)
                _update_publish_state(journal, target.final_key, _PUBLISH_STATE_FINAL_VERIFIED)
                write_journal(self.dayu_root, journal)
            for target in journal.delete_targets:
                if target.delete_state != _DELETE_STATE_PENDING:
                    continue
                remote_meta = self._head_expected(target)
                if remote_meta is None:
                    raise RuntimeError("remote delete target 缺失，swap 前 abort fail closed")
            if target_dir.exists():
                shutil.move(str(target_dir), str(backup_dir))
                self._write_batch_journal(token, _PHASE_BACKED_UP_TARGET)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging_dir), str(target_dir))
            self._write_batch_journal(token, _PHASE_SWAPPED_TARGET)
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            self._write_batch_journal(token, _PHASE_COMMITTED)
            journal = self._remote_journal(token)
            journal = RemoteOpJournal(
                operation_id=journal.operation_id,
                ticker=journal.ticker,
                created_at=journal.created_at,
                owner_pid=journal.owner_pid,
                phase=_PHASE_METADATA_COMMITTED,
                publish_targets=journal.publish_targets,
                delete_targets=journal.delete_targets,
            )
            write_journal(self.dayu_root, journal)
            self._cleanup_s3_operation(token, journal)
            self._invalidate_company_meta_caches()
        except Exception:
            # FS swap 前失败：回滚 FS backup（若已移动），远端已发布/删除
            # 目标由 journal/recovery 收敛，绝不先删 remote。
            if backup_dir.exists() and target_dir.exists() and not staging_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            if backup_dir.exists() and not target_dir.exists():
                shutil.move(str(backup_dir), str(target_dir))
            raise
        finally:
            self._active_batches.pop(token.ticker, None)
            shutil.rmtree(token.staging_root_dir, ignore_errors=True)
            self._release_ticker_lock(token.ticker)

    def _publish_one_target(self, target: RemotePublishTarget) -> None:
        """发布单个 publish target 到 final key。

        Args:
            target: publish target。

        Returns:
            无。

        Raises:
            RuntimeError: copy 失败且无法以 head 判定完成、或 staging 缺失时
                抛出（fail closed）。
        """

        assert isinstance(self._file_store, StagedFileStoreProtocol)
        try:
            self._file_store.publish_staged(
                staging_key=target.staging_key,
                final_key=target.final_key,
                content_type=target.content_type,
                metadata=dict(target.metadata),
            )
            return
        except OSError as exc:
            # copy 响应模糊：以 head final 的 digest/size 判定自己的完成。
            try:
                remote_meta = self._file_store.stat_object(target.final_key)
            except (OSError, FileNotFoundError):
                remote_meta = None
            # 内容身份 = SHA-256 且 size 同时匹配（S14-CR-03 唯一真源）。
            if remote_meta is not None and _remote_matches_expected(
                remote_meta,
                sha256=target.sha256,
                size=target.size,
            ):
                return
            try:
                staging_meta = self._file_store.stat_object(target.staging_key)
            except (OSError, FileNotFoundError):
                staging_meta = None
            if staging_meta is None:
                raise RuntimeError("publish staging 缺失，fail closed") from exc
            # staging 存在：重试一次 copy。
            try:
                self._file_store.publish_staged(
                    staging_key=target.staging_key,
                    final_key=target.final_key,
                    content_type=target.content_type,
                    metadata=dict(target.metadata),
                )
            except OSError as retry_exc:
                raise RuntimeError("publish copy 重试失败") from retry_exc

    def _head_expected(self, target: RemoteDeleteTarget) -> FileObjectMeta | None:
        """head 验证 delete target 的 remote 仍匹配 expected sha/size。

        Args:
            target: delete target。

        Returns:
            remote 元数据（SHA-256 与 size 同时匹配时）；remote 缺失或
            digest drift 时返回 ``None``。

        Raises:
            无。
        """

        assert isinstance(self._file_store, StagedFileStoreProtocol)
        try:
            remote_meta = self._file_store.stat_object(target.final_key)
        except FileNotFoundError:
            return None
        except OSError:
            return None
        if not _remote_matches_expected(
            remote_meta,
            sha256=target.expected_sha256,
            size=target.expected_size,
        ):
            return None
        return remote_meta

    def _cleanup_s3_operation(self, token: BatchToken, journal: RemoteOpJournal) -> None:
        """commit 后清理：删 staging keys + 幂等 remote delete。

        Args:
            token: 批处理 token。
            journal: 当前 journal（已置 ``metadata_committed``）。

        Returns:
            无。

        Raises:
            无（失败语义：publish staging 删除失败或 delete 失败 => journal
            置 ``cleanup_pending``，由 startup recovery 重试）。
        """

        assert isinstance(self._file_store, StagedFileStoreProtocol)
        cleanup_ok = True
        try:
            for target in journal.publish_targets:
                try:
                    self._file_store.delete_object_idempotent(target.staging_key)
                except OSError:
                    cleanup_ok = False
            for target in journal.delete_targets:
                if target.delete_state == _DELETE_STATE_REMOTE_DELETED:
                    continue
                try:
                    self._file_store.delete_object_idempotent(target.final_key)
                    updated = _update_delete_state(
                        journal,
                        target.final_key,
                        _DELETE_STATE_REMOTE_DELETED,
                    )
                    if updated:
                        write_journal(self.dayu_root, journal)
                except OSError:
                    cleanup_ok = False
        finally:
            if cleanup_ok:
                journal = self._remote_journal(token)
                journal = RemoteOpJournal(
                    operation_id=journal.operation_id,
                    ticker=journal.ticker,
                    created_at=journal.created_at,
                    owner_pid=journal.owner_pid,
                    phase=_PHASE_CLEANUP_DONE,
                    publish_targets=journal.publish_targets,
                    delete_targets=journal.delete_targets,
                )
                write_journal(self.dayu_root, journal)
                remove_journal(self.dayu_root, token.token_id)
            else:
                journal = self._remote_journal(token)
                journal = RemoteOpJournal(
                    operation_id=journal.operation_id,
                    ticker=journal.ticker,
                    created_at=journal.created_at,
                    owner_pid=journal.owner_pid,
                    phase=_PHASE_CLEANUP_PENDING,
                    publish_targets=journal.publish_targets,
                    delete_targets=journal.delete_targets,
                )
                write_journal(self.dayu_root, journal)

    def rollback_batch(self, token: BatchToken) -> None:
        """回滚批处理事务。

        Args:
            token: 批处理 token。

        Returns:
            无。

        Raises:
            ValueError: token 非当前活动事务时抛出。
            OSError: 清理失败时抛出。
        """

        current = self._active_batches.get(token.ticker)
        if current is None or current.token_id != token.token_id:
            raise ValueError("无效的 batch token，无法回滚")
        self._active_batches.pop(token.ticker, None)
        self._invalidate_company_meta_caches()
        rollback_error: Exception | None = None
        try:
            self._write_batch_journal(token, _PHASE_ROLLED_BACK)
        except Exception as exc:
            rollback_error = exc
            Log.warn(
                f"rollback_batch 写入 journal 失败，但仍继续清理 staging 与释放锁: ticker={token.ticker}",
                module=self.MODULE,
            )
        finally:
            try:
                if self._is_s3_mode():
                    self._rollback_s3_remote(token)
            finally:
                try:
                    shutil.rmtree(token.staging_root_dir, ignore_errors=True)
                finally:
                    self._release_ticker_lock(token.ticker)
        if rollback_error is not None:
            raise rollback_error

    def _rollback_s3_remote(self, token: BatchToken) -> None:
        """S3 模式回滚的远端清理：只删 operation-owned staging keys。

        Args:
            token: 批处理 token。

        Returns:
            无。

        Raises:
            无（远端清理失败只记录日志，不阻塞本地回滚）。
        """

        from .remote_op_journal import read_journal, write_journal

        journal = read_journal(self.dayu_root, token.token_id)
        if journal is None:
            return
        assert isinstance(self._file_store, StagedFileStoreProtocol)
        for target in journal.publish_targets:
            try:
                self._file_store.delete_object_idempotent(target.staging_key)
            except OSError as exc:
                Log.warn(
                    f"rollback staging key 删除失败: key={target.staging_key} error={exc}",
                    module=self.MODULE,
                )
        # delete target 未做任何远端副作用，直接置 rolled_back 后移除 journal。
        journal = RemoteOpJournal(
            operation_id=journal.operation_id,
            ticker=journal.ticker,
            created_at=journal.created_at,
            owner_pid=journal.owner_pid,
            phase=_PHASE_ROLLED_BACK,
            publish_targets=journal.publish_targets,
            delete_targets=journal.delete_targets,
        )
        write_journal(self.dayu_root, journal)
        remove_journal(self.dayu_root, token.token_id)

    def _execute_with_auto_batch(
        self,
        ticker: str,
        operation: Callable[..., _T],
        *args: Any,
        admission: BatchAdmission,
        **kwargs: Any,
    ) -> _T:
        """在无活动事务时按 admission 分类自动开启 batch 执行写操作。

        S3 模式（注入 ``StagedFileStoreProtocol``）下：

        - 已有同-core active token 一律复用（不新建 batch）；
        - ``EXPLICIT_REQUIRED`` 无 active token => 稳定抛
          ``s3_write_requires_batch``，零 begin/commit 副作用；
        - ``AUTO_ATOMIC_ALLOWED`` 无 active token => 至多自建一个短内部
          batch（begin -> operation -> commit/rollback，同一 core，走既有
          remote journal/恢复）。

        FS/local 模式（无 staged file store）保留现有 auto-begin 行为，
        无论 admission 分类。

        Args:
            ticker: 股票代码。
            operation: 具体执行函数。
            *args: 传给执行函数的位置参数。
            admission: S3 模式下的显式 admission 分类。
            **kwargs: 传给执行函数的关键字参数。

        Returns:
            执行函数返回值。

        Raises:
            Exception: 执行或提交失败时透传原异常。
            RuntimeError: S3 模式 EXPLICIT_REQUIRED 无 active token 时抛出
                ``s3_write_requires_batch``。
        """

        normalized_ticker = _normalize_ticker(ticker)
        if normalized_ticker in self._active_batches:
            return operation(*args, **kwargs)
        if self._is_s3_mode() and admission is BatchAdmission.EXPLICIT_REQUIRED:
            raise RuntimeError(_S3_WRITE_REQUIRES_BATCH)
        token = self.begin_batch(normalized_ticker)
        try:
            result = operation(*args, **kwargs)
        except Exception as operation_error:
            # 复杂逻辑说明：写操作失败时必须显式回滚 staging，避免留下半更新目录。
            Log.warn(f"写操作失败，已回滚 batch: ticker={token.ticker}", module=self.MODULE)
            rollback_error: Exception | None = None
            try:
                self.rollback_batch(token)
            except Exception as exc:
                rollback_error = exc
            if rollback_error is not None:
                operation_error.add_note(f"rollback_batch failed: {rollback_error}")
            raise
        self.commit_batch(token)
        return result

    def _invalidate_company_meta_caches(self) -> None:
        """清空公司级元数据与 alias 索引缓存。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._company_meta_by_ticker = None
        self._alias_index = None

    def recover_orphan_batches(self, *, dry_run: bool = False) -> tuple[str, ...]:
        """恢复异常退出后遗留的孤儿 batch/backup。

        Args:
            dry_run: 是否仅返回将执行的动作，不真正修改文件系统。

        Returns:
            动作摘要元组。

        Raises:
            OSError: 文件系统访问失败时抛出。
        """

        if not self._should_manage_batch_state():
            return ()
        self._ensure_batch_storage_dirs()
        lock_stream = self._acquire_recovery_lock()
        try:
            actions = self._recover_remote_ops(dry_run=dry_run)
            actions.extend(self._recover_orphan_batch_dirs(dry_run=dry_run))
            actions.extend(self._recover_orphan_backup_dirs(dry_run=dry_run))
        finally:
            self._release_lock_stream(lock_stream)
        return tuple(actions)

    def _recover_remote_ops(self, *, dry_run: bool) -> list[str]:
        """S3 模式下重放 remote-operation journal（S14-CTRL-04 recovery）。

        逐 target 独立判定、逐 action 独立处理；绝不允许把部分 publish 当全未
        publish，绝不允许在 metadata 仍引用时丢失远端 bytes；任何路径禁止先删
        remote。fail closed 时保留 journal 与远端 objects 并抛出稳定错误。

        Args:
            dry_run: 是否仅返回将执行的动作，不真正修改远端。

        Returns:
            动作摘要列表。

        Raises:
            RuntimeError: publish staging 缺失、delete drift、FS staging 缺失
                等 fail-closed 窗口触发时抛出（保留 journal 供人工恢复）。
        """

        actions: list[str] = []
        if not self._is_s3_mode():
            return actions
        from .remote_op_journal import list_journal_ids, read_journal

        for operation_id in list_journal_ids(self.dayu_root):
            # journal 是 recovery 唯一真源：存在但损坏/非法必须稳定 fail
            # closed（保留 journal、FS staging 与远端 objects），绝不允许把
            # 损坏 journal 当作“无 remote operation”继续 FS orphan cleanup
            # （S14-CR-04）。
            journal = read_journal(self.dayu_root, operation_id)
            if journal is None:
                continue
            if journal.phase == _PHASE_CLEANUP_DONE or journal.phase == _PHASE_ROLLED_BACK:
                if not dry_run:
                    remove_journal(self.dayu_root, operation_id)
                continue
            actions.extend(
                self._recover_single_remote_op(journal, dry_run=dry_run)
            )
        return actions

    def _recover_single_remote_op(self, journal: RemoteOpJournal, *, dry_run: bool) -> list[str]:
        """重放单个 remote-operation journal。

        Args:
            journal: 待恢复的 journal。
            dry_run: 是否仅返回动作。

        Returns:
            动作摘要列表。

        Raises:
            RuntimeError: fail-closed 窗口触发时抛出。
        """

        assert isinstance(self._file_store, StagedFileStoreProtocol)
        actions: list[str] = []
        if journal.phase == _PHASE_ROLLED_BACK:
            for target in journal.publish_targets:
                actions.append(f"rollback delete staging key={target.staging_key}")
                if not dry_run:
                    self._file_store.delete_object_idempotent(target.staging_key)
            if not dry_run:
                remove_journal(self.dayu_root, journal.operation_id)
            return actions

        # 1. publish target 逐 target 判定（以本 target 期望 digest/size 为真值）。
        for target in journal.publish_targets:
            if target.publish_state == _PUBLISH_STATE_FINAL_VERIFIED:
                continue
            remote_meta = None
            try:
                remote_meta = self._file_store.stat_object(target.final_key)
            except FileNotFoundError:
                remote_meta = None
            # 内容身份 = SHA-256 且 size 同时匹配才可幂等置 verified
            # （S14-CR-03 唯一真源；同-size/different-SHA 或 same-SHA/
            # different-size 都必须继续从 staging 发布或 fail closed）。
            if remote_meta is not None and _remote_matches_expected(
                remote_meta,
                sha256=target.sha256,
                size=target.size,
            ):
                actions.append(f"recovery verify final key={target.final_key}")
                if not dry_run:
                    _update_publish_state(journal, target.final_key, _PUBLISH_STATE_FINAL_VERIFIED)
                continue
            try:
                staging_meta = self._file_store.stat_object(target.staging_key)
            except FileNotFoundError:
                staging_meta = None
            if staging_meta is None:
                raise RuntimeError(
                    f"publish staging 缺失，fail closed: operation={journal.operation_id} key={target.final_key}"
                )
            actions.append(f"recovery publish key={target.final_key}")
            if not dry_run:
                self._file_store.publish_staged(
                    staging_key=target.staging_key,
                    final_key=target.final_key,
                    content_type=target.content_type,
                    metadata=dict(target.metadata),
                )
                _update_publish_state(journal, target.final_key, _PUBLISH_STATE_FINAL_VERIFIED)

        # 2. delete target 逐 target 判定（S14-CTRL-13）。
        delete_ok = True
        for target in journal.delete_targets:
            if target.delete_state == _DELETE_STATE_REMOTE_DELETED:
                continue
            if journal.phase == _PHASE_METADATA_COMMITTED:
                actions.append(f"recovery delete key={target.final_key}")
                if not dry_run:
                    try:
                        self._file_store.delete_object_idempotent(target.final_key)
                        _update_delete_state(journal, target.final_key, _DELETE_STATE_REMOTE_DELETED)
                    except OSError:
                        delete_ok = False
                continue
            remote_meta = None
            try:
                remote_meta = self._file_store.stat_object(target.final_key)
            except FileNotFoundError:
                remote_meta = None
            if remote_meta is None or not _remote_matches_expected(
                remote_meta,
                sha256=target.expected_sha256,
                size=target.expected_size,
            ):
                raise RuntimeError(
                    f"delete target drift/缺失，fail closed: operation={journal.operation_id} key={target.final_key}"
                )

        if not dry_run:
            self._persist_recovered_journal(journal, delete_ok)
        return actions

    def _persist_recovered_journal(self, journal: RemoteOpJournal, delete_ok: bool) -> None:
        """按恢复结果持久化 journal 并收敛 cleanup。

        Args:
            journal: 已更新的 journal。
            delete_ok: delete cleanup 是否全部成功。

        Returns:
            无。

        Raises:
            RuntimeError: FS batch staging 目录缺失/损坏（无法确定 meta 方向）
                时抛出（fail closed）。
        """

        from .remote_op_journal import write_journal

        write_journal(self.dayu_root, journal)
        all_verified = all(
            target.publish_state == _PUBLISH_STATE_FINAL_VERIFIED
            for target in journal.publish_targets
        )
        if not all_verified:
            return
        phase = journal.phase
        if phase == _PHASE_METADATA_COMMITTED or phase == _PHASE_CLEANUP_PENDING:
            if delete_ok:
                journal = RemoteOpJournal(
                    operation_id=journal.operation_id,
                    ticker=journal.ticker,
                    created_at=journal.created_at,
                    owner_pid=journal.owner_pid,
                    phase=_PHASE_CLEANUP_DONE,
                    publish_targets=journal.publish_targets,
                    delete_targets=journal.delete_targets,
                )
                write_journal(self.dayu_root, journal)
                remove_journal(self.dayu_root, journal.operation_id)
            else:
                journal = RemoteOpJournal(
                    operation_id=journal.operation_id,
                    ticker=journal.ticker,
                    created_at=journal.created_at,
                    owner_pid=journal.owner_pid,
                    phase=_PHASE_CLEANUP_PENDING,
                    publish_targets=journal.publish_targets,
                    delete_targets=journal.delete_targets,
                )
                write_journal(self.dayu_root, journal)
            return
        # 顶层仍 staged：FS 尚未 swap，需 metadata roll-forward。
        self._roll_forward_recovered_meta(journal)

    def _roll_forward_recovered_meta(self, journal: RemoteOpJournal) -> None:
        """对顶层仍 staged 的 operation 执行 metadata roll-forward。

        要求 FS batch staging 目录完整存活；缺失/损坏 => fail closed。bytes
        已发布即权威，绝不把 metadata 恢复回旧版本。

        Args:
            journal: 已全部 verified 的 journal。

        Returns:
            无。

        Raises:
            RuntimeError: FS batch staging 目录缺失/损坏时抛出。
        """

        assert isinstance(self._file_store, StagedFileStoreProtocol)
        token_dir = self.batch_root / journal.operation_id
        staging_ticker_dir = token_dir / journal.ticker
        if not staging_ticker_dir.exists() or not staging_ticker_dir.is_dir():
            raise RuntimeError(
                f"FS batch staging 目录缺失/损坏，fail closed: operation={journal.operation_id}"
            )
        target_dir = self._target_ticker_dir(journal.ticker)
        backup_dir = self.backup_root / f"{target_dir.name}.bak.{journal.operation_id}"
        if target_dir.exists():
            shutil.move(str(target_dir), str(backup_dir))
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging_ticker_dir), str(target_dir))
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
        for target in journal.publish_targets:
            try:
                self._file_store.delete_object_idempotent(target.staging_key)
            except OSError:
                pass
        delete_ok = True
        for target in journal.delete_targets:
            try:
                self._file_store.delete_object_idempotent(target.final_key)
                _update_delete_state(journal, target.final_key, _DELETE_STATE_REMOTE_DELETED)
            except OSError:
                delete_ok = False
        journal = RemoteOpJournal(
            operation_id=journal.operation_id,
            ticker=journal.ticker,
            created_at=journal.created_at,
            owner_pid=journal.owner_pid,
            phase=_PHASE_CLEANUP_PENDING if not delete_ok else _PHASE_CLEANUP_DONE,
            publish_targets=journal.publish_targets,
            delete_targets=journal.delete_targets,
        )
        write_journal(self.dayu_root, journal)
        if delete_ok:
            remove_journal(self.dayu_root, journal.operation_id)

    def _should_manage_batch_state(self) -> bool:
        """判断当前是否需要接触 batch 持久化状态。

        Args:
            无。

        Returns:
            若应访问 `.dayu` 下的 batch 状态则返回 `True`。

        Raises:
            无。
        """

        return self._create_directories or self.dayu_root.exists() or self.batch_root.exists() or self.backup_root.exists()

    def _ensure_batch_storage_dirs(self) -> None:
        """确保 `.dayu` 下的 batch 基础目录存在。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        self.dayu_root.mkdir(parents=True, exist_ok=True)
        self.batch_root.mkdir(parents=True, exist_ok=True)
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self._batch_lock_root.mkdir(parents=True, exist_ok=True)
        self._remote_ops_dir.mkdir(parents=True, exist_ok=True)

    def _ticker_lock_path(self, ticker: str) -> Path:
        """返回指定 ticker 的事务锁路径。

        Args:
            ticker: 股票代码。

        Returns:
            锁文件路径。

        Raises:
            无。
        """

        return self._batch_lock_root / f"{ticker}.lock"

    def _open_and_lock_stream(self, lock_path: Path, *, blocking: bool) -> TextIO:
        """打开并持有文件锁。

        Args:
            lock_path: 锁文件路径。
            blocking: 是否阻塞等待锁。

        Returns:
            已持锁的文件流。

        Raises:
            RuntimeError: 非阻塞模式下锁已被占用时抛出。
            OSError: 锁文件打开或加锁失败时抛出。
        """

        lock_path.parent.mkdir(parents=True, exist_ok=True)
        stream = lock_path.open("a+", encoding="utf-8")
        try:
            file_lock_module.acquire_text_file_lock(
                stream,
                blocking=blocking,
                lock_name="Fins batch 文件锁",
            )
        except OSError as exc:
            stream.close()
            if not blocking and file_lock_module.is_lock_contention_error(exc):
                raise RuntimeError(f"ticker={lock_path.stem} 已存在跨进程活动 batch") from exc
            raise
        return stream

    def _release_lock_stream(self, stream: TextIO) -> None:
        """释放并关闭文件锁流。

        Args:
            stream: 已持锁的文件流。

        Returns:
            无。

        Raises:
            OSError: 解锁失败时抛出。
        """

        try:
            file_lock_module.release_text_file_lock(
                stream,
                lock_name="Fins batch 文件锁",
            )
        finally:
            stream.close()

    def _acquire_ticker_lock(self, ticker: str) -> TextIO:
        """获取某个 ticker 的跨进程事务锁。

        Args:
            ticker: 股票代码。

        Returns:
            已持锁的文件流。

        Raises:
            RuntimeError: 锁已被其他进程持有时抛出。
            OSError: 锁文件访问失败时抛出。
        """

        stream = self._open_and_lock_stream(self._ticker_lock_path(ticker), blocking=False)
        self._ticker_lock_streams[ticker] = stream
        return stream

    def _release_ticker_lock(self, ticker: str, *, stream: TextIO | None = None) -> None:
        """释放某个 ticker 的跨进程事务锁。

        Args:
            ticker: 股票代码。
            stream: 可选显式文件流；未提供时使用内部缓存流。

        Returns:
            无。

        Raises:
            OSError: 解锁失败时抛出。
        """

        effective_stream = stream or self._ticker_lock_streams.pop(ticker, None)
        if effective_stream is None:
            return
        self._release_lock_stream(effective_stream)

    def _acquire_recovery_lock(self) -> TextIO:
        """获取全局 batch 恢复锁。

        Args:
            无。

        Returns:
            已持锁的文件流。

        Raises:
            OSError: 锁文件访问失败时抛出。
        """

        return self._open_and_lock_stream(self._recovery_lock_path, blocking=True)

    def _write_batch_journal(self, token: BatchToken, phase: str) -> None:
        """把事务 phase 写入 journal。

        Args:
            token: 批处理 token。
            phase: 当前事务阶段。

        Returns:
            无。

        Raises:
            OSError: journal 写入失败时抛出。
        """

        payload = {
            "token_id": token.token_id,
            "ticker": token.ticker,
            "created_at": token.created_at,
            "owner_pid": str(self._current_pid()),
            "hostname": socket.gethostname(),
            "phase": phase,
            "target_dir": str(token.target_ticker_dir),
            "staging_root_dir": str(token.staging_root_dir),
            "staging_ticker_dir": str(token.staging_ticker_dir),
            "backup_dir": str(token.backup_dir),
            "journal_path": str(token.journal_path),
            "ticker_lock_path": str(token.ticker_lock_path),
        }
        _write_json(token.journal_path, payload)

    def _current_pid(self) -> int:
        """返回当前进程 PID。

        Args:
            无。

        Returns:
            当前进程 PID。

        Raises:
            无。
        """
        return os.getpid()

    def _recover_orphan_batch_dirs(self, *, dry_run: bool) -> list[str]:
        """扫描并恢复 batch 暂存目录。

        Args:
            dry_run: 是否仅返回将执行的动作。

        Returns:
            动作摘要列表。

        Raises:
            OSError: 文件系统访问失败时抛出。
        """

        actions: list[str] = []
        if not self.batch_root.exists():
            return actions
        for token_dir in sorted(self.batch_root.iterdir(), key=lambda item: item.name):
            if not token_dir.is_dir():
                continue
            actions.extend(self._recover_single_batch_dir(token_dir, dry_run=dry_run))
        return actions

    def _recover_single_batch_dir(self, token_dir: Path, *, dry_run: bool) -> list[str]:
        """恢复单个 batch token 目录。

        Args:
            token_dir: token 根目录。
            dry_run: 是否仅返回将执行的动作。

        Returns:
            动作摘要列表。

        Raises:
            OSError: 文件系统访问失败时抛出。
        """

        actions: list[str] = []
        journal_path = token_dir / _JOURNAL_FILENAME
        journal_exists = journal_path.exists()
        journal = _read_json_object(journal_path) if journal_exists else {}
        ticker = str(journal.get("ticker", "")).strip() or self._infer_batch_ticker(token_dir)
        phase = str(journal.get("phase", "")).strip()
        if not ticker:
            reason = "missing ticker journal" if journal_exists else "missing journal"
            action = f"skip batch token={token_dir.name} phase={phase or 'unknown'} reason={reason}"
            actions.append(action)
            return actions
        normalized_ticker = _normalize_ticker(ticker)
        ticker_stream = self._try_acquire_recovery_ticker_lock(normalized_ticker)
        if ticker_stream is None:
            return actions
        try:
            target_dir = self._target_ticker_dir(normalized_ticker)
            backup_dir = Path(str(journal.get("backup_dir", "")).strip() or self.backup_root / f"{normalized_ticker}.bak.{token_dir.name}")
            if phase == _PHASE_BACKED_UP_TARGET and backup_dir.exists() and not target_dir.exists():
                actions.append(f"restore backup ticker={normalized_ticker} token={token_dir.name} phase={phase}")
                if not dry_run:
                    target_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(backup_dir), str(target_dir))
            elif phase == _PHASE_SWAPPED_TARGET and backup_dir.exists() and target_dir.exists():
                actions.append(f"delete backup ticker={normalized_ticker} token={token_dir.name} phase={phase}")
                if not dry_run:
                    shutil.rmtree(backup_dir, ignore_errors=True)
            elif backup_dir.exists() and not target_dir.exists():
                actions.append(f"restore backup ticker={normalized_ticker} token={token_dir.name} phase={phase or 'unknown'}")
                if not dry_run:
                    target_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(backup_dir), str(target_dir))
            elif backup_dir.exists() and target_dir.exists():
                actions.append(f"delete backup ticker={normalized_ticker} token={token_dir.name} phase={phase or 'unknown'}")
                if not dry_run:
                    shutil.rmtree(backup_dir, ignore_errors=True)
            actions.append(f"cleanup batch ticker={normalized_ticker} token={token_dir.name} phase={phase or 'unknown'}")
            if not dry_run:
                shutil.rmtree(token_dir, ignore_errors=True)
        finally:
            self._release_lock_stream(ticker_stream)
        return actions

    def _recover_orphan_backup_dirs(self, *, dry_run: bool) -> list[str]:
        """扫描并恢复孤儿备份目录。

        Args:
            dry_run: 是否仅返回将执行的动作。

        Returns:
            动作摘要列表。

        Raises:
            OSError: 文件系统访问失败时抛出。
        """

        actions: list[str] = []
        if not self.backup_root.exists():
            return actions
        for backup_dir in sorted(self.backup_root.iterdir(), key=lambda item: item.name):
            if not backup_dir.is_dir():
                continue
            parsed = _parse_backup_directory_name(backup_dir.name)
            if parsed is None:
                continue
            ticker, token_id = parsed
            token_dir = self.batch_root / token_id
            if token_dir.exists():
                continue
            normalized_ticker = _normalize_ticker(ticker)
            ticker_stream = self._try_acquire_recovery_ticker_lock(normalized_ticker)
            if ticker_stream is None:
                continue
            try:
                target_dir = self._target_ticker_dir(normalized_ticker)
                if target_dir.exists():
                    actions.append(f"delete backup ticker={normalized_ticker} token={token_id}")
                    if not dry_run:
                        shutil.rmtree(backup_dir, ignore_errors=True)
                    continue
                actions.append(f"restore backup ticker={normalized_ticker} token={token_id}")
                if not dry_run:
                    target_dir.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(backup_dir), str(target_dir))
            finally:
                self._release_lock_stream(ticker_stream)
        return actions

    def _infer_batch_ticker(self, token_dir: Path) -> str:
        """从 token 目录结构推断 ticker。

        Args:
            token_dir: token 根目录。

        Returns:
            推断出的 ticker；无法推断时返回空字符串。

        Raises:
            OSError: 目录访问失败时抛出。
        """

        try:
            for child in token_dir.iterdir():
                if child.is_dir():
                    return child.name.strip()
        except FileNotFoundError:
            # 并发恢复场景下，live batch 可能在 recovery 扫描完 token 列表后、
            # 真正进入该 token 前已经完成提交并删掉 staging 根目录。
            # 此时应把它视为“无需恢复的已消失 token”，而不是让 ENOENT
            # 中断整个 recover_orphan_batches 流程。
            return ""
        return ""

    def _try_acquire_recovery_ticker_lock(self, ticker: str) -> TextIO | None:
        """尝试在恢复流程中获取某个 ticker 的锁。

        Args:
            ticker: 股票代码。

        Returns:
            成功时返回已持锁的文件流；若锁正被活跃事务持有则返回 `None`。

        Raises:
            OSError: 锁文件访问失败时抛出。
        """

        try:
            return self._open_and_lock_stream(self._ticker_lock_path(ticker), blocking=False)
        except RuntimeError:
            return None

    # ========== handle 辅助 ==========

    def _handle_dir_path(self, handle: SourceHandle | ProcessedHandle) -> Path:
        """返回句柄对应的文档目录路径。

        Args:
            handle: 源文档/解析产物句柄。

        Returns:
            文档目录路径。

        Raises:
            ValueError: 来源类型非法时抛出。
            OSError: 路径构建失败时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        if isinstance(handle, ProcessedHandle):
            return self._processed_dir_for_read(normalized_ticker, handle.document_id)
        source_kind = _normalize_source_kind(handle.source_kind)
        return self._source_root_for_read(normalized_ticker, source_kind) / handle.document_id

    def _resolve_handle_child_path(self, handle: SourceHandle | ProcessedHandle, name: str) -> Path:
        """解析句柄目录下的直系条目路径。

        Args:
            handle: 源文档/解析产物句柄。
            name: 直系条目名称。

        Returns:
            解析后的绝对路径。

        Raises:
            ValueError: 名称为空、包含路径分隔或越界时抛出。
        """

        normalized_name = _normalize_entry_name(name)
        base_dir = self._handle_dir_path(handle)
        candidate = (base_dir / normalized_name).resolve()
        try:
            candidate.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise ValueError("条目名称越界，禁止访问文档目录外路径") from exc
        return candidate

    def _get_handle_meta(self, handle: SourceHandle | ProcessedHandle) -> dict[str, Any]:
        """读取句柄对应的 meta.json。

        Args:
            handle: 文档句柄。

        Returns:
            meta.json 内容。

        Raises:
            FileNotFoundError: meta.json 不存在时抛出。
            ValueError: JSON 内容非法时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        if isinstance(handle, ProcessedHandle):
            meta_path = self._processed_meta_path_for_read(normalized_ticker, handle.document_id)
        else:
            source_kind = _normalize_source_kind(handle.source_kind)
            meta_path = self._source_meta_path_for_read(normalized_ticker, handle.document_id, source_kind)
        if not meta_path.exists():
            raise FileNotFoundError(f"meta.json 不存在: {meta_path}")
        return _read_json_object(meta_path)

    # ========== core 辅助 ==========

    def _ensure_ticker_structure(self, ticker_dir: Path) -> None:
        """确保 ticker 目录结构存在。

        Args:
            ticker_dir: ticker 目录路径。

        Returns:
            无。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        (ticker_dir / "filings").mkdir(parents=True, exist_ok=True)
        (ticker_dir / "materials").mkdir(parents=True, exist_ok=True)
        (ticker_dir / "processed").mkdir(parents=True, exist_ok=True)

    def _build_file_store(self, ticker: str) -> FileStore:
        """构建文件存储实例。

        Args:
            ticker: 股票代码。

        Returns:
            文件存储实例。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        if self._file_store is not None:
            return self._file_store
        return LocalFileStore(root=self._file_store_root_for_ticker(ticker), scheme="local")

    def _build_store_key(self, handle: SourceHandle | ProcessedHandle, filename: str) -> str:
        """构建对象存储 key。

        Args:
            handle: 文档句柄。
            filename: 文件名。

        Returns:
            逻辑 key。

        Raises:
            ValueError: 来源类型非法时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        if isinstance(handle, ProcessedHandle):
            return f"{normalized_ticker}/processed/{handle.document_id}/{filename}"
        source_kind = _normalize_source_kind(handle.source_kind)
        return f"{normalized_ticker}/{_source_dir_name(source_kind)}/{handle.document_id}/{filename}"

    def _select_primary_document(
        self,
        explicit_primary: Optional[str],
        previous_primary: Any,
        current_file_names: list[str],
        previous_file_names: list[str],
    ) -> Optional[str]:
        """确定主文件名。

        Args:
            explicit_primary: 请求显式传入主文件名。
            previous_primary: 旧 meta 中主文件名。
            current_file_names: 本次写入文件名列表。
            previous_file_names: 上一次保存的文件名列表。

        Returns:
            主文件名；若无法确定则返回 `None`。

        Raises:
            无。
        """

        if isinstance(explicit_primary, str) and explicit_primary.strip():
            return explicit_primary
        if isinstance(previous_primary, str) and previous_primary.strip():
            return previous_primary
        if current_file_names:
            return current_file_names[0]
        if previous_file_names:
            return previous_file_names[0]
        return None

    # ========== manifest 操作 ==========

    def upsert_filing_manifest(self, ticker: str, items: list[FilingManifestItem]) -> None:
        """批量合并写入 filing manifest。

        Args:
            ticker: 股票代码。
            items: filing manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        self._execute_with_auto_batch(
            ticker,
            self._upsert_filing_manifest_impl,
            ticker,
            items,
            admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
        )

    def _upsert_filing_manifest_impl(self, ticker: str, items: list[FilingManifestItem]) -> None:
        """执行 filing manifest 合并写入（内部实现）。

        Args:
            ticker: 股票代码。
            items: filing manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        payloads = [item.to_dict() for item in items]
        self._upsert_manifest_items(self._filing_manifest_path(normalized_ticker), normalized_ticker, payloads)

    def upsert_material_manifest(self, ticker: str, items: list[MaterialManifestItem]) -> None:
        """批量合并写入 material manifest。

        Args:
            ticker: 股票代码。
            items: material manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        self._execute_with_auto_batch(
            ticker,
            self._upsert_material_manifest_impl,
            ticker,
            items,
            admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
        )

    def _upsert_material_manifest_impl(self, ticker: str, items: list[MaterialManifestItem]) -> None:
        """执行 material manifest 合并写入（内部实现）。

        Args:
            ticker: 股票代码。
            items: material manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        payloads = [item.to_dict() for item in items]
        self._upsert_manifest_items(self._material_manifest_path(normalized_ticker), normalized_ticker, payloads)

    def upsert_processed_manifest(self, ticker: str, items: list[ProcessedManifestItem]) -> None:
        """批量合并写入 processed manifest。

        Args:
            ticker: 股票代码。
            items: processed manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        self._execute_with_auto_batch(
            ticker,
            self._upsert_processed_manifest_impl,
            ticker,
            items,
            admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
        )

    def _upsert_processed_manifest_impl(self, ticker: str, items: list[ProcessedManifestItem]) -> None:
        """执行 processed manifest 合并写入（内部实现）。

        Args:
            ticker: 股票代码。
            items: processed manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        payloads = [item.to_dict() for item in items]
        self._upsert_manifest_items(self._processed_manifest_path(normalized_ticker), normalized_ticker, payloads)

    def _upsert_manifest_items(self, path: Path, ticker: str, items: list[dict[str, Any]]) -> None:
        """合并并写入 manifest 项目。

        Args:
            path: manifest 文件路径。
            ticker: 股票代码。
            items: 待写入项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败。
        """

        manifest = self._read_manifest(path, ticker)
        documents_map = {doc["document_id"]: doc for doc in manifest["documents"] if "document_id" in doc}
        for item in items:
            documents_map[item["document_id"]] = item
        manifest["documents"] = sorted(documents_map.values(), key=lambda x: x["document_id"])
        manifest["updated_at"] = now_iso8601()
        _write_json(path, manifest)

    def _remove_manifest_item(self, path: Path, ticker: str, document_id: str) -> None:
        """从 manifest 中移除一个文档项目。

        Args:
            path: manifest 文件路径。
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            无。

        Raises:
            OSError: 写入失败。
        """

        manifest = self._read_manifest(path, ticker)
        manifest["documents"] = [doc for doc in manifest["documents"] if doc.get("document_id") != document_id]
        manifest["updated_at"] = now_iso8601()
        _write_json(path, manifest)

    def _remove_manifest_items(self, path: Path, ticker: str, document_ids: list[str]) -> None:
        """从 manifest 中批量移除文档项目。

        Args:
            path: manifest 文件路径。
            ticker: 股票代码。
            document_ids: 待移除的文档 ID 列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        stale_set = set(document_ids)
        manifest = self._read_manifest(path, ticker)
        manifest["documents"] = [doc for doc in manifest["documents"] if doc.get("document_id") not in stale_set]
        manifest["updated_at"] = now_iso8601()
        _write_json(path, manifest)

    def _read_manifest(self, path: Path, ticker: str) -> dict[str, Any]:
        """读取 manifest，不存在则返回默认结构。

        Args:
            path: manifest 路径。
            ticker: 股票代码。

        Returns:
            manifest 字典。

        Raises:
            ValueError: JSON 内容非法时抛出。
            OSError: 文件读取失败时抛出。
        """

        if path.exists():
            return _read_json_object(path)
        return {"ticker": ticker, "updated_at": now_iso8601(), "documents": []}

    # ========== 路径方法 ==========

    def _target_ticker_dir(self, ticker: str) -> Path:
        """返回正式 ticker 目录。

        Args:
            ticker: 股票代码。

        Returns:
            正式目录路径。

        Raises:
            无。
        """

        return self.portfolio_root / ticker

    def _ticker_dir_for_write(self, ticker: str) -> Path:
        """返回当前可写 ticker 目录（优先 batch staging）。

        Args:
            ticker: 股票代码。

        Returns:
            可写目录路径。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        token = self._active_batches.get(ticker)
        if token is not None:
            self._ensure_ticker_structure(token.staging_ticker_dir)
            return token.staging_ticker_dir
        target = self._target_ticker_dir(ticker)
        self._ensure_ticker_structure(target)
        return target

    def _ticker_dir_for_read(self, ticker: str) -> Path:
        """返回当前可读 ticker 目录（优先 batch staging）。

        Args:
            ticker: 股票代码。

        Returns:
            可读目录路径。

        Raises:
            无。
        """

        token = self._active_batches.get(ticker)
        if token is not None:
            return token.staging_ticker_dir
        return self._target_ticker_dir(ticker)

    def _file_store_root_for_ticker(self, ticker: str) -> Path:
        """获取文件存储根目录（兼容 batch staging）。

        Args:
            ticker: 股票代码。

        Returns:
            文件存储根目录。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        token = self._active_batches.get(ticker)
        if token is not None:
            self._ensure_ticker_structure(token.staging_ticker_dir)
            return token.staging_ticker_dir.parent
        self._ensure_ticker_structure(self._target_ticker_dir(ticker))
        return self.portfolio_root

    def _source_root(self, ticker: str, source_kind: SourceKind) -> Path:
        """返回来源目录根路径。

        Args:
            ticker: 股票代码。
            source_kind: 来源类型。

        Returns:
            来源目录路径。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        ticker_dir = self._ticker_dir_for_write(ticker)
        if source_kind == SourceKind.FILING:
            return ticker_dir / "filings"
        return ticker_dir / "materials"

    def _source_root_for_read(self, ticker: str, source_kind: SourceKind) -> Path:
        """返回来源目录根路径（用于读取）。

        Args:
            ticker: 股票代码。
            source_kind: 来源类型。

        Returns:
            来源目录路径。

        Raises:
            无。
        """

        ticker_dir = self._ticker_dir_for_read(ticker)
        if source_kind == SourceKind.FILING:
            return ticker_dir / "filings"
        return ticker_dir / "materials"

    def _source_meta_path(self, ticker: str, document_id: str, source_kind: SourceKind) -> Path:
        """返回源文档 meta 路径。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            meta 文件路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._source_root(ticker, source_kind) / document_id / _SOURCE_META_FILENAME

    def _source_meta_path_for_read(self, ticker: str, document_id: str, source_kind: SourceKind) -> Path:
        """返回源文档 meta 路径（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            meta 文件路径。

        Raises:
            无。
        """

        return self._source_root_for_read(ticker, source_kind) / document_id / _SOURCE_META_FILENAME

    def _company_meta_path(self, ticker: str) -> Path:
        """返回公司级 meta 路径。

        Args:
            ticker: 股票代码。

        Returns:
            公司级 meta 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        return self._ticker_dir_for_write(normalized_ticker) / _SOURCE_META_FILENAME

    def _company_meta_path_for_read(self, ticker: str) -> Path:
        """返回公司级 meta 路径（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            公司级 meta 路径。

        Raises:
            无。
        """

        normalized_ticker = _normalize_ticker(ticker)
        return self._ticker_dir_for_read(normalized_ticker) / _SOURCE_META_FILENAME

    def _filing_manifest_path(self, ticker: str) -> Path:
        """返回 filing manifest 路径。

        Args:
            ticker: 股票代码。

        Returns:
            filing manifest 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker) / "filings" / "filing_manifest.json"

    def _filing_manifest_path_for_read(self, ticker: str) -> Path:
        """返回 filing manifest 路径（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            filing manifest 路径。

        Raises:
            无。
        """

        return self._ticker_dir_for_read(ticker) / "filings" / "filing_manifest.json"

    def _material_manifest_path(self, ticker: str) -> Path:
        """返回 material manifest 路径。

        Args:
            ticker: 股票代码。

        Returns:
            material manifest 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker) / "materials" / "material_manifest.json"

    def _material_manifest_path_for_read(self, ticker: str) -> Path:
        """返回 material manifest 路径（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            material manifest 路径。

        Raises:
            无。
        """

        return self._ticker_dir_for_read(ticker) / "materials" / "material_manifest.json"

    def _processed_manifest_path(self, ticker: str) -> Path:
        """返回 processed manifest 路径。

        Args:
            ticker: 股票代码。

        Returns:
            processed manifest 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker) / "processed" / "manifest.json"

    def _processed_manifest_path_for_read(self, ticker: str) -> Path:
        """返回 processed manifest 路径（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            processed manifest 路径。

        Raises:
            无。
        """

        return self._ticker_dir_for_read(ticker) / "processed" / "manifest.json"

    def _processed_dir_for_write(self, ticker: str, document_id: str) -> Path:
        """获取解析产物目录路径（用于写入）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            解析产物目录路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        return self._ticker_dir_for_write(normalized_ticker) / "processed" / document_id

    def _processed_dir_for_read(self, ticker: str, document_id: str) -> Path:
        """获取解析产物目录路径（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            解析产物目录路径。

        Raises:
            无。
        """

        normalized_ticker = _normalize_ticker(ticker)
        return self._ticker_dir_for_read(normalized_ticker) / "processed" / document_id

    def _processed_meta_path(self, ticker: str, document_id: str) -> Path:
        """获取解析产物 tool_snapshot_meta.json 路径。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            tool_snapshot_meta.json 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._processed_dir_for_write(ticker, document_id) / _PROCESSED_META_FILENAME

    def _processed_meta_path_for_read(self, ticker: str, document_id: str) -> Path:
        """获取解析产物 tool_snapshot_meta.json 路径（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            tool_snapshot_meta.json 路径。

        Raises:
            无。
        """

        return self._processed_dir_for_read(ticker, document_id) / _PROCESSED_META_FILENAME

    def _download_rejections_path(self, ticker: str) -> Path:
        """返回下载拒绝注册表路径。

        Args:
            ticker: 股票代码。

        Returns:
            拒绝注册表路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker) / "filings" / _DOWNLOAD_REJECTIONS_FILENAME

    def _download_rejections_path_for_read(self, ticker: str) -> Path:
        """返回下载拒绝注册表路径（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            拒绝注册表路径。

        Raises:
            无。
        """

        return self._ticker_dir_for_read(ticker) / "filings" / _DOWNLOAD_REJECTIONS_FILENAME

    def _rejected_filings_root(self, ticker: str) -> Path:
        """返回 rejected filings 根目录。

        Args:
            ticker: 股票代码。

        Returns:
            rejected filings 根目录。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker) / "filings" / _REJECTED_FILINGS_DIRNAME

    def _rejected_filings_root_for_read(self, ticker: str) -> Path:
        """返回 rejected filings 根目录（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            rejected filings 根目录。

        Raises:
            无。
        """

        return self._ticker_dir_for_read(ticker) / "filings" / _REJECTED_FILINGS_DIRNAME

    def _rejected_filing_dir(self, ticker: str, document_id: str) -> Path:
        """返回单个 rejected filing 目录。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            文档目录路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._rejected_filings_root(ticker) / document_id

    def _rejected_filing_dir_for_read(self, ticker: str, document_id: str) -> Path:
        """返回单个 rejected filing 目录（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            文档目录路径。

        Raises:
            无。
        """

        return self._rejected_filings_root_for_read(ticker) / document_id

    def _rejected_filing_meta_path(self, ticker: str, document_id: str) -> Path:
        """返回 rejected filing meta 路径。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            meta.json 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._rejected_filing_dir(ticker, document_id) / _SOURCE_META_FILENAME

    def _rejected_filing_meta_path_for_read(self, ticker: str, document_id: str) -> Path:
        """返回 rejected filing meta 路径（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            meta.json 路径。

        Raises:
            无。
        """

        return self._rejected_filing_dir_for_read(ticker, document_id) / _SOURCE_META_FILENAME

    def _rejected_filing_file_path_for_read(self, ticker: str, document_id: str, filename: str) -> Path:
        """返回 rejected filing 文件路径（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            filename: 文件名。

        Returns:
            文件路径。

        Raises:
            ValueError: 文件名为空或越界时抛出。
        """

        normalized_name = _normalize_entry_name(filename)
        base_dir = self._rejected_filing_dir_for_read(ticker, document_id)
        candidate = (base_dir / normalized_name).resolve()
        try:
            candidate.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise ValueError("条目名称越界，禁止访问文档目录外路径") from exc
        return candidate


def _update_publish_state(journal: RemoteOpJournal, final_key: str, state: str) -> None:
    """把 journal 中指定 publish target 的 publish_state 更新为给定值。

    Args:
        journal: 待更新的 journal。
        final_key: 目标 final key。
        state: 新 publish_state。

    Returns:
        无。

    Raises:
        无。
    """

    for index, target in enumerate(journal.publish_targets):
        if target.final_key == final_key:
            journal.publish_targets[index] = RemotePublishTarget(
                final_key=target.final_key,
                staging_key=target.staging_key,
                sha256=target.sha256,
                size=target.size,
                content_type=target.content_type,
                metadata=dict(target.metadata),
                publish_state=state,
            )
            return


def _update_delete_state(journal: RemoteOpJournal, final_key: str, state: str) -> None:
    """把 journal 中指定 delete target 的 delete_state 更新为给定值。

    Args:
        journal: 待更新的 journal。
        final_key: 目标 final key。
        state: 新 delete_state。

    Returns:
        无。

    Raises:
        无。
    """

    for index, target in enumerate(journal.delete_targets):
        if target.final_key == final_key:
            journal.delete_targets[index] = RemoteDeleteTarget(
                final_key=target.final_key,
                expected_sha256=target.expected_sha256,
                expected_size=target.expected_size,
                delete_state=state,
            )
            return
