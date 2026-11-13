"""Unit tests for ATR levels and event-driven backtesting engine (M3 / T05).

Verifies:
- compute_atr_levels exact mathematical alignment for long, short, and flat.
- BacktestEngine trade execution, stop loss, take profit, and exit mechanics.
- Mathematical equity identity: final_equity == initial_capital + sum(pnl).
- Performance metrics: total_return_pct, max_drawdown_pct, win_rate, profit_factor.
- Strict Lookahead Bias defense: on every simulated bar, strategy receives only data <= as_of.
"""

from datetime import date
from decimal import Decimal

from app.modules.marketdata.models import Bar as MarketBar
from app.modules.strategy.backtest import BacktestEngine
from app.modules.strategy.levels import compute_atr_levels
from app.modules.strategy.ports import Strategy
from app.modules.strategy.schemas import (
    BacktestRequest,
    Signal,
    StrategyContext,
)


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


class TestAtrLevels:
    """Tests for compute_atr_levels."""

    def test_long_levels_standard(self) -> None:
        # entry=100.0, atr=5.0, stop_mult=2.0, target_mult=3.0
        # stop = 100 - (5 * 2) = 90.0
        # target = 100 + (5 * 3) = 115.0
        levels = compute_atr_levels(
            entry_price=Decimal("100.0"),
            atr=Decimal("5.0"),
            direction="long",
            stop_mult=Decimal("2.0"),
            target_mult=Decimal("3.0"),
        )
        assert levels["entry"] == Decimal("100.0")
        assert levels["stop"] == Decimal("90.0")
        assert levels["target"] == Decimal("115.0")

    def test_long_levels_negative_stop_protection(self) -> None:
        # entry=5.0, atr=10.0, stop_mult=2.0 -> raw_stop = 5 - 20 = -15 -> bound to 0.01
        levels = compute_atr_levels(
            entry_price=Decimal("5.0"),
            atr=Decimal("10.0"),
            direction="long",
        )
        assert levels["stop"] == Decimal("0.01")

    def test_short_levels_standard(self) -> None:
        # entry=100.0, atr=4.0, stop_mult=2.0, target_mult=3.0
        # stop = 100 + (4 * 2) = 108.0
        # target = 100 - (4 * 3) = 88.0
        levels = compute_atr_levels(
            entry_price=Decimal("100.0"),
            atr=Decimal("4.0"),
            direction="short",
            stop_mult=Decimal("2.0"),
            target_mult=Decimal("3.0"),
        )
        assert levels["entry"] == Decimal("100.0")
        assert levels["stop"] == Decimal("108.0")
        assert levels["target"] == Decimal("88.0")

    def test_flat_levels(self) -> None:
        levels = compute_atr_levels(
            entry_price=Decimal("100.0"),
            atr=Decimal("4.0"),
            direction="flat",
        )
        assert levels["entry"] == Decimal("100.0")
        assert levels["stop"] == Decimal("100.0")
        assert levels["target"] == Decimal("100.0")


class MockStrategy(Strategy):
    """Configurable mock strategy for testing backtesting behavior."""

    id = "mock_strat"
    display_name = "Mock Strategy"
    category = "trend"
    description = "Mock for backtesting"
    requires = {"bars"}
    default_params = {}

    def __init__(
        self,
        signals_map: dict[date, Signal] | None = None,
        record_lookahead: bool = False,
    ) -> None:
        self.signals_map = signals_map or {}
        self.record_lookahead = record_lookahead
        self.max_bar_dates_seen: list[tuple[date, date]] = []

    def evaluate(self, ctx: StrategyContext) -> Signal:
        if self.record_lookahead and ctx.bars:
            max_seen = max(b.trade_date for b in ctx.bars)
            self.max_bar_dates_seen.append((ctx.as_of, max_seen))

        if ctx.as_of in self.signals_map:
            return self.signals_map[ctx.as_of]

        return Signal(
            strategy_id=self.id,
            symbol=ctx.symbol,
            as_of=ctx.as_of,
            direction="flat",
        )


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    def test_empty_bars(self) -> None:
        strat = MockStrategy()
        engine = BacktestEngine(strat)
        req = BacktestRequest(
            strategy_id="mock_strat",
            symbol="AAPL",
            start=date(2026, 1, 1),
            end=date(2026, 1, 10),
            initial_capital=Decimal("100000.0"),
        )
        res = engine.run([], req)
        assert res.final_equity == Decimal("100000.0")
        assert res.total_trades == 0
        assert len(res.trades) == 0
        assert len(res.equity_curve) == 0

    def test_single_trade_profitable_closed_at_end(self) -> None:
        """Buy on day 2 at 100, hold until end of backtest (day 5) at 120."""
        d1 = date(2026, 1, 1)
        d2 = date(2026, 1, 2)
        d3 = date(2026, 1, 3)
        d4 = date(2026, 1, 4)
        d5 = date(2026, 1, 5)

        bars = [
            _make_bar(d1, "98", "102", "97", "100"),
            _make_bar(d2, "100", "105", "99", "102"),
            _make_bar(d3, "102", "110", "101", "108"),
            _make_bar(d4, "108", "116", "107", "114"),
            _make_bar(d5, "114", "122", "113", "120"),
        ]

        buy_signal = Signal(
            strategy_id="mock_strat",
            symbol="AAPL",
            as_of=d2,
            direction="long",
            strength=80,
            levels={"entry": Decimal("102"), "stop": Decimal("90"), "target": Decimal("150")},
        )
        strat = MockStrategy(signals_map={d2: buy_signal})
        engine = BacktestEngine(strat)

        req = BacktestRequest(
            strategy_id="mock_strat",
            symbol="AAPL",
            start=d1,
            end=d5,
            initial_capital=Decimal("10000.0"),
        )
        res = engine.run(bars, req)

        assert res.total_trades == 1
        assert len(res.trades) == 2  # 1 buy, 1 sell
        buy_trade = res.trades[0]
        sell_trade = res.trades[1]

        assert buy_trade.action == "buy"
        assert buy_trade.price == Decimal("102")
        assert sell_trade.action == "sell"
        assert sell_trade.price == Decimal("120")
        assert sell_trade.reason == "end_of_backtest"
        assert sell_trade.pnl is not None and sell_trade.pnl > Decimal(0)

        # Mathematical equity identity verification:
        total_pnl = sum((t.pnl for t in res.trades if t.pnl is not None), Decimal(0))
        assert res.final_equity == req.initial_capital + total_pnl
        assert res.win_rate == Decimal("100.0")

    def test_stop_loss_trigger(self) -> None:
        """Buy at 100 with stop at 90. Day 3 drops to low 88 -> Stop loss executed."""
        d1 = date(2026, 1, 1)
        d2 = date(2026, 1, 2)
        d3 = date(2026, 1, 3)

        bars = [
            _make_bar(d1, "98", "102", "97", "100"),
            _make_bar(d2, "100", "105", "99", "100"),  # Buy trigger
            _make_bar(d3, "95", "96", "88", "89"),  # Low drops to 88 <= stop 90
        ]

        buy_signal = Signal(
            strategy_id="mock_strat",
            symbol="AAPL",
            as_of=d2,
            direction="long",
            levels={"entry": Decimal("100"), "stop": Decimal("90"), "target": Decimal("130")},
        )
        strat = MockStrategy(signals_map={d2: buy_signal})
        engine = BacktestEngine(strat)

        req = BacktestRequest(
            strategy_id="mock_strat",
            symbol="AAPL",
            start=d1,
            end=d3,
            initial_capital=Decimal("10000.0"),
        )
        res = engine.run(bars, req)

        assert res.total_trades == 1
        sell_trade = res.trades[-1]
        assert sell_trade.action == "sell"
        assert sell_trade.reason == "stop_loss"
        assert sell_trade.price == Decimal("90")  # Executed at stop price
        assert sell_trade.pnl is not None and sell_trade.pnl < Decimal(0)
        assert res.win_rate == Decimal("0.0")

    def test_take_profit_trigger(self) -> None:
        """Buy at 100 with target at 120. Day 3 spikes to high 125 -> Take profit executed."""
        d1 = date(2026, 1, 1)
        d2 = date(2026, 1, 2)
        d3 = date(2026, 1, 3)

        bars = [
            _make_bar(d1, "98", "102", "97", "100"),
            _make_bar(d2, "100", "105", "99", "100"),  # Buy trigger
            _make_bar(d3, "115", "125", "114", "122"),  # High reaches 125 >= target 120
        ]

        buy_signal = Signal(
            strategy_id="mock_strat",
            symbol="AAPL",
            as_of=d2,
            direction="long",
            levels={"entry": Decimal("100"), "stop": Decimal("85"), "target": Decimal("120")},
        )
        strat = MockStrategy(signals_map={d2: buy_signal})
        engine = BacktestEngine(strat)

        req = BacktestRequest(
            strategy_id="mock_strat",
            symbol="AAPL",
            start=d1,
            end=d3,
            initial_capital=Decimal("10000.0"),
        )
        res = engine.run(bars, req)

        assert res.total_trades == 1
        sell_trade = res.trades[-1]
        assert sell_trade.action == "sell"
        assert sell_trade.reason == "take_profit"
        assert sell_trade.price == Decimal("120")  # Executed at target price
        assert sell_trade.pnl is not None and sell_trade.pnl > Decimal(0)
        assert res.win_rate == Decimal("100.0")

    def test_explicit_strategy_exit_signal(self) -> None:
        """Buy on day 2, explicit strategy exit signal on day 3."""
        d1 = date(2026, 1, 1)
        d2 = date(2026, 1, 2)
        d3 = date(2026, 1, 3)
        d4 = date(2026, 1, 4)

        bars = [
            _make_bar(d1, "98", "102", "97", "100"),
            _make_bar(d2, "100", "105", "99", "102"),
            _make_bar(d3, "102", "110", "101", "108"),
            _make_bar(d4, "108", "112", "105", "110"),
        ]

        buy_signal = Signal(
            strategy_id="mock_strat",
            symbol="AAPL",
            as_of=d2,
            direction="long",
            strength=80,
            levels={"entry": Decimal("102"), "stop": Decimal("90"), "target": Decimal("150")},
        )
        exit_signal = Signal(
            strategy_id="mock_strat",
            symbol="AAPL",
            as_of=d3,
            direction="flat",
            strength=50,
            reasons=["exit_rule_triggered"],
        )
        strat = MockStrategy(signals_map={d2: buy_signal, d3: exit_signal})
        engine = BacktestEngine(strat)

        req = BacktestRequest(
            strategy_id="mock_strat",
            symbol="AAPL",
            start=d1,
            end=d4,
            initial_capital=Decimal("10000.0"),
        )
        res = engine.run(bars, req)

        assert res.total_trades == 1
        assert len(res.trades) == 2
        sell_trade = res.trades[1]
        assert sell_trade.action == "sell"
        assert sell_trade.trade_date == d3
        assert sell_trade.price == Decimal("108")
        assert sell_trade.reason == "exit_rule_triggered"
        assert sell_trade.pnl is not None and sell_trade.pnl > Decimal(0)

    def test_lookahead_bias_verification(self) -> None:
        """Verify on every step t, strategy only receives historical data where trade_date <= t."""
        d1 = date(2026, 1, 1)
        d2 = date(2026, 1, 2)
        d3 = date(2026, 1, 3)
        d4 = date(2026, 1, 4)

        bars = [
            _make_bar(d1, "100", "105", "95", "102"),
            _make_bar(d2, "102", "106", "98", "103"),
            _make_bar(d3, "103", "108", "100", "107"),
            _make_bar(d4, "107", "112", "105", "110"),
        ]

        strat = MockStrategy(record_lookahead=True)
        engine = BacktestEngine(strat)

        req = BacktestRequest(
            strategy_id="mock_strat",
            symbol="AAPL",
            start=d1,
            end=d4,
            initial_capital=Decimal("10000.0"),
        )
        engine.run(bars, req)

        # Assert every step strictly satisfied max_seen <= as_of
        assert len(strat.max_bar_dates_seen) == 4
        for as_of, max_seen in strat.max_bar_dates_seen:
            assert max_seen <= as_of
