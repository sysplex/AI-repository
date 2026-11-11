"""0001_initial: 启用 pgcrypto 并创建 audit_log

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-11

字段与 docs/03-data-model.md §3.1 一致；此阶段 user_id 不加外键（M1 再补）。
两个索引：(user_id, created_at)、(action, created_at)。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """建扩展、建表、建索引。"""
    # PG13+ 自带 gen_random_uuid()；pgcrypto 兼容旧版本且 IF NOT EXISTS 幂等。
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index(
        "ix_audit_log_user_id_created_at",
        "audit_log",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_log_action_created_at",
        "audit_log",
        ["action", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """完整可逆：先删索引，再删表，最后移除扩展。"""
    op.drop_index("ix_audit_log_action_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_user_id_created_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
