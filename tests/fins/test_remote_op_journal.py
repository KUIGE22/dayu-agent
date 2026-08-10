"""remote-op journal 单元测试（S14-CTRL-04 状态机/原子写/严格 fail-closed）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

from dayu.fins.storage.remote_op_journal import (
    RemoteDeleteTarget,
    RemoteOpJournal,
    RemoteOpJournalError,
    RemotePublishTarget,
    journal_path,
    list_journal_ids,
    read_journal,
    remove_journal,
    write_journal,
)


def _journal(operation_id: str = "op1") -> RemoteOpJournal:
    """构造测试 journal。"""

    return RemoteOpJournal(
        operation_id=operation_id,
        ticker="AAPL",
        created_at="2026-08-11T00:00:00+00:00",
        owner_pid="123",
        phase="staged",
        publish_targets=[
            RemotePublishTarget(
                final_key="AAPL/filings/fil_1/a.pdf",
                staging_key=".dayu-staging/op1/aaaa",
                sha256="a" * 64,
                size=10,
                content_type="application/pdf",
                metadata={"source": "original"},
                publish_state="staged",
            )
        ],
        delete_targets=[
            RemoteDeleteTarget(
                final_key="AAPL/filings/old/old.pdf",
                expected_sha256="b" * 64,
                expected_size=20,
                delete_state="pending",
            )
        ],
    )


def test_write_read_roundtrip(tmp_path: Path) -> None:
    """写入后读回逐字段一致。"""

    dayu_root = tmp_path / ".dayu"
    journal = _journal()
    write_journal(dayu_root, journal)

    loaded = read_journal(dayu_root, "op1")
    assert loaded is not None
    assert loaded.operation_id == "op1"
    assert loaded.ticker == "AAPL"
    assert loaded.phase == "staged"
    assert len(loaded.publish_targets) == 1
    assert loaded.publish_targets[0].final_key == "AAPL/filings/fil_1/a.pdf"
    assert loaded.publish_targets[0].publish_state == "staged"
    assert loaded.delete_targets[0].final_key == "AAPL/filings/old/old.pdf"
    assert loaded.delete_targets[0].delete_state == "pending"


def test_journal_path_shape(tmp_path: Path) -> None:
    """journal 路径为 remote_ops/{operation_id}.json。"""

    assert journal_path(tmp_path, "op1") == tmp_path / "remote_ops" / "op1.json"


def test_read_missing_returns_none(tmp_path: Path) -> None:
    """缺失 journal 返回 None。"""

    assert read_journal(tmp_path, "nope") is None


def test_list_journal_ids(tmp_path: Path) -> None:
    """list_journal_ids 返回排序 id。"""

    write_journal(tmp_path, _journal("b2"))
    write_journal(tmp_path, _journal("a1"))
    assert list_journal_ids(tmp_path) == ["a1", "b2"]


def test_remove_journal(tmp_path: Path) -> None:
    """remove_journal 幂等移除。"""

    write_journal(tmp_path, _journal("op1"))
    remove_journal(tmp_path, "op1")
    assert list_journal_ids(tmp_path) == []
    remove_journal(tmp_path, "op1")


def test_atomic_write_no_partial_on_crash(tmp_path: Path) -> None:
    """写入是原子 replace：无残留 temp 文件。"""

    dayu_root = tmp_path / ".dayu"
    write_journal(dayu_root, _journal("op1"))
    leftovers = [
        path.name
        for path in (dayu_root / "remote_ops").iterdir()
        if path.name.endswith(".tmp")
    ]
    assert leftovers == []


def test_read_invalid_json_fails_closed(tmp_path: Path) -> None:
    """存在但 JSON 非法的 journal 稳定抛 RemoteOpJournalError（fail closed）。

    journal 是 recovery 唯一真源：存在但损坏必须与“真正缺失”分离，绝不
    归一成 ``None`` 后被 FS orphan cleanup 丢弃（S14-CR-04）。
    """

    path = journal_path(tmp_path, "bad")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(RemoteOpJournalError, match="无法解析"):
        read_journal(tmp_path, "bad")


def test_serialized_keys_exact(tmp_path: Path) -> None:
    """序列化键集合精确（顶层 phase 与 per-target state 独立）。"""

    dayu_root = tmp_path / ".dayu"
    write_journal(dayu_root, _journal("op1"))
    raw = json.loads((dayu_root / "remote_ops" / "op1.json").read_text(encoding="utf-8"))
    assert set(raw) == {"operation_id", "ticker", "created_at", "owner_pid", "phase", "targets"}
    publish = next(item for item in raw["targets"] if item["action"] == "publish")
    assert set(publish) == {
        "action",
        "final_key",
        "staging_key",
        "sha256",
        "size",
        "content_type",
        "metadata",
        "publish_state",
    }
    delete = next(item for item in raw["targets"] if item["action"] == "delete")
    assert set(delete) == {
        "action",
        "final_key",
        "expected_sha256",
        "expected_size",
        "delete_state",
    }


def _write_then_assert_rejected(tmp_path: Path, mutate: Callable[..., None]) -> None:
    """写合法 journal -> 改写为非法 -> 断言 read_journal fail closed。

    Args:
        tmp_path: 测试临时目录。
        mutate: 对原始 payload（``json.loads`` 返回值）的改写回调。

    Returns:
        无。

    Raises:
        RemoteOpJournalError: read_journal 稳定抛出（测试通过条件）。
    """

    path = journal_path(tmp_path, "op1")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_journal(tmp_path, _journal("op1"))
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutate(raw)
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RemoteOpJournalError):
        read_journal(tmp_path, "op1")


def test_read_top_level_non_dict_fails_closed(tmp_path: Path) -> None:
    """顶层非字典的 journal 稳定抛 RemoteOpJournalError。"""

    path = journal_path(tmp_path, "bad")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(RemoteOpJournalError, match="顶层必须为字典"):
        read_journal(tmp_path, "bad")


def test_unknown_phase_fails_closed(tmp_path: Path) -> None:
    """未知 phase 的 journal 稳定 fail closed。"""

    _write_then_assert_rejected(tmp_path, lambda raw: raw.update({"phase": "not-a-phase"}))


def test_unknown_target_action_fails_closed(tmp_path: Path) -> None:
    """未知 target action 的 journal 稳定 fail closed（不再被静默跳过）。"""

    _write_then_assert_rejected(tmp_path, lambda raw: raw["targets"][0].update({"action": "explode"}))


def test_unknown_publish_state_fails_closed(tmp_path: Path) -> None:
    """未知 publish_state 的 journal 稳定 fail closed。"""

    _write_then_assert_rejected(
        tmp_path, lambda raw: raw["targets"][0].update({"publish_state": "half_verified"})
    )


def test_unknown_delete_state_fails_closed(tmp_path: Path) -> None:
    """未知 delete_state 的 journal 稳定 fail closed。"""

    _write_then_assert_rejected(
        tmp_path, lambda raw: raw["targets"][1].update({"delete_state": "half_deleted"})
    )


def test_bad_publish_sha_fails_closed(tmp_path: Path) -> None:
    """publish sha256 非 64 位 hex 的 journal 稳定 fail closed。"""

    _write_then_assert_rejected(tmp_path, lambda raw: raw["targets"][0].update({"sha256": "short"}))


def test_negative_publish_size_fails_closed(tmp_path: Path) -> None:
    """publish size 为负数的 journal 稳定 fail closed。"""

    _write_then_assert_rejected(tmp_path, lambda raw: raw["targets"][0].update({"size": -1}))


def test_missing_operation_id_fails_closed(tmp_path: Path) -> None:
    """顶层缺 operation_id 的 journal 稳定 fail closed。"""

    _write_then_assert_rejected(tmp_path, lambda raw: raw.pop("operation_id"))


def test_operation_id_mismatch_fails_closed(tmp_path: Path) -> None:
    """payload operation_id 与文件名身份不一致的 journal 稳定 fail closed（S14-RR-01）。

    合法格式但 ``operation_id`` 被损坏为另一非空值时，必须作为结构性损坏
    处理：绝不允许 recovery 先按 payload publish 再因 token 目录缺失才失败。
    """

    _write_then_assert_rejected(
        tmp_path, lambda raw: raw.update({"operation_id": "other-valid-operation-id"})
    )


def test_staging_key_namespace_mismatch_fails_closed(tmp_path: Path) -> None:
    """publish staging_key 命名空间不属于本 operation 的 journal 稳定 fail closed。

    staging key 必须属于 ``.dayu-staging/{operation_id}/`` 命名空间；引用其它
    operation 的 staging 命名空间视为结构性损坏（S14-RR-01）。
    """

    _write_then_assert_rejected(
        tmp_path,
        lambda raw: raw["targets"][0].update(
            {"staging_key": ".dayu-staging/other-valid-operation-id/aaaa"}
        ),
    )


def test_empty_ticker_fails_closed(tmp_path: Path) -> None:
    """顶层 ticker 为空的 journal 稳定 fail closed。"""

    _write_then_assert_rejected(tmp_path, lambda raw: raw.update({"ticker": ""}))


def test_duplicate_publish_key_fails_closed(tmp_path: Path) -> None:
    """同一 operation 内重复 publish final_key 的 journal 稳定 fail closed。"""

    _write_then_assert_rejected(tmp_path, lambda raw: raw["targets"].append(dict(raw["targets"][0])))


def test_duplicate_delete_key_fails_closed(tmp_path: Path) -> None:
    """同一 operation 内重复 delete final_key 的 journal 稳定 fail closed。"""

    _write_then_assert_rejected(tmp_path, lambda raw: raw["targets"].append(dict(raw["targets"][1])))


def test_metadata_non_string_value_fails_closed(tmp_path: Path) -> None:
    """publish metadata 含非字符串值（不再静默丢弃）的 journal fail closed。"""

    _write_then_assert_rejected(
        tmp_path, lambda raw: raw["targets"][0].update({"metadata": {"source": 123}})
    )


def test_missing_journal_still_returns_none(tmp_path: Path) -> None:
    """真正缺失的 journal 仍返回 None（无回归，S14-CR-04 分离语义）。"""

    assert read_journal(tmp_path, "definitely-missing") is None
