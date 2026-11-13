"""Strategy engine module for technical indicators and quantitative strategies."""

from app.modules.strategy.backtest import BacktestEngine
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
from app.modules.strategy.levels import compute_atr_levels
from app.modules.strategy.ports import (
    MarketDataServiceProtocol,
    Strategy,
    StrategyRegistry,
)
from app.modules.strategy.registry import (
    StrategyRegistryImpl,
    default_registry,
    get_strategy,
    list_strategies,
    register_strategy,
)
from app.modules.strategy.schemas import (
    BacktestRequest,
    BacktestResult,
    EquityPoint,
    EvaluateRequest,
    ScanRequest,
    Signal,
    SignalDirection,
    StrategyContext,
    StrategyMetadata,
    TechnicalSnapshot,
    TradeRecord,
)
from app.modules.strategy.service import StrategyService

__all__ = [
    "BacktestEngine",
    "BacktestRequest",
    "BacktestResult",
    "Bar",
    "EquityPoint",
    "EvaluateRequest",
    "MarketDataServiceProtocol",
    "ScanRequest",
    "Signal",
    "SignalDirection",
    "Strategy",
    "StrategyContext",
    "StrategyMetadata",
    "StrategyRegistry",
    "StrategyRegistryImpl",
    "StrategyService",
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
    "compute_atr_levels",
    "default_registry",
    "get_strategy",
    "list_strategies",
    "register_strategy",
]
