# M4 接口契约（CONTRACTS）

> 模拟盘引擎（simbroker）权威接线图。每个任务严格按本契约的**签名与行为**实现。
> 对应设计：`docs/02-architecture.md§5`、`docs/03-data-model.md§3.3`、`docs/04-modules.md#m4`、`docs/05-api-spec.md§2.4`、`docs/08-test-plan.md§6`。

---

## 0. 全局与数据约定

| 项 | 约定 |
|---|---|
| 语言/版本 | Python 3.12；必须通过 `mypy --strict` |
| 金额与价格 | `Decimal`，严禁使用 `float`（持仓、成本、订单价格、点位、手续费、净值） |
| 日期与时间 | 时间为带时区的 UTC `datetime`；交易日为 `date`（美东交易日） |
| 幂等性约定 | 下单接口必须传入 `Idempotency-Key` 请求头，数据库 `(account_id, idempotency_key)` 唯一约束防重复提交 |
| 架构边界 | `simbroker` 模块严格遵循六边形端口架构，不得直接 `import app.modules.marketdata`，通过注入端口协议解耦 |
| 异常规范 | 业务拒绝抛出 `app.core.errors.ValidationFailed` / `ConflictError` / `NotFoundError` |

---

## 1. 领域模型与 DTO（`app/modules/simbroker/schemas.py`）

```python
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

AccountStatus = Literal["active", "suspended", "closed"]
OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit", "stop"]
TimeInForce = Literal["day", "gtc"]
OrderStatus = Literal["pending", "accepted", "filled", "cancelled", "rejected", "expired"]
FeeType = Literal["zero", "per_share", "bps", "tiered"]

class FeeModelConfig(BaseModel):
    """手续费模型配置"""
    model_config = ConfigDict(frozen=True)

    type: FeeType = "zero"
    per_share: Decimal = Decimal("0")
    bps: Decimal = Decimal("0")
    min_fee: Decimal = Decimal("0")
    max_fee: Decimal | None = None

class AccountCreate(BaseModel):
    """创建模拟盘账户请求"""
    name: str = Field(min_length=1, max_length=100)
    initial_cash: Decimal = Field(default=Decimal("100000.00"), gt=0)
    fee_model: FeeModelConfig = Field(default_factory=FeeModelConfig)
    slippage_bps: Decimal = Field(default=Decimal("5.0"), ge=0)
    pdt_enabled: bool = True

class AccountResponse(BaseModel):
    """模拟盘账户基本信息"""
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    user_id: UUID
    name: str
    initial_cash: Decimal
    cash: Decimal
    fee_model: FeeModelConfig
    slippage_bps: Decimal
    pdt_enabled: bool
    status: AccountStatus
    created_at: datetime
    updated_at: datetime

class AccountOverview(BaseModel):
    """账户概览（实时计算市值与净值）"""
    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    status: AccountStatus
    initial_cash: Decimal
    cash: Decimal
    market_value: Decimal
    equity: Decimal
    daily_pnl: Decimal
    daily_pnl_pct: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal
    pdt_day_trades_count: int
    pdt_warning: bool

class DepositRequest(BaseModel):
    """出入金请求"""
    amount: Decimal = Field(gt=0)

class OrderCreate(BaseModel):
    """创建订单请求"""
    symbol: str = Field(min_length=1, max_length=20)
    side: OrderSide
    type: OrderType
    qty: Decimal = Field(gt=0)
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    tif: TimeInForce = "day"
    note: str | None = None
    ai_report_id: UUID | None = None
    source: str = "manual"

class OrderResponse(BaseModel):
    """订单详情响应"""
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    user_id: UUID
    account_id: UUID
    symbol: str
    side: OrderSide
    type: OrderType
    qty: Decimal
    limit_price: Decimal | None
    stop_price: Decimal | None
    tif: TimeInForce
    status: OrderStatus
    idempotency_key: str
    source: str
    ai_report_id: UUID | None
    note: str | None
    reject_reason: str | None = None
    created_at: datetime
    updated_at: datetime

class PositionResponse(BaseModel):
    """持仓响应"""
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    account_id: UUID
    symbol: str
    qty: Decimal
    avg_cost: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    realized_pnl: Decimal
    weight_pct: Decimal

class TradeResponse(BaseModel):
    """成交记录响应"""
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    user_id: UUID
    account_id: UUID
    order_id: UUID
    symbol: str
    side: OrderSide
    qty: Decimal
    price: Decimal
    fee: Decimal
    realized_pnl: Decimal
    executed_at: datetime

class EquitySnapshotResponse(BaseModel):
    """每日净值快照响应"""
    model_config = ConfigDict(from_attributes=True, frozen=True)

    account_id: UUID
    trade_date: date
    cash: Decimal
    market_value: Decimal
    equity: Decimal
    drawdown: Decimal

class TradeJournalUpdate(BaseModel):
    """交易日志录入与复盘"""
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    emotion: str | None = None

class TradeJournalResponse(BaseModel):
    """交易日志响应"""
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    trade_id: UUID
    notes: str | None
    tags: list[str]
    emotion: str | None
    created_at: datetime
    updated_at: datetime

class PerformanceMetrics(BaseModel):
    """业绩表现汇总指标"""
    model_config = ConfigDict(frozen=True)

    account_id: UUID
    initial_cash: Decimal
    current_equity: Decimal
    total_return: Decimal
    total_return_pct: Decimal
    max_drawdown: Decimal
    win_rate: Decimal
    profit_loss_ratio: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    benchmark_return_pct: Decimal | None = None
    alpha: Decimal | None = None
    beta: Decimal | None = None
    equity_curve: list[EquitySnapshotResponse] = Field(default_factory=list)

class RiskOverview(BaseModel):
    """持仓风险体检"""
    model_config = ConfigDict(frozen=True)

    account_id: UUID
    cash_ratio: Decimal
    single_stock_weights: dict[str, Decimal]
    top_positions: list[tuple[str, Decimal]]
    sector_weights: dict[str, Decimal]
    pdt_day_trades_count: int
    pdt_warning: bool
```

---

## 2. 外部端口协议（`app/modules/simbroker/ports.py`）

```python
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, Sequence
from uuid import UUID

from app.modules.simbroker.schemas import (
    AccountOverview,
    OrderCreate,
    OrderResponse,
    PositionResponse,
    TradeResponse,
)

class Broker(Protocol):
    """系统统一定义的 Broker 端口协议（docs/02-architecture.md）"""
    name: str

    def submit_order(
        self, account_id: str, req: OrderCreate, idempotency_key: str
    ) -> OrderResponse: ...

    def cancel_order(self, account_id: str, order_id: str) -> OrderResponse: ...

    def get_account(self, account_id: str) -> AccountOverview: ...

    def get_positions(self, account_id: str) -> Sequence[PositionResponse]: ...

    def process_bar(self, account_id: str, bar_time: datetime) -> Sequence[TradeResponse]: ...

class MarketDataFeedProtocol(Protocol):
    """行情数据注入协议（避免直接依赖 marketdata 模块实体）"""
    def get_latest_price(self, symbol: str) -> Decimal | None: ...

    def get_daily_bar(self, symbol: str, trade_date: date) -> Any | None: ...

    def get_sp500_return(self, start_date: date, end_date: date) -> Decimal | None: ...

    def get_symbol_sector(self, symbol: str) -> str | None: ...

class CorporateActionFeedProtocol(Protocol):
    """公司行动数据源协议（拆股与分红）"""
    def get_split_ratio(self, symbol: str, trade_date: date) -> Decimal | None: ...

    def get_dividend_per_share(self, symbol: str, trade_date: date) -> Decimal | None: ...
```

---

## 3. 撮合与不变量规则规范

1. **撮合核心逻辑**：
   - 市价单：成交价为 `bar.open + (slippage if side == 'buy' else -slippage)`。
   - 限价买：若 `bar.open <= limit_price`，按 `bar.open` 成交；否则若 `bar.low <= limit_price`，按 `limit_price` 成交；否则不成交。
   - 限价卖：若 `bar.open >= limit_price`，按 `bar.open` 成交；否则若 `bar.high >= limit_price`，按 `limit_price` 成交；否则不成交。
   - 止损买：当 `bar.high >= stop_price` 触发；成交价为 `max(stop_price, bar.open)`。
   - 止损卖：当 `bar.low <= stop_price` 触发；成交价为 `min(stop_price, bar.open)`。
   - 行情缺失：若缺失当天行情 Bar，订单严格保持 `accepted` 并记录 warning 警报，严禁用陈旧价格撮合。
2. **财务不变量**：
   - 现金守恒：`cash == initial_cash + deposits - withdrawals + sum(sell_proceeds) - sum(buy_costs) - sum(fees)`
   - 净值恒等：`equity == cash + market_value`
   - 不超卖：任何股票持仓数量 `qty >= 0`。
   - 拆股保值：股票拆股后 `qty * ratio`，`avg_cost / ratio`，持仓总市值保持恒等。
