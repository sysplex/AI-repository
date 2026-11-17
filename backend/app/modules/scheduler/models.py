"""M10 Scheduler 领域 ORM 实体（T01），`CONTRACTS.md §2.4`。

包含：
- 每日投研与模拟持仓简报 (daily_reports)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPkMixin

__all__ = [
    "DailyReport",
]


class DailyReport(Base, UUIDPkMixin):
    """每日市场大盘与模拟持仓简报快照实体。"""

    __tablename__ = "daily_reports"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    report_date: Mapped[date] = mapped_column(
        Date(),
        nullable=False,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_daily_reports_date_type", "report_date", "report_type"),
        Index("ix_daily_reports_user_date", "user_id", "report_date"),
        {"extend_existing": True},
    )
