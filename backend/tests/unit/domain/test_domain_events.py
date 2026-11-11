"""M0-T05 领域事件模型与 JSON 序列化测试。"""

from __future__ import annotations

from datetime import UTC, date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.core.events import Event
from app.domain.events import OrderFilled, ReportCreated, SignalTriggered


def test_order_filled_json_serialization() -> None:
    account_id = uuid4()
    order_id = uuid4()
    event = OrderFilled(
        account_id=account_id,
        order_id=order_id,
        symbol="AAPL",
        side="buy",
        qty=Decimal("10"),
        price=Decimal("180.50"),
    )
    payload = event.model_dump(mode="json")
    assert payload["account_id"] == str(account_id)
    assert payload["order_id"] == str(order_id)
    assert payload["qty"] == "10"
    assert payload["price"] == "180.50"
    assert isinstance(payload["qty"], str)
    assert isinstance(payload["price"], str)
    assert isinstance(payload["event_id"], str)
    assert isinstance(payload["occurred_at"], str)
    assert payload["occurred_at"].endswith("Z") or "+00:00" in payload["occurred_at"]

    python_mode = event.model_dump(mode="python")
    assert isinstance(python_mode["qty"], Decimal)
    assert isinstance(python_mode["event_id"], UUID)


def test_report_created_json_serialization() -> None:
    report_id = uuid4()
    user_id = uuid4()
    event = ReportCreated(
        report_id=report_id,
        user_id=user_id,
        use_case="compare",
        symbols=["AAPL", "MSFT"],
    )
    payload = event.model_dump(mode="json")
    assert payload["report_id"] == str(report_id)
    assert payload["user_id"] == str(user_id)
    assert payload["symbols"] == ["AAPL", "MSFT"]
    assert payload["use_case"] == "compare"


def test_signal_triggered_json_serialization() -> None:
    event = SignalTriggered(
        strategy_id="ma-cross",
        symbol="SPY",
        as_of=date(2026, 11, 11),
        direction="long",
        strength=3,
    )
    payload = event.model_dump(mode="json")
    assert payload["as_of"] == "2026-11-11"
    assert payload["strength"] == 3
    assert payload["strategy_id"] == "ma-cross"
    assert isinstance(event.as_of, date)


@pytest.mark.parametrize(
    ("event_cls", "kwargs"),
    [
        (
            OrderFilled,
            {
                "account_id": uuid4(),
                "order_id": uuid4(),
                "symbol": "AAPL",
                "side": "buy",
                "qty": Decimal("1"),
                "price": Decimal("2"),
            },
        ),
        (
            ReportCreated,
            {"report_id": uuid4(), "user_id": uuid4(), "use_case": "research", "symbols": ["AAPL"]},
        ),
        (
            SignalTriggered,
            {
                "strategy_id": "s",
                "symbol": "SPY",
                "as_of": date(2026, 1, 2),
                "direction": "long",
                "strength": 1,
            },
        ),
    ],
)
def test_domain_events_are_frozen_and_inherit_event(
    event_cls: type[Event], kwargs: dict[str, object]
) -> None:
    event = event_cls.model_validate(kwargs)
    assert issubclass(event_cls, Event)
    assert event.event_id.version == 4
    assert event.occurred_at.tzinfo is not None
    offset = event.occurred_at.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0
    frozen_field = "event_id"
    with pytest.raises(ValidationError):
        setattr(event, frozen_field, uuid4())

    dumped = event.model_dump(mode="json")
    assert set(dumped) == set(event_cls.model_fields)


def test_explicit_event_fields_are_preserved() -> None:
    fixed_id = uuid4()
    fixed_time = "2026-11-11T14:30:00Z"
    event = PingedDomain(event_id=fixed_id, occurred_at=fixed_time)
    assert event.event_id == fixed_id
    assert event.occurred_at.tzinfo == UTC


class PingedDomain(Event):
    """仅用于验证显式传入基类字段。"""
