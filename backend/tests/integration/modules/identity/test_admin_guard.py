# ruff: noqa: S105, S106
# 本文件使用伪造口令验证管理员守卫，非真实凭据。
"""M1-T05：`/admin/users` 管理员守卫（真实 Postgres + fakeredis）。

四态断言：匿名 401、普通用户 403 `FORBIDDEN`、admin 200、禁用用户 401；
并覆盖 `require_role` 两种角色的判定（经 HTTP 走真实依赖）。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_identity_service
from app.core.config import Settings
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.models import User
from app.modules.identity.service import build_identity_service

pytestmark = pytest.mark.integration

_PASSWORD = "Str0ngPassw0rd!"
_REGISTER = "/api/v1/auth/register"
_LOGIN = "/api/v1/auth/login"
_ADMIN_USERS = "/api/v1/admin/users"


@pytest.fixture
def auth(app: FastAPI, db_session: AsyncSession, redis: Any, settings: Settings) -> FastAPI:
    def _override() -> Any:
        return build_identity_service(session=db_session, settings=settings, redis=redis)

    app.dependency_overrides[get_identity_service] = _override
    return app


async def _account(
    client: AsyncClient,
    db_session: AsyncSession,
    email: str,
    *,
    role: UserRole = UserRole.USER,
) -> str:
    """注册（必要时先提权）+ 登录，返回 access 令牌。

    角色必须在登录**之前**改：`authenticate_access_token` 会比对令牌里的 role
    与库里的现状，登录后再提权会导致令牌立即失效（这是设计使然，见 T04 D6）。
    """
    created = await client.post(_REGISTER, json={"email": email, "password": _PASSWORD})
    assert created.status_code == 201, created.text
    if role is not UserRole.USER:
        await db_session.execute(
            update(User).where(User.id == uuid.UUID(created.json()["id"])).values(role=role.value)
        )
        await db_session.commit()
    pair = await client.post(_LOGIN, json={"email": email, "password": _PASSWORD})
    assert pair.status_code == 200, pair.text
    return str(pair.json()["access_token"])


async def test_admin_users_rejects_anonymous(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    del auth
    await _account(client, db_session, "anon@example.com")

    response = await client.get(_ADMIN_USERS)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_admin_users_rejects_normal_user(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    del auth
    token = await _account(client, db_session, "plain@example.com")

    response = await client.get(_ADMIN_USERS, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "FORBIDDEN"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


async def test_admin_users_allows_admin(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    del auth
    await _account(client, db_session, "member@example.com")
    token = await _account(client, db_session, "root@example.com", role=UserRole.ADMIN)

    response = await client.get(_ADMIN_USERS, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1 and body["page_size"] == 20
    assert body["total"] == 2
    assert {item["email"] for item in body["items"]} == {"member@example.com", "root@example.com"}
    assert all("password" not in item and "password_hash" not in item for item in body["items"])


async def test_admin_users_pagination(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    del auth
    token = await _account(client, db_session, "pageroot@example.com", role=UserRole.ADMIN)
    for index in range(3):
        await _account(client, db_session, f"page{index}@example.com")

    first = await client.get(
        _ADMIN_USERS,
        params={"page": 1, "page_size": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    second = await client.get(
        _ADMIN_USERS,
        params={"page": 2, "page_size": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == second.json()["total"] == 4
    assert len(first.json()["items"]) == len(second.json()["items"]) == 2
    ids = {item["id"] for item in first.json()["items"]} & {
        item["id"] for item in second.json()["items"]
    }
    assert ids == set()


@pytest.mark.parametrize(
    "params",
    [{"page": 0}, {"page_size": 0}, {"page_size": 101}, {"page": "x"}],
)
async def test_admin_users_rejects_invalid_pagination(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession, params: dict[str, Any]
) -> None:
    del auth
    token = await _account(client, db_session, "parambad@example.com", role=UserRole.ADMIN)
    response = await client.get(
        _ADMIN_USERS, params=params, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_disabled_user_is_unauthenticated(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    """登录后被禁用：既有令牌立即失效，返回 401 而不是 403。"""
    del auth
    token = await _account(client, db_session, "disabled@example.com")
    await db_session.execute(
        update(User)
        .where(User.email == "disabled@example.com")
        .values(status=UserStatus.DISABLED.value)
    )
    await db_session.commit()

    response = await client.get(_ADMIN_USERS, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
