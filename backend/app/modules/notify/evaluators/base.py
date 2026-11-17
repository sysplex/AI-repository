"""提醒规则评估基类与数据结构（M10-T03）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.modules.notify.models import Alert

__all__ = [
    "BaseAlertEvaluator",
    "EvaluationResult",
]


@dataclass(frozen=True)
class EvaluationResult:
    """单个提醒规则评估结果。"""

    triggered: bool
    message: str = ""
    triggered_value: dict[str, Any] = field(default_factory=dict)


class BaseAlertEvaluator(ABC):
    """提醒规则评估器抽象基类。"""

    @abstractmethod
    def evaluate(self, alert: Alert, context: dict[str, Any]) -> EvaluationResult:
        """评估规则是否触发。

        Args:
            alert: 数据库中待评估的 Alert 实体。
            context: 评估上下文（包含行情最新价、前值、指标、基本面、财报日期等）。

        Returns:
            EvaluationResult: 评估判定结果。
        """
        raise NotImplementedError
