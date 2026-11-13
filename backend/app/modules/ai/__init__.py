"""AI 核心框架模块（M5）。

包含 LLM 适配器、报告模型、提示词版本管理、输出 Schema 校验、数字溯源与配额风控。
"""

from __future__ import annotations

from app.modules.ai.adapters import (
    DEFAULT_MOCK_PAYLOAD,
    BaseLLMClient,
    MockCall,
    MockFaultMode,
    MockLLMClient,
)
from app.modules.ai.exceptions import (
    AIServiceError,
    AIServiceUnavailableError,
    BudgetCircuitOpenError,
    FactTracingError,
    PromptNotFoundError,
    QuotaExceededError,
    SchemaValidationError,
)
from app.modules.ai.models import (
    AIRecommendationOutcome,
    AIReport,
)
from app.modules.ai.ports import (
    LLMClient,
    PromptRegistryProtocol,
    QuotaServiceProtocol,
)
from app.modules.ai.pricing import (
    COST_DECIMAL_PLACES,
    COST_QUANTIZE_EXPONENT,
    DEFAULT_FALLBACK_PRICING,
    ModelPricing,
    calculate_cost,
    get_model_pricing,
    list_supported_models,
    register_model_pricing,
    reset_pricing_registry,
)
from app.modules.ai.schemas import (
    AIAnalyzeRequest,
    AIPromptInfo,
    AIRecommendationOutcomeCreate,
    AIRecommendationOutcomeResponse,
    AIReportCreate,
    AIReportResponse,
    AnalysisReport,
    DataSnapshotCreate,
    DataSnapshotResponse,
    FactTracingResult,
    FactTracingViolation,
    LLMMessage,
    LLMResult,
    QuotaStatus,
    ReportStatus,
)

__all__ = [
    "AIAnalyzeRequest",
    "AIPromptInfo",
    "AIRecommendationOutcome",
    "AIRecommendationOutcomeCreate",
    "AIRecommendationOutcomeResponse",
    "AIReport",
    "AIReportCreate",
    "AIReportResponse",
    "AIServiceError",
    "AIServiceUnavailableError",
    "AnalysisReport",
    "BaseLLMClient",
    "BudgetCircuitOpenError",
    "COST_DECIMAL_PLACES",
    "COST_QUANTIZE_EXPONENT",
    "DEFAULT_FALLBACK_PRICING",
    "DEFAULT_MOCK_PAYLOAD",
    "DataSnapshotCreate",
    "DataSnapshotResponse",
    "FactTracingError",
    "FactTracingResult",
    "FactTracingViolation",
    "LLMClient",
    "LLMMessage",
    "LLMResult",
    "MockCall",
    "MockFaultMode",
    "MockLLMClient",
    "ModelPricing",
    "PromptNotFoundError",
    "PromptRegistryProtocol",
    "QuotaExceededError",
    "QuotaServiceProtocol",
    "QuotaStatus",
    "ReportStatus",
    "SchemaValidationError",
    "calculate_cost",
    "get_model_pricing",
    "list_supported_models",
    "register_model_pricing",
    "reset_pricing_registry",
]
