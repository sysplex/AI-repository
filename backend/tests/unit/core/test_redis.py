"""M0-T07 Redis 客户端验收（`docs/tasks/M0/T07-health-metrics-redis.md`）。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import fakeredis
import pytest
from pydantic import SecretStr

from app.core import redis as redis_module
from app.core.config import Settings
from app.core.redis import check_redis, close_redis, get_redis


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://svc@db.internal:5432/app",
        redis_url="redis://cache.internal:6379/0",
        secret_key=SecretStr("s" * 40),
    )


@pytest.fixture(autouse=True)
def _reset_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """每个用例都从「未初始化」状态开始，避免单例串味。"""
    monkeypatch.setattr(redis_module, "_client", None)
    yield


async def test_get_redis_is_lazy_singleton_with_two_second_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)

    def fake_from_url(url: str, **kwargs: Any) -> Any:
        captured.update(url=url, **kwargs)
        return fake

    monkeypatch.setattr("redis.asyncio.from_url", fake_from_url)
    monkeypatch.setattr("app.core.redis.get_settings", _settings)

    assert redis_module._client is None
    assert get_redis() is fake
    assert get_redis() is fake  # 第二次不再创建
    assert captured["url"] == "redis://cache.internal:6379/0"
    assert captured["decode_responses"] is True
    assert captured["socket_connect_timeout"] == 2.0
    assert captured["socket_timeout"] == 2.0


async def test_check_redis_true_with_fakeredis(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "_client", fake)
    assert await check_redis() is True
    await close_redis()


async def test_check_redis_false_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Broken:
        async def ping(self) -> bool:
            raise ConnectionError("redis down")

    monkeypatch.setattr(redis_module, "_client", _Broken())
    assert await check_redis() is False


async def test_check_redis_false_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Hanging:
        async def ping(self) -> bool:
            await asyncio.Event().wait()
            return True

    monkeypatch.setattr(redis_module, "_client", _Hanging())
    monkeypatch.setattr(redis_module, "_TIMEOUT_SECONDS", 0.01)
    assert await check_redis() is False


async def test_close_redis_resets_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Closable:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    fake = _Closable()
    monkeypatch.setattr(redis_module, "_client", fake)
    await close_redis()
    assert fake.closed is True
    assert redis_module._client is None


async def test_close_redis_is_idempotent() -> None:
    await close_redis()
    await close_redis()
    assert redis_module._client is None
