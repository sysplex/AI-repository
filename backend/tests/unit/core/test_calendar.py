"""M0-T06 NYSE 交易日历测试。

# NYSE 官方来源: https://www.nyse.com/markets/hours-calendars
# NYSE 官方来源（2026–2028 表）: https://www.nyse.com/trade/hours-calendars
# NYSE 官方来源（2024 节假日与提前收盘公告）: https://ir.theice.com/press/news-details/2021/NYSE-Group-Announces-2022-2023-and-2024-Holiday-and-Early-Closings-Calendar/default.aspx
# NYSE 官方来源（2026 节假日与提前收盘公告转载）: https://www.nasdaq.com/press-release/nyse-group-announces-2024-2025-and-2026-holiday-and-early-closings-calendar-2023-11
# NYSE 官方来源（2024 年度日历 PDF）: https://www.nyse.com/publicdocs/ICE_NYSE_2024_Yearly_Trading_Calendar.pdf
# NYSE 官方来源（2025-01-09 全国哀悼日临时休市公告）: https://ir.theice.com/press/news-details/2024/The-New-York-Stock-Exchange-Will-Close-Markets-on-January-9-to-Honor-the-Passing-of-Former-President-Jimmy-Carter-on-National-Day-of-Mourning/default.aspx
# NYSE 官方来源（同日监管备忘录 PDF）: https://www.nyse.com/publicdocs/nyse/markets/arca-options/rule-interpretations/2025/National_Day_of_Mourning_20250102.pdf
# 核对日期: 2026-11-11
# 交叉验证: exchange_calendars 4.13.2 的 XNYS(start=2020-01-01, end=2030-12-31)
#           与上述官方公告逐年逐日比对，三年休市日与半日市全部一致；
#           官方年度节假日表未列的 2025-01-09（卡特总统全国哀悼日临时休市）
#           依据 ICE/NYSE 2024-12-30 公告补入，XNYS 日历亦已收录。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.calendar import (
    ET,
    MAX_DATE,
    MIN_DATE,
    CalendarRangeError,
    NotATradingDay,
    get_session,
    is_market_open,
    is_trading_day,
    next_trading_day,
    previous_trading_day,
    to_et,
    to_utc,
    trading_days_between,
)

# 休市日（全日 Market Closed），来自官方公告，禁止照抄任务卡参考值。
CLOSED_2024 = (
    "2024-01-01",
    "2024-01-15",
    "2024-02-19",
    "2024-03-29",
    "2024-05-27",
    "2024-06-19",
    "2024-07-04",
    "2024-09-02",
    "2024-11-28",
    "2024-12-25",
)
CLOSED_2025 = (
    "2025-01-01",
    "2025-01-09",
    "2025-01-20",
    "2025-02-17",
    "2025-04-18",
    "2025-05-26",
    "2025-06-19",
    "2025-07-04",
    "2025-09-01",
    "2025-11-27",
    "2025-12-25",
)
CLOSED_2026 = (
    "2026-01-01",
    "2026-01-19",
    "2026-02-16",
    "2026-04-03",
    "2026-05-25",
    "2026-06-19",
    "2026-07-03",
    "2026-09-07",
    "2026-11-26",
    "2026-12-25",
)
ALL_CLOSED = CLOSED_2024 + CLOSED_2025 + CLOSED_2026

# 提前收盘日（13:00 ET），来自同一批官方公告的脚注。
HALF_DAY_2024 = ("2024-07-03", "2024-11-29", "2024-12-24")
HALF_DAY_2025 = ("2025-07-03", "2025-11-28", "2025-12-24")
HALF_DAY_2026 = ("2026-11-27", "2026-12-24")
ALL_HALF_DAYS = HALF_DAY_2024 + HALF_DAY_2025 + HALF_DAY_2026


@pytest.mark.parametrize("day", ALL_CLOSED)
def test_official_holidays_are_not_trading_days(day: str) -> None:
    assert is_trading_day(date.fromisoformat(day)) is False


@pytest.mark.parametrize("day", ALL_HALF_DAYS)
def test_official_early_closes_are_half_days(day: str) -> None:
    session = get_session(date.fromisoformat(day))
    assert session.is_half_day is True
    assert session.close_at.hour == 13
    assert session.close_at.minute == 0
    assert session.close_at.tzinfo is ET
    assert to_utc(session.close_at).hour in (17, 18)


@pytest.mark.parametrize(
    "day",
    ["2024-07-02", "2025-03-14", "2026-03-06", "2026-03-09", "2026-07-02"],
)
def test_normal_sessions_close_at_16_et(day: str) -> None:
    session = get_session(date.fromisoformat(day))
    assert session.is_half_day is False
    assert session.open_at.hour == 9
    assert session.open_at.minute == 30
    assert session.close_at == datetime.combine(date.fromisoformat(day), time(16, 0), tzinfo=ET)
    assert session.open_at.tzinfo is ET
    assert session.trade_date == date.fromisoformat(day)


def test_weekends_are_never_trading_days() -> None:
    for day in ("2026-11-07", "2026-11-08", "2024-06-15", "2024-06-16"):
        assert is_trading_day(date.fromisoformat(day)) is False


def test_next_trading_day_skips_holiday_and_weekend() -> None:
    assert next_trading_day(date(2026, 7, 2)) == date(2026, 7, 6)
    assert next_trading_day(date(2026, 11, 6)) == date(2026, 11, 9)
    assert next_trading_day(date(2025, 1, 8)) == date(2025, 1, 10)
    assert next_trading_day(date(2026, 11, 26)) == date(2026, 11, 27)


def test_previous_trading_day_skips_holiday_and_weekend() -> None:
    assert previous_trading_day(date(2026, 7, 6)) == date(2026, 7, 2)
    assert previous_trading_day(date(2025, 1, 10)) == date(2025, 1, 8)
    assert previous_trading_day(date(2026, 1, 1)) == date(2025, 12, 31)


@settings(max_examples=60, deadline=None)
@given(st.dates(min_value=date(2021, 1, 4), max_value=date(2029, 12, 28)))
def test_previous_of_next_is_not_after_original(value: date) -> None:
    following = next_trading_day(value)
    preceding = previous_trading_day(following)
    assert preceding <= value
    assert following > value
    assert is_trading_day(following) is True
    assert is_trading_day(preceding) is True


@pytest.mark.parametrize("day", ["2026-01-01", "2026-11-26", "2026-11-07", "2025-01-09"])
def test_get_session_raises_for_non_trading_day(day: str) -> None:
    with pytest.raises(NotATradingDay):
        get_session(date.fromisoformat(day))


def test_utc_offset_changes_after_dst_switch() -> None:
    # 2026-03-08 夏令时开始；3/6 周五 EST(-5) → 21:00Z，3/9 周一 EDT(-4) → 20:00Z
    assert to_utc(get_session(date(2026, 3, 6)).close_at).hour == 21
    assert to_utc(get_session(date(2026, 3, 9)).close_at).hour == 20
    # 半日市 13:00 ET：EDT → 17:00Z，EST → 18:00Z
    assert to_utc(get_session(date(2025, 7, 3)).close_at).hour == 17
    assert to_utc(get_session(date(2026, 11, 27)).close_at).hour == 18
    assert to_utc(get_session(date(2026, 3, 9)).open_at).hour == 13


def test_dst_switch_dates_2026() -> None:
    # 2026-03-08 开始 EDT；2026-11-01 结束回到 EST
    before = to_utc(datetime(2026, 3, 6, 16, 0, tzinfo=ET)).hour
    after = to_utc(datetime(2026, 3, 9, 16, 0, tzinfo=ET)).hour
    assert (before, after) == (21, 20)
    assert to_utc(datetime(2026, 7, 1, 16, 0, tzinfo=ET)).hour == 20
    assert to_utc(datetime(2026, 12, 1, 16, 0, tzinfo=ET)).hour == 21


def test_is_market_open_boundaries() -> None:
    day = date(2026, 3, 9)
    open_at = datetime.combine(day, time(9, 30), tzinfo=ET)
    close_at = datetime.combine(day, time(16, 0), tzinfo=ET)
    assert is_market_open(open_at - timedelta(seconds=1)) is False
    assert is_market_open(open_at) is True
    assert is_market_open(close_at - timedelta(seconds=1)) is True
    assert is_market_open(close_at) is False
    assert is_market_open(datetime.combine(day, time(17, 0), tzinfo=UTC)) is True

    half = date(2026, 11, 27)
    half_close = datetime.combine(half, time(13, 0), tzinfo=ET)
    assert is_market_open(half_close - timedelta(seconds=1)) is True
    assert is_market_open(half_close) is False
    assert is_market_open(datetime.combine(half, time(15, 0), tzinfo=ET)) is False

    assert is_market_open(datetime.combine(date(2026, 11, 26), time(12, 0), tzinfo=ET)) is False
    assert is_market_open(datetime.combine(date(2026, 11, 28), time(12, 0), tzinfo=ET)) is False


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 3, 9, 12, 0),
        datetime(2026, 3, 9, 12, 0, tzinfo=None),
    ],
)
def test_naive_datetime_is_rejected(value: datetime) -> None:
    with pytest.raises(ValueError, match="时区"):
        is_market_open(value)
    with pytest.raises(ValueError, match="时区"):
        to_et(value)
    with pytest.raises(ValueError, match="时区"):
        to_utc(value)


def test_to_et_and_to_utc_roundtrip() -> None:
    instant = datetime(2026, 7, 1, 20, 0, tzinfo=UTC)
    local = to_et(instant)
    assert local.hour == 16
    assert local.tzinfo is ET
    assert to_utc(local) == instant


def test_trading_days_between_is_inclusive_and_sorted() -> None:
    days = trading_days_between(date(2026, 11, 23), date(2026, 11, 30))
    assert days == sorted(days)
    assert days == [
        date(2026, 11, 23),
        date(2026, 11, 24),
        date(2026, 11, 25),
        date(2026, 11, 27),
        date(2026, 11, 30),
    ]
    assert trading_days_between(date(2026, 11, 28), date(2026, 11, 29)) == []
    assert trading_days_between(date(2026, 3, 6), date(2026, 3, 6)) == [date(2026, 3, 6)]
    with pytest.raises(ValueError, match="start"):
        trading_days_between(date(2026, 3, 9), date(2026, 3, 6))


@pytest.mark.parametrize(
    "call",
    [
        lambda d: is_trading_day(d),
        lambda d: next_trading_day(d),
        lambda d: previous_trading_day(d),
        lambda d: get_session(d),
        lambda d: trading_days_between(d, d),
        lambda d: is_market_open(datetime.combine(d, time(12, 0), tzinfo=UTC)),
    ],
)
def test_out_of_range_dates_raise(call: object) -> None:
    from collections.abc import Callable
    from typing import cast

    for value in (date(2019, 12, 31), date(2031, 1, 2)):
        with pytest.raises(CalendarRangeError):
            cast(Callable[[date], object], call)(value)


def test_supported_range_constants() -> None:
    assert date(2020, 1, 1) == MIN_DATE
    assert date(2030, 12, 31) == MAX_DATE
    assert is_trading_day(MIN_DATE) is False  # 2020-01-01 元旦
    assert is_trading_day(MAX_DATE) is True  # 2030-12-31 周二


def test_calendar_is_thread_safe() -> None:
    from app.core import calendar as calendar_module

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: id(calendar_module._get_calendar()), range(32)))
        flags = list(pool.map(lambda _: is_trading_day(date(2026, 3, 9)), range(32)))
    assert len(set(results)) == 1
    assert all(flags)
    assert calendar_module._get_calendar() is calendar_module._get_calendar()


def test_only_calendar_module_references_exchange_calendars() -> None:
    app_dir = Path(__file__).resolve().parents[3] / "app"
    offenders = [
        path.relative_to(app_dir).as_posix()
        for path in app_dir.rglob("*.py")
        if "exchange_calendars" in path.read_text(encoding="utf-8") and path.name != "calendar.py"
    ]
    assert offenders == []


def test_calendar_boundary_conditions() -> None:
    with pytest.raises(CalendarRangeError):
        next_trading_day(MAX_DATE)
    with pytest.raises(CalendarRangeError):
        previous_trading_day(MIN_DATE)
    # 2020-01-01 早于 XNYS 的 first_session(2020-01-02)，闭区间内无交易日
    assert trading_days_between(MIN_DATE, MIN_DATE) == []


def test_no_sessions_defensive_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import calendar as calendar_module

    class _Bound:
        def __init__(self, value: date) -> None:
            self._value = value

        def date(self) -> date:
            return self._value

    class _EmptyCalendar:
        first_session = _Bound(date(2020, 1, 2))
        last_session = _Bound(date(2030, 12, 31))

        def sessions_in_range(self, start: str, end: str) -> list[object]:
            del start, end
            return []

    monkeypatch.setattr(calendar_module, "_get_calendar", lambda: _EmptyCalendar())
    with pytest.raises(CalendarRangeError, match="无交易日"):
        next_trading_day(date(2026, 3, 6))
    with pytest.raises(CalendarRangeError, match="无交易日"):
        previous_trading_day(date(2026, 3, 6))


def test_double_checked_lock_covers_second_waiter(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import calendar as calendar_module

    sentinel = object()

    class _FakeXcals:
        @staticmethod
        def get_calendar(*args: object, **kwargs: object) -> object:
            del args, kwargs
            return sentinel

    # patch 模块内绑定的名字（而非直接引用未导出的 xcals），保持 mypy --strict 通过
    monkeypatch.setattr(calendar_module, "xcals", _FakeXcals())
    monkeypatch.setattr(calendar_module, "_calendar", None)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: calendar_module._get_calendar(), range(24)))
    assert all(result is sentinel for result in results)
    monkeypatch.setattr(calendar_module, "_calendar", None)
