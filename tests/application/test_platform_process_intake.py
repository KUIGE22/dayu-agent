"""平台进程入口 epoch 闸门的单元测试。"""

from __future__ import annotations

from dataclasses import fields

import pytest

from dayu.host.process_intake import IntakeEpoch, ProcessIntakeGate


@pytest.mark.unit
def test_process_intake_gate_closes_once_and_invalidates_inflight_epoch() -> None:
    """首次 stop 关闭闸门并让已派发工作失去启动资格。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    dispatched = gate.capture()
    assert gate.is_open is True
    assert gate.is_current(dispatched) is True

    gate.request_stop()

    assert gate.is_open is False
    assert gate.is_current(dispatched) is False
    stopped = gate.capture()
    assert stopped == IntakeEpoch(value=1)
    assert gate.is_current(stopped) is True


@pytest.mark.unit
def test_repeated_stop_request_never_reopens_or_advances_epoch_twice() -> None:
    """重复 soft stop 保持幂等且不存在 reopen seam。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gate.request_stop()
    first_stopped_epoch = gate.capture()

    gate.request_stop()
    gate.request_stop()

    assert gate.is_open is False
    assert gate.capture() == first_stopped_epoch
    assert gate.capture() == IntakeEpoch(value=1)


@pytest.mark.unit
@pytest.mark.parametrize("value", (True, False, -1))
def test_intake_epoch_rejects_bool_and_negative_values(value: int) -> None:
    """epoch 拒绝 bool-int 与负数。

    Args:
        value: 非法 epoch 值。

    Returns:
        无。

    Raises:
        无。
    """

    expected_error = TypeError if type(value) is bool else ValueError
    with pytest.raises(expected_error):
        IntakeEpoch(value=value)


@pytest.mark.unit
def test_process_intake_public_contract_is_exact_and_fail_closed() -> None:
    """公开 DTO 字段与 gate 方法保持 accepted closed surface。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    assert tuple(field.name for field in fields(IntakeEpoch)) == ("value",)
    public_names = {
        name
        for name in ProcessIntakeGate.__dict__
        if not name.startswith("_")
    }
    assert public_names == {"capture", "request_stop", "is_current", "is_open"}
