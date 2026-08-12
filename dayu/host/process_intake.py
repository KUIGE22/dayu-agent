"""平台 Worker/Scheduler 共用的进程入口 epoch 闸门。

本模块只保存 event-loop-owned 的进程内状态，不 import Service、storage、
Redis 或业务模块。阻塞调用派发前取得 ``IntakeEpoch``；调用返回后，调用方
必须同时验证 ``is_open`` 与 ``is_current(epoch)``，才可启动下一项工作。
首次停止请求永久关闭闸门并推进一次 epoch，重复请求保持幂等。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IntakeEpoch:
    """一次入口许可快照。

    Args:
        value: 非负、exact ``int`` 的进程内 epoch。
    """

    value: int

    def __post_init__(self) -> None:
        """校验 epoch scalar。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ``value`` 不是 exact ``int`` 时抛出。
            ValueError: ``value`` 为负数时抛出。
        """

        if type(self.value) is not int:
            raise TypeError("intake epoch 必须是 exact int")
        if self.value < 0:
            raise ValueError("intake epoch 不得为负数")


class ProcessIntakeGate:
    """event-loop-owned、关闭后不可重开的入口闸门。"""

    def __init__(self) -> None:
        """构造初始开放的 epoch 0 闸门。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._epoch = 0
        self._is_open = True

    @property
    def is_open(self) -> bool:
        """返回闸门是否仍接受新工作。

        Args:
            无。

        Returns:
            闸门开放时为 ``True``。

        Raises:
            无。
        """

        return self._is_open

    def capture(self) -> IntakeEpoch:
        """捕获当前入口 epoch。

        Args:
            无。

        Returns:
            当前 immutable ``IntakeEpoch``。

        Raises:
            无。
        """

        return IntakeEpoch(self._epoch)

    def request_stop(self) -> None:
        """首次调用永久关闭闸门并推进一次 epoch。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        if not self._is_open:
            return
        self._is_open = False
        self._epoch += 1

    def is_current(self, epoch: IntakeEpoch) -> bool:
        """检查快照是否仍对应当前 epoch。

        Args:
            epoch: 派发阻塞调用前捕获的 epoch。

        Returns:
            参数是 ``IntakeEpoch`` 且值仍等于当前 epoch 时为 ``True``；
            错误类型或过期快照均 fail closed 为 ``False``。

        Raises:
            无。
        """

        return type(epoch) is IntakeEpoch and epoch.value == self._epoch


__all__ = ["IntakeEpoch", "ProcessIntakeGate"]
