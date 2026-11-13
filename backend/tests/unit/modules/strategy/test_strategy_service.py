"""Unit tests for StrategyService facade (M3 / T06)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.core.errors import DataUnavailable, NotFound, ValidationFailed
from app.modules.strategy.indicators import Bar
from app.modules.strategy.schemas import (
    BacktestRequest,
    BacktestResult,
    Signal,
    TechnicalSnapshot,
)
from app.modules.strategy.service import StrategyService


class DummyBar:
    """Mock candlestick bar."""

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


class DummyFundamentals:
    """Mock fundamental data."""

    def __init__(self) -> None:
        self.pe_trailing = Decimal("15.0")
        self.pe_forward = Decimal("14.0")
        self.pb = Decimal("2.0")
        self.ps = Decimal("1.5")
        self.roe = Decimal("18.0")
        self.net_margin = Decimal("20.0")
        self.debt_to_equity = Decimal("0.8")
        self.dividend_yield = Decimal("3.5")
        self.market_cap = Decimal("1000000000")


@pytest.fixture
def mock_data_service() -> AsyncMock:
    """Mock for MarketDataServiceProtocol."""
    ds = AsyncMock()

    # Generate 100 consecutive days of bars
    base_date = date(2026, 1, 1)
    bars: list[Bar] = []
    price = Decimal("100.0")
    for i in range(100):
        d = base_date + timedelta(days=i)
        bars.append(
            DummyBar(
                trade_date=d,
                open_=str(price),
                high=str(price + Decimal("2.0")),
                low=str(price - Decimal("2.0")),
                close=str(price + Decimal("1.0")),
                volume=10000,
            )
        )
        price += Decimal("0.5")

    ds.get_bars.return_value = bars
    ds.get_fundamentals.return_value = DummyFundamentals()
    return ds


class TestStrategyService:
    """Test suite for StrategyService facade."""

    def test_list_strategies(self) -> None:
        service = StrategyService()
        strats = service.list_strategies()
        assert len(strats) >= 7
        ids = {s.id for s in strats}
        assert "turtle_20_55" in ids
        assert "dow_trend" in ids
        assert "pullback_rsi" in ids
        assert "reversal_123" in ids
        assert "value_basic" in ids
        assert "growth_basic" in ids
        assert "dividend_basic" in ids

    @pytest.mark.asyncio
    async def test_evaluate_not_found(self, mock_data_service: AsyncMock) -> None:
        service = StrategyService(data_service=mock_data_service)
        with pytest.raises(NotFound) as exc_info:
            await service.evaluate("non_existent", "AAPL", date(2026, 3, 1))
        assert "non_existent" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_evaluate_empty_symbol(self, mock_data_service: AsyncMock) -> None:
        service = StrategyService(data_service=mock_data_service)
        with pytest.raises(ValidationFailed):
            await service.evaluate("turtle_20_55", "   ", date(2026, 3, 1))

    @pytest.mark.asyncio
    async def test_evaluate_no_data_service(self) -> None:
        service = StrategyService(data_service=None)
        with pytest.raises(DataUnavailable):
            await service.evaluate("turtle_20_55", "AAPL", date(2026, 3, 1))

    @pytest.mark.asyncio
    async def test_evaluate_technical_strategy(self, mock_data_service: AsyncMock) -> None:
        service = StrategyService(data_service=mock_data_service)
        sig = await service.evaluate("turtle_20_55", "aapl", date(2026, 3, 1))
        assert isinstance(sig, Signal)
        assert sig.strategy_id == "turtle_20_55"
        assert sig.symbol == "AAPL"
        assert sig.as_of == date(2026, 3, 1)
        mock_data_service.get_bars.assert_awaited()

    @pytest.mark.asyncio
    async def test_evaluate_fundamental_strategy(self, mock_data_service: AsyncMock) -> None:
        service = StrategyService(data_service=mock_data_service)
        sig = await service.evaluate("value_basic", "msft", date(2026, 3, 1))
        assert isinstance(sig, Signal)
        assert sig.strategy_id == "value_basic"
        assert sig.symbol == "MSFT"
        mock_data_service.get_fundamentals.assert_awaited_with("MSFT")

    @pytest.mark.asyncio
    async def test_scan_not_found(self, mock_data_service: AsyncMock) -> None:
        service = StrategyService(data_service=mock_data_service)
        with pytest.raises(NotFound):
            await service.scan("unknown_strat", ["AAPL"], date(2026, 3, 1))

    @pytest.mark.asyncio
    async def test_scan_empty_universe(self, mock_data_service: AsyncMock) -> None:
        service = StrategyService(data_service=mock_data_service)
        with pytest.raises(ValidationFailed):
            await service.scan("turtle_20_55", ["  ", ""], date(2026, 3, 1))

    @pytest.mark.asyncio
    async def test_scan_filter_active_signals(self, mock_data_service: AsyncMock) -> None:
        service = StrategyService(data_service=mock_data_service)
        # Value strategy with qualifying fundamentals triggers long
        signals = await service.scan("value_basic", ["AAPL", "MSFT"], date(2026, 3, 1))
        assert isinstance(signals, list)
        for s in signals:
            assert s.direction != "flat"

    @pytest.mark.asyncio
    async def test_scan_include_flat(self, mock_data_service: AsyncMock) -> None:
        service = StrategyService(data_service=mock_data_service)
        signals = await service.scan(
            "turtle_20_55",
            ["AAPL"],
            date(2026, 3, 1),
            params={"include_flat": True},
        )
        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_compute_technical_snapshot(self, mock_data_service: AsyncMock) -> None:
        service = StrategyService(data_service=mock_data_service)
        snapshot = await service.compute_technical_snapshot("AAPL", date(2026, 3, 1))
        assert isinstance(snapshot, TechnicalSnapshot)
        assert snapshot.symbol == "AAPL"
        assert snapshot.as_of == date(2026, 3, 1)
        assert snapshot.sma_20 is not None
        assert snapshot.sma_50 is not None
        assert snapshot.rsi_14 is not None
        assert snapshot.macd is not None
        assert snapshot.atr_14 is not None

    @pytest.mark.asyncio
    async def test_compute_technical_snapshot_no_service(self) -> None:
        service = StrategyService(data_service=None)
        with pytest.raises(DataUnavailable):
            await service.compute_technical_snapshot("AAPL", date(2026, 3, 1))

    @pytest.mark.asyncio
    async def test_compute_technical_snapshot_empty_symbol(
        self, mock_data_service: AsyncMock
    ) -> None:
        service = StrategyService(data_service=mock_data_service)
        with pytest.raises(ValidationFailed):
            await service.compute_technical_snapshot("   ", date(2026, 3, 1))

    @pytest.mark.asyncio
    async def test_backtest_invalid_date_range(self, mock_data_service: AsyncMock) -> None:
        service = StrategyService(data_service=mock_data_service)
        req = BacktestRequest(
            strategy_id="turtle_20_55",
            symbol="AAPL",
            start=date(2026, 3, 10),
            end=date(2026, 3, 1),
        )
        with pytest.raises(ValidationFailed):
            await service.backtest(req)

    @pytest.mark.asyncio
    async def test_backtest_strategy_not_found(self, mock_data_service: AsyncMock) -> None:
        service = StrategyService(data_service=mock_data_service)
        req = BacktestRequest(
            strategy_id="non_existent",
            symbol="AAPL",
            start=date(2026, 1, 1),
            end=date(2026, 3, 1),
        )
        with pytest.raises(NotFound):
            await service.backtest(req)

    @pytest.mark.asyncio
    async def test_backtest_no_data_service(self) -> None:
        service = StrategyService(data_service=None)
        req = BacktestRequest(
            strategy_id="turtle_20_55",
            symbol="AAPL",
            start=date(2026, 1, 1),
            end=date(2026, 3, 1),
        )
        with pytest.raises(DataUnavailable):
            await service.backtest(req)

    @pytest.mark.asyncio
    async def test_backtest_success(self, mock_data_service: AsyncMock) -> None:
        service = StrategyService(data_service=mock_data_service)
        req = BacktestRequest(
            strategy_id="turtle_20_55",
            symbol="AAPL",
            start=date(2026, 1, 10),
            end=date(2026, 3, 1),
            initial_capital=Decimal("50000.0"),
        )
        res = await service.backtest(req)
        assert isinstance(res, BacktestResult)
        assert res.strategy_id == "turtle_20_55"
        assert res.symbol == "AAPL"
        assert res.initial_capital == Decimal("50000.0")
        assert res.final_equity > Decimal(0)
