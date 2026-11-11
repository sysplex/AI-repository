"""NYSE 交易日历（M0 / T06），`CONTRACTS.md §7`。

本模块是**唯一**允许引用 `exchange_calendars` 的地方；业务代码只通过这里
判断交易日 / 开收盘时间。日历显式限定 2020-01-01 ~ 2030-12-31，越界抛
`CalendarRangeError`。时间统一使用带时区的 datetime：会话时间为
America/New_York，UTC 转换由 `to_utc` 完成。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals  # type: ignore[import-untyped]

__all__ = [
    "ET",
    "MAX_DATE",
    "MIN_DATE",
    "CalendarRangeError",
    "NotATradingDay",
    "Session",
    "get_session",
    "is_market_open",
    "is_trading_day",
    "next_trading_day",
    "previous_trading_day",
    "to_et",
    "to_utc",
    "trading_days_between",
]

ET: ZoneInfo = ZoneInfo("America/New_York")
UTC = UTC

MIN_DATE = date(2020, 1, 1)
MAX_DATE = date(2030, 12, 31)

_CALENDAR_START = "2020-01-01"
_CALENDAR_END = "2030-12-31"
_NORMAL_CLOSE_HOUR = 16


@dataclass(frozen=True)
class Session:
    """一个交易日的会话；open_at / close_at 均带 America/New_York 时区。"""

    trade_date: date
    open_at: datetime
    close_at: datetime
    is_half_day: bool


class NotATradingDay(ValueError):
    """get_session 收到非交易日。"""


class CalendarRangeError(ValueError):
    """日期超出 XNYS 日历支持范围 2020-01-01 ~ 2030-12-31。"""


_calendar: Any = None
_calendar_lock = threading.Lock()


def _get_calendar() -> Any:
    """进程内单例，双重检查锁保证线程安全；显式固定 XNYS 的起止范围。"""
    global _calendar
    if _calendar is None:
        with _calendar_lock:
            if _calendar is None:
                _calendar = xcals.get_calendar("XNYS", start=_CALENDAR_START, end=_CALENDAR_END)
    return _calendar


def _validate_date(value: date) -> None:
    if value < MIN_DATE or value > MAX_DATE:
        raise CalendarRangeError(
            f"{value.isoformat()} 超出日历范围 {MIN_DATE.isoformat()} ~ {MAX_DATE.isoformat()}"
        )


def _require_aware(value: datetime) -> None:
    """所有接受 datetime 的函数都拒绝不带时区的值（契约 §7 第 3 条）。"""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime 必须带时区")


def to_et(value: datetime) -> datetime:
    """把带时区的 datetime 转成 America/New_York。"""
    _require_aware(value)
    return value.astimezone(ET)


def to_utc(value: datetime) -> datetime:
    """把带时区的 datetime 转成 UTC。"""
    _require_aware(value)
    return value.astimezone(UTC)


def is_trading_day(value: date) -> bool:
    """是否为 XNYS 交易日（周末与节假日为 False）。

    XNYS 的 first_session 是 2020-01-02（元旦休市），因此 2020-01-01 属于
    契约允许的范围，但早于日历首个 session，需直接返回 False 而不是让
    exchange_calendars 抛 DateOutOfBounds。
    """
    _validate_date(value)
    calendar = _get_calendar()
    first: date = calendar.first_session.date()
    last: date = calendar.last_session.date()
    if value < first or value > last:
        return False
    return bool(calendar.is_session(value.isoformat()))


def _session_date(timestamp: Any) -> date:
    extracted: date = timestamp.date()
    _validate_date(extracted)
    return extracted


def next_trading_day(value: date) -> date:
    """严格晚于 value 的下一个交易日（value 本身可以不是交易日）。"""
    _validate_date(value)
    calendar = _get_calendar()
    start = value + timedelta(days=1)
    last: date = calendar.last_session.date()
    if start > last:
        raise CalendarRangeError(f"{value.isoformat()} 之后已超出日历范围")
    sessions = calendar.sessions_in_range(start.isoformat(), last.isoformat())
    for session in sessions:
        return _session_date(session)
    raise CalendarRangeError(f"{value.isoformat()} 之后已无交易日")


def previous_trading_day(value: date) -> date:
    """严格早于 value 的上一个交易日（value 本身可以不是交易日）。"""
    _validate_date(value)
    calendar = _get_calendar()
    end = value - timedelta(days=1)
    first: date = calendar.first_session.date()
    if end < first:
        raise CalendarRangeError(f"{value.isoformat()} 之前已超出日历范围")
    sessions = calendar.sessions_in_range(first.isoformat(), end.isoformat())
    for session in reversed(sessions):
        return _session_date(session)
    raise CalendarRangeError(f"{value.isoformat()} 之前已无交易日")


def get_session(value: date) -> Session:
    """返回某交易日的开收盘时间；非交易日抛 NotATradingDay。"""
    _validate_date(value)
    if not is_trading_day(value):
        raise NotATradingDay(f"{value.isoformat()} 不是 NYSE 交易日")

    label = value.isoformat()
    calendar = _get_calendar()
    open_et = calendar.session_open(label).tz_convert(ET)
    close_et = calendar.session_close(label).tz_convert(ET)
    is_half_day = close_et.hour < _NORMAL_CLOSE_HOUR
    return Session(
        trade_date=value,
        open_at=datetime.combine(value, time(open_et.hour, open_et.minute), tzinfo=ET),
        close_at=datetime.combine(value, time(close_et.hour, close_et.minute), tzinfo=ET),
        is_half_day=is_half_day,
    )


def trading_days_between(start: date, end: date) -> list[date]:
    """闭区间内的交易日，升序；无交易日返回空列表。"""
    _validate_date(start)
    _validate_date(end)
    if start > end:
        raise ValueError("start 不得晚于 end")
    calendar = _get_calendar()
    first: date = calendar.first_session.date()
    last: date = calendar.last_session.date()
    effective_start = max(start, first)
    effective_end = min(end, last)
    if effective_start > effective_end:
        return []
    sessions = calendar.sessions_in_range(effective_start.isoformat(), effective_end.isoformat())
    return [session.date() for session in sessions]


def is_market_open(at: datetime) -> bool:
    """at 是否落在常规交易时段（开盘含、收盘不含）。"""
    _require_aware(at)
    local = to_et(at)
    _validate_date(local.date())
    if not is_trading_day(local.date()):
        return False
    session = get_session(local.date())
    return session.open_at <= local < session.close_at
