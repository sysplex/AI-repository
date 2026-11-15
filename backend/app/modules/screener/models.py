"""M8 筛选器与自选清单 ORM 实体（T01），`CONTRACTS.md §2`。

包含：
- 筛选运行记录 (`screener_runs`)
- 筛选标的结果 (`screener_results`)
- 用户自选清单 (`watchlists`)
- 自选关注标的 (`watchlist_items`)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UUIDPkMixin

__all__ = [
    "ScreenerResult",
    "ScreenerRun",
    "Watchlist",
    "WatchlistItem",
]


class ScreenerRun(Base, UUIDPkMixin):
    """筛选任务实体；记录用户提交的策略筛选任务参数、状态与统计指标。"""

    __tablename__ = "screener_runs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    universe: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
        index=True,
    )
    total_symbols: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    matched_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    failed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    results: Mapped[list[ScreenerResult]] = relationship(
        "ScreenerResult",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ScreenerResult.rank",
    )

    __table_args__ = (Index("ix_screener_runs_user_id_created_at", "user_id", "created_at"),)


class ScreenerResult(Base, UUIDPkMixin):
    """筛选结果单项实体；记录每个入选标的在筛选时刻的得分、排名与指标快照。"""

    __tablename__ = "screener_results"

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("screener_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    signal: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    run: Mapped[ScreenerRun] = relationship("ScreenerRun", back_populates="results")

    __table_args__ = (Index("ix_screener_results_run_id_rank", "run_id", "rank"),)


class Watchlist(Base, UUIDPkMixin, TimestampMixin):
    """用户自选清单实体；支持创建多份清单并设置默认清单。"""

    __tablename__ = "watchlists"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default=text("''"),
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    items: Mapped[list[WatchlistItem]] = relationship(
        "WatchlistItem",
        back_populates="watchlist",
        cascade="all, delete-orphan",
        order_by="WatchlistItem.created_at",
    )

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_watchlists_user_id_name"),)


class WatchlistItem(Base, UUIDPkMixin):
    """自选关注标的实体；关联至自选清单，记录个人备注、目标价与主题标签。"""

    __tablename__ = "watchlist_items"

    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("watchlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    notes: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
    )
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    theme_tags: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    watchlist: Mapped[Watchlist] = relationship("Watchlist", back_populates="items")

    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_items_watchlist_id_symbol"),
    )
