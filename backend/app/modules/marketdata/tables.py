"""SQLAlchemy 2.0 mapped tables for M2 shared market data.

All tables are shared reference data across all users (no user_id column)
following docs/03-data-model.md §3.2.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SymbolTable(Base):
    """Symbols table for equity and ETF tickers."""

    __tablename__ = "symbols"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'active'"),
    )  # active / delisted / halted
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class BarDailyTable(Base):
    """Daily OHLCV candlestick bars table."""

    __tablename__ = "bars_daily"
    __table_args__ = (
        PrimaryKeyConstraint("symbol", "trade_date", name="pk_bars_daily"),
        Index("ix_bars_daily_trade_date", "trade_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date(), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    adj_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class CorporateActionTable(Base):
    """Corporate actions: stock splits and cash dividends."""

    __tablename__ = "corporate_actions"
    __table_args__ = (
        PrimaryKeyConstraint("symbol", "ex_date", "action_type", name="pk_corporate_actions"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    ex_date: Mapped[date] = mapped_column(Date(), nullable=False)
    action_type: Mapped[str] = mapped_column(String(16), nullable=False)  # split / dividend
    ratio: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class FundamentalsSnapshotTable(Base):
    """Valuation and financial ratio snapshot table."""

    __tablename__ = "fundamentals_snapshots"
    __table_args__ = (PrimaryKeyConstraint("symbol", "as_of", name="pk_fundamentals_snapshots"),)

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of: Mapped[date] = mapped_column(Date(), nullable=False)
    pe_trailing: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    pe_forward: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    pb: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    ps: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    roe: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    net_margin: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    dividend_yield: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    beta: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    missing_fields: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class FinancialStatementTable(Base):
    """Quarterly and annual financial statements stored as JSONB."""

    __tablename__ = "financial_statements"
    __table_args__ = (
        PrimaryKeyConstraint("symbol", "period_end", "period_type", name="pk_financial_statements"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    period_end: Mapped[date] = mapped_column(Date(), nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)  # annual / quarterly
    balance_sheet: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    income_statement: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    cash_flow: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class EarningsEventTable(Base):
    """Historical and scheduled earnings events."""

    __tablename__ = "earnings_events"
    __table_args__ = (PrimaryKeyConstraint("symbol", "report_date", name="pk_earnings_events"),)

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    report_date: Mapped[date] = mapped_column(Date(), nullable=False)
    eps_estimated: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    eps_actual: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    revenue_estimated: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    revenue_actual: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    guidance: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reaction_1d_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class NewsItemTable(Base):
    """Market news item records."""

    __tablename__ = "news_items"
    __table_args__ = (Index("ix_news_items_symbol_published_at", "symbol", "published_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class DataSnapshotTable(Base):
    """AI input fact snapshots with SHA-256 hash deduplication."""

    __tablename__ = "data_snapshots"
    __table_args__ = (Index("ix_data_snapshots_symbol_as_of", "symbol", "as_of"),)

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scope: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    missing_fields: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
