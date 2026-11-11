"""审计日志模型与写入入口（M0 / T04），`CONTRACTS.md §5`。

`audit_log` 只增不改；`detail` 为 JSONB 且限制 ≤ 8 KiB，避免把大对象写进库。
此阶段 `user_id` 不加外键（users 表要等 M1）。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPkMixin

__all__ = ["AuditLog", "MAX_DETAIL_BYTES", "record_audit"]

MAX_DETAIL_BYTES = 8 * 1024


class AuditLog(Base, UUIDPkMixin):
    """审计日志；字段与 `docs/03-data-model.md §3.1` 一致。"""

    __tablename__ = "audit_log"

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB(),
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_audit_log_user_id_created_at", "user_id", "created_at"),
        Index("ix_audit_log_action_created_at", "action", "created_at"),
    )


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    ip: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """向当前 session 追加一条审计记录（不 commit，由 get_session 统一提交）。

    `detail` 序列化后超过 8 KiB 直接抛 `ValueError`，不写库。
    """
    payload: dict[str, Any] = dict(detail) if detail else {}
    size = len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
    if size > MAX_DETAIL_BYTES:
        raise ValueError(f"audit detail 超过 {MAX_DETAIL_BYTES} 字节限制")
    session.add(
        AuditLog(
            action=action,
            user_id=user_id,
            entity=entity,
            entity_id=entity_id,
            ip=ip,
            detail=payload,
        )
    )
    await session.flush()
