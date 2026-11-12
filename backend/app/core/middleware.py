"""请求上下文 / 安全响应头 / CORS 中间件（M0 / T02），`CONTRACTS.md §3`。

T07 在本文件「指标中间件插入点」补唯一一行 `install_metrics(app, settings)`
调用；T02 只留注释，不得自行调用。

M0-F1：``SECURITY_HEADERS`` 公开给 ``app.core.errors`` 的 500 handler 复用，
``RequestContextMiddleware`` 同时把 request_id 写进 ``scope["state"]``。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger, request_id_var
from app.core.metrics import install_metrics

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.core.config import Settings

__all__ = [
    "SECURITY_HEADERS",
    "RequestContextMiddleware",
    "SecurityHeadersMiddleware",
    "install_middlewares",
]

_access_log = get_logger("app.access")

SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
)


def _is_valid_request_id(value: str | None) -> bool:
    """合法条件：非空、≤64 字符、全部为可见 ASCII（0x21–0x7E）。

    契约「合法 UUID/≤64 字符 ASCII」取并集：UUID 属于可见 ASCII 串的子集，
    网关生成的其它 ≤64 字符追踪 ID 也允许沿用；空白与控制字符一律拒绝，
    避免日志注入。
    """
    if not value or len(value) > 64:
        return False
    return all(0x21 <= ord(char) <= 0x7E for char in value)


class RequestContextMiddleware:
    """绑定 request_id、回写响应头，并输出不含敏感头的访问日志。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id")
        request_id: str
        if incoming is not None and _is_valid_request_id(incoming):
            request_id = incoming
        else:
            request_id = str(uuid4())
        token = request_id_var.set(request_id)
        # ServerErrorMiddleware 位于本中间件之外：未捕获异常传播到 500 handler 时
        # ContextVar 已被 finally 里的 reset 清掉。scope 是同一个对象，这里留一份
        # 稳定的 request_id，供 app.core.errors._unhandled_exception_handler 读取。
        state = cast(dict[str, Any], scope.setdefault("state", {}))
        state["request_id"] = request_id
        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            _access_log.info(
                "http.access",
                method=str(scope.get("method", "")),
                path=str(scope.get("path", "")),
                status_code=status_code,
                duration_ms=elapsed_ms,
            )
            request_id_var.reset(token)


class SecurityHeadersMiddleware:
    """三项安全响应头，见 CONTRACTS §3。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS:
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_wrapper)


def install_middlewares(app: FastAPI, settings: Settings) -> None:
    """按 CONTRACTS §3 安装中间件；顺序由本函数内部定义，`main.py` 无需改动。"""
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # 指标中间件插入点（CONTRACTS §3/§8/§9）：install_metrics 的唯一调用点。
    install_metrics(app, settings)

    if settings.cors_origins:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
