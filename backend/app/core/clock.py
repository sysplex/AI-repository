"""可替换时钟（M0 / T06），`CONTRACTS.md §7`。

业务代码只通过 `get_clock().now()` 取当前时间；测试用 `FrozenClock` +
`set_clock` 冻结，`reset_clock` 恢复系统时钟。所有 now() 均为 UTC aware。
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

NEGATIVE_PROBE: int = "not-an-int"

__all__ = [
    "Clock",
    "FrozenClock",
    "SystemClock",
    "get_clock",
    "reset_clock",
    "set_clock",
]


@runtime_checkable
class Clock(Protocol):
    """时钟协议；now() 返回带 UTC 时区的 datetime。"""

    def now(self) -> datetime: ...


class SystemClock:
    """系统真实时钟。"""

    def now(self) -> datetime:
        """当前 UTC 时间。"""
        return datetime.now(UTC)


class FrozenClock:
    """测试用冻结时钟；set 与 advance 可模拟时间流逝。"""

    def __init__(self, at: datetime) -> None:
        self._at = _as_utc(at)

    def set(self, at: datetime) -> None:
        """把时钟重设为指定时刻。"""
        self._at = _as_utc(at)

    def advance(self, delta: timedelta) -> None:
        """把时钟向前（或向后）推进一段时间。"""
        self._at = self._at + delta

    def now(self) -> datetime:
        """返回冻结时刻，恒为 UTC aware。"""
        return self._at


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime 必须带时区")
    return value.astimezone(UTC)


_clock: Clock = SystemClock()


def get_clock() -> Clock:
    """返回当前进程时钟。"""
    return _clock


def set_clock(clock: Clock) -> None:
    """替换进程时钟（供测试注入 FrozenClock）。"""
    global _clock
    _clock = clock


def reset_clock() -> None:
    """恢复 SystemClock。"""
    global _clock
    _clock = SystemClock()
