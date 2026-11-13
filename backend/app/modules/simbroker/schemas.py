"""M4 模拟盘 DTO Schema（T01），`CONTRACTS.md §1`。

包含账户、订单、成交、持仓、净值快照、交易日志、绩效表现及风险概览数据传输模型。
金额与比率一律采用高精 Decimal 运算。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AccountCreate",
    "AccountOverview",
    "AccountResponse",
    "AccountStatus",
    "DepositRequest",
    "EquitySnapshotResponse",
    "FeeModelConfig",
    "FeeType",
    "OrderCreate",
    "OrderResponse",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PerformanceMetrics",
    "PositionResponse",
    "RiskOverview",
    "TimeInForce",
    "TradeJournalResponse",
    "TradeJournalUpdate",
    "TradeResponse",
]

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
    pdt_day_trades_count: int = 0
    pdt_warning: bool = False


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
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    tif: TimeInForce
    status: OrderStatus
    idempotency_key: str
    source: str
    ai_report_id: UUID | None = None
    note: str | None = None
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
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    emotion: str | None = None
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
    single_stock_weights: dict[str, Decimal] = Field(default_factory=dict)
    top_positions: list[tuple[str, Decimal]] = Field(default_factory=list)
    sector_weights: dict[str, Decimal] = Field(default_factory=dict)
    pdt_day_trades_count: int = 0
    pdt_warning: bool = False
