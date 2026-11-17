"""单元测试：Scheduler 模块 REST API 端点（M10-T06）。

测试覆盖：
- 认证上下文与服务提供器工厂
- 每日简报检索列表与单篇查询（含多租户隔离校验）
- 收盘批处理流水线触发
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import NotFound, Unauthenticated
from app.modules.scheduler.api import (
    RunPipelineRequest,
    get_current_user,
    get_daily_report,
    get_scheduler_service,
    list_daily_reports,
    run_post_market,
    set_scheduler_service_factory,
)
from app.modules.scheduler.enums import DailyReportType, JobStatus
from app.modules.scheduler.schemas import DailyReportRead, PipelineRunResult

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


@pytest.fixture
def sample_market_report() -> DailyReportRead:
    return DailyReportRead(
        id=uuid.uuid4(),
        user_id=None,
        report_date=date(2026, 11, 17),
        report_type=DailyReportType.MARKET_DIGEST,
        title="美股大盘收盘简报",
        summary="今日标普 500 上涨 0.8%",
        payload={"sp500": "+0.8%"},
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_portfolio_report(mock_user: MagicMock) -> DailyReportRead:
    return DailyReportRead(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        report_date=date(2026, 11, 17),
        report_type=DailyReportType.PORTFOLIO_DIGEST,
        title="个人模拟组合收盘复盘",
        summary="总资产 $102,400.00",
        payload={"equity": 102400.0},
        created_at=datetime.now(UTC),
    )


# =============================================================================
# 1. 鉴权与服务提供器测试
# =============================================================================


def test_get_current_user_present(mock_user: MagicMock) -> None:
    req = MagicMock()
    req.state.user = mock_user
    assert get_current_user(req) is mock_user


def test_get_current_user_absent_raises() -> None:
    req = MagicMock()
    req.state.user = None
    with pytest.raises(Unauthenticated, match="需要登录"):
        get_current_user(req)


def test_get_scheduler_service_default() -> None:
    set_scheduler_service_factory(None)
    session = AsyncMock()
    svc = get_scheduler_service(session)
    assert svc is not None


def test_set_scheduler_service_factory_override() -> None:
    custom_mock = MagicMock()
    set_scheduler_service_factory(lambda sess: custom_mock)
    assert get_scheduler_service(AsyncMock()) is custom_mock
    set_scheduler_service_factory(None)


# =============================================================================
# 2. 每日简报端点测试
# =============================================================================


@pytest.mark.asyncio
async def test_list_daily_reports_api(
    mock_user: MagicMock, sample_market_report: DailyReportRead
) -> None:
    service = AsyncMock()
    service.list_daily_reports.return_value = [sample_market_report]

    res = await list_daily_reports(
        service=service,
        user=mock_user,
        report_date=date(2026, 11, 17),
        report_type=DailyReportType.MARKET_DIGEST,
        limit=20,
        offset=0,
    )
    assert len(res) == 1
    assert res[0].title == "美股大盘收盘简报"
    service.list_daily_reports.assert_awaited_once_with(
        user_id=mock_user.id,
        report_date=date(2026, 11, 17),
        report_type=DailyReportType.MARKET_DIGEST,
        limit=20,
        offset=0,
    )


@pytest.mark.asyncio
async def test_get_daily_report_public_success(
    mock_user: MagicMock, sample_market_report: DailyReportRead
) -> None:
    service = AsyncMock()
    service.get_daily_report.return_value = sample_market_report

    res = await get_daily_report(report_id=sample_market_report.id, service=service, user=mock_user)
    assert res.id == sample_market_report.id


@pytest.mark.asyncio
async def test_get_daily_report_private_success(
    mock_user: MagicMock, sample_portfolio_report: DailyReportRead
) -> None:
    service = AsyncMock()
    service.get_daily_report.return_value = sample_portfolio_report

    res = await get_daily_report(
        report_id=sample_portfolio_report.id, service=service, user=mock_user
    )
    assert res.id == sample_portfolio_report.id


@pytest.mark.asyncio
async def test_get_daily_report_not_found(mock_user: MagicMock) -> None:
    service = AsyncMock()
    service.get_daily_report.return_value = None

    with pytest.raises(NotFound, match="报告不存在"):
        await get_daily_report(report_id=uuid.uuid4(), service=service, user=mock_user)


@pytest.mark.asyncio
async def test_get_daily_report_tenant_mismatch_raises_404(
    mock_user: MagicMock, sample_portfolio_report: DailyReportRead
) -> None:
    # 模拟属于其他用户的私有简报
    service = AsyncMock()
    other_user = MagicMock()
    other_user.id = uuid.uuid4()
    service.get_daily_report.return_value = sample_portfolio_report

    with pytest.raises(NotFound, match="报告不存在或无权访问"):
        await get_daily_report(
            report_id=sample_portfolio_report.id, service=service, user=other_user
        )


# =============================================================================
# 3. 调度流水线执行端点测试
# =============================================================================


@pytest.mark.asyncio
async def test_run_post_market_api(mock_user: MagicMock) -> None:
    service = AsyncMock()
    run_res = PipelineRunResult(
        trade_date=date(2026, 11, 17),
        status=JobStatus.COMPLETED,
        started_at=datetime.now(UTC),
        is_trading_day=True,
    )
    service.run_pipeline.return_value = run_res

    req = RunPipelineRequest(trade_date=date(2026, 11, 17), force=True)
    res = await run_post_market(data=req, service=service, user=mock_user)
    assert res.status == JobStatus.COMPLETED
    assert res.trade_date == date(2026, 11, 17)
    service.run_pipeline.assert_awaited_once_with(trade_date=date(2026, 11, 17), force=True)
