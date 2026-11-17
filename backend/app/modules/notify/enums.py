"""Notify 领域枚举定义（M10-T01），`CONTRACTS.md §3`。"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "AlertStatus",
    "AlertType",
    "ChannelType",
    "ComparisonOperator",
    "DeliveryStatus",
    "PriceDirection",
]


class ChannelType(StrEnum):
    """通知渠道类型。"""

    EMAIL = "email"
    WEBHOOK = "webhook"
    IN_APP = "in_app"


class AlertType(StrEnum):
    """提醒规则类型。"""

    PRICE = "price"
    TECHNICAL_SIGNAL = "technical_signal"
    EARNINGS_DATE = "earnings_date"
    THESIS_BREAKER = "thesis_breaker"


class AlertStatus(StrEnum):
    """提醒规则状态。"""

    ACTIVE = "active"
    TRIGGERED = "triggered"
    DISABLED = "disabled"
    COOLDOWN = "cooldown"


class PriceDirection(StrEnum):
    """价格突破方向。"""

    CROSS_ABOVE = "cross_above"
    CROSS_BELOW = "cross_below"


class ComparisonOperator(StrEnum):
    """数值比较操作符（用于论文破裂和指标判定）。"""

    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    EQ = "eq"


class DeliveryStatus(StrEnum):
    """通知投递状态。"""

    PENDING = "pending"
    SENT = "sent"
    PARTIAL = "partial"
    FAILED = "failed"
