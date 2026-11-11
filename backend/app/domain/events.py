"""首批领域事件（M0 / T05），`CONTRACTS.md §6`。

均继承冻结的 `Event`；`Decimal` 在 `model_dump(mode="json")` 下输出字符串，
避免浮点误差，符合 docs/07 §5「金额用 Decimal」。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from app.core.events import Event

__all__ = ["OrderFilled", "ReportCreated", "SignalTriggered"]


class OrderFilled(Event):
    """模拟盘订单成交。"""

    account_id: UUID
    order_id: UUID
    symbol: str
    side: str
    qty: Decimal
    price: Decimal


class ReportCreated(Event):
    """AI 报告生成完成。"""

    report_id: UUID
    user_id: UUID
    use_case: str
    symbols: list[str]


class SignalTriggered(Event):
    """策略信号触发。"""

    strategy_id: str
    symbol: str
    as_of: date
    direction: str
    strength: int
