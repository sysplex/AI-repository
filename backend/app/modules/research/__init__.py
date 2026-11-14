"""`research` 模块（M6 AI 研究用例 A：深度研究 / 买入决策 / 技术面 / 财报解读）。

实现与对外暴露：
- 领域 DTO Schemas
- 端口协议
- 业务异常
- 提示词模板与注册器
- 事实聚合器 (FactAggregator)
- 代码量化衍生指标引擎 (QuantitativeEngine)
"""

from __future__ import annotations

from app.modules.research.aggregator import (
    USE_CASE_BUY_DECISION,
    USE_CASE_EARNINGS,
    USE_CASE_RESEARCH,
    USE_CASE_TECHNICAL,
    VALID_USE_CASES,
    FactAggregator,
)
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
from app.modules.research.prompts import (
    BUY_DECISION_V1_TEMPLATE,
    EARNINGS_V1_TEMPLATE,
    RESEARCH_PROMPT_TEMPLATES,
    RESEARCH_V1_TEMPLATE,
    TECHNICAL_V1_TEMPLATE,
    ResearchPromptInfo,
    ResearchPromptTemplate,
    get_research_prompt_template,
    register_research_prompts,
)
from app.modules.research.quantitative import (
    QuantitativeEngine,
    compute_pos_in_52w_range,
    compute_target_vs_price_pct,
    compute_technical_trade_plan,
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
from app.modules.research.service import ResearchService

__all__ = [
    "AIServiceProtocol",
    "BUY_DECISION_V1_TEMPLATE",
    "BuyDecisionPayload",
    "BuyDecisionRequest",
    "BuyVerdict",
    "EARNINGS_V1_TEMPLATE",
    "EarningsAnalysisRequest",
    "EarningsAssessment",
    "EarningsMetric",
    "EarningsPayload",
    "EvidenceItem",
    "FactAggregator",
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
    "QuantitativeEngine",
    "QuantitativeEngineProtocol",
    "RESEARCH_PROMPT_TEMPLATES",
    "RESEARCH_V1_TEMPLATE",
    "ResearchEnvelope",
    "ResearchError",
    "ResearchPayload",
    "ResearchPromptInfo",
    "ResearchPromptTemplate",
    "ResearchRequest",
    "ResearchService",
    "ResearchServiceProtocol",
    "RevenueSourceItem",
    "RiskItem",
    "RiskLevel",
    "RiskSeverity",
    "Scenarios",
    "StrategyServiceProtocol",
    "SymbolNotFoundError",
    "TECHNICAL_V1_TEMPLATE",
    "TechnicalAnalysisRequest",
    "TechnicalMetricExplanation",
    "TechnicalPayload",
    "TradePlan",
    "USE_CASE_BUY_DECISION",
    "USE_CASE_EARNINGS",
    "USE_CASE_RESEARCH",
    "USE_CASE_TECHNICAL",
    "VALID_USE_CASES",
    "compute_pos_in_52w_range",
    "compute_target_vs_price_pct",
    "compute_technical_trade_plan",
    "get_research_prompt_template",
    "register_research_prompts",
]
