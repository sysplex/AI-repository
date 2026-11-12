# ruff: noqa: S105, S106
# 本文件使用伪造口令验证重置流程，非真实凭据。
"""M1-T06：密码重置两端点集成测试（真实 Postgres + fakeredis）。

覆盖 `docs/08-test-plan.md` M1 第 4 项「审计日志记录改密」与 `CONTRACTS §9` 行为 6–7：
完整流程、账号枚举防护、令牌一次性/过期/伪造、改密后旧 refresh 全吊销、
审计不含口令与令牌、访问日志与响应体不含明文令牌。
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_identity_service
from app.core.audit import AuditLog
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.modules.identity.adapters.mail import InMemoryMailSender
from app.modules.identity.models import PasswordResetToken
from app.modules.identity.service import build_identity_service

pytestmark = pytest.mark.integration

_PASSWORD = "Str0ngPassw0rd!"
_NEW_PASSWORD = "N3wStr0ngPassw0rd!"
_REGISTER = "/api/v1/auth/register"
_LOGIN = "/api/v1/auth/login"
_REFRESH = "/api/v1/auth/refresh"
_RESET_REQUEST = "/api/v1/auth/password/reset-request"
_RESET_CONFIRM = "/api/v1/auth/password/reset-confirm"
_TOKEN_LINE = re.compile(r"^[A-Za-z0-9_-]{32,64}$", re.MULTILINE)


@pytest.fixture(autouse=True)
def _freeze_clock(frozen_clock: Any) -> None:
    del frozen_clock


@pytest.fixture
def mailbox() -> InMemoryMailSender:
    """测试专用信箱：服务的 `MailSender` 端口实现，测试从中取明文令牌。"""
    return InMemoryMailSender()


@pytest.fixture
def auth(
    app: FastAPI,
    db_session: AsyncSession,
    redis: Any,
    settings: Settings,
    mailbox: InMemoryMailSender,
) -> FastAPI:
    def _override() -> Any:
        return build_identity_service(
            session=db_session, settings=settings, redis=redis, mail=mailbox
        )

    app.dependency_overrides[get_identity_service] = _override
    return app


async def _register(client: AsyncClient, email: str) -> uuid.UUID:
    response = await client.post(_REGISTER, json={"email": email, "password": _PASSWORD})
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


async def _login(client: AsyncClient, email: str, password: str = _PASSWORD) -> Any:
    return await client.post(_LOGIN, json={"email": email, "password": password})


def _token_of(mailbox: InMemoryMailSender) -> str:
    matches = _TOKEN_LINE.findall(mailbox.messages[-1].body)
    assert len(matches) == 1, f"邮件正文应恰好含一个令牌行，实际 {matches}"
    return str(matches[0])


async def _audit_actions(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    await session.commit()
    result = await session.execute(
        select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.created_at)
    )
    return [row.action for row in result.scalars().all()]


async def _reset_rows(session: AsyncSession) -> list[PasswordResetToken]:
    await session.commit()
    result = await session.execute(
        select(PasswordResetToken).order_by(PasswordResetToken.created_at)
    )
    return list(result.scalars().all())


async def test_full_reset_flow_changes_password_and_revokes_sessions(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession, mailbox: InMemoryMailSender
) -> None:
    """请求 → 取令牌 → 确认 → 旧口令 401 / 新口令 200 / 旧 refresh 401。"""
    del auth
    email = "reset@example.com"
    user_id = await _register(client, email)
    first = await _login(client, email)
    assert first.status_code == 200
    old_refresh = first.json()["refresh_token"]

    requested = await client.post(_RESET_REQUEST, json={"email": email})
    assert requested.status_code == 202
    assert requested.json() == {"status": "accepted"}
    assert len(mailbox.messages) == 1
    assert mailbox.messages[0].to == email
    token = _token_of(mailbox)

    confirmed = await client.post(
        _RESET_CONFIRM, json={"token": token, "new_password": _NEW_PASSWORD}
    )
    assert confirmed.status_code == 204
    assert confirmed.text == ""

    assert (await _login(client, email)).status_code == 401
    assert (await _login(client, email, _NEW_PASSWORD)).status_code == 200

    rejected = await client.post(_REFRESH, json={"refresh_token": old_refresh})
    assert rejected.status_code == 401

    assert await _audit_actions(db_session, user_id) == [
        "auth.register",
        "auth.login",
        "auth.password_reset_requested",
        "auth.password_changed",
    ]
    rows = await _reset_rows(db_session)
    assert len(rows) == 1
    assert rows[0].used_at is not None
    assert rows[0].token_hash != token


async def test_reset_request_hides_account_existence(
    auth: FastAPI, client: AsyncClient, mailbox: InMemoryMailSender
) -> None:
    """存在与不存在的邮箱返回完全相同的 202 响应体，且只有真实账号会收到邮件。"""
    del auth
    email = "exists@example.com"
    await _register(client, email)

    exists = await client.post(_RESET_REQUEST, json={"email": email})
    ghost = await client.post(_RESET_REQUEST, json={"email": "ghost@example.com"})

    assert exists.status_code == ghost.status_code == 202
    assert exists.json() == ghost.json() == {"status": "accepted"}
    assert len(mailbox.messages) == 1
    assert mailbox.messages[0].to == email


async def test_reset_token_is_single_use(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession, mailbox: InMemoryMailSender
) -> None:
    del auth
    email = "once@example.com"
    await _register(client, email)
    await client.post(_RESET_REQUEST, json={"email": email})
    token = _token_of(mailbox)
    payload = {"token": token, "new_password": _NEW_PASSWORD}

    assert (await client.post(_RESET_CONFIRM, json=payload)).status_code == 204
    second = await client.post(_RESET_CONFIRM, json=payload)

    assert second.status_code == 401
    assert second.json()["error"]["code"] == "UNAUTHENTICATED"
    rows = await _reset_rows(db_session)
    assert [row.used_at is not None for row in rows] == [True]


async def test_expired_reset_token_is_rejected(
    auth: FastAPI,
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: InMemoryMailSender,
    frozen_clock: FrozenClock,
    settings: Settings,
) -> None:
    del auth
    email = "expired@example.com"
    await _register(client, email)
    await client.post(_RESET_REQUEST, json={"email": email})
    token = _token_of(mailbox)

    frozen_clock.advance(timedelta(seconds=settings.password_reset_ttl_seconds + 1))
    expired = await client.post(
        _RESET_CONFIRM, json={"token": token, "new_password": _NEW_PASSWORD}
    )

    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "UNAUTHENTICATED"
    rows = await _reset_rows(db_session)
    assert rows[0].used_at is None
    assert (await _login(client, email)).status_code == 200


async def test_forged_reset_token_is_rejected(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession, mailbox: InMemoryMailSender
) -> None:
    """伪造令牌与真令牌摘要不匹配，一律 401；真令牌仍然可用（未被误消耗）。"""
    del auth
    email = "forged@example.com"
    await _register(client, email)
    await client.post(_RESET_REQUEST, json={"email": email})
    token = _token_of(mailbox)

    forged = await client.post(
        _RESET_CONFIRM,
        json={"token": "A" * 43, "new_password": _NEW_PASSWORD},
    )
    assert forged.status_code == 401
    rows = await _reset_rows(db_session)
    assert rows[0].used_at is None

    valid = await client.post(_RESET_CONFIRM, json={"token": token, "new_password": _NEW_PASSWORD})
    assert valid.status_code == 204


async def test_reset_revokes_every_refresh_token(
    auth: FastAPI, client: AsyncClient, mailbox: InMemoryMailSender
) -> None:
    """改密后该用户此前签发的全部 refresh 令牌（多个会话）立即不可用。"""
    del auth
    email = "multi@example.com"
    await _register(client, email)
    sessions = [(await _login(client, email)).json()["refresh_token"] for _ in range(2)]

    await client.post(_RESET_REQUEST, json={"email": email})
    token = _token_of(mailbox)
    confirmed = await client.post(
        _RESET_CONFIRM, json={"token": token, "new_password": _NEW_PASSWORD}
    )
    assert confirmed.status_code == 204

    for refresh_token in sessions:
        response = await client.post(_REFRESH, json={"refresh_token": refresh_token})
        assert response.status_code == 401


async def test_plaintext_token_never_leaks_to_logs_or_responses(
    auth: FastAPI,
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: InMemoryMailSender,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """令牌只出现在邮件正文：响应体、审计 detail、访问日志都不得含明文。"""
    del auth
    email = "leak@example.com"
    user_id = await _register(client, email)

    with caplog.at_level(logging.DEBUG):
        requested = await client.post(_RESET_REQUEST, json={"email": email})
        token = _token_of(mailbox)
        confirmed = await client.post(
            _RESET_CONFIRM, json={"token": token, "new_password": _NEW_PASSWORD}
        )

    assert requested.status_code == 202
    assert confirmed.status_code == 204
    assert token not in requested.text
    assert token not in confirmed.text

    await db_session.commit()
    result = await db_session.execute(select(AuditLog).where(AuditLog.user_id == user_id))
    for row in result.scalars().all():
        assert token not in str(row.detail), f"审计泄露令牌：{row.action}"
        assert _NEW_PASSWORD not in str(row.detail), f"审计泄露口令：{row.action}"

    assert token not in caplog.text
    assert _NEW_PASSWORD not in caplog.text
