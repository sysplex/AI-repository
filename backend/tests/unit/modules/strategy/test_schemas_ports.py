"""Unit tests for Strategy domain models, DTO schemas, and ports (M3 / T01)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.strategy.ports import Strategy, StrategyRegistry
from app.modules.strategy.schemas import (
    BacktestRequest,
    BacktestResult,
    EquityPoint,
    Signal,
    StrategyContext,
    StrategyMetadata,
    TechnicalSnapshot,
    TradeRecord,
)

pytestmark = pytest.mark.unit


def test_signal_schema_validation_and_immutability() -> None:
    """Verify Signal model serialization, validation constraints, and frozen behavior."""
    sig = Signal(
        strategy_id="turtle_20",
        symbol="AAPL",
        as_of=date(2026, 11, 10),
        direction="long",
        strength=85,
        reasons=["20-day high breakout", "Volume confirmation"],
        levels={"entry": Decimal("225.00"), "stop": Decimal("218.50"), "target": Decimal("238.00")},
        metrics={"donchian_high": Decimal("224.50"), "atr": Decimal("3.25")},
    )

    assert sig.strategy_id == "turtle_20"
    assert sig.symbol == "AAPL"
    assert sig.as_of == date(2026, 11, 10)
    assert sig.direction == "long"
    assert sig.strength == 85
    assert len(sig.reasons) == 2
    assert sig.levels["stop"] == Decimal("218.50")
    assert isinstance(sig.levels["stop"], Decimal)

    # Immutability verification
    with pytest.raises(ValidationError):
        sig.strength = 90  # type: ignore[misc]

    # Strength range validation
    with pytest.raises(ValidationError):
        Signal(
            strategy_id="test",
            symbol="AAPL",
            as_of=date(2026, 11, 10),
            direction="long",
            strength=150,  # exceeds 100
        )
    with pytest.raises(ValidationError):
        Signal(
            strategy_id="test",
            symbol="AAPL",
            as_of=date(2026, 11, 10),
            direction="long",
            strength=-5,  # negative
        )


def test_technical_snapshot_schema() -> None:
    """Verify TechnicalSnapshot model construction and nullable field semantics."""
    snap = TechnicalSnapshot(
        symbol="MSFT",
        as_of=date(2026, 11, 10),
        sma_20=Decimal("410.50"),
        sma_50=Decimal("405.20"),
        sma_200=Decimal("390.10"),
        rsi_14=Decimal("62.5"),
        macd=Decimal("3.80"),
        macd_signal=Decimal("2.90"),
        macd_hist=Decimal("0.90"),
        atr_14=Decimal("5.40"),
        bb_upper=Decimal("420.00"),
        bb_middle=Decimal("410.50"),
        bb_lower=Decimal("401.00"),
        obv=154000000,
        support=Decimal("400.00"),
        resistance=Decimal("425.00"),
    )

    assert snap.symbol == "MSFT"
    assert snap.rsi_14 == Decimal("62.5")
    assert snap.obv == 154000000

    # Minimal snapshot with defaults
    empty_snap = TechnicalSnapshot(symbol="NVDA", as_of=date(2026, 11, 10))
    assert empty_snap.sma_20 is None
    assert empty_snap.rsi_14 is None


def test_strategy_context_schema() -> None:
    """Verify StrategyContext container holds bars and parameters."""
    ctx = StrategyContext(
        symbol="AAPL",
        as_of=date(2026, 11, 10),
        bars=[{"trade_date": "2026-11-10", "close": "224.23"}],
        fundamentals={"pe_trailing": "34.2"},
        params={"donchian_period": 20},
    )

    assert ctx.symbol == "AAPL"
    assert len(ctx.bars) == 1
    assert ctx.params["donchian_period"] == 20

    with pytest.raises(ValidationError):
        ctx.symbol = "MSFT"  # type: ignore[misc]


def test_strategy_metadata_schema() -> None:
    """Verify StrategyMetadata catalog schema."""
    meta = StrategyMetadata(
        id="pullback_rsi",
        display_name="RSI Pullback Trend Following",
        category="pullback",
        description="Buys on RSI oversold pullbacks within a confirmed multi-period bull trend.",
        requires=["bars"],
        default_params={"rsi_period": 14, "rsi_threshold": 40},
    )

    assert meta.id == "pullback_rsi"
    assert meta.category == "pullback"
    assert meta.default_params["rsi_period"] == 14

    # Invalid category
    with pytest.raises(ValidationError):
        StrategyMetadata(
            id="bad",
            display_name="Bad",
            category="invalid_category",
            description="desc",
        )


def test_backtest_models() -> None:
    """Verify BacktestRequest, TradeRecord, EquityPoint, and BacktestResult models."""
    req = BacktestRequest(
        strategy_id="turtle_20",
        symbol="AAPL",
        start=date(2024, 1, 1),
        end=date(2024, 12, 31),
        initial_capital=Decimal("50000.00"),
        params={"atr_mult": 2.0},
    )
    assert req.initial_capital == Decimal("50000.00")

    trade = TradeRecord(
        trade_date=date(2024, 6, 15),
        action="buy",
        price=Decimal("180.50"),
        shares=100,
        amount=Decimal("18050.00"),
        pnl=Decimal("1500.00"),
        pnl_pct=Decimal("0.083"),
        reason="Turtle breakout",
    )
    assert trade.action == "buy"
    assert trade.pnl == Decimal("1500.00")

    point = EquityPoint(
        trade_date=date(2024, 6, 15),
        equity=Decimal("51500.00"),
        cash=Decimal("33450.00"),
        drawdown_pct=Decimal("0.021"),
    )
    assert point.equity == Decimal("51500.00")

    res = BacktestResult(
        strategy_id="turtle_20",
        symbol="AAPL",
        start=date(2024, 1, 1),
        end=date(2024, 12, 31),
        initial_capital=Decimal("50000.00"),
        final_equity=Decimal("62500.00"),
        total_return_pct=Decimal("0.25"),
        annualized_return_pct=Decimal("0.25"),
        max_drawdown_pct=Decimal("0.085"),
        win_rate=Decimal("0.60"),
        profit_factor=Decimal("2.10"),
        total_trades=15,
        trades=[trade],
        equity_curve=[point],
    )
    assert res.final_equity == Decimal("62500.00")
    assert res.total_trades == 15
    assert len(res.trades) == 1
    assert len(res.equity_curve) == 1


def test_strategy_and_registry_protocols() -> None:
    """Verify Strategy and StrategyRegistry protocols satisfy runtime checks."""

    class MockStrategy:
        id = "mock_strat"
        display_name = "Mock Strategy"
        category = "trend"
        description = "A mock strategy for testing"
        requires = {"bars"}
        default_params: dict[str, Any] = {"period": 20}

        def evaluate(self, ctx: StrategyContext) -> Signal:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
            )

    strat = MockStrategy()
    assert isinstance(strat, Strategy)

    class MockRegistry:
        def __init__(self) -> None:
            self._strats: dict[str, Strategy] = {}

        def register(self, s: Strategy) -> None:
            self._strats[s.id] = s

        def get(self, strategy_id: str) -> Strategy | None:
            return self._strats.get(strategy_id)

        def list_all(self) -> Sequence[Strategy]:
            return list(self._strats.values())

    registry = MockRegistry()
    assert isinstance(registry, StrategyRegistry)
    registry.register(strat)
    assert registry.get("mock_strat") is strat
    assert len(registry.list_all()) == 1
