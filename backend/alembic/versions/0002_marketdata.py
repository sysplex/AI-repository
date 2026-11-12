"""0002_marketdata: create M2 shared market data tables.

Revision ID: 0002_marketdata
Revises: 0001_initial
Create Date: 2026-11-12

Creates shared reference tables without user_id following docs/03-data-model.md §3.2:
- symbols
- bars_daily
- corporate_actions
- fundamentals_snapshots
- financial_statements
- earnings_events
- news_items
- data_snapshots
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_marketdata"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create marketdata shared tables and indexes."""
    # 1. symbols
    op.create_table(
        "symbols",
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("symbol", name="pk_symbols"),
    )

    # 2. bars_daily
    op.create_table(
        "bars_daily",
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("high", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("low", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("close", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("adj_close", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "trade_date", name="pk_bars_daily"),
    )
    op.create_index("ix_bars_daily_trade_date", "bars_daily", ["trade_date"], unique=False)

    # 3. corporate_actions
    op.create_table(
        "corporate_actions",
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("action_type", sa.String(length=16), nullable=False),
        sa.Column("ratio", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "ex_date", "action_type", name="pk_corporate_actions"),
    )

    # 4. fundamentals_snapshots
    op.create_table(
        "fundamentals_snapshots",
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("pe_trailing", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("pe_forward", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("pb", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("ps", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("roe", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("net_margin", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("debt_to_equity", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("market_cap", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("dividend_yield", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("beta", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column(
            "missing_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "as_of", name="pk_fundamentals_snapshots"),
    )

    # 5. financial_statements
    op.create_table(
        "financial_statements",
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column(
            "balance_sheet",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "income_statement",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "cash_flow",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "period_end", "period_type", name="pk_financial_statements"),
    )

    # 6. earnings_events
    op.create_table(
        "earnings_events",
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("eps_estimated", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("eps_actual", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("revenue_estimated", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("revenue_actual", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("guidance", sa.String(length=255), nullable=True),
        sa.Column("reaction_1d_pct", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "report_date", name="pk_earnings_events"),
    )

    # 7. news_items
    op.create_table(
        "news_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_news_items"),
    )
    op.create_index("ix_news_items_symbol_published_at", "news_items", ["symbol", "published_at"], unique=False)

    # 8. data_snapshots
    op.create_table(
        "data_snapshots",
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "missing_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("content_hash", name="pk_data_snapshots"),
    )
    op.create_index("ix_data_snapshots_symbol_as_of", "data_snapshots", ["symbol", "as_of"], unique=False)


def downgrade() -> None:
    """Drop marketdata tables and indexes."""
    op.drop_index("ix_data_snapshots_symbol_as_of", table_name="data_snapshots")
    op.drop_table("data_snapshots")

    op.drop_index("ix_news_items_symbol_published_at", table_name="news_items")
    op.drop_table("news_items")

    op.drop_table("earnings_events")
    op.drop_table("financial_statements")
    op.drop_table("fundamentals_snapshots")
    op.drop_table("corporate_actions")

    op.drop_index("ix_bars_daily_trade_date", table_name="bars_daily")
    op.drop_table("bars_daily")

    op.drop_table("symbols")
