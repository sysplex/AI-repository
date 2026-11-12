# ruff: noqa: S105, S106
# 本文件使用伪造口令验证限流行为，非真实凭据。
"""M1-T04：登录失败限流（真实 Postgres + fakeredis），`CONTRACTS §12`。

覆盖：达阈值 429 + `Retry-After`、成功登录清零、账号键与 IP 键相互独立、
Redis 键的过期窗口（fakeredis 直接断言 TTL）。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_identity_service
from app.core.config import Settings
from app.modules.identity.security import hash_opaque_token
from app.modules.identity.service import build_identity_service

pytestmark = pytest.mark.integration

_PASSWORD = "Str0ngPassw0rd!"
_WRONG = "Wr0ngPassw0rd!"
_REGISTER = "/api/v1/auth/register"
_LOGIN = "/api/v1/auth/login"


@pytest.fixture
def auth(app: FastAPI, db_session: AsyncSession, redis: Any, settings: Settings) -> FastAPI:
    def _override() -> Any:
        return build_identity_service(session=db_session, settings=settings, redis=redis)

    app.dependency_overrides[get_identity_service] = _override
    return app


async def _register(client: AsyncClient, email: str) -> None:
    response = await client.post(_REGISTER, json={"email": email, "password": _PASSWORD})
    assert response.status_code == 201, response.text


async def _fail_login(client: AsyncClient, email: str, times: int) -> None:
    for _ in range(times):
        response = await client.post(_LOGIN, json={"email": email, "password": _WRONG})
        assert response.status_code == 401


async def test_blocks_after_threshold_with_retry_after(
    auth: FastAPI, client: AsyncClient, settings: Settings, redis: Any
) -> None:
    del auth
    email = "limit@example.com"
    await _register(client, email)
    await _fail_login(client, email, settings.login_rate_limit_max)

    blocked = await client.post(_LOGIN, json={"email": email, "password": _PASSWORD})
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert body["error"]["details"]["retry_after"] >= 1

    account_key = f"login:fail:account:{hash_opaque_token(email)[:12]}"
    assert int(await redis.get(account_key)) == settings.login_rate_limit_max
    assert 0 < int(await redis.ttl(account_key)) <= settings.login_rate_limit_window_seconds


async def test_successful_login_resets_counters(
    auth: FastAPI, client: AsyncClient, settings: Settings, redis: Any
) -> None:
    del auth
    email = "reset@example.com"
    await _register(client, email)
    await _fail_login(client, email, settings.login_rate_limit_max - 1)

    ok = await client.post(_LOGIN, json={"email": email, "password": _PASSWORD})
    assert ok.status_code == 200

    account_key = f"login:fail:account:{hash_opaque_token(email)[:12]}"
    assert await redis.get(account_key) is None
    # 清零后仍可继续失败到阈值，说明窗口确实被重置而不是继续累加
    await _fail_login(client, email, settings.login_rate_limit_max - 1)
    assert (
        await client.post(_LOGIN, json={"email": email, "password": _PASSWORD})
    ).status_code == 200


async def test_account_key_alone_blocks_even_with_clean_ip(
    auth: FastAPI, client: AsyncClient, settings: Settings, redis: Any
) -> None:
    """账号键单独达阈值就拦：用预置键把 IP 键保持为 0，排除 IP 维度干扰。"""
    del auth
    email = "account-key@example.com"
    await _register(client, email)

    account_key = f"login:fail:account:{hash_opaque_token(email)[:12]}"
    await redis.set(account_key, settings.login_rate_limit_max)
    assert await redis.get("login:fail:ip:127.0.0.1") is None

    blocked = await client.post(_LOGIN, json={"email": email, "password": _PASSWORD})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"


async def test_ip_key_alone_blocks_across_accounts(
    auth: FastAPI, client: AsyncClient, settings: Settings, redis: Any
) -> None:
    """IP 键单独达阈值就拦：账号键为空也要拒，防止换账号绕过。"""
    del auth
    first, second = "ip-a@example.com", "ip-b@example.com"
    await _register(client, first)
    await _register(client, second)

    await _fail_login(client, first, 1)
    ip_keys = [key async for key in redis.scan_iter("login:fail:ip:*")]
    assert len(ip_keys) == 1
    assert "127.0.0.1" in ip_keys[0]
    await redis.set(ip_keys[0], settings.login_rate_limit_max)

    blocked = await client.post(_LOGIN, json={"email": second, "password": _PASSWORD})
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
