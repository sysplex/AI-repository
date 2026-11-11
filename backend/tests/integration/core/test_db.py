"""M0-T04 数据库层测试。

单元测试不依赖外部服务（用 mock 验证懒单例、commit/rollback、探活）。
真实库用例改用 T10 共享 `db_engine` fixture：连接串注入、迁移与 skip 提示
统一由 `tests/conftest.py` 负责，本文件不再就地定义 `TEST_DATABASE_URL`。
"""

from __future__ import annotations

import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import DateTime, Uuid, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import db as db_module
from app.core.audit import AuditLog


@pytest.fixture(autouse=True)
def _reset_singletons() -> Any:
    """每个测试前后清空模块级单例，避免顺序耦合。"""
    db_module._engine = None
    db_module._session_factory = None
    yield
    db_module._engine = None
    db_module._session_factory = None


def _settings_mock(url: str = "postgresql+asyncpg://user@host:5432/db") -> MagicMock:
    return MagicMock(database_url=url)


def test_naming_convention_and_base_metadata() -> None:
    assert set(db_module.NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}
    assert db_module.Base.metadata.naming_convention == db_module.NAMING_CONVENTION
    assert db_module.NAMING_CONVENTION["pk"] == "pk_%(table_name)s"


def test_mixins_column_definitions() -> None:
    id_column: Any = db_module.UUIDPkMixin.__dict__["id"].column
    assert isinstance(id_column.type, Uuid)
    assert id_column.primary_key is True
    assert "gen_random_uuid" in str(id_column.server_default.arg.text)

    for field in ("created_at", "updated_at"):
        column: Any = db_module.TimestampMixin.__dict__[field].column
        assert isinstance(column.type, DateTime)
        assert column.type.timezone is True
        assert column.nullable is False
        assert "now()" in str(column.server_default.arg.text)


async def test_get_engine_is_lazy_singleton_with_utc_connect_args() -> None:
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()
    with (
        patch.object(db_module, "get_settings", return_value=_settings_mock()),
        patch.object(db_module, "create_async_engine", return_value=fake_engine) as create,
    ):
        assert db_module._engine is None
        first = db_module.get_engine()
        second = db_module.get_engine()
        assert first is second is fake_engine
        create.assert_called_once()
        kwargs = create.call_args.kwargs
        assert kwargs["pool_pre_ping"] is True
        assert kwargs["pool_size"] == 5
        assert kwargs["max_overflow"] == 10
        assert kwargs["connect_args"]["server_settings"]["timezone"] == "UTC"

        await db_module.dispose_engine()
        fake_engine.dispose.assert_awaited_once()
        assert db_module._engine is None
        assert db_module._session_factory is None
        db_module.get_engine()
        assert create.call_count == 2


def test_get_session_factory_is_singleton() -> None:
    fake_engine = MagicMock()
    with (
        patch.object(db_module, "get_settings", return_value=_settings_mock()),
        patch.object(db_module, "create_async_engine", return_value=fake_engine),
    ):
        factory = db_module.get_session_factory()
        assert isinstance(factory, async_sessionmaker)
        assert factory is db_module.get_session_factory()
        assert db_module._engine is fake_engine


async def test_get_session_commits_and_closes() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    factory = MagicMock(return_value=session)
    with patch.object(db_module, "get_session_factory", return_value=factory):
        generator = db_module.get_session()
        received = await anext(generator)
        assert received is session
        with pytest.raises(StopAsyncIteration):
            await anext(generator)
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once()


async def test_get_session_rolls_back_on_exception() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    factory = MagicMock(return_value=session)
    with patch.object(db_module, "get_session_factory", return_value=factory):
        generator = db_module.get_session()
        await anext(generator)
        with pytest.raises(RuntimeError, match="boom"):
            await cast(Any, generator).athrow(RuntimeError("boom"))
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()


async def test_get_session_rolls_back_when_commit_fails() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.commit.side_effect = RuntimeError("commit failed")
    with patch.object(
        db_module, "get_session_factory", return_value=MagicMock(return_value=session)
    ):
        generator = db_module.get_session()
        await anext(generator)
        with pytest.raises(RuntimeError, match="commit failed"):
            await anext(generator)
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()


async def test_check_db_true_and_false() -> None:
    connection = AsyncMock()
    engine = MagicMock()
    engine.connect.return_value.__aenter__.return_value = connection
    with patch.object(db_module, "get_engine", return_value=engine):
        assert await db_module.check_db() is True
    connection.execute.assert_awaited_once()
    assert str(connection.execute.await_args.args[0].text) == "SELECT 1"

    broken = MagicMock()
    broken.connect.side_effect = OSError("db down")
    with patch.object(db_module, "get_engine", return_value=broken):
        assert await db_module.check_db() is False


async def test_dispose_engine_without_engine_is_noop() -> None:
    await db_module.dispose_engine()
    assert db_module._engine is None


@pytest.mark.usefixtures("db_engine")
def test_real_session_commit_and_rollback() -> None:
    """真实库：正常 commit 写入、异常 rollback 不落库、check_db 探活。"""

    async def scenario() -> tuple[bool, int, int, bool]:
        await db_module.dispose_engine()
        alive = await db_module.check_db()

        session = db_module.get_session_factory()()
        await session.execute(text("DELETE FROM audit_log WHERE action LIKE 't04_%'"))
        await session.commit()
        await session.close()

        # 正常路径：通过 get_session 依赖写入并提交
        generator = db_module.get_session()
        committed = await anext(generator)
        committed.add(AuditLog(action="t04_commit", detail={"ok": True}))
        with pytest.raises(StopAsyncIteration):
            await anext(generator)

        # 异常路径：同一依赖抛错后应回滚
        generator = db_module.get_session()
        rolled_back = await anext(generator)
        rolled_back.add(AuditLog(action="t04_rollback", detail={"ok": False}))
        with pytest.raises(RuntimeError):
            await cast(Any, generator).athrow(RuntimeError("force rollback"))

        engine = db_module.get_engine()
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT action FROM audit_log WHERE action LIKE 't04_%'")
            )
            rows = [row[0] for row in result]
        await db_module.dispose_engine()
        return alive, rows.count("t04_commit"), rows.count("t04_rollback"), True

    alive, committed_count, rolled_back_count, completed = asyncio.run(scenario())
    assert alive is True
    assert committed_count == 1
    assert rolled_back_count == 0
    assert completed is True


@pytest.mark.usefixtures("db_engine")
def test_real_timestamptz_is_utc_aware() -> None:
    """真实库：created_at 为 timestamptz，读回带 UTC 时区。"""

    async def scenario() -> tuple[str, Any]:
        await db_module.dispose_engine()
        engine = db_module.get_engine()
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM audit_log WHERE action = 't04_tz'"))
            await connection.execute(
                text("INSERT INTO audit_log (action, detail) VALUES ('t04_tz', '{}'::jsonb)")
            )
            result = await connection.execute(
                text(
                    "SELECT data_type, created_at FROM audit_log "
                    "JOIN information_schema.columns "
                    "ON table_name = 'audit_log' AND column_name = 'created_at' "
                    "WHERE action = 't04_tz' LIMIT 1"
                )
            )
            row = result.first()
            assert row is not None
            data_type, created_at = row[0], row[1]
        await db_module.dispose_engine()
        return str(data_type), created_at

    data_type, created_at = asyncio.run(scenario())
    assert data_type == "timestamp with time zone"
    assert created_at.utcoffset().total_seconds() == 0
