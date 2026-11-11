"""M0-T07 健康检查、指标端点与生命周期验收。

`docs/tasks/M0/T07-health-metrics-redis.md`；依赖探针在本文件内全部替换，
不连接真实数据库或 Redis（真实依赖联调由 T08/T09/T11 补齐）。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from pydantic import SecretStr

from app.api import health as health_module
from app.api.router import root_router
from app.core import lifecycle as lifecycle_module
from app.core.config import Settings
from app.core.lifecycle import on_shutdown, on_startup
from app.core.middleware import install_middlewares


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "postgresql+asyncpg://svc@db.internal:5432/app",
        "redis_url": "redis://cache.internal:6379/0",
        "secret_key": SecretStr("s" * 40),
        "app_version": "0.1.0",
        "app_env": "ci",
    }
    values.update(overrides)
    return Settings(**values)


def _app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(openapi_url="/api/v1/openapi.json")
    install_middlewares(app, settings or _settings())
    app.include_router(root_router)
    return app


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def _ok() -> bool:
    return True


async def _down() -> bool:
    return False


@pytest.fixture(autouse=True)
def _probes(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """默认两个依赖均可用；各用例按需覆盖。"""
    monkeypatch.setattr("app.api.health.check_db", _ok)
    monkeypatch.setattr("app.api.health.check_redis", _ok)
    yield


async def test_healthz_is_always_200_even_when_dependencies_are_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.health.check_db", _down)
    monkeypatch.setattr("app.api.health.check_redis", _down)
    response = await _get(_app(), "/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_returns_200_when_all_checks_pass() -> None:
    response = await _get(_app(), "/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": True, "redis": True},
    }


@pytest.mark.parametrize(
    ("failed", "expected_checks"),
    [
        ("db", {"database": False, "redis": True}),
        ("redis", {"database": True, "redis": False}),
        ("both", {"database": False, "redis": False}),
    ],
)
async def test_readyz_returns_503_when_a_dependency_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    failed: str,
    expected_checks: dict[str, bool],
) -> None:
    if failed in ("db", "both"):
        monkeypatch.setattr("app.api.health.check_db", _down)
    if failed in ("redis", "both"):
        monkeypatch.setattr("app.api.health.check_redis", _down)
    response = await _get(_app(), "/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": expected_checks}


async def test_readyz_probe_exception_is_reported_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exploding() -> bool:
        raise RuntimeError("probe blew up")

    monkeypatch.setattr("app.api.health.check_db", exploding)
    response = await _get(_app(), "/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] is False


async def test_readyz_times_out_within_two_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    assert health_module._READY_TIMEOUT == 2.0

    async def hanging() -> bool:
        await asyncio.Event().wait()
        return True

    monkeypatch.setattr("app.api.health.check_db", hanging)
    monkeypatch.setattr(health_module, "_READY_TIMEOUT", 0.05)
    started = time.perf_counter()
    response = await _get(_app(), "/readyz")
    elapsed = time.perf_counter() - started
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": False, "redis": False}
    assert elapsed <= 2.5


async def test_three_probe_endpoints_are_absent_from_openapi() -> None:
    response = await _get(_app(), "/api/v1/openapi.json")
    assert response.status_code == 200
    paths = set(response.json()["paths"])
    assert paths.isdisjoint({"/healthz", "/readyz", "/metrics"})


async def test_metrics_endpoint_serves_prometheus_text() -> None:
    response = await _get(_app(), "/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "# HELP app_info" in response.text


async def test_metrics_disabled_returns_404() -> None:
    response = await _get(_app(_settings(metrics_enabled=False)), "/metrics")
    assert response.status_code == 404


async def test_healthz_is_fast() -> None:
    app = _app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/healthz")  # 预热，避免把首次中间件构建计入耗时
        timings: list[float] = []
        for _ in range(3):
            started = time.perf_counter()
            response = await client.get("/healthz")
            timings.append(time.perf_counter() - started)
            assert response.status_code == 200
    assert min(timings) < 0.05


class _RecordingLogger:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def info(self, event: str, **kwargs: Any) -> None:
        self.records.append({"event": event, **kwargs})

    def error(self, event: str, **kwargs: Any) -> None:
        self.records.append({"event": event, **kwargs})


async def test_on_startup_logs_version_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = _RecordingLogger()
    monkeypatch.setattr(lifecycle_module, "_log", logger)
    monkeypatch.setattr(
        "app.core.lifecycle.get_settings",
        lambda: _settings(app_version="1.2.3", app_env="ci"),
    )
    await on_startup(FastAPI(title="stockpilot"))
    record = logger.records[0]
    assert record["event"] == "app.startup"
    assert record["version"] == "1.2.3"
    assert record["env"] == "ci"


async def test_on_shutdown_closes_both_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    logger = _RecordingLogger()
    monkeypatch.setattr(lifecycle_module, "_log", logger)

    async def close_db() -> None:
        calls.append("database")

    async def close_cache() -> None:
        calls.append("redis")

    monkeypatch.setattr("app.core.lifecycle.dispose_engine", close_db)
    monkeypatch.setattr("app.core.lifecycle.close_redis", close_cache)
    await on_shutdown(FastAPI())
    assert calls == ["database", "redis"]
    assert logger.records[-1]["event"] == "app.shutdown"


async def test_on_shutdown_continues_when_one_dependency_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    logger = _RecordingLogger()
    monkeypatch.setattr(lifecycle_module, "_log", logger)

    async def broken_db() -> None:
        calls.append("database")
        raise RuntimeError("dispose failed")

    async def close_cache() -> None:
        calls.append("redis")

    monkeypatch.setattr("app.core.lifecycle.dispose_engine", broken_db)
    monkeypatch.setattr("app.core.lifecycle.close_redis", close_cache)
    await on_shutdown(FastAPI())
    assert calls == ["database", "redis"]
    assert logger.records[0]["event"] == "app.shutdown_component_failed"
    assert logger.records[0]["component"] == "database"
