"""M1-T01 迁移集成测试：真实 Postgres 下的表、外键、可逆性与孤儿行清理。

无 `TEST_DATABASE_URL` 且无 Docker 时由 conftest 的 `db_engine` fixture 自动 skip。
Alembic `env.py` 的在线模式内部用 `asyncio.run`，因此本文件的测试必须是同步函数，
且对 async engine 的访问各自用 `asyncio.run` 包一层。
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import command

_TABLES = {"users", "refresh_tokens", "password_reset_tokens", "ai_usage"}
_ORPHAN_ACTION = "test.m1.orphan"


def _alembic_config() -> Config:
    backend = Path(__file__).resolve().parents[3]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    return config


def _table_names(engine: AsyncEngine) -> set[str]:
    async def _run() -> set[str]:
        async with engine.connect() as connection:
            names = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
        return set(names)

    return asyncio.run(_run())


def test_alembic_has_single_head() -> None:
    """并行里程碑合入后仍只有一个 head，防 0002/0003 多头回归（见 #12）。

    M2-T02 的 `0002_marketdata` 与 M1-T01 原本的 `0002_identity` 都挂在
    `0001_initial` 上，曾导致 CI 全部集成测试报 MultipleHeads。
    """
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config())
    assert list(script.get_heads()) == ["0006_screener"]
    assert script.get_revision("0006_screener").down_revision == "0005_ai"
    assert script.get_revision("0005_ai").down_revision == "0004_simbroker"
    assert script.get_revision("0004_simbroker").down_revision == "0003_identity"
    assert script.get_revision("0003_identity").down_revision == "0002_marketdata"


def test_env_registers_identity_models_and_exempts_audit_fk() -> None:
    """`env.py` 必须注册 identity 表，并排除只在库里存在的 audit_log 外键。

    前者防止 `alembic check` 把 4 张新表判为应删除；后者防止它把
    fk_audit_log_user_id_users 判为「多余约束」生成破坏性 DROP CONSTRAINT。
    """
    source = (Path(__file__).resolve().parents[3] / "alembic" / "env.py").read_text(
        encoding="utf-8"
    )
    assert "import app.modules.identity.models" in source
    assert "include_object=include_object" in source
    assert '"fk_audit_log_user_id_users"' in source


@pytest.mark.integration
def test_identity_tables_exist_after_upgrade(db_engine: AsyncEngine) -> None:
    """`0003_identity` 在空库建出全部 4 张表。"""
    assert _table_names(db_engine) >= _TABLES


@pytest.mark.integration
def test_audit_log_user_id_foreign_key_exists(db_engine: AsyncEngine) -> None:
    """接缝 S1：audit_log.user_id 指向 users.id（ON DELETE SET NULL）。"""

    async def _run() -> Any:
        async with db_engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_foreign_keys("audit_log")
            )

    foreign_keys = asyncio.run(_run())
    assert any(
        fk.get("constrained_columns") == ["user_id"] and fk.get("referred_table") == "users"
        for fk in foreign_keys
    )


@pytest.mark.integration
def test_downgrade_upgrade_roundtrip_and_orphan_cleanup(db_engine: AsyncEngine) -> None:
    """降到 0001 再升回 head 可逆；历史孤儿 user_id 在加 FK 前被置 NULL。"""
    config = _alembic_config()
    orphan_id = uuid.uuid4()

    async def _insert_orphan() -> None:
        async with db_engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO audit_log (user_id, action) VALUES (:user_id, :action)"),
                {"user_id": orphan_id, "action": _ORPHAN_ACTION},
            )

    try:
        # 必须先降到 0001（此时 audit_log 尚无 FK）才能写入孤儿行；在 head 上
        # 直接插入会被 fk_audit_log_user_id_users 拒绝，无法验证迁移的清理逻辑。
        command.downgrade(config, "0001_initial")
        asyncio.run(_insert_orphan())
        command.upgrade(config, "head")
    finally:
        # 任何失败也尝试恢复到 head，避免污染同会话的其它 DB 用例。
        command.upgrade(config, "head")

    async def _verify_and_cleanup() -> Any:
        async with db_engine.connect() as connection:
            result = await connection.execute(
                text("SELECT user_id FROM audit_log WHERE action = :action"),
                {"action": _ORPHAN_ACTION},
            )
            rows = list(result.all())
        async with db_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM audit_log WHERE action = :action"),
                {"action": _ORPHAN_ACTION},
            )
        return rows

    rows = asyncio.run(_verify_and_cleanup())
    assert len(rows) == 1
    assert rows[0][0] is None
    assert _table_names(db_engine) >= _TABLES
