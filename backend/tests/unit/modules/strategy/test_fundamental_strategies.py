"""Unit tests for fundamental screening strategies (M3 / T04).

Verifies:
- Protocol compatibility between marketdata.models.Fundamentals and FundamentalsLike.
- ValueBasicStrategy rules evaluation, trigger and rejection cases.
- GrowthBasicStrategy rules evaluation, trigger and rejection cases.
- DividendBasicStrategy rules evaluation, trigger and rejection cases.
- Explicit detection of missing fundamentals or missing fields (no hallucination).
"""

from datetime import date
from decimal import Decimal

from app.modules.marketdata.models import Bar as MarketBar
from app.modules.marketdata.models import Fundamentals as MarketFundamentals
from app.modules.strategy.registry import get_strategy
from app.modules.strategy.schemas import StrategyContext
from app.modules.strategy.strategies.fundamental import (
    DividendBasicStrategy,
    FundamentalsLike,
    GrowthBasicStrategy,
    ValueBasicStrategy,
)


def _make_fundamentals(
    symbol: str = "AAPL",
    as_of: date = date(2026, 1, 1),
    pe_trailing: str | None = None,
    pe_forward: str | None = None,
    pb: str | None = None,
    ps: str | None = None,
    roe: str | None = None,
    net_margin: str | None = None,
    debt_to_equity: str | None = None,
    dividend_yield: str | None = None,
    market_cap: str | None = None,
    missing_fields: list[str] | None = None,
) -> MarketFundamentals:
    """Helper to build real MarketFundamentals models."""
    return MarketFundamentals(
        symbol=symbol,
        as_of=as_of,
        pe_trailing=Decimal(pe_trailing) if pe_trailing is not None else None,
        pe_forward=Decimal(pe_forward) if pe_forward is not None else None,
        pb=Decimal(pb) if pb is not None else None,
        ps=Decimal(ps) if ps is not None else None,
        roe=Decimal(roe) if roe is not None else None,
        net_margin=Decimal(net_margin) if net_margin is not None else None,
        debt_to_equity=Decimal(debt_to_equity) if debt_to_equity is not None else None,
        dividend_yield=Decimal(dividend_yield) if dividend_yield is not None else None,
        market_cap=Decimal(market_cap) if market_cap is not None else None,
        missing_fields=missing_fields or [],
    )


def _make_bar(close: str = "150.0") -> MarketBar:
    return MarketBar(
        symbol="AAPL",
        trade_date=date(2026, 1, 1),
        open=Decimal(close),
        high=Decimal(close) + Decimal("2.0"),
        low=Decimal(close) - Decimal("2.0"),
        close=Decimal(close),
        volume=10000,
    )


class TestFundamentalsProtocol:
    """Tests for protocol compatibility."""

    def test_market_fundamentals_satisfies_protocol(self) -> None:
        fund = _make_fundamentals(pe_trailing="15.0", pb="2.0", roe="0.18")
        assert isinstance(fund, FundamentalsLike)

    def test_registered_in_catalog(self) -> None:
        assert get_strategy("value_basic") is not None
        assert get_strategy("growth_basic") is not None
        assert get_strategy("dividend_basic") is not None


class TestValueBasicStrategy:
    """Tests for ValueBasicStrategy."""

    def test_value_trigger_long(self) -> None:
        strat = ValueBasicStrategy()
        # PE=16 (< 20), PB=2.5 (< 3.0), ROE=0.20 (>= 15%), Debt/Equity=0.6 (<= 1.0)
        fund = _make_fundamentals(
            pe_trailing="16.0",
            pb="2.5",
            roe="0.20",
            debt_to_equity="0.60",
        )
        bar = _make_bar("100.0")
        ctx = StrategyContext(
            symbol="AAPL",
            as_of=date(2026, 1, 1),
            bars=[bar],
            fundamentals=fund,
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "long"
        assert sig.strength == 85
        assert len(sig.reasons) == 4
        assert sig.levels["entry"] == Decimal("100.0")
        assert sig.levels["stop"] == Decimal("85.0")
        assert sig.levels["target"] == Decimal("125.0")

    def test_value_fallback_to_pe_forward(self) -> None:
        strat = ValueBasicStrategy()
        fund = _make_fundamentals(
            pe_trailing=None,
            pe_forward="14.5",
            pb="2.1",
            roe="0.19",
            debt_to_equity="0.5",
        )
        ctx = StrategyContext(
            symbol="AAPL",
            as_of=date(2026, 1, 1),
            bars=[],
            fundamentals=fund,
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "long"
        assert sig.metrics["pe"] == Decimal("14.5")

    def test_value_rejection_overvalued_pe(self) -> None:
        strat = ValueBasicStrategy()
        fund = _make_fundamentals(
            pe_trailing="32.0",  # > 20
            pb="2.5",
            roe="0.22",
            debt_to_equity="0.4",
        )
        ctx = StrategyContext(
            symbol="AAPL",
            as_of=date(2026, 1, 1),
            bars=[],
            fundamentals=fund,
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "flat"
        assert any("PE 32.0 not in (0, 20.0]" in r for r in sig.reasons)

    def test_value_missing_fundamentals(self) -> None:
        strat = ValueBasicStrategy()
        ctx = StrategyContext(
            symbol="AAPL",
            as_of=date(2026, 1, 1),
            bars=[],
            fundamentals=None,
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "flat"
        assert "missing_fundamentals" in sig.reasons[0]

    def test_value_missing_required_fields(self) -> None:
        strat = ValueBasicStrategy()
        fund = _make_fundamentals(
            pe_trailing=None,
            pe_forward=None,  # Missing PE
            pb="2.0",
            roe=None,  # Missing ROE
            debt_to_equity="0.5",
        )
        ctx = StrategyContext(
            symbol="AAPL",
            as_of=date(2026, 1, 1),
            bars=[],
            fundamentals=fund,
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "flat"
        assert "insufficient_data: missing required fields" in sig.reasons[0]
        assert "pe" in sig.reasons[0]
        assert "roe" in sig.reasons[0]


class TestGrowthBasicStrategy:
    """Tests for GrowthBasicStrategy."""

    def test_growth_trigger_long(self) -> None:
        strat = GrowthBasicStrategy()
        # Net Margin=0.22 (>= 15%), ROE=0.25 (>= 18%),
        # Forward PE=28 (<= 35), Debt/Equity=0.8 (<= 1.5)
        fund = _make_fundamentals(
            net_margin="0.22",
            roe="0.25",
            pe_forward="28.0",
            debt_to_equity="0.8",
        )
        bar = _make_bar("200.0")
        ctx = StrategyContext(
            symbol="NVDA",
            as_of=date(2026, 1, 1),
            bars=[bar],
            fundamentals=fund,
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "long"
        assert sig.strength == 80
        assert sig.levels["entry"] == Decimal("200.0")

    def test_growth_rejection_low_net_margin(self) -> None:
        strat = GrowthBasicStrategy()
        fund = _make_fundamentals(
            net_margin="0.08",  # 8% < 15%
            roe="0.20",
            pe_forward="22.0",
            debt_to_equity="0.5",
        )
        ctx = StrategyContext(
            symbol="NVDA",
            as_of=date(2026, 1, 1),
            bars=[],
            fundamentals=fund,
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "flat"
        assert any("Net Margin 8.0% < 15.0%" in r for r in sig.reasons)

    def test_growth_missing_fields(self) -> None:
        strat = GrowthBasicStrategy()
        fund = _make_fundamentals(
            net_margin="0.20",
            roe=None,
            pe_forward=None,
            debt_to_equity="0.8",
        )
        ctx = StrategyContext(
            symbol="NVDA",
            as_of=date(2026, 1, 1),
            bars=[],
            fundamentals=fund,
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "flat"
        assert "insufficient_data" in sig.reasons[0]


class TestDividendBasicStrategy:
    """Tests for DividendBasicStrategy."""

    def test_dividend_trigger_long(self) -> None:
        strat = DividendBasicStrategy()
        # Dividend Yield=0.042 (4.2% >= 3%), ROE=0.14 (14% >= 10%),
        # PE=18 (<= 25), Debt/Equity=0.7 (<= 1.2)
        fund = _make_fundamentals(
            dividend_yield="0.042",
            roe="0.14",
            pe_trailing="18.0",
            debt_to_equity="0.7",
        )
        bar = _make_bar("50.0")
        ctx = StrategyContext(
            symbol="KO",
            as_of=date(2026, 1, 1),
            bars=[bar],
            fundamentals=fund,
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "long"
        assert sig.strength == 80
        assert sig.levels["entry"] == Decimal("50.0")

    def test_dividend_rejection_low_yield(self) -> None:
        strat = DividendBasicStrategy()
        fund = _make_fundamentals(
            dividend_yield="0.015",  # 1.5% < 3%
            roe="0.15",
            pe_trailing="18.0",
            debt_to_equity="0.7",
        )
        ctx = StrategyContext(
            symbol="KO",
            as_of=date(2026, 1, 1),
            bars=[],
            fundamentals=fund,
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "flat"
        assert any("Dividend Yield 1.50% < 3.00%" in r for r in sig.reasons)

    def test_dividend_missing_fundamentals(self) -> None:
        strat = DividendBasicStrategy()
        ctx = StrategyContext(
            symbol="KO",
            as_of=date(2026, 1, 1),
            bars=[],
            fundamentals=None,
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "flat"
        assert "missing_fundamentals" in sig.reasons[0]
