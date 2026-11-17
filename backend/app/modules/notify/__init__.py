"""M10 Notify 模块：通知分发网关与智能提醒监控（T01, T02, T03）。"""

from __future__ import annotations

from app.modules.notify.adapters.email_notifier import EmailNotifier
from app.modules.notify.adapters.in_app_notifier import InAppNotifier
from app.modules.notify.adapters.webhook_notifier import WebhookNotifier
from app.modules.notify.dispatcher import NotificationDispatcher
from app.modules.notify.enums import (
    AlertStatus,
    AlertType,
    ChannelType,
    ComparisonOperator,
    DeliveryStatus,
    PriceDirection,
)
from app.modules.notify.evaluators import (
    BaseAlertEvaluator,
    EarningsDateEvaluator,
    EvaluationResult,
    PriceAlertEvaluator,
    TechnicalSignalEvaluator,
    ThesisBreakerEvaluator,
    get_evaluator,
)
from app.modules.notify.models import (
    Alert,
    AlertHistory,
    NotificationChannel,
)
from app.modules.notify.ports import (
    BaseNotifier,
    NotificationMessage,
    NotificationResult,
)
from app.modules.notify.schemas import (
    AlertCreate,
    AlertHistoryRead,
    AlertRead,
    AlertUpdate,
    EarningsDateCondition,
    NotificationChannelCreate,
    NotificationChannelRead,
    NotificationChannelUpdate,
    PriceCondition,
    TechnicalSignalCondition,
    ThesisBreakerCondition,
)
from app.modules.notify.service import AlertService

__all__ = [
    "Alert",
    "AlertCreate",
    "AlertHistory",
    "AlertHistoryRead",
    "AlertRead",
    "AlertService",
    "AlertStatus",
    "AlertType",
    "AlertUpdate",
    "BaseAlertEvaluator",
    "BaseNotifier",
    "ChannelType",
    "ComparisonOperator",
    "DeliveryStatus",
    "EarningsDateCondition",
    "EarningsDateEvaluator",
    "EmailNotifier",
    "EvaluationResult",
    "InAppNotifier",
    "NotificationChannel",
    "NotificationChannelCreate",
    "NotificationChannelRead",
    "NotificationChannelUpdate",
    "NotificationDispatcher",
    "NotificationMessage",
    "NotificationResult",
    "PriceAlertEvaluator",
    "PriceCondition",
    "PriceDirection",
    "TechnicalSignalCondition",
    "TechnicalSignalEvaluator",
    "ThesisBreakerCondition",
    "ThesisBreakerEvaluator",
    "WebhookNotifier",
    "get_evaluator",
]
