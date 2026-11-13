"""Alembic 异步迁移环境（M0 / T04）。

- URL 取自 `Settings.database_url`（不写进 alembic.ini）
- `target_metadata = Base.metadata`，开启 `compare_type` 以便 `alembic check`
- 在线模式用 asyncpg 驱动执行迁移
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.core.audit  # noqa: F401  # 导入以把 AuditLog 注册到 Base.metadata
import app.modules.identity.models  # noqa: F401  # M1-T01：注册 identity 四表，供 alembic check 比对
import app.modules.marketdata.tables  # noqa: F401  # 导入以把 marketdata 表注册到 Base.metadata
import app.modules.simbroker.models  # noqa: F401  # M4-T01：注册 simbroker 六表，供 alembic check 比对
from alembic import context
from app.core.config import get_settings
from app.core.db import Base

config = context.config
# 不在此调用 logging.config.fileConfig：alembic CLI 入口已处理 ini 的 logging 段，
# 而在 pytest / 程序内调用 command.* 时重配全局 logging 会破坏应用的 structlog 配置。

# ConfigParser 会把 % 当插值符，连接串里的百分号需转义。
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

target_metadata = Base.metadata


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """接缝 S1：让 autogenerate 忽略只在库里存在的 audit_log.user_id 外键。

    M0 冻结的 `app/core/audit.py` 刻意不声明该外键（users 表到 M1 才存在），
    而 `0003_identity` 已在库里建出 `fk_audit_log_user_id_users`。若照常比对，
    autogenerate 会把它当成「多余约束」生成破坏性的 `DROP CONSTRAINT`，
    使 `alembic check` / `test_upgrade_downgrade_upgrade_and_check` 失败。
    这里用 Alembic 官方的 include_object 钩子精确排除这一条约束，
    不影响其它表、列、索引、约束的漂移检测。
    """
    return not (
        type_ == "foreign_key_constraint"
        and reflected
        and name == "fk_audit_log_user_id_users"
        and getattr(getattr(obj, "table", None), "name", None) == "audit_log"
    )


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连接数据库。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """在同步连接上配置并执行迁移（由 run_sync 调用）。"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """在线模式：用 NullPool 的异步引擎跑迁移。"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """入口：把异步协程交给 asyncio.run。"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
