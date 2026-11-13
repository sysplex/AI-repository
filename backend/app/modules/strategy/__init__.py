"""Strategy engine module for technical indicators and quantitative strategies."""

from app.modules.strategy.indicators import (
    Bar,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_obv,
    calculate_rsi,
    calculate_sma,
    calculate_support_resistance,
    calculate_swing_high_low,
    calculate_true_range,
)
from app.modules.strategy.ports import Strategy, StrategyRegistry
from app.modules.strategy.schemas import (
    BacktestRequest,
    BacktestResult,
    EquityPoint,
    Signal,
    SignalDirection,
    StrategyContext,
    StrategyMetadata,
    TechnicalSnapshot,
    TradeRecord,
)

__all__ = [
    "BacktestRequest",
    "BacktestResult",
    "Bar",
    "EquityPoint",
    "Signal",
    "SignalDirection",
    "Strategy",
    "StrategyContext",
    "StrategyMetadata",
    "StrategyRegistry",
    "TechnicalSnapshot",
    "TradeRecord",
    "calculate_atr",
    "calculate_bollinger_bands",
    "calculate_ema",
    "calculate_macd",
    "calculate_obv",
    "calculate_rsi",
    "calculate_sma",
    "calculate_support_resistance",
    "calculate_swing_high_low",
    "calculate_true_range",
]
