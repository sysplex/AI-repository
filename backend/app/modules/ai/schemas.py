"""M5 AI 核心框架 Pydantic DTO Schemas（T01），`CONTRACTS.md §1`。

包含 LLM 调用结果、数据快照、AI 报告、配额状态、数字溯源结果与请求响应模型。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AIAnalyzeRequest",
    "AIPromptInfo",
    "AIRecommendationOutcomeCreate",
    "AIRecommendationOutcomeResponse",
    "AIReportCreate",
    "AIReportResponse",
    "AnalysisReport",
    "BudgetCircuitStatus",
    "DataSnapshotCreate",
    "DataSnapshotResponse",
    "FactTracingResult",
    "FactTracingViolation",
    "LLMMessage",
    "LLMResult",
    "QuotaStatus",
    "ReportStatus",
]

ReportStatus = Literal["pending", "processing", "success", "failed"]


class LLMMessage(BaseModel):
    """LLM 输入消息"""

    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class LLMResult(BaseModel):
    """LLM 调用返回结果"""

    model_config = ConfigDict(frozen=True)

    parsed_json: dict[str, Any] | None = None
    raw_text: str
    model: str
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: Decimal = Field(default=Decimal("0.000000"), ge=0)
    latency_ms: int = Field(default=0, ge=0)


class DataSnapshotCreate(BaseModel):
    """数据快照创建请求"""

    model_config = ConfigDict(frozen=True)

    content_hash: str = Field(min_length=64, max_length=64)
    facts: dict[str, Any]
    as_of: datetime


class DataSnapshotResponse(BaseModel):
    """数据快照返回"""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    content_hash: str
    facts: dict[str, Any]
    as_of: datetime
    created_at: datetime


class AIReportCreate(BaseModel):
    """创建 AI 报告记录"""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    use_case: str
    params: dict[str, Any] = Field(default_factory=dict)
    cache_key: str
    data_snapshot_id: str
    prompt_version: str
    model: str
    payload: dict[str, Any] = Field(default_factory=dict)
    cost_usd: Decimal = Field(default=Decimal("0.000000"), ge=0)
    status: ReportStatus = "pending"
    error_message: str | None = None


class AIReportResponse(BaseModel):
    """AI 报告基本响应"""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    user_id: UUID
    use_case: str
    params: dict[str, Any]
    cache_key: str
    data_snapshot_id: str
    prompt_version: str
    model: str
    payload: dict[str, Any]
    cost_usd: Decimal
    status: ReportStatus
    error_message: str | None = None
    created_at: datetime


class AIRecommendationOutcomeCreate(BaseModel):
    """建议评估记录创建"""

    model_config = ConfigDict(frozen=True)

    report_id: UUID
    symbol: str = Field(min_length=1, max_length=16)
    verdict: str
    price_at_report: Decimal = Field(gt=0)
    ret_5d: Decimal | None = None
    ret_20d: Decimal | None = None
    ret_60d: Decimal | None = None
    ret_vs_spy_20d: Decimal | None = None


class AIRecommendationOutcomeResponse(BaseModel):
    """建议评估记录响应"""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    report_id: UUID
    symbol: str
    verdict: str
    price_at_report: Decimal
    ret_5d: Decimal | None = None
    ret_20d: Decimal | None = None
    ret_60d: Decimal | None = None
    ret_vs_spy_20d: Decimal | None = None
    created_at: datetime


class AnalysisReport(BaseModel):
    """对外统一分析报告封装（含缓存标记）"""

    model_config = ConfigDict(frozen=True)

    id: UUID
    use_case: str
    payload: dict[str, Any]
    cached: bool
    data_snapshot_id: str
    prompt_version: str
    model: str
    cost_usd: Decimal
    created_at: datetime


class QuotaStatus(BaseModel):
    """用户当日配额状态"""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    usage_date: date
    calls_today: int
    daily_quota: int
    remaining_calls: int
    is_exceeded: bool


class BudgetCircuitStatus(BaseModel):
    """全局或用户预算熔断器状态"""

    model_config = ConfigDict(frozen=True)

    state: Literal["CLOSED", "OPEN", "HALF_OPEN"]
    daily_cost_usd: Decimal
    daily_budget_usd: Decimal
    monthly_cost_usd: Decimal
    monthly_budget_usd: Decimal
    is_open: bool
    tripped_at: datetime | None = None
    tripped_reason: str | None = None


class FactTracingViolation(BaseModel):
    """数字溯源违规详情"""

    model_config = ConfigDict(frozen=True)

    field_path: str
    claimed_value: Decimal | str
    reason: str  # "untraced_number", "invalid_source_path", "missing_fact", "forbidden_word"


class FactTracingResult(BaseModel):
    """数字溯源校验结果"""

    model_config = ConfigDict(frozen=True)

    valid: bool
    violations: list[FactTracingViolation] = Field(default_factory=list)
    checked_numbers_count: int = 0


class AIAnalyzeRequest(BaseModel):
    """执行 AI 分析请求"""

    model_config = ConfigDict(frozen=True)

    use_case: str = Field(min_length=1, max_length=64)
    facts: dict[str, Any]
    params: dict[str, Any] = Field(default_factory=dict)
    prompt_version: str | None = None


class AIPromptInfo(BaseModel):
    """可用提示词信息"""

    model_config = ConfigDict(frozen=True)

    use_case: str
    version: str
    description: str
    is_active: bool = True
    output_schema: dict[str, Any] = Field(default_factory=dict)
