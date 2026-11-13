"""0005_ai: M5 AI 核心框架表

Revision ID: 0005_ai
Revises: 0004_simbroker
Create Date: 2026-11-13

包含 AI 分析报告记录 (ai_reports)
与建议事后表现追踪 (ai_recommendation_outcomes) 2 张核心表。
注：事实数据快照表 (data_snapshots) 属于共享市场数据，已由 M2 (0002_marketdata) 创建，
ai_reports.data_snapshot_id 外键关联至 data_snapshots.content_hash。
严格遵循可逆降级原则 (downgrade)。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_ai"
down_revision: str | None = "0004_simbroker"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "ai_recommendation_outcomes",
    "ai_reports",
)


def upgrade() -> None:
    # 1. AI 分析报告记录表
    op.create_table(
        "ai_reports",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("use_case", sa.String(length=64), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("cache_key", sa.String(length=128), nullable=False),
        sa.Column("data_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=18, scale=6),
            server_default=sa.text("0.000000"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["data_snapshot_id"],
            ["data_snapshots.content_hash"],
            name=op.f("fk_ai_reports_data_snapshot_id_data_snapshots"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_reports_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_reports")),
    )
    op.create_index(
        op.f("ix_ai_reports_cache_key"),
        "ai_reports",
        ["cache_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_reports_data_snapshot_id"),
        "ai_reports",
        ["data_snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_reports_use_case"),
        "ai_reports",
        ["use_case"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_reports_user_id"),
        "ai_reports",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_reports_use_case_cache",
        "ai_reports",
        ["use_case", "cache_key"],
        unique=False,
    )
    op.create_index(
        "ix_ai_reports_user_created",
        "ai_reports",
        ["user_id", "created_at"],
        unique=False,
    )

    # 2. 投资建议事后表现评估追踪表
    op.create_table(
        "ai_recommendation_outcomes",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column(
            "price_at_report",
            sa.Numeric(precision=18, scale=4),
            nullable=False,
        ),
        sa.Column(
            "ret_5d",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
        ),
        sa.Column(
            "ret_20d",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
        ),
        sa.Column(
            "ret_60d",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
        ),
        sa.Column(
            "ret_vs_spy_20d",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["ai_reports.id"],
            name=op.f("fk_ai_recommendation_outcomes_report_id_ai_reports"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_recommendation_outcomes")),
    )
    op.create_index(
        op.f("ix_ai_recommendation_outcomes_report_id"),
        "ai_recommendation_outcomes",
        ["report_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_recommendation_outcomes_symbol"),
        "ai_recommendation_outcomes",
        ["symbol"],
        unique=False,
    )


def downgrade() -> None:
    for tbl in _TABLES:
        op.drop_table(tbl)
