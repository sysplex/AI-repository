"""进程内事件总线（M0 / T05），`CONTRACTS.md §6`。

- 事件是冻结的 pydantic 模型，带 UUID 与 UTC 时间戳
- 订阅父类可收到子类事件；处理器按全局订阅顺序串行 await
- 单个处理器异常 / 超时被隔离并记录日志，不影响其它处理器与发布方
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_logger

__all__ = [
    "Event",
    "EventBus",
    "EventHandler",
    "get_event_bus",
    "reset_event_bus",
    "set_event_bus",
]

DEFAULT_HANDLER_TIMEOUT = 5.0

E = TypeVar("E", bound="Event")
EventHandler = Callable[[E], Awaitable[None]]


class Event(BaseModel):
    """冻结的事件基类；默认生成 event_id 与带 UTC 时区的 occurred_at。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class _Subscription:
    """一条订阅；seq 保证跨事件类型的全局订阅顺序。"""

    sequence: int
    event_type: type[Event]
    handler: EventHandler[Any]
    name: str


def _handler_name(handler: EventHandler[Any]) -> str:
    qualname = getattr(handler, "__qualname__", None)
    if isinstance(qualname, str):
        return qualname
    name = getattr(handler, "__name__", None)
    return name if isinstance(name, str) else repr(handler)


class EventBus:
    """类型安全、错误隔离的进程内异步事件总线。"""

    def __init__(self, handler_timeout: float = DEFAULT_HANDLER_TIMEOUT) -> None:
        self._handler_timeout = handler_timeout
        self._subscriptions: list[_Subscription] = []
        self._sequence = 0

    def subscribe(self, event_type: type[E], handler: EventHandler[E]) -> None:
        """订阅某事件类型（含其子类）；同一 (类型, 处理器) 重复订阅忽略。"""
        for existing in self._subscriptions:
            if existing.event_type is event_type and existing.handler is handler:
                return
        self._subscriptions.append(
            _Subscription(
                sequence=self._sequence,
                event_type=event_type,
                handler=handler,
                name=_handler_name(handler),
            )
        )
        self._sequence += 1

    def unsubscribe(self, event_type: type[E], handler: EventHandler[E]) -> None:
        """取消订阅；不存在的订阅静默忽略。"""
        self._subscriptions = [
            entry
            for entry in self._subscriptions
            if not (entry.event_type is event_type and entry.handler is handler)
        ]

    async def publish(self, event: Event) -> None:
        """按订阅顺序串行 await；异常与超时被隔离，publish 永不向发布方抛。"""
        subscribers = [
            entry for entry in self._subscriptions if isinstance(event, entry.event_type)
        ]
        logger = get_logger("app.events")
        for entry in subscribers:
            try:
                await asyncio.wait_for(entry.handler(event), timeout=self._handler_timeout)
            except TimeoutError:
                logger.warning(
                    "event_handler_timeout",
                    event_type=type(event).__name__,
                    handler=entry.name,
                    event_id=str(event.event_id),
                    timeout_seconds=self._handler_timeout,
                )
            except Exception:
                logger.error(
                    "event_handler_failed",
                    event_type=type(event).__name__,
                    handler=entry.name,
                    event_id=str(event.event_id),
                    exc_info=True,
                )


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """进程内单例；测试可用 set_event_bus / reset_event_bus 替换。"""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def set_event_bus(bus: EventBus) -> None:
    """替换进程内单例（供 T10 的 event_bus fixture 提供干净实例）。"""
    global _bus
    _bus = bus


def reset_event_bus() -> None:
    """恢复默认单例；测试结束后调用，避免串扰。"""
    global _bus
    _bus = None
