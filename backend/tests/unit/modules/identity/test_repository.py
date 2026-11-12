"""M1-T02：`CONTRACTS §7` 仓储签名、租户谓词与令牌过滤的纯单元验证。

用 `AsyncMock(spec=AsyncSession)` 检查发出的 SQL 与返回值，不依赖真实数据库；
真实 PG 下的隔离/过滤行为由 `tests/integration/modules/identity/test_tenant_isolation_db.py` 覆盖。
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import AiUsage, PasswordResetToken, RefreshToken, User
from app.modules.identity.repo import (
    AiUsageRepository,
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)

_NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
# 测试用占位哈希（非真实凭据），用变量而非字面量以避免 ruff S105/S106 误报。
_TEST_HASH = "argon2$test-hash"


def _result(
    *, scalar: Any = None, scalars: Sequence[Any] = (), rowcount: int = 0, count: Any = 0
) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalar_one.return_value = count
    result.scalars.return_value.all.return_value = list(scalars)
    result.rowcount = rowcount
    return result


def _session(*, result: MagicMock | None = None) -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result if result is not None else _result()
    return session


def _sql(session: AsyncMock, *, call: int = 0) -> str:
    stmt = session.execute.await_args_list[call].args[0]
    return str(stmt)


# --- TenantRepository -------------------------------------------------------


def test_missing_user_id_raises_value_error() -> None:
    repo = AiUsageRepository(_session(), user_id=cast(uuid.UUID, None))
    with pytest.raises(ValueError, match="user_id"):
        repo._user_id()
    with pytest.raises(ValueError, match="user_id"):
        repo._scoped(select(AiUsage))


def test_scoped_statement_contains_user_id_predicate() -> None:
    tenant = uuid.uuid4()
    repo = AiUsageRepository(_session(), user_id=tenant)
    stmt = repo._scoped(select(AiUsage))
    sql = str(stmt)
    assert "ai_usage.user_id" in sql
    assert "WHERE" in sql
    assert tenant in stmt.compile().params.values()


def test_two_tenants_bind_different_ids() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    repo_a = AiUsageRepository(_session(), user_id=first)
    repo_b = AiUsageRepository(_session(), user_id=second)
    params_a = repo_a._scoped(select(AiUsage)).compile().params
    params_b = repo_b._scoped(select(AiUsage)).compile().params
    assert first in params_a.values()
    assert second in params_b.values()
    assert first not in params_b.values()


async def test_get_by_id_always_scoped() -> None:
    tenant, entity_id = uuid.uuid4(), uuid.uuid4()
    sentinel = object()
    session = _session(result=_result(scalar=sentinel))
    repo = AiUsageRepository(session, user_id=tenant)
    assert await repo.get_by_id(entity_id) is sentinel
    sql = _sql(session)
    assert "ai_usage.user_id" in sql
    assert "ai_usage.id" in sql
    params = session.execute.await_args_list[0].args[0].compile().params
    assert tenant in params.values()
    assert entity_id in params.values()


async def test_get_by_id_returns_none_when_other_tenant() -> None:
    session = _session(result=_result(scalar=None))
    repo = AiUsageRepository(session, user_id=uuid.uuid4())
    assert await repo.get_by_id(uuid.uuid4()) is None


async def test_list_for_user_applies_limit_offset_and_scope() -> None:
    rows = [object(), object()]
    session = _session(result=_result(scalars=rows))
    repo = AiUsageRepository(session, user_id=uuid.uuid4())
    assert list(await repo.list_for_user(limit=7, offset=3)) == rows
    sql = _sql(session)
    assert "ai_usage.user_id" in sql
    assert "LIMIT" in sql
    assert "OFFSET" in sql


async def test_ai_usage_get_for_date_is_scoped() -> None:
    sentinel = object()
    session = _session(result=_result(scalar=sentinel))
    repo = AiUsageRepository(session, user_id=uuid.uuid4())
    assert await repo.get_for_date(usage_date=_NOW.date()) is sentinel
    sql = _sql(session)
    assert "ai_usage.usage_date" in sql
    assert "ai_usage.user_id" in sql


# --- UserRepository ---------------------------------------------------------


async def test_user_create_flushes_and_refreshes() -> None:
    session = _session()
    repo = UserRepository(session)
    user = await repo.create(
        email="neo@example.com", password_hash=_TEST_HASH, settings={"language": "en-US"}
    )
    assert isinstance(user, User)
    assert user.email == "neo@example.com"
    assert user.password_hash == _TEST_HASH
    assert user.settings == {"language": "en-US"}
    session.add.assert_called_once_with(user)
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(user)


async def test_user_get_by_email_and_get_by_id() -> None:
    sentinel = object()
    session = _session(result=_result(scalar=sentinel))
    repo = UserRepository(session)
    assert await repo.get_by_email("neo@example.com") is sentinel
    assert "users.email" in _sql(session)
    user_id = uuid.uuid4()
    session.get.return_value = sentinel
    assert await repo.get_by_id(user_id) is sentinel
    session.get.assert_awaited_once_with(User, user_id)


async def test_user_save_flushes() -> None:
    session = _session()
    repo = UserRepository(session)
    user = User(email="neo@example.com", password_hash=_TEST_HASH)
    await repo.save(user)
    session.add.assert_called_once_with(user)
    session.flush.assert_awaited_once()


async def test_user_list_paginated() -> None:
    users = [object(), object()]
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [_result(count=12), _result(scalars=users)]
    repo = UserRepository(session)
    items, total = await repo.list_paginated(page=2, page_size=5)
    assert list(items) == users
    assert total == 12
    assert session.execute.await_count == 2
    assert "LIMIT" in _sql(session, call=1)
    assert "OFFSET" in _sql(session, call=1)


async def test_user_list_paginated_handles_zero_count() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [_result(count=0), _result(scalars=[])]
    repo = UserRepository(session)
    items, total = await repo.list_paginated(page=1, page_size=20)
    assert list(items) == []
    assert total == 0


# --- RefreshTokenRepository -------------------------------------------------


async def test_refresh_token_create() -> None:
    session = _session()
    repo = RefreshTokenRepository(session)
    tenant = uuid.uuid4()
    token = await repo.create(user_id=tenant, token_hash="a" * 64, expires_at=_NOW)
    assert isinstance(token, RefreshToken)
    assert token.user_id == tenant
    assert token.token_hash == "a" * 64
    assert token.expires_at == _NOW
    session.flush.assert_awaited_once()


async def test_refresh_token_active_filter_sql() -> None:
    sentinel = object()
    session = _session(result=_result(scalar=sentinel))
    repo = RefreshTokenRepository(session)
    assert await repo.get_active_by_hash("b" * 64, now=_NOW) is sentinel
    sql = _sql(session)
    assert "refresh_tokens.token_hash" in sql
    assert "revoked_at IS NULL" in sql
    assert "expires_at >" in sql


async def test_refresh_token_inactive_returns_none() -> None:
    session = _session(result=_result(scalar=None))
    assert await RefreshTokenRepository(session).get_active_by_hash("c" * 64, now=_NOW) is None


async def test_refresh_token_revoke() -> None:
    session = _session()
    token = RefreshToken(user_id=uuid.uuid4(), token_hash="d" * 64, expires_at=_NOW)
    await RefreshTokenRepository(session).revoke(token, now=_NOW)
    assert token.revoked_at == _NOW
    session.flush.assert_awaited_once()


@pytest.mark.parametrize("affected,expected", [(3, 3), (0, 0)])
async def test_refresh_token_revoke_all_for_user(affected: int, expected: int) -> None:
    tenant = uuid.uuid4()
    session = _session(result=_result(rowcount=affected))
    repo = RefreshTokenRepository(session)
    assert await repo.revoke_all_for_user(user_id=tenant, now=_NOW) == expected
    sql = _sql(session)
    assert "refresh_tokens.user_id" in sql
    assert "revoked_at IS NULL" in sql
    assert tenant in session.execute.await_args_list[0].args[0].compile().params.values()


# --- PasswordResetTokenRepository -------------------------------------------


async def test_password_reset_token_create() -> None:
    session = _session()
    repo = PasswordResetTokenRepository(session)
    tenant = uuid.uuid4()
    token = await repo.create(user_id=tenant, token_hash="e" * 64, expires_at=_NOW)
    assert isinstance(token, PasswordResetToken)
    assert token.user_id == tenant
    assert token.used_at is None
    session.flush.assert_awaited_once()


async def test_password_reset_token_active_filter_sql() -> None:
    sentinel = object()
    session = _session(result=_result(scalar=sentinel))
    repo = PasswordResetTokenRepository(session)
    assert await repo.get_active_by_hash("f" * 64, now=_NOW) is sentinel
    sql = _sql(session)
    assert "password_reset_tokens.token_hash" in sql
    assert "used_at IS NULL" in sql
    assert "expires_at >" in sql


async def test_password_reset_token_inactive_returns_none() -> None:
    session = _session(result=_result(scalar=None))
    assert (
        await PasswordResetTokenRepository(session).get_active_by_hash("g" * 64, now=_NOW) is None
    )


async def test_password_reset_token_mark_used() -> None:
    session = _session()
    token = PasswordResetToken(user_id=uuid.uuid4(), token_hash="h" * 64, expires_at=_NOW)
    await PasswordResetTokenRepository(session).mark_used(token, now=_NOW)
    assert token.used_at == _NOW
    session.flush.assert_awaited_once()
