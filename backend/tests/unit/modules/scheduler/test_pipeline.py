"""单元测试：收盘后批处理任务链 DAG 调度与 SchedulerService（M10-T05）。"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.scheduler.enums import DailyReportType, JobStatus
from app.modules.scheduler.models import DailyReport
from app.modules.scheduler.pipeline import PostMarketPipeline
from app.modules.scheduler.reports import DailyReportGenerator
from app.modules.scheduler.service import SchedulerService
from app.modules.simbroker.models import SimAccount, SimPosition


class FakeSession:
    """轻量内存 AsyncSession 模拟器。"""

    def __init__(self) -> None:
        self.entities: dict[uuid.UUID, Any] = {}
        self.added: list[Any] = []

    def add(self, entity: Any) -> None:
        if not getattr(entity, "id", None):
            entity.id = uuid.uuid4()
        if not getattr(entity, "created_at", None):
            entity.created_at = datetime.now(UTC)
        self.entities[entity.id] = entity
        self.added.append(entity)

    async def commit(self) -> None:
        pass

    async def refresh(self, entity: Any) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def execute(self, stmt: Any) -> Any:
        mock_res = MagicMock()
        items = list(self.entities.values())
        stmt_str = str(stmt).lower()

        filtered: list[Any]
        if "from daily_reports" in stmt_str:
            filtered = [e for e in items if isinstance(e, DailyReport)]
        elif "from sim_accounts" in stmt_str:
            filtered = [e for e in items if isinstance(e, SimAccount)]
        elif "from sim_positions" in stmt_str:
            filtered = [e for e in items if isinstance(e, SimPosition)]
        else:
            filtered = items

        try:
            params = stmt.compile().params
            for k, v in params.items():
                if "report_date" in k:
                    filtered = [e for e in filtered if getattr(e, "report_date", None) == v]
                elif "user_id" in k:
                    filtered = [e for e in filtered if getattr(e, "user_id", None) == v]
                elif "account_id" in k:
                    filtered = [e for e in filtered if getattr(e, "account_id", None) == v]
                elif "id" in k and isinstance(v, uuid.UUID):
                    filtered = [e for e in filtered if getattr(e, "id", None) == v]
        except Exception:  # noqa: S110
            pass

        mock_res.scalars.return_value.all.return_value = filtered
        mock_res.scalar_one_or_none.return_value = filtered[0] if filtered else None
        return mock_res


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession()


class TestPostMarketPipeline:
    """收盘任务链 DAG 调度器测试。"""

    @pytest.mark.asyncio
    async def test_session_none_raises_value_error(self) -> None:
        pipeline = PostMarketPipeline(session=None)
        with pytest.raises(ValueError, match="AsyncSession 必须传入"):
            await pipeline.run()

    @pytest.mark.asyncio
    async def test_non_trading_day_skipped(self, fake_session: FakeSession) -> None:
        pipeline = PostMarketPipeline(session=fake_session)  # type: ignore[arg-type]
        # 周日 2026-11-15 非美股交易日
        sunday = date(2026, 11, 15)
        res = await pipeline.run(trade_date=sunday, force=False)

        assert res.is_trading_day is False
        assert res.status == JobStatus.COMPLETED
        assert len(res.steps) == 1
        assert res.steps[0].name == "calendar_guard"
        assert "非美股交易日" in (res.error_message or "")

    @pytest.mark.asyncio
    async def test_full_pipeline_run_success(self, fake_session: FakeSession) -> None:
        # 周二 2026-11-17 为美股交易日
        trade_date = date(2026, 11, 17)

        # 准备模拟盘账户
        user_id = uuid.uuid4()
        account = SimAccount(
            id=uuid.uuid4(),
            user_id=user_id,
            name="我的模拟盘",
            cash=Decimal("50000.00"),
            initial_cash=Decimal("100000.00"),
        )
        fake_session.add(account)

        position = SimPosition(
            id=uuid.uuid4(),
            user_id=user_id,
            account_id=account.id,
            symbol="AAPL",
            qty=Decimal("100"),
            avg_cost=Decimal("200.00"),
        )
        fake_session.add(position)

        # Mock 各微服务
        mock_sim_service = MagicMock()
        mock_sim_close_res = MagicMock()
        mock_sim_close_res.equity = Decimal("72000.00")
        mock_sim_close_res.cash = Decimal("50000.00")
        mock_sim_close_res.market_value = Decimal("22000.00")
        mock_sim_close_res.drawdown = Decimal("0.05")
        mock_sim_close_res.expired_orders_count = 2
        mock_sim_service.process_market_close = AsyncMock(return_value=mock_sim_close_res)

        mock_alert_service = MagicMock()
        mock_alert_service.evaluate_alerts = AsyncMock(return_value=[("mock_alert", "mock_res")])

        mock_review_service = MagicMock()
        mock_review_service.backfill_outcomes = AsyncMock(return_value=[{"report_id": "r1"}])

        mock_report_gen = DailyReportGenerator()

        pipeline = PostMarketPipeline(
            session=fake_session,  # type: ignore[arg-type]
            sim_service=mock_sim_service,
            alert_service=mock_alert_service,
            review_service=mock_review_service,
            report_generator=mock_report_gen,
        )

        market_context = {
            "AAPL": {"current_price": "220.00", "change": "+2.50", "change_pct": "+1.15"},
            "SPY": {"current_price": "585.00", "change": "+3.00", "change_pct": "+0.51"},
        }

        run_result = await pipeline.run(
            trade_date=trade_date,
            force=False,
            market_context=market_context,
        )

        assert run_result.status == JobStatus.COMPLETED
        assert run_result.is_trading_day is True
        assert len(run_result.steps) == 6

        step_names = [s.name for s in run_result.steps]
        assert step_names == [
            "market_data_sync",
            "simbroker_settlement",
            "screener_scan",
            "alert_evaluation",
            "ai_review_backfill",
            "daily_reports_generation",
        ]

        # 验证各服务调用
        mock_sim_service.process_market_close.assert_awaited_once()
        mock_alert_service.evaluate_alerts.assert_awaited_once()
        mock_review_service.backfill_outcomes.assert_awaited_once()

        # 验证生成了 market_digest 与 portfolio_digest
        reports = [e for e in fake_session.entities.values() if isinstance(e, DailyReport)]
        types = {r.report_type for r in reports}
        assert DailyReportType.MARKET_DIGEST.value in types
        assert DailyReportType.PORTFOLIO_DIGEST.value in types


class TestSchedulerServiceFacade:
    """SchedulerService 门面服务测试。"""

    @pytest.mark.asyncio
    async def test_scheduler_service_query(self, fake_session: FakeSession) -> None:
        user_id = uuid.uuid4()
        r1 = DailyReport(
            id=uuid.uuid4(),
            user_id=None,
            report_date=date(2026, 11, 17),
            report_type=DailyReportType.MARKET_DIGEST.value,
            title="公共大盘简报",
            summary="Market Summary",
            payload={},
        )
        fake_session.add(r1)

        r2 = DailyReport(
            id=uuid.uuid4(),
            user_id=user_id,
            report_date=date(2026, 11, 17),
            report_type=DailyReportType.PORTFOLIO_DIGEST.value,
            title="个人持仓简报",
            summary="Portfolio Summary",
            payload={},
        )
        fake_session.add(r2)

        svc = SchedulerService(session=fake_session)  # type: ignore[arg-type]

        # 查单条
        fetched = await svc.get_daily_report(r1.id)
        assert fetched is not None
        assert fetched.title == "公共大盘简报"

        # 查不存在
        none_rep = await svc.get_daily_report(uuid.uuid4())
        assert none_rep is None

        # 查列表（带 user_id）
        reps = await svc.list_daily_reports(user_id=user_id)
        assert len(reps) >= 1

        # 查大盘简报
        public_reps = await svc.list_daily_reports(user_id=None)
        assert len(public_reps) >= 1
