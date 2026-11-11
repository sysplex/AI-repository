"""M0-T07 Prometheus 指标验收（`docs/tasks/M0/T07-health-metrics-redis.md`）。"""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from pydantic import SecretStr
from starlette.types import Scope

from app.api.router import root_router
from app.core.config import Settings
from app.core.metrics import install_metrics, path_template, render_metrics
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

    @app.get("/sim/accounts/{account_id}")
    async def account(account_id: str) -> dict[str, str]:
        return {"id": account_id}

    return app


async def _get(app: FastAPI, path: str, method: str = "GET") -> httpx.Response:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path)


def _render(app: FastAPI) -> str:
    return render_metrics(app).decode("utf-8")


async def test_counter_and_histogram_use_route_template() -> None:
    app = _app()
    assert (await _get(app, "/sim/accounts/42")).status_code == 200
    assert (await _get(app, "/sim/accounts/another-id")).status_code == 200

    text = _render(app)
    assert (
        'http_requests_total{method="GET",path_template="/sim/accounts/{account_id}",'
        'status="200"} 2.0' in text
    )
    assert (
        'http_request_duration_seconds_count{method="GET",'
        'path_template="/sim/accounts/{account_id}"} 2.0' in text
    )
    assert 'path_template="/sim/accounts/42"' not in text


async def test_unmatched_paths_do_not_grow_label_cardinality() -> None:
    app = _app()
    for index in range(6):
        assert (await _get(app, f"/does-not-exist-{index}")).status_code == 404

    text = _render(app)
    counter_lines = [
        line
        for line in text.splitlines()
        if line.startswith("http_requests_total{") and not line.startswith("#")
    ]
    assert counter_lines
    assert all('path_template="unmatched"' in line for line in counter_lines)
    assert len(counter_lines) == 1
    assert 'status="404"' in counter_lines[0]


async def test_health_and_metrics_endpoints_are_not_counted() -> None:
    app = _app()
    assert (await _get(app, "/healthz")).status_code == 200
    assert (await _get(app, "/metrics")).status_code == 200
    text = _render(app)
    assert "http_requests_total{" not in text
    assert 'app_info{env="ci",version="0.1.0"} 1.0' in text


async def test_metrics_disabled_returns_404() -> None:
    app = _app(_settings(metrics_enabled=False))
    response = await _get(app, "/metrics")
    assert response.status_code == 404
    assert app.state.metrics_enabled is False


async def test_metrics_content_type_is_prometheus_text() -> None:
    app = _app()
    response = await _get(app, "/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "# HELP http_requests_total" in response.text


def test_each_install_gets_an_independent_registry() -> None:
    first = FastAPI()
    second = FastAPI()
    install_metrics(first, _settings())
    install_metrics(second, _settings())
    assert first.state.metrics_registry is not second.state.metrics_registry
    assert b"# HELP app_info" in render_metrics(first)
    assert render_metrics(FastAPI()) == b""


def test_path_template_falls_back_to_unmatched() -> None:
    assert path_template(cast(Scope, {"type": "http", "path": "/x"})) == "unmatched"

    class _Route:
        path = "/sim/accounts/{account_id}"

    scope = cast(Scope, {"type": "http", "path": "/sim/accounts/1", "route": _Route()})
    assert path_template(scope) == "/sim/accounts/{account_id}"


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
async def test_method_label_and_non_200_status(method: str) -> None:
    app = _app()
    response = await _get(app, "/sim/accounts/7", method=method)
    text = _render(app)
    assert f'method="{method}"' in text
    if response.status_code != 200:
        assert f'status="{response.status_code}"' in text
