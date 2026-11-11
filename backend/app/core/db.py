"""异步数据库层（M0 / T04），`CONTRACTS.md §5`。

引擎与 session factory 均为懒创建单例；连接级时区统一 UTC。
URL 只从 `Settings.database_url` 读取，任何文件都不含硬编码口令。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, Uuid, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import get_settings

__all__ = [
    "Base",
    "NAMING_CONVENTION",
    "TimestampMixin",
    "UUIDPkMixin",
    "check_db",
    "dispose_engine",
    "get_engine",
    "get_session",
    "get_session_factory",
]

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    """声明式基类；统一约束命名，保证 autogenerate 稳定。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPkMixin:
    """UUID 主键；由 PG13+ 内置 / pgcrypto 的 gen_random_uuid() 生成。"""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """创建/更新时间，timestamptz，数据库端 now() 生成。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


def _connect_args() -> dict[str, Any]:
    """asyncpg 连接级参数：把会话时区固定为 UTC（docs/07 §5）。"""
    return {"server_settings": {"timezone": "UTC"}}


def get_engine() -> AsyncEngine:
    """懒创建单例 AsyncEngine；pool_pre_ping 保证连接失效可自愈。"""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            connect_args=_connect_args(),
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """懒创建单例 session factory；与 engine 同生命周期。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：正常结束 commit，异常 rollback，最后 close。"""
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


async def check_db() -> bool:
    """SELECT 1 探活；任何失败都返回 False，不向调用方抛异常。"""
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def dispose_engine() -> None:
    """释放连接池并清空两个单例，供应用关闭与测试重置使用。"""
    global _engine, _session_factory
    engine, _engine, _session_factory = _engine, None, None
    if engine is not None:
        await engine.dispose()
