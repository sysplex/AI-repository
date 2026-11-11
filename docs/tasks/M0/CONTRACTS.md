# M0 接口契约（CONTRACTS）

> 并行开发的"接线图"。每个任务按这里的**签名与行为**实现，签名不得擅自更改（有疑问在 Issue 里提）。
> 对应设计：`docs/02-architecture.md`、`docs/04-modules.md#m0`、`docs/05-api-spec.md`、`docs/07-delivery-standard.md`。

## 0. 全局约定

| 项 | 约定 |
|---|---|
| 语言/版本 | Python 3.12；`from __future__ import annotations` 不强制，类型标注必须完整 |
| 依赖管理 | `uv`，配置在 `backend/pyproject.toml`，`backend/uv.lock` 入库 |
| 导入根 | 包名 `app`（代码在 `backend/app/`），例：`from app.core.config import get_settings` |
| 异步 | IO 一律 `async`；禁止在事件循环里做阻塞调用 |
| 类型 | `mypy --strict` 通过 |
| 时间 | 带时区 `datetime`；存储/传输 UTC；业务日历用 `America/New_York` |
| 金额 | `Decimal`，禁止 float |
| 测试 | `pytest` + `pytest-asyncio`（`asyncio_mode = "auto"`）；标记：`unit` `integration` `contract` `e2e` |

## 1. 目录结构（T01 创建，其余任务在其中填充）

```
backend/
  pyproject.toml  uv.lock  alembic.ini
  alembic/                       env.py  versions/        ← T04
  app/
    __init__.py
    main.py                      create_app()             ← T01（接线，仅 T01 与 T11 可改）
    worker.py                    ARQ WorkerSettings       ← T08
    core/
      config.py                  Settings / get_settings  ← T02
      logging.py                 setup_logging / get_logger / contextvars ← T02
      middleware.py              install_middlewares      ← T02
      errors.py                  AppError 体系 / handlers ← T03
      db.py                      engine / session / Base  ← T04
      audit.py                   AuditLog / record_audit  ← T04
      events.py                  EventBus                 ← T05
      calendar.py                NYSE 日历                ← T06
      clock.py                   Clock / FrozenClock      ← T06
      redis.py                   Redis 客户端             ← T07
      metrics.py                 Prometheus 指标          ← T07
      lifecycle.py               on_startup/on_shutdown   ← T07
    domain/
      __init__.py
      events.py                  领域事件                 ← T05
    api/
      __init__.py
      router.py                  root_router / api_router ← T01 创建空壳，T07 接入 health
      health.py                  /healthz /readyz /metrics ← T07
    modules/
      identity/ marketdata/ strategy/ simbroker/ ai/ research/ screener/ scheduler/ notify/
        __init__.py              ← T01（仅空包，M1+ 填充）
  tests/
    conftest.py                  ← T10
    unit/ integration/ contract/ e2e/ fixtures/
deploy/
  Dockerfile  docker-compose.yml  nginx/nginx.conf  env.example   ← T08
.github/workflows/ci.yml  .github/dependabot.yml                    ← T09
Makefile  .editorconfig  .pre-commit-config.yaml                     ← T01
```

**"空壳（stub）"规则**：T01 为每个被其他任务拥有的文件创建**最小可运行占位**（不报错、无副作用）。该文件之后**归所属任务所有并可整体重写**，其他任务不得修改。

## 2. 配置 `app/core/config.py`（T02）

```python
class Settings(BaseSettings):
    app_env: Literal["local", "ci", "staging", "production"] = "local"
    app_name: str = "stockpilot"
    app_version: str = "0.0.0"
    log_level: str = "INFO"
    log_json: bool = True
    database_url: str            # 必填，形如 postgresql+asyncpg://user:pass@host:5432/db
    redis_url: str               # 必填，形如 redis://host:6379/0
    secret_key: SecretStr        # 必填，≥ 32 字符
    cors_origins: list[str] = []
    metrics_enabled: bool = True
    docs_enabled: bool = True    # production 默认应关闭（由部署环境变量控制）

def get_settings() -> Settings   # lru_cache 单例；测试可 get_settings.cache_clear()
```
行为：
- 环境变量名为字段名大写（`DATABASE_URL`）；支持 `.env`（仅 local）。
- **必填项缺失或非法 → 启动失败**，错误信息列出**所有**缺失/非法变量名（不是只报第一个），进程退出码 ≠ 0。
- `SecretStr` 不得出现在日志/`repr`。

## 3. 日志与请求上下文（T02）

```python
# app/core/logging.py
request_id_var: ContextVar[str | None]
user_id_var:    ContextVar[str | None]
task_id_var:    ContextVar[str | None]
def setup_logging(settings: Settings) -> None
def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger

# app/core/middleware.py
def install_middlewares(app: FastAPI, settings: Settings) -> None
```
行为：
- JSON 日志（`log_json=True`）每行含：`timestamp`(UTC ISO)、`level`、`event`、`logger`、`request_id`、`user_id`、`task_id`（有则带）。`log_json=False` 用人类可读控制台格式。
- `RequestContextMiddleware`：读取请求头 `X-Request-ID`（合法 UUID/≤64 字符 ASCII 则沿用，否则新生成 UUID4），写入 `request_id_var`，**响应头回写 `X-Request-ID`**；请求结束输出一条访问日志（方法、路径、状态码、耗时 ms，**不记录 Authorization/Cookie/请求体**）。
- CORS：按 `settings.cors_origins` 安装 `CORSMiddleware`（空列表则不安装）。
- 安全响应头中间件：`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer`。
- `install_middlewares` 之后 T07 会追加指标中间件，故中间件顺序须写在 `install_middlewares` 内部并用注释标明"指标中间件插入点"。

## 4. 错误体系 `app/core/errors.py`（T03）

```python
class ErrorCode(StrEnum):
    VALIDATION_ERROR; UNAUTHENTICATED; TOKEN_EXPIRED; FORBIDDEN; NOT_FOUND
    IDEMPOTENCY_CONFLICT; STATE_CONFLICT
    INSUFFICIENT_FUNDS; INSUFFICIENT_POSITION; INVALID_ORDER
    DATA_UNAVAILABLE; RATE_LIMITED; QUOTA_EXCEEDED
    LLM_FAILED; LLM_OUTPUT_INVALID; BUDGET_CIRCUIT_OPEN; INTERNAL_ERROR

class AppError(Exception):
    code: ErrorCode; http_status: int; message: str; details: dict[str, Any]
    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None) -> None
# 子类（默认 http_status / code 见 docs/05-api-spec.md §1.2）：
ValidationFailed(400) Unauthenticated(401) TokenExpired(401) Forbidden(403) NotFound(404)
IdempotencyConflict(409) StateConflict(409) InsufficientFunds(422) InsufficientPosition(422)
InvalidOrder(422) DataUnavailable(424) RateLimited(429) QuotaExceeded(429)
LLMFailed(502) LLMOutputInvalid(502) BudgetCircuitOpen(503) InternalError(500)

def register_exception_handlers(app: FastAPI) -> None
```
响应体（所有错误统一）：
```json
{"error": {"code": "NOT_FOUND", "message": "...", "details": {}, "request_id": "<当前 request_id 或 null>"}}
```
处理器：`AppError`、`RequestValidationError`（→ 400 `VALIDATION_ERROR`，`details.errors` 为精简后的字段错误列表）、`StarletteHTTPException`（404/405 等映射为统一格式）、未捕获 `Exception`（→ 500 `INTERNAL_ERROR`，**对外 message 固定为通用文案，不泄露堆栈**；完整异常写日志）。`RateLimited` 若 `details` 含 `retry_after`（秒）则加 `Retry-After` 响应头。

## 5. 数据库 `app/core/db.py`、`app/core/audit.py`（T04）

```python
# db.py
class Base(DeclarativeBase): ...          # 含统一 naming_convention（ix/uq/ck/fk/pk）
class UUIDPkMixin:      id: Mapped[uuid.UUID]            # server_default gen_random_uuid()
class TimestampMixin:   created_at, updated_at: Mapped[datetime]   # timestamptz, server_default now()
def get_engine() -> AsyncEngine          # 懒创建单例
def get_session_factory() -> async_sessionmaker[AsyncSession]
async def get_session() -> AsyncIterator[AsyncSession]    # FastAPI 依赖：请求结束 commit/异常 rollback
async def check_db() -> bool             # SELECT 1，失败返回 False 不抛异常
async def dispose_engine() -> None

# audit.py
class AuditLog(Base, UUIDPkMixin):
    user_id: UUID | None; action: str; entity: str | None; entity_id: str | None
    ip: str | None; detail: dict (JSONB); created_at: datetime
async def record_audit(session, *, action, user_id=None, entity=None, entity_id=None, ip=None, detail=None) -> None
```
- Alembic：异步 `env.py`；`alembic.ini` 不含密码，URL 取自 `Settings.database_url`；初始迁移 `0001_initial` 启用 `pgcrypto`（或使用 PG13+ 内置 `gen_random_uuid()`）并创建 `audit_log`（字段与 `docs/03-data-model.md` 一致，`user_id` 此时**不加外键**，M1 再补）及索引 `(user_id, created_at)`、`(action, created_at)`。
- 迁移必须 `upgrade head` 与 `downgrade base` 均可执行。

## 6. 事件总线 `app/core/events.py`、`app/domain/events.py`（T05）

```python
# core/events.py
class Event(BaseModel):                       # 冻结模型
    event_id: UUID  (默认 uuid4)
    occurred_at: datetime  (默认 UTC now，带时区)
EventHandler = Callable[[E], Awaitable[None]]
class EventBus:
    def subscribe(self, event_type: type[E], handler: EventHandler[E]) -> None
    def unsubscribe(self, event_type: type[E], handler: EventHandler[E]) -> None
    async def publish(self, event: Event) -> None
def get_event_bus() -> EventBus               # 进程内单例
```
- `publish`：按**订阅顺序**依次 `await` 处理器（同一事件类型及其**父类**订阅者都会收到）；**单个处理器抛异常不得影响其他处理器与发布方**，异常以 `ERROR` 日志记录（含事件类型、处理器名）。
- 无订阅者时 `publish` 为空操作。
- `domain/events.py` 定义（均继承 `Event`）：
  `OrderFilled(account_id: UUID, order_id: UUID, symbol: str, side: str, qty: Decimal, price: Decimal)`、
  `ReportCreated(report_id: UUID, user_id: UUID, use_case: str, symbols: list[str])`、
  `SignalTriggered(strategy_id: str, symbol: str, as_of: date, direction: str, strength: int)`。

## 7. 日历与时钟 `app/core/calendar.py`、`app/core/clock.py`（T06）

```python
ET: ZoneInfo = ZoneInfo("America/New_York")

@dataclass(frozen=True)
class Session:
    trade_date: date; open_at: datetime; close_at: datetime; is_half_day: bool   # open/close 为带时区(ET)

class NotATradingDay(ValueError): ...
class CalendarRangeError(ValueError): ...      # 超出支持范围 2020-01-01 ~ 2030-12-31

def is_trading_day(d: date) -> bool
def next_trading_day(d: date) -> date          # 严格晚于 d
def previous_trading_day(d: date) -> date      # 严格早于 d
def get_session(d: date) -> Session            # 非交易日抛 NotATradingDay
def trading_days_between(start: date, end: date) -> list[date]   # 闭区间，升序
def is_market_open(at: datetime) -> bool       # at 必须带时区，否则抛 ValueError
def to_et(dt: datetime) -> datetime
def to_utc(dt: datetime) -> datetime

# clock.py
class Clock(Protocol):  def now(self) -> datetime            # 带时区 UTC
class SystemClock: ...
class FrozenClock:      def __init__(self, at: datetime); def set(self, at); def advance(self, delta: timedelta); def now(self)
def get_clock() -> Clock
def set_clock(clock: Clock) -> None            # 供测试替换；另提供 reset_clock()
```
- 基于 `exchange_calendars` 的 `XNYS`，初始化时显式指定 `start=2020-01-01, end=2030-12-31`；**其他模块禁止直接引用 exchange_calendars**。
- 提前收盘日（半日市）`close_at` = 13:00 ET。

## 8. Redis / 健康检查 / 指标（T07）

```python
# core/redis.py
def get_redis() -> redis.asyncio.Redis        # 懒创建单例，decode_responses=True
async def check_redis() -> bool               # PING，失败返回 False 不抛异常
async def close_redis() -> None

# core/lifecycle.py
async def on_startup(app: FastAPI) -> None     # M0：记录启动日志
async def on_shutdown(app: FastAPI) -> None    # 调用 dispose_engine() 与 close_redis()

# core/metrics.py
def install_metrics(app: FastAPI, settings: Settings) -> None    # 指标中间件 + 注册表
```
端点（**根路径，不带 /api/v1**）：

| 端点 | 行为 |
|---|---|
| `GET /healthz` | 进程存活，恒 `200 {"status":"ok"}`，不访问外部依赖 |
| `GET /readyz` | 检查 DB 与 Redis：全部正常 `200`，否则 `503`；响应 `{"status":"ready|not_ready","checks":{"database":true,"redis":true}}`；检查带 2 秒超时 |
| `GET /metrics` | Prometheus 文本格式；`metrics_enabled=false` 时 404；Nginx 层限制仅内网（T08） |

指标：`http_requests_total{method,path_template,status}`、`http_request_duration_seconds{method,path_template}`（直方图）、`app_info{version,env}`。`path_template` 用路由模板（如 `/sim/accounts/{id}`），**严禁用原始路径**（防基数爆炸）；未匹配路由记为 `unmatched`。

## 9. 应用接线 `app/main.py`（T01 创建；之后仅 T01/T11 可改）

```python
def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)                         # T02
    app = FastAPI(title=settings.app_name, version=settings.app_version,
                  docs_url="/docs" if settings.docs_enabled else None,
                  openapi_url="/api/v1/openapi.json" if settings.docs_enabled else None,
                  lifespan=lifespan)                # lifespan 调用 lifecycle.on_startup/on_shutdown
    install_middlewares(app, settings)              # T02（内含 T07 指标插入点）
    register_exception_handlers(app)                # T03
    app.include_router(root_router)                 # T07：/healthz /readyz /metrics
    app.include_router(api_router, prefix="/api/v1")# M1+ 逐步挂载
    return app

app = create_app()
```
> T01 的空壳让上述调用全部可运行（no-op）。因此各任务**只改自己的文件，不碰 main.py**。

## 10. 环境变量清单（T08 写入 `deploy/env.example`，值为占位符）

| 变量 | 必填 | 说明 |
|---|---|---|
| `APP_ENV` | 否 | local/ci/staging/production |
| `LOG_LEVEL` `LOG_JSON` | 否 | 日志 |
| `DATABASE_URL` | 是 | `postgresql+asyncpg://...` |
| `REDIS_URL` | 是 | `redis://...` |
| `SECRET_KEY` | 是 | ≥ 32 字符随机串 |
| `CORS_ORIGINS` | 否 | JSON 数组或逗号分隔 |
| `METRICS_ENABLED` `DOCS_ENABLED` | 否 | 开关 |
| `TEST_DATABASE_URL` | 测试 | 测试库（T10） |
| `POSTGRES_USER/PASSWORD/DB` | compose | Postgres 容器 |

## 11. Makefile 目标（T01）

`make install`（uv sync）`lint`（ruff check + format --check）`fmt` `typecheck`（mypy --strict）`lint-imports` `test` `test-unit` `check`（= lint + typecheck + lint-imports + test）`up` `down` `migrate` `revision m="msg"`。
