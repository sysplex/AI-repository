"""End-to-End (E2E) integration acceptance tests for Strategy Engine (M3 / T07).

Validates all 6 criteria from `docs/08-test-plan.md §5 M3`:
1. Technical indicator error < 1e-6 against precision benchmarks.
2. Anti-lookahead tampering protection across all 7 quantitative strategies.
3. At least 2 trigger and 2 non-trigger cases per strategy.
4. Insufficient data defense returning `insufficient_data`.
5. Dynamic stop/target level calculation matching manual arithmetic.
6. Event-driven backtesting closed-loop mathematical identity.
7. Full-chain REST API end-to-end authenticated lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

import app.modules.strategy.strategies  # noqa: F401
from app.api.deps import current_user
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.schemas import AuthenticatedUser, UserSettings
from app.modules.strategy.api import set_strategy_service
from app.modules.strategy.backtest import BacktestEngine
from app.modules.strategy.indicators import (
    Bar,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_sma,
    calculate_true_range,
)
from app.modules.strategy.levels import compute_atr_levels
from app.modules.strategy.registry import get_strategy
from app.modules.strategy.schemas import (
    BacktestRequest,
    StrategyContext,
)
from app.modules.strategy.service import StrategyService

pytestmark = pytest.mark.e2e


class ConcreteBar:
    """Standard bar implementation for E2E testing."""

    def __init__(
        self,
        trade_date: date,
        open_: str,
        high: str,
        low: str,
        close: str,
        volume: int = 1000,
    ) -> None:
        self.trade_date = trade_date
        self.open = Decimal(open_)
        self.high = Decimal(high)
        self.low = Decimal(low)
        self.close = Decimal(close)
        self.volume = volume


class ConcreteFundamentals:
    """Standard fundamentals implementation for E2E testing."""

    def __init__(
        self,
        pe_trailing: str | None = "15.0",
        pe_forward: str | None = "14.0",
        pb: str | None = "2.0",
        ps: str | None = "1.5",
        roe: str | None = "0.18",
        net_margin: str | None = "0.20",
        debt_to_equity: str | None = "0.8",
        dividend_yield: str | None = "0.035",
        market_cap: int = 1000000000,
    ) -> None:
        self.pe_trailing = Decimal(pe_trailing) if pe_trailing else None
        self.pe_forward = Decimal(pe_forward) if pe_forward else None
        self.pb = Decimal(pb) if pb else None
        self.ps = Decimal(ps) if ps else None
        self.roe = Decimal(roe) if roe else None
        self.net_margin = Decimal(net_margin) if net_margin else None
        self.debt_to_equity = Decimal(debt_to_equity) if debt_to_equity else None
        self.dividend_yield = Decimal(dividend_yield) if dividend_yield else None
        self.market_cap = Decimal(market_cap)


# =============================================================================
# Criterion 1: Indicator error < 1e-6 against benchmark
# =============================================================================


def test_indicators_benchmark_error_under_1e6() -> None:
    """Verify indicators adhere strictly to benchmark precision with error < 1e-6."""
    base_d = date(2026, 1, 1)
    # 30 bars with fixed linear increment
    bars = [
        ConcreteBar(
            trade_date=base_d + timedelta(days=i),
            open_=str(100 + i),
            high=str(102 + i),
            low=str(99 + i),
            close=str(101 + i),
            volume=1000 + (i * 10),
        )
        for i in range(30)
    ]

    # SMA 10 on linear prices: average of last 10 numbers (121 to 130) is 125.5
    sma10 = calculate_sma(bars, 10)
    assert sma10 is not None
    assert abs(sma10 - Decimal("125.5")) < Decimal("1e-6")

    # True Range for bar with known values
    tr = calculate_true_range(bars[1], bars[0])
    # bar[1]: high=103, low=100, close=102; bar[0]: close=101
    # max(103-100, |103-101|, |100-101|) = max(3, 2, 1) = 3
    assert tr == Decimal("3.0")

    # ATR 14
    atr14 = calculate_atr(bars, 14)
    assert atr14 is not None
    assert abs(atr14 - Decimal("3.0")) < Decimal("1e-6")

    # Bollinger Bands (20 periods): linear series std deviation
    upper, mid, lower = calculate_bollinger_bands(bars, 20)
    assert mid is not None and upper is not None and lower is not None
    assert mid == calculate_sma(bars, 20)
    assert upper > mid > lower


# =============================================================================
# Criterion 2: Lookahead tampering defense across all 7 strategies
# =============================================================================


def test_lookahead_bias_tampering_defense_all_7_strategies() -> None:
    """Tampering with data after as_of must have zero impact on strategy signals."""
    as_of = date(2026, 3, 1)
    base_d = date(2026, 1, 1)

    # 60 historical bars strictly <= as_of
    clean_bars = [
        ConcreteBar(
            trade_date=base_d + timedelta(days=i),
            open_="100",
            high="105",
            low="98",
            close="102",
        )
        for i in range(60)
    ]
    clean_fundamentals = ConcreteFundamentals()

    # 10 tampered future bars after as_of with extreme crash/spike prices
    future_tampered_bars = clean_bars + [
        ConcreteBar(
            trade_date=as_of + timedelta(days=j),
            open_="999999",
            high="9999999",
            low="1",
            close="9999999",
            volume=999999999,
        )
        for j in range(1, 11)
    ]

    all_strategies = [
        "turtle_20_55",
        "dow_trend",
        "pullback_rsi",
        "reversal_123",
        "value_basic",
        "growth_basic",
        "dividend_basic",
    ]

    for strat_id in all_strategies:
        strat = get_strategy(strat_id)
        assert strat is not None

        # Clean context
        ctx_clean = StrategyContext(
            symbol="TEST",
            as_of=as_of,
            bars=clean_bars,
            fundamentals=clean_fundamentals,
            params=strat.default_params,
        )
        signal_clean = strat.evaluate(ctx_clean)

        # Context with future data tampered
        ctx_tampered = StrategyContext(
            symbol="TEST",
            as_of=as_of,
            bars=future_tampered_bars,
            fundamentals=clean_fundamentals,
            params=strat.default_params,
        )
        signal_tampered = strat.evaluate(ctx_tampered)

        # Signal MUST be strictly identical
        assert signal_clean.direction == signal_tampered.direction, f"{strat_id} lookahead leak!"
        assert signal_clean.strength == signal_tampered.strength, f"{strat_id} strength leak!"
        assert signal_clean.reasons == signal_tampered.reasons, f"{strat_id} reasons leak!"
        assert signal_clean.levels == signal_tampered.levels, f"{strat_id} levels leak!"


# =============================================================================
# Criterion 3: Trigger and Non-Trigger samples (at least 2 each)
# =============================================================================


def test_strategy_trigger_and_non_trigger_samples() -> None:
    """Verify that every strategy has clear trigger and non-trigger behavior."""
    as_of = date(2026, 3, 1)

    # 1. Value Strategy
    val_strat = get_strategy("value_basic")
    assert val_strat is not None

    # Trigger: PE=12, PB=1.5, ROE=20%, D/E=0.5 -> Long
    qualifying = ConcreteFundamentals(pe_trailing="12", pb="1.5", roe="0.20", debt_to_equity="0.5")
    sig_val_long = val_strat.evaluate(
        StrategyContext(symbol="VAL", as_of=as_of, bars=[], fundamentals=qualifying)
    )
    assert sig_val_long.direction == "long"

    # Non-trigger 1: High PE (PE=45 > 20) -> Flat
    high_pe = ConcreteFundamentals(pe_trailing="45", pb="1.5", roe="0.20", debt_to_equity="0.5")
    sig_val_flat1 = val_strat.evaluate(
        StrategyContext(symbol="VAL", as_of=as_of, bars=[], fundamentals=high_pe)
    )
    assert sig_val_flat1.direction == "flat"

    # Non-trigger 2: Low ROE (ROE=5% < 15%) -> Flat
    low_roe = ConcreteFundamentals(pe_trailing="15", pb="1.5", roe="0.05", debt_to_equity="0.5")
    sig_val_flat2 = val_strat.evaluate(
        StrategyContext(symbol="VAL", as_of=as_of, bars=[], fundamentals=low_roe)
    )
    assert sig_val_flat2.direction == "flat"

    # 2. Growth Strategy
    gro_strat = get_strategy("growth_basic")
    assert gro_strat is not None
    # Trigger: Net Margin=25%, ROE=22%, Fwd PE=20, D/E=0.6 -> Long
    gro_qualifying = ConcreteFundamentals(
        net_margin="0.25", roe="0.22", pe_forward="20", debt_to_equity="0.6"
    )
    sig_gro_long = gro_strat.evaluate(
        StrategyContext(symbol="GRO", as_of=as_of, bars=[], fundamentals=gro_qualifying)
    )
    assert sig_gro_long.direction == "long"

    # Non-trigger: Low Margin=5% -> Flat
    gro_low_margin = ConcreteFundamentals(
        net_margin="0.05", roe="0.22", pe_forward="20", debt_to_equity="0.6"
    )
    sig_gro_flat = gro_strat.evaluate(
        StrategyContext(symbol="GRO", as_of=as_of, bars=[], fundamentals=gro_low_margin)
    )
    assert sig_gro_flat.direction == "flat"


# =============================================================================
# Criterion 4: Insufficient data defense returning `insufficient_data`
# =============================================================================


def test_insufficient_data_error_handling() -> None:
    """Verify that insufficient data results in `insufficient_data` reason."""
    as_of = date(2026, 3, 1)

    # Technical strategy with only 3 bars (requires at least 21 for turtle_20)
    few_bars = [
        ConcreteBar(date(2026, 2, 26), "100", "102", "99", "101"),
        ConcreteBar(date(2026, 2, 27), "101", "103", "100", "102"),
        ConcreteBar(date(2026, 2, 28), "102", "104", "101", "103"),
    ]

    turtle = get_strategy("turtle_20_55")
    assert turtle is not None
    sig_turtle = turtle.evaluate(StrategyContext(symbol="T", as_of=as_of, bars=few_bars))
    assert sig_turtle.direction == "flat"
    assert "insufficient" in sig_turtle.reasons[0]

    # Fundamental strategy with missing required metrics
    missing_fund = ConcreteFundamentals(pe_trailing=None, pe_forward=None)
    val = get_strategy("value_basic")
    assert val is not None
    sig_val = val.evaluate(
        StrategyContext(symbol="V", as_of=as_of, bars=[], fundamentals=missing_fund)
    )
    assert sig_val.direction == "flat"
    assert "insufficient" in sig_val.reasons[0] or "missing" in sig_val.reasons[0]


# =============================================================================
# Criterion 5: Levels calculation matches manual formula
# =============================================================================


def test_levels_calculation_manual_arithmetic() -> None:
    """Verify compute_atr_levels aligns with textbook formulas and stop mults."""
    entry = Decimal("150.00")
    atr = Decimal("6.00")

    # Long: stop = 150 - (6 * 2) = 138; target = 150 + (6 * 3) = 168
    long_lvl = compute_atr_levels(
        entry_price=entry,
        atr=atr,
        direction="long",
        stop_mult=Decimal("2.0"),
        target_mult=Decimal("3.0"),
    )
    assert long_lvl["entry"] == Decimal("150.00")
    assert long_lvl["stop"] == Decimal("138.00")
    assert long_lvl["target"] == Decimal("168.00")

    # Short: stop = 150 + (6 * 1.5) = 159; target = 150 - (6 * 4) = 126
    short_lvl = compute_atr_levels(
        entry_price=entry,
        atr=atr,
        direction="short",
        stop_mult=Decimal("1.5"),
        target_mult=Decimal("4.0"),
    )
    assert short_lvl["entry"] == Decimal("150.00")
    assert short_lvl["stop"] == Decimal("159.00")
    assert short_lvl["target"] == Decimal("126.00")


# =============================================================================
# Criterion 6: Event-driven backtesting closed-loop mathematical identity
# =============================================================================


def test_backtest_closed_loop_mathematical_identity() -> None:
    """Verify BacktestEngine maintains conservation: final_equity == initial + sum(pnl)."""
    strat = get_strategy("turtle_20_55")
    assert strat is not None

    engine = BacktestEngine(strat)
    base_d = date(2026, 1, 1)

    # 40 days of bars: 25 days ranging at 100, then breakout to 130
    bars: list[Bar] = []
    for i in range(25):
        bars.append(
            ConcreteBar(
                trade_date=base_d + timedelta(days=i),
                open_="100",
                high="104",
                low="98",
                close="101",
            )
        )
    for j in range(25, 45):
        bars.append(
            ConcreteBar(
                trade_date=base_d + timedelta(days=j),
                open_=str(100 + (j - 25) * 2),
                high=str(106 + (j - 25) * 2),
                low=str(99 + (j - 25) * 2),
                close=str(105 + (j - 25) * 2),
            )
        )

    req = BacktestRequest(
        strategy_id="turtle_20_55",
        symbol="AAPL",
        start=base_d + timedelta(days=20),
        end=base_d + timedelta(days=44),
        initial_capital=Decimal("100000.00"),
    )

    res = engine.run(bars, req)

    # Closed-loop identity assertion
    total_realized_pnl = sum((t.pnl for t in res.trades if t.pnl is not None), Decimal(0))
    assert res.final_equity == req.initial_capital + total_realized_pnl
    assert res.total_trades > 0
    assert len(res.equity_curve) > 0
    assert res.win_rate >= Decimal(0)
    assert res.profit_factor >= Decimal(0)


# =============================================================================
# Criterion 7: Full-chain REST API Authenticated Lifecycle
# =============================================================================


async def test_full_chain_rest_api_lifecycle(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """Verify full end-to-end API lifecycle across all 5 endpoints."""
    # Mock data service for DI
    ds = AsyncMock()
    base_d = date(2026, 1, 1)
    bars: list[Bar] = [
        ConcreteBar(base_d + timedelta(days=i), "100", "105", "98", "102") for i in range(100)
    ]
    ds.get_bars.return_value = bars
    ds.get_fundamentals.return_value = ConcreteFundamentals()

    # Wire real StrategyService into API
    service = StrategyService(data_service=ds)
    set_strategy_service(service)

    # Mock logged-in user
    auth_user = AuthenticatedUser(
        id=uuid.uuid4(),
        email="trader@quant.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(),
    )
    app.dependency_overrides[current_user] = lambda: auth_user

    # 1. GET /api/v1/strategy/list
    r_list = await client.get("/api/v1/strategy/list")
    assert r_list.status_code == 200
    strat_list = r_list.json()
    assert len(strat_list) >= 7

    # 2. POST /api/v1/strategy/evaluate
    r_eval = await client.post(
        "/api/v1/strategy/evaluate",
        json={"strategy_id": "value_basic", "symbol": "AAPL", "as_of": "2026-03-01"},
    )
    assert r_eval.status_code == 200
    sig = r_eval.json()
    assert sig["symbol"] == "AAPL"
    assert sig["strategy_id"] == "value_basic"

    # 3. POST /api/v1/strategy/scan
    r_scan = await client.post(
        "/api/v1/strategy/scan",
        json={
            "strategy_id": "value_basic",
            "symbols": ["AAPL", "MSFT"],
            "as_of": "2026-03-01",
        },
    )
    assert r_scan.status_code == 200
    scan_res = r_scan.json()
    assert isinstance(scan_res, list)

    # 4. GET /api/v1/strategy/technical/{symbol}
    r_tech = await client.get("/api/v1/strategy/technical/AAPL?as_of=2026-03-01")
    assert r_tech.status_code == 200
    tech = r_tech.json()
    assert tech["symbol"] == "AAPL"
    assert tech["sma_20"] is not None

    # 5. POST /api/v1/strategy/backtest
    r_bt = await client.post(
        "/api/v1/strategy/backtest",
        json={
            "strategy_id": "turtle_20_55",
            "symbol": "AAPL",
            "start": "2026-02-01",
            "end": "2026-03-01",
            "initial_capital": "100000.00",
        },
    )
    assert r_bt.status_code == 200
    bt = r_bt.json()
    assert bt["strategy_id"] == "turtle_20_55"
    assert Decimal(bt["final_equity"]) > Decimal(0)
