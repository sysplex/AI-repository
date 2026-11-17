"""单元测试：每日大盘与持仓简报生成器（M10-T05）。"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.modules.scheduler.enums import DailyReportType
from app.modules.scheduler.models import DailyReport
from app.modules.scheduler.reports import DailyReportGenerator


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
        filtered = [e for e in items if isinstance(e, DailyReport)]

        # 模拟过滤
        try:
            params = stmt.compile().params
            for k, v in params.items():
                if "report_date" in k:
                    filtered = [e for e in filtered if getattr(e, "report_date", None) == v]
                elif "report_type" in k:
                    filtered = [e for e in filtered if getattr(e, "report_type", None) == v]
                elif "user_id" in k:
                    filtered = [e for e in filtered if getattr(e, "user_id", None) == v]
        except Exception:  # noqa: S110
            pass

        mock_res.scalars.return_value.all.return_value = filtered
        mock_res.scalar_one_or_none.return_value = filtered[0] if filtered else None
        return mock_res


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession()


class TestDailyReportGenerator:
    """简报生成器测试。"""

    def setup_method(self) -> None:
        self.generator = DailyReportGenerator()

    @pytest.mark.asyncio
    async def test_generate_market_digest(self, fake_session: FakeSession) -> None:
        trade_date = date(2026, 11, 17)
        market_snapshot = {
            "SPY": {"current_price": "585.50", "change": "+4.20", "change_pct": "+0.72"},
            "QQQ": {"current_price": "505.20", "change": "+5.80", "change_pct": "+1.16"},
            "movers": {
                "gainers": [{"symbol": "NVDA", "change_pct": "+4.5"}],
                "losers": [{"symbol": "TSLA", "change_pct": "-2.1"}],
            },
        }

        report = await self.generator.generate_market_digest(
            session=fake_session,  # type: ignore[arg-type]
            trade_date=trade_date,
            market_snapshot=market_snapshot,
            alerts_count=5,
        )

        assert report.report_date == trade_date
        assert report.report_type == DailyReportType.MARKET_DIGEST.value
        assert "美股收盘大盘日报" in report.title
        assert "SPY" in report.summary
        assert "NVDA (+4.5%)" in report.summary
        assert "5" in report.summary

        # 测试幂等更新
        report_updated = await self.generator.generate_market_digest(
            session=fake_session,  # type: ignore[arg-type]
            trade_date=trade_date,
            market_snapshot=market_snapshot,
            alerts_count=8,
        )
        assert report_updated.id == report.id
        assert report_updated.payload["alerts_count"] == 8

    @pytest.mark.asyncio
    async def test_generate_portfolio_digest(self, fake_session: FakeSession) -> None:
        trade_date = date(2026, 11, 17)
        user_id = uuid.uuid4()
        account_id = uuid.uuid4()
        positions = [
            {
                "symbol": "AAPL",
                "shares": 50,
                "cost_basis": 220.0,
                "current_price": 230.0,
                "unrealized_pnl": 500.0,
                "unrealized_pnl_pct": 4.55,
            }
        ]
        trades = [
            {
                "time": "10:15:00",
                "symbol": "AAPL",
                "side": "buy",
                "shares": 50,
                "price": 220.0,
                "amount": 11000.0,
            }
        ]

        report = await self.generator.generate_portfolio_digest(
            session=fake_session,  # type: ignore[arg-type]
            user_id=user_id,
            account_id=account_id,
            trade_date=trade_date,
            equity=Decimal("105000.00"),
            cash=Decimal("94000.00"),
            market_value=Decimal("11000.00"),
            drawdown=Decimal("0.025"),
            positions=positions,
            trades=trades,
        )

        assert report.user_id == user_id
        assert report.report_date == trade_date
        assert report.report_type == DailyReportType.PORTFOLIO_DIGEST.value
        assert "$105,000.00" in report.summary
        assert "AAPL" in report.summary
        assert "2.50%" in report.summary

        # 测试空持仓报告渲染
        empty_report = await self.generator.generate_portfolio_digest(
            session=fake_session,  # type: ignore[arg-type]
            user_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            trade_date=date(2026, 11, 18),
            equity=Decimal("100000.00"),
            cash=Decimal("100000.00"),
            market_value=Decimal("0.00"),
            drawdown=Decimal("0.00"),
            positions=[],
            trades=[],
        )
        assert "100% 现金观望" in empty_report.summary
