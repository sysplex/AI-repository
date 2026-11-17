"""M10-T01 Scheduler 领域模型与 Schema 单元测试。"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from app.modules.scheduler.enums import DailyReportType, JobStatus
from app.modules.scheduler.models import DailyReport
from app.modules.scheduler.schemas import (
    DailyReportCreate,
    DailyReportFilter,
    DailyReportRead,
)


class TestSchedulerEnums:
    """调度相关枚举测试。"""

    def test_enums(self) -> None:
        assert DailyReportType.MARKET_DIGEST.value == "market_digest"
        assert DailyReportType.PORTFOLIO_DIGEST.value == "portfolio_digest"

        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"


class TestDailyReportSchemas:
    """每日简报 Pydantic Schema 测试。"""

    def test_daily_report_create_public(self) -> None:
        req = DailyReportCreate(
            user_id=None,
            report_date=date(2026, 11, 17),
            report_type=DailyReportType.MARKET_DIGEST,
            title="2026-11-17 美股收盘复盘大盘简报",
            summary="标普 500 上涨 0.8%，科技板块领跑...",
            payload={"sp500_change": "+0.8%", "top_gainers": ["NVDA", "AAPL"]},
        )
        assert req.user_id is None
        assert req.report_date == date(2026, 11, 17)
        assert req.report_type == DailyReportType.MARKET_DIGEST
        assert req.payload["sp500_change"] == "+0.8%"

    def test_daily_report_create_personalized(self) -> None:
        uid = uuid.uuid4()
        req = DailyReportCreate(
            user_id=uid,
            report_date=date(2026, 11, 17),
            report_type=DailyReportType.PORTFOLIO_DIGEST,
            title="您的 2026-11-17 模拟盘持仓日报",
            summary="当日收益 +$1,250.00 (+1.25%)，持仓 3 只股票...",
            payload={"daily_pnl": 1250.00, "positions_count": 3},
        )
        assert req.user_id == uid
        assert req.report_type == DailyReportType.PORTFOLIO_DIGEST

    def test_daily_report_read(self) -> None:
        rid = uuid.uuid4()
        now = datetime.now(UTC)
        read = DailyReportRead(
            id=rid,
            user_id=None,
            report_date=date(2026, 11, 17),
            report_type=DailyReportType.MARKET_DIGEST,
            title="大盘简报",
            summary="行情摘要",
            payload={"market": "open"},
            created_at=now,
        )
        assert read.id == rid
        assert read.report_type == DailyReportType.MARKET_DIGEST
        assert read.created_at == now

    def test_daily_report_filter(self) -> None:
        f = DailyReportFilter(
            report_date=date(2026, 11, 17),
            report_type=DailyReportType.MARKET_DIGEST,
        )
        assert f.report_date == date(2026, 11, 17)
        assert f.report_type == DailyReportType.MARKET_DIGEST


class TestSchedulerOrmModels:
    """调度 ORM 实体测试。"""

    def test_daily_report_orm_instantiation(self) -> None:
        report = DailyReport(
            user_id=None,
            report_date=date(2026, 11, 17),
            report_type="market_digest",
            title="美股大盘全天复盘",
            summary="收盘综述",
            payload={"indices": {"sp500": 5800}},
        )
        assert report.user_id is None
        assert report.report_date == date(2026, 11, 17)
        assert report.__tablename__ == "daily_reports"
