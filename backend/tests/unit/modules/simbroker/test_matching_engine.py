"""M4-T03 单元测试：核心撮合引擎（市价/限价/止损单、TIF 与行情缺失防御）。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.modules.simbroker.matcher import MatchingEngine
from app.modules.simbroker.ports import BarProtocol
from app.modules.simbroker.schemas import FeeModelConfig


@dataclass
class MockBar:
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 1000000


@dataclass
class MockOrder:
    id: uuid.UUID
    symbol: str
    side: str
    type: str
    qty: Decimal
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    tif: str = "day"
    status: str = "accepted"


class TestMatchingEngineMarketOrders:
    """市价单撮合测试"""

    @pytest.fixture
    def default_fee(self) -> FeeModelConfig:
        return FeeModelConfig(type="per_share", per_share=Decimal("0.005"))

    def test_market_buy_fill(self, default_fee: FeeModelConfig) -> None:
        # open $100.00, slippage 10 bps (0.10%) => fill $100.1000
        bar = MockBar(
            trade_date=date(2026, 11, 13),
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("99.00"),
            close=Decimal("104.00"),
        )
        order = MockOrder(
            id=uuid.uuid4(),
            symbol="AAPL",
            side="buy",
            type="market",
            qty=Decimal("100"),
        )
        res = MatchingEngine.match_order(
            order=order,
            bar=bar,
            slippage_bps=Decimal("10.0"),
            fee_model=default_fee,
        )
        assert res.status == "filled"
        assert res.filled_qty == Decimal("100")
        assert res.fill_price == Decimal("100.1000")
        assert res.fee == Decimal("0.5000")  # 100 * 0.005

    def test_market_sell_fill(self, default_fee: FeeModelConfig) -> None:
        # open $100.00, slippage 10 bps => fill $99.9000
        bar = MockBar(
            trade_date=date(2026, 11, 13),
            open=Decimal("100.00"),
            high=Decimal("102.00"),
            low=Decimal("98.00"),
            close=Decimal("99.00"),
        )
        order = MockOrder(
            id=uuid.uuid4(),
            symbol="AAPL",
            side="sell",
            type="market",
            qty=Decimal("50"),
        )
        res = MatchingEngine.match_order(
            order=order,
            bar=bar,
            slippage_bps=Decimal("10.0"),
            fee_model=default_fee,
        )
        assert res.status == "filled"
        assert res.filled_qty == Decimal("50")
        assert res.fill_price == Decimal("99.9000")
        assert res.fee == Decimal("0.2500")


class TestMatchingEngineLimitOrders:
    """限价单撮合测试"""

    @pytest.fixture
    def default_fee(self) -> FeeModelConfig:
        return FeeModelConfig(type="zero")

    def test_limit_buy_gap_down_price_improvement(self, default_fee: FeeModelConfig) -> None:
        # limit buy $105.00, open $102.00 <= $105.00 => 按 open $102.00 成交（跳空穿透更优价）
        bar = MockBar(
            trade_date=date(2026, 11, 13),
            open=Decimal("102.00"),
            high=Decimal("104.00"),
            low=Decimal("101.00"),
            close=Decimal("103.00"),
        )
        order = MockOrder(
            id=uuid.uuid4(),
            symbol="MSFT",
            side="buy",
            type="limit",
            qty=Decimal("10"),
            limit_price=Decimal("105.00"),
        )
        res = MatchingEngine.match_order(order, bar, Decimal("5.0"), default_fee)
        assert res.status == "filled"
        assert res.fill_price == Decimal("102.00")

    def test_limit_buy_intraday_hit(self, default_fee: FeeModelConfig) -> None:
        # limit buy $101.00, open $103.00, low $100.50 => 盘中触及，按限价 $101.00 成交
        bar = MockBar(
            trade_date=date(2026, 11, 13),
            open=Decimal("103.00"),
            high=Decimal("104.00"),
            low=Decimal("100.50"),
            close=Decimal("102.00"),
        )
        order = MockOrder(
            id=uuid.uuid4(),
            symbol="MSFT",
            side="buy",
            type="limit",
            qty=Decimal("10"),
            limit_price=Decimal("101.00"),
        )
        res = MatchingEngine.match_order(order, bar, Decimal("5.0"), default_fee)
        assert res.status == "filled"
        assert res.fill_price == Decimal("101.00")

    def test_limit_buy_not_hit(self, default_fee: FeeModelConfig) -> None:
        # limit buy $98.00, low $100.00 => 未触及
        bar = MockBar(
            trade_date=date(2026, 11, 13),
            open=Decimal("102.00"),
            high=Decimal("105.00"),
            low=Decimal("100.00"),
            close=Decimal("103.00"),
        )
        order_day = MockOrder(
            id=uuid.uuid4(),
            symbol="MSFT",
            side="buy",
            type="limit",
            qty=Decimal("10"),
            limit_price=Decimal("98.00"),
            tif="day",
        )
        # 盘中不满足撮合条件
        res_midday = MatchingEngine.match_order(
            order_day, bar, Decimal("5.0"), default_fee, is_market_close=False
        )
        assert res_midday.status == "accepted"

        # 收盘批处理时 DAY 订单过期
        res_close = MatchingEngine.match_order(
            order_day, bar, Decimal("5.0"), default_fee, is_market_close=True
        )
        assert res_close.status == "expired"

        # GTC 订单收盘保持 accepted
        order_gtc = MockOrder(
            id=uuid.uuid4(),
            symbol="MSFT",
            side="buy",
            type="limit",
            qty=Decimal("10"),
            limit_price=Decimal("98.00"),
            tif="gtc",
        )
        res_gtc = MatchingEngine.match_order(
            order_gtc, bar, Decimal("5.0"), default_fee, is_market_close=True
        )
        assert res_gtc.status == "accepted"

    def test_limit_sell_gap_up_price_improvement(self, default_fee: FeeModelConfig) -> None:
        # limit sell $150.00, open $153.00 >= $150.00 => 按 open $153.00 成交（跳空穿透更优价）
        bar = MockBar(
            trade_date=date(2026, 11, 13),
            open=Decimal("153.00"),
            high=Decimal("155.00"),
            low=Decimal("151.00"),
            close=Decimal("154.00"),
        )
        order = MockOrder(
            id=uuid.uuid4(),
            symbol="NVDA",
            side="sell",
            type="limit",
            qty=Decimal("20"),
            limit_price=Decimal("150.00"),
        )
        res = MatchingEngine.match_order(order, bar, Decimal("5.0"), default_fee)
        assert res.status == "filled"
        assert res.fill_price == Decimal("153.00")

    def test_limit_sell_intraday_hit(self, default_fee: FeeModelConfig) -> None:
        # limit sell $152.00, open $149.00, high $153.00 => 盘中触及，按限价 $152.00 成交
        bar = MockBar(
            trade_date=date(2026, 11, 13),
            open=Decimal("149.00"),
            high=Decimal("153.00"),
            low=Decimal("148.00"),
            close=Decimal("151.00"),
        )
        order = MockOrder(
            id=uuid.uuid4(),
            symbol="NVDA",
            side="sell",
            type="limit",
            qty=Decimal("20"),
            limit_price=Decimal("152.00"),
        )
        res = MatchingEngine.match_order(order, bar, Decimal("5.0"), default_fee)
        assert res.status == "filled"
        assert res.fill_price == Decimal("152.00")


class TestMatchingEngineStopOrders:
    """止损单撮合测试"""

    @pytest.fixture
    def default_fee(self) -> FeeModelConfig:
        return FeeModelConfig(type="zero")

    def test_stop_buy_gap_up_worse_price(self, default_fee: FeeModelConfig) -> None:
        # 突破止损买入：stop_price $110.00, open $112.00, high $115.00
        # 触发价 max(stop, open) = $112.00，加上 10 bps 滑点 = $112.1120
        bar = MockBar(
            trade_date=date(2026, 11, 13),
            open=Decimal("112.00"),
            high=Decimal("115.00"),
            low=Decimal("111.00"),
            close=Decimal("114.00"),
        )
        order = MockOrder(
            id=uuid.uuid4(),
            symbol="AMD",
            side="buy",
            type="stop",
            qty=Decimal("100"),
            stop_price=Decimal("110.00"),
        )
        res = MatchingEngine.match_order(order, bar, Decimal("10.0"), default_fee)
        assert res.status == "filled"
        assert res.fill_price == Decimal("112.1120")

    def test_stop_buy_intraday_touch(self, default_fee: FeeModelConfig) -> None:
        # stop_price $110.00, open $106.00, high $111.00
        # 触发价 max(stop, open) = $110.00，加上 10 bps 滑点 = $110.1100
        bar = MockBar(
            trade_date=date(2026, 11, 13),
            open=Decimal("106.00"),
            high=Decimal("111.00"),
            low=Decimal("105.00"),
            close=Decimal("109.00"),
        )
        order = MockOrder(
            id=uuid.uuid4(),
            symbol="AMD",
            side="buy",
            type="stop",
            qty=Decimal("100"),
            stop_price=Decimal("110.00"),
        )
        res = MatchingEngine.match_order(order, bar, Decimal("10.0"), default_fee)
        assert res.status == "filled"
        assert res.fill_price == Decimal("110.1100")

    def test_stop_sell_gap_down_worse_price(self, default_fee: FeeModelConfig) -> None:
        # 跌破止损卖出：stop_price $90.00, open $88.00, low $85.00
        # 触发价 min(stop, open) = $88.00，扣除 10 bps 滑点 = $87.9120
        bar = MockBar(
            trade_date=date(2026, 11, 13),
            open=Decimal("88.00"),
            high=Decimal("89.00"),
            low=Decimal("85.00"),
            close=Decimal("86.00"),
        )
        order = MockOrder(
            id=uuid.uuid4(),
            symbol="AMD",
            side="sell",
            type="stop",
            qty=Decimal("100"),
            stop_price=Decimal("90.00"),
        )
        res = MatchingEngine.match_order(order, bar, Decimal("10.0"), default_fee)
        assert res.status == "filled"
        assert res.fill_price == Decimal("87.9120")

    def test_stop_sell_intraday_touch(self, default_fee: FeeModelConfig) -> None:
        # stop_price $90.00, open $93.00, low $89.00
        # 触发价 min(stop, open) = $90.00，扣除 10 bps 滑点 = $89.9100
        bar = MockBar(
            trade_date=date(2026, 11, 13),
            open=Decimal("93.00"),
            high=Decimal("94.00"),
            low=Decimal("89.00"),
            close=Decimal("91.00"),
        )
        order = MockOrder(
            id=uuid.uuid4(),
            symbol="AMD",
            side="sell",
            type="stop",
            qty=Decimal("100"),
            stop_price=Decimal("90.00"),
        )
        res = MatchingEngine.match_order(order, bar, Decimal("10.0"), default_fee)
        assert res.status == "filled"
        assert res.fill_price == Decimal("89.9100")


class TestMissingBarAndEdgeCases:
    """行情缺失防御与边界状态测试"""

    def test_missing_bar_defense(self) -> None:
        # 行情 K 线缺失时，订单严格保持 accepted，发出告警日志，严禁用陈旧价格成交
        order = MockOrder(
            id=uuid.uuid4(),
            symbol="UNKNOWN",
            side="buy",
            type="market",
            qty=Decimal("50"),
        )
        fee = FeeModelConfig()
        res = MatchingEngine.match_order(
            order, bar=None, slippage_bps=Decimal("5.0"), fee_model=fee
        )
        assert res.status == "accepted"
        assert res.fill_price is None
        assert res.filled_qty == Decimal("0.0000")
        assert "Market data missing" in (res.message or "")

    def test_ignore_already_filled_or_cancelled_order(self) -> None:
        order = MockOrder(
            id=uuid.uuid4(),
            symbol="AAPL",
            side="buy",
            type="market",
            qty=Decimal("10"),
            status="filled",
        )
        bar = MockBar(
            trade_date=date(2026, 11, 13),
            open=Decimal("150.00"),
            high=Decimal("155.00"),
            low=Decimal("149.00"),
            close=Decimal("152.00"),
        )
        res = MatchingEngine.match_order(order, bar, Decimal("5.0"), FeeModelConfig())
        assert res.status == "filled"
        assert res.fill_price is None  # 不再重复撮合

    def test_batch_match_orders(self) -> None:
        b_aapl = MockBar(
            date(2026, 11, 13), Decimal("100"), Decimal("105"), Decimal("99"), Decimal("103")
        )
        b_msft = MockBar(
            date(2026, 11, 13), Decimal("200"), Decimal("205"), Decimal("198"), Decimal("202")
        )

        ord1 = MockOrder(uuid.uuid4(), "AAPL", "buy", "market", Decimal("10"))
        ord2 = MockOrder(
            uuid.uuid4(), "MSFT", "sell", "limit", Decimal("5"), limit_price=Decimal("199")
        )
        ord3 = MockOrder(uuid.uuid4(), "GOOGL", "buy", "market", Decimal("8"))  # missing bar

        bars: dict[str, BarProtocol | None] = {"AAPL": b_aapl, "MSFT": b_msft, "GOOGL": None}
        results = MatchingEngine.match_orders(
            [ord1, ord2, ord3],
            bars,
            slippage_bps=Decimal("0.0"),
            fee_model=FeeModelConfig(),
        )
        assert len(results) == 3
        assert results[0].status == "filled"
        assert results[0].fill_price == Decimal("100.0000")
        assert results[1].status == "filled"
        assert results[1].fill_price == Decimal("200.0000")  # open 200 >= 199 price improvement
        assert results[2].status == "accepted"
        assert results[2].fill_price is None
