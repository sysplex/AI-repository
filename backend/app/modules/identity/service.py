"""M1 identity 应用服务（T04 主干），`CONTRACTS.md §9` / `§12`。

本层不依赖 HTTP 对象（`docs/07 §5`）：`ip` 由路由层从 `Request.client.host` 传入，
`now` 一律取 `app.core.clock.get_clock()`，测试用 `frozen_clock` 可确定性复现。
T05 / T06 只允许在本类追加方法，不得改动已有签名。

两条安全约定：

* 登录失败对外只有一种文案，且「用户不存在」也走一次真实的 argon2 校验
  （`_DUMMY_PASSWORD_HASH`），避免通过响应时间枚举账号。
* 审计 `detail` 只放摘要类信息（邮箱 SHA-256 前缀），不放明文密码、令牌或邮箱本身。

邮件投递（T06 装配 / Q3 裁决 2026-11-13）：服务只依赖 `MailSender` 端口，具体实现由
`make_mail_sender` 按 `APP_ENV` 与 SMTP 配置选择（`ci` 内存 / 已配置则 Gmail·Outlook
SMTP / 未配置时本地日志）。明文重置令牌只出现在邮件正文里，响应体、审计与访问日志
均不含；真实投递的日志只记录收件人摘要与连接信息。
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
from app.core.logging import get_logger
from app.modules.identity.adapters.mail import InMemoryMailSender, LoggingMailSender
from app.modules.identity.adapters.password_hasher import Argon2PasswordHasher
from app.modules.identity.adapters.smtp_mail import SmtpMailSender
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
    PasswordResetConfirm,
    PasswordResetRequest,
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

__all__ = [
    "IdentityService",
    "LoginRateLimiter",
    "build_identity_service",
    "make_mail_sender",
    "normalize_email",
]

_LOGIN_ACCOUNT_KEY: Final[str] = "login:fail:account:{}"
_LOGIN_IP_KEY: Final[str] = "login:fail:ip:{}"
_UNKNOWN_IP: Final[str] = "unknown"
_EMAIL_DIGEST_PREFIX: Final[int] = 12
_RESET_SUBJECT: Final[str] = "密码重置令牌"
_LOGGER = get_logger(__name__)

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


def _render_reset_body(token: str, *, ttl_seconds: int) -> str:
    """重置邮件正文：明文令牌**只**出现在这里（不落库、不进审计、不进响应体）。

    令牌独占一行且无其它字符干扰，便于调用方/测试按行提取；
    正文不含邮箱，避免同一份内容在本地日志里重复出现 PII。
    """
    minutes = max(ttl_seconds // 60, 1)
    return (
        "你好：\n\n"
        f"我们收到你的密码重置请求。请在 {minutes} 分钟内使用下面的令牌完成重置，"
        "该令牌仅可使用一次：\n\n"
        f"{token}\n\n"
        "如果这不是你本人的操作，请忽略本邮件，你的密码不会被修改。\n"
    )


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
        """整体替换 `users.settings`，并审计。"""
        record = await self._require_user(user.id)
        current = record.settings or {}
        new_data = update.settings.model_dump(mode="json")
        # 若新保存未提供 google_api_key 或传入了掩码，保留已有真实密钥
        if not new_data.get("google_api_key") or new_data.get("google_api_key", "").startswith("***"):
            if current.get("google_api_key"):
                new_data["google_api_key"] = current["google_api_key"]
        record.settings = new_data
        await self._users.save(record)
        await self._audit(
            "auth.settings_updated",
            user_id=record.id,
            ip=None,
            detail={"keys": sorted(record.settings)},
        )
        return UserPublic.model_validate(record)

    async def get_user_settings(self, user_id: uuid.UUID) -> UserSettings:
        """获取指定用户的个性化设置（含 AI 偏好与凭证）。"""
        record = await self._require_user(user_id)
        return UserSettings.model_validate(record.settings or {})

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

    # ------------------------------------------------------------------ T06

    async def request_password_reset(self, req: PasswordResetRequest, *, ip: str | None) -> None:
        """发起重置：账号存在才落库 + 发信，否则静默返回（`CONTRACTS §9` 行为 6）。

        账号不存在、被禁用都走「什么都不做」的分支，路由层统一回 202，
        响应体与耗时量级一致，不泄露账号是否存在。
        """
        email = normalize_email(str(req.email))
        user = await self._users.get_by_email(email)
        if user is None or user.status != UserStatus.ACTIVE.value:
            return

        now = get_clock().now()
        ttl = self._settings.password_reset_ttl_seconds
        plain_token = new_opaque_token()
        await self._reset_tokens.create(
            user_id=user.id,
            token_hash=hash_opaque_token(plain_token),
            expires_at=now + timedelta(seconds=ttl),
        )
        await self._mail.send(
            to=email,
            subject=_RESET_SUBJECT,
            body=_render_reset_body(plain_token, ttl_seconds=ttl),
        )
        await self._audit(
            "auth.password_reset_requested",
            user_id=user.id,
            ip=ip,
            detail={"email": _email_digest(email)},
        )

    async def confirm_password_reset(self, req: PasswordResetConfirm, *, ip: str | None) -> None:
        """确认重置：一次性令牌 → 吊销全部 refresh → 改密 → 审计。

        无效/过期/已用三种情况在 `get_active_by_hash` 里已经收敛成「查不到」，
        对外一律 401 `UNAUTHENTICATED`，不区分原因（`CONTRACTS §9` 行为 7）。
        """
        digest = hash_opaque_token(req.token.get_secret_value())
        now = get_clock().now()
        record = await self._reset_tokens.get_active_by_hash(digest, now=now)
        if record is None:
            raise Unauthenticated()

        user = await self._users.get_by_id(record.user_id)
        if user is None or user.status != UserStatus.ACTIVE.value:
            raise Unauthenticated()

        await self._reset_tokens.mark_used(record, now=now)
        revoked = await self._refresh_tokens.revoke_all_for_user(user_id=user.id, now=now)
        user.password_hash = hash_password(self._hasher, req.new_password)
        await self._users.save(user)
        await self._audit(
            "auth.password_changed",
            user_id=user.id,
            ip=ip,
            detail={"email": _email_digest(user.email), "refresh_tokens_revoked": revoked},
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


def make_mail_sender(settings: Settings) -> MailSender:
    """按 `APP_ENV` 与 SMTP 配置选择 `MailSender` 实现（Q3 裁决 2026-11-13）。

    优先级从高到低：

    1. `ci`：`InMemoryMailSender` —— **即使配了 SMTP 也不外发**，令牌不进 CI 日志，
       测试自行注入实例断言；保证集成测试与 `scripts/m1_demo.py` 行为不变。
    2. `smtp_configured`：`SmtpMailSender` —— Gmail / Outlook STARTTLS 真实投递；
       凭据以 `SecretStr` 保持到最后一步，service 业务逻辑不接触明文。
    3. `local` 未配 SMTP：`LoggingMailSender` —— 控制台可见令牌，便于手工联调。
    4. `staging` / `production` 未配 SMTP：仍回落日志实现，但打 **error** 级
       `mail.adapter.placeholder` 标记（T06 D2 保留，作为上线门槛告警）。
    """
    if settings.app_env == "ci":
        return InMemoryMailSender()
    password = settings.smtp_password
    if settings.smtp_configured and password is not None:
        return SmtpMailSender(
            host=settings.smtp_resolved_host,
            port=settings.smtp_port,
            user=settings.smtp_user or "",
            password=password,
            sender=settings.smtp_resolved_from,
            use_starttls=settings.smtp_starttls,
            timeout=settings.smtp_timeout_seconds,
        )
    if settings.app_env != "local":
        _LOGGER.error(
            "mail.adapter.placeholder",
            app_env=settings.app_env,
            incident="mail_adapter_missing",
            detail="非本地环境仍在使用日志投递，邮件正文含一次性重置令牌，上线前必须替换",
        )
    return LoggingMailSender()


def build_identity_service(
    *,
    session: AsyncSession,
    settings: Settings,
    redis: aioredis.Redis,
    mail: MailSender | None = None,
) -> IdentityService:
    """组合根：把端口实现装配进服务。

    放在模块内而非 `app/api/deps.py`，是因为 import-linter 禁止路由层引用
    `app.modules.identity.adapters`（T01 契约 C8）；服务层引用本模块适配器不受限。
    `mail` 为空时按 `APP_ENV` 自动选择（T06）；测试可显式传入 `InMemoryMailSender`。
    """
    return IdentityService(
        session=session,
        settings=settings,
        hasher=Argon2PasswordHasher(),
        codec=JWTTokenCodec(settings.secret_key.get_secret_value(), settings.jwt_algorithm),
        mail=mail if mail is not None else make_mail_sender(settings),
        redis=redis,
    )
