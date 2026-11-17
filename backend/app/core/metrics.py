"""Prometheus 指标（M0 / T07 / M10-T07），`CONTRACTS.md §8`。

每次 `install_metrics` 都创建**独立** `CollectorRegistry`，避免重复注册到全局
默认注册表（测试间互不影响）。`path_template` 取路由模板而非原始路径，
未匹配路由统一记为 `unmatched`，防止标签基数爆炸。
提供业务与运维度量指标及非阻塞安全埋点接口。
"""

from __future__ import annotations

import contextlib
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

_CURRENT_METRICS: AppMetrics | None = None


class AppMetrics:
    """容器类：持有独立 CollectorRegistry 及其所有注册指标。"""

    def __init__(self, registry: CollectorRegistry, settings: Settings) -> None:
        self.registry = registry
        self.http_requests_total = Counter(
            "http_requests_total",
            "HTTP 请求总数",
            ["method", "path_template", "status"],
            registry=registry,
        )
        self.http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP 请求耗时（秒）",
            ["method", "path_template"],
            registry=registry,
        )
        self.app_info = Gauge(
            "app_info",
            "应用版本与环境",
            ["version", "env"],
            registry=registry,
        )
        self.app_info.labels(version=settings.app_version, env=settings.app_env).set(1)

        # -------------------------------------------------------------
        # 业务与运维度量指标（M10-T07）
        # -------------------------------------------------------------
        self.simbroker_orders_total = Counter(
            "simbroker_orders_total",
            "模拟交易订单总数",
            ["status"],
            registry=registry,
        )
        self.simbroker_trades_total = Counter(
            "simbroker_trades_total",
            "模拟交易撮合成交总数",
            registry=registry,
        )
        self.scheduler_pipeline_runs_total = Counter(
            "scheduler_pipeline_runs_total",
            "收盘批处理 DAG 运行总数",
            ["status"],
            registry=registry,
        )
        self.scheduler_pipeline_duration_seconds = Histogram(
            "scheduler_pipeline_duration_seconds",
            "收盘批处理 DAG 运行耗时（秒）",
            buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
            registry=registry,
        )
        self.alerts_evaluated_total = Counter(
            "alerts_evaluated_total",
            "提醒规则评估总次数",
            registry=registry,
        )
        self.alerts_triggered_total = Counter(
            "alerts_triggered_total",
            "提醒规则触发总次数",
            ["alert_type"],
            registry=registry,
        )
        self.notifications_dispatched_total = Counter(
            "notifications_dispatched_total",
            "多渠道通知投递总次数",
            ["channel_type", "status"],
            registry=registry,
        )
        self.ai_reports_generated_total = Counter(
            "ai_reports_generated_total",
            "AI 研报与每日报告生成总数",
            ["verdict"],
            registry=registry,
        )


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


def create_metrics(settings: Settings, registry: CollectorRegistry | None = None) -> AppMetrics:
    """构建一套与全局注册表隔离的指标对象集。"""
    reg = registry if registry is not None else CollectorRegistry()
    return AppMetrics(reg, settings)


def _new_registry(settings: Settings) -> tuple[CollectorRegistry, Counter, Histogram]:
    """保持内部兼容的注册表构建函数。"""
    metrics = create_metrics(settings)
    return metrics.registry, metrics.http_requests_total, metrics.http_request_duration_seconds


def get_current_metrics() -> AppMetrics | None:
    """获取当前激活的 AppMetrics 单例。"""
    return _CURRENT_METRICS


def set_current_metrics(metrics: AppMetrics | None) -> None:
    """设置当前激活的 AppMetrics 单例（供测试隔离或动态注入）。"""
    global _CURRENT_METRICS
    _CURRENT_METRICS = metrics


def install_metrics(app: FastAPI, settings: Settings) -> None:
    """唯一调用点在 `core/middleware.py` 的「指标中间件插入点」。"""
    metrics = create_metrics(settings)
    app.state.metrics_registry = metrics.registry
    app.state.metrics_enabled = bool(settings.metrics_enabled)
    app.state.app_metrics = metrics
    set_current_metrics(metrics)
    if settings.metrics_enabled:
        app.add_middleware(
            MetricsMiddleware,
            counter=metrics.http_requests_total,
            histogram=metrics.http_request_duration_seconds,
        )


def render_metrics(app: FastAPI) -> bytes:
    """渲染该 app 自己的注册表；未安装指标时返回空字节串。"""
    registry: Any = getattr(app.state, "metrics_registry", None)
    if registry is None:
        return b""
    return generate_latest(registry)


# -------------------------------------------------------------
# 非阻塞、故障隔离的安全埋点辅助函数
# -------------------------------------------------------------


def record_pipeline_run(status: str, duration: float, *, metrics: AppMetrics | None = None) -> None:
    """记录收盘 DAG 流水线执行状态与耗时。"""
    with contextlib.suppress(Exception):
        m = metrics or get_current_metrics()
        if m is not None:
            m.scheduler_pipeline_runs_total.labels(status=status).inc()
            m.scheduler_pipeline_duration_seconds.observe(duration)


def record_alert_evaluated(count: int = 1, *, metrics: AppMetrics | None = None) -> None:
    """记录提醒规则求值总数。"""
    with contextlib.suppress(Exception):
        m = metrics or get_current_metrics()
        if m is not None and count > 0:
            m.alerts_evaluated_total.inc(count)


def record_alert_triggered(alert_type: str, *, metrics: AppMetrics | None = None) -> None:
    """记录提醒规则触发总数。"""
    with contextlib.suppress(Exception):
        m = metrics or get_current_metrics()
        if m is not None:
            m.alerts_triggered_total.labels(alert_type=alert_type).inc()


def record_notification_dispatched(
    channel_type: str, status: str, *, metrics: AppMetrics | None = None
) -> None:
    """记录多渠道通知投递总数。"""
    with contextlib.suppress(Exception):
        m = metrics or get_current_metrics()
        if m is not None:
            m.notifications_dispatched_total.labels(channel_type=channel_type, status=status).inc()


def record_simbroker_order(status: str, *, metrics: AppMetrics | None = None) -> None:
    """记录模拟交易订单状态变更。"""
    with contextlib.suppress(Exception):
        m = metrics or get_current_metrics()
        if m is not None:
            m.simbroker_orders_total.labels(status=status).inc()


def record_simbroker_trade(count: int = 1, *, metrics: AppMetrics | None = None) -> None:
    """记录模拟交易撮合成交数。"""
    with contextlib.suppress(Exception):
        m = metrics or get_current_metrics()
        if m is not None and count > 0:
            m.simbroker_trades_total.inc(count)


def record_ai_report(verdict: str, *, metrics: AppMetrics | None = None) -> None:
    """记录 AI 研报与每日报告生成。"""
    with contextlib.suppress(Exception):
        m = metrics or get_current_metrics()
        if m is not None:
            m.ai_reports_generated_total.labels(verdict=verdict).inc()


__all__ = [
    "CONTENT_TYPE_LATEST",
    "UNMATCHED",
    "AppMetrics",
    "MetricsMiddleware",
    "create_metrics",
    "get_current_metrics",
    "install_metrics",
    "path_template",
    "record_ai_report",
    "record_alert_evaluated",
    "record_alert_triggered",
    "record_notification_dispatched",
    "record_pipeline_run",
    "record_simbroker_order",
    "record_simbroker_trade",
    "render_metrics",
    "set_current_metrics",
]
