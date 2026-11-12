# ruff: noqa: S105, S106, S107
# 本文件使用伪造口令验证重置流程，非真实凭据。
"""M1-T06：密码重置服务（`CONTRACTS §9` 行为 6–7）单元测试。

替身仓储 + 真 `InMemoryMailSender` + 真 argon2 驱动**真实**服务代码：
断言「令牌只以摘要落库、明文只出现在邮件正文」「一次性」「改密吊销全部 refresh」。
真实 SQL 行为（`used_at` 落库、并发）由 `tests/integration/` 下的用例覆盖。
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import fakeredis
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.errors import Unauthenticated
from app.modules.identity.adapters.mail import InMemoryMailSender, LoggingMailSender
from app.modules.identity.adapters.password_hasher import Argon2PasswordHasher
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.models import PasswordResetToken, User
from app.modules.identity.repo import (
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.modules.identity.schemas import PasswordResetConfirm, PasswordResetRequest
from app.modules.identity.security import hash_opaque_token
from app.modules.identity.service import (
    IdentityService,
    build_identity_service,
    make_mail_sender,
)

# 与 tests/conftest.py 的 FROZEN_AT 对齐
_NOW = datetime(2026, 11, 11, 14, 30, tzinfo=UTC)
_PASSWORD = "Str0ngPassw0rd!"
_NEW_PASSWORD = "N3wStr0ngPassw0rd!"
_TOKEN_LINE = re.compile(r"^[A-Za-z0-9_-]{32,64}$", re.MULTILINE)
_HASHER = Argon2PasswordHasher()


# --------------------------------------------------------------------- 替身


class _FakeSession:
    """只实现 service 用到的三个方法；审计写在 `added` 里供断言。"""

    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: Any) -> None:
        del obj

    def audits(self) -> list[AuditLog]:
        return [obj for obj in self.added if isinstance(obj, AuditLog)]


class _FakeUserRepository:
    def __init__(self, users: list[User] | None = None) -> None:
        self.users = list(users or [])
        self.saved: list[User] = []

    async def get_by_email(self, email: str) -> User | None:
        return next((user for user in self.users if user.email == email), None)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return next((user for user in self.users if user.id == user_id), None)

    async def save(self, user: User) -> None:
        self.saved.append(user)


class _FakeRefreshTokenRepository:
    def __init__(self, active: int = 2) -> None:
        self.active = active
        self.revoked_for: list[uuid.UUID] = []

    async def revoke_all_for_user(self, *, user_id: uuid.UUID, now: datetime) -> int:
        del now
        self.revoked_for.append(user_id)
        return self.active


class _FakeResetTokenRepository:
    """内存版重置令牌仓储，行为对齐 `PasswordResetTokenRepository`。"""

    def __init__(self) -> None:
        self.created: list[PasswordResetToken] = []
        self.used: list[PasswordResetToken] = []

    async def create(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> PasswordResetToken:
        token = PasswordResetToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        token.id = uuid.uuid4()
        token.used_at = None
        self.created.append(token)
        return token

    async def get_active_by_hash(
        self, token_hash: str, *, now: datetime
    ) -> PasswordResetToken | None:
        for token in self.created:
            if token.token_hash != token_hash:
                continue
            if token.used_at is not None or token.expires_at <= now:
                return None
            return token
        return None

    async def mark_used(self, token: PasswordResetToken, *, now: datetime) -> None:
        token.used_at = now
        self.used.append(token)


def _make_user(
    *,
    email: str = "neo@example.com",
    status: str = UserStatus.ACTIVE.value,
) -> User:
    user = User(email=email, password_hash=_HASHER.hash(_PASSWORD), settings={})
    user.id = uuid.uuid4()
    user.role = UserRole.USER.value
    user.status = status
    user.created_at = _NOW
    return user


def _build(
    settings: Settings,
    *,
    users: list[User] | None = None,
    mail: InMemoryMailSender | None = None,
) -> tuple[
    IdentityService,
    _FakeUserRepository,
    _FakeResetTokenRepository,
    _FakeRefreshTokenRepository,
    _FakeSession,
]:
    fake_session = _FakeSession()
    sender = mail if mail is not None else InMemoryMailSender()
    service = build_identity_service(
        session=cast(AsyncSession, fake_session),
        settings=settings,
        redis=fakeredis.FakeAsyncRedis(decode_responses=True),
        mail=sender,
    )
    user_repo = _FakeUserRepository(users)
    reset_repo = _FakeResetTokenRepository()
    refresh_repo = _FakeRefreshTokenRepository()
    service._users = cast(UserRepository, user_repo)
    service._reset_tokens = cast(PasswordResetTokenRepository, reset_repo)
    service._refresh_tokens = cast(RefreshTokenRepository, refresh_repo)
    return service, user_repo, reset_repo, refresh_repo, fake_session


def _token_from(message: Any) -> str:
    """从邮件正文取令牌（独占一行，便于调用方解析）。"""
    matches = _TOKEN_LINE.findall(message.body)
    assert len(matches) == 1, f"邮件正文应恰好含一个令牌行，实际 {matches}"
    return str(matches[0])


@pytest.fixture(autouse=True)
def _freeze_clock(frozen_clock: Any) -> None:
    del frozen_clock


# --------------------------------------------------------------------- 用例


async def test_request_stores_digest_and_mails_plaintext(settings: Settings) -> None:
    user = _make_user()
    mail = InMemoryMailSender()
    service, _, resets, _, session = _build(settings, users=[user], mail=mail)

    await service.request_password_reset(
        PasswordResetRequest(email="  Neo@Example.COM "), ip="10.0.0.7"
    )

    assert len(mail.messages) == 1
    message = mail.messages[0]
    assert message.to == "neo@example.com"
    assert message.subject == "密码重置令牌"

    token = _token_from(message)
    stored = resets.created[0]
    assert stored.token_hash == hash_opaque_token(token)
    assert token not in stored.token_hash
    assert stored.user_id == user.id
    assert stored.expires_at == _NOW + timedelta(seconds=settings.password_reset_ttl_seconds)

    audits = session.audits()
    assert [row.action for row in audits] == ["auth.password_reset_requested"]
    assert audits[0].user_id == user.id
    assert audits[0].ip == "10.0.0.7"
    assert "neo@example.com" not in str(audits[0].detail)
    assert token not in str(audits[0].detail)


async def test_request_for_unknown_email_is_silent(settings: Settings) -> None:
    mail = InMemoryMailSender()
    service, _, resets, _, session = _build(settings, mail=mail)

    await service.request_password_reset(PasswordResetRequest(email="ghost@example.com"), ip=None)

    assert mail.messages == []
    assert resets.created == []
    assert session.audits() == []


async def test_request_for_disabled_account_is_silent(settings: Settings) -> None:
    """禁用账号与不存在账号表现一致，避免通过重置接口探测账号状态。"""
    user = _make_user(email="off@example.com", status=UserStatus.DISABLED.value)
    mail = InMemoryMailSender()
    service, _, resets, _, session = _build(settings, users=[user], mail=mail)

    await service.request_password_reset(PasswordResetRequest(email="off@example.com"), ip=None)

    assert mail.messages == []
    assert resets.created == []
    assert session.audits() == []


async def test_confirm_rotates_password_revokes_refresh_and_audits(
    settings: Settings,
) -> None:
    user = _make_user()
    mail = InMemoryMailSender()
    service, users, resets, refresh, session = _build(settings, users=[user], mail=mail)
    await service.request_password_reset(PasswordResetRequest(email=user.email), ip=None)
    token = _token_from(mail.messages[0])

    await service.confirm_password_reset(
        PasswordResetConfirm(token=token, new_password=_NEW_PASSWORD), ip="10.0.0.7"
    )

    record = resets.created[0]
    assert record.used_at == _NOW
    assert refresh.revoked_for == [user.id]
    assert users.saved == [user]
    assert _HASHER.verify(_NEW_PASSWORD, user.password_hash) is True
    assert _HASHER.verify(_PASSWORD, user.password_hash) is False

    audits = session.audits()
    assert [row.action for row in audits] == [
        "auth.password_reset_requested",
        "auth.password_changed",
    ]
    changed = audits[-1]
    assert changed.user_id == user.id
    assert changed.ip == "10.0.0.7"
    assert "refresh_tokens_revoked" in str(changed.detail)
    assert token not in str(changed.detail)
    assert _NEW_PASSWORD not in str(changed.detail)


async def test_confirm_rejects_unknown_digest(settings: Settings) -> None:
    mail = InMemoryMailSender()
    service, _, resets, refresh, session = _build(settings, mail=mail)

    with pytest.raises(Unauthenticated):
        await service.confirm_password_reset(
            PasswordResetConfirm(
                token="forged-token-value-0000000000000000", new_password=_NEW_PASSWORD
            ),
            ip=None,
        )

    assert resets.used == []
    assert refresh.revoked_for == []
    assert session.audits() == []


async def test_confirm_rejects_reused_token(settings: Settings) -> None:
    """一次性：第二次提交同一令牌一律 401，且不会再次改密。"""
    user = _make_user()
    mail = InMemoryMailSender()
    service, users, resets, _, _ = _build(settings, users=[user], mail=mail)
    await service.request_password_reset(PasswordResetRequest(email=user.email), ip=None)
    token = _token_from(mail.messages[0])

    request = PasswordResetConfirm(token=token, new_password=_NEW_PASSWORD)
    await service.confirm_password_reset(request, ip=None)
    users.saved.clear()

    with pytest.raises(Unauthenticated):
        await service.confirm_password_reset(request, ip=None)

    assert users.saved == []
    assert len(resets.used) == 1


async def test_confirm_rejects_expired_token(settings: Settings, frozen_clock: FrozenClock) -> None:
    user = _make_user()
    mail = InMemoryMailSender()
    service, _, resets, refresh, session = _build(settings, users=[user], mail=mail)
    await service.request_password_reset(PasswordResetRequest(email=user.email), ip=None)
    token = _token_from(mail.messages[0])

    frozen_clock.advance(timedelta(seconds=settings.password_reset_ttl_seconds + 1))

    with pytest.raises(Unauthenticated):
        await service.confirm_password_reset(
            PasswordResetConfirm(token=token, new_password=_NEW_PASSWORD), ip=None
        )

    assert resets.used == []
    assert refresh.revoked_for == []
    assert [row.action for row in session.audits()] == ["auth.password_reset_requested"]


async def test_confirm_rejects_disabled_user(settings: Settings) -> None:
    """令牌有效但账号被禁用时同样 401，且不写 `used_at`、不改密、不吊销。"""
    user = _make_user()
    mail = InMemoryMailSender()
    service, _, resets, refresh, _ = _build(settings, users=[user], mail=mail)
    await service.request_password_reset(PasswordResetRequest(email=user.email), ip=None)
    token = _token_from(mail.messages[0])

    user.status = UserStatus.DISABLED.value
    with pytest.raises(Unauthenticated):
        await service.confirm_password_reset(
            PasswordResetConfirm(token=token, new_password=_NEW_PASSWORD), ip=None
        )

    assert resets.used == []
    assert refresh.revoked_for == []


def test_make_mail_sender_is_env_driven(settings: Settings) -> None:
    """ci 用内存实现；local 与其它环境用日志实现（后者见 T06 偏差 D2）。"""
    ci_settings = settings.model_copy(update={"app_env": "ci"})
    assert isinstance(make_mail_sender(ci_settings), InMemoryMailSender)

    for env in ("local", "staging", "production"):
        sender = make_mail_sender(settings.model_copy(update={"app_env": env}))
        assert isinstance(sender, LoggingMailSender)
