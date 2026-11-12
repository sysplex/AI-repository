# ruff: noqa: S105, S106
# 本文件使用伪造口令验证审计内容，非真实凭据。
"""M1-T04：认证审计（真实 Postgres），`CONTRACTS §9` 行为 1–4。

读回 `audit_log` 断言 4 类 action 齐全、`user_id` 正确关联，
并确认 `detail` 里既没有密码/令牌，也没有明文邮箱。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_identity_service
from app.core.audit import AuditLog
from app.core.config import Settings
from app.modules.identity.service import build_identity_service

pytestmark = pytest.mark.integration

_PASSWORD = "Str0ngPassw0rd!"
_REGISTER = "/api/v1/auth/register"
_LOGIN = "/api/v1/auth/login"
_REFRESH = "/api/v1/auth/refresh"
_LOGOUT = "/api/v1/auth/logout"


@pytest.fixture
def auth(app: FastAPI, db_session: AsyncSession, redis: Any, settings: Settings) -> FastAPI:
    def _override() -> Any:
        return build_identity_service(session=db_session, settings=settings, redis=redis)

    app.dependency_overrides[get_identity_service] = _override
    return app


async def _audit_rows(session: AsyncSession, user_id: uuid.UUID) -> list[AuditLog]:
    await session.commit()
    result = await session.execute(
        select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.created_at)
    )
    return list(result.scalars().all())


async def test_full_flow_writes_four_audit_actions(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    del auth
    email = "audit@example.com"
    created = (await client.post(_REGISTER, json={"email": email, "password": _PASSWORD})).json()
    user_id = uuid.UUID(created["id"])

    pair = (await client.post(_LOGIN, json={"email": email, "password": _PASSWORD})).json()
    rotated = (await client.post(_REFRESH, json={"refresh_token": pair["refresh_token"]})).json()
    logout = await client.post(
        _LOGOUT,
        json={"refresh_token": rotated["refresh_token"]},
        headers={"Authorization": f"Bearer {rotated['access_token']}"},
    )
    assert logout.status_code == 204

    rows = await _audit_rows(db_session, user_id)
    actions = [row.action for row in rows]
    assert actions == ["auth.register", "auth.login", "auth.refresh", "auth.logout"]
    assert all(row.entity == "user" and row.entity_id == str(user_id) for row in rows)
    assert all(row.ip for row in rows)

    secrets = [pair["access_token"], pair["refresh_token"], rotated["refresh_token"], _PASSWORD]
    for row in rows:
        text = str(row.detail)
        assert email not in text, "审计 detail 不应写明文邮箱"
        for secret in secrets:
            assert secret not in text, f"审计 detail 泄露了凭据：{row.action}"


async def test_failed_login_is_not_audited_but_does_not_leak(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    """失败尝试只计数不写审计（避免被用来刷库），且响应体不含凭据。"""
    del auth
    email = "audit-fail@example.com"
    created = (await client.post(_REGISTER, json={"email": email, "password": _PASSWORD})).json()
    user_id = uuid.UUID(created["id"])

    failed = await client.post(_LOGIN, json={"email": email, "password": "Wr0ngPassw0rd!"})
    assert failed.status_code == 401
    assert "Wr0ngPassw0rd!" not in failed.text

    rows = await _audit_rows(db_session, user_id)
    assert [row.action for row in rows] == ["auth.register"]
