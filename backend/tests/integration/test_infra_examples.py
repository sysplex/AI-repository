"""M0-T10 测试基座示例（兼作使用范例与验收证据）。

`db_session` 相关用例需要真实 Postgres；未设置 TEST_DATABASE_URL 且无 Docker 时
由 `db_engine` fixture 明确 skip，其余用例不依赖任何外部服务。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock, SystemClock, get_clock
from app.core.events import Event, get_event_bus
from app.core.redis import check_redis
from tests.fixtures.loader import load_fixture

_FROZEN = datetime(2026, 11, 11, 14, 30, tzinfo=UTC)
_MARKER = "t10_isolation_marker"
_MARKER_COMMIT = "t10_commit_marker"


async def _whoami() -> str:
    return "production"


class _Pinged(Event):
    label: str


def test_recorded_fixture_loader() -> None:
    assert load_fixture("m0/_smoke/healthz.json") == {"status": "ok"}
    with pytest.raises(ValueError, match="tests/fixtures"):
        load_fixture("../../etc/passwd")
    with pytest.raises(FileNotFoundError):
        load_fixture("m0/_smoke/not-there.json")


def test_frozen_clock_is_fixed(frozen_clock: FrozenClock) -> None:
    assert get_clock() is frozen_clock
    assert get_clock().now() == _FROZEN
    frozen_clock.advance(timedelta(minutes=5))
    assert get_clock().now() == _FROZEN + timedelta(minutes=5)


def test_system_clock_is_restored_after_frozen_clock() -> None:
    """上一个用例结束后 `frozen_clock` fixture 应已 reset_clock()。"""
    assert isinstance(get_clock(), SystemClock)


async def test_event_bus_fixture_is_clean(event_bus: Any) -> None:
    seen: list[str] = []

    async def handler(event: _Pinged) -> None:
        seen.append(event.label)

    event_bus.subscribe(_Pinged, handler)
    await event_bus.publish(_Pinged(label="first"))
    assert seen == ["first"]


def test_event_bus_singleton_is_reset_between_tests() -> None:
    """autouse _clean_globals 保证上一个用例的订阅不会泄漏到本用例。"""
    assert get_event_bus()._subscriptions == []


async def test_redis_fixture_uses_fakeredis_by_default(redis: Any) -> None:
    await redis.set("t10:key", "value")
    assert await redis.get("t10:key") == "value"
    assert await check_redis() is True


async def test_client_hits_healthz(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_client_supports_dependency_overrides(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    @app.get("/_whoami")
    async def whoami(value: str = Depends(_whoami)) -> dict[str, str]:
        return {"value": value}

    assert (await client.get("/_whoami")).json() == {"value": "production"}
    app.dependency_overrides[_whoami] = lambda: "test-double"
    assert (await client.get("/_whoami")).json() == {"value": "test-double"}
    app.dependency_overrides.clear()


async def test_db_session_writer_commits_inside_transaction(
    db_session: AsyncSession,
) -> None:
    """测试 A：写入并 commit（被测代码里的 commit 也不应泄漏到其它测试）。"""
    await db_session.execute(
        text("INSERT INTO audit_log (action, detail) VALUES (:action, CAST('{}' AS jsonb))"),
        {"action": _MARKER},
    )
    await db_session.commit()
    count: int = (
        await db_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = :marker"),
            {"marker": _MARKER},
        )
    ).scalar_one()
    assert count == 1


async def test_db_session_reader_cannot_see_previous_test(db_session: AsyncSession) -> None:
    """测试 B：上一个用例写入并 commit 的数据在本用例不可见。"""
    count: int = (
        await db_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = :marker"),
            {"marker": _MARKER},
        )
    ).scalar_one()
    assert count == 0


async def test_db_session_explicit_commit_writer(db_session: AsyncSession) -> None:
    await db_session.execute(
        text("INSERT INTO audit_log (action, detail) VALUES (:action, CAST('{}' AS jsonb))"),
        {"action": _MARKER_COMMIT},
    )
    await db_session.commit()
    assert (
        await db_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = :marker"),
            {"marker": _MARKER_COMMIT},
        )
    ).scalar_one() == 1


async def test_db_session_explicit_commit_does_not_leak(db_session: AsyncSession) -> None:
    """专门用例：被测代码内 commit() 后，另一个事务仍读不到。"""
    count: int = (
        await db_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = :marker"),
            {"marker": _MARKER_COMMIT},
        )
    ).scalar_one()
    assert count == 0
