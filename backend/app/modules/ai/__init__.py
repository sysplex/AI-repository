"""AI 核心框架模块（M5）。

包含 LLM 适配器、报告模型、提示词版本管理、输出 Schema 校验、数字溯源与配额风控。
"""

from __future__ import annotations

from app.modules.ai.models import (
    AIRecommendationOutcome,
    AIReport,
)
from app.modules.ai.ports import (
    LLMClient,
    PromptRegistryProtocol,
    QuotaServiceProtocol,
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
    "AnalysisReport",
    "DataSnapshotCreate",
    "DataSnapshotResponse",
    "FactTracingResult",
    "FactTracingViolation",
    "LLMClient",
    "LLMMessage",
    "LLMResult",
    "PromptRegistryProtocol",
    "QuotaServiceProtocol",
    "QuotaStatus",
    "ReportStatus",
]
