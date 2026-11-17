"""业务与运维度量指标单元测试（M10-T07）。

验证 Prometheus 扩展指标：
- simbroker_orders_total / simbroker_trades_total
- scheduler_pipeline_runs_total / scheduler_pipeline_duration_seconds
- alerts_evaluated_total / alerts_triggered_total
- notifications_dispatched_total
- ai_reports_generated_total
- 安全隔离与异常静默兜底机制
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from pydantic import SecretStr

from app.api.router import root_router
from app.core.config import Settings
from app.core.metrics import (
    AppMetrics,
    create_metrics,
    get_current_metrics,
    record_ai_report,
    record_alert_evaluated,
    record_alert_triggered,
    record_notification_dispatched,
    record_pipeline_run,
    record_simbroker_order,
    record_simbroker_trade,
    render_metrics,
    set_current_metrics,
)
from app.core.middleware import install_middlewares


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "postgresql+asyncpg://svc@db.internal:5432/app",
        "redis_url": "redis://cache.internal:6379/0",
        "secret_key": SecretStr("s" * 40),
        "app_version": "1.0.0",
        "app_env": "production",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(autouse=True)
def _reset_metrics() -> Iterator[None]:
    """每个测试前后重置全局指标单例，确保测试独立隔离。"""
    previous = get_current_metrics()
    set_current_metrics(None)
    yield
    set_current_metrics(previous)


def test_app_metrics_initialization() -> None:
    """验证 AppMetrics 初始化时包含所有指标定义。"""
    settings = _settings()
    metrics = create_metrics(settings)
    assert isinstance(metrics, AppMetrics)
    assert metrics.registry is not None

    app = FastAPI()
    app.state.metrics_registry = metrics.registry
    raw = render_metrics(app).decode("utf-8")

    assert "# HELP simbroker_orders_total" in raw
    assert "# HELP simbroker_trades_total" in raw
    assert "# HELP scheduler_pipeline_runs_total" in raw
    assert "# HELP scheduler_pipeline_duration_seconds" in raw
    assert "# HELP alerts_evaluated_total" in raw
    assert "# HELP alerts_triggered_total" in raw
    assert "# HELP notifications_dispatched_total" in raw
    assert "# HELP ai_reports_generated_total" in raw
    assert 'app_info{env="production",version="1.0.0"} 1.0' in raw


def test_record_pipeline_run() -> None:
    """验证收盘流水线运行次数与耗时直方图记录。"""
    metrics = create_metrics(_settings())
    record_pipeline_run("completed", 12.5, metrics=metrics)
    record_pipeline_run("failed", 3.2, metrics=metrics)

    app = FastAPI()
    app.state.metrics_registry = metrics.registry
    raw = render_metrics(app).decode("utf-8")

    assert 'scheduler_pipeline_runs_total{status="completed"} 1.0' in raw
    assert 'scheduler_pipeline_runs_total{status="failed"} 1.0' in raw
    assert "scheduler_pipeline_duration_seconds_count 2.0" in raw
    assert "scheduler_pipeline_duration_seconds_sum 15.7" in raw


def test_record_alert_metrics() -> None:
    """验证提醒规则求值总数与触发总数记录。"""
    metrics = create_metrics(_settings())
    record_alert_evaluated(5, metrics=metrics)
    record_alert_evaluated(3, metrics=metrics)

    record_alert_triggered("price", metrics=metrics)
    record_alert_triggered("thesis_breaker", metrics=metrics)
    record_alert_triggered("price", metrics=metrics)

    app = FastAPI()
    app.state.metrics_registry = metrics.registry
    raw = render_metrics(app).decode("utf-8")

    assert "alerts_evaluated_total 8.0" in raw
    assert 'alerts_triggered_total{alert_type="price"} 2.0' in raw
    assert 'alerts_triggered_total{alert_type="thesis_breaker"} 1.0' in raw


def test_record_notification_dispatched() -> None:
    """验证多渠道通知分发状态与渠道类型统计。"""
    metrics = create_metrics(_settings())
    record_notification_dispatched("email", "success", metrics=metrics)
    record_notification_dispatched("email", "failure", metrics=metrics)
    record_notification_dispatched("webhook", "success", metrics=metrics)
    record_notification_dispatched("in_app", "success", metrics=metrics)

    app = FastAPI()
    app.state.metrics_registry = metrics.registry
    raw = render_metrics(app).decode("utf-8")

    assert 'notifications_dispatched_total{channel_type="email",status="success"} 1.0' in raw
    assert 'notifications_dispatched_total{channel_type="email",status="failure"} 1.0' in raw
    assert 'notifications_dispatched_total{channel_type="webhook",status="success"} 1.0' in raw
    assert 'notifications_dispatched_total{channel_type="in_app",status="success"} 1.0' in raw


def test_record_simbroker_metrics() -> None:
    """验证模拟盘订单与成交统计。"""
    metrics = create_metrics(_settings())
    record_simbroker_order("pending", metrics=metrics)
    record_simbroker_order("filled", metrics=metrics)
    record_simbroker_order("filled", metrics=metrics)
    record_simbroker_order("cancelled", metrics=metrics)

    record_simbroker_trade(1, metrics=metrics)
    record_simbroker_trade(2, metrics=metrics)

    app = FastAPI()
    app.state.metrics_registry = metrics.registry
    raw = render_metrics(app).decode("utf-8")

    assert 'simbroker_orders_total{status="pending"} 1.0' in raw
    assert 'simbroker_orders_total{status="filled"} 2.0' in raw
    assert 'simbroker_orders_total{status="cancelled"} 1.0' in raw
    assert "simbroker_trades_total 3.0" in raw


def test_record_ai_report() -> None:
    """验证 AI 报告与研报评级统计。"""
    metrics = create_metrics(_settings())
    record_ai_report("buy", metrics=metrics)
    record_ai_report("buy", metrics=metrics)
    record_ai_report("avoid", metrics=metrics)
    record_ai_report("market_digest", metrics=metrics)

    app = FastAPI()
    app.state.metrics_registry = metrics.registry
    raw = render_metrics(app).decode("utf-8")

    assert 'ai_reports_generated_total{verdict="buy"} 2.0' in raw
    assert 'ai_reports_generated_total{verdict="avoid"} 1.0' in raw
    assert 'ai_reports_generated_total{verdict="market_digest"} 1.0' in raw


def test_fail_safe_when_metrics_uninitialized() -> None:
    """当指标未初始化时，所有安全记录辅助函数必须无异常静默执行。"""
    set_current_metrics(None)

    # 均不应抛出异常
    record_pipeline_run("completed", 5.0)
    record_alert_evaluated(10)
    record_alert_triggered("price")
    record_notification_dispatched("email", "success")
    record_simbroker_order("filled")
    record_simbroker_trade(1)
    record_ai_report("neutral")


async def test_metrics_endpoint_integration() -> None:
    """验证在完整 FastAPI 链路中，业务记录通过 /metrics 成功暴露。"""
    app = FastAPI(openapi_url="/api/v1/openapi.json")
    install_middlewares(app, _settings())
    app.include_router(root_router)

    # 此时全局单例已由 install_metrics 注册
    record_pipeline_run("completed", 8.4)
    record_alert_evaluated(4)
    record_alert_triggered("thesis_breaker")
    record_notification_dispatched("webhook", "success")
    record_simbroker_trade(3)
    record_ai_report("bullish")

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text

        assert 'scheduler_pipeline_runs_total{status="completed"} 1.0' in text
        assert "scheduler_pipeline_duration_seconds_count 1.0" in text
        assert "alerts_evaluated_total 4.0" in text
        assert 'alerts_triggered_total{alert_type="thesis_breaker"} 1.0' in text
        assert 'notifications_dispatched_total{channel_type="webhook",status="success"} 1.0' in text
        assert "simbroker_trades_total 3.0" in text
        assert 'ai_reports_generated_total{verdict="bullish"} 1.0' in text
