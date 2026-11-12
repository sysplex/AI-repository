"""0003_identity: M1 用户与多租户表 + audit_log 外键

Revision ID: 0003_identity
Revises: 0002_marketdata
Create Date: 2026-11-12

`CONTRACTS.md §3`。M0 的 `0001_initial.py` 注释写明「user_id 不加外键（M1 再补）」，
本迁移补上该外键（接缝 S1）：加约束前把历史孤儿 user_id 置 NULL，避免迁移失败。

并行模块约定（已在 #12 登记）：M2-T02 先行合入 `0002_marketdata.py`（同样基于
`0001_initial`）。M1 作为后合并者改为 `0003_identity` 并指向 `0002_marketdata`，
保证全仓库始终是单一 Alembic head；不得再把本文件改回 0002。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_identity"
down_revision: str | None = "0002_marketdata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "refresh_tokens",
    "password_reset_tokens",
    "ai_usage",
    "users",
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    ]


def upgrade() -> None:
    """建 4 张私有表、索引与 audit_log 外键。"""
    op.create_table(
        "users",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), server_default=sa.text("'user'"), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index(
        "ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_password_reset_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_password_reset_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),
    )
    op.create_index(
        "ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"], unique=False
    )

    op.create_table(
        "ai_usage",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tokens_in", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=18, scale=6), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_ai_usage_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_usage"),
        sa.UniqueConstraint(
            "user_id", "usage_date", name="uq_ai_usage_user_id_usage_date"
        ),
    )

    # 接缝 S1：M0 冒烟数据可能留下不指向真实用户的 user_id，先清理再加外键。
    op.execute(
        "UPDATE audit_log SET user_id = NULL "
        "WHERE user_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM users WHERE users.id = audit_log.user_id)"
    )
    op.create_foreign_key(
        "fk_audit_log_user_id_users",
        "audit_log",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """完整可逆：先删外键与子表，最后删 users；0001 的 audit_log 保持不变。"""
    op.drop_constraint("fk_audit_log_user_id_users", "audit_log", type_="foreignkey")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    for table in _TABLES:
        op.drop_table(table)
