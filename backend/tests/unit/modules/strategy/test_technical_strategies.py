"""Unit tests for strategy registry and technical strategies (M3 / T03).

Verifies:
- Registry catalog operations, decorators, and error handling.
- >=2 trigger/no-trigger scenarios for Turtle, Dow, Pullback RSI, and 123 Reversal.
- Strict Lookahead Bias defense: adding future data leaves signal 100% identical.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pytest

from app.modules.marketdata.models import Bar as MarketBar
from app.modules.strategy.registry import (
    StrategyRegistryImpl,
    get_strategy,
    list_strategies,
    register_strategy,
)
from app.modules.strategy.schemas import StrategyContext
from app.modules.strategy.strategies.dow import DowTrendStrategy
from app.modules.strategy.strategies.pullback_rsi import PullbackRsiStrategy
from app.modules.strategy.strategies.reversal_123 import Reversal123Strategy
from app.modules.strategy.strategies.turtle import TurtleStrategy


def _make_bar(
    trade_date: date,
    open_: str,
    high: str,
    low: str,
    close: str,
    volume: int = 1000,
    symbol: str = "AAPL",
) -> MarketBar:
    return MarketBar(
        symbol=symbol,
        trade_date=trade_date,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
    )


def _make_bars_from_closes(
    closes: Sequence[str | int | float],
    start_date: date = date(2026, 1, 1),
    symbol: str = "AAPL",
) -> list[MarketBar]:
    bars: list[MarketBar] = []
    for i, c in enumerate(closes):
        c_dec = Decimal(str(c))
        bars.append(
            MarketBar(
                symbol=symbol,
                trade_date=date.fromordinal(start_date.toordinal() + i),
                open=c_dec,
                high=c_dec + Decimal("1.0"),
                low=c_dec - Decimal("1.0"),
                close=c_dec,
                volume=1000 + i * 10,
            )
        )
    return bars


class TestStrategyRegistry:
    """Tests for StrategyRegistry and @register_strategy decorator."""

    def test_registry_registration_and_lookup(self) -> None:
        reg = StrategyRegistryImpl()
        turtle = TurtleStrategy()
        reg.register(turtle)

        assert reg.get("turtle_20_55") is turtle
        assert reg.get("non_existent") is None
        assert len(reg.list_all()) == 1

        reg.clear()
        assert len(reg.list_all()) == 0

    def test_register_decorator_with_class(self) -> None:
        custom_reg = StrategyRegistryImpl()

        @register_strategy(registry=custom_reg)
        class DummyStrategy:
            id = "dummy_strat"
            display_name = "Dummy"
            category = "trend"
            description = "Test"
            requires = {"bars"}
            default_params = {}

            def evaluate(self, ctx: StrategyContext):  # type: ignore[no-untyped-def]
                pass

        assert custom_reg.get("dummy_strat") is not None

    def test_register_invalid_id(self) -> None:
        reg = StrategyRegistryImpl()

        class InvalidStrategy:
            id = ""

        with pytest.raises(ValueError, match="non-empty 'id'"):
            reg.register(InvalidStrategy())  # type: ignore[arg-type]

    def test_global_helpers(self) -> None:
        # Default registry should have the registered strategies imported
        all_strats = list_strategies()
        assert len(all_strats) >= 4
        assert get_strategy("turtle_20_55") is not None
        assert get_strategy("dow_trend") is not None
        assert get_strategy("pullback_rsi") is not None
        assert get_strategy("reversal_123") is not None


class TestTurtleStrategy:
    """Tests for TurtleStrategy (20/55 day breakout)."""

    def test_turtle_trigger_long_breakout(self) -> None:
        """20 prior bars range 100-110 (high=110), current bar closes at 115 -> Long."""
        strat = TurtleStrategy()
        # 20 bars with close 105, high 110, low 100
        bars = []
        base_date = date(2026, 1, 1)
        for i in range(20):
            bars.append(
                _make_bar(
                    date.fromordinal(base_date.toordinal() + i),
                    "105",
                    "110",
                    "100",
                    "105",
                )
            )
        # Bar 21 (current): close 115 > prior 20-day high (110)
        as_of = date.fromordinal(base_date.toordinal() + 20)
        bars.append(_make_bar(as_of, "110", "116", "109", "115"))

        ctx = StrategyContext(symbol="AAPL", as_of=as_of, bars=bars)
        sig = strat.evaluate(ctx)

        assert sig.direction == "long"
        assert sig.strength == 85
        assert "broke above 20-day high" in sig.reasons[0]
        assert sig.levels["entry"] == Decimal("115")
        assert sig.levels["stop"] < Decimal("115")
        assert sig.levels["target"] > Decimal("115")

    def test_turtle_no_trigger_in_range(self) -> None:
        """Price stays within 20-day range -> Flat."""
        strat = TurtleStrategy()
        bars = []
        base_date = date(2026, 1, 1)
        for i in range(21):
            bars.append(
                _make_bar(
                    date.fromordinal(base_date.toordinal() + i),
                    "105",
                    "110",
                    "100",
                    "105",
                )
            )
        as_of = bars[-1].trade_date
        ctx = StrategyContext(symbol="AAPL", as_of=as_of, bars=bars)
        sig = strat.evaluate(ctx)

        assert sig.direction == "flat"
        assert sig.strength == 0

    def test_turtle_exit_trigger(self) -> None:
        """Close drops below 10-day low -> Flat with exit trigger reason."""
        strat = TurtleStrategy()
        bars = []
        base_date = date(2026, 1, 1)
        for i in range(20):
            bars.append(
                _make_bar(
                    date.fromordinal(base_date.toordinal() + i),
                    "105",
                    "110",
                    "100",
                    "105",
                )
            )
        # Current bar drops below prior 10-day low of 100 -> close 95
        as_of = date.fromordinal(base_date.toordinal() + 20)
        bars.append(_make_bar(as_of, "99", "101", "94", "95"))

        ctx = StrategyContext(symbol="AAPL", as_of=as_of, bars=bars)
        sig = strat.evaluate(ctx)

        assert sig.direction == "flat"
        assert sig.strength == 60
        assert "exit low" in sig.reasons[0]

    def test_turtle_lookahead_bias_protection(self) -> None:
        """Appending future tampered bars must NOT alter the signal for as_of."""
        strat = TurtleStrategy()
        base_date = date(2026, 1, 1)
        bars = []
        for i in range(20):
            bars.append(
                _make_bar(
                    date.fromordinal(base_date.toordinal() + i),
                    "105",
                    "110",
                    "100",
                    "105",
                )
            )
        as_of = date.fromordinal(base_date.toordinal() + 20)
        bars.append(_make_bar(as_of, "110", "116", "109", "115"))

        clean_ctx = StrategyContext(symbol="AAPL", as_of=as_of, bars=list(bars))
        sig_clean = strat.evaluate(clean_ctx)

        # Inject future bars after as_of with extreme values
        future_date = date.fromordinal(as_of.toordinal() + 1)
        bars.append(_make_bar(future_date, "500", "600", "400", "550"))
        tampered_ctx = StrategyContext(symbol="AAPL", as_of=as_of, bars=bars)
        sig_tampered = strat.evaluate(tampered_ctx)

        assert sig_clean.direction == sig_tampered.direction
        assert sig_clean.strength == sig_tampered.strength
        assert sig_clean.levels == sig_tampered.levels
        assert sig_clean.reasons == sig_tampered.reasons


class TestDowTrendStrategy:
    """Tests for DowTrendStrategy."""

    def test_dow_trigger_long_uptrend_breakout(self) -> None:
        """Higher highs and higher lows + current breakout above last high."""
        strat = DowTrendStrategy()
        # window=2 requires 2 bars before and 2 bars after each peak
        # Swing High 1 at index 2 (high=110), Swing Low 1 at index 4 (low=95)
        # Swing High 2 at index 6 (high=120), Swing Low 2 at index 8 (low=105)
        # Current bar at index 11 breaks above Swing High 2 (high=120) with close 125
        highs = [100, 105, 110, 102, 100, 115, 120, 112, 110, 114, 118, 126]
        lows = [90, 94, 98, 92, 90, 104, 108, 103, 102, 106, 110, 120]
        closes = [95, 100, 105, 96, 92, 110, 115, 108, 105, 110, 115, 125]

        base_date = date(2026, 1, 1)
        bars = []
        for i in range(len(highs)):
            bars.append(
                _make_bar(
                    date.fromordinal(base_date.toordinal() + i),
                    open_=str(closes[i]),
                    high=str(highs[i]),
                    low=str(lows[i]),
                    close=str(closes[i]),
                )
            )

        as_of = bars[-1].trade_date
        ctx = StrategyContext(
            symbol="AAPL",
            as_of=as_of,
            bars=bars,
            params={"swing_window": 2},
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "long"
        assert sig.strength == 85
        assert "Dow uptrend" in sig.reasons[0]
        assert sig.levels["entry"] == Decimal("125")

    def test_dow_no_trigger_downtrend(self) -> None:
        """Lower highs and lower lows establish downtrend -> Flat."""
        strat = DowTrendStrategy()
        # Descending swing points with window=2:
        # Swing High 1 at index 2 (150), Swing Low 1 at index 4 (125)
        # Swing High 2 at index 6 (140 < 150), Swing Low 2 at index 8 (115 < 125)
        highs = [140, 145, 150, 142, 135, 138, 140, 132, 125, 128, 126]
        lows = [130, 135, 140, 132, 125, 130, 132, 122, 115, 118, 116]
        closes = [135, 140, 145, 136, 128, 135, 136, 126, 118, 122, 120]

        base_date = date(2026, 1, 1)
        bars = []
        for i in range(len(highs)):
            bars.append(
                _make_bar(
                    date.fromordinal(base_date.toordinal() + i),
                    open_=str(closes[i]),
                    high=str(highs[i]),
                    low=str(lows[i]),
                    close=str(closes[i]),
                )
            )

        as_of = bars[-1].trade_date
        ctx = StrategyContext(
            symbol="AAPL",
            as_of=as_of,
            bars=bars,
            params={"swing_window": 2},
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "flat"
        assert "Dow downtrend" in sig.reasons[0]

    def test_dow_lookahead_bias_protection(self) -> None:
        """Tampering future data must not change as_of evaluation."""
        strat = DowTrendStrategy()
        bars = _make_bars_from_closes([str(100 + i * 2) for i in range(25)])
        as_of = bars[-1].trade_date

        clean_ctx = StrategyContext(symbol="AAPL", as_of=as_of, bars=list(bars))
        sig_clean = strat.evaluate(clean_ctx)

        # Future data
        bars.append(_make_bar(date.fromordinal(as_of.toordinal() + 1), "10", "20", "5", "15"))
        tampered_ctx = StrategyContext(symbol="AAPL", as_of=as_of, bars=bars)
        sig_tampered = strat.evaluate(tampered_ctx)

        assert sig_clean.direction == sig_tampered.direction
        assert sig_clean.reasons == sig_tampered.reasons


class TestPullbackRsiStrategy:
    """Tests for PullbackRsiStrategy."""

    def test_pullback_rsi_trigger_long(self) -> None:
        """In uptrend (> SMA15), RSI dips to oversold and hooks up -> Long."""
        strat = PullbackRsiStrategy()
        closes = [80 + i * 2 for i in range(20)]  # 80 to 118
        closes += [120, 114, 108, 112]  # Pullback then hook up

        bars = _make_bars_from_closes(closes)
        as_of = bars[-1].trade_date

        ctx = StrategyContext(
            symbol="AAPL",
            as_of=as_of,
            bars=bars,
            params={
                "trend_sma_period": 15,
                "rsi_period": 3,
                "rsi_oversold": Decimal("35.0"),
                "pullback_lookback": 2,
            },
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "long"
        assert sig.strength == 80
        assert "Uptrend" in sig.reasons[0]
        assert sig.levels["entry"] == Decimal("112")

    def test_pullback_rsi_trend_filter_rejection(self) -> None:
        """Price below trend SMA -> Rejected as flat."""
        strat = PullbackRsiStrategy()
        # Monotonically falling prices
        closes = [str(150 - i * 2) for i in range(30)]
        bars = _make_bars_from_closes(closes)
        as_of = bars[-1].trade_date

        ctx = StrategyContext(
            symbol="AAPL",
            as_of=as_of,
            bars=bars,
            params={"trend_sma_period": 20},
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "flat"
        assert "Trend filter failed" in sig.reasons[0]

    def test_pullback_rsi_lookahead_bias_protection(self) -> None:
        """Tampered future bars do not alter signal for as_of."""
        strat = PullbackRsiStrategy()
        closes = [str(100 + i) for i in range(30)]
        bars = _make_bars_from_closes(closes)
        as_of = bars[-1].trade_date

        clean_ctx = StrategyContext(
            symbol="AAPL",
            as_of=as_of,
            bars=list(bars),
            params={"trend_sma_period": 20},
        )
        sig_clean = strat.evaluate(clean_ctx)

        bars.append(_make_bar(date.fromordinal(as_of.toordinal() + 1), "10", "15", "5", "8"))
        tampered_ctx = StrategyContext(
            symbol="AAPL",
            as_of=as_of,
            bars=bars,
            params={"trend_sma_period": 20},
        )
        sig_tampered = strat.evaluate(tampered_ctx)

        assert sig_clean.direction == sig_tampered.direction
        assert sig_clean.reasons == sig_tampered.reasons


class TestReversal123Strategy:
    """Tests for Reversal123Strategy."""

    def test_reversal_123_trigger_long(self) -> None:
        """Satisfies 1) > SMA; 2) Higher Low; 3) Breakout above swing high -> Long."""
        strat = Reversal123Strategy()
        # Window=2:
        # Trough 1 at index 3 (low 50), Peak at index 6 (high 70),
        # Trough 2 at index 9 (low 60 > 50 -> Higher Low)
        # Final bar at index 12 breaks out above Peak (70) -> close 75
        highs = [65, 62, 58, 55, 62, 68, 70, 66, 64, 63, 67, 72, 78]
        lows = [60, 56, 52, 50, 54, 60, 62, 58, 57, 60, 62, 66, 72]
        closes = [62, 58, 54, 52, 58, 65, 68, 62, 60, 62, 65, 70, 75]

        base_date = date(2026, 1, 1)
        bars = []
        for i in range(len(highs)):
            bars.append(
                _make_bar(
                    date.fromordinal(base_date.toordinal() + i),
                    open_=str(closes[i]),
                    high=str(highs[i]),
                    low=str(lows[i]),
                    close=str(closes[i]),
                )
            )

        as_of = bars[-1].trade_date
        ctx = StrategyContext(
            symbol="AAPL",
            as_of=as_of,
            bars=bars,
            params={"trend_period": 10, "swing_window": 2},
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "long"
        assert sig.strength == 80
        assert "1-2-3 Reversal confirmed" in sig.reasons[0]
        assert sig.levels["entry"] == Decimal("75")
        assert sig.levels["stop"] == Decimal("57")  # last higher low

    def test_reversal_123_failed_rule_1_below_sma(self) -> None:
        """Close is below trend SMA -> Rule 1 fails -> Flat."""
        strat = Reversal123Strategy()
        bars = _make_bars_from_closes([str(100 - i) for i in range(25)])
        as_of = bars[-1].trade_date
        ctx = StrategyContext(
            symbol="AAPL",
            as_of=as_of,
            bars=bars,
            params={"trend_period": 10},
        )
        sig = strat.evaluate(ctx)

        assert sig.direction == "flat"
        assert "Rule 1 failed" in sig.reasons[0]

    def test_reversal_123_lookahead_bias_protection(self) -> None:
        """Tampering future bars leaves as_of evaluation unchanged."""
        strat = Reversal123Strategy()
        bars = _make_bars_from_closes([str(50 + i * 2) for i in range(25)])
        as_of = bars[-1].trade_date

        clean_ctx = StrategyContext(
            symbol="AAPL",
            as_of=as_of,
            bars=list(bars),
            params={"trend_period": 10, "swing_window": 2},
        )
        sig_clean = strat.evaluate(clean_ctx)

        # Append future data
        bars.append(_make_bar(date.fromordinal(as_of.toordinal() + 1), "10", "20", "5", "10"))
        tampered_ctx = StrategyContext(
            symbol="AAPL",
            as_of=as_of,
            bars=bars,
            params={"trend_period": 10, "swing_window": 2},
        )
        sig_tampered = strat.evaluate(tampered_ctx)

        assert sig_clean.direction == sig_tampered.direction
        assert sig_clean.reasons == sig_tampered.reasons
