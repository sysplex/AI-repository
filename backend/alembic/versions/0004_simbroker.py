"""0004_simbroker: M4 模拟盘引擎核心表

Revision ID: 0004_simbroker
Revises: 0003_identity
Create Date: 2026-11-13

包含虚拟账户 (sim_accounts)、订单 (sim_orders)、成交 (sim_trades)、
持仓 (sim_positions)、每日净值快照 (equity_snapshots) 与交易日志 (trade_journal) 6 张表。
严格遵循可逆降级原则 (downgrade)。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_simbroker"
down_revision: str | None = "0003_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "trade_journal",
    "equity_snapshots",
    "sim_positions",
    "sim_trades",
    "sim_orders",
    "sim_accounts",
)


def _timestamps() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    # 1. 模拟盘账户表
    op.create_table(
        "sim_accounts",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "initial_cash",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("100000.0000"),
            nullable=False,
        ),
        sa.Column(
            "cash",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("100000.0000"),
            nullable=False,
        ),
        sa.Column(
            "fee_model",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "slippage_bps",
            sa.Numeric(precision=10, scale=4),
            server_default=sa.text("5.0000"),
            nullable=False,
        ),
        sa.Column(
            "pdt_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sim_accounts_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sim_accounts"),
    )
    op.create_index("ix_sim_accounts_user_id", "sim_accounts", ["user_id"], unique=False)

    # 2. 模拟盘订单表
    op.create_table(
        "sim_orders",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("qty", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("limit_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("stop_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column(
            "tif", sa.String(length=8), server_default=sa.text("'day'"), nullable=False
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default=sa.text("'manual'"),
            nullable=False,
        ),
        sa.Column("ai_report_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sim_orders_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["sim_accounts.id"],
            name="fk_sim_orders_account_id_sim_accounts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sim_orders"),
        sa.UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="uq_sim_orders_account_id_idempotency_key",
        ),
    )
    op.create_index("ix_sim_orders_user_id", "sim_orders", ["user_id"], unique=False)
    op.create_index("ix_sim_orders_account_id", "sim_orders", ["account_id"], unique=False)
    op.create_index(
        "ix_sim_orders_account_status",
        "sim_orders",
        ["account_id", "status"],
        unique=False,
    )

    # 3. 模拟盘成交明细表
    op.create_table(
        "sim_trades",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("qty", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "fee",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0.0000"),
            nullable=False,
        ),
        sa.Column(
            "realized_pnl",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0.0000"),
            nullable=False,
        ),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sim_trades_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["sim_accounts.id"],
            name="fk_sim_trades_account_id_sim_accounts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["sim_orders.id"],
            name="fk_sim_trades_order_id_sim_orders",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sim_trades"),
    )
    op.create_index("ix_sim_trades_account_id", "sim_trades", ["account_id"], unique=False)
    op.create_index("ix_sim_trades_order_id", "sim_trades", ["order_id"], unique=False)
    op.create_index(
        "ix_sim_trades_account_symbol",
        "sim_trades",
        ["account_id", "symbol"],
        unique=False,
    )

    # 4. 模拟盘持仓表
    op.create_table(
        "sim_positions",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column(
            "qty",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0.0000"),
            nullable=False,
        ),
        sa.Column(
            "avg_cost",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0.0000"),
            nullable=False,
        ),
        sa.Column(
            "realized_pnl",
            sa.Numeric(precision=18, scale=4),
            server_default=sa.text("0.0000"),
            nullable=False,
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sim_positions_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["sim_accounts.id"],
            name="fk_sim_positions_account_id_sim_accounts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sim_positions"),
        sa.UniqueConstraint(
            "account_id", "symbol", name="uq_sim_positions_account_id_symbol"
        ),
    )
    op.create_index(
        "ix_sim_positions_account_id", "sim_positions", ["account_id"], unique=False
    )

    # 5. 每日收盘净值快照表
    op.create_table(
        "equity_snapshots",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("cash", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("market_value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("equity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "drawdown",
            sa.Numeric(precision=10, scale=6),
            server_default=sa.text("0.000000"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["sim_accounts.id"],
            name="fk_equity_snapshots_account_id_sim_accounts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "trade_date", name="pk_equity_snapshots"),
    )
    op.create_index(
        "ix_equity_snapshots_account_date",
        "equity_snapshots",
        ["account_id", "trade_date"],
        unique=False,
    )

    # 6. 交易复盘日志表
    op.create_table(
        "trade_journal",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("trade_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("emotion", sa.String(length=32), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["trade_id"],
            ["sim_trades.id"],
            name="fk_trade_journal_trade_id_sim_trades",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trade_journal"),
        sa.UniqueConstraint("trade_id", name="uq_trade_journal_trade_id"),
    )
    op.create_index("ix_trade_journal_trade_id", "trade_journal", ["trade_id"], unique=False)


def downgrade() -> None:
    for table in _TABLES:
        op.drop_table(table)
