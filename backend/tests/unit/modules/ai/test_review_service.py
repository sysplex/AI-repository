"""单元测试：ReviewService 投资建议复盘与超额收益评估（M10-T04）。"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.modules.ai.models import AIRecommendationOutcome, AIReport
from app.modules.ai.ports import PriceFeedProtocol
from app.modules.ai.review_service import ReviewService


class FakeSession:
    """轻量内存 AsyncSession 模拟器。"""

    def __init__(self) -> None:
        self.entities: dict[uuid.UUID, Any] = {}
        self.added: list[Any] = []
        self.deleted: list[Any] = []

    def add(self, entity: Any) -> None:
        if not getattr(entity, "id", None):
            entity.id = uuid.uuid4()
        if not getattr(entity, "created_at", None):
            entity.created_at = datetime.now(UTC)
        self.entities[entity.id] = entity
        self.added.append(entity)

    async def delete(self, entity: Any) -> None:
        if entity.id in self.entities:
            del self.entities[entity.id]
        self.deleted.append(entity)

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
        if "from ai_recommendation_outcomes" in stmt_str:
            filtered = [e for e in items if isinstance(e, AIRecommendationOutcome)]
        elif "from ai_reports" in stmt_str:
            filtered = [e for e in items if isinstance(e, AIReport)]
        else:
            filtered = items

        # 根据编译参数做 report_id 过滤
        try:
            params = stmt.compile().params
            for k, v in params.items():
                if "report_id" in k:
                    filtered = [e for e in filtered if getattr(e, "report_id", None) == v]
                elif "verdict" in k:
                    filtered = [e for e in filtered if getattr(e, "verdict", None) == v]
                elif "symbol" in k:
                    filtered = [e for e in filtered if getattr(e, "symbol", None) == v]
        except Exception:  # noqa: S110
            pass

        mock_res.scalars.return_value.all.return_value = filtered
        mock_res.scalar_one_or_none.return_value = filtered[0] if filtered else None
        return mock_res


class MockPriceFeed(PriceFeedProtocol):
    """测试用价格供给器。"""

    def __init__(self, prices: dict[tuple[str, date], Decimal] | None = None) -> None:
        self.prices: dict[tuple[str, date], Decimal] = prices or {}

    async def get_price(self, symbol: str, trade_date: date) -> Decimal | None:
        return self.prices.get((symbol.upper(), trade_date))


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession()


class TestReviewServiceExtractReportInfo:
    """研报信息提取测试。"""

    def test_extract_full_info(self) -> None:
        report = AIReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            use_case="stock_analysis",
            params={"symbol": "AAPL"},
            payload={"verdict": "buy", "price": "230.50"},
            cache_key="k1",
            data_snapshot_id="s1",
            prompt_version="v1",
            model="mock",
        )
        sym, verdict, p0 = ReviewService._extract_report_info(report)
        assert sym == "AAPL"
        assert verdict == "buy"
        assert p0 == Decimal("230.50")

    def test_extract_from_quote_nested(self) -> None:
        report = AIReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            use_case="long_term",
            params={},
            payload={"symbol": "NVDA", "verdict": "holdable", "quote": {"price": "$125.00"}},
            cache_key="k2",
            data_snapshot_id="s2",
            prompt_version="v1",
            model="mock",
        )
        sym, verdict, p0 = ReviewService._extract_report_info(report)
        assert sym == "NVDA"
        assert verdict == "holdable"
        assert p0 == Decimal("125.00")

    def test_extract_missing_price_returns_none(self) -> None:
        report = AIReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            use_case="stock_analysis",
            params={"symbol": "TSLA"},
            payload={"verdict": "avoid"},
            cache_key="k3",
            data_snapshot_id="s3",
            prompt_version="v1",
            model="mock",
        )
        sym, verdict, p0 = ReviewService._extract_report_info(report)
        assert sym == "TSLA"
        assert verdict == "avoid"
        assert p0 is None


class TestReviewServiceHorizonDates:
    """基于交易日历计算 T+5, T+20, T+60 交易日。"""

    def test_horizon_dates_calculation(self) -> None:
        # 假设报告出具日为 2026-06-01 (周一)
        report_date = date(2026, 6, 1)
        horizons = ReviewService._calculate_horizon_dates(report_date)
        assert 5 in horizons
        assert 20 in horizons
        assert 60 in horizons
        assert horizons[5] > report_date
        assert horizons[20] > horizons[5]
        assert horizons[60] > horizons[20]


class TestReviewServiceBackfillOutcomes:
    """扫描回填核心流程测试。"""

    @pytest.mark.asyncio
    async def test_session_none_raises_value_error(self) -> None:
        svc = ReviewService(session=None, price_feed=MockPriceFeed())
        with pytest.raises(ValueError, match="AsyncSession 必须传入"):
            await svc.backfill_outcomes()

    @pytest.mark.asyncio
    async def test_no_price_feed_returns_empty(self, fake_session: FakeSession) -> None:
        svc = ReviewService(session=fake_session, price_feed=None)  # type: ignore[arg-type]
        res = await svc.backfill_outcomes()
        assert res == []

    @pytest.mark.asyncio
    async def test_backfill_full_horizons_and_alpha(
        self,
        fake_session: FakeSession,
    ) -> None:
        # 1. 创建研报：2026-01-05 (周一) 出具 AAPL 买入研报
        report_date = date(2026, 1, 5)
        report_dt = datetime(2026, 1, 5, 14, 0, 0, tzinfo=UTC)
        report = AIReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            use_case="stock_analysis",
            params={"symbol": "AAPL"},
            payload={"verdict": "buy", "price": "100.00"},
            cache_key="key_1",
            data_snapshot_id="snap_1",
            prompt_version="v1",
            model="mock",
            status="completed",
            created_at=report_dt,
        )
        fake_session.add(report)

        # 获取对应的交易日锚点
        horizons = ReviewService._calculate_horizon_dates(report_date)
        d5 = horizons[5]
        d20 = horizons[20]
        d60 = horizons[60]

        # 模拟价格数据：
        # AAPL: P0=100, P5=105 (+5%), P20=110 (+10%), P60=120 (+20%)
        # SPY:  P0=500, P20=520 (+4%) -> Alpha_20d = 10% - 4% = +6% (0.0600)
        prices: dict[tuple[str, date], Decimal] = {
            ("AAPL", report_date): Decimal("100.00"),
            ("AAPL", d5): Decimal("105.00"),
            ("AAPL", d20): Decimal("110.00"),
            ("AAPL", d60): Decimal("120.00"),
            ("SPY", report_date): Decimal("500.00"),
            ("SPY", d20): Decimal("520.00"),
        }
        price_feed = MockPriceFeed(prices)
        svc = ReviewService(session=fake_session, price_feed=price_feed)  # type: ignore[arg-type]

        # 2. 模拟在 d60 当天执行回填
        outcomes = await svc.backfill_outcomes(as_of=d60)
        assert len(outcomes) == 1
        res = outcomes[0]
        assert res.symbol == "AAPL"
        assert res.verdict == "buy"
        assert res.price_at_report == Decimal("100.0000")
        assert res.ret_5d == Decimal("0.0500")
        assert res.ret_20d == Decimal("0.1000")
        assert res.ret_vs_spy_20d == Decimal("0.0600")
        assert res.ret_60d == Decimal("0.2000")

    @pytest.mark.asyncio
    async def test_progressive_backfill_and_idempotency(
        self,
        fake_session: FakeSession,
    ) -> None:
        report_date = date(2026, 1, 5)
        report = AIReport(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            use_case="stock_analysis",
            params={"symbol": "NVDA"},
            payload={"verdict": "buy", "price": "100.00"},
            cache_key="key_nvda",
            data_snapshot_id="snap_nvda",
            prompt_version="v1",
            model="mock",
            status="success",
            created_at=datetime(2026, 1, 5, 14, 0, 0, tzinfo=UTC),
        )
        fake_session.add(report)

        horizons = ReviewService._calculate_horizon_dates(report_date)
        d5 = horizons[5]
        d20 = horizons[20]

        prices: dict[tuple[str, date], Decimal] = {
            ("NVDA", report_date): Decimal("100.00"),
            ("NVDA", d5): Decimal("108.00"),
            ("NVDA", d20): Decimal("115.00"),
            ("SPY", report_date): Decimal("500.00"),
            ("SPY", d20): Decimal("510.00"),
        }
        price_feed = MockPriceFeed(prices)
        svc = ReviewService(session=fake_session, price_feed=price_feed)  # type: ignore[arg-type]

        # 阶段 1：时间仅到 d5
        outcomes_1 = await svc.backfill_outcomes(as_of=d5)
        assert len(outcomes_1) == 1
        assert outcomes_1[0].ret_5d == Decimal("0.0800")
        assert outcomes_1[0].ret_20d is None  # 尚未到达 T+20
        assert outcomes_1[0].ret_60d is None

        # 阶段 2：时间推进到 d20 再次扫描
        outcomes_2 = await svc.backfill_outcomes(as_of=d20)
        assert len(outcomes_2) == 1
        assert outcomes_2[0].ret_5d == Decimal("0.0800")  # 保留
        assert outcomes_2[0].ret_20d == Decimal("0.1500")  # 补全
        assert outcomes_2[0].ret_vs_spy_20d == Decimal("0.1300")  # 15% - 2% = 13%


class TestReviewServiceOutcomesSummary:
    """复盘看板聚合与胜率统计测试。"""

    @pytest.mark.asyncio
    async def test_outcomes_summary_aggregation(
        self,
        fake_session: FakeSession,
    ) -> None:
        # 准备样本数据
        # 1. 买入且盈利
        o1 = AIRecommendationOutcome(
            id=uuid.uuid4(),
            report_id=uuid.uuid4(),
            symbol="AAPL",
            verdict="buy",
            price_at_report=Decimal("100"),
            ret_5d=Decimal("0.0300"),
            ret_20d=Decimal("0.0800"),
            ret_60d=Decimal("0.1200"),
            ret_vs_spy_20d=Decimal("0.0500"),
        )
        fake_session.add(o1)

        # 2. 买入但亏损
        o2 = AIRecommendationOutcome(
            id=uuid.uuid4(),
            report_id=uuid.uuid4(),
            symbol="MSFT",
            verdict="buy",
            price_at_report=Decimal("400"),
            ret_5d=Decimal("-0.0100"),
            ret_20d=Decimal("-0.0200"),
            ret_60d=Decimal("0.0100"),
            ret_vs_spy_20d=Decimal("-0.0400"),
        )
        fake_session.add(o2)

        # 3. 避开且下跌（符合预期，算赢）
        o3 = AIRecommendationOutcome(
            id=uuid.uuid4(),
            report_id=uuid.uuid4(),
            symbol="TSLA",
            verdict="avoid",
            price_at_report=Decimal("200"),
            ret_5d=Decimal("-0.0500"),
            ret_20d=Decimal("-0.1000"),
            ret_60d=Decimal("-0.1500"),
            ret_vs_spy_20d=Decimal("-0.0800"),
        )
        fake_session.add(o3)

        svc = ReviewService(session=fake_session)  # type: ignore[arg-type]
        summary = await svc.outcomes()

        assert summary.total_recommendations == 3
        assert summary.evaluated_count == 3
        # buy 胜率：1 赢 1 输 -> 50% (0.5000)
        assert "buy" in summary.by_verdict
        buy_stats = summary.by_verdict["buy"]
        assert buy_stats.total_count == 2
        assert buy_stats.win_rate_20d == Decimal("0.5000")
        assert buy_stats.avg_return_20d == Decimal("0.0300")  # (0.08 - 0.02) / 2

        # avoid 胜率：1 跌 (符合预期) -> 100% (1.0000)
        assert "avoid" in summary.by_verdict
        avoid_stats = summary.by_verdict["avoid"]
        assert avoid_stats.total_count == 1
        assert avoid_stats.win_rate_20d == Decimal("1.0000")
        assert avoid_stats.avg_return_20d == Decimal("-0.1000")

        # 全局胜率：2/3 赢 -> 66.67%
        assert summary.win_rate_20d == Decimal("0.6667")

    @pytest.mark.asyncio
    async def test_outcomes_empty_returns_zero(
        self,
        fake_session: FakeSession,
    ) -> None:
        svc = ReviewService(session=fake_session)  # type: ignore[arg-type]
        summary = await svc.outcomes(symbol="NONEXISTENT")
        assert summary.total_recommendations == 0
        assert summary.evaluated_count == 0
        assert summary.avg_return_20d is None
        assert summary.by_verdict == {}
