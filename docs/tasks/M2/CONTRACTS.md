# M2 接口契约（CONTRACTS）

> 并行与线性开发的权威接线图。每个任务按这里的**签名与行为**实现，签名不得擅自更改。
> 对应设计：`docs/02-architecture.md§3`、`docs/03-data-model.md§3.2`、`docs/04-modules.md#m2`、`docs/05-api-spec.md§2.2`。

## 0. 全局与数据约定

| 项 | 约定 |
|---|---|
| 语言/版本 | Python 3.12；必须通过 `mypy --strict` |
| 异步规范 | IO 与外部调用一律 `async`；阻塞调用（如 yfinance SDK）必须使用 `asyncio.to_thread` 隔离 |
| 金额与价格 | `Decimal`，禁止使用 `float` |
| 日期与时间 | 时间为带时区的 UTC `datetime`；交易日为 `date`（美东交易日） |
| 外部 SDK 约束 | `yfinance` 仅允许在 `app.modules.marketdata.adapters` 出现 |
| 错误处理 | 统一继承 `AppError`；数据不可用使用 `app.core.errors.DataUnavailable`（HTTP 424） |

---

## 1. 领域模型 `app/modules/marketdata/models.py`（T01）

```python
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

class Bar(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    adj_close: Decimal | None = None

class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    price: Decimal
    change: Decimal
    change_pct: Decimal
    volume: int
    as_of: datetime
    delayed_seconds: int = 0
    stale: bool = False

class CompanyProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    exchange: str
    sector: str
    industry: str
    description: str = ""
    website: str | None = None
    employees: int | None = None
    country: str = "US"

class Fundamentals(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: date
    pe_trailing: Decimal | None = None
    pe_forward: Decimal | None = None
    pb: Decimal | None = None
    ps: Decimal | None = None
    roe: Decimal | None = None
    net_margin: Decimal | None = None
    debt_to_equity: Decimal | None = None
    market_cap: Decimal | None = None
    dividend_yield: Decimal | None = None
    beta: Decimal | None = None
    missing_fields: list[str] = Field(default_factory=list)

class FinancialStatements(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    period: Literal["annual", "quarterly"]
    period_end: date
    balance_sheet: dict[str, Any] = Field(default_factory=dict)
    income_statement: dict[str, Any] = Field(default_factory=dict)
    cash_flow: dict[str, Any] = Field(default_factory=dict)

class EarningsEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    report_date: date
    eps_estimated: Decimal | None = None
    eps_actual: Decimal | None = None
    revenue_estimated: Decimal | None = None
    revenue_actual: Decimal | None = None
    guidance: str | None = None
    reaction_1d_pct: Decimal | None = None

class EarningsHistory(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    events: list[EarningsEvent] = Field(default_factory=list)

class NewsItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    symbol: str
    title: str
    summary: str
    source: str
    url: str
    published_at: datetime

class AnalystRatings(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: date
    consensus_rating: str  # buy / strong_buy / hold / underperform / sell
    target_high: Decimal | None = None
    target_low: Decimal | None = None
    target_mean: Decimal | None = None
    target_median: Decimal | None = None
    analyst_count: int = 0

class CorporateAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    ex_date: date
    action_type: Literal["split", "dividend"]
    ratio: Decimal | None = None    # 拆股比例（如 10.0 表示 10:1 拆股）
    amount: Decimal | None = None   # 每股分红金额

class FactsSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    content_hash: str
    symbol: str
    as_of: datetime
    scope: list[str]
    facts: dict[str, Any]
    missing_fields: list[str] = Field(default_factory=list)
```

---

## 2. 端口契约 `app/modules/marketdata/ports.py`（T01）

```python
from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal, Protocol
from app.modules.marketdata.models import (
    AnalystRatings,
    Bar,
    CompanyProfile,
    CorporateAction,
    EarningsHistory,
    FinancialStatements,
    Fundamentals,
    NewsItem,
    Quote,
)

class DataProvider(Protocol):
    name: str

    async def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> Sequence[Bar]: ...

    async def get_quote(self, symbol: str) -> Quote: ...

    async def get_quotes(self, symbols: Sequence[str]) -> dict[str, Quote]: ...

    async def get_fundamentals(self, symbol: str) -> Fundamentals: ...

    async def get_financial_statements(
        self,
        symbol: str,
        period: Literal["annual", "quarterly"] = "annual",
        limit: int = 10,
    ) -> FinancialStatements: ...

    async def get_earnings(self, symbol: str, limit: int = 8) -> EarningsHistory: ...

    async def get_news(
        self,
        symbol: str,
        limit: int = 20,
        since: datetime | None = None,
    ) -> Sequence[NewsItem]: ...

    async def get_analyst_ratings(self, symbol: str) -> AnalystRatings: ...

    async def get_corporate_actions(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> Sequence[CorporateAction]: ...

    async def get_profile(self, symbol: str) -> CompanyProfile: ...

    async def get_universe(self, name: str) -> Sequence[str]: ...
```

---

## 3. 数据表映射与 Alembic 迁移（T02）

- 文件：`app/modules/marketdata/tables.py`
- 迁移：`alembic/versions/0002_marketdata.py` (down_revision = "0001_initial")
- 遵循 `docs/03-data-model.md §3.2`：共享行情参考数据，**无 user_id**。

| 表名 | 键/索引 | 核心字段说明 |
|---|---|---|
| `symbols` | PK `symbol` | `name`, `exchange`, `sector`, `industry`, `status` |
| `bars_daily` | PK `(symbol, trade_date)` | `open`, `high`, `low`, `close`, `volume`, `adj_close` (NUMERIC(18,6)) |
| `corporate_actions` | PK `(symbol, ex_date, action_type)` | `ratio`, `amount`, `created_at` |
| `fundamentals_snapshots` | PK `(symbol, as_of)` | `pe_trailing`, `pb`, `ps`, `market_cap`, `metrics` (JSONB) |
| `financial_statements` | PK `(symbol, period_end, period_type)`| `balance_sheet`, `income_statement`, `cash_flow` (JSONB) |
| `earnings_events` | PK `(symbol, report_date)` | `eps_actual`, `eps_estimated`, `guidance` |
| `news_items` | PK `id`，索引 `(symbol, published_at)` | `symbol`, `title`, `summary`, `source`, `url`, `published_at` |
| `data_snapshots` | PK `content_hash` | `symbol`, `scope`, `payload` (JSONB), `created_at` |

---

## 4. 适配器与离线回放 `adapters/yfinance.py`（T03）

- 适配器类：`YFinanceAdapter(DataProvider)`
- SDK 调用全部包裹在 `asyncio.to_thread`，不得阻塞事件循环。
- 提供离线 Mock/Fixture 拦截机制：设置环境变量或传参 `fixture_dir`，优先从本地 JSON 回放，避免 CI / 测试时依赖真实雅虎外网。

---

## 5. 缓存与弹性降级 `cache.py`（T04）

- 类：`MarketDataCache(redis_client)`
- 缓存策略：
  - Quote: key `quote:{symbol}`, TTL 60s（美东交易时段）/ 300s（休市时段）。
  - Profile/Fundamentals: key `fundamentals:{symbol}`, TTL 86400s (24h)。
  - Bars: key `bars:{symbol}:{start}:{end}:{interval}`, TTL 3600s。
- 弹性降级机制：
  - 外部超时/网络异常重试 2 次（指数退避，如 200ms, 400ms）；
  - 仍失败时，检查 Redis 中已缓存的历史值（若存在则标记 `stale=True` 返回）；
  - 若无缓存，抛出 `DataUnavailable("外部数据源不可用且无可用缓存")`。

---

## 6. 核心服务与事实提取 `service.py`（T05）

```python
class DataService:
    def __init__(
        self,
        provider: DataProvider,
        cache: MarketDataCache | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None: ...

    async def get_bars(self, symbol: str, start: date, end: date, interval: str = "1d", adjusted: bool = True) -> Sequence[Bar]: ...
    async def get_quote(self, symbol: str) -> Quote: ...
    async def get_quotes(self, symbols: Sequence[str]) -> dict[str, Quote]: ...
    async def get_fundamentals(self, symbol: str) -> Fundamentals: ...
    async def get_profile(self, symbol: str) -> CompanyProfile: ...
    async def get_news(self, symbol: str, limit: int = 20) -> Sequence[NewsItem]: ...
    async def get_universe(self, name: str) -> Sequence[str]: ...
    async def build_facts(self, symbol: str, scope: Sequence[str] | None = None) -> FactsSnapshot: ...
```
- `build_facts` 规则：
  - scope 默认 `["quote", "profile", "fundamentals", "bars"]`；
  - 缺失字段统一标 `null` 并收集入 `missing_fields`；
  - 计算标准化 JSON 字符串的 SHA-256 作为 `content_hash`，并持久化到 `data_snapshots`。

---

## 7. REST API 端点 `api.py`（T06）

路由挂载于 `/api/v1/market`：

| 方法 | 路径 | 参数 | 响应模型 |
|---|---|---|---|
| `GET` | `/quotes` | `symbols: str` (逗号分隔) | `dict[str, Quote]` |
| `GET` | `/bars/{symbol}` | `start: date, end: date, interval: str = "1d"` | `list[Bar]` |
| `GET` | `/profile/{symbol}` | 路径参数 | `CompanyProfile` |
| `GET` | `/fundamentals/{symbol}` | 路径参数 | `Fundamentals` |
| `GET` | `/news/{symbol}` | `limit: int = 20` | `list[NewsItem]` |
| `GET` | `/universe/{name}` | 路径参数 (sp500/nasdaq100) | `list[str]` |
| `POST` | `/facts/{symbol}` | 请求体可选 `scope` | `FactsSnapshot` |
