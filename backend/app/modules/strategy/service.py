"""Strategy engine facade service orchestrating data retrieval and strategy execution."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from app.core.errors import DataUnavailable, NotFound, ValidationFailed
from app.modules.strategy.backtest import BacktestEngine
from app.modules.strategy.indicators import (
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_obv,
    calculate_rsi,
    calculate_sma,
    calculate_support_resistance,
)
from app.modules.strategy.ports import MarketDataServiceProtocol, StrategyRegistry
from app.modules.strategy.registry import default_registry
from app.modules.strategy.schemas import (
    BacktestRequest,
    BacktestResult,
    Signal,
    StrategyContext,
    StrategyMetadata,
    TechnicalSnapshot,
)


class StrategyService:
    """Facade orchestrating market data fetching, indicator calculations, and strategy runs."""

    def __init__(
        self,
        data_service: MarketDataServiceProtocol | Any = None,
        registry: StrategyRegistry | None = None,
    ) -> None:
        self._data_service = data_service
        self._registry = registry or default_registry

    def list_strategies(self) -> list[StrategyMetadata]:
        """List metadata for all registered quantitative and technical strategies."""
        return [
            StrategyMetadata(
                id=strat.id,
                display_name=strat.display_name,
                category=strat.category,
                description=strat.description,
                requires=sorted(strat.requires),
                default_params=strat.default_params,
            )
            for strat in self._registry.list_all()
        ]

    async def evaluate(
        self,
        strategy_id: str,
        symbol: str,
        as_of: date,
        params: dict[str, Any] | None = None,
    ) -> Signal:
        """Evaluate a registered strategy on a specific stock symbol as of a target date."""
        strat = self._registry.get(strategy_id)
        if strat is None:
            raise NotFound(f"Strategy '{strategy_id}' not found")

        symbol = symbol.strip().upper()
        if not symbol:
            raise ValidationFailed("Symbol must not be empty")

        if self._data_service is None:
            raise DataUnavailable("Market data service is not configured")

        merged_params = dict(strat.default_params)
        if params:
            merged_params.update(params)

        bars: Sequence[Any] = []
        fundamentals: Any = None

        if "bars" in strat.requires:
            lookback_days = int(merged_params.get("lookback_days", 400))
            start_date = as_of - timedelta(days=lookback_days)
            raw_bars = await self._data_service.get_bars(
                symbol=symbol,
                start=start_date,
                end=as_of,
                interval="1d",
                adjusted=True,
            )
            sorted_bars = sorted(raw_bars, key=lambda b: b.trade_date)
            bars = [b for b in sorted_bars if b.trade_date <= as_of]

        if "fundamentals" in strat.requires:
            fundamentals = await self._data_service.get_fundamentals(symbol)

        ctx = StrategyContext(
            symbol=symbol,
            as_of=as_of,
            bars=bars,
            fundamentals=fundamentals,
            params=merged_params,
        )
        return strat.evaluate(ctx)

    async def scan(
        self,
        strategy_id: str,
        universe: Sequence[str],
        as_of: date,
        params: dict[str, Any] | None = None,
    ) -> list[Signal]:
        """Scan a universe of stock symbols with a strategy and filter active signals."""
        strat = self._registry.get(strategy_id)
        if strat is None:
            raise NotFound(f"Strategy '{strategy_id}' not found")

        clean_universe = [s.strip().upper() for s in universe if s.strip()]
        if not clean_universe:
            raise ValidationFailed("Universe must contain at least one valid symbol")

        signals: list[Signal] = []
        include_flat = bool(params.get("include_flat", False)) if params else False

        for sym in clean_universe:
            sig = await self.evaluate(
                strategy_id=strategy_id,
                symbol=sym,
                as_of=as_of,
                params=params,
            )
            if include_flat or sig.direction != "flat":
                signals.append(sig)

        return signals

    async def compute_technical_snapshot(
        self,
        symbol: str,
        as_of: date | None = None,
    ) -> TechnicalSnapshot:
        """Compute technical indicator snapshot for a symbol as of a target date."""
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValidationFailed("Symbol must not be empty")

        target_date = as_of or date.today()
        if self._data_service is None:
            raise DataUnavailable("Market data service is not configured")

        start_date = target_date - timedelta(days=400)
        raw_bars = await self._data_service.get_bars(
            symbol=symbol,
            start=start_date,
            end=target_date,
            interval="1d",
            adjusted=True,
        )
        sorted_bars = sorted(raw_bars, key=lambda b: b.trade_date)
        bars = [b for b in sorted_bars if b.trade_date <= target_date]

        macd_line, macd_signal, macd_hist = calculate_macd(bars, 12, 26, 9)
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(bars, 20)
        support, resistance = calculate_support_resistance(bars, 20)

        return TechnicalSnapshot(
            symbol=symbol,
            as_of=target_date,
            sma_20=calculate_sma(bars, 20),
            sma_50=calculate_sma(bars, 50),
            sma_200=calculate_sma(bars, 200),
            ema_12=calculate_ema(bars, 12),
            ema_26=calculate_ema(bars, 26),
            rsi_14=calculate_rsi(bars, 14),
            macd=macd_line,
            macd_signal=macd_signal,
            macd_hist=macd_hist,
            atr_14=calculate_atr(bars, 14),
            bb_upper=bb_upper,
            bb_middle=bb_middle,
            bb_lower=bb_lower,
            obv=calculate_obv(bars),
            support=support,
            resistance=resistance,
        )

    async def backtest(self, req: BacktestRequest) -> BacktestResult:
        """Execute historical backtesting simulation for a registered strategy."""
        if req.start > req.end:
            raise ValidationFailed("Start date cannot be after end date")

        strat = self._registry.get(req.strategy_id)
        if strat is None:
            raise NotFound(f"Strategy '{req.strategy_id}' not found")

        if self._data_service is None:
            raise DataUnavailable("Market data service is not configured")

        warmup_days = int(req.params.get("warmup_days", 400))
        fetch_start = req.start - timedelta(days=warmup_days)

        raw_bars = await self._data_service.get_bars(
            symbol=req.symbol,
            start=fetch_start,
            end=req.end,
            interval="1d",
            adjusted=True,
        )
        sorted_bars = sorted(raw_bars, key=lambda b: b.trade_date)

        engine = BacktestEngine(strat)
        return engine.run(sorted_bars, req)
