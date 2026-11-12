# ruff: noqa: S105, S106
# 本文件使用伪造口令验证越权隔离，非真实凭据。
"""M1-T05：私有端点越权矩阵（真实 Postgres + fakeredis）。

矩阵一行对应一个私有端点；每行都验证「用户 A 的令牌既拿不到 B 的数据，
也不能对 B 的资源产生副作用」。越权一律 404 / 403 / 401 且响应体不含 B 的任何信息
（C10：越权与不存在同码，避免探测资源是否存在）。
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_identity_service
from app.core.config import Settings
from app.modules.identity.models import AiUsage
from app.modules.identity.service import build_identity_service

pytestmark = pytest.mark.integration

_PASSWORD = "Str0ngPassw0rd!"
_TODAY = date(2026, 11, 11)

Case = Callable[[AsyncClient, AsyncSession, "Actor", "Actor"], Awaitable[None]]


class Actor:
    """一个租户：注册返回的公开视图 + 登录得到的 access/refresh。"""

    def __init__(self, created: dict[str, Any], pair: dict[str, Any]) -> None:
        self.id = uuid.UUID(created["id"])
        self.email = created["email"]
        self.access = str(pair["access_token"])
        self.refresh = str(pair["refresh_token"])

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access}"}

    def assert_hidden(self, text: str) -> None:
        """响应体不得出现他人的邮箱、id 或令牌。"""
        assert self.email not in text
        assert str(self.id) not in text
        assert self.refresh not in text
        assert self.access not in text


@pytest.fixture(autouse=True)
def _freeze_clock(frozen_clock: Any) -> None:
    del frozen_clock


@pytest.fixture
def auth(app: FastAPI, db_session: AsyncSession, redis: Any, settings: Settings) -> FastAPI:
    def _override() -> Any:
        return build_identity_service(session=db_session, settings=settings, redis=redis)

    app.dependency_overrides[get_identity_service] = _override
    return app


async def _make_actor(client: AsyncClient, email: str) -> Actor:
    created = (
        await client.post("/api/v1/auth/register", json={"email": email, "password": _PASSWORD})
    ).json()
    pair = (
        await client.post("/api/v1/auth/login", json={"email": email, "password": _PASSWORD})
    ).json()
    return Actor(created, pair)


async def _case_get_me(client: AsyncClient, other: Actor, mine: Actor) -> None:
    response = await client.get("/api/v1/me", headers=mine.headers())
    assert response.status_code == 200
    assert response.json()["id"] == str(mine.id)
    other.assert_hidden(response.text)


async def _case_patch_me(client: AsyncClient, other: Actor, mine: Actor) -> None:
    response = await client.patch(
        "/api/v1/me",
        headers=mine.headers(),
        json={"settings": {"risk_profile": "aggressive", "language": "en-US"}},
    )
    assert response.status_code == 200
    other.assert_hidden(response.text)

    # 副作用隔离：B 的设置必须保持默认，A 的写入不得波及 B
    theirs = await client.get("/api/v1/me", headers=other.headers())
    assert theirs.json()["settings"]["risk_profile"] == "balanced"
    assert theirs.json()["settings"]["language"] == "zh-CN"


async def _case_usage(
    client: AsyncClient, session: AsyncSession, other: Actor, mine: Actor
) -> None:
    session.add_all(
        [
            AiUsage(
                id=uuid.uuid4(),
                user_id=mine.id,
                usage_date=_TODAY,
                calls=3,
                tokens_in=10,
                tokens_out=5,
                cost_usd=Decimal("0.100000"),
            ),
            AiUsage(
                id=uuid.uuid4(),
                user_id=other.id,
                usage_date=_TODAY,
                calls=88,
                tokens_in=8888,
                tokens_out=888,
                cost_usd=Decimal("8.880000"),
            ),
        ]
    )
    await session.commit()

    response = await client.get("/api/v1/me/usage", headers=mine.headers())
    assert response.status_code == 200
    body = response.json()
    assert body["calls"] == 3
    assert Decimal(body["cost_usd"]) == Decimal("0.100000")
    other.assert_hidden(response.text)


async def _case_admin_users(client: AsyncClient, other: Actor, mine: Actor) -> None:
    response = await client.get("/api/v1/admin/users", headers=mine.headers())
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    other.assert_hidden(response.text)


async def _case_logout(client: AsyncClient, other: Actor, mine: Actor) -> None:
    """A 用自己的 access 提交 B 的 refresh：不得吊销 B 的令牌。"""
    response = await client.post(
        "/api/v1/auth/logout",
        headers=mine.headers(),
        json={"refresh_token": other.refresh},
    )
    assert response.status_code == 204
    assert response.text == ""

    # B 的 refresh 仍然可用（说明没有跨租户吊销）
    still_valid = await client.post("/api/v1/auth/refresh", json={"refresh_token": other.refresh})
    assert still_valid.status_code == 200, still_valid.text


_MATRIX = [
    pytest.param(_case_get_me, "GET /me", id="GET /me"),
    pytest.param(_case_patch_me, "PATCH /me", id="PATCH /me"),
    pytest.param(_case_usage, "GET /me/usage", id="GET /me/usage"),
    pytest.param(_case_admin_users, "GET /admin/users", id="GET /admin/users"),
    pytest.param(_case_logout, "POST /auth/logout", id="POST /auth/logout"),
]


@pytest.mark.parametrize(("case", "endpoint"), _MATRIX)
async def test_private_endpoints_are_tenant_isolated(
    case: Case,
    endpoint: str,
    auth: FastAPI,
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    del auth, endpoint
    mine = await _make_actor(client, "tenant-a@example.com")
    other = await _make_actor(client, "tenant-b@example.com")
    await case(client, db_session, other, mine)


def test_matrix_covers_every_private_endpoint() -> None:
    """维护约定：新增私有端点必须同步扩充矩阵（T05 §7）。

    私有端点清单来自 `docs/tasks/M1/CONTRACTS.md §10` 与 `docs/05 §2.1`；
    T06 合入两个密码重置端点后由 T07 复核本清单。
    """
    covered = {param.id for param in _MATRIX}
    expected = {"GET /me", "PATCH /me", "GET /me/usage", "GET /admin/users", "POST /auth/logout"}
    assert covered == expected
