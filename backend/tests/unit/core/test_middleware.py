"""T02 验收：请求上下文、访问日志、安全响应头与 CORS。"""

from __future__ import annotations

import json
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from pydantic import SecretStr
from starlette.types import Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.logging import setup_logging
from app.core.middleware import (
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    _is_valid_request_id,
    install_middlewares,
)

_PWD = "h" * 12
_SECRET = "s" * 40
_DB = f"postgresql+asyncpg://svc:{_PWD}@db.internal:5432/app"
_REDIS = "redis://localhost:6379/0"


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": _DB,
        "redis_url": _REDIS,
        "secret_key": SecretStr(_SECRET),
    }
    values.update(overrides)
    return Settings(**values)


def _app(settings: Settings) -> FastAPI:
    app = FastAPI()
    install_middlewares(app, settings)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "ok"}

    return app


async def _request(
    app: FastAPI,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    path: str = "/ping",
) -> httpx.Response:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, headers=headers)


async def test_valid_request_id_is_echoed() -> None:
    rid = str(uuid4())
    response = await _request(_app(_settings()), {"X-Request-ID": rid})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == rid


async def test_missing_request_id_generates_uuid4() -> None:
    response = await _request(_app(_settings()))
    generated = response.headers["x-request-id"]
    assert UUID(generated).version == 4


@pytest.mark.parametrize("bad", ["a" * 65, "has space"])
async def test_invalid_request_id_regenerates(bad: str) -> None:
    response = await _request(_app(_settings()), {"X-Request-ID": bad})
    generated = response.headers["x-request-id"]
    assert generated != bad
    assert UUID(generated).version == 4


def test_request_id_validator_edges() -> None:
    assert _is_valid_request_id(None) is False
    assert _is_valid_request_id("") is False
    assert _is_valid_request_id("a" * 65) is False
    assert _is_valid_request_id("has space") is False
    assert _is_valid_request_id("ctrl\x01value") is False
    assert _is_valid_request_id(str(uuid4())) is True
    assert _is_valid_request_id("gateway-trace-123") is True


async def test_security_headers_present() -> None:
    response = await _request(_app(_settings()))
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


async def test_access_log_fields_and_no_authorization(
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup_logging(_settings())
    response = await _request(_app(_settings()), {"Authorization": "Bearer TOPSECRETVALUE"})
    assert response.status_code == 200
    text = capsys.readouterr().err
    assert "TOPSECRETVALUE" not in text
    # httpx 自身也会经 root handler 输出一行 JSON 日志，故按 event 精确取访问日志。
    access_lines = [line for line in text.splitlines() if line.strip() and "http.access" in line]
    assert len(access_lines) == 1
    payload = json.loads(access_lines[0])
    assert payload["event"] == "http.access"
    assert payload["method"] == "GET"
    assert payload["path"] == "/ping"
    assert payload["status_code"] == 200
    assert "duration_ms" in payload
    assert "Cookie" not in text


async def test_access_log_omits_cookie_value(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(_settings())
    await _request(_app(_settings()), {"Cookie": "session=SUPERSECRETCOOKIE"})
    assert "SUPERSECRETCOOKIE" not in capsys.readouterr().err


async def test_cors_preflight_allowed() -> None:
    headers = {
        "Origin": "https://allowed.example",
        "Access-Control-Request-Method": "GET",
    }
    response = await _request(
        _app(_settings(cors_origins=["https://allowed.example"])),
        headers,
        method="OPTIONS",
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://allowed.example"


async def test_cors_not_installed_when_origins_empty() -> None:
    headers = {
        "Origin": "https://allowed.example",
        "Access-Control-Request-Method": "GET",
    }
    response = await _request(_app(_settings()), headers, method="OPTIONS")
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "raw",
    [
        '["https://allowed.example"]',
        "https://allowed.example",
        "https://other.example, https://allowed.example",
    ],
)
async def test_cors_origins_both_formats_feed_middleware(raw: str) -> None:
    headers = {
        "Origin": "https://allowed.example",
        "Access-Control-Request-Method": "GET",
    }
    response = await _request(_app(_settings(cors_origins=raw)), headers, method="OPTIONS")
    assert response.headers.get("access-control-allow-origin") == "https://allowed.example"


async def test_non_http_scope_passes_through() -> None:
    calls: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        del receive, send
        calls.append(str(scope["type"]))

    async def receive() -> Message:
        raise RuntimeError("not called for websocket scope")

    async def send(message: Message) -> None:
        del message
        raise RuntimeError("not called for websocket scope")

    scope = cast(Scope, {"type": "websocket"})
    await RequestContextMiddleware(inner)(scope, receive, send)
    await SecurityHeadersMiddleware(inner)(scope, receive, send)
    assert calls == ["websocket", "websocket"]
