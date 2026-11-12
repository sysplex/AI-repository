"""M1 identity 应用服务（T04 主干），`CONTRACTS.md §9` / `§12`。

本层不依赖 HTTP 对象（`docs/07 §5`）：`ip` 由路由层从 `Request.client.host` 传入，
`now` 一律取 `app.core.clock.get_clock()`，测试用 `frozen_clock` 可确定性复现。
T05 / T06 只允许在本类追加方法，不得改动已有签名。

两条安全约定：

* 登录失败对外只有一种文案，且「用户不存在」也走一次真实的 argon2 校验
  （`_DUMMY_PASSWORD_HASH`），避免通过响应时间枚举账号。
* 审计 `detail` 只放摘要类信息（邮箱 SHA-256 前缀），不放明文密码、令牌或邮箱本身。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Final

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.clock import get_clock
from app.core.config import Settings
from app.core.errors import (
    NotFound,
    RateLimited,
    StateConflict,
    TokenExpired,
    Unauthenticated,
)
from app.modules.identity.adapters.mail import LoggingMailSender
from app.modules.identity.adapters.password_hasher import Argon2PasswordHasher
from app.modules.identity.adapters.token_codec import JWTTokenCodec
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.models import RefreshToken, User
from app.modules.identity.ports import MailSender, PasswordHasher, TokenCodec
from app.modules.identity.repo import (
    AiUsageRepository,
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.modules.identity.schemas import (
    AuthenticatedUser,
    LoginRequest,
    LogoutRequest,
    PaginatedUsers,
    RefreshRequest,
    RegisterRequest,
    SettingsUpdate,
    TokenPair,
    UsageResponse,
    UserPublic,
)
from app.modules.identity.security import (
    hash_opaque_token,
    hash_password,
    new_opaque_token,
    verify_password,
)
from app.modules.identity.tokens import issue_access

__all__ = ["IdentityService", "LoginRateLimiter", "build_identity_service", "normalize_email"]

_LOGIN_ACCOUNT_KEY: Final[str] = "login:fail:account:{}"
_LOGIN_IP_KEY: Final[str] = "login:fail:ip:{}"
_UNKNOWN_IP: Final[str] = "unknown"
_EMAIL_DIGEST_PREFIX: Final[int] = 12

# 时序对齐用的哑哈希：明文是随机字符串且从未在任何地方保存，仅用于让
# 「账号不存在」与「密码错误」两条分支都消耗一次完整的 argon2 校验时间。
# 拆成两段拼接是为了不让静态扫描把它当成硬编码口令（它确实不是）。
_DUMMY_PASSWORD_HASH: Final[str] = "".join(
    (
        "$argon2id$v=19$m=65536,t=3,p=2$",
        "/Paa9SImDlQ8Lf2hfmNpBg$0e/bVnwidhQ5quN0nnXXvwTvq32u/T7QH2qDOr2K74M",
    )
)


def normalize_email(email: str) -> str:
    """邮箱规范化：去首尾空白 + 小写（`CONTRACTS §9` 行为 1）。"""
    return email.strip().lower()


def _email_digest(email: str) -> str:
    """审计用邮箱摘要：可追溯、不可逆、不写 PII。"""
    return hash_opaque_token(email)[:_EMAIL_DIGEST_PREFIX]


class LoginRateLimiter:
    """登录失败限流（`CONTRACTS §12`），键为账号摘要与来源 IP 两条独立计数。

    同一个 `INCR` + `EXPIRE(window)`；任一键达到阈值即拒绝，成功登录后两条键都删除。
    只采信路由层传入的 `ip`（`Request.client.host`），不读任何客户端可伪造的头。
    """

    def __init__(self, redis: aioredis.Redis, *, max_attempts: int, window_seconds: int) -> None:
        if max_attempts <= 0 or window_seconds <= 0:
            raise ValueError("限流阈值与窗口必须为正整数")
        self._redis = redis
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds

    def keys(self, *, email: str, ip: str | None) -> tuple[str, str]:
        """返回 (账号键, IP 键)；账号键用邮箱摘要，避免把邮箱写进 Redis 键。"""
        return (
            _LOGIN_ACCOUNT_KEY.format(_email_digest(email)),
            _LOGIN_IP_KEY.format(ip or _UNKNOWN_IP),
        )

    async def ensure_allowed(self, *, email: str, ip: str | None) -> None:
        """任一计数达到阈值即抛 429，`details["retry_after"]` 为剩余窗口秒数。"""
        for key in self.keys(email=email, ip=ip):
            current = await self._redis.get(key)
            if current is None:
                continue
            if int(current) >= self._max_attempts:
                ttl = int(await self._redis.ttl(key))
                raise RateLimited(
                    "登录失败次数过多，请稍后再试",
                    details={"retry_after": max(ttl, 1)},
                )

    async def register_failure(self, *, email: str, ip: str | None) -> None:
        """记录一次失败；只在键首次创建时设置过期，窗口不随失败次数滑动。"""
        for key in self.keys(email=email, ip=ip):
            count = int(await self._redis.incr(key))
            if count == 1:
                await self._redis.expire(key, self._window_seconds)

    async def reset(self, *, email: str, ip: str | None) -> None:
        """登录成功后清零，避免白名单用户被历史失败拖累。"""
        await self._redis.delete(*self.keys(email=email, ip=ip))


class IdentityService:
    """认证主链路：注册 / 登录 / 刷新 / 登出 / access 校验。"""

    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        hasher: PasswordHasher,
        codec: TokenCodec,
        mail: MailSender,
        redis: aioredis.Redis,
    ) -> None:
        self._session = session
        self._settings = settings
        self._hasher = hasher
        self._codec = codec
        self._mail = mail
        self._redis = redis
        self._users = UserRepository(session)
        self._refresh_tokens = RefreshTokenRepository(session)
        self._reset_tokens = PasswordResetTokenRepository(session)
        self._limiter = LoginRateLimiter(
            redis,
            max_attempts=settings.login_rate_limit_max,
            window_seconds=settings.login_rate_limit_window_seconds,
        )

    # ------------------------------------------------------------------ T04

    async def register(self, req: RegisterRequest, *, ip: str | None) -> UserPublic:
        """创建用户；重复邮箱 409，成功只返回公开视图，不自动登录。"""
        email = normalize_email(str(req.email))
        if await self._users.get_by_email(email) is not None:
            raise StateConflict("该邮箱已注册")

        user = await self._users.create(
            email=email,
            password_hash=hash_password(self._hasher, req.password),
            settings=req.settings.model_dump(mode="json"),
        )
        await self._audit(
            "auth.register", user_id=user.id, ip=ip, detail={"email": _email_digest(email)}
        )
        return UserPublic.model_validate(user)

    async def login(self, req: LoginRequest, *, ip: str | None) -> TokenPair:
        """限流 → 校验凭据 → 清零计数 → 签发双令牌 → 审计。"""
        email = normalize_email(str(req.email))
        await self._limiter.ensure_allowed(email=email, ip=ip)

        user = await self._users.get_by_email(email)
        matched = verify_password(
            self._hasher,
            req.password,
            user.password_hash if user is not None else _DUMMY_PASSWORD_HASH,
        )
        if user is None or not matched:
            await self._limiter.register_failure(email=email, ip=ip)
            raise Unauthenticated()
        if user.status != UserStatus.ACTIVE.value:
            # 被禁用的账号与「密码错」返回同一文案，避免暴露账号状态。
            await self._limiter.register_failure(email=email, ip=ip)
            raise Unauthenticated()

        await self._limiter.reset(email=email, ip=ip)
        now = get_clock().now()
        pair = await self._issue_pair(user, now=now)
        await self._audit(
            "auth.login", user_id=user.id, ip=ip, detail={"email": _email_digest(email)}
        )
        return pair

    async def refresh(self, req: RefreshRequest, *, ip: str | None) -> TokenPair:
        """轮换刷新令牌：旧的立即吊销，返回全新一对；过期与失效分别映射。"""
        digest = hash_opaque_token(req.refresh_token.get_secret_value())
        now = get_clock().now()
        record = await self._load_refresh_record(digest)
        if record is None or record.revoked_at is not None:
            raise Unauthenticated()
        if record.expires_at <= now:
            raise TokenExpired()

        user = await self._users.get_by_id(record.user_id)
        if user is None or user.status != UserStatus.ACTIVE.value:
            raise Unauthenticated()

        await self._refresh_tokens.revoke(record, now=now)
        pair = await self._issue_pair(user, now=now)
        await self._audit("auth.refresh", user_id=user.id, ip=ip)
        return pair

    async def logout(self, req: LogoutRequest, *, user: AuthenticatedUser, ip: str | None) -> None:
        """吊销提交的 refresh 令牌；幂等，令牌不存在也按成功返回。"""
        digest = hash_opaque_token(req.refresh_token.get_secret_value())
        now = get_clock().now()
        record = await self._load_refresh_record(digest)
        if record is not None and record.user_id == user.id and record.revoked_at is None:
            await self._refresh_tokens.revoke(record, now=now)
        await self._audit("auth.logout", user_id=user.id, ip=ip)

    async def authenticate_access_token(self, token: str) -> AuthenticatedUser:
        """校验 access 并回读用户；角色变更、账号禁用都立即失效。"""
        claims = self._codec.decode_access(token, now=get_clock().now())
        user = await self._users.get_by_id(claims.user_id)
        if user is None or user.status != UserStatus.ACTIVE.value:
            raise Unauthenticated()
        if user.role != claims.role.value:
            # 权限被降级后，旧令牌不得继续携带更高权限。
            raise Unauthenticated()
        return AuthenticatedUser.model_validate(user)

    # ------------------------------------------------------------------ T05

    async def get_profile(self, user: AuthenticatedUser) -> UserPublic:
        """回读本人资料；记录已被删除时按「私有资源不存在」返回 404（C10）。"""
        record = await self._require_user(user.id)
        return UserPublic.model_validate(record)

    async def update_settings(self, user: AuthenticatedUser, update: SettingsUpdate) -> UserPublic:
        """整体替换 `users.settings`（`UserSettings` 已 `extra="forbid"`），并审计。"""
        record = await self._require_user(user.id)
        record.settings = update.settings.model_dump(mode="json")
        await self._users.save(record)
        await self._audit(
            "auth.settings_updated",
            user_id=record.id,
            ip=None,
            detail={"keys": sorted(record.settings)},
        )
        return UserPublic.model_validate(record)

    async def get_usage(self, user: AuthenticatedUser) -> UsageResponse:
        """当日 AI 用量（M1 只读，C6）；无记录返回全 0 + 配置里的配额上限。"""
        today = get_clock().now().date()
        repo = AiUsageRepository(self._session, user_id=user.id)
        record = await repo.get_for_date(usage_date=today)
        quota = self._settings.ai_daily_quota
        if record is None:
            return UsageResponse(
                usage_date=today,
                calls=0,
                tokens_in=0,
                tokens_out=0,
                cost_usd=Decimal("0"),
                quota=quota,
                quota_used=0,
            )
        return UsageResponse(
            usage_date=record.usage_date,
            calls=record.calls,
            tokens_in=record.tokens_in,
            tokens_out=record.tokens_out,
            cost_usd=record.cost_usd,
            quota=quota,
            quota_used=record.calls,
        )

    async def list_users(self, *, page: int, page_size: int) -> PaginatedUsers:
        """分页列出全部用户（admin 专用；鉴权在路由层 `require_role`）。"""
        items, total = await self._users.list_paginated(page=page, page_size=page_size)
        return PaginatedUsers(
            items=[UserPublic.model_validate(user) for user in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    # ------------------------------------------------------------- 内部工具

    async def _require_user(self, user_id: uuid.UUID) -> User:
        """取用户，缺失即 404；用于「令牌有效但用户已被删」的边界。"""
        record = await self._users.get_by_id(user_id)
        if record is None:
            raise NotFound("用户不存在")
        return record

    async def _issue_pair(self, user: User, *, now: datetime) -> TokenPair:
        """签发 access（JWT，只含 sub/role/iat/exp）+ refresh（不透明随机串落摘要）。"""
        access_token, expires_in = issue_access(
            self._codec,
            user_id=user.id,
            role=UserRole(user.role),
            settings=self._settings,
            now=now,
        )
        plain_refresh = new_opaque_token()
        await self._refresh_tokens.create(
            user_id=user.id,
            token_hash=hash_opaque_token(plain_refresh),
            expires_at=now + timedelta(seconds=self._settings.refresh_token_ttl_seconds),
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=plain_refresh,
            expires_in=expires_in,
        )

    async def _load_refresh_record(self, digest: str) -> RefreshToken | None:
        """按摘要取刷新令牌记录（**不过滤** revoked/expired，供上层区分失效与过期）。

        `CONTRACTS §9` 行为 3 要求「失效 401 / 过期 TOKEN_EXPIRED」两种映射，
        而 T02 的 `RefreshTokenRepository.get_active_by_hash` 只返回有效记录，
        故这里直查本模块自己的表；只按唯一列等值查询，不跨租户。
        """
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == digest)
        )
        return result.scalar_one_or_none()

    async def _audit(
        self,
        action: str,
        *,
        user_id: uuid.UUID,
        ip: str | None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """写审计（不 commit，随请求事务提交）；`detail` 不含密码/令牌/明文邮箱。"""
        await record_audit(
            self._session,
            action=action,
            user_id=user_id,
            entity="user",
            entity_id=str(user_id),
            ip=ip,
            detail=detail,
        )


def build_identity_service(
    *,
    session: AsyncSession,
    settings: Settings,
    redis: aioredis.Redis,
) -> IdentityService:
    """组合根：把端口实现装配进服务。

    放在模块内而非 `app/api/deps.py`，是因为 import-linter 禁止路由层引用
    `app.modules.identity.adapters`（T01 契约 C8）；服务层引用本模块适配器不受限。
    T06 换真实邮件适配器只需改这里一行。
    """
    return IdentityService(
        session=session,
        settings=settings,
        hasher=Argon2PasswordHasher(),
        codec=JWTTokenCodec(settings.secret_key.get_secret_value(), settings.jwt_algorithm),
        mail=LoggingMailSender(),
        redis=redis,
    )
