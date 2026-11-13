"""Domain schemas and data transfer objects for the strategy engine (M3 / T01).

Adheres to docs/tasks/M3/CONTRACTS.md §1:
- Strict Pydantic v2 validation with `frozen=True` for immutability.
- Decimal for all currency, price, ratio, and percentage metrics.
- UTC timezone-aware datetimes and ISO dates.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SignalDirection = Literal["long", "flat", "short"]


class Signal(BaseModel):
    """Trading signal produced by a strategy evaluation."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    as_of: date
    direction: SignalDirection
    strength: int = Field(default=0, ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    levels: dict[str, Decimal] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


class EvaluateRequest(BaseModel):
    """Request payload to evaluate strategy signal for a symbol."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    as_of: date
    params: dict[str, Any] = Field(default_factory=dict)


class ScanRequest(BaseModel):
    """Request payload to scan an equity universe for signals."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbols: list[str] = Field(min_length=1)
    as_of: date
    params: dict[str, Any] = Field(default_factory=dict)


class TechnicalSnapshot(BaseModel):
    """Comprehensive technical indicators snapshot for a symbol at a given date."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: date
    sma_20: Decimal | None = None
    sma_50: Decimal | None = None
    sma_200: Decimal | None = None
    ema_12: Decimal | None = None
    ema_26: Decimal | None = None
    rsi_14: Decimal | None = None
    macd: Decimal | None = None
    macd_signal: Decimal | None = None
    macd_hist: Decimal | None = None
    atr_14: Decimal | None = None
    bb_upper: Decimal | None = None
    bb_middle: Decimal | None = None
    bb_lower: Decimal | None = None
    obv: int | None = None
    support: Decimal | None = None
    resistance: Decimal | None = None


class StrategyContext(BaseModel):
    """Context object passed to Strategy.evaluate(), strictly guarding against lookahead bias."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: date
    bars: list[Any]  # Sequence of Bar objects (ts <= as_of)
    fundamentals: Any | None = None  # Fundamentals object from marketdata
    params: dict[str, Any] = Field(default_factory=dict)


class StrategyMetadata(BaseModel):
    """Strategy metadata for catalog listing and dynamic form rendering."""

    model_config = ConfigDict(frozen=True)

    id: str
    display_name: str
    category: Literal["trend", "pullback", "reversal", "value", "growth", "dividend"]
    description: str
    requires: list[str] = Field(default_factory=list)
    default_params: dict[str, Any] = Field(default_factory=dict)


class TradeRecord(BaseModel):
    """Individual trade execution record in a backtest simulation."""

    model_config = ConfigDict(frozen=True)

    trade_date: date
    action: Literal["buy", "sell"]
    price: Decimal
    shares: int
    amount: Decimal
    pnl: Decimal | None = None
    pnl_pct: Decimal | None = None
    reason: str = ""


class EquityPoint(BaseModel):
    """Daily equity curve snapshot point."""

    model_config = ConfigDict(frozen=True)

    trade_date: date
    equity: Decimal
    cash: Decimal
    drawdown_pct: Decimal


class BacktestRequest(BaseModel):
    """Request payload to initiate historical strategy backtest."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    start: date
    end: date
    initial_capital: Decimal = Decimal("100000.00")
    params: dict[str, Any] = Field(default_factory=dict)


class BacktestResult(BaseModel):
    """Aggregated backtest performance metrics, trade logs, and equity curve."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    start: date
    end: date
    initial_capital: Decimal
    final_equity: Decimal
    total_return_pct: Decimal
    annualized_return_pct: Decimal
    max_drawdown_pct: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    total_trades: int
    trades: list[TradeRecord] = Field(default_factory=list)
    equity_curve: list[EquityPoint] = Field(default_factory=list)
