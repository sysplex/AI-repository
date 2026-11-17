"""技术指标信号提醒评估器（M10-T03）。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.modules.notify.enums import ComparisonOperator
from app.modules.notify.evaluators.base import BaseAlertEvaluator, EvaluationResult
from app.modules.notify.models import Alert

__all__ = ["TechnicalSignalEvaluator"]


def _to_decimal(val: Any) -> Decimal | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, Decimal):
        return val
    try:
        cleaned = str(val).replace("%", "").replace(",", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError, TypeError):
        return None


def _normalize_operator(op: Any) -> ComparisonOperator | None:
    if isinstance(op, ComparisonOperator):
        return op
    if not op:
        return None
    normalized = str(op).strip().lower()
    mapping = {
        "<": ComparisonOperator.LT,
        "lt": ComparisonOperator.LT,
        "<=": ComparisonOperator.LTE,
        "lte": ComparisonOperator.LTE,
        ">": ComparisonOperator.GT,
        "gt": ComparisonOperator.GT,
        ">=": ComparisonOperator.GTE,
        "gte": ComparisonOperator.GTE,
        "==": ComparisonOperator.EQ,
        "=": ComparisonOperator.EQ,
        "eq": ComparisonOperator.EQ,
    }
    return mapping.get(normalized)


class TechnicalSignalEvaluator(BaseAlertEvaluator):
    """评估技术指标信号规则（如 RSI 超买超卖、均线交叉与阈值）。"""

    def evaluate(self, alert: Alert, context: dict[str, Any]) -> EvaluationResult:
        conditions = alert.conditions or {}
        indicator = conditions.get("indicator")
        if not indicator or not str(indicator).strip():
            return EvaluationResult(triggered=False)

        indicator_key = str(indicator).strip()
        op = _normalize_operator(conditions.get("operator"))
        threshold = _to_decimal(conditions.get("threshold"))

        if op is None or threshold is None:
            return EvaluationResult(triggered=False)

        # 尝试从 context 中检索指标实际值：
        # 1. context.get("indicator_value")
        # 2. context.get("indicators", {}).get(...)
        # 3. context.get(...)
        actual_val = None
        if "indicator_value" in context:
            actual_val = _to_decimal(context["indicator_value"])

        if actual_val is None:
            indicators_map = context.get("indicators")
            if isinstance(indicators_map, dict):
                actual_val = (
                    _to_decimal(indicators_map.get(indicator_key))
                    or _to_decimal(indicators_map.get(indicator_key.upper()))
                    or _to_decimal(indicators_map.get(indicator_key.lower()))
                )

        if actual_val is None:
            actual_val = (
                _to_decimal(context.get(indicator_key))
                or _to_decimal(context.get(indicator_key.upper()))
                or _to_decimal(context.get(indicator_key.lower()))
            )

        if actual_val is None:
            return EvaluationResult(triggered=False)

        # 进行操作符比较
        triggered = False
        if op == ComparisonOperator.LT:
            triggered = actual_val < threshold
        elif op == ComparisonOperator.LTE:
            triggered = actual_val <= threshold
        elif op == ComparisonOperator.GT:
            triggered = actual_val > threshold
        elif op == ComparisonOperator.GTE:
            triggered = actual_val >= threshold
        elif op == ComparisonOperator.EQ:
            triggered = actual_val == threshold

        if not triggered:
            return EvaluationResult(triggered=False)

        symbol = alert.symbol or context.get("symbol") or "标的"
        op_symbol_map = {
            ComparisonOperator.LT: "<",
            ComparisonOperator.LTE: "<=",
            ComparisonOperator.GT: ">",
            ComparisonOperator.GTE: ">=",
            ComparisonOperator.EQ: "==",
        }
        op_sym = op_symbol_map.get(op, op.value)
        message = (
            f"[{symbol}] 技术指标 {indicator_key} 触发预警："
            f"当前值 {actual_val:g} {op_sym} 阈值 {threshold:g}"
        )
        triggered_value = {
            "symbol": symbol,
            "indicator": indicator_key,
            "operator": op.value,
            "threshold": str(threshold),
            "actual_value": str(actual_val),
        }
        return EvaluationResult(
            triggered=True,
            message=message,
            triggered_value=triggered_value,
        )
