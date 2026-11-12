"""M2 marketdata domain models.

All models are immutable (frozen) and enforce Decimal for monetary/pricing values
and timezone-aware datetimes for temporal fields.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Bar(BaseModel):
    """OHLCV candlestick bar."""

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
    """Realtime or delayed market quote."""

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
    """Company background and sector classification."""

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
    """Valuation, profitability, and balance sheet snapshot metrics."""

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
    """Three core financial statements: balance sheet, income, and cash flow."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    period: Literal["annual", "quarterly"]
    period_end: date
    balance_sheet: dict[str, Any] = Field(default_factory=dict)
    income_statement: dict[str, Any] = Field(default_factory=dict)
    cash_flow: dict[str, Any] = Field(default_factory=dict)


class EarningsEvent(BaseModel):
    """Earnings report event with estimates vs actuals."""

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
    """Historical earnings events collection."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    events: list[EarningsEvent] = Field(default_factory=list)


class NewsItem(BaseModel):
    """Market news item with attribution."""

    model_config = ConfigDict(frozen=True)

    id: str
    symbol: str
    title: str
    summary: str
    source: str
    url: str
    published_at: datetime


class AnalystRatings(BaseModel):
    """Consensus analyst recommendations and price targets."""

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
    """Corporate actions including stock splits and cash dividends."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    ex_date: date
    action_type: Literal["split", "dividend"]
    ratio: Decimal | None = None  # e.g. Decimal("10.0") for 10:1 split
    amount: Decimal | None = None  # dividend amount per share


class FactsSnapshot(BaseModel):
    """Immutable structured fact sheet used for AI input with SHA-256 integrity hash."""

    model_config = ConfigDict(frozen=True)

    content_hash: str
    symbol: str
    as_of: datetime
    scope: list[str]
    facts: dict[str, Any]
    missing_fields: list[str] = Field(default_factory=list)
