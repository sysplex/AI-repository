# ruff: noqa: S105, S106, S107
# 本文件使用伪造口令验证认证行为，非真实凭据。
"""M1-T04：`IdentityService` 主链路（注册/登录/刷新/登出/access 校验）单元测试。

这里用替身仓储 + fakeredis 驱动**真实**的服务代码（含 argon2 与 JWT 适配器），
不伪造 service 内部逻辑；真实 SQL 行为由 `tests/integration/modules/identity/`
下的集成用例在 CI 的 Postgres 上覆盖。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import fakeredis
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import RateLimited, StateConflict, TokenExpired, Unauthenticated
from app.modules.identity.adapters.password_hasher import Argon2PasswordHasher
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.models import RefreshToken, User
from app.modules.identity.repo import RefreshTokenRepository, UserRepository
from app.modules.identity.schemas import (
    AuthenticatedUser,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
)
from app.modules.identity.security import hash_opaque_token
from app.modules.identity.service import (
    IdentityService,
    LoginRateLimiter,
    build_identity_service,
    normalize_email,
)

# 与 tests/conftest.py 的 FROZEN_AT 对齐：服务内部取 get_clock().now()
_NOW = datetime(2026, 11, 11, 14, 30, tzinfo=UTC)
_PASSWORD = "Str0ngPassw0rd!"
_TEST_HASH = "argon2$test-hash"


# --------------------------------------------------------------------- 替身


class _FakeSession:
    """只实现 service 用到的四个方法：add / flush / refresh / execute。"""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.refresh_record: RefreshToken | None = None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: Any) -> None:
        del obj

    async def execute(self, statement: Any) -> Any:
        del statement
        record = self.refresh_record
        return type(
            "_Result",
            (),
            {"scalar_one_or_none": lambda self: record},
        )()


class _FakeUserRepository:
    def __init__(self, users: list[User] | None = None) -> None:
        self.users = list(users or [])
        self.created: list[User] = []

    async def get_by_email(self, email: str) -> User | None:
        return next((user for user in self.users if user.email == email), None)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return next((user for user in self.users if user.id == user_id), None)

    async def create(self, *, email: str, password_hash: str, settings: dict[str, Any]) -> User:
        user = _make_user(email=email, password_hash=password_hash, settings=settings)
        self.created.append(user)
        self.users.append(user)
        return user


class _FakeRefreshTokenRepository:
    def __init__(self) -> None:
        self.created: list[RefreshToken] = []
        self.revoked: list[RefreshToken] = []

    async def create(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        token = _make_refresh(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.created.append(token)
        return token

    async def revoke(self, token: RefreshToken, *, now: datetime) -> None:
        token.revoked_at = now
        self.revoked.append(token)


def _make_user(
    *,
    email: str = "neo@example.com",
    password_hash: str = _TEST_HASH,
    settings: dict[str, Any] | None = None,
    role: str = UserRole.USER.value,
    status: str = UserStatus.ACTIVE.value,
) -> User:
    """构造未持久化的 ORM 对象；字段足够喂给 `UserPublic.model_validate`。"""
    user = User(email=email, password_hash=password_hash, settings=settings or {})
    user.id = uuid.uuid4()
    user.role = role
    user.status = status
    user.created_at = _NOW
    return user


def _make_refresh(
    *,
    user_id: uuid.UUID,
    token_hash: str = "digest",
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> RefreshToken:
    token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at or (_NOW + timedelta(days=1)),
    )
    token.id = uuid.uuid4()
    token.revoked_at = revoked_at
    return token


def _build(
    settings: Settings,
    *,
    users: _FakeUserRepository | None = None,
    tokens: _FakeRefreshTokenRepository | None = None,
    session: _FakeSession | None = None,
) -> tuple[IdentityService, _FakeUserRepository, _FakeRefreshTokenRepository, _FakeSession]:
    fake_session = session or _FakeSession()
    service = build_identity_service(
        session=cast(AsyncSession, fake_session),
        settings=settings,
        redis=fakeredis.FakeAsyncRedis(decode_responses=True),
    )
    user_repo = users or _FakeUserRepository()
    token_repo = tokens or _FakeRefreshTokenRepository()
    service._users = cast(UserRepository, user_repo)
    service._refresh_tokens = cast(RefreshTokenRepository, token_repo)
    return service, user_repo, token_repo, fake_session


# --------------------------------------------------------------------- 用例


def test_normalize_email_strips_and_lowercases() -> None:
    assert normalize_email("  Neo@Example.COM ") == "neo@example.com"


def test_rate_limiter_uses_digested_account_key_and_plain_ip_key() -> None:
    limiter = LoginRateLimiter(
        fakeredis.FakeAsyncRedis(decode_responses=True), max_attempts=3, window_seconds=60
    )
    account_key, ip_key = limiter.keys(email="Neo@Example.com", ip="10.0.0.1")
    assert account_key.startswith("login:fail:account:")
    assert "neo@example.com" not in account_key
    assert account_key == f"login:fail:account:{hash_opaque_token('Neo@Example.com')[:12]}"
    assert ip_key == "login:fail:ip:10.0.0.1"


def test_rate_limiter_rejects_non_positive_threshold() -> None:
    with pytest.raises(ValueError):
        LoginRateLimiter(
            fakeredis.FakeAsyncRedis(decode_responses=True), max_attempts=0, window_seconds=60
        )


async def test_rate_limiter_blocks_after_max_and_sets_window() -> None:
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    limiter = LoginRateLimiter(redis, max_attempts=2, window_seconds=30)
    await limiter.ensure_allowed(email="a@example.com", ip="1.1.1.1")

    await limiter.register_failure(email="a@example.com", ip="1.1.1.1")
    assert 0 < int(await redis.ttl("login:fail:ip:1.1.1.1")) <= 30
    await limiter.register_failure(email="a@example.com", ip="1.1.1.1")

    with pytest.raises(RateLimited) as exc:
        await limiter.ensure_allowed(email="a@example.com", ip="1.1.1.1")
    assert exc.value.details["retry_after"] >= 1

    await limiter.reset(email="a@example.com", ip="1.1.1.1")
    await limiter.ensure_allowed(email="a@example.com", ip="1.1.1.1")


async def test_register_rejects_duplicate_email(settings: Settings) -> None:
    service, users, _, _ = _build(
        settings, users=_FakeUserRepository([_make_user(email="neo@example.com")])
    )
    with pytest.raises(StateConflict):
        await service.register(
            RegisterRequest(email="NEO@example.com", password=_PASSWORD), ip="10.0.0.1"
        )
    assert users.created == []


async def test_register_creates_user_and_audits_digest_only(
    settings: Settings, frozen_clock: Any
) -> None:
    del frozen_clock
    service, users, _, session = _build(settings)
    public = await service.register(
        RegisterRequest(email="  Neo@Example.com ", password=_PASSWORD), ip="10.0.0.1"
    )
    assert public.email == "neo@example.com"
    assert public.role is UserRole.USER
    assert public.status is UserStatus.ACTIVE
    assert users.created[0].email == "neo@example.com"
    assert users.created[0].password_hash.startswith("$argon2id$")

    audit = [obj for obj in session.added if getattr(obj, "action", "").startswith("auth.")]
    assert [entry.action for entry in audit] == ["auth.register"]
    detail = audit[0].detail
    assert "neo@example.com" not in str(detail)
    assert "password" not in str(detail).lower()


async def test_login_success_issues_pair_and_clears_limit(
    settings: Settings, frozen_clock: Any
) -> None:
    del frozen_clock
    hashed = Argon2PasswordHasher().hash(_PASSWORD)
    user = _make_user(password_hash=hashed)
    service, _, tokens, session = _build(settings, users=_FakeUserRepository([user]))

    pair = await service.login(LoginRequest(email=user.email, password=_PASSWORD), ip="10.0.0.1")

    assert pair.token_type == "bearer"
    assert pair.expires_in == settings.access_token_ttl_seconds
    assert len(tokens.created) == 1
    assert tokens.created[0].token_hash == hash_opaque_token(pair.refresh_token)
    assert pair.refresh_token not in tokens.created[0].token_hash
    claims = service._codec.decode_access(pair.access_token, now=_NOW)
    assert claims.user_id == user.id
    assert claims.role is UserRole.USER

    actions = [obj.action for obj in session.added if hasattr(obj, "action")]
    assert "auth.login" in actions


async def test_login_unknown_user_and_wrong_password_share_one_message(
    settings: Settings, frozen_clock: Any
) -> None:
    del frozen_clock
    user = _make_user(password_hash=Argon2PasswordHasher().hash(_PASSWORD))
    service, _, _, _ = _build(settings, users=_FakeUserRepository([user]))

    with pytest.raises(Unauthenticated) as unknown:
        await service.login(LoginRequest(email="ghost@example.com", password=_PASSWORD), ip=None)
    with pytest.raises(Unauthenticated) as wrong:
        await service.login(LoginRequest(email=user.email, password="Wr0ngPassword!"), ip=None)

    assert str(unknown.value) == str(wrong.value)
    assert unknown.value.code is wrong.value.code


async def test_login_disabled_account_is_rejected(settings: Settings, frozen_clock: Any) -> None:
    del frozen_clock
    user = _make_user(
        password_hash=Argon2PasswordHasher().hash(_PASSWORD), status=UserStatus.DISABLED.value
    )
    service, _, _, _ = _build(settings, users=_FakeUserRepository([user]))
    with pytest.raises(Unauthenticated):
        await service.login(LoginRequest(email=user.email, password=_PASSWORD), ip=None)


async def test_login_counts_failures_and_blocks_at_threshold(
    settings: Settings, frozen_clock: Any
) -> None:
    del frozen_clock
    user = _make_user(password_hash=Argon2PasswordHasher().hash(_PASSWORD))
    service, _, _, _ = _build(settings, users=_FakeUserRepository([user]))

    for _ in range(settings.login_rate_limit_max):
        with pytest.raises(Unauthenticated):
            await service.login(
                LoginRequest(email=user.email, password="Wr0ngPassword!"), ip="2.2.2.2"
            )

    with pytest.raises(RateLimited) as exc:
        await service.login(LoginRequest(email=user.email, password=_PASSWORD), ip="2.2.2.2")
    assert exc.value.details["retry_after"] >= 1


async def test_refresh_rotates_and_revokes_old_token(settings: Settings, frozen_clock: Any) -> None:
    del frozen_clock
    user = _make_user()
    service, _, _, session = _build(settings, users=_FakeUserRepository([user]))

    plain = "plain-refresh-token"
    record = _make_refresh(user_id=user.id, token_hash=hash_opaque_token(plain))
    with_token = _FakeRefreshTokenRepository()
    service._refresh_tokens = cast(RefreshTokenRepository, with_token)
    session.refresh_record = record

    pair = await service.refresh(RefreshRequest(refresh_token=plain), ip="3.3.3.3")

    assert pair.refresh_token != plain
    assert record.revoked_at == _NOW
    assert len(with_token.created) == 1


async def test_refresh_rejects_missing_revoked_and_expired(
    settings: Settings, frozen_clock: Any
) -> None:
    del frozen_clock
    user = _make_user()
    service, _, _, session = _build(settings, users=_FakeUserRepository([user]))

    session.refresh_record = None
    with pytest.raises(Unauthenticated):
        await service.refresh(RefreshRequest(refresh_token="nope"), ip=None)

    session.refresh_record = _make_refresh(user_id=user.id, revoked_at=_NOW)
    with pytest.raises(Unauthenticated):
        await service.refresh(RefreshRequest(refresh_token="revoked"), ip=None)

    session.refresh_record = _make_refresh(user_id=user.id, expires_at=_NOW)
    with pytest.raises(TokenExpired):
        await service.refresh(RefreshRequest(refresh_token="expired"), ip=None)


async def test_refresh_rejects_disabled_user(settings: Settings, frozen_clock: Any) -> None:
    del frozen_clock
    user = _make_user(status=UserStatus.DISABLED.value)
    service, _, _, session = _build(settings, users=_FakeUserRepository([user]))
    session.refresh_record = _make_refresh(user_id=user.id)
    with pytest.raises(Unauthenticated):
        await service.refresh(RefreshRequest(refresh_token="token"), ip=None)


async def test_logout_revokes_and_is_idempotent(settings: Settings, frozen_clock: Any) -> None:
    del frozen_clock
    user = _make_user()
    service, _, tokens, session = _build(settings, users=_FakeUserRepository([user]))
    record = _make_refresh(user_id=user.id, token_hash=hash_opaque_token("plain"))
    session.refresh_record = record
    current = AuthenticatedUser.model_validate(user)

    await service.logout(LogoutRequest(refresh_token="plain"), user=current, ip="4.4.4.4")
    assert record.revoked_at == _NOW
    assert tokens.revoked == [record]

    await service.logout(LogoutRequest(refresh_token="plain"), user=current, ip="4.4.4.4")
    assert tokens.revoked == [record]  # 幂等：已吊销不再重复写
    actions = [obj.action for obj in session.added if hasattr(obj, "action")]
    assert actions.count("auth.logout") == 2


async def test_authenticate_access_returns_user(settings: Settings, frozen_clock: Any) -> None:
    del frozen_clock
    user = _make_user(role=UserRole.ADMIN.value)
    service, _, _, _ = _build(settings, users=_FakeUserRepository([user]))
    token = service._codec.issue_access(
        user_id=user.id, role=UserRole.ADMIN, now=_NOW, ttl_seconds=900
    )
    authenticated = await service.authenticate_access_token(token)
    assert authenticated.id == user.id
    assert authenticated.role is UserRole.ADMIN


async def test_authenticate_access_rejects_role_downgrade_and_disabled(
    settings: Settings, frozen_clock: Any
) -> None:
    del frozen_clock
    user = _make_user()  # 实际角色 user
    service, _, _, _ = _build(settings, users=_FakeUserRepository([user]))
    elevated = service._codec.issue_access(
        user_id=user.id, role=UserRole.ADMIN, now=_NOW, ttl_seconds=900
    )
    with pytest.raises(Unauthenticated):
        await service.authenticate_access_token(elevated)

    user.status = UserStatus.DISABLED.value
    plain = service._codec.issue_access(
        user_id=user.id, role=UserRole.USER, now=_NOW, ttl_seconds=900
    )
    with pytest.raises(Unauthenticated):
        await service.authenticate_access_token(plain)


async def test_authenticate_access_rejects_expired_and_unknown_user(
    settings: Settings, frozen_clock: Any
) -> None:
    del frozen_clock
    service, _, _, _ = _build(settings)
    issued = service._codec.issue_access(
        user_id=uuid.uuid4(),
        role=UserRole.USER,
        now=_NOW - timedelta(seconds=10),
        ttl_seconds=1,
    )
    with pytest.raises(TokenExpired):
        await service.authenticate_access_token(issued)

    live = service._codec.issue_access(
        user_id=uuid.uuid4(), role=UserRole.USER, now=_NOW, ttl_seconds=900
    )
    with pytest.raises(Unauthenticated):
        await service.authenticate_access_token(live)


# ----------------------------------------------------------------- 路由依赖


def test_bearer_token_parsing() -> None:
    """`Authorization` 解析：大小写不敏感、容忍多余空格、其余一律 401。"""
    from fastapi import Request

    from app.api.deps import bearer_token

    def _request(headers: dict[str, str]) -> Request:
        return cast(Request, _FakeRequest(headers))

    assert bearer_token(_request({"Authorization": "Bearer abc"})) == "abc"
    assert bearer_token(_request({"Authorization": "bearer   abc  "})) == "abc"
    for headers in (
        {},
        {"Authorization": "Token abc"},
        {"Authorization": "Bearer    "},
        {"Authorization": "abc"},
    ):
        with pytest.raises(Unauthenticated):
            bearer_token(_request(headers))


def test_client_ip_prefers_socket_peer() -> None:
    """只取 `Request.client.host`，不读 `X-Forwarded-For`（可由客户端伪造）。"""
    from fastapi import Request

    from app.api.deps import client_ip

    with_peer = cast(Request, _FakeRequest({}, client=type("_C", (), {"host": "10.0.0.5"})()))
    assert client_ip(with_peer) == "10.0.0.5"
    assert client_ip(cast(Request, _FakeRequest({}, client=None))) is None


class _FakeRequest:
    """只带 `headers` / `client` 的请求替身，避免为解析函数构造真实 ASGI scope。"""

    def __init__(self, headers: dict[str, str], *, client: Any = None) -> None:
        self.headers = headers
        self.client = client
