"""M5 AI 核心框架异常体系，`CONTRACTS.md §5`。

定义 AI 模块专用业务异常，全部继承自 ``AppError``，
支持统一错误码、HTTP 状态码映射与审计追踪。
"""

from __future__ import annotations

from typing import Any

from app.core.errors import AppError, ErrorCode

__all__ = [
    "AIServiceError",
    "AIServiceUnavailableError",
    "BudgetCircuitOpenError",
    "FactTracingError",
    "PromptNotFoundError",
    "QuotaExceededError",
    "SchemaValidationError",
]


class AIServiceError(AppError):
    """AI 核心框架业务异常基类。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500
    default_message: str = "AI 服务内部错误"

    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)


class AIServiceUnavailableError(AIServiceError):
    """LLM 外部服务网络异常/超时/不可用 (503)。"""

    code: ErrorCode = ErrorCode.LLM_FAILED
    http_status: int = 503
    default_message: str = "LLM 外部服务暂不可用或请求超时"


class SchemaValidationError(AIServiceError):
    """LLM 输出不符合预设 JSON Schema 且重试失败 (422)。"""

    code: ErrorCode = ErrorCode.LLM_OUTPUT_INVALID
    http_status: int = 422
    default_message: str = "AI 输出未能通过 Schema 校验"


class FactTracingError(AIServiceError):
    """AI 输出包含编造的虚假数字或不存在的事实路径 (422)。"""

    code: ErrorCode = ErrorCode.LLM_OUTPUT_INVALID
    http_status: int = 422
    default_message: str = "AI 输出包含未经数据源佐证的幻觉数字"


class QuotaExceededError(AIServiceError):
    """用户当日 AI 配额已耗尽 (429)。"""

    code: ErrorCode = ErrorCode.QUOTA_EXCEEDED
    http_status: int = 429
    default_message: str = "用户当日 AI 请求配额已用尽"


class BudgetCircuitOpenError(AIServiceError):
    """全局或用户预算熔断器触发，暂停外部 LLM 请求 (503)。"""

    code: ErrorCode = ErrorCode.BUDGET_CIRCUIT_OPEN
    http_status: int = 503
    default_message: str = "AI 预算熔断器已开启，暂停外部模型调用"


class PromptNotFoundError(AIServiceError):
    """找不到对应 use_case 或版本的提示词模板 (404)。"""

    code: ErrorCode = ErrorCode.NOT_FOUND
    http_status: int = 404
    default_message: str = "找不到指定的提示词模板"
