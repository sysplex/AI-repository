"""M0-T04 Alembic 迁移测试。

`test_offline_sql_contains_ddl` 不需要数据库；其余用例需要 ``TEST_DATABASE_URL``，
未设置时明确 skip（本机/CI 由 T09 的 postgres:16 服务容器或 K8S 提供）。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import get_settings

BACKEND = Path(__file__).resolve().parents[3]
ALEMBIC_DIR = BACKEND / "alembic"
INI_PATH = BACKEND / "alembic.ini"
TEST_DB_URL = os.getenv("TEST_DATABASE_URL")


def _config() -> Config:
    config = Config(str(INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config


async def _query(sql: str, params: dict[str, str] | None = None) -> list[tuple[object, ...]]:
    engine = create_async_engine(TEST_DB_URL or "")
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text(sql), params or {})
            return [tuple(row) for row in result]
    finally:
        await engine.dispose()


def test_offline_sql_contains_ddl(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """离线模式能生成完整 DDL，无需数据库。"""
    from app.core.config import Settings

    offline_settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user@localhost:5432/offline",
        redis_url="redis://localhost:6379/0",
        secret_key="x" * 32,
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: offline_settings)
    command.upgrade(_config(), "head", sql=True)
    output = capsys.readouterr().out
    assert "CREATE TABLE audit_log" in output
    assert "gen_random_uuid" in output
    assert "ix_audit_log_user_id_created_at" in output
    assert "ix_audit_log_action_created_at" in output
    assert "pgcrypto" in output


@pytest.mark.skipif(not TEST_DB_URL, reason="未设置 TEST_DATABASE_URL，跳过真实迁移用例")
def test_upgrade_downgrade_upgrade_and_check() -> None:
    """空库升级 → 降级到 base → 再升级 → 无模型漂移。"""
    os.environ["DATABASE_URL"] = TEST_DB_URL or ""
    get_settings.cache_clear()
    config = _config()

    command.downgrade(config, "base")
    command.upgrade(config, "head")
    versions = asyncio.run(_query("SELECT version_num FROM alembic_version"))
    assert versions == [("0001_initial",)]

    command.downgrade(config, "base")
    tables = asyncio.run(_query("SELECT tablename FROM pg_tables WHERE tablename = 'audit_log'"))
    assert tables == []

    command.upgrade(config, "head")
    command.check(config)


@pytest.mark.skipif(not TEST_DB_URL, reason="未设置 TEST_DATABASE_URL，跳过真实迁移用例")
def test_migrated_schema_and_indexes() -> None:
    """迁移后列类型/可空性/索引与 docs/03 §3.1 一致。"""
    os.environ["DATABASE_URL"] = TEST_DB_URL or ""
    get_settings.cache_clear()
    command.upgrade(_config(), "head")

    columns = asyncio.run(
        _query(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns WHERE table_name = 'audit_log' "
            "ORDER BY column_name"
        )
    )
    by_name = {str(row[0]): (str(row[1]), str(row[2])) for row in columns}
    assert set(by_name) == {
        "id",
        "user_id",
        "action",
        "entity",
        "entity_id",
        "ip",
        "detail",
        "created_at",
    }
    assert by_name["id"][0] == "uuid"
    assert by_name["detail"][0] == "jsonb"
    assert by_name["created_at"][0] == "timestamp with time zone"
    assert by_name["action"][1] == "NO"
    assert by_name["user_id"][1] == "YES"

    indexes = asyncio.run(_query("SELECT indexname FROM pg_indexes WHERE tablename = 'audit_log'"))
    names = {str(row[0]) for row in indexes}
    assert {"ix_audit_log_user_id_created_at", "ix_audit_log_action_created_at"} <= names


@pytest.mark.skipif(not TEST_DB_URL, reason="未设置 TEST_DATABASE_URL，跳过真实迁移用例")
def test_migration_file_has_no_hardcoded_credentials() -> None:
    """迁移与 env.py 不得含硬编码连接串/口令。"""
    for path in (INI_PATH, ALEMBIC_DIR / "env.py", ALEMBIC_DIR / "versions" / "0001_initial.py"):
        content = path.read_text(encoding="utf-8")
        assert "postgresql+asyncpg://" not in content
        assert "sqlalchemy.url =" not in content
