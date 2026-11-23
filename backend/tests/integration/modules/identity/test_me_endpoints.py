# ruff: noqa: S105, S106
# 本文件使用伪造口令验证自助接口，非真实凭据。
"""M1-T05：`/me`、`PATCH /me`、`/me/usage`（真实 Postgres + fakeredis）。

覆盖设置项往返、`auth.settings_updated` 审计、非法枚举 400、
用量全 0 与 `Decimal` 字符串序列化、以及两个用户用量互不串读。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_identity_service
from app.core.audit import AuditLog
from app.core.config import Settings
from app.modules.identity.models import AiUsage
from app.modules.identity.service import build_identity_service

pytestmark = pytest.mark.integration

_PASSWORD = "Str0ngPassw0rd!"
_REGISTER = "/api/v1/auth/register"
_LOGIN = "/api/v1/auth/login"
_ME = "/api/v1/me"
_USAGE = "/api/v1/me/usage"
_TODAY = date(2026, 11, 11)  # 与 conftest FROZEN_AT 一致


@pytest.fixture(autouse=True)
def _freeze_clock(frozen_clock: Any) -> None:
    """冻结时钟，使 `/me/usage` 的「今日」与 `_TODAY` 一致。"""
    del frozen_clock


@pytest.fixture
def auth(app: FastAPI, db_session: AsyncSession, redis: Any, settings: Settings) -> FastAPI:
    def _override() -> Any:
        return build_identity_service(session=db_session, settings=settings, redis=redis)

    app.dependency_overrides[get_identity_service] = _override
    return app


async def _account(client: AsyncClient, email: str) -> tuple[dict[str, Any], str]:
    created = (await client.post(_REGISTER, json={"email": email, "password": _PASSWORD})).json()
    pair = (await client.post(_LOGIN, json={"email": email, "password": _PASSWORD})).json()
    return created, str(pair["access_token"])


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_get_me_returns_own_profile(auth: FastAPI, client: AsyncClient) -> None:
    del auth
    created, token = await _account(client, "me@example.com")

    response = await client.get(_ME, headers=_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["email"] == "me@example.com"
    assert body["settings"]["risk_profile"] == "balanced"
    assert body["settings"]["ai_provider"] == "mock"
    assert body["settings"]["google_api_key"] is None
    assert body["settings"]["google_model"] == "gemini-3.5-flash-lite"
    assert "password" not in str(body) and "password_hash" not in body


async def test_patch_me_roundtrip_and_audit(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    del auth
    created, token = await _account(client, "patch@example.com")
    account_id = str(uuid.uuid4())

    updated = await client.patch(
        _ME,
        headers=_headers(token),
        json={
            "settings": {
                "risk_profile": "aggressive",
                "language": "en-US",
                "default_account_id": account_id,
                "ai_provider": "google",
                "google_api_key": "test-google-key",
                "google_model": "gemini-2.5-flash",
            }
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["settings"] == {
        "risk_profile": "aggressive",
        "language": "en-US",
        "default_account_id": account_id,
        "ai_provider": "google",
        "google_api_key": "test-google-key",
        "google_model": "gemini-2.5-flash",
    }
    # 再读一次确认已落库（不是只改了响应对象）
    again = await client.get(_ME, headers=_headers(token))
    assert again.json()["settings"]["risk_profile"] == "aggressive"
    assert again.json()["settings"]["ai_provider"] == "google"
    assert again.json()["settings"]["google_api_key"] == "test-google-key"
    assert again.json()["settings"]["google_model"] == "gemini-2.5-flash"

    await db_session.commit()
    rows = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.user_id == uuid.UUID(created["id"]),
                    AuditLog.action == "auth.settings_updated",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].detail == {
        "keys": [
            "ai_provider",
            "default_account_id",
            "google_api_key",
            "google_model",
            "language",
            "risk_profile",
        ]
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"settings": {"risk_profile": "yolo"}},
        {"settings": {"language": "zh-CN", "unknown_key": 1}},
        {},
    ],
)
async def test_patch_me_rejects_invalid_settings(
    auth: FastAPI, client: AsyncClient, payload: dict[str, Any]
) -> None:
    del auth
    _, token = await _account(client, "bad-patch@example.com")
    response = await client.patch(_ME, headers=_headers(token), json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_usage_without_record_is_zero_with_configured_quota(
    auth: FastAPI, client: AsyncClient, settings: Settings
) -> None:
    del auth
    _, token = await _account(client, "usage-empty@example.com")

    response = await client.get(_USAGE, headers=_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body["usage_date"] == _TODAY.isoformat()
    assert body["calls"] == body["tokens_in"] == body["tokens_out"] == body["quota_used"] == 0
    assert body["quota"] == settings.ai_daily_quota
    # Decimal 按 docs/05 §1 以字符串返回，避免二进制浮点误差
    assert isinstance(body["cost_usd"], str)
    assert Decimal(body["cost_usd"]) == Decimal("0")


async def test_usage_is_isolated_between_users(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    del auth
    first, first_token = await _account(client, "usage-a@example.com")
    second, second_token = await _account(client, "usage-b@example.com")

    db_session.add_all(
        [
            AiUsage(
                id=uuid.uuid4(),
                user_id=uuid.UUID(first["id"]),
                usage_date=_TODAY,
                calls=7,
                tokens_in=1000,
                tokens_out=500,
                cost_usd=Decimal("1.234567"),
            ),
            AiUsage(
                id=uuid.uuid4(),
                user_id=uuid.UUID(second["id"]),
                usage_date=_TODAY,
                calls=42,
                tokens_in=9000,
                tokens_out=4000,
                cost_usd=Decimal("9.876543"),
            ),
        ]
    )
    await db_session.commit()

    mine = (await client.get(_USAGE, headers=_headers(first_token))).json()
    others = (await client.get(_USAGE, headers=_headers(second_token))).json()

    assert (mine["calls"], mine["tokens_in"], mine["tokens_out"]) == (7, 1000, 500)
    assert (others["calls"], others["tokens_in"], others["tokens_out"]) == (42, 9000, 4000)
    assert Decimal(mine["cost_usd"]) == Decimal("1.234567")
    assert Decimal(others["cost_usd"]) == Decimal("9.876543")
    assert mine["quota_used"] == 7 and others["quota_used"] == 42


async def test_usage_ignores_other_days(
    auth: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    """只读「当日」：未来/历史日期的记录不出现在今天的结果里。"""
    del auth
    created, token = await _account(client, "usage-day@example.com")
    db_session.add(
        AiUsage(
            id=uuid.uuid4(),
            user_id=uuid.UUID(created["id"]),
            usage_date=datetime(2026, 11, 10, tzinfo=UTC).date(),
            calls=99,
            tokens_in=1,
            tokens_out=1,
            cost_usd=Decimal("0.5"),
        )
    )
    await db_session.commit()

    body = (await client.get(_USAGE, headers=_headers(token))).json()
    assert body["calls"] == 0
    assert Decimal(body["cost_usd"]) == Decimal("0")
