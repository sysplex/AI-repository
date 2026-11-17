"""提醒规则评估器导出与工厂方法（M10-T03）。"""

from __future__ import annotations

from app.modules.notify.enums import AlertType
from app.modules.notify.evaluators.base import BaseAlertEvaluator, EvaluationResult
from app.modules.notify.evaluators.earnings_evaluator import EarningsDateEvaluator
from app.modules.notify.evaluators.price_evaluator import PriceAlertEvaluator
from app.modules.notify.evaluators.technical_evaluator import TechnicalSignalEvaluator
from app.modules.notify.evaluators.thesis_breaker_evaluator import ThesisBreakerEvaluator

__all__ = [
    "BaseAlertEvaluator",
    "EarningsDateEvaluator",
    "EvaluationResult",
    "PriceAlertEvaluator",
    "TechnicalSignalEvaluator",
    "ThesisBreakerEvaluator",
    "get_evaluator",
]

_EVALUATORS: dict[AlertType, BaseAlertEvaluator] = {
    AlertType.PRICE: PriceAlertEvaluator(),
    AlertType.TECHNICAL_SIGNAL: TechnicalSignalEvaluator(),
    AlertType.EARNINGS_DATE: EarningsDateEvaluator(),
    AlertType.THESIS_BREAKER: ThesisBreakerEvaluator(),
}


def get_evaluator(alert_type: AlertType | str) -> BaseAlertEvaluator | None:
    """根据 AlertType 获取对应的评估器实例。"""
    if isinstance(alert_type, str):
        try:
            alert_type = AlertType(alert_type)
        except ValueError:
            return None
    return _EVALUATORS.get(alert_type)
