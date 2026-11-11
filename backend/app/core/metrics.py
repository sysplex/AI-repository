"""Prometheus 指标（M0 / T07），`CONTRACTS.md §8`。

每次 `install_metrics` 都创建**独立** `CollectorRegistry`，避免重复注册到全局
默认注册表（测试间互不影响）。`path_template` 取路由模板而非原始路径，
未匹配路由统一记为 `unmatched`，防止标签基数爆炸。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.core.config import Settings

CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
UNMATCHED = "unmatched"

_EXCLUDED_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})


class MetricsMiddleware:
    """纯 ASGI 中间件：记录请求总数与耗时，标签只含路由模板。"""

    def __init__(self, app: ASGIApp, *, counter: Any, histogram: Any) -> None:
        self.app = app
        self._counter = counter
        self._histogram = histogram

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in _EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            template = path_template(scope)
            method = str(scope.get("method", "UNKNOWN"))
            self._counter.labels(
                method=method, path_template=template, status=str(status_code)
            ).inc()
            self._histogram.labels(method=method, path_template=template).observe(
                time.perf_counter() - started
            )


def path_template(scope: Scope) -> str:
    """从 Starlette 匹配到的路由取模板；404 时降级为 `unmatched`。"""
    route = scope.get("route")
    template = getattr(route, "path", None)
    return str(template) if template else UNMATCHED


def _new_registry(settings: Settings) -> tuple[CollectorRegistry, Counter, Histogram]:
    """构建一套与全局注册表隔离的指标对象。"""
    registry = CollectorRegistry()
    counter = Counter(
        "http_requests_total",
        "HTTP 请求总数",
        ["method", "path_template", "status"],
        registry=registry,
    )
    histogram = Histogram(
        "http_request_duration_seconds",
        "HTTP 请求耗时（秒）",
        ["method", "path_template"],
        registry=registry,
    )
    app_info = Gauge("app_info", "应用版本与环境", ["version", "env"], registry=registry)
    app_info.labels(version=settings.app_version, env=settings.app_env).set(1)
    return registry, counter, histogram


def install_metrics(app: FastAPI, settings: Settings) -> None:
    """唯一调用点在 `core/middleware.py` 的「指标中间件插入点」。"""
    registry, counter, histogram = _new_registry(settings)
    app.state.metrics_registry = registry
    app.state.metrics_enabled = bool(settings.metrics_enabled)
    if settings.metrics_enabled:
        app.add_middleware(MetricsMiddleware, counter=counter, histogram=histogram)


def render_metrics(app: FastAPI) -> bytes:
    """渲染该 app 自己的注册表；未安装指标时返回空字节串。"""
    registry: Any = getattr(app.state, "metrics_registry", None)
    if registry is None:
        return b""
    return generate_latest(registry)
