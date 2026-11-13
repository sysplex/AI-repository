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
from app.modules.ai.prompts import (
    DEFAULT_FACTS_SUMMARY_TEMPLATE,
    DEFAULT_HEALTH_CHECK_TEMPLATE,
    DEFAULT_STOCK_ANALYSIS_TEMPLATE,
    PromptRegistry,
    PromptTemplate,
    default_prompt_registry,
    format_untrusted_facts,
    get_prompt_template,
    register_prompt_template,
    sanitize_untrusted_text,
)
from app.modules.ai.retry import (
    RetryableLLMCaller,
    ValidatedLLMResult,
    execute_with_retry,
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
from app.modules.ai.validator import (
    SchemaValidationResult,
    SchemaValidator,
    clean_and_extract_json,
    validate_json_schema,
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
    "DEFAULT_FACTS_SUMMARY_TEMPLATE",
    "DEFAULT_FALLBACK_PRICING",
    "DEFAULT_HEALTH_CHECK_TEMPLATE",
    "DEFAULT_MOCK_PAYLOAD",
    "DEFAULT_STOCK_ANALYSIS_TEMPLATE",
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
    "PromptRegistry",
    "PromptRegistryProtocol",
    "PromptTemplate",
    "QuotaExceededError",
    "QuotaServiceProtocol",
    "QuotaStatus",
    "ReportStatus",
    "RetryableLLMCaller",
    "SchemaValidationError",
    "SchemaValidationResult",
    "SchemaValidator",
    "ValidatedLLMResult",
    "calculate_cost",
    "clean_and_extract_json",
    "default_prompt_registry",
    "execute_with_retry",
    "format_untrusted_facts",
    "get_model_pricing",
    "get_prompt_template",
    "list_supported_models",
    "register_model_pricing",
    "register_prompt_template",
    "reset_pricing_registry",
    "sanitize_untrusted_text",
    "validate_json_schema",
]
