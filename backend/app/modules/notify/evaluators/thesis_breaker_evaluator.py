"""长期持有投资论文破裂提醒评估器（M10-T03）。

对齐 M7 F5 的 `thesis_breakers` 结构化规范与可监控点分路径。
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.modules.notify.enums import ComparisonOperator
from app.modules.notify.evaluators.base import BaseAlertEvaluator, EvaluationResult
from app.modules.notify.models import Alert

__all__ = ["ThesisBreakerEvaluator"]


def _to_decimal(val: Any) -> Decimal | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, Decimal):
        return val
    try:
        cleaned = str(val).replace("%", "").replace(",", "").replace("$", "").strip()
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


def _parse_threshold_string(raw: str) -> tuple[ComparisonOperator | None, Decimal | None]:
    """从类似 '< 0.15'、'<= 40%'、'45.0' 中解析操作符与阈值。"""
    raw = raw.strip()
    match = re.match(r"^([<>!=]=?|[a-zA-Z]+)?\s*([+-]?\d+(?:\.\d+)?%?)$", raw)
    if not match:
        return None, None
    op_part, val_part = match.groups()
    op = _normalize_operator(op_part) if op_part else None
    val = _to_decimal(val_part)
    return op, val


def _resolve_data_field(context: dict[str, Any], field_path: str) -> Any:
    """根据点分路径从 context 中深度解析数值。"""
    if field_path in context:
        return context[field_path]

    parts = field_path.split(".")
    current: Any = context
    for p in parts:
        if isinstance(current, dict) and p in current:
            current = current[p]
        else:
            return None
    return current


class ThesisBreakerEvaluator(BaseAlertEvaluator):
    """评估长期持有论文破裂条件（对齐 M7 ThesisEvaluation 规格）。"""

    def evaluate(self, alert: Alert, context: dict[str, Any]) -> EvaluationResult:
        conditions = alert.conditions or {}

        metric = conditions.get("metric") or alert.title
        data_field = conditions.get("data_field") or (f"fundamentals.{metric}" if metric else None)
        desc = conditions.get("description") or alert.title

        # 解析 operator 与 threshold
        raw_op = conditions.get("operator")
        raw_threshold = conditions.get("threshold")

        op = _normalize_operator(raw_op)
        threshold = _to_decimal(raw_threshold)

        # 兼容 threshold 形如 "< 0.15" 的复合字符串
        if (op is None or threshold is None) and isinstance(raw_threshold, str):
            parsed_op, parsed_val = _parse_threshold_string(raw_threshold)
            if op is None:
                op = parsed_op
            if threshold is None:
                threshold = parsed_val

        # 若依然无法确定操作符与阈值，判定无法求值
        if op is None or threshold is None:
            return EvaluationResult(triggered=False)

        # 从 context 解析实际指标值
        actual_raw: Any = None
        if data_field:
            actual_raw = _resolve_data_field(context, data_field)

        if actual_raw is None and metric:
            # 回退尝试直接从 context 或 context["fundamentals"] 寻找
            actual_raw = context.get(metric)
            if actual_raw is None and isinstance(context.get("fundamentals"), dict):
                actual_raw = context["fundamentals"].get(metric)
            if actual_raw is None and isinstance(context.get("quote"), dict):
                actual_raw = context["quote"].get(metric)

        actual_val = _to_decimal(actual_raw)
        if actual_val is None:
            return EvaluationResult(triggered=False)

        # 进行比较
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

        reason_header = f"[{symbol}] 长期投资论文破裂预警"
        if desc and str(desc).strip() and str(desc).strip() != str(metric):
            body_text = f"：{desc}（实际值: {actual_val:g}，破裂阈值: {op_sym} {threshold:g}）"
        else:
            body_text = (
                f"：指标 {metric} 触发破裂条件"
                f"（实际值: {actual_val:g}，破裂阈值: {op_sym} {threshold:g}）"
            )

        message = f"{reason_header}{body_text}"
        triggered_value = {
            "symbol": symbol,
            "metric": str(metric),
            "data_field": str(data_field) if data_field else None,
            "operator": op.value,
            "threshold": str(threshold),
            "actual_value": str(actual_val),
            "description": str(desc) if desc else None,
        }
        return EvaluationResult(
            triggered=True,
            message=message,
            triggered_value=triggered_value,
        )
