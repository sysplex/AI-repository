"""M4 模拟盘 ORM 模型（T01），`CONTRACTS.md §1`。

包含虚拟账户、订单、成交记录、持仓、净值快照与交易日志 6 张私有表。
所有金额与成本严格使用 Numeric (Decimal)，所有时间均带时区 (timestamptz)。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPkMixin

__all__ = [
    "EquitySnapshot",
    "SimAccount",
    "SimOrder",
    "SimPosition",
    "SimTrade",
    "TradeJournal",
]


class SimAccount(Base, UUIDPkMixin, TimestampMixin):
    """模拟盘账户；支持配置手续费模型、滑点基点与 PDT 规则控制。"""

    __tablename__ = "sim_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    initial_cash: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("100000.00"),
        server_default=text("100000.0000"),
    )
    cash: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("100000.00"),
        server_default=text("100000.0000"),
    )
    fee_model: Mapped[dict[str, Any]] = mapped_column(
        JSONB(),
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    slippage_bps: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        default=Decimal("5.0"),
        server_default=text("5.0000"),
    )
    pdt_enabled: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )

    __table_args__ = (Index("ix_sim_accounts_user_id", "user_id"),)


class SimOrder(Base, UUIDPkMixin, TimestampMixin):
    """模拟盘订单；具备 idempotency_key 唯一约束防止重复提交。"""

    __tablename__ = "sim_orders"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("sim_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # buy, sell
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # market, limit, stop
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    tif: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="day",
        server_default=text("'day'"),
    )  # day, gtc
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )  # pending, accepted, filled, cancelled, rejected, expired
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="manual",
        server_default=text("'manual'"),
    )
    ai_report_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "idempotency_key",
            name="uq_sim_orders_account_id_idempotency_key",
        ),
        Index("ix_sim_orders_account_id", "account_id"),
        Index("ix_sim_orders_user_id", "user_id"),
        Index("ix_sim_orders_account_status", "account_id", "status"),
    )


class SimTrade(Base, UUIDPkMixin):
    """模拟盘成交明细；记录成交单价、实际手续费及结转已实现盈亏。"""

    __tablename__ = "sim_trades"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("sim_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("sim_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # buy, sell
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fee: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0.0000"),
    )
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0.0000"),
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_sim_trades_account_id", "account_id"),
        Index("ix_sim_trades_order_id", "order_id"),
        Index("ix_sim_trades_account_symbol", "account_id", "symbol"),
    )


class SimPosition(Base, UUIDPkMixin, TimestampMixin):
    """当前持仓；基于加权平均成本法（Weighted Average Cost），(account_id, symbol) 唯一。"""

    __tablename__ = "sim_positions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("sim_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0.0000"),
    )
    avg_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0.0000"),
    )
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0.0000"),
    )

    __table_args__ = (
        UniqueConstraint("account_id", "symbol", name="uq_sim_positions_account_id_symbol"),
        Index("ix_sim_positions_account_id", "account_id"),
    )


class EquitySnapshot(Base):
    """每日收盘净值快照；主键复合 (account_id, trade_date)。"""

    __tablename__ = "equity_snapshots"

    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("sim_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    trade_date: Mapped[date] = mapped_column(Date(), primary_key=True)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    drawdown: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0.000000"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (Index("ix_equity_snapshots_account_date", "account_id", "trade_date"),)


class TradeJournal(Base, UUIDPkMixin, TimestampMixin):
    """交易复盘日志；与成交记录一对一绑定。"""

    __tablename__ = "trade_journal"

    trade_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("sim_trades.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        JSONB(),
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    emotion: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (Index("ix_trade_journal_trade_id", "trade_id"),)
