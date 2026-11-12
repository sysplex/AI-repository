"""M0-T03 统一错误体系单元测试（`docs/tasks/M0/T03-errors.md`）。"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings
from app.core.errors import (
    DEFAULT_MESSAGES,
    AppError,
    BudgetCircuitOpen,
    DataUnavailable,
    ErrorCode,
    Forbidden,
    IdempotencyConflict,
    InsufficientFunds,
    InsufficientPosition,
    InternalError,
    InvalidOrder,
    LLMFailed,
    LLMOutputInvalid,
    NotFound,
    QuotaExceeded,
    RateLimited,
    StateConflict,
    TokenExpired,
    Unauthenticated,
    ValidationFailed,
    _app_error_handler,
    _http_exception_handler,
    _validation_error_handler,
    register_exception_handlers,
)
from app.core.logging import request_id_var, setup_logging
from app.core.middleware import RequestContextMiddleware


class EchoBody(BaseModel):
    """模块级定义：``from __future__ import annotations`` 下 FastAPI 才能解析注解。"""

    qty: int


# docs/05-api-spec.md §1.2 的 16 个码 + 契约 §4 的 INTERNAL_ERROR
SPEC_CODES = {
    "VALIDATION_ERROR",
    "UNAUTHENTICATED",
    "TOKEN_EXPIRED",
    "FORBIDDEN",
    "NOT_FOUND",
    "IDEMPOTENCY_CONFLICT",
    "STATE_CONFLICT",
    "INSUFFICIENT_FUNDS",
    "INSUFFICIENT_POSITION",
    "INVALID_ORDER",
    "DATA_UNAVAILABLE",
    "RATE_LIMITED",
    "QUOTA_EXCEEDED",
    "LLM_FAILED",
    "LLM_OUTPUT_INVALID",
    "BUDGET_CIRCUIT_OPEN",
    "INTERNAL_ERROR",
}

ALL_ERRORS: tuple[tuple[type[AppError], int, str], ...] = (
    (ValidationFailed, 400, "VALIDATION_ERROR"),
    (Unauthenticated, 401, "UNAUTHENTICATED"),
    (TokenExpired, 401, "TOKEN_EXPIRED"),
    (Forbidden, 403, "FORBIDDEN"),
    (NotFound, 404, "NOT_FOUND"),
    (IdempotencyConflict, 409, "IDEMPOTENCY_CONFLICT"),
    (StateConflict, 409, "STATE_CONFLICT"),
    (InsufficientFunds, 422, "INSUFFICIENT_FUNDS"),
    (InsufficientPosition, 422, "INSUFFICIENT_POSITION"),
    (InvalidOrder, 422, "INVALID_ORDER"),
    (DataUnavailable, 424, "DATA_UNAVAILABLE"),
    (RateLimited, 429, "RATE_LIMITED"),
    (QuotaExceeded, 429, "QUOTA_EXCEEDED"),
    (LLMFailed, 502, "LLM_FAILED"),
    (LLMOutputInvalid, 502, "LLM_OUTPUT_INVALID"),
    (BudgetCircuitOpen, 503, "BUDGET_CIRCUIT_OPEN"),
    (InternalError, 500, "INTERNAL_ERROR"),
)

ERROR_CLASSES: dict[str, type[AppError]] = {code: cls for cls, _, code in ALL_ERRORS}


@pytest.fixture(scope="module", autouse=True)
def _configure_structlog() -> None:
    """让 structlog 走标准库 root handler，使 caplog 能验证 500 日志。"""
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user@localhost:5432/stockpilot",
        redis_url="redis://localhost:6379/0",
        secret_key="x" * 32,
    )
    setup_logging(settings)


def _request() -> Any:
    """构造最小 ASGI Request，用于直接调用私有 handler 覆盖兜底分支。"""
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("testclient", 1234),
            "http_version": "1.1",
        }
    )


def _decode(response: Any) -> Any:
    """从 Starlette Response 的 body 解析 JSON（Response 没有 .json()）。"""
    return json.loads(bytes(response.body))


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.post("/echo")
    async def echo(body: EchoBody) -> dict[str, int]:
        return {"qty": body.qty}

    @app.get("/raise/{name}")
    async def raise_named(name: str) -> None:
        error_cls = ERROR_CLASSES.get(name)
        if error_cls is None:
            raise RuntimeError("unknown-error-class")
        raise error_cls()

    @app.get("/custom")
    async def custom_error() -> None:
        raise NotFound("自定义文案", details={"resource": "order"})

    @app.get("/rate-limited")
    async def rate_limited() -> None:
        raise RateLimited(details={"retry_after": 30})

    @app.get("/rate-limited-no-header")
    async def rate_limited_no_header() -> None:
        raise RateLimited()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("division-by-zero-secret")

    @app.get("/http/{status_code}")
    async def http_error(status_code: int) -> None:
        raise StarletteHTTPException(
            status_code=status_code,
            detail="内部细节不得外泄",
            headers={"X-Test": "1"} if status_code == 418 else None,
        )

    return app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=_build_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as instance:
        yield instance


def test_error_code_set_matches_spec() -> None:
    assert {code.value for code in ErrorCode} == SPEC_CODES
    assert set(DEFAULT_MESSAGES) == set(ErrorCode)
    assert all(message for message in DEFAULT_MESSAGES.values())


@pytest.mark.parametrize(("error_cls", "status", "code"), ALL_ERRORS)
def test_subclass_status_and_code(error_cls: type[AppError], status: int, code: str) -> None:
    error = error_cls()
    assert error.http_status == status
    assert error.code is ErrorCode(code)
    assert error.code.value == code
    assert error.message == DEFAULT_MESSAGES[ErrorCode(code)]
    assert error.details == {}
    assert str(error) == error.message
    assert isinstance(error, AppError)


def test_custom_message_and_details_are_isolated() -> None:
    source = {"resource": "order"}
    error = NotFound("自定义文案", details=source)
    source["resource"] = "mutated"
    assert error.message == "自定义文案"
    assert error.details == {"resource": "order"}
    assert AppError().details == {}
    assert AppError().message == DEFAULT_MESSAGES[ErrorCode.INTERNAL_ERROR]


@pytest.mark.parametrize(("error_cls", "status", "code"), ALL_ERRORS)
async def test_app_error_response_shape(
    client: httpx.AsyncClient, error_cls: type[AppError], status: int, code: str
) -> None:
    response = await client.get(f"/raise/{code}", headers={"X-Request-ID": "req-0001"})
    assert response.status_code == status
    assert response.headers["X-Request-ID"] == "req-0001"
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert body["error"]["details"] == {}
    assert body["error"]["request_id"] == "req-0001"
    assert error_cls.code.value == code


async def test_custom_message_and_details_in_response(client: httpx.AsyncClient) -> None:
    response = await client.get("/custom")
    assert response.status_code == 404
    body = response.json()["error"]
    assert body["code"] == "NOT_FOUND"
    assert body["message"] == "自定义文案"
    assert body["details"] == {"resource": "order"}
    assert body["request_id"] == response.headers["X-Request-ID"]


async def test_request_validation_error_is_redacted(client: httpx.AsyncClient) -> None:
    response = await client.post("/echo", json={"qty": "secret-value"})
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert "secret-value" not in response.text
    errors = body["details"]["errors"]
    assert errors
    assert errors[0]["field"] == "body.qty"
    assert set(errors[0]) == {"field", "message", "type"}
    assert errors[0]["message"]
    assert errors[0]["type"]


async def test_404_and_405_use_unified_format(client: httpx.AsyncClient) -> None:
    missing = await client.get("/definitely-not-a-route")
    assert missing.status_code == 404
    missing_body = missing.json()["error"]
    assert missing_body["code"] == "NOT_FOUND"
    assert missing_body["message"] == DEFAULT_MESSAGES[ErrorCode.NOT_FOUND]
    assert missing_body["details"] == {}
    assert missing_body["request_id"] == missing.headers["X-Request-ID"]

    method = await client.post("/custom")
    assert method.status_code == 405
    assert set(method.json()["error"]) == {"code", "message", "details", "request_id"}
    assert method.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "内部细节" not in method.text


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (400, "VALIDATION_ERROR"),
        (401, "UNAUTHENTICATED"),
        (403, "FORBIDDEN"),
        (404, "NOT_FOUND"),
        (409, "STATE_CONFLICT"),
        (418, "VALIDATION_ERROR"),
        (422, "INVALID_ORDER"),
        (429, "RATE_LIMITED"),
        (503, "INTERNAL_ERROR"),
    ],
)
async def test_http_exception_mapping(
    client: httpx.AsyncClient, status: int, expected_code: str
) -> None:
    response = await client.get(f"/http/{status}")
    assert response.status_code == status
    assert response.json()["error"]["code"] == expected_code
    assert "内部细节不得外泄" not in response.text
    if status == 418:
        assert response.headers["X-Test"] == "1"


async def test_unhandled_exception_is_opaque_but_logged(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        response = await client.get("/boom", headers={"X-Request-ID": "req-boom"})
    assert response.status_code == 500
    body = response.json()["error"]
    assert body == {
        "code": "INTERNAL_ERROR",
        "message": "服务器内部错误",
        "details": {},
        "request_id": "req-boom",
    }
    assert "division-by-zero-secret" not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text
    assert "RuntimeError" in caplog.text
    assert "division-by-zero-secret" in caplog.text
    assert "req-boom" in caplog.text


async def test_retry_after_header(client: httpx.AsyncClient) -> None:
    response = await client.get("/rate-limited")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json()["error"]["details"] == {"retry_after": 30}

    without = await client.get("/rate-limited-no-header")
    assert without.status_code == 429
    assert "Retry-After" not in without.headers


async def test_handler_fallback_branches() -> None:
    request = _request()
    token = request_id_var.set(None)

    fallback_app = await _app_error_handler(request, RuntimeError("plain"))
    assert fallback_app.status_code == 500
    assert _decode(fallback_app)["error"]["code"] == "INTERNAL_ERROR"

    fallback_validation = await _validation_error_handler(request, RuntimeError("plain"))
    assert fallback_validation.status_code == 400
    assert _decode(fallback_validation)["error"]["details"] == {"errors": []}

    fallback_http = await _http_exception_handler(request, RuntimeError("plain"))
    assert fallback_http.status_code == 500
    assert _decode(fallback_http)["error"]["request_id"] is None

    request_id_var.reset(token)


async def test_unhandled_handler_falls_back_to_request_header() -> None:
    """500 handler 位于 middleware 栈之外时，仍能从请求头恢复 request_id。"""
    from starlette.requests import Request

    from app.core.errors import _resolve_request_id, _unhandled_exception_handler

    token_ctx = request_id_var.set("ctx-rid")
    try:
        assert _resolve_request_id(_request()) == "ctx-rid"
    finally:
        request_id_var.reset(token_ctx)

    def make_request(header: str | None) -> Request:
        headers: list[tuple[bytes, bytes]] = []
        if header is not None:
            headers.append((b"x-request-id", header.encode()))
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/boom",
                "root_path": "",
                "scheme": "http",
                "query_string": b"",
                "headers": headers,
                "server": ("testserver", 80),
                "client": ("testclient", 1234),
                "http_version": "1.1",
            }
        )

    token = request_id_var.set(None)
    try:
        assert _resolve_request_id(make_request("header-rid")) == "header-rid"
        assert _resolve_request_id(make_request("bad value")) is None
        assert _resolve_request_id(make_request(None)) is None
        response = await _unhandled_exception_handler(
            make_request("header-rid"), RuntimeError("plain")
        )
        assert _decode(response)["error"]["request_id"] == "header-rid"
    finally:
        request_id_var.reset(token)


async def test_request_id_follows_context_var() -> None:
    token = request_id_var.set("context-value")
    try:
        response = await _app_error_handler(_request(), NotFound())
        assert _decode(response)["error"]["request_id"] == "context-value"
    finally:
        request_id_var.reset(token)


async def test_500_response_echoes_request_id_and_security_headers(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """M0-F1：500 由最外层 ServerErrorMiddleware 处理，仍需回写追踪头与安全头。"""
    from app.core.middleware import SECURITY_HEADERS

    with caplog.at_level(logging.ERROR):
        response = await client.get("/boom", headers={"X-Request-ID": "f1-trace"})
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "f1-trace"
    assert response.json()["error"]["request_id"] == "f1-trace"
    for name, value in SECURITY_HEADERS:
        assert response.headers[name] == value
    assert "f1-trace" in caplog.text
    assert "RuntimeError" not in response.text
    assert "division-by-zero-secret" not in response.text


async def test_500_generated_request_id_is_consistent_across_header_body_and_logs(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """M0-F1：不带追踪头时，服务端 UUID4 在响应头、响应体、访问日志三处一致。"""
    import uuid

    from app.core.middleware import SECURITY_HEADERS

    with caplog.at_level(logging.INFO):
        response = await client.get("/boom")
    assert response.status_code == 500
    generated = response.headers.get("X-Request-ID")
    assert generated is not None
    assert str(uuid.UUID(generated)) == generated
    assert response.json()["error"]["request_id"] == generated
    for name, value in SECURITY_HEADERS:
        assert response.headers[name] == value
    access_records = [record for record in caplog.records if "http.access" in record.getMessage()]
    assert access_records, "访问日志未捕获"
    assert generated in access_records[-1].getMessage()


async def test_resolve_request_id_prefers_scope_state() -> None:
    """M0-F1：scope state 优先于 ContextVar 与请求头，保证 500 场景拿到同一个 ID。"""
    from starlette.requests import Request

    from app.core.errors import _resolve_request_id

    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/boom",
        "root_path": "",
        "scheme": "http",
        "query_string": b"",
        "headers": [(b"x-request-id", b"header-rid")],
        "server": ("testserver", 80),
        "client": ("testclient", 1234),
        "http_version": "1.1",
        "state": {"request_id": "state-rid"},
    }
    token = request_id_var.set("ctx-rid")
    try:
        assert _resolve_request_id(Request(scope)) == "state-rid"
    finally:
        request_id_var.reset(token)
