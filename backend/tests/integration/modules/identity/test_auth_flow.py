# ruff: noqa: S105, S106, S107
# 本文件使用伪造口令与 `bearer` 字面量验证认证行为，均非真实凭据。
"""M1-T04：注册 → 登录 → 刷新 → 登出全链路（真实 Postgres + fakeredis）。

`docs/08-test-plan.md` M1 第 1 项。用 `app.dependency_overrides` 把
`get_identity_service` 换成绑定测试会话与 fakeredis 的实例，走真实 HTTP 栈
（含 M0 的中间件、统一错误处理与安全响应头）。
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, cast

import jwt
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_identity_service
from app.core.clock import get_clock
from app.core.config import Settings
from app.modules.identity.adapters.token_codec import JWTTokenCodec
from app.modules.identity.enums import UserRole
from app.modules.identity.service import build_identity_service

pytestmark = pytest.mark.integration

_PASSWORD = "Str0ngPassw0rd!"
_REGISTER = "/api/v1/auth/register"
_LOGIN = "/api/v1/auth/login"
_REFRESH = "/api/v1/auth/refresh"
_LOGOUT = "/api/v1/auth/logout"


@pytest.fixture
def auth(app: FastAPI, db_session: AsyncSession, redis: Any, settings: Settings) -> FastAPI:
    """把服务依赖指向测试会话与 fakeredis（同一事件循环，异步会话可直传）。"""

    def _override() -> Any:
        return build_identity_service(session=db_session, settings=settings, redis=redis)

    app.dependency_overrides[get_identity_service] = _override
    return app


async def _register(client: AsyncClient, email: str = "neo@example.com") -> dict[str, Any]:
    response = await client.post(_REGISTER, json={"email": email, "password": _PASSWORD})
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


async def _login(client: AsyncClient, email: str = "neo@example.com") -> dict[str, Any]:
    response = await client.post(_LOGIN, json={"email": email, "password": _PASSWORD})
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


async def test_register_login_refresh_logout_flow(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    del auth
    created = await _register(client)
    assert created["email"] == "neo@example.com"
    assert created["role"] == "user"
    assert created["status"] == "active"
    assert created["settings"]["risk_profile"] == "balanced"
    assert "password" not in created and "password_hash" not in created
    await db_session.commit()

    first = await _login(client)
    assert first["token_type"] == "bearer"
    assert first["expires_in"] > 0
    assert first["access_token"] != first["refresh_token"]
    await db_session.commit()

    rotated = await client.post(_REFRESH, json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    # access 令牌的 claims 只有 sub/role/iat/exp（CONTRACTS §5/§8），没有 jti，
    # 因此同一秒内为同一用户签发的 access 可能逐字节相同——这是契约的必然结果，
    # 不作为「轮换是否生效」的判据；这里只断言它仍然有效且属于同一用户。
    assert _user_id_from(second) == _user_id_from(first)
    await db_session.commit()

    # 轮换后旧 refresh 立即失效（OAuth 刷新令牌轮换语义）
    reused = await client.post(_REFRESH, json={"refresh_token": first["refresh_token"]})
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "UNAUTHENTICATED"

    logout = await client.post(
        _LOGOUT,
        json={"refresh_token": second["refresh_token"]},
        headers={"Authorization": f"Bearer {second['access_token']}"},
    )
    assert logout.status_code == 204
    await db_session.commit()

    after_logout = await client.post(_REFRESH, json={"refresh_token": second["refresh_token"]})
    assert after_logout.status_code == 401
    assert after_logout.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_register_duplicate_email_conflicts(auth: FastAPI, client: AsyncClient) -> None:
    del auth
    await _register(client)
    duplicate = await client.post(
        _REGISTER, json={"email": "NEO@example.com", "password": _PASSWORD}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "STATE_CONFLICT"


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": _PASSWORD},
        {"email": "neo@example.com", "password": "short"},
        {"email": "neo@example.com", "password": "alllowercase12345"},
    ],
)
async def test_register_validation_errors_are_400_and_do_not_echo(
    auth: FastAPI, client: AsyncClient, payload: dict[str, str]
) -> None:
    del auth
    response = await client.post(_REGISTER, json=payload)
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert _PASSWORD not in response.text
    assert payload["password"] not in response.text


async def test_login_failures_are_generic(auth: FastAPI, client: AsyncClient) -> None:
    del auth
    await _register(client)
    wrong = await client.post(
        _LOGIN, json={"email": "neo@example.com", "password": "Wr0ngPassword!"}
    )
    ghost = await client.post(_LOGIN, json={"email": "ghost@example.com", "password": _PASSWORD})

    assert wrong.status_code == ghost.status_code == 401
    assert wrong.json()["error"]["code"] == ghost.json()["error"]["code"] == "UNAUTHENTICATED"
    assert wrong.json()["error"]["message"] == ghost.json()["error"]["message"]


async def test_logout_requires_valid_bearer(auth: FastAPI, client: AsyncClient) -> None:
    del auth
    await _register(client)
    pair = await _login(client)

    missing = await client.post(_LOGOUT, json={"refresh_token": pair["refresh_token"]})
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "UNAUTHENTICATED"

    malformed = await client.post(
        _LOGOUT,
        json={"refresh_token": pair["refresh_token"]},
        headers={"Authorization": "Token abc"},
    )
    assert malformed.status_code == 401

    garbage = await client.post(
        _LOGOUT,
        json={"refresh_token": pair["refresh_token"]},
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert garbage.status_code == 401


async def test_expired_access_returns_token_expired(
    auth: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    del auth
    await _register(client)
    pair = await _login(client)
    claims = JWTTokenCodec(settings.secret_key.get_secret_value(), settings.jwt_algorithm)

    expired = claims.issue_access(
        user_id=_user_id_from(pair),
        role=UserRole.USER,
        now=get_clock().now() - timedelta(seconds=10),
        ttl_seconds=1,
    )
    response = await client.post(
        _LOGOUT,
        json={"refresh_token": pair["refresh_token"]},
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


async def test_error_body_request_id_matches_header(auth: FastAPI, client: AsyncClient) -> None:
    """M0-F1 回归：错误体的 `request_id` 必须与响应头一致。"""
    del auth
    response = await client.post(_LOGIN, json={"email": "ghost@example.com", "password": _PASSWORD})
    assert response.status_code == 401
    header_id = response.headers["X-Request-ID"]
    assert response.json()["error"]["request_id"] == header_id


def _user_id_from(pair: dict[str, Any]) -> uuid.UUID:
    """从 access 令牌里取 `sub`，避免测试再查一次库。"""
    payload: dict[str, Any] = jwt.decode(
        pair["access_token"],
        options={"verify_signature": False, "verify_exp": False, "verify_iat": False},
    )
    return uuid.UUID(str(payload["sub"]))
