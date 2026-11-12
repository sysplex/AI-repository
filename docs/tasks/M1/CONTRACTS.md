# M1 接口契约（identity）

> 阶段 0 由执行方代拟，待协调者追认。**接口签名以本文件为准**；认为契约有问题，在对应 Issue 提出，由协调者裁决，不得自行改签名。
> 依赖的 M0 基础设施（`app.core.*`）签名见 `docs/tasks/M0/CONTRACTS.md`，本文件只定义 M1 新增面。
> 代码位置一律在 `backend/app/modules/identity/` 下，除 §10 的路由层与 §11 的配置改动。

## 1. 通用约定

| 项 | 约定 |
|---|---|
| 基础路径 | `/api/v1`；`docs/05 §2.1` 表中的路径均相对此前缀（裁定 C2） |
| 认证 | `Authorization: Bearer <access_token>`；公开端点：`/auth/register`、`/auth/login`、`/auth/refresh`、`/auth/password/*` 与 M0 健康检查 |
| 成功响应 | 直接返回资源对象；列表返回 `{items, total, page, page_size}`（`docs/05 §1.1`） |
| 失败响应 | 沿用 M0 统一结构 `{"error":{"code","message","details","request_id"}}`，由 `app.core.errors` 的 `AppError` handler 生成；**M1 不新增异常处理器、不改 `core/errors.py`** |
| 时间 | 所有 `datetime` 带 UTC 时区；令牌时间用 `app.core.clock.get_clock().now()`，便于 `frozen_clock` 测试 |
| 金额 | `cost_usd` 用 `Decimal`，序列化为字符串（`docs/07 §5`） |
| 越权 | 私有资源越权返回 `404 NOT_FOUND`（不区分不存在/不属于，防探测）；角色不足返回 `403 FORBIDDEN`（裁定 C10） |
| 限流 | `429 RATE_LIMITED`，`details["retry_after"]` 会被 M0 handler 转成 `Retry-After` 响应头 |
| 敏感数据 | 密码、令牌、重置令牌一律用 `pydantic.SecretStr` 接收；日志不得打印其值；库中只存哈希/摘要 |

## 2. 配置（`app/core/config.py`，T01 新增字段）

全部有默认值，**不改变 M0 的三个必填变量 `DATABASE_URL` / `REDIS_URL` / `SECRET_KEY`**，也不改变 `load_settings_or_exit()` 的失败提示格式。

```python
class Settings(BaseSettings):
    # ... M0 既有字段保持不变 ...
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_ttl_seconds: int = 900            # 15 min，必须 > 0
    refresh_token_ttl_seconds: int = 2592000       # 30 d，必须 > 0
    password_reset_ttl_seconds: int = 3600        # 1 h，必须 > 0
    login_rate_limit_max: int = 5                 # 窗口内最大失败次数
    login_rate_limit_window_seconds: int = 60
    ai_daily_quota: int = 20                     # C5：Q4 前默认值
```

`field_validator` 保证三个 TTL、窗口与 `max` 均为正整数；校验失败沿用 `SettingsError` 的「变量名 + 原因」格式。JWT 签名密钥复用 `settings.secret_key.get_secret_value()`（C4）。

## 3. 数据模型（`models.py` / `0002_identity.py`）

所有表继承 `app.core.db.Base` / `UUIDPkMixin` / `TimestampMixin`；时间列 `DateTime(timezone=True)`，主键 `gen_random_uuid()`。

| 表 | 字段 | 约束 |
|---|---|---|
| `users` | `email`(String(320), unique, not null)、`password_hash`(String(255))、`role`(String(16), default `user`)、`status`(String(16), default `active`)、`settings`(JSONB, default `{}`)、`created_at`/`updated_at` | `uq_users_email`；`(email)` 唯一索引覆盖登录查询 |
| `refresh_tokens` | `user_id`(Uuid, FK `users.id` ON DELETE CASCADE)、`token_hash`(String(64), unique)、`expires_at`、`revoked_at`(nullable)、`created_at` | `ix_refresh_tokens_user_id` |
| `password_reset_tokens` | `user_id`(Uuid, FK `users.id` ON DELETE CASCADE)、`token_hash`(String(64), unique)、`expires_at`、`used_at`(nullable)、`created_at` | `ix_password_reset_tokens_user_id` |
| `ai_usage` | `user_id`(Uuid, FK `users.id` ON DELETE CASCADE)、`usage_date`(Date)、`calls`/`tokens_in`/`tokens_out`(Integer, default 0)、`cost_usd`(Numeric(18,6), default 0) | `uq(user_id, usage_date)`；M1 只读（C6） |

- `0002_identity.py`：`revision = "0002_identity"`，`down_revision = "0001_initial"`；`upgrade()` 建 4 表 + 索引，并为 `audit_log.user_id` 补外键 `fk_audit_log_user_id_users`（`ON DELETE SET NULL`，接缝 S1）；`downgrade()` 反向且完整可逆。
- 迁移前置检查：`audit_log` 若存在 `user_id` 非 NULL 且不在 `users` 中的历史行，先置 NULL 再加外键（M0 冒烟写的行无真实用户）。
- **禁止**修改 `0001_initial.py`；**禁止**在 T02–T07 新增迁移。

## 4. 领域 schema（`schemas.py`）

```python
class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"

class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"

class UserSettings(BaseModel):
    risk_profile: Literal["conservative", "balanced", "aggressive"] = "balanced"
    language: str = "zh-CN"
    default_account_id: uuid.UUID | None = None

class RegisterRequest(BaseModel):
    email: EmailStr
    password: SecretStr                 # ≥ 12 字符，含大小写与数字
    settings: UserSettings = UserSettings()

class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr

class RefreshRequest(BaseModel):
    refresh_token: SecretStr

class LogoutRequest(BaseModel):
    refresh_token: SecretStr

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: SecretStr
    new_password: SecretStr

class SettingsUpdate(BaseModel):
    settings: UserSettings

class UserPublic(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    status: UserStatus
    settings: UserSettings
    created_at: datetime

class AuthenticatedUser(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    status: UserStatus
    settings: UserSettings

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int                    # = access_token_ttl_seconds

class UsageResponse(BaseModel):
    usage_date: date
    calls: int
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal
    quota: int
    quota_used: int

class PaginatedUsers(BaseModel):
    items: list[UserPublic]
    total: int
    page: int
    page_size: int
```

`RegisterRequest.password` 的复杂度在 Pydantic `field_validator` 里校验，失败由 M0 的 `RequestValidationError` handler 统一成 `400 VALIDATION_ERROR`，错误消息不回显输入值。

## 5. 端口（`ports.py`）

外部系统只经端口接入；实现放 `adapters/`，业务代码不直接 import 第三方 SDK（`docs/02 §4`）。

```python
class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, password_hash: str) -> bool: ...

@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: uuid.UUID
    role: UserRole
    issued_at: datetime
    expires_at: datetime

class TokenCodec(Protocol):
    def issue_access(self, *, user_id: uuid.UUID, role: UserRole,
                     now: datetime, ttl_seconds: int) -> str: ...
    def decode_access(self, token: str, *, now: datetime) -> AccessClaims: ...
    # 解码失败抛 app.core.errors.Unauthenticated / TokenExpired，不抛库原生异常

class MailSender(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...
```

## 6. 适配器（`adapters/`）

| 文件 | 实现 | 说明 |
|---|---|---|
| `adapters/password_hasher.py` | `Argon2PasswordHasher` | 唯一允许 `import argon2` 的位置；`PasswordHasher` 默认参数按 OWASP 基线，超时/内存参数写常量 |
| `adapters/token_codec.py` | `JWTTokenCodec(secret: str, algorithm: str)` | 唯一允许 `import jwt` 的位置；HS256，claims 只含 `sub/role/iat/exp`，解码严格校验 `exp` 与必要字段 |
| `adapters/mail.py` | `InMemoryMailSender`（`messages: list[MailMessage]`）、`LoggingMailSender` | C1：不接外部服务商、不读密钥；`MailMessage` 为 dataclass，仅测试/本地可用 |

`adapters/__init__.py` 只导出上述类；`app.ruff` 的 `TID251` 禁用列表 **不需要** 扩充（argon2/jwt 不是数据源/LLM/券商 SDK），但 import-linter 会禁止 `identity` 之外引用 `adapters`（§11）。

## 7. 仓储（`repo.py`）

```python
ModelT = TypeVar("ModelT", bound=Base)

class TenantRepository(Generic[ModelT]):
    """所有用户私有表查询的唯一入口：构造时必须带 user_id，_scoped() 强制注入过滤。"""
    model: type[ModelT]
    def __init__(self, session: AsyncSession, *, user_id: uuid.UUID) -> None: ...
    def _user_id(self) -> uuid.UUID: ...                 # 为空抛 ValueError
    def _scoped(self, stmt: Select[tuple[ModelT]]) -> Select[tuple[ModelT]]: ...
    async def get_by_id(self, entity_id: uuid.UUID) -> ModelT | None: ...
    async def list_for_user(self, *, limit: int = 20, offset: int = 0) -> Sequence[ModelT]: ...

class UserRepository:
    def __init__(self, session: AsyncSession) -> None: ...
    async def create(self, *, email: str, password_hash: str,
                     settings: dict[str, Any]) -> User: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_id(self, user_id: uuid.UUID) -> User | None: ...
    async def save(self, user: User) -> None: ...
    async def list_paginated(self, *, page: int, page_size: int) -> tuple[Sequence[User], int]: ...

class RefreshTokenRepository:
    # 按摘要查询属认证凭据路径（摘要本身是秘密），不走 TenantRepository；
    # 但所有「按用户」的吊销/列举必须带 user_id。
    def __init__(self, session: AsyncSession) -> None: ...
    async def create(self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> RefreshToken: ...
    async def get_active_by_hash(self, token_hash: str, *, now: datetime) -> RefreshToken | None: ...
    async def revoke(self, token: RefreshToken, *, now: datetime) -> None: ...
    async def revoke_all_for_user(self, *, user_id: uuid.UUID, now: datetime) -> int: ...

class PasswordResetTokenRepository:
    def __init__(self, session: AsyncSession) -> None: ...
    async def create(self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> PasswordResetToken: ...
    async def get_active_by_hash(self, token_hash: str, *, now: datetime) -> PasswordResetToken | None: ...
    async def mark_used(self, token: PasswordResetToken, *, now: datetime) -> None: ...

class AiUsageRepository(TenantRepository[AiUsage]):
    model = AiUsage
    async def get_for_date(self, *, usage_date: date) -> AiUsage | None: ...
```

`_scoped()` 必须无条件追加 `where(self.model.user_id == self._user_id())`；任何绕过它的查询都视为越权缺陷。单测用两个不同 `user_id` 断言互相读不到。

## 8. 安全原语（`security.py` / `tokens.py`）

```python
# security.py —— 只做组合，不 import 第三方 SDK
def hash_password(hasher: PasswordHasher, password: SecretStr) -> str: ...
def verify_password(hasher: PasswordHasher, password: SecretStr, password_hash: str) -> bool: ...
def new_opaque_token() -> str: ...            # secrets.token_urlsafe(32)
def hash_opaque_token(token: str) -> str: ... # sha256 hexdigest，64 字符

# tokens.py —— 只负责 access 颁发；refresh 明文令牌由 service 生成、哈希后落库，
# 两者组装成 TokenPair 是 service 的职责，避免 tokens.py 反向依赖仓储。
def issue_access(codec: TokenCodec, *, user_id: uuid.UUID, role: UserRole,
                 settings: Settings, now: datetime) -> tuple[str, int]: ...
```

`hash_opaque_token` 的输出即 `refresh_tokens.token_hash` / `password_reset_tokens.token_hash`；明文令牌只通过响应体或邮件适配器返回一次，绝不落库、绝不写日志。

## 9. 应用服务（`service.py`）

service 层不依赖 HTTP 对象（`docs/07 §5`）；`ip` 由路由层从 `Request.client.host` 传入。

```python
class IdentityService:
    def __init__(self, *, session: AsyncSession, settings: Settings,
                 hasher: PasswordHasher, codec: TokenCodec,
                 mail: MailSender, redis: aioredis.Redis) -> None: ...

    # T04
    async def register(self, req: RegisterRequest, *, ip: str | None) -> UserPublic: ...
    async def login(self, req: LoginRequest, *, ip: str | None) -> TokenPair: ...
    async def refresh(self, req: RefreshRequest, *, ip: str | None) -> TokenPair: ...
    async def logout(self, req: LogoutRequest, *, user: AuthenticatedUser,
                     ip: str | None) -> None: ...
    async def authenticate_access_token(self, token: str) -> AuthenticatedUser: ...

    # T05（只允许追加，不改上面签名）
    async def get_profile(self, user: AuthenticatedUser) -> UserPublic: ...
    async def update_settings(self, user: AuthenticatedUser,
                              update: SettingsUpdate) -> UserPublic: ...
    async def get_usage(self, user: AuthenticatedUser) -> UsageResponse: ...
    async def list_users(self, *, page: int, page_size: int) -> PaginatedUsers: ...

    # T06（只允许追加）
    async def request_password_reset(self, req: PasswordResetRequest, *, ip: str | None) -> None: ...
    async def confirm_password_reset(self, req: PasswordResetConfirm, *, ip: str | None) -> None: ...
```

行为约束：

1. `register`：邮箱先规范化（小写 + strip）；重复邮箱抛 `StateConflict`（409）；写 `audit_log` action `auth.register`；返回 `UserPublic`，**不自动登录**。
2. `login`：先过限流（§12），失败抛 `Unauthenticated`（401，通用消息，不区分「用户不存在/密码错」）；成功清限流计数、签发 access + refresh、写 `audit_log` action `auth.login`。
3. `refresh`：按摘要查未吊销未过期记录；轮换（旧记录 `revoked_at` 置当前时间，新建一条），返回新 `TokenPair`；失效一律 `Unauthenticated`，过期用 `TokenExpired`；写 `audit_log` action `auth.refresh`。
4. `logout`：吊销指定 refresh 令牌；**登出后该 refresh 立即不可用**（验收项 1）；写 `audit_log` action `auth.logout`。`/auth/logout` 需要有效 access 令牌。
5. `update_settings` / `confirm_password_reset`：写 `audit_log` action `auth.settings_updated` / `auth.password_changed`（验收项 4「改密」）。
6. `request_password_reset`：无论账号是否存在都返回 `None`（路由层 202），不泄露枚举信息；存在时生成一次性令牌、`MailSender.send` 输出带令牌的正文。
7. `confirm_password_reset`：令牌校验一次性（校验后立即 `mark_used` + 吊销该用户全部 refresh 令牌），改密码并审计；无效/过期/已用一律 `Unauthenticated`。

## 10. 路由层（`app/api/identity.py` / `app/api/deps.py` / `app/api/router.py`）

```python
# app/api/deps.py
async def get_identity_service(session: AsyncSession = Depends(get_session)) -> IdentityService: ...
async def current_user(request: Request, service: IdentityService = Depends(get_identity_service)) -> AuthenticatedUser: ...
def require_role(role: UserRole) -> Callable[..., Awaitable[AuthenticatedUser]]: ...
```

`current_user` 从 `Authorization` 解析 Bearer；缺失/格式错误抛 `Unauthenticated`；`require_role` 在角色不足时抛 `Forbidden`。`app/api/router.py` 由 T04 一次性 `api_router.include_router(identity_router)`，**不得改 `main.py`**。

| 方法 | 路径（相对 `/api/v1`） | 成功 | 认证 | 任务 |
|---|---|---|---|---|
| POST | `/auth/register` | 201 `UserPublic` | 公开 | T04 |
| POST | `/auth/login` | 200 `TokenPair` | 公开 | T04 |
| POST | `/auth/refresh` | 200 `TokenPair` | refresh 令牌 | T04 |
| POST | `/auth/logout` | 204 空 | Bearer access | T04 |
| POST | `/auth/password/reset-request` | 202 `{"status":"accepted"}` | 公开 | T06 |
| POST | `/auth/password/reset-confirm` | 204 空 | 重置令牌 | T06 |
| GET | `/me` | 200 `UserPublic` | Bearer | T05 |
| PATCH | `/me` | 200 `UserPublic` | Bearer | T05 |
| GET | `/me/usage` | 200 `UsageResponse` | Bearer | T05 |
| GET | `/admin/users?page=1&page_size=20` | 200 `PaginatedUsers` | admin | T05 |

`docs/05 §2.1` 表格由 T04/T05/T06 按此表登记（含 C2 的基础路径说明）。所有私有端点必须出现在 T05 的越权测试矩阵里。

## 11. import-linter 契约（`backend/pyproject.toml`，T01 修正）

M0 的第四条契约把 `app.api` 列为 source、把整个 `app.modules.identity` 列为 forbidden，会使 §10 的路由层无法调用 service（接缝 S2）。T01 改为：

- 保留前三条契约（分层、identity 独立、identity 不依赖其它业务模块）不变。
- 第四条「禁止引用内部面」：`source_modules = [app.api, app.domain, 其它业务模块…]`，`forbidden_modules = [app.modules.identity.repo, app.modules.identity.models, app.modules.identity.adapters, app.modules.identity.ports, …]`；`app.api` 不再被禁止引用 `app.modules.identity.service` / `schemas`。
- 新增第五条：`app.modules.identity.adapters` 只能被 `app.modules.identity` 自身引用（禁止跨模块直连适配器）。

`lint-imports --config pyproject.toml` 必须输出全部契约 `kept`、`0 broken`。

## 12. 限流与错误码映射

限流键（Redis）：`login:fail:account:{sha256(email)}` 与 `login:fail:ip:{ip}`，同一个 `INCR` + `EXPIRE(window)`；任一达到 `login_rate_limit_max` 即抛 `RateLimited("登录失败次数过多", details={"retry_after": <剩余秒>})`。成功登录后 `DELETE` 两个键。伪造/缺失 `X-Forwarded-For` 不采信，只用 `Request.client.host`（nginx 已设 `proxy_set_header`，但 M1 不信任客户端头）。

| 场景 | 异常（M0） | HTTP / code |
|---|---|---|
| 参数校验失败 | `RequestValidationError` → M0 handler | 400 `VALIDATION_ERROR` |
| 邮箱重复 | `StateConflict` | 409 `STATE_CONFLICT` |
| 登录凭据错 / refresh 无效 / 重置令牌无效 | `Unauthenticated` | 401 `UNAUTHENTICATED` |
| access / refresh 过期 | `TokenExpired` | 401 `TOKEN_EXPIRED` |
| 非 admin 访问 admin 接口 | `Forbidden` | 403 `FORBIDDEN` |
| 越权访问他人私有资源 | `NotFound` | 404 `NOT_FOUND` |
| 登录失败超阈值 | `RateLimited` | 429 `RATE_LIMITED` + `Retry-After` |

## 13. 环境变量（`deploy/env.example`，T01 追加，全部可选项）

```
ACCESS_TOKEN_TTL_SECONDS=900
REFRESH_TOKEN_TTL_SECONDS=2592000
PASSWORD_RESET_TTL_SECONDS=3600
LOGIN_RATE_LIMIT_MAX=5
LOGIN_RATE_LIMIT_WINDOW_SECONDS=60
AI_DAILY_QUOTA=20
```

不得把真实密钥写入示例；`SECRET_KEY` 仍只有 `CHANGE_ME_*` 占位值。`docs/03 §3.1` 由 T01 补 4 张表的字段说明与 C3/C6 注记。

## 14. 与验收清单的映射（`docs/08-test-plan.md` M1）

| 验收项 | 责任任务 | 证据 |
|---|---|---|
| 注册→登录→刷新→登出，登出后刷新失效 | T04 | `tests/integration/identity/test_auth_flow.py`，`client` fixture 全流程断言 |
| 登录失败限流生效 | T04 | `test_login_rate_limit.py`，fakeredis 断言计数与 `Retry-After` |
| 越权测试覆盖全部私有端点 | T05 | `test_tenant_isolation.py` 参数化矩阵，逐端点列出 |
| 审计日志记录登录/改密 | T04 / T06 | `test_audit_actions.py` 读回 `audit_log` |
| 管理员接口仅管理员可访问 | T05 | `test_admin_guard.py` 的 user/admin/disabled 三态断言 |

T07 追加：迁移可升可降、OpenAPI 与 `docs/05` 对照、可演示脚本、`docs/acceptance/M1.md` 五项清单逐项勾选。
