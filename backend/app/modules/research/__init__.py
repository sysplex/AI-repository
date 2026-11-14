"""`research` 模块（M6 AI 研究用例 A：深度研究 / 买入决策 / 技术面 / 财报解读）。

实现与对外暴露：
- 领域 DTO Schemas
- 端口协议
- 业务异常
"""

from __future__ import annotations

from app.modules.research.exceptions import (
    InsufficientDataError,
    InvalidParameterError,
    QuantitativeCalculationError,
    ResearchError,
    SymbolNotFoundError,
)
from app.modules.research.ports import (
    AIServiceProtocol,
    FactAggregatorProtocol,
    MarketDataServiceProtocol,
    QuantitativeEngineProtocol,
    ResearchServiceProtocol,
    StrategyServiceProtocol,
)
from app.modules.research.schemas import (
    BuyDecisionPayload,
    BuyDecisionRequest,
    BuyVerdict,
    EarningsAnalysisRequest,
    EarningsAssessment,
    EarningsMetric,
    EarningsPayload,
    EvidenceItem,
    FactorAssessment,
    FactorItem,
    FactorRating,
    InvestmentHorizon,
    MoatItem,
    MoatStrength,
    PricePosition,
    ResearchEnvelope,
    ResearchPayload,
    ResearchRequest,
    RevenueSourceItem,
    RiskItem,
    RiskLevel,
    RiskSeverity,
    Scenarios,
    TechnicalAnalysisRequest,
    TechnicalMetricExplanation,
    TechnicalPayload,
    TradePlan,
)

__all__ = [
    "AIServiceProtocol",
    "BuyDecisionPayload",
    "BuyDecisionRequest",
    "BuyVerdict",
    "EarningsAnalysisRequest",
    "EarningsAssessment",
    "EarningsMetric",
    "EarningsPayload",
    "EvidenceItem",
    "FactAggregatorProtocol",
    "FactorAssessment",
    "FactorItem",
    "FactorRating",
    "InsufficientDataError",
    "InvalidParameterError",
    "InvestmentHorizon",
    "MarketDataServiceProtocol",
    "MoatItem",
    "MoatStrength",
    "PricePosition",
    "QuantitativeCalculationError",
    "QuantitativeEngineProtocol",
    "ResearchEnvelope",
    "ResearchError",
    "ResearchPayload",
    "ResearchRequest",
    "ResearchServiceProtocol",
    "RevenueSourceItem",
    "RiskItem",
    "RiskLevel",
    "RiskSeverity",
    "Scenarios",
    "StrategyServiceProtocol",
    "SymbolNotFoundError",
    "TechnicalAnalysisRequest",
    "TechnicalMetricExplanation",
    "TechnicalPayload",
    "TradePlan",
]
