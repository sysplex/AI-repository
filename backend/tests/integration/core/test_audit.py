"""M0-T04 审计表与 record_audit 测试。

真实库用例改用 T10 共享 `db_engine` fixture（连接串、迁移、skip 提示见 conftest）。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB

from app.core import db as db_module
from app.core.audit import MAX_DETAIL_BYTES, AuditLog, record_audit


def test_audit_log_table_matches_data_model() -> None:
    table: Any = AuditLog.__table__
    assert table.name == "audit_log"
    assert {column.name for column in table.columns} == {
        "id",
        "user_id",
        "action",
        "entity",
        "entity_id",
        "ip",
        "detail",
        "created_at",
    }
    assert isinstance(table.c.detail.type, JSONB)
    assert table.c.action.nullable is False
    assert table.c.detail.nullable is False
    assert table.c.user_id.nullable is True
    assert table.c.created_at.type.timezone is True
    # M1 才补 users 外键，本阶段必须为空
    assert list(table.foreign_keys) == []

    indexes = {
        index.name: tuple(column.name for column in index.columns) for index in table.indexes
    }
    assert indexes["ix_audit_log_user_id_created_at"] == ("user_id", "created_at")
    assert indexes["ix_audit_log_action_created_at"] == ("action", "created_at")
    assert table.primary_key.columns.keys() == ["id"]
    assert "gen_random_uuid" in str(table.c.id.server_default.arg.text)


async def test_record_audit_adds_and_flushes() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    user_id = uuid.uuid4()
    await record_audit(
        session,
        action="login",
        user_id=user_id,
        entity="user",
        entity_id="42",
        ip="127.0.0.1",
        detail={"method": "password"},
    )
    session.add.assert_called_once()
    entry: Any = session.add.call_args.args[0]
    assert isinstance(entry, AuditLog)
    assert entry.action == "login"
    assert entry.user_id == user_id
    assert entry.entity == "user"
    assert entry.entity_id == "42"
    assert entry.ip == "127.0.0.1"
    assert entry.detail == {"method": "password"}
    session.flush.assert_awaited_once()


async def test_record_audit_defaults_and_copies_detail() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    detail = {"k": "v"}
    await record_audit(session, action="ping", detail=detail)
    entry: Any = session.add.call_args.args[0]
    assert entry.detail == {"k": "v"}
    detail["k"] = "mutated"
    assert entry.detail == {"k": "v"}
    assert entry.user_id is None
    assert entry.entity is None
    assert entry.entity_id is None
    assert entry.ip is None

    await record_audit(session, action="bare")
    bare: Any = session.add.call_args.args[0]
    assert bare.detail == {}


async def test_record_audit_rejects_oversized_detail() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    with pytest.raises(ValueError, match="8192"):
        await record_audit(session, action="big", detail={"blob": "x" * MAX_DETAIL_BYTES})
    session.add.assert_not_called()
    session.flush.assert_not_awaited()

    boundary = "x" * (MAX_DETAIL_BYTES - 128)
    await record_audit(session, action="boundary", detail={"blob": boundary})
    session.add.assert_called_once()
    session.flush.assert_awaited_once()


@pytest.mark.usefixtures("db_engine")
def test_real_audit_log_roundtrip() -> None:
    """真实库：写入审计记录并读回，JSONB 与 UTC 时间正确。"""
    marker = str(uuid.uuid4())

    async def scenario() -> tuple[Any, Any, Any]:
        await db_module.dispose_engine()
        engine = db_module.get_engine()
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO audit_log (action, entity, entity_id, detail) "
                    "VALUES (:action, 'order', :marker, CAST(:detail AS jsonb))"
                ),
                {"action": "t04_roundtrip", "marker": marker, "detail": '{"source": "m0"}'},
            )
            result = await connection.execute(
                text(
                    "SELECT detail, entity_id, created_at FROM audit_log WHERE entity_id = :marker"
                ),
                {"marker": marker},
            )
            row = result.first()
            assert row is not None
            return row[0], row[1], row[2]
        # engine 在 finally 中释放

    try:
        detail, entity_id, created_at = asyncio.run(scenario())
        assert detail == {"source": "m0"}
        assert entity_id == marker
        assert created_at.utcoffset().total_seconds() == 0
    finally:
        asyncio.run(db_module.dispose_engine())
