"""M4-T02 单元测试：费用模型、滑点计算、PDT 规则与订单验证引擎。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.modules.simbroker.fee import FeeEngine, calculate_fee, calculate_slippage
from app.modules.simbroker.pdt import PdtEngine
from app.modules.simbroker.schemas import FeeModelConfig, OrderCreate
from app.modules.simbroker.validator import OrderValidator


class TestFeeEngine:
    """费用计算引擎测试"""

    def test_zero_fee_model(self) -> None:
        config = FeeModelConfig(type="zero")
        fee = calculate_fee(Decimal("100"), Decimal("150.00"), config)
        assert fee == Decimal("0.0000")

    def test_per_share_fee_model(self) -> None:
        config = FeeModelConfig(type="per_share", per_share=Decimal("0.0050"))
        # 200 shares * $0.005 = $1.0000
        fee = calculate_fee(Decimal("200"), Decimal("100.00"), config)
        assert fee == Decimal("1.0000")

    def test_bps_fee_model(self) -> None:
        # 10 bps = 0.10% = 0.001
        config = FeeModelConfig(type="bps", bps=Decimal("10.0"))
        # 100 shares * $100.00 = $10,000 * 0.001 = $10.0000
        fee = calculate_fee(Decimal("100"), Decimal("100.00"), config)
        assert fee == Decimal("10.0000")

    def test_tiered_fee_model(self) -> None:
        # 混合阶梯模型：每股 $0.01 + 5 bps (0.05%)
        config = FeeModelConfig(type="tiered", per_share=Decimal("0.01"), bps=Decimal("5.0"))
        # 100 shares @ $50 = $5,000
        # 固定费: 100 * 0.01 = $1.00
        # 比例费: 5,000 * 0.0005 = $2.50
        # 总费: $3.5000
        fee = calculate_fee(Decimal("100"), Decimal("50.00"), config)
        assert fee == Decimal("3.5000")

    def test_min_and_max_fee_caps(self) -> None:
        # 设定保底 $1.00，封顶 $10.00
        config = FeeModelConfig(
            type="per_share",
            per_share=Decimal("0.001"),
            min_fee=Decimal("1.0000"),
            max_fee=Decimal("10.0000"),
        )
        # 100 shares * $0.001 = $0.10 < $1.00 => $1.0000
        low_fee = calculate_fee(Decimal("100"), Decimal("50.00"), config)
        assert low_fee == Decimal("1.0000")

        # 20,000 shares * $0.001 = $20.00 > $10.00 => $10.0000
        high_fee = calculate_fee(Decimal("20000"), Decimal("50.00"), config)
        assert high_fee == Decimal("10.0000")

    def test_fee_edge_cases(self) -> None:
        config = FeeModelConfig(type="per_share", per_share=Decimal("0.01"))
        assert calculate_fee(Decimal("0"), Decimal("100.00"), config) == Decimal("0.0000")
        assert calculate_fee(Decimal("100"), Decimal("0.00"), config) == Decimal("0.0000")
        assert calculate_fee(Decimal("-10"), Decimal("50.00"), config) == Decimal("0.0000")

    def test_fee_engine_wrapper(self) -> None:
        config = FeeModelConfig(type="per_share", per_share=Decimal("0.02"))
        assert FeeEngine.compute_fee(Decimal("50"), Decimal("10.00"), config) == Decimal("1.0000")


class TestSlippageCalculation:
    """滑点计算测试"""

    def test_buy_slippage_upward(self) -> None:
        # 基准价 $100.00，滑点 10 bps (0.10%) => $100.1000
        price = calculate_slippage(Decimal("100.00"), "buy", Decimal("10.0"))
        assert price == Decimal("100.1000")

    def test_sell_slippage_downward(self) -> None:
        # 基准价 $100.00，滑点 10 bps (0.10%) => $99.9000
        price = calculate_slippage(Decimal("100.00"), "sell", Decimal("10.0"))
        assert price == Decimal("99.9000")

    def test_zero_slippage(self) -> None:
        price = calculate_slippage(Decimal("175.50"), "buy", Decimal("0.0"))
        assert price == Decimal("175.5000")

    def test_extreme_slippage_non_negative(self) -> None:
        # 卖出滑点超过 100% 不得产生负价
        price = calculate_slippage(Decimal("10.00"), "sell", Decimal("15000.0"))
        assert price == Decimal("0.0000")

    def test_slippage_edge_cases(self) -> None:
        assert calculate_slippage(Decimal("0.00"), "buy", Decimal("5.0")) == Decimal("0.0000")
        assert calculate_slippage(Decimal("-10.00"), "buy", Decimal("5.0")) == Decimal("0.0000")

    def test_fee_engine_slippage_wrapper(self) -> None:
        p = FeeEngine.compute_slippage_price(Decimal("50.00"), "buy", Decimal("20.0"))
        assert p == Decimal("50.1000")


@dataclass
class MockTrade:
    trade_date: date
    symbol: str
    side: str


class TestPdtEngine:
    """美股 PDT 5 日滑动窗口与合规拦截测试"""

    def test_count_day_trades_single_day(self) -> None:
        d1 = date(2026, 11, 10)
        trades = [
            MockTrade(trade_date=d1, symbol="AAPL", side="buy"),
            MockTrade(trade_date=d1, symbol="AAPL", side="sell"),
            MockTrade(trade_date=d1, symbol="MSFT", side="buy"),
        ]
        # AAPL 在同一天既买又卖，计数 1；MSFT 仅买入，不计数
        count = PdtEngine.count_day_trades(trades, [d1])
        assert count == 1

    def test_count_day_trades_rolling_window(self) -> None:
        d1 = date(2026, 11, 9)
        d2 = date(2026, 11, 10)
        d3 = date(2026, 11, 11)
        d_out = date(2026, 11, 1)  # 窗口外
        trades = [
            MockTrade(trade_date=d1, symbol="AAPL", side="buy"),
            MockTrade(trade_date=d1, symbol="AAPL", side="sell"),  # +1
            MockTrade(trade_date=d2, symbol="NVDA", side="buy"),
            MockTrade(trade_date=d2, symbol="NVDA", side="sell"),  # +1
            MockTrade(trade_date=d3, symbol="TSLA", side="buy"),  # 仅买入，0
            MockTrade(trade_date=d_out, symbol="AMZN", side="buy"),
            MockTrade(trade_date=d_out, symbol="AMZN", side="sell"),  # 窗口外，不计
        ]
        count = PdtEngine.count_day_trades(trades, [d1, d2, d3])
        assert count == 2

    def test_pdt_disabled(self) -> None:
        # 当 pdt_enabled=False 时不受任何限制
        status = PdtEngine.evaluate(
            equity=Decimal("5000.00"),
            pdt_enabled=False,
            current_day_trades_count=5,
            is_closing_same_day=True,
        )
        assert not status.is_restricted
        assert not status.warning
        assert not status.pdt_enabled

    def test_pdt_exempt_for_equity_above_25k(self) -> None:
        # 净值达到 $25,000 以上豁免 PDT 交易限制
        status = PdtEngine.evaluate(
            equity=Decimal("30000.00"),
            pdt_enabled=True,
            current_day_trades_count=4,
            is_closing_same_day=True,
        )
        assert not status.is_restricted
        assert not status.warning
        assert "waived" in (status.message or "")

    def test_pdt_warning_and_restriction_sub_25k(self) -> None:
        equity = Decimal("15000.00")

        # 累计 2 次，不结转平仓 => count 2, no warning, not restricted
        s1 = PdtEngine.evaluate(equity, True, current_day_trades_count=2, is_closing_same_day=False)
        assert s1.day_trades_count == 2
        assert not s1.warning
        assert not s1.is_restricted

        # 累计 2 次，当前平仓将变为第 3 次 => warning=True, not restricted
        s2 = PdtEngine.evaluate(equity, True, current_day_trades_count=2, is_closing_same_day=True)
        assert s2.day_trades_count == 3
        assert s2.warning
        assert not s2.is_restricted

        # 累计 3 次，当前平仓将变为第 4 次 => is_restricted=True, warning=True
        s3 = PdtEngine.evaluate(equity, True, current_day_trades_count=3, is_closing_same_day=True)
        assert s3.day_trades_count == 4
        assert s3.is_restricted
        assert s3.warning
        assert "PDT_RESTRICTION" in (s3.message or "")


class TestOrderValidator:
    """订单前置校验引擎全流程测试"""

    @pytest.fixture
    def default_fee_model(self) -> FeeModelConfig:
        return FeeModelConfig(type="per_share", per_share=Decimal("0.005"))

    def test_invalid_symbol(self, default_fee_model: FeeModelConfig) -> None:
        # 标的代码含非法字符或空格
        req = OrderCreate(symbol="AAPL INVALID", side="buy", type="market", qty=Decimal("10"))
        res = OrderValidator.validate(
            order_req=req,
            account_cash=Decimal("10000.00"),
            account_slippage_bps=Decimal("5.0"),
            account_fee_model=default_fee_model,
            account_pdt_enabled=True,
            account_equity=Decimal("10000.00"),
        )
        assert not res.is_valid
        assert res.error_code == "INVALID_ORDER_PARAMS"

    def test_invalid_qty_defensive(self, default_fee_model: FeeModelConfig) -> None:
        # 使用 model_construct 绕过 Pydantic 前置验证测试验证器的防御性判断
        req = OrderCreate.model_construct(
            symbol="AAPL", side="buy", type="market", qty=Decimal("0"), tif="day", source="manual"
        )
        res = OrderValidator.validate(
            order_req=req,
            account_cash=Decimal("10000.00"),
            account_slippage_bps=Decimal("5.0"),
            account_fee_model=default_fee_model,
            account_pdt_enabled=True,
            account_equity=Decimal("10000.00"),
        )
        assert not res.is_valid
        assert res.error_code == "INVALID_ORDER_PARAMS"

    def test_limit_order_missing_price(self, default_fee_model: FeeModelConfig) -> None:
        req = OrderCreate(
            symbol="AAPL", side="buy", type="limit", qty=Decimal("10"), limit_price=None
        )
        res = OrderValidator.validate(
            order_req=req,
            account_cash=Decimal("10000.00"),
            account_slippage_bps=Decimal("5.0"),
            account_fee_model=default_fee_model,
            account_pdt_enabled=True,
            account_equity=Decimal("10000.00"),
        )
        assert not res.is_valid
        assert res.error_code == "INVALID_ORDER_PARAMS"

    def test_stop_order_missing_price(self, default_fee_model: FeeModelConfig) -> None:
        req = OrderCreate(
            symbol="AAPL", side="sell", type="stop", qty=Decimal("10"), stop_price=None
        )
        res = OrderValidator.validate(
            order_req=req,
            account_cash=Decimal("10000.00"),
            account_slippage_bps=Decimal("5.0"),
            account_fee_model=default_fee_model,
            account_pdt_enabled=True,
            account_equity=Decimal("10000.00"),
            current_position_qty=Decimal("20"),
        )
        assert not res.is_valid
        assert res.error_code == "INVALID_ORDER_PARAMS"

    def test_buy_order_insufficient_funds(self, default_fee_model: FeeModelConfig) -> None:
        # 买入 100 股 @ $150.00 = $15,000 + 滑点 + 手续费，当前仅有 $10,000 现金
        req = OrderCreate(
            symbol="AAPL",
            side="buy",
            type="limit",
            qty=Decimal("100"),
            limit_price=Decimal("150.00"),
        )
        res = OrderValidator.validate(
            order_req=req,
            account_cash=Decimal("10000.00"),
            account_slippage_bps=Decimal("5.0"),
            account_fee_model=default_fee_model,
            account_pdt_enabled=True,
            account_equity=Decimal("10000.00"),
        )
        assert not res.is_valid
        assert res.error_code == "INSUFFICIENT_FUNDS"
        assert "INSUFFICIENT_FUNDS" in (res.reject_reason or "")
        assert res.estimated_total_cost is not None and res.estimated_total_cost > Decimal(
            "15000.00"
        )

    def test_buy_order_sufficient_funds(self, default_fee_model: FeeModelConfig) -> None:
        # 现金 $20,000，充足
        req = OrderCreate(
            symbol="AAPL",
            side="buy",
            type="limit",
            qty=Decimal("100"),
            limit_price=Decimal("150.00"),
        )
        res = OrderValidator.validate(
            order_req=req,
            account_cash=Decimal("20000.00"),
            account_slippage_bps=Decimal("5.0"),
            account_fee_model=default_fee_model,
            account_pdt_enabled=True,
            account_equity=Decimal("20000.00"),
        )
        assert res.is_valid
        assert res.error_code is None
        assert res.estimated_price is not None
        assert res.estimated_total_cost is not None

    def test_sell_order_overselling_rejected(self, default_fee_model: FeeModelConfig) -> None:
        # 当前持仓 5 股，尝试卖出 10 股 => 超卖拦截
        req = OrderCreate(symbol="TSLA", side="sell", type="market", qty=Decimal("10"))
        res = OrderValidator.validate(
            order_req=req,
            account_cash=Decimal("1000.00"),
            account_slippage_bps=Decimal("5.0"),
            account_fee_model=default_fee_model,
            account_pdt_enabled=True,
            account_equity=Decimal("5000.00"),
            current_position_qty=Decimal("5.0"),
            current_market_price=Decimal("200.00"),
        )
        assert not res.is_valid
        assert res.error_code == "INSUFFICIENT_POSITION"
        assert "INSUFFICIENT_POSITION" in (res.reject_reason or "")

    def test_sell_order_sufficient_position(self, default_fee_model: FeeModelConfig) -> None:
        # 当前持仓 15 股，卖出 10 股 => 通过
        req = OrderCreate(symbol="TSLA", side="sell", type="market", qty=Decimal("10"))
        res = OrderValidator.validate(
            order_req=req,
            account_cash=Decimal("1000.00"),
            account_slippage_bps=Decimal("5.0"),
            account_fee_model=default_fee_model,
            account_pdt_enabled=True,
            account_equity=Decimal("5000.00"),
            current_position_qty=Decimal("15.0"),
            current_market_price=Decimal("200.00"),
        )
        assert res.is_valid
        assert res.error_code is None

    def test_sell_order_pdt_restriction_rejected(self, default_fee_model: FeeModelConfig) -> None:
        # 净值 $10,000 < $25,000，已发生 3 次日内交易，本笔平仓构成第 4 次 => 拦截
        req = OrderCreate(symbol="NVDA", side="sell", type="market", qty=Decimal("10"))
        res = OrderValidator.validate(
            order_req=req,
            account_cash=Decimal("2000.00"),
            account_slippage_bps=Decimal("5.0"),
            account_fee_model=default_fee_model,
            account_pdt_enabled=True,
            account_equity=Decimal("10000.00"),
            current_position_qty=Decimal("20.0"),
            current_market_price=Decimal("120.00"),
            rolling_day_trades=3,
            is_same_day_roundtrip=True,
        )
        assert not res.is_valid
        assert res.error_code == "PDT_RESTRICTION"
        assert "PDT_RESTRICTION" in (res.reject_reason or "")
