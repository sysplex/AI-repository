"""M8 筛选器与主题自选异常体系，`CONTRACTS.md §4`。

全部继承自 ``AppError``，支持统一错误码、HTTP 状态码映射与多租户审计追踪。
"""

from __future__ import annotations

from typing import Any

from app.core.errors import AppError, ErrorCode

__all__ = [
    "DuplicateWatchlistItemError",
    "ScreenerError",
    "ScreenerExecutionError",
    "ScreenerRunNotFoundError",
    "StrategyNotFoundError",
    "ThemeNotFoundError",
    "UniverseNotFoundError",
    "WatchlistItemNotFoundError",
    "WatchlistNotFoundError",
]


class ScreenerError(AppError):
    """筛选器模块业务异常基类。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500
    default_message: str = "筛选器服务内部错误"

    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, details=details)


class UniverseNotFoundError(ScreenerError):
    """指定的股票池不存在 (404)。"""

    code: ErrorCode = ErrorCode.NOT_FOUND
    http_status: int = 404
    default_message: str = "指定的股票池不存在"


class StrategyNotFoundError(ScreenerError):
    """指定的预设策略不存在 (404)。"""

    code: ErrorCode = ErrorCode.NOT_FOUND
    http_status: int = 404
    default_message: str = "指定的预设策略不存在"


class ThemeNotFoundError(ScreenerError):
    """指定的主题不存在 (404)。"""

    code: ErrorCode = ErrorCode.NOT_FOUND
    http_status: int = 404
    default_message: str = "指定的主题不存在"


class ScreenerRunNotFoundError(ScreenerError):
    """筛选任务不存在或非当前租户所有 (404)。"""

    code: ErrorCode = ErrorCode.NOT_FOUND
    http_status: int = 404
    default_message: str = "未找到指定的筛选任务记录"


class WatchlistNotFoundError(ScreenerError):
    """自选清单不存在或非当前租户所有 (404)。"""

    code: ErrorCode = ErrorCode.NOT_FOUND
    http_status: int = 404
    default_message: str = "未找到指定的自选清单"


class WatchlistItemNotFoundError(ScreenerError):
    """自选清单标的不存在 (404)。"""

    code: ErrorCode = ErrorCode.NOT_FOUND
    http_status: int = 404
    default_message: str = "自选清单中未找到指定标的"


class DuplicateWatchlistItemError(ScreenerError):
    """自选清单中已存在该标的 (409)。"""

    code: ErrorCode = ErrorCode.STATE_CONFLICT
    http_status: int = 409
    default_message: str = "该标的已在当前自选清单中"


class ScreenerExecutionError(ScreenerError):
    """筛选引擎批量执行致命异常 (500)。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500
    default_message: str = "策略筛选批量执行异常"
