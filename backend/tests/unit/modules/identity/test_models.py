"""M1-T01：identity 四张表的 ORM 元数据与 `CONTRACTS §3` 一致性。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from sqlalchemy import DateTime, Table, UniqueConstraint

from app.modules.identity.models import AiUsage, PasswordResetToken, RefreshToken, User

_TABLES = {
    "users": User,
    "refresh_tokens": RefreshToken,
    "password_reset_tokens": PasswordResetToken,
    "ai_usage": AiUsage,
}


def test_all_tables_declared_with_expected_columns() -> None:
    """表名、主键、时间戳与关键列全部存在。"""
    expected_columns: dict[str, set[str]] = {
        "users": {
            "id",
            "email",
            "password_hash",
            "role",
            "status",
            "settings",
            "created_at",
            "updated_at",
        },
        "refresh_tokens": {
            "id",
            "user_id",
            "token_hash",
            "expires_at",
            "revoked_at",
            "created_at",
            "updated_at",
        },
        "password_reset_tokens": {
            "id",
            "user_id",
            "token_hash",
            "expires_at",
            "used_at",
            "created_at",
            "updated_at",
        },
        "ai_usage": {
            "id",
            "user_id",
            "usage_date",
            "calls",
            "tokens_in",
            "tokens_out",
            "cost_usd",
            "created_at",
            "updated_at",
        },
    }
    for table_name, model in _TABLES.items():
        assert model.__tablename__ == table_name
        assert set(model.__table__.columns.keys()) == expected_columns[table_name]
        assert model.__table__.columns["id"].primary_key


def test_private_tables_have_user_id_foreign_key() -> None:
    """三张私有表都有指向 users.id 的级联外键。"""
    for model in (RefreshToken, PasswordResetToken, AiUsage):
        foreign_keys = list(model.__table__.columns["user_id"].foreign_keys)
        assert len(foreign_keys) == 1
        assert foreign_keys[0].target_fullname == "users.id"
        assert foreign_keys[0].ondelete == "CASCADE"


def test_unique_constraints_match_contract() -> None:
    """email 唯一、两类令牌摘要唯一、ai_usage 按用户+日期唯一。"""

    def _unique_column_sets(model: Any) -> list[set[str]]:
        table = cast(Table, model.__table__)
        return [
            set(constraint.columns.keys())
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        ]

    assert {"email"} in _unique_column_sets(User)
    for model in (RefreshToken, PasswordResetToken):
        assert {"token_hash"} in _unique_column_sets(model)
    assert {"user_id", "usage_date"} in _unique_column_sets(AiUsage)


def test_expiry_columns_are_timezone_aware() -> None:
    """所有令牌时间戳为 timestamptz（`docs/07 §5`）。"""
    for model in (RefreshToken, PasswordResetToken):
        for name in ("expires_at", "created_at", "updated_at"):
            column = model.__table__.columns[name]
            assert isinstance(column.type, DateTime)
            assert column.type.timezone is True


def test_migration_revision_and_symmetry() -> None:
    """迁移声明 0001→0002，且 upgrade/downgrade 覆盖同样的 4 张表。"""
    source = (
        Path(__file__).resolve().parents[4] / "alembic" / "versions" / "0002_identity.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0002_identity"' in source
    assert 'down_revision: str | None = "0001_initial"' in source
    for table in _TABLES:
        assert f'"{table}"' in source
    assert 'op.drop_constraint("fk_audit_log_user_id_users"' in source
    assert "op.create_foreign_key(" in source
