"""M0-T05 进程内事件总线单元测试。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.events import (
    DEFAULT_HANDLER_TIMEOUT,
    Event,
    EventBus,
    get_event_bus,
    reset_event_bus,
    set_event_bus,
)
from app.core.logging import setup_logging
from app.domain.events import ReportCreated


class Pinged(Event):
    """测试用事件 A。"""

    value: int = 0


class Ponged(Event):
    """测试用事件 B（Pinged 的兄弟类）。"""


@pytest.fixture(scope="module", autouse=True)
def _configure_structlog() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user@localhost:5432/stockpilot",
        redis_url="redis://localhost:6379/0",
        secret_key="x" * 32,
    )
    setup_logging(settings)


def _recorder(log: list[str], label: str) -> Any:
    async def handler(event: Event) -> None:
        log.append(f"{label}:{type(event).__name__}")

    return handler


def test_default_timeout_is_five_seconds() -> None:
    assert DEFAULT_HANDLER_TIMEOUT == 5.0


async def test_publish_calls_handlers_in_subscription_order() -> None:
    bus = EventBus()
    order: list[str] = []
    bus.subscribe(Pinged, _recorder(order, "first"))
    bus.subscribe(Pinged, _recorder(order, "second"))
    bus.subscribe(Pinged, _recorder(order, "third"))
    await bus.publish(Pinged(value=1))
    assert order == ["first:Pinged", "second:Pinged", "third:Pinged"]


async def test_parent_subscription_receives_subclasses() -> None:
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(Event, _recorder(seen, "parent"))
    bus.subscribe(Pinged, _recorder(seen, "ping"))
    bus.subscribe(ReportCreated, _recorder(seen, "report"))

    await bus.publish(Pinged())
    await bus.publish(Ponged())
    assert seen == ["parent:Pinged", "ping:Pinged", "parent:Ponged"]


async def test_publish_with_no_subscribers_is_noop() -> None:
    bus = EventBus()
    await bus.publish(Pinged())
    assert bus._subscriptions == []


async def test_handler_exception_is_isolated_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()
    executed: list[str] = []

    async def broken(event: Event) -> None:
        raise RuntimeError("handler exploded")

    async def healthy(event: Event) -> None:
        executed.append("healthy")

    bus.subscribe(Pinged, broken)
    bus.subscribe(Pinged, healthy)
    event = Pinged()
    with caplog.at_level(logging.ERROR):
        await bus.publish(event)  # 不得向发布方抛

    assert executed == ["healthy"]
    text = caplog.text
    assert "event_handler_failed" in text
    assert "Pinged" in text
    assert "broken" in text
    assert str(event.event_id) in text
    assert "handler exploded" in text


async def test_handler_timeout_is_cancelled_and_does_not_block(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus(handler_timeout=0.02)
    executed: list[str] = []

    async def slow(event: Event) -> None:
        await asyncio.sleep(1.0)

    async def after(event: Event) -> None:
        executed.append("after")

    bus.subscribe(Pinged, slow)
    bus.subscribe(Pinged, after)
    with caplog.at_level(logging.WARNING):
        await bus.publish(Pinged())

    assert executed == ["after"]
    text = caplog.text
    assert "event_handler_timeout" in text
    assert "slow" in text
    assert "Pinged" in text


async def test_duplicate_subscribe_is_idempotent_and_unsubscribe_is_safe() -> None:
    bus = EventBus()
    calls: list[str] = []
    handler = _recorder(calls, "once")
    bus.subscribe(Pinged, handler)
    bus.subscribe(Pinged, handler)
    await bus.publish(Pinged())
    assert calls == ["once:Pinged"]

    bus.unsubscribe(Pinged, handler)
    bus.unsubscribe(Pinged, handler)  # 不存在不报错
    bus.unsubscribe(Ponged, handler)  # 从未订阅过不报错
    await bus.publish(Pinged())
    assert calls == ["once:Pinged"]


async def test_subscription_sequence_is_global_across_types() -> None:
    bus = EventBus()
    order: list[str] = []
    bus.subscribe(Pinged, _recorder(order, "second"))
    bus.subscribe(Event, _recorder(order, "first"))
    await bus.publish(Pinged())
    # 后订阅的父类处理器仍排在先订阅的子类处理器之后：按全局订阅顺序，
    # 而不是先按事件类型分组。
    assert order == ["second:Pinged", "first:Pinged"]


def test_event_is_immutable_and_has_utc_timestamp() -> None:
    first = Pinged()
    second = Pinged()
    assert first.event_id != second.event_id
    assert first.occurred_at.tzinfo is not None
    offset = first.occurred_at.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0
    frozen_field = "value"
    with pytest.raises(ValidationError):
        setattr(first, frozen_field, 10)
    with pytest.raises(ValidationError):
        Pinged.model_validate({"unexpected": 1})


async def test_concurrent_publish_does_not_interfere() -> None:
    bus = EventBus()
    calls: list[str] = []

    async def handler(event: Event) -> None:
        await asyncio.sleep(0)
        calls.append(str(event.event_id))

    bus.subscribe(Pinged, handler)
    events = [Pinged() for _ in range(12)]
    await asyncio.gather(*(bus.publish(event) for event in events))
    assert set(calls) == {str(event.event_id) for event in events}
    assert len(calls) == 12


def test_get_set_reset_event_bus() -> None:
    reset_event_bus()
    default = get_event_bus()
    assert get_event_bus() is default

    replacement = EventBus(handler_timeout=0.5)
    set_event_bus(replacement)
    assert get_event_bus() is replacement
    assert replacement._handler_timeout == 0.5

    reset_event_bus()
    assert get_event_bus() is not default


def test_handler_name_fallback_for_callable_objects() -> None:
    class CallableHandler:
        async def __call__(self, event: Event) -> None:
            raise RuntimeError("boom")

    from app.core.events import _handler_name

    handler = CallableHandler()
    name = _handler_name(handler)
    assert "CallableHandler" in name
