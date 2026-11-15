"""M6 AI 研究用例异常体系，`CONTRACTS.md §0, §7`。

定义 research 模块专用业务异常，全部继承自 ``AppError``，
支持统一错误码、HTTP 状态码映射与多租户隔离审计追踪。
"""

from __future__ import annotations

from typing import Any

from app.core.errors import AppError, ErrorCode

__all__ = [
    "ComplianceViolationError",
    "InsufficientDataError",
    "InvalidParameterError",
    "QuantitativeCalculationError",
    "ResearchError",
    "SymbolNotFoundError",
]


class ResearchError(AppError):
    """AI 研究用例业务异常基类。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500
    default_message: str = "AI 研究服务内部错误"

    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)


class SymbolNotFoundError(ResearchError):
    """指定股票标的不存在或无法查询到有效信息 (404)。"""

    code: ErrorCode = ErrorCode.NOT_FOUND
    http_status: int = 404
    default_message: str = "未找到指定的股票标的或该标的数据不存在"


class InsufficientDataError(ResearchError):
    """股票数据严重缺失，无法支撑分析与指标计算 (422)。"""

    code: ErrorCode = ErrorCode.DATA_UNAVAILABLE
    http_status: int = 422
    default_message: str = "标的数据严重缺失，无法生成可靠研究结论"


class InvalidParameterError(ResearchError):
    """请求参数非法或超出允许范围 (400)。"""

    code: ErrorCode = ErrorCode.VALIDATION_ERROR
    http_status: int = 400
    default_message: str = "研究用例请求参数无效"


class QuantitativeCalculationError(ResearchError):
    """代码量化衍生指标或交易计划计算失败 (500)。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500
    default_message: str = "量化指标派生或交易计划计算异常"


class ComplianceViolationError(ResearchError):
    """AI 输出未通过合规校验、缺少核心破裂监控条件或篡改确定性量化结果 (422)。"""

    code: ErrorCode = ErrorCode.LLM_OUTPUT_INVALID
    http_status: int = 422
    default_message: str = "AI 分析输出未通过合规校验或包含被篡改的数据"
