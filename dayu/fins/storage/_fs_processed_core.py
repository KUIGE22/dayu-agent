"""文件系统仓储 — 解析产物操作 mixin。

S3 模式（注入 ``StagedFileStoreProtocol``）下：
- ``_upsert_processed`` 的 sections/tables/financials JSON 走 FileStore
  （final key ``{TICKER}/processed/{document_id}/{filename}``），
  计数/是否含 financials 从请求与 previous meta 计算，绝不读尚未发布的
  远端 final 对象（S14-CTRL-13）；
- 所有 metadata mutation 比较 old/new authoritative inventory，在 local
  metadata swap 前把 removed targets journal 为 ``action=delete`` delete
  intents（S14-CTRL-13 inventory contraction）；processed meta 显式持久化
  authoritative files inventory；
- ``financials`` present -> None 必须先 diff old/new inventory 并把移除的
  ``processed/.../financials.json`` 记为 ``action=delete`` target；
- delete/clear 从 old authoritative files inventory 逐 key 复用 stage-delete
  helper 记录 delete intents 后再只 ``rmtree``/``unlink`` staging local；
  remote delete 只在 commit 的 post-swap cleanup 或 recovery 收敛；
- admission 分类：create/update/delete/mark/clear 均
  ``AUTO_ATOMIC_ALLOWED``（单-repository 完整原子语义单元）。

FS/local 模式行为逐字节不变。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TypeAlias

from dayu.fins.domain.document_models import (
    DocumentHandle,
    DocumentMeta,
    ProcessedCreateRequest,
    ProcessedDeleteRequest,
    ProcessedHandle,
    ProcessedManifestItem,
    ProcessedUpdateRequest,
    now_iso8601,
)

from ._fs_storage_infra import BatchAdmission, _FsStorageInfra
from ._fs_storage_utils import (
    _PROCESSED_META_FILENAME,
    _normalize_ticker,
    _read_json_object,
    _write_json,
)

_ProcessedJsonPayload: TypeAlias = DocumentMeta | list[DocumentMeta]
"""processed JSON 文件的 legacy ingress payload。

与仓储协议接受的既有 ``DocumentMeta`` 领域形状一致（即 legacy 元数据字典
形状），仅用于 ``_upsert_processed`` 的 S3 写入边界；随后 ``json.dumps``
序列化为字节，不展开递归 JSON 契约。
"""


class _FsProcessedMixin(_FsStorageInfra):
    """解析产物（processed）操作 mixin。"""

    # ========== processed CRUD ==========

    def create_processed(self, req: ProcessedCreateRequest) -> DocumentHandle:
        """创建解析产物。

        Args:
            req: 解析产物创建请求。

        Returns:
            文档句柄。

        Raises:
            FileExistsError: 产物已存在时抛出。
            OSError: 写入失败时抛出。
        """

        return self._execute_with_auto_batch(
            req.ticker,
            self._upsert_processed,
            req,
            True,
            admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
        )

    def update_processed(self, req: ProcessedUpdateRequest) -> DocumentHandle:
        """更新解析产物。

        Args:
            req: 解析产物更新请求。

        Returns:
            文档句柄。

        Raises:
            FileNotFoundError: 产物不存在时抛出。
            OSError: 更新失败时抛出。
        """

        return self._execute_with_auto_batch(
            req.ticker,
            self._upsert_processed,
            req,
            False,
            admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
        )

    def delete_processed(self, req: ProcessedDeleteRequest) -> None:
        """删除解析产物。

        Args:
            req: 解析产物删除请求。

        Returns:
            无。

        Raises:
            FileNotFoundError: 产物不存在时抛出。
            OSError: 删除失败时抛出。
        """

        self._execute_with_auto_batch(
            req.ticker,
            self._delete_processed_impl,
            req,
            admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
        )

    def _delete_processed_impl(self, req: ProcessedDeleteRequest) -> None:
        """执行解析产物删除（内部实现）。

        Args:
            req: 解析产物删除请求。

        Returns:
            无。

        Raises:
            FileNotFoundError: 产物不存在时抛出。
            OSError: 删除失败时抛出。
        """

        ticker = _normalize_ticker(req.ticker)
        processed_dir = self._processed_dir_for_write(ticker, req.document_id)
        if not processed_dir.exists():
            raise FileNotFoundError(f"processed 文档不存在: {processed_dir}")
        if self._is_s3_mode():
            self._stage_delete_processed_dir(ticker, req.document_id)
        shutil.rmtree(processed_dir)
        self._remove_manifest_item(self._processed_manifest_path(ticker), ticker, req.document_id)

    def _stage_delete_processed_dir(self, ticker: str, document_id: str) -> None:
        """S3 模式：从 processed meta 的 files inventory 逐 key 记录 delete intents。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            无。

        Raises:
            OSError: journal 写入失败时抛出。
        """

        token = self._active_batches.get(_normalize_ticker(ticker))
        if token is None:
            raise RuntimeError("s3_write_requires_batch")
        meta_path = self._processed_meta_path_for_read(ticker, document_id)
        if not meta_path.exists():
            return
        meta = _read_json_object(meta_path)
        for filename in _iterate_processed_file_keys(meta):
            key = f"{_normalize_ticker(ticker)}/processed/{document_id}/{filename}"
            self._stage_delete_one_key(token, key)

    # ========== handle & 元数据 ==========

    def get_processed_handle(self, ticker: str, document_id: str) -> ProcessedHandle:
        """获取解析产物句柄。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            解析产物句柄。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        meta_path = self._processed_meta_path_for_read(normalized_ticker, document_id)
        if not meta_path.exists():
            raise FileNotFoundError(f"processed 文档不存在: {meta_path}")
        return ProcessedHandle(
            ticker=normalized_ticker,
            document_id=document_id,
        )

    def get_processed_meta(self, ticker: str, document_id: str) -> DocumentMeta:
        """读取 processed 元数据。

        优先读取 ``meta.json``；若不存在则回退到 ``tool_snapshot_meta.json``
        （CI 管线产物）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            processed 元数据字典。

        Raises:
            FileNotFoundError: 两种元数据文件均不存在时抛出。
            ValueError: 元数据格式非法时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        meta_path = self._processed_meta_path_for_read(normalized_ticker, document_id)
        if meta_path.exists():
            return _read_json_object(meta_path)
        raise FileNotFoundError(f"processed 元数据不存在: {meta_path}")

    # ========== reprocess ==========

    def mark_processed_reprocess_required(self, ticker: str, document_id: str) -> bool:
        """将 processed 文档标记为需要重处理。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            是否成功标记。

        Raises:
            OSError: 读写失败时抛出。
        """

        return self._execute_with_auto_batch(
            ticker,
            self._mark_processed_reprocess_required_impl,
            ticker,
            document_id,
            admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
        )

    def _mark_processed_reprocess_required_impl(self, ticker: str, document_id: str) -> bool:
        """执行重处理标记写入（内部实现）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            是否成功标记。

        Raises:
            OSError: 读写失败时抛出。
        """

        processed_meta_path = self._processed_meta_path(_normalize_ticker(ticker), document_id)
        if not processed_meta_path.exists():
            return False
        processed_meta = _read_json_object(processed_meta_path)
        processed_meta["reprocess_required"] = True
        processed_meta["updated_at"] = now_iso8601()
        _write_json(processed_meta_path, processed_meta)
        return True

    # ========== 批量清理 ==========

    def clear_processed_documents(self, ticker: str) -> None:
        """清空某个 ticker 下的 processed 目录内容。

        Args:
            ticker: 股票代码。

        Returns:
            无。

        Raises:
            OSError: 清理失败时抛出。
        """

        self._execute_with_auto_batch(
            ticker,
            self._clear_processed_documents_impl,
            ticker,
            admission=BatchAdmission.AUTO_ATOMIC_ALLOWED,
        )

    def _clear_processed_documents_impl(self, ticker: str) -> None:
        """执行 processed 目录清理（内部实现）。

        Args:
            ticker: 股票代码。

        Returns:
            无。

        Raises:
            OSError: 清理失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        processed_dir = self._ticker_dir_for_write(normalized_ticker) / "processed"
        if not processed_dir.exists():
            return
        if self._is_s3_mode():
            self._stage_delete_processed_children(normalized_ticker, processed_dir)
        for child in processed_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
                continue
            child.unlink(missing_ok=True)

    def _stage_delete_processed_children(self, ticker: str, processed_dir: Path) -> None:
        """S3 模式：逐个 processed 子目录记录 delete intents。

        Args:
            ticker: 股票代码。
            processed_dir: processed 根目录路径。

        Returns:
            无。

        Raises:
            OSError: journal 写入失败时抛出。
        """

        token = self._active_batches.get(ticker)
        if token is None:
            raise RuntimeError("s3_write_requires_batch")
        for child in sorted(processed_dir.iterdir(), key=lambda item: item.name):
            if not child.is_dir():
                continue
            meta_path = child / _PROCESSED_META_FILENAME
            if not meta_path.exists():
                continue
            try:
                meta = _read_json_object(meta_path)
            except (ValueError, OSError):
                continue
            for filename in _iterate_processed_file_keys(meta):
                key = f"{ticker}/processed/{child.name}/{filename}"
                self._stage_delete_one_key(token, key)

    # ========== 内部实现 ==========

    def _upsert_processed(self, req: ProcessedCreateRequest | ProcessedUpdateRequest, is_create: bool) -> DocumentHandle:
        """创建或更新解析产物。

        Args:
            req: 解析产物请求。
            is_create: 是否创建流程。

        Returns:
            文档句柄。

        Raises:
            FileExistsError: 创建时已存在。
            FileNotFoundError: 更新时不存在。
            OSError: 写入失败。
        """

        ticker = _normalize_ticker(req.ticker)
        processed_dir = self._processed_dir_for_write(ticker, req.document_id)
        meta_path = processed_dir / _PROCESSED_META_FILENAME

        exists = processed_dir.exists()
        if is_create and exists:
            raise FileExistsError(f"processed 文档已存在: {processed_dir}")
        if not is_create and not exists:
            raise FileNotFoundError(f"processed 文档不存在: {processed_dir}")

        processed_dir.mkdir(parents=True, exist_ok=True)
        previous_meta = _read_json_object(meta_path) if meta_path.exists() else {}
        previous_files = _extract_processed_files(previous_meta)
        new_files: list[str] = []

        if self._is_s3_mode():
            _stage_processed_json_entries(
                self,
                ticker,
                req.document_id,
                (
                    ("sections.json", req.sections),
                    ("tables.json", req.tables),
                    ("financials.json", req.financials),
                ),
            )
            new_files.extend(_iter_present_processed_files(req))
        else:
            if req.sections is not None:
                _write_json(processed_dir / "sections.json", req.sections)
                new_files.append("sections.json")
            if req.tables is not None:
                _write_json(processed_dir / "tables.json", req.tables)
                new_files.append("tables.json")
            if req.financials is not None:
                _write_json(processed_dir / "financials.json", req.financials)
                new_files.append("financials.json")

        financials_present = req.financials is not None
        financials_path = processed_dir / "financials.json"
        if not financials_present and self._is_s3_mode():
            # inventory contraction：financials present -> None 必须把移除的
            # financials.json 记为 action=delete target。
            if "financials.json" in previous_files:
                token = self._active_batches.get(ticker)
                if token is not None:
                    self._stage_delete_one_key(
                        token,
                        f"{ticker}/processed/{req.document_id}/financials.json",
                    )
        elif not financials_present and financials_path.exists():
            # 显式移除旧 financials，避免 has_xbrl 被历史产物污染。
            financials_path.unlink()

        # 计数与是否含 financials 从请求与 previous meta 计算：S3 模式下新写
        # 字节只存在于 staging、尚未发布到 final key，读远端 final 会看到旧值
        # （S14-CTRL-13 inventory contraction，不读未发布对象）。
        section_count = (
            len(req.sections)
            if req.sections is not None
            else int(previous_meta.get("section_count", 0))
        )
        table_count = (
            len(req.tables)
            if req.tables is not None
            else int(previous_meta.get("table_count", 0))
        )
        has_xbrl = financials_present

        merged_meta = dict(previous_meta)
        merged_meta.update(req.meta)
        merged_meta["document_id"] = req.document_id
        merged_meta["internal_document_id"] = req.internal_document_id
        merged_meta["source_kind"] = req.source_kind
        merged_meta.setdefault("source_document_version", "v1")
        merged_meta.setdefault("schema_version", "v1")
        merged_meta.setdefault("parser_version", "v1")
        merged_meta.setdefault("source_fingerprint", "")
        merged_meta.setdefault("reprocess_required", False)
        merged_meta["section_count"] = section_count
        merged_meta["table_count"] = table_count
        merged_meta["has_xbrl"] = has_xbrl
        merged_meta["processed_at"] = now_iso8601()
        # 显式持久化 authoritative files inventory（S14-CTRL-13）。
        merged_meta["files"] = _merge_processed_files(
            previous_files, new_files, financials_present=financials_present
        )

        _write_json(meta_path, merged_meta)

        self.upsert_processed_manifest(
            ticker,
            [
                ProcessedManifestItem(
                    document_id=req.document_id,
                    internal_document_id=req.internal_document_id,
                    source_kind=req.source_kind,
                    form_type=req.form_type,
                    material_name=merged_meta.get("material_name"),
                    fiscal_year=merged_meta.get("fiscal_year"),
                    fiscal_period=merged_meta.get("fiscal_period"),
                    report_date=merged_meta.get("report_date"),
                    filing_date=merged_meta.get("filing_date"),
                    amended=bool(merged_meta.get("amended", False)),
                    is_deleted=bool(merged_meta.get("is_deleted", False)),
                    document_version=str(merged_meta.get("source_document_version", "v1")),
                    quality=str(merged_meta.get("quality", "full")),
                    has_financials=has_xbrl,
                    section_count=section_count,
                    table_count=table_count,
                )
            ],
        )

        return DocumentHandle(
            ticker=ticker,
            document_id=req.document_id,
            form_type=req.form_type,
        )


def _extract_processed_files(meta: DocumentMeta) -> list[str]:
    """从 processed meta 提取 files 清单。

    Args:
        meta: processed 元数据字典。

    Returns:
        文件名列表。

    Raises:
        无。
    """

    files = meta.get("files", [])
    if not isinstance(files, list):
        return []
    return [str(item) for item in files if isinstance(item, str) and item]


def _merge_processed_files(
    previous: list[str],
    new: list[str],
    *,
    financials_present: bool,
) -> list[str]:
    """合并 processed files 清单（去重保序，financials 显式移除）。

    Args:
        previous: 旧文件清单。
        new: 本次写入的文件名列表。
        financials_present: 请求中 financials 是否为非 ``None``；为 ``False``
            时从合并结果中移除 ``financials.json``。

    Returns:
        合并后的清单。

    Raises:
        无。
    """

    removed = frozenset() if financials_present else frozenset({"financials.json"})
    merged: list[str] = []
    for name in [*previous, *new]:
        if name in removed or name in merged:
            continue
        merged.append(name)
    return merged


def _iterate_processed_file_keys(meta: DocumentMeta) -> list[str]:
    """从 processed meta 迭代文件 key 名。

    Args:
        meta: processed 元数据字典。

    Returns:
        文件名字符串列表。

    Raises:
        无。
    """

    return _extract_processed_files(meta)


def _iter_present_processed_files(
    req: ProcessedCreateRequest | ProcessedUpdateRequest,
) -> list[str]:
    """枚举请求中非 None 的 processed JSON 文件名。

    Args:
        req: processed 写入请求。

    Returns:
        本次写入存在的文件名列表。

    Raises:
        无。
    """

    present: list[str] = []
    if req.sections is not None:
        present.append("sections.json")
    if req.tables is not None:
        present.append("tables.json")
    if req.financials is not None:
        present.append("financials.json")
    return present


def _stage_processed_json_entries(
    owner: _FsProcessedMixin,
    ticker: str,
    document_id: str,
    entries: tuple[tuple[str, _ProcessedJsonPayload | None], ...],
) -> None:
    """S3 模式：把 processed JSON 逐文件 staging + journal。

    Args:
        owner: processed mixin 实例（复用 batch/journal 语义）。
        ticker: 股票代码。
        document_id: 文档 ID。
        entries: ``(filename, payload)`` 序列；payload 为 ``None`` 的条目跳过。

    Returns:
        无。

    Raises:
        RuntimeError: 无 active batch 时抛出 ``s3_write_requires_batch``。
        OSError: staging 写入或 journal 追加失败时抛出。
    """

    import io
    import json

    for filename, payload in entries:
        if payload is None:
            continue
        token = owner._active_batches.get(ticker)
        if token is None:
            raise RuntimeError("s3_write_requires_batch")
        serialized = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        stream = io.BytesIO(serialized)
        owner._stage_publish(
            token,
            final_key=f"{ticker}/processed/{document_id}/{filename}",
            data=stream,
            content_type="application/json",
        )
