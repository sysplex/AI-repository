"""M0-T06 可替换时钟测试。

# NYSE 官方来源: https://www.nyse.com/markets/hours-calendars
# 核对日期: 2026-11-11
# 说明: 时钟只依赖带时区的 UTC datetime；交易日历数据见 test_calendar.py 头部注释。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.clock import (
    Clock,
    FrozenClock,
    SystemClock,
    get_clock,
    reset_clock,
    set_clock,
)

FROZEN = datetime(2026, 11, 11, 14, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _reset_clock() -> object:
    reset_clock()
    yield
    reset_clock()


def test_system_clock_returns_utc_aware_now() -> None:
    now = SystemClock().now()
    assert now.tzinfo is UTC
    assert now.utcoffset() == timedelta(0)
    assert abs((datetime.now(UTC) - now).total_seconds()) < 5


def test_frozen_clock_now_is_fixed() -> None:
    clock = FrozenClock(FROZEN)
    assert clock.now() == FROZEN
    assert clock.now() == FROZEN
    assert clock.now().tzinfo is UTC
    assert clock.now().utcoffset() == timedelta(0)


def test_frozen_clock_set_and_advance() -> None:
    clock = FrozenClock(FROZEN)
    clock.advance(timedelta(minutes=90))
    assert clock.now() == datetime(2026, 11, 11, 16, 0, tzinfo=UTC)

    clock.advance(timedelta(days=-1))
    assert clock.now() == datetime(2026, 11, 10, 16, 0, tzinfo=UTC)

    clock.set(datetime(2025, 1, 2, 3, 4, tzinfo=UTC))
    assert clock.now() == datetime(2025, 1, 2, 3, 4, tzinfo=UTC)


def test_frozen_clock_normalizes_offsets_to_utc() -> None:
    from datetime import timezone

    plus_two = timezone(timedelta(hours=2))
    clock = FrozenClock(datetime(2026, 11, 11, 16, 30, tzinfo=plus_two))
    assert clock.now() == FROZEN
    assert clock.now().tzinfo is UTC


@pytest.mark.parametrize("factory", [FrozenClock, lambda value: SystemClock()])
def test_clock_protocol_is_satisfied(factory: object) -> None:
    from collections.abc import Callable
    from typing import cast

    instance = cast(Callable[[datetime], Clock], factory)(FROZEN)
    assert isinstance(instance, Clock)
    assert instance.now().utcoffset() == timedelta(0)


def test_get_set_reset_clock() -> None:
    assert isinstance(get_clock(), SystemClock)
    frozen = FrozenClock(FROZEN)
    set_clock(frozen)
    assert get_clock() is frozen
    assert get_clock().now() == FROZEN
    reset_clock()
    assert isinstance(get_clock(), SystemClock)
    assert get_clock() is not frozen


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="时区"):
        FrozenClock(datetime(2026, 11, 11, 14, 30))
    clock = FrozenClock(FROZEN)
    with pytest.raises(ValueError, match="时区"):
        clock.set(datetime(2026, 11, 12, 0, 0))
