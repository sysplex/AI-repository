"""0007_scheduler_notify: M10 调度、提醒与日报表

Revision ID: 0007_scheduler_notify
Revises: 0006_screener
Create Date: 2026-11-17

包含：
- 用户通知渠道表 (notification_channels)
- 智能提醒规则表 (alerts)
- 提醒触发历史日志表 (alert_history)
- 每日市场与持仓简报表 (daily_reports)
严格遵循可逆降级原则 (downgrade)。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_scheduler_notify"
down_revision: str | None = "0006_screener"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "daily_reports",
    "alert_history",
    "alerts",
    "notification_channels",
)


def upgrade() -> None:
    # 1. 用户通知渠道表
    op.create_table(
        "notification_channels",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
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
            name=op.f("fk_notification_channels_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_channels")),
    )
    op.create_index(
        op.f("ix_notification_channels_user_id"),
        "notification_channels",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_channels_user_type",
        "notification_channels",
        ["user_id", "channel_type"],
        unique=False,
    )

    # 2. 智能提醒规则表
    op.create_table(
        "alerts",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=True),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column(
            "conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "channel_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "trigger_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "cooldown_minutes",
            sa.Integer(),
            server_default=sa.text("1440"),
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
            name=op.f("fk_alerts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
    )
    op.create_index(
        op.f("ix_alerts_user_id"),
        "alerts",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alerts_symbol"),
        "alerts",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alerts_status"),
        "alerts",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_alerts_type_status",
        "alerts",
        ["alert_type", "status"],
        unique=False,
    )

    # 3. 提醒触发审计历史表
    op.create_table(
        "alert_history",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=True),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column(
            "triggered_value",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "delivery_status",
            sa.String(length=32),
            server_default=sa.text("'sent'"),
            nullable=False,
        ),
        sa.Column(
            "delivered_channels",
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
            ["alert_id"],
            ["alerts.id"],
            name=op.f("fk_alert_history_alert_id_alerts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_alert_history_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_history")),
    )
    op.create_index(
        op.f("ix_alert_history_alert_id"),
        "alert_history",
        ["alert_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alert_history_user_id"),
        "alert_history",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_alert_history_user_created",
        "alert_history",
        ["user_id", "created_at"],
        unique=False,
    )

    # 4. 每日市场与持仓简报表
    op.create_table(
        "daily_reports",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "payload",
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_daily_reports_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_reports")),
    )
    op.create_index(
        op.f("ix_daily_reports_user_id"),
        "daily_reports",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_daily_reports_report_date"),
        "daily_reports",
        ["report_date"],
        unique=False,
    )
    op.create_index(
        "ix_daily_reports_date_type",
        "daily_reports",
        ["report_date", "report_type"],
        unique=False,
    )
    op.create_index(
        "ix_daily_reports_user_date",
        "daily_reports",
        ["user_id", "report_date"],
        unique=False,
    )


def downgrade() -> None:
    for tbl in _TABLES:
        op.drop_table(tbl)
