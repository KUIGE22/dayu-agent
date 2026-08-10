"""S3 模式 remote-operation journal。

本模块承载 S3 模式下字节发布/删除的最小 remote journal（S14-CTRL-04）：

- journal 文件为 ``.dayu/remote_ops/{operation_id}.json``，``operation_id``
  等于 FS batch token id；**顶层 ``phase`` 只表示 batch/meta 阶段，绝不承载
  bytes 发布进度**；
- 每个 target 的 ``action`` 闭合字节目标的两种处理：
  ``publish``（staging -> final 发布，``publish_state: staged|final_verified``）
  与 ``delete``（staged-delete，``delete_state: pending|remote_deleted``）；
- 顶层 ``phase`` 状态机：``staged -> metadata_committed -> cleanup_done``，
  旁路 ``rolled_back`` 与 ``metadata_committed + cleanup_pending``（cleanup
  失败）；publish 进度由 ``publish_state`` 独立表达、delete 进度由
  ``delete_state`` 独立表达，顶层 phase 与 per-target state 不得互相推导；
- journal 是 S3 bytes 与 FS metadata 之间唯一 recovery 真源：``read_journal``
  严格区分缺失与损坏——仅文件真正不存在返回 ``None``，存在但任何
  schema/phase/action/state/key/digest/size/唯一性非法都稳定抛
  ``RemoteOpJournalError`` fail closed，绝不允许把损坏 journal 当作不存在；
- 本模块使用独立模块私有 atomic JSON helper（same-dir temp + flush +
  fsync + ``os.replace`` + parent dir fsync），不复用
  ``_fs_storage_utils._write_json``。
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from dayu.fins.domain.evidence_locator import JsonValue

_PHASE_STAGED = "staged"
_PHASE_METADATA_COMMITTED = "metadata_committed"
_PHASE_CLEANUP_DONE = "cleanup_done"
_PHASE_ROLLED_BACK = "rolled_back"
_PHASE_CLEANUP_PENDING = "cleanup_pending"

_ACTION_PUBLISH = "publish"
_ACTION_DELETE = "delete"

_PUBLISH_STATE_STAGED = "staged"
_PUBLISH_STATE_FINAL_VERIFIED = "final_verified"

_DELETE_STATE_PENDING = "pending"
_DELETE_STATE_REMOTE_DELETED = "remote_deleted"

_VALID_PHASES = frozenset(
    {
        _PHASE_STAGED,
        _PHASE_METADATA_COMMITTED,
        _PHASE_CLEANUP_DONE,
        _PHASE_ROLLED_BACK,
        _PHASE_CLEANUP_PENDING,
    }
)
_VALID_ACTIONS = frozenset({_ACTION_PUBLISH, _ACTION_DELETE})
_VALID_PUBLISH_STATES = frozenset({_PUBLISH_STATE_STAGED, _PUBLISH_STATE_FINAL_VERIFIED})
_VALID_DELETE_STATES = frozenset({_DELETE_STATE_PENDING, _DELETE_STATE_REMOTE_DELETED})
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
"""content digest 必须为 64 位小写 hex。"""
_STAGING_NAMESPACE_PREFIX = ".dayu-staging/"
"""staging key 命名空间前缀；staging key 必须为 ``{prefix}{operation_id}/...``。"""


class RemoteOpJournalError(RuntimeError):
    """remote-operation journal 读写或状态非法时抛出的错误。"""


@dataclass(frozen=True)
class RemotePublishTarget:
    """单个 publish target。

    Args:
        final_key: 最终对象 key。
        staging_key: staging key（``.dayu-staging/{operation_id}/{sha256}``）。
        sha256: 内容 SHA-256。
        size: 内容字节数。
        content_type: 可选内容类型。
        metadata: 可选扩展元数据。
        publish_state: 发布状态（staged|final_verified）。
    """

    final_key: str
    staging_key: str
    sha256: str
    size: int
    content_type: str | None
    metadata: dict[str, str]
    publish_state: str


@dataclass(frozen=True)
class RemoteDeleteTarget:
    """单个 delete target。

    Args:
        final_key: 最终对象 key。
        expected_sha256: head 时记录的期望 SHA-256。
        expected_size: head 时记录的期望大小。
        delete_state: 删除状态（pending|remote_deleted）。
    """

    final_key: str
    expected_sha256: str
    expected_size: int
    delete_state: str


@dataclass(frozen=True)
class RemoteOpJournal:
    """remote-operation journal 的数据视图。

    Args:
        operation_id: 操作唯一标识（等于 FS batch token id）。
        ticker: 对应股票代码。
        created_at: 创建时间（ISO8601）。
        owner_pid: 创建进程 PID。
        phase: 顶层 batch/meta 阶段。
        publish_targets: publish target 列表。
        delete_targets: delete target 列表。
    """

    operation_id: str
    ticker: str
    created_at: str
    owner_pid: str
    phase: str
    publish_targets: list[RemotePublishTarget] = field(default_factory=list)
    delete_targets: list[RemoteDeleteTarget] = field(default_factory=list)


def journal_path(dayu_root: Path, operation_id: str) -> Path:
    """返回指定 operation 的 journal 文件路径。

    Args:
        dayu_root: 工作区 ``.dayu`` 目录。
        operation_id: 操作唯一标识。

    Returns:
        journal 文件路径。

    Raises:
        无。
    """

    return dayu_root / "remote_ops" / f"{operation_id}.json"


def write_journal(dayu_root: Path, journal: RemoteOpJournal) -> None:
    """原子写入 journal 文件。

    Args:
        dayu_root: 工作区 ``.dayu`` 目录。
        journal: 待持久化的 journal 视图。

    Returns:
        无。

    Raises:
        RemoteOpJournalError: 序列化或写入失败时抛出。
    """

    payload = _journal_to_dict(journal)
    path = journal_path(dayu_root, journal.operation_id)
    try:
        _write_json_atomic(path, payload)
    except (OSError, TypeError) as exc:
        raise RemoteOpJournalError("remote journal 写入失败") from exc


def read_journal(dayu_root: Path, operation_id: str) -> RemoteOpJournal | None:
    """读取指定 operation 的 journal（严格区分缺失与损坏）。

    journal 文件名身份（``{operation_id}.json``）与 payload 内
    ``operation_id`` 是同一 batch 的双重身份（S14-RR-01）：文件名的
    operation id 作为期望身份传入严格 parser，payload 必须精确相等，
    任一不一致即视为存在但损坏的 journal，在任何远端/FS 副作用前稳定
    fail closed，保留 journal、staging metadata 与远端 objects。

    Args:
        dayu_root: 工作区 ``.dayu`` 目录。
        operation_id: 操作唯一标识（journal 文件名身份）。

    Returns:
        journal 视图；仅当文件真正不存在时返回 ``None``。

    Raises:
        RemoteOpJournalError: 文件存在但 JSON/顶层类型/schema/phase/action/
            state/key/digest/size/唯一性/operation_id 身份/staging 命名空间
            任一非法时抛出（fail closed，保留 journal 供人工恢复）。
    """

    path = journal_path(dayu_root, operation_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RemoteOpJournalError("remote journal 无法解析") from exc
    if not isinstance(payload, dict):
        raise RemoteOpJournalError("remote journal 顶层必须为字典")
    return _journal_from_dict(payload, expected_operation_id=operation_id)


def list_journal_ids(dayu_root: Path) -> list[str]:
    """列出 remote_ops 目录下的全部 operation id。

    Args:
        dayu_root: 工作区 ``.dayu`` 目录。

    Returns:
        按文件名字典序排列的 operation id 列表。

    Raises:
        无。
    """

    remote_ops_dir = dayu_root / "remote_ops"
    if not remote_ops_dir.exists():
        return []
    ids: list[str] = []
    for path in sorted(remote_ops_dir.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.suffix == ".json":
            ids.append(path.stem)
    return ids


def remove_journal(dayu_root: Path, operation_id: str) -> None:
    """移除指定 operation 的 journal 文件（幂等）。

    Args:
        dayu_root: 工作区 ``.dayu`` 目录。
        operation_id: 操作唯一标识。

    Returns:
        无。

    Raises:
        OSError: 文件删除失败时抛出。
    """

    path = journal_path(dayu_root, operation_id)
    if path.exists():
        path.unlink()


def _journal_to_dict(journal: RemoteOpJournal) -> dict[str, JsonValue]:
    """把 journal 视图序列化为字典。

    Args:
        journal: journal 视图。

    Returns:
        可 JSON 序列化的字典。

    Raises:
        无。
    """

    return {
        "operation_id": journal.operation_id,
        "ticker": journal.ticker,
        "created_at": journal.created_at,
        "owner_pid": journal.owner_pid,
        "phase": journal.phase,
        "targets": [
            {
                "action": _ACTION_PUBLISH,
                "final_key": target.final_key,
                "staging_key": target.staging_key,
                "sha256": target.sha256,
                "size": target.size,
                "content_type": target.content_type,
                "metadata": dict(target.metadata),
                "publish_state": target.publish_state,
            }
            for target in journal.publish_targets
        ]
        + [
            {
                "action": _ACTION_DELETE,
                "final_key": target.final_key,
                "expected_sha256": target.expected_sha256,
                "expected_size": target.expected_size,
                "delete_state": target.delete_state,
            }
            for target in journal.delete_targets
        ],
    }


def _journal_from_dict(
    payload: dict[str, JsonValue],
    *,
    expected_operation_id: str,
) -> RemoteOpJournal:
    """从字典严格构建 journal 视图（任一非法字段即整体 fail closed）。

    Args:
        payload: 已解析的字典。
        expected_operation_id: 期望的 operation id（journal 文件名身份）；
            payload 的 ``operation_id`` 必须精确等于该值，且每个 publish
            target 的 ``staging_key`` 必须属于该 operation 的 staging
            命名空间，否则视为损坏 journal（S14-RR-01）。

    Returns:
        journal 视图。

    Raises:
        RemoteOpJournalError: 顶层字段类型、operation_id 身份、phase、
            action、per-target state/key/digest/size、target 唯一性或
            staging 命名空间任一非法时抛出。
    """

    operation_id = _require_nonempty_text(payload, "operation_id")
    if operation_id != expected_operation_id:
        # journal 文件名与 payload 的 operation id 是同一 batch 的双重身份；
        # 不一致即结构性损坏，必须在任何远端/FS 副作用前 fail closed。
        raise RemoteOpJournalError(
            "remote journal operation_id 与文件名不一致: "
            f"file={expected_operation_id} body={operation_id}"
        )
    ticker = _require_nonempty_text(payload, "ticker")
    created_at = _require_nonempty_text(payload, "created_at")
    owner_pid = _require_nonempty_text(payload, "owner_pid")
    phase = payload.get("phase")
    targets = payload.get("targets")
    if not isinstance(phase, str) or phase not in _VALID_PHASES:
        raise RemoteOpJournalError(f"remote journal phase 非法: {phase!r}")
    if not isinstance(targets, list):
        raise RemoteOpJournalError("remote journal targets 必须为 list")
    staging_namespace = f"{_STAGING_NAMESPACE_PREFIX}{operation_id}/"
    publish_targets: list[RemotePublishTarget] = []
    delete_targets: list[RemoteDeleteTarget] = []
    publish_keys: set[str] = set()
    delete_keys: set[str] = set()
    for item in targets:
        if not isinstance(item, dict):
            raise RemoteOpJournalError("remote journal target 必须为字典")
        action = item.get("action")
        if action not in _VALID_ACTIONS:
            raise RemoteOpJournalError(f"remote journal target action 非法: {action!r}")
        if action == _ACTION_PUBLISH:
            parsed = _parse_publish_target(item)
            if not parsed.staging_key.startswith(staging_namespace):
                raise RemoteOpJournalError(
                    "remote journal publish staging_key 命名空间不属于本 "
                    f"operation: operation={operation_id} key={parsed.staging_key}"
                )
            if parsed.final_key in publish_keys:
                raise RemoteOpJournalError(f"remote journal publish final_key 重复: {parsed.final_key}")
            publish_keys.add(parsed.final_key)
            publish_targets.append(parsed)
        else:
            parsed = _parse_delete_target(item)
            if parsed.final_key in delete_keys:
                raise RemoteOpJournalError(f"remote journal delete final_key 重复: {parsed.final_key}")
            delete_keys.add(parsed.final_key)
            delete_targets.append(parsed)
    return RemoteOpJournal(
        operation_id=operation_id,
        ticker=ticker,
        created_at=created_at,
        owner_pid=owner_pid,
        phase=phase,
        publish_targets=publish_targets,
        delete_targets=delete_targets,
    )


def _require_nonempty_text(payload: dict[str, JsonValue], key: str) -> str:
    """读取必填非空字符串字段，非法时抛 fail-closed 错误。

    Args:
        payload: 已解析的字典。
        key: 字段名。

    Returns:
        非空字符串。

    Raises:
        RemoteOpJournalError: 字段缺失、非字符串或为空时抛出。
    """

    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RemoteOpJournalError(f"remote journal 缺少 {key}")
    return value


def _parse_publish_target(item: dict[str, JsonValue]) -> RemotePublishTarget:
    """严格解析单个 publish target 字典。

    Args:
        item: target 字典。

    Returns:
        publish target。

    Raises:
        RemoteOpJournalError: 任一字段类型或取值非法时抛出。
    """

    final_key = _require_nonempty_text(item, "final_key")
    staging_key = _require_nonempty_text(item, "staging_key")
    sha256 = item.get("sha256")
    size = item.get("size")
    if not isinstance(sha256, str) or _SHA256_PATTERN.fullmatch(sha256) is None:
        raise RemoteOpJournalError("remote journal publish sha256 非法")
    if not isinstance(size, int) or size < 0:
        raise RemoteOpJournalError("remote journal publish size 非法")
    content_type = item.get("content_type")
    if content_type is not None and not isinstance(content_type, str):
        raise RemoteOpJournalError("remote journal publish content_type 非法")
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        raise RemoteOpJournalError("remote journal publish metadata 必须为字典")
    normalized_metadata: dict[str, str] = {}
    for metadata_key, metadata_value in metadata.items():
        if not isinstance(metadata_key, str) or not isinstance(metadata_value, str):
            raise RemoteOpJournalError("remote journal publish metadata 键值必须为 string")
        normalized_metadata[metadata_key] = metadata_value
    publish_state = item.get("publish_state")
    if not isinstance(publish_state, str) or publish_state not in _VALID_PUBLISH_STATES:
        raise RemoteOpJournalError(f"remote journal publish_state 非法: {publish_state!r}")
    return RemotePublishTarget(
        final_key=final_key,
        staging_key=staging_key,
        sha256=sha256,
        size=size,
        content_type=content_type,
        metadata=normalized_metadata,
        publish_state=publish_state,
    )


def _parse_delete_target(item: dict[str, JsonValue]) -> RemoteDeleteTarget:
    """严格解析单个 delete target 字典。

    Args:
        item: target 字典。

    Returns:
        delete target。

    Raises:
        RemoteOpJournalError: 任一字段类型或取值非法时抛出。
    """

    final_key = _require_nonempty_text(item, "final_key")
    expected_sha256 = item.get("expected_sha256")
    expected_size = item.get("expected_size")
    # expected_sha256 允许为空串：head 时远端已缺失/不可达记录为空期望，
    # 该意图必须可读回（commit/recovery 依此 fail closed，S14-CTRL-13）；
    # 非空时必须为合法 digest。
    if not isinstance(expected_sha256, str):
        raise RemoteOpJournalError("remote journal delete expected_sha256 非法")
    if expected_sha256 and _SHA256_PATTERN.fullmatch(expected_sha256) is None:
        raise RemoteOpJournalError("remote journal delete expected_sha256 非法")
    if not isinstance(expected_size, int) or expected_size < 0:
        raise RemoteOpJournalError("remote journal delete expected_size 非法")
    delete_state = item.get("delete_state")
    if not isinstance(delete_state, str) or delete_state not in _VALID_DELETE_STATES:
        raise RemoteOpJournalError(f"remote journal delete_state 非法: {delete_state!r}")
    return RemoteDeleteTarget(
        final_key=final_key,
        expected_sha256=expected_sha256,
        expected_size=expected_size,
        delete_state=delete_state,
    )


def _write_json_atomic(path: Path, payload: dict[str, JsonValue]) -> None:
    """模块私有原子 JSON 写入（same-dir temp + flush + fsync + replace）。

    Args:
        path: 目标路径。
        payload: 可序列化对象。

    Returns:
        无。

    Raises:
        OSError: 写入或同步失败时抛出。
        TypeError: 对象不可序列化时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temp_path.open("w", encoding="utf-8") as stream:
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())
    temp_path.replace(path)
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    """将目录元数据刷新到磁盘（尽力而为）。

    Args:
        path: 目录路径。

    Returns:
        无。

    Raises:
        无。
    """

    try:
        directory_fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    except OSError:
        return
    finally:
        os.close(directory_fd)
