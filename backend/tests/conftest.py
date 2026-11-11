"""M0-T10 全项目共享测试基座（`docs/tasks/M0/T10-test-infrastructure.md`）。

提供：环境隔离的 Settings、真实/容器化 Postgres 与事务级 DB 隔离、HTTP 客户端、
fakeredis、冻结时钟、干净事件总线；目录自动打标与 hypothesis profile。
单元测试不得依赖 `db_engine` / `redis` / 网络。
"""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fakeredis
import httpx
import pytest
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport
from hypothesis import settings as hypothesis_settings
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core import redis as redis_module
from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.config import Settings, get_settings
from app.core.events import EventBus, reset_event_bus, set_event_bus

BACKEND = Path(__file__).resolve().parents[1]
INI_PATH = BACKEND / "alembic.ini"
ALEMBIC_DIR = BACKEND / "alembic"
FROZEN_AT = datetime(2026, 11, 11, 14, 30, tzinfo=UTC)

_DEFAULT_ENV: dict[str, str] = {
    "APP_ENV": "ci",
    "DATABASE_URL": "postgresql+asyncpg://postgres@db.test:5432/app",
    "REDIS_URL": "redis://cache.test:6379/0",
    "SECRET_KEY": "t" * 40,
}
_LAYERS = ("unit", "integration", "contract", "e2e")

# 收集期导入 app.main（模块级 app = create_app()）需要三个必填变量；
# 放在 conftest 而非各测试模块，T02 的收集期兼容写法由此变成无副作用的冗余。
for _key, _value in _DEFAULT_ENV.items():
    os.environ.setdefault(_key, _value)

hypothesis_settings.register_profile("ci", max_examples=200, deadline=None)
hypothesis_settings.register_profile("dev", max_examples=50, deadline=None)
hypothesis_settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """按目录自动打标：tests/unit → unit，integration → integration，依此类推。"""
    for item in items:
        parts = item.path.parts
        for layer in _LAYERS:
            if layer in parts:
                item.add_marker(getattr(pytest.mark, layer))
                break


def _alembic_config() -> Config:
    config = Config(str(INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config


@pytest.fixture(autouse=True)
def _clean_globals() -> Iterator[None]:
    """每个用例结束后恢复进程级单例，避免测试间串扰。"""
    yield
    get_settings.cache_clear()
    reset_clock()
    reset_event_bus()
    redis_module._client = None


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """覆盖环境变量的 Settings；自动清理 lru_cache。"""
    for key, value in _DEFAULT_ENV.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    result = get_settings()
    yield result
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def test_database_url() -> Iterator[str]:
    """优先 TEST_DATABASE_URL；否则若本机有 Docker 则用 testcontainers 起 PG16。

    两者都不可用时 `pytest.skip` 并给出明确提示，让依赖 DB 的用例跳过而不是报错。
    """
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        yield url
        return

    if shutil.which("docker") is None:
        pytest.skip("未设置 TEST_DATABASE_URL，且本机无 docker：跳过真实数据库用例")

    container: Any = None
    try:
        from testcontainers.postgres import PostgresContainer

        container = PostgresContainer("postgres:16")
        container.start()
    except Exception as exc:  # pragma: no cover - 环境相关分支
        pytest.skip(f"未设置 TEST_DATABASE_URL，且 testcontainers 启动失败：{exc}")

    try:
        yield str(container.get_connection_url()).replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
    finally:
        container.stop()


@pytest.fixture(scope="session")
def db_engine(test_database_url: str) -> Iterator[AsyncEngine]:
    """会话级引擎：注入测试连接串、跑 alembic upgrade head、结束降回 base。"""
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_database_url
    get_settings.cache_clear()
    command.upgrade(_alembic_config(), "head")
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        asyncio.run(engine.dispose())
        command.downgrade(_alembic_config(), "base")
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """函数级事务隔离：外层事务 + savepoint，被测代码里的 commit() 也不落库。"""
    connection = await db_engine.connect()
    transaction = await connection.begin()
    try:
        async with AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as session:
            yield session
    finally:
        await transaction.rollback()
        await connection.close()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """全新 FastAPI 应用；`app.dependency_overrides` 可直接用于依赖替换。"""
    from app.main import create_app

    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """ASGI 内存客户端，不发真实网络请求。"""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as instance:
        yield instance


@pytest.fixture
async def redis(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Any]:
    """默认 fakeredis；`REDIS_URL` 指向可达真实 Redis 时自动改用真实客户端。"""
    client: Any = None
    if os.getenv("REDIS_URL"):
        try:
            candidate = redis_module.get_redis()
            await candidate.ping()
            client = candidate
        except Exception:
            await redis_module.close_redis()
    if client is None:
        client = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "_client", client)
    yield client
    await client.aclose()
    monkeypatch.setattr(redis_module, "_client", None)


@pytest.fixture
def frozen_clock() -> Iterator[FrozenClock]:
    """冻结到 2026-11-11T14:30:00Z；用例结束自动恢复 SystemClock。"""
    clock = FrozenClock(FROZEN_AT)
    set_clock(clock)
    yield clock
    reset_clock()


@pytest.fixture
def event_bus() -> Iterator[EventBus]:
    """每个用例一个干净的事件总线。"""
    bus = EventBus()
    set_event_bus(bus)
    yield bus
    reset_event_bus()
