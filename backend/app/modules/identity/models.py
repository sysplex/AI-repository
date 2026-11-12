"""M1 identity ORM 模型（T01），`CONTRACTS.md §3`。

四张用户私有表；`users` 是主体，其余三张通过 `user_id` 外键级联删除。
M1 不写 `ai_usage`（属 M5），但先建表供 `/me/usage` 只读视图使用（裁定 C6）。
所有时间列为 `timestamptz`（UTC），主键由 PG 的 `gen_random_uuid()` 生成。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPkMixin

__all__ = ["AiUsage", "PasswordResetToken", "RefreshToken", "User"]

_USER_FK = "users.id"


class User(Base, UUIDPkMixin, TimestampMixin):
    """用户主表；email 全局唯一（登录查询），settings 为 JSONB。"""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="user", server_default=text("'user'")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default=text("'active'")
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB(), nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class RefreshToken(Base, UUIDPkMixin, TimestampMixin):
    """刷新令牌；只存 SHA-256 摘要，吊销即时生效（`revoked_at`）。"""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey(_USER_FK, ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_refresh_tokens_user_id", "user_id"),)


class PasswordResetToken(Base, UUIDPkMixin, TimestampMixin):
    """密码重置令牌；一次性（`used_at`），只存 SHA-256 摘要（裁定 C3）。"""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey(_USER_FK, ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_password_reset_tokens_user_id", "user_id"),)


class AiUsage(Base, UUIDPkMixin, TimestampMixin):
    """按用户/日期聚合的 AI 用量；M1 只读，写入与配额扣减属 M5（裁定 C6）。"""

    __tablename__ = "ai_usage"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey(_USER_FK, ondelete="CASCADE"), nullable=False
    )
    usage_date: Mapped[date] = mapped_column(Date(), nullable=False)
    calls: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default=text("0")
    )
    tokens_in: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default=text("0")
    )
    tokens_out: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default=text("0")
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default=text("0")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "usage_date", name="uq_ai_usage_user_id_usage_date"),
    )
