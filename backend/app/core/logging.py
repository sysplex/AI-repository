"""结构化日志与请求上下文（M0 / T02），`CONTRACTS.md §3`。

`c4b30e8` 澄清要求保留两个公开签名：`setup_logging(settings)` 与
`get_logger(name=None)`；T02 把后者改为返回 structlog BoundLogger。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

import structlog
from structlog.typing import EventDict

if TYPE_CHECKING:
    from app.core.config import Settings

__all__ = [
    "get_logger",
    "request_id_var",
    "setup_logging",
    "task_id_var",
    "user_id_var",
]

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
task_id_var: ContextVar[str | None] = ContextVar("task_id", default=None)

_HANDLER_FLAG = "_stockpilot_structlog_handler"
_BRIDGED_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "sqlalchemy.engine",
    "arq",
)


def _add_context_vars(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """把三个 ContextVar 的值并入每条日志（有值才带，见 CONTRACTS §3）。"""
    del logger, method_name
    for key, var in (
        ("request_id", request_id_var),
        ("user_id", user_id_var),
        ("task_id", task_id_var),
    ):
        value = var.get()
        if value is not None:
            event_dict[key] = value
    return event_dict


def _shared_processors() -> list[Any]:
    return [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_context_vars,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]


def setup_logging(settings: Settings) -> None:
    """配置 structlog + 标准库桥接；可重复调用（幂等，不叠加 handler）。"""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer()
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_shared_processors(),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    setattr(handler, _HANDLER_FLAG, True)

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _HANDLER_FLAG, False):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # 让 uvicorn / sqlalchemy / arq 的记录也走同一个 root handler 与格式。
    for name in _BRIDGED_LOGGERS:
        external = logging.getLogger(name)
        external.propagate = True
        for existing in list(external.handlers):
            external.removeHandler(existing)

    structlog.configure(
        processors=[
            *_shared_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """返回 structlog 绑定 logger；签名与 `CONTRACTS.md §3` 一致。"""
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))
