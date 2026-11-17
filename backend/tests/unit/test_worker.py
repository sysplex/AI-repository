"""单元测试：ARQ Worker 后台任务与定时作业（M10-T05）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.scheduler.enums import JobStatus
from app.modules.scheduler.schemas import PipelineRunResult
from app.worker import WorkerSettings, on_shutdown, on_startup, ping, run_post_market_pipeline


@pytest.mark.asyncio
async def test_worker_ping() -> None:
    res = await ping({})
    assert res == "pong"


@pytest.mark.asyncio
async def test_worker_run_post_market_pipeline() -> None:
    # 模拟 session factory
    mock_session = AsyncMock()

    @asynccontextmanager
    async def fake_session_factory() -> AsyncIterator[AsyncMock]:
        yield mock_session

    mock_run_result = PipelineRunResult(
        trade_date=date(2026, 11, 17),
        status=JobStatus.COMPLETED,
        started_at=datetime.now(UTC),
        is_trading_day=True,
    )

    with patch("app.worker.PostMarketPipeline") as mock_pipeline_cls:
        mock_instance = mock_pipeline_cls.return_value
        mock_instance.run = AsyncMock(return_value=mock_run_result)

        ctx = {"session_factory": fake_session_factory}
        out = await run_post_market_pipeline(ctx, trade_date="2026-11-17", force=True)

        assert out["trade_date"] == "2026-11-17"
        assert out["status"] == "completed"
        mock_instance.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_lifecycle() -> None:
    ctx: dict[str, Any] = {}
    with patch("app.worker.get_session_factory") as mock_get_sf:
        mock_get_sf.return_value = "fake_factory"
        await on_startup(ctx)
        assert ctx["session_factory"] == "fake_factory"

    with patch("app.worker.dispose_engine", new_callable=AsyncMock) as mock_dispose:
        await on_shutdown(ctx)
        mock_dispose.assert_awaited_once()


def test_worker_settings() -> None:
    assert ping in WorkerSettings.functions
    assert run_post_market_pipeline in WorkerSettings.functions
    assert len(WorkerSettings.cron_jobs) >= 1
    assert WorkerSettings.job_timeout >= 300
