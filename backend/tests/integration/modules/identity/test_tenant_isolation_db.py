"""M1-T02：真实 Postgres 下的租户隔离与令牌有效性过滤。

本机无 `TEST_DATABASE_URL` 且无 Docker 时由 conftest 的 `db_session` 自动 skip；
CI 的 test job 带真实 Postgres 16，这些用例必须实跑（CONTRACTS §7 / T02 验收项）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import AiUsage, PasswordResetToken, RefreshToken, User
from app.modules.identity.repo import (
    AiUsageRepository,
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)

_NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
# 测试用占位哈希（非真实凭据）。
_TEST_HASH = "argon2$test-hash"


def _user(email: str) -> User:
    return User(id=uuid.uuid4(), email=email, password_hash=_TEST_HASH, settings={})


@pytest.mark.integration
async def test_tenant_repository_isolates_rows_between_users(db_session: AsyncSession) -> None:
    """用户 A 的仓储绝不能读到用户 B 的私有行（越权矩阵第一层）。"""
    user_a, user_b = _user("tenant-a@example.com"), _user("tenant-b@example.com")
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    day_a, day_b = _NOW.date(), (_NOW + timedelta(days=1)).date()
    usage_a = AiUsage(id=uuid.uuid4(), user_id=user_a.id, usage_date=day_a, calls=1)
    usage_b = AiUsage(id=uuid.uuid4(), user_id=user_b.id, usage_date=day_b, calls=2)
    db_session.add_all([usage_a, usage_b])
    await db_session.flush()

    repo_a = AiUsageRepository(db_session, user_id=user_a.id)
    repo_b = AiUsageRepository(db_session, user_id=user_b.id)

    rows_a = await repo_a.list_for_user()
    assert [row.id for row in rows_a] == [usage_a.id]
    assert all(row.user_id == user_a.id for row in rows_a)
    assert await repo_a.get_by_id(usage_b.id) is None
    assert await repo_b.get_by_id(usage_a.id) is None
    assert await repo_a.get_for_date(usage_date=day_b) is None
    found_b = await repo_b.get_for_date(usage_date=day_b)
    assert found_b is not None and found_b.id == usage_b.id


@pytest.mark.integration
async def test_user_repository_roundtrip_against_real_db(db_session: AsyncSession) -> None:
    """create 取回服务端默认值，按 email 检索、save、分页均可用。"""
    repo = UserRepository(db_session)
    user = await repo.create(
        email="roundtrip@example.com", password_hash=_TEST_HASH, settings={"language": "en-US"}
    )
    assert user.id is not None
    assert user.role == "user"
    assert user.status == "active"
    assert user.settings == {"language": "en-US"}
    assert user.created_at is not None

    found = await repo.get_by_email("roundtrip@example.com")
    assert found is not None and found.id == user.id
    assert await repo.get_by_email("absent@example.com") is None
    assert (await repo.get_by_id(user.id)) is not None

    found.settings = {"language": "fr-FR", "risk_profile": "aggressive"}
    await repo.save(found)
    items, total = await repo.list_paginated(page=1, page_size=10)
    assert total >= 1
    assert any(item.id == user.id for item in items)


@pytest.mark.integration
async def test_refresh_token_filters_against_real_db(db_session: AsyncSession) -> None:
    """过期 / 已吊销 / 不存在 / 摘要不匹配四类均返回 None；按用户批量吊销生效。"""
    user = _user("refresh-filter@example.com")
    db_session.add(user)
    await db_session.flush()

    active = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash="a" * 64,
        expires_at=_NOW + timedelta(days=1),
    )
    expired = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash="b" * 64,
        expires_at=_NOW - timedelta(seconds=1),
    )
    revoked = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash="c" * 64,
        expires_at=_NOW + timedelta(days=1),
        revoked_at=_NOW,
    )
    db_session.add_all([active, expired, revoked])
    await db_session.flush()

    repo = RefreshTokenRepository(db_session)
    assert (await repo.get_active_by_hash(active.token_hash, now=_NOW)) is not None
    assert (await repo.get_active_by_hash(expired.token_hash, now=_NOW)) is None
    assert (await repo.get_active_by_hash(revoked.token_hash, now=_NOW)) is None
    assert (await repo.get_active_by_hash("z" * 64, now=_NOW)) is None

    # active 与 expired 的 revoked_at 均为 NULL，批量吊销影响 2 行。
    assert await repo.revoke_all_for_user(user_id=user.id, now=_NOW) == 2
    assert (await repo.get_active_by_hash(active.token_hash, now=_NOW)) is None


@pytest.mark.integration
async def test_password_reset_token_filters_against_real_db(db_session: AsyncSession) -> None:
    """一次性令牌：已用 / 过期 / 不存在均返回 None；mark_used 后立刻失效。"""
    user = _user("reset-filter@example.com")
    db_session.add(user)
    await db_session.flush()

    active = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash="d" * 64,
        expires_at=_NOW + timedelta(hours=1),
    )
    used = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash="e" * 64,
        expires_at=_NOW + timedelta(hours=1),
        used_at=_NOW,
    )
    expired = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash="f" * 64,
        expires_at=_NOW - timedelta(seconds=1),
    )
    db_session.add_all([active, used, expired])
    await db_session.flush()

    repo = PasswordResetTokenRepository(db_session)
    assert (await repo.get_active_by_hash(active.token_hash, now=_NOW)) is not None
    assert (await repo.get_active_by_hash(used.token_hash, now=_NOW)) is None
    assert (await repo.get_active_by_hash(expired.token_hash, now=_NOW)) is None
    assert (await repo.get_active_by_hash("z" * 64, now=_NOW)) is None

    await repo.mark_used(active, now=_NOW)
    assert (await repo.get_active_by_hash(active.token_hash, now=_NOW)) is None
