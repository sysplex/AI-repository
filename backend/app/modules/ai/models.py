"""M5 AI 核心框架 ORM 实体（T01），`CONTRACTS.md §3`。

包含 AI 分析报告记录 (ai_reports)
与投资建议事后表现追踪 (ai_recommendation_outcomes) 核心实体。
注：事实数据快照表 (data_snapshots) 属于共享市场数据，已由 M2 (0002_marketdata) 创建，
ai_reports 通过 ForeignKey("data_snapshots.content_hash") 引用其唯一 content_hash。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPkMixin

__all__ = [
    "AIRecommendationOutcome",
    "AIReport",
]


class AIReport(Base, UUIDPkMixin):
    """AI 报告实体；记录用户请求、用例、参数、缓存键、模型、Token 成本与生成结果。"""

    __tablename__ = "ai_reports"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    use_case: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    cache_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    data_snapshot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("data_snapshots.content_hash", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0.000000"),
        server_default=text("0.000000"),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_ai_reports_user_created", "user_id", "created_at"),
        Index("ix_ai_reports_use_case_cache", "use_case", "cache_key"),
    )


class AIRecommendationOutcome(Base, UUIDPkMixin):
    """AI 投资建议事后表现评估追踪表（5/20/60 日绝对表现与相对 SPY 超额）。"""

    __tablename__ = "ai_recommendation_outcomes"

    report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("ai_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    price_at_report: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    ret_5d: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ret_20d: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ret_60d: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ret_vs_spy_20d: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
