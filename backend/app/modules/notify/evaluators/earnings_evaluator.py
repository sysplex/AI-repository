"""财报日倒计时提醒评估器（M10-T03）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.modules.notify.evaluators.base import BaseAlertEvaluator, EvaluationResult
from app.modules.notify.models import Alert

__all__ = ["EarningsDateEvaluator"]


def _to_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        try:
            return datetime.strptime(val.strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


class EarningsDateEvaluator(BaseAlertEvaluator):
    """评估财报日倒计时规则。"""

    def evaluate(self, alert: Alert, context: dict[str, Any]) -> EvaluationResult:
        conditions = alert.conditions or {}
        days_before = int(conditions.get("days_before", 1))

        raw_earnings_date = (
            context.get("earnings_date")
            or context.get("next_earnings_date")
            or conditions.get("earnings_date")
        )
        earnings_date = _to_date(raw_earnings_date)
        if earnings_date is None:
            return EvaluationResult(triggered=False)

        raw_current_date = (
            context.get("as_of_date") or context.get("current_date") or context.get("today")
        )
        current_date = _to_date(raw_current_date) or date.today()

        days_remaining = (earnings_date - current_date).days

        # 触发区间：0 <= days_remaining <= days_before
        if not (0 <= days_remaining <= days_before):
            return EvaluationResult(triggered=False)

        symbol = alert.symbol or context.get("symbol") or "标的"
        date_str = earnings_date.isoformat()

        if days_remaining == 0:
            message = (
                f"[{symbol}] 财报发布日预警：将于今日公布最新季度财报，"
                f"请密切关注业绩表现与持仓风险。"
            )
        else:
            message = (
                f"[{symbol}] 财报发布日临近：将于 {days_remaining} 天后（{date_str}）"
                f"公布最新季度财报，请注意持仓波动与风险。"
            )

        triggered_value = {
            "symbol": symbol,
            "earnings_date": date_str,
            "current_date": current_date.isoformat(),
            "days_remaining": days_remaining,
            "days_before": days_before,
        }
        return EvaluationResult(
            triggered=True,
            message=message,
            triggered_value=triggered_value,
        )
