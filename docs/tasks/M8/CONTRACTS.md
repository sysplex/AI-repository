# M8 接口契约（CONTRACTS）

> 筛选器与主题自选（screener）权威接线图。每个任务严格按本契约的**签名与行为**实现。
> 对应设计：`docs/01-prd.md§F9, F10`、`docs/02-architecture.md§5`、`docs/03-data-model.md§3.4`、`docs/04-modules.md#m8`、`docs/05-api-spec.md§2.6`、`docs/06-ai-prompt-spec.md§4.8`、`docs/08-test-plan.md§5 M8`。

---

## 0. 全局与数据约定

| 项 | 约定 |
|---|---|
| 语言/版本 | Python 3.12；必须通过 `mypy app tests`（严格模式 0 错误） |
| 金额、分值与关键数值 | 关键数值严格采用 `Decimal`，严禁使用 `float`（如价格、得分 `score`、目标价 `target_price` 等） |
| 架构分层契约 | `screener` 位于应用组装与用例能力层（Layer 2），仅允许消费 Layer 3 的 `marketdata.service.DataService`、`strategy.service.StrategyService`、`ai.service.AIService` 及其 `schemas` 公开面 |
| 严禁跨层依赖 | 严禁直接依赖底层 ORM 实体或第三方 LLM SDK，所有大模型交互由 `AIService` 统一中转 |
| 防编造铁律（F10/F9） | **策略筛选 100% 由代码规则与策略算法执行，全市场选股严禁让 AI 自由发挥编造**；**主题卡片（Theme Cards）所引用事实指标 100% 来自代码 facts，AI 仅生成通俗解读与新人指导**；输出必须由 `FactTracingEngine` 严格溯源校验 |
| 筛选容错与隔离 | 扫描大样本股票池（如标普 500）时，单只标的获取异常（如数据缺失、网络抖动）不得导致整个批次奔溃，必须记录在 `failed_items` 并在完成时记录 `failed_count` |
| 多租户数据隔离 | 所有的筛选任务 `screener_runs` 和自选清单 `watchlists` 查询与操作必须带 `user_id` 过滤，严禁越权读取/修改其他租户数据 |
| 数据库迁移可逆性 | Alembic `0006_screener` 迁移脚本必须严格实现 `upgrade()` 和 `downgrade()`，测试覆盖升级与回滚 |

---

## 1. 领域模型与 DTO（`app/modules/screener/schemas.py`）

```python
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

ScreenerRunStatus = Literal["pending", "running", "succeeded", "failed"]

# ---------------------------------------------------------
# 股票池 (Universe) 与 主题 (Theme) 领域定义
# ---------------------------------------------------------
class UniverseInfo(BaseModel):
    """股票池基本信息"""
    model_config = ConfigDict(frozen=True)
    id: str = Field(description="股票池标识符，如 sp500, nasdaq100, dow30, custom")
    name: str = Field(description="股票池中文名称")
    description: str = Field(description="股票池说明")
    symbol_count: int = Field(ge=1, description="包含标的数量")

class ThemeStockItem(BaseModel):
    """主题预设成分股"""
    model_config = ConfigDict(frozen=True)
    symbol: str
    name: str
    sector: str
    sub_industry: str
    market_cap_tier: str = Field(description="mega, large, mid, small")

class ThemeInfo(BaseModel):
    """主题基本信息（F9 主题清单）"""
    model_config = ConfigDict(frozen=True)
    id: str = Field(description="主题标识，如 ai_chips, glp1_weightloss, high_dividend, cyber_security")
    name: str = Field(description="主题展示名称")
    category: str = Field(description="主题分类：tech, healthcare, dividend, energy, macro")
    tagline: str = Field(description="一句话导语")
    description: str = Field(description="新手向背景与逻辑说明")
    stocks: list[ThemeStockItem] = Field(default_factory=list)

# ---------------------------------------------------------
# 策略筛选任务 (Screener Runs & Results)
# ---------------------------------------------------------
class ScreenerRunCreate(BaseModel):
    """创建策略筛选任务请求"""
    strategy_id: str = Field(min_length=1, max_length=64, description="预设策略标识符")
    universe: str = Field(min_length=1, max_length=64, description="目标股票池或自定义池标识")
    params: dict[str, Any] = Field(default_factory=dict, description="策略微调参数")
    custom_symbols: list[str] | None = Field(default=None, description="自定义股票池时的标的列表")

class ScreenerResultItem(BaseModel):
    """单个标的筛选结果与指标快照"""
    model_config = ConfigDict(frozen=True)
    symbol: str
    rank: int = Field(ge=1)
    score: Decimal = Field(description="量化得分")
    signal: str = Field(description="策略信号，如 BUY, STRONG_BUY, NEUTRAL")
    metrics_snapshot: dict[str, Any] = Field(default_factory=dict, description="筛选时刻的核心指标")

class ScreenerRunRead(BaseModel):
    """筛选任务详情与结果返回"""
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    strategy_id: str
    universe: str
    params: dict[str, Any]
    status: ScreenerRunStatus
    total_symbols: int
    matched_count: int
    failed_count: int = 0
    error_message: str | None = None
    results: list[ScreenerResultItem] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None

# ---------------------------------------------------------
# F9 主题卡片（Theme Cards AI 响应模型）
# ---------------------------------------------------------
class ThemeCardItem(BaseModel):
    """AI 生成的单股主题卡片（严格受 facts 约束）"""
    model_config = ConfigDict(frozen=True)
    symbol: str
    name: str
    one_line_intro: str = Field(description="一句话商业模式/行业地位")
    why_watch: str = Field(description="为什么值得关注/核心看点")
    financial_strengths: list[str] = Field(description="财务亮点（引用真实数据）")
    main_risks: list[str] = Field(description="主要潜在风险")
    suitable_for: list[str] = Field(description="适合的投资者类型画像")
    more_attractive_when: str = Field(description="何时或何种估值/市场情境下更具吸引力")

class ThemeCardsResponse(BaseModel):
    """主题卡片完整返回包"""
    theme_id: str
    theme_name: str
    cards: list[ThemeCardItem]
    as_of: datetime
    prompt_version: str

# ---------------------------------------------------------
# 自选清单 (Watchlists & Items)
# ---------------------------------------------------------
class WatchlistItemCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    notes: str = Field(default="", max_length=500)
    target_price: Decimal | None = Field(default=None, gt=0)
    theme_tags: list[str] = Field(default_factory=list)

class WatchlistItemUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=500)
    target_price: Decimal | None = Field(default=None, gt=0)
    theme_tags: list[str] | None = None

class WatchlistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    watchlist_id: UUID
    symbol: str
    notes: str
    target_price: Decimal | None
    theme_tags: list[str]
    created_at: datetime

class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)
    is_default: bool = False

class WatchlistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    is_default: bool | None = None

class WatchlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    name: str
    description: str
    is_default: bool
    items: list[WatchlistItemRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

class ExportToResearchRequest(BaseModel):
    """一键将筛选或自选标的送入研报或对比"""
    symbols: list[str] = Field(min_length=1, max_length=10)
    target_action: Literal["compare", "portfolio", "deep_research"]
```

---

## 2. ORM 数据表（`backend/app/modules/screener/models.py`）

```python
class ScreenerRun(Base, UUIDPkMixin):
    __tablename__ = "screener_runs"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    universe: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    total_symbols: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    results: Mapped[list[ScreenerResult]] = relationship(back_populates="run", cascade="all, delete-orphan")

class ScreenerResult(Base, UUIDPkMixin):
    __tablename__ = "screener_results"
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("screener_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    signal: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    run: Mapped[ScreenerRun] = relationship(back_populates="results")

class Watchlist(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "watchlists"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    items: Mapped[list[WatchlistItem]] = relationship(back_populates="watchlist", cascade="all, delete-orphan")

class WatchlistItem(Base, UUIDPkMixin):
    __tablename__ = "watchlist_items"
    watchlist_id: Mapped[uuid.UUID] = mapped_column(Uuid(), ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    theme_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    watchlist: Mapped[Watchlist] = relationship(back_populates="items")
```

---

## 3. 端口协议与依赖倒置（`backend/app/modules/screener/ports.py`）

```python
@runtime_checkable
class UniverseManagerProtocol(Protocol):
    """股票池与主题股票库管理协议"""
    def list_universes(self) -> list[UniverseInfo]: ...
    def get_universe_symbols(self, universe_id: str) -> list[str]: ...
    def list_themes(self) -> list[ThemeInfo]: ...
    def get_theme(self, theme_id: str) -> ThemeInfo: ...

@runtime_checkable
class ScreenerExecutorProtocol(Protocol):
    """多标的并发策略筛选引擎协议（带隔离容错与确定性排序）"""
    async def execute_screening(
        self,
        strategy_id: str,
        symbols: list[str],
        params: dict[str, Any],
        as_of: datetime | None = None,
    ) -> tuple[list[ScreenerResultItem], list[dict[str, Any]]]: ...

@runtime_checkable
class ScreenerRepositoryProtocol(Protocol):
    """筛选任务持久化仓储协议（用户多租户隔离）"""
    async def create_run(self, run: ScreenerRun) -> ScreenerRun: ...
    async def update_run(self, run: ScreenerRun) -> ScreenerRun: ...
    async def get_run(self, run_id: UUID, user_id: UUID) -> ScreenerRun | None: ...
    async def list_runs(self, user_id: UUID, limit: int = 20, offset: int = 0) -> list[ScreenerRun]: ...

@runtime_checkable
class WatchlistRepositoryProtocol(Protocol):
    """自选列表持久化仓储协议"""
    async def list_watchlists(self, user_id: UUID) -> list[Watchlist]: ...
    async def get_watchlist(self, watchlist_id: UUID, user_id: UUID) -> Watchlist | None: ...
    async def create_watchlist(self, user_id: UUID, data: WatchlistCreate) -> Watchlist: ...
    async def update_watchlist(self, watchlist_id: UUID, user_id: UUID, data: WatchlistUpdate) -> Watchlist | None: ...
    async def delete_watchlist(self, watchlist_id: UUID, user_id: UUID) -> bool: ...
    async def add_item(self, watchlist_id: UUID, user_id: UUID, data: WatchlistItemCreate) -> WatchlistItem: ...
    async def remove_item(self, watchlist_id: UUID, item_id: UUID, user_id: UUID) -> bool: ...

@runtime_checkable
class ScreenerServiceProtocol(Protocol):
    """统一筛选器服务对外门面协议"""
    async def run_screener(self, user_id: UUID, request: ScreenerRunCreate) -> ScreenerRunRead: ...
    async def get_screener_run(self, run_id: UUID, user_id: UUID) -> ScreenerRunRead: ...
    def list_universes(self) -> list[UniverseInfo]: ...
    def list_themes(self) -> list[ThemeInfo]: ...
    def get_theme(self, theme_id: str) -> ThemeInfo: ...
    async def generate_theme_cards(self, theme_id: str, user_id: UUID) -> ThemeCardsResponse: ...
```

---

## 4. 业务异常（`backend/app/modules/screener/exceptions.py`）

| 异常类 | 继承基类 | 对应 HTTP 状态码 | 对应 ErrorCode | 说明 |
|---|---|---|---|---|
| `ScreenerError` | `AppError` | 500 | `INTERNAL_ERROR` | screener 模块基类 |
| `UniverseNotFoundError` | `ScreenerError` | 404 | `NOT_FOUND` | 指定股票池不存在 |
| `StrategyNotFoundError` | `ScreenerError` | 404 | `NOT_FOUND` | 指定预设策略不存在 |
| `ThemeNotFoundError` | `ScreenerError` | 404 | `NOT_FOUND` | 指定主题不存在 |
| `ScreenerRunNotFoundError` | `ScreenerError` | 404 | `NOT_FOUND` | 筛选任务记录不存在或非本租户 |
| `WatchlistNotFoundError` | `ScreenerError` | 404 | `NOT_FOUND` | 自选清单不存在或非本租户 |
| `WatchlistItemNotFoundError` | `ScreenerError` | 404 | `NOT_FOUND` | 自选标的不存在 |
| `DuplicateWatchlistItemError` | `ScreenerError` | 409 | `STATE_CONFLICT` | 自选清单中已存在该标的 |
| `ScreenerExecutionError` | `ScreenerError` | 500 | `INTERNAL_ERROR` | 筛选引擎批量执行致命异常 |

---

## 5. REST API 端点规范（`backend/app/modules/screener/api.py`）

| 方法 | 路径 | 鉴权要求 | 说明 | 对应 Issue |
|---|---|---|---|---|
| `GET` | `/api/v1/universes` | 必须登录 | 获取可选股票池列表（标普500、纳指100、道指30、自定义） | #154 |
| `POST` | `/api/v1/screener/runs` | 必须登录 | 创建并异步启动策略筛选任务 | #154 |
| `GET` | `/api/v1/screener/runs/{id}` | 必须登录 | 查询筛选任务详情、进度、结果排名及指标快照 | #154 |
| `GET` | `/api/v1/themes` | 必须登录 | 获取系统预设热门主题清单（F9） | #154 |
| `GET` | `/api/v1/themes/{id}` | 必须登录 | 获取指定主题详情与成分标的 | #154 |
| `POST` | `/api/v1/themes/{id}/cards` | 必须登录 | AI 生成指定主题的新手说明卡片（可信溯源校验） | #154 |
| `GET` | `/api/v1/watchlists` | 必须登录 | 获取当前用户的所有自选清单列表 | #154 |
| `POST` | `/api/v1/watchlists` | 必须登录 | 创建新的自选清单 | #154 |
| `GET` | `/api/v1/watchlists/{id}` | 必须登录 | 获取自选清单详情及全部关注标的 | #154 |
| `PUT` | `/api/v1/watchlists/{id}` | 必须登录 | 更新自选清单名称/描述/默认属性 | #154 |
| `DELETE` | `/api/v1/watchlists/{id}` | 必须登录 | 删除自选清单（级联删除 items） | #154 |
| `POST` | `/api/v1/watchlists/{id}/items` | 必须登录 | 向指定自选清单添加关注股票 | #154 |
| `DELETE` | `/api/v1/watchlists/{id}/items/{item_id}` | 必须登录 | 从自选清单移除关注标的 | #154 |
