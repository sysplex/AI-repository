"""0006_screener: M8 筛选器与主题自选表

Revision ID: 0006_screener
Revises: 0005_ai
Create Date: 2026-11-15

包含：
- 筛选运行记录表 (screener_runs)
- 筛选标的结果表 (screener_results)
- 用户自选清单表 (watchlists)
- 自选关注标的表 (watchlist_items)
严格遵循可逆降级原则 (downgrade)。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_screener"
down_revision: str | None = "0005_ai"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "watchlist_items",
    "watchlists",
    "screener_results",
    "screener_runs",
)


def upgrade() -> None:
    # 1. 策略筛选运行记录表
    op.create_table(
        "screener_runs",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("universe", sa.String(length=64), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "total_symbols",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "matched_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "failed_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_screener_runs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_screener_runs")),
    )
    op.create_index(
        op.f("ix_screener_runs_user_id"),
        "screener_runs",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_screener_runs_strategy_id"),
        "screener_runs",
        ["strategy_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_screener_runs_universe"),
        "screener_runs",
        ["universe"],
        unique=False,
    )
    op.create_index(
        op.f("ix_screener_runs_status"),
        "screener_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_screener_runs_user_id_created_at",
        "screener_runs",
        ["user_id", "created_at"],
        unique=False,
    )

    # 2. 策略筛选结果单项表
    op.create_table(
        "screener_results",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("signal", sa.String(length=32), nullable=False),
        sa.Column(
            "metrics_snapshot",
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
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["screener_runs.id"],
            name=op.f("fk_screener_results_run_id_screener_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_screener_results")),
    )
    op.create_index(
        op.f("ix_screener_results_run_id"),
        "screener_results",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_screener_results_symbol"),
        "screener_results",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_screener_results_run_id_rank",
        "screener_results",
        ["run_id", "rank"],
        unique=False,
    )

    # 3. 用户自选清单表
    op.create_table(
        "watchlists",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "description",
            sa.String(length=255),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_watchlists_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watchlists")),
        sa.UniqueConstraint(
            "user_id",
            "name",
            name=op.f("uq_watchlists_user_id_name"),
        ),
    )
    op.create_index(
        op.f("ix_watchlists_user_id"),
        "watchlists",
        ["user_id"],
        unique=False,
    )

    # 4. 自选关注标的表
    op.create_table(
        "watchlist_items",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("watchlist_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column(
            "notes",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("target_price", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column(
            "theme_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["watchlist_id"],
            ["watchlists.id"],
            name=op.f("fk_watchlist_items_watchlist_id_watchlists"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watchlist_items")),
        sa.UniqueConstraint(
            "watchlist_id",
            "symbol",
            name=op.f("uq_watchlist_items_watchlist_id_symbol"),
        ),
    )
    op.create_index(
        op.f("ix_watchlist_items_watchlist_id"),
        "watchlist_items",
        ["watchlist_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_watchlist_items_symbol"),
        "watchlist_items",
        ["symbol"],
        unique=False,
    )


def downgrade() -> None:
    for tbl in _TABLES:
        op.drop_table(tbl)
