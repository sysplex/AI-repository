"""统一错误体系（M0 / T03），`CONTRACTS.md §4` 与 `docs/05-api-spec.md §1.1–1.2`。

T01 空壳只导出 ``register_exception_handlers`` 的 no-op；本任务整体重写。
所有错误响应统一为::

    {"error": {"code": ..., "message": ..., "details": ..., "request_id": ...}}
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, request_id_var

__all__ = [
    "AppError",
    "BudgetCircuitOpen",
    "DataUnavailable",
    "ErrorCode",
    "Forbidden",
    "IdempotencyConflict",
    "InsufficientFunds",
    "InsufficientPosition",
    "InternalError",
    "InvalidOrder",
    "LLMFailed",
    "LLMOutputInvalid",
    "NotFound",
    "QuotaExceeded",
    "RateLimited",
    "StateConflict",
    "TokenExpired",
    "Unauthenticated",
    "ValidationFailed",
    "register_exception_handlers",
]


class ErrorCode(StrEnum):
    """`docs/05-api-spec.md §1.2` 的错误码全集，外加 `INTERNAL_ERROR`（契约 §4）。"""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"  # noqa: S105 - 枚举值，不是口令
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    STATE_CONFLICT = "STATE_CONFLICT"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    INSUFFICIENT_POSITION = "INSUFFICIENT_POSITION"
    INVALID_ORDER = "INVALID_ORDER"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    LLM_FAILED = "LLM_FAILED"
    LLM_OUTPUT_INVALID = "LLM_OUTPUT_INVALID"
    BUDGET_CIRCUIT_OPEN = "BUDGET_CIRCUIT_OPEN"
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: 每个错误码的默认中文文案；500 对外固定使用通用文案，不泄露内部信息。
DEFAULT_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "参数不合法",
    ErrorCode.UNAUTHENTICATED: "未登录或凭据无效",
    ErrorCode.TOKEN_EXPIRED: "登录令牌已过期",
    ErrorCode.FORBIDDEN: "无权限执行此操作",
    ErrorCode.NOT_FOUND: "资源不存在",
    ErrorCode.IDEMPOTENCY_CONFLICT: "幂等键冲突",
    ErrorCode.STATE_CONFLICT: "当前状态不允许此操作",
    ErrorCode.INSUFFICIENT_FUNDS: "可用资金不足",
    ErrorCode.INSUFFICIENT_POSITION: "持仓数量不足",
    ErrorCode.INVALID_ORDER: "订单参数不符合业务规则",
    ErrorCode.DATA_UNAVAILABLE: "数据源暂不可用",
    ErrorCode.RATE_LIMITED: "请求过于频繁，请稍后重试",
    ErrorCode.QUOTA_EXCEEDED: "配额已用完",
    ErrorCode.LLM_FAILED: "AI 服务调用失败",
    ErrorCode.LLM_OUTPUT_INVALID: "AI 输出未通过校验",
    ErrorCode.BUDGET_CIRCUIT_OPEN: "AI 预算熔断已开启",
    ErrorCode.INTERNAL_ERROR: "服务器内部错误",
}


class AppError(Exception):
    """业务/系统错误基类。

    子类用类属性声明默认 ``code`` / ``http_status``；``message`` 与
    ``details`` 可在抛出点覆盖。``details`` 会被复制，避免共享可变字典。
    """

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500
    default_message: str = DEFAULT_MESSAGES[ErrorCode.INTERNAL_ERROR]

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message if message is not None else self.default_message
        self.details: dict[str, Any] = dict(details) if details else {}
        super().__init__(self.message)


class ValidationFailed(AppError):
    """400 参数不合法。"""

    code = ErrorCode.VALIDATION_ERROR
    http_status = 400
    default_message = DEFAULT_MESSAGES[ErrorCode.VALIDATION_ERROR]


class Unauthenticated(AppError):
    """401 未登录。"""

    code = ErrorCode.UNAUTHENTICATED
    http_status = 401
    default_message = DEFAULT_MESSAGES[ErrorCode.UNAUTHENTICATED]


class TokenExpired(AppError):
    """401 令牌过期。"""

    code = ErrorCode.TOKEN_EXPIRED
    http_status = 401
    default_message = DEFAULT_MESSAGES[ErrorCode.TOKEN_EXPIRED]


class Forbidden(AppError):
    """403 无权限。"""

    code = ErrorCode.FORBIDDEN
    http_status = 403
    default_message = DEFAULT_MESSAGES[ErrorCode.FORBIDDEN]


class NotFound(AppError):
    """404 资源不存在（不区分是否属于当前用户，防探测）。"""

    code = ErrorCode.NOT_FOUND
    http_status = 404
    default_message = DEFAULT_MESSAGES[ErrorCode.NOT_FOUND]


class IdempotencyConflict(AppError):
    """409 幂等键冲突。"""

    code = ErrorCode.IDEMPOTENCY_CONFLICT
    http_status = 409
    default_message = DEFAULT_MESSAGES[ErrorCode.IDEMPOTENCY_CONFLICT]


class StateConflict(AppError):
    """409 状态不允许。"""

    code = ErrorCode.STATE_CONFLICT
    http_status = 409
    default_message = DEFAULT_MESSAGES[ErrorCode.STATE_CONFLICT]


class InsufficientFunds(AppError):
    """422 资金不足。"""

    code = ErrorCode.INSUFFICIENT_FUNDS
    http_status = 422
    default_message = DEFAULT_MESSAGES[ErrorCode.INSUFFICIENT_FUNDS]


class InsufficientPosition(AppError):
    """422 持仓不足。"""

    code = ErrorCode.INSUFFICIENT_POSITION
    http_status = 422
    default_message = DEFAULT_MESSAGES[ErrorCode.INSUFFICIENT_POSITION]


class InvalidOrder(AppError):
    """422 订单不合法。"""

    code = ErrorCode.INVALID_ORDER
    http_status = 422
    default_message = DEFAULT_MESSAGES[ErrorCode.INVALID_ORDER]


class DataUnavailable(AppError):
    """424 数据源不可用。"""

    code = ErrorCode.DATA_UNAVAILABLE
    http_status = 424
    default_message = DEFAULT_MESSAGES[ErrorCode.DATA_UNAVAILABLE]


class RateLimited(AppError):
    """429 限流；``details["retry_after"]`` 会转成 ``Retry-After`` 响应头。"""

    code = ErrorCode.RATE_LIMITED
    http_status = 429
    default_message = DEFAULT_MESSAGES[ErrorCode.RATE_LIMITED]


class QuotaExceeded(AppError):
    """429 配额耗尽。"""

    code = ErrorCode.QUOTA_EXCEEDED
    http_status = 429
    default_message = DEFAULT_MESSAGES[ErrorCode.QUOTA_EXCEEDED]


class LLMFailed(AppError):
    """502 AI 调用失败。"""

    code = ErrorCode.LLM_FAILED
    http_status = 502
    default_message = DEFAULT_MESSAGES[ErrorCode.LLM_FAILED]


class LLMOutputInvalid(AppError):
    """502 AI 输出未通过校验。"""

    code = ErrorCode.LLM_OUTPUT_INVALID
    http_status = 502
    default_message = DEFAULT_MESSAGES[ErrorCode.LLM_OUTPUT_INVALID]


class BudgetCircuitOpen(AppError):
    """503 AI 预算熔断。"""

    code = ErrorCode.BUDGET_CIRCUIT_OPEN
    http_status = 503
    default_message = DEFAULT_MESSAGES[ErrorCode.BUDGET_CIRCUIT_OPEN]


class InternalError(AppError):
    """500 内部错误；对外文案固定。"""

    code = ErrorCode.INTERNAL_ERROR
    http_status = 500
    default_message = DEFAULT_MESSAGES[ErrorCode.INTERNAL_ERROR]


#: Starlette HTTPException → 统一 code；未知 4xx/5xx 有兜底。
_STATUS_CODE_TO_ERROR: dict[int, ErrorCode] = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.VALIDATION_ERROR,
    409: ErrorCode.STATE_CONFLICT,
    422: ErrorCode.INVALID_ORDER,
    429: ErrorCode.RATE_LIMITED,
}


def _current_request_id() -> str | None:
    """读取 T02 的 request_id ContextVar；无请求上下文时返回 None。"""
    return request_id_var.get()


def _resolve_request_id(request: Request) -> str | None:
    """优先取 ContextVar；ServerErrorMiddleware 位于请求中间件栈之外，
    未捕获异常在 ContextVar 设置之前抛出，因此回退读取合法的请求头，
    保证 500 响应仍可追踪（与 docs/05 §1「请求追踪」一致）。
    """
    current = _current_request_id()
    if current is not None:
        return current
    candidate = request.headers.get("X-Request-ID")
    if candidate and len(candidate) <= 64 and all(0x21 <= ord(ch) <= 0x7E for ch in candidate):
        return candidate
    return None


def _payload(
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """构造统一错误响应体（不携带任何输入值或堆栈）。"""
    return {
        "error": {
            "code": code.value,
            "message": message,
            "details": details or {},
            "request_id": request_id if request_id is not None else _current_request_id(),
        }
    }


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理 AppError 及其子类。"""
    del request
    error = exc if isinstance(exc, AppError) else InternalError()
    headers: dict[str, str] | None = None
    retry_after = error.details.get("retry_after")
    if error.code is ErrorCode.RATE_LIMITED and retry_after is not None:
        headers = {"Retry-After": str(retry_after)}
    return JSONResponse(
        status_code=error.http_status,
        content=_payload(error.code, error.message, error.details),
        headers=headers,
    )


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """把 FastAPI 校验错误精简为 field/message/type，绝不回显输入值。"""
    del request
    errors: list[dict[str, str]] = []
    if isinstance(exc, RequestValidationError):
        for item in exc.errors():
            location = item.get("loc", ())
            field = ".".join(str(part) for part in location) or "body"
            errors.append(
                {
                    "field": field,
                    "message": str(item.get("msg", "")),
                    "type": str(item.get("type", "")),
                }
            )
    return JSONResponse(
        status_code=400,
        content=_payload(
            ErrorCode.VALIDATION_ERROR,
            DEFAULT_MESSAGES[ErrorCode.VALIDATION_ERROR],
            {"errors": errors},
        ),
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """404/405 等 Starlette HTTPException 统一为约定的错误格式。"""
    if not isinstance(exc, StarletteHTTPException):
        return await _app_error_handler(request, InternalError())
    status = exc.status_code
    code = _STATUS_CODE_TO_ERROR.get(
        status,
        ErrorCode.INTERNAL_ERROR if status >= 500 else ErrorCode.VALIDATION_ERROR,
    )
    return JSONResponse(
        status_code=status,
        content=_payload(code, DEFAULT_MESSAGES[code]),
        headers=getattr(exc, "headers", None),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """未捕获异常：对外固定文案，对内用 get_logger 记录完整堆栈与 request_id。"""
    logger = get_logger("app.errors")
    logger.error(
        "unhandled_exception",
        exc_info=(type(exc), exc, exc.__traceback__),
        request_id=_resolve_request_id(request),
        path=request.url.path,
        method=request.method,
        exception_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content=_payload(
            ErrorCode.INTERNAL_ERROR,
            DEFAULT_MESSAGES[ErrorCode.INTERNAL_ERROR],
            request_id=_resolve_request_id(request),
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """注册四类统一异常处理器；签名与 CONTRACTS §4 一致。"""
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
