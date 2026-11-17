"""价格突破提醒评估器（M10-T03）。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.modules.notify.enums import PriceDirection
from app.modules.notify.evaluators.base import BaseAlertEvaluator, EvaluationResult
from app.modules.notify.models import Alert

__all__ = ["PriceAlertEvaluator"]


def _to_decimal(val: Any) -> Decimal | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, Decimal):
        return val
    try:
        cleaned = str(val).replace("$", "").replace(",", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError, TypeError):
        return None


class PriceAlertEvaluator(BaseAlertEvaluator):
    """评估价格突破规则（cross_above / cross_below）。"""

    def evaluate(self, alert: Alert, context: dict[str, Any]) -> EvaluationResult:
        conditions = alert.conditions or {}
        raw_direction = conditions.get("direction")
        raw_target = conditions.get("target_price")

        target_price = _to_decimal(raw_target)
        if target_price is None or target_price <= 0:
            return EvaluationResult(triggered=False)

        direction = (
            raw_direction.value if isinstance(raw_direction, PriceDirection) else str(raw_direction)
        )

        # 从 context 提取当前价与前值
        current_price = _to_decimal(
            context.get("current_price") or context.get("price") or context.get("close")
        )
        if current_price is None:
            return EvaluationResult(triggered=False)

        previous_price = _to_decimal(context.get("previous_price") or context.get("prev_close"))

        symbol = alert.symbol or context.get("symbol") or "标的"

        triggered = False
        if direction == PriceDirection.CROSS_ABOVE.value:
            if previous_price is not None:
                triggered = previous_price < target_price <= current_price
            else:
                triggered = current_price >= target_price
            action_desc = "向上突破"
        elif direction == PriceDirection.CROSS_BELOW.value:
            if previous_price is not None:
                triggered = previous_price > target_price >= current_price
            else:
                triggered = current_price <= target_price
            action_desc = "向下跌破"
        else:
            return EvaluationResult(triggered=False)

        if not triggered:
            return EvaluationResult(triggered=False)

        message = (
            f"[{symbol}] 股价{action_desc}目标价 ${target_price:g}（当前价: ${current_price:g}）"
        )
        triggered_value = {
            "symbol": symbol,
            "direction": direction,
            "target_price": str(target_price),
            "current_price": str(current_price),
            "previous_price": str(previous_price) if previous_price is not None else None,
        }
        return EvaluationResult(
            triggered=True,
            message=message,
            triggered_value=triggered_value,
        )
