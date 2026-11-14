"""M6 AI 研究用例代码量化派生引擎，`CONTRACTS.md §3`。

实现严格由代码确定的量化指标衍生与交易计划计算：
- ``compute_target_vs_price_pct``：想买价相对现价偏差率计算
- ``compute_pos_in_52w_range``：52周价格区间位置计算（含高低点相等保护与 clamp）
- ``compute_technical_trade_plan``：确定性交易计划生成（入场、止损、目标、盈亏比）
- ``QuantitativeEngine``：实现 ``QuantitativeEngineProtocol`` 的引擎类
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.modules.research.exceptions import (
    InvalidParameterError,
    QuantitativeCalculationError,
)

__all__ = [
    "QuantitativeEngine",
    "compute_pos_in_52w_range",
    "compute_target_vs_price_pct",
    "compute_technical_trade_plan",
]

_TWO_PLACES = Decimal("0.01")
_ZERO = Decimal("0.00")
_ONE = Decimal("1.00")
_HALF = Decimal("0.50")


def _to_decimal(val: Decimal | float | int | str, name: str) -> Decimal:
    """把输入数值安全转换为 Decimal。"""
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except Exception as exc:
        raise InvalidParameterError(
            f"Invalid numeric value for {name}: {val}",
            details={"parameter": name, "value": str(val)},
        ) from exc


def compute_target_vs_price_pct(
    current_price: Decimal | float | int | str,
    target_price: Decimal | float | int | str,
) -> Decimal:
    """计算想买价相对现价偏差率百分比。

    公式：((target_price - current_price) / current_price) * 100
    结果保留 2 位小数 Decimal（ROUND_HALF_UP）。

    Args:
        current_price: 当前市场价格（必须 > 0）。
        target_price: 计划买入价格（必须 > 0）。

    Returns:
        Decimal: 相对偏差率百分比，正数代表计划价高于现价，负数代表计划价低于现价。

    Raises:
        InvalidParameterError: 当价格 <= 0 或无效时。
    """
    cur = _to_decimal(current_price, "current_price")
    tgt = _to_decimal(target_price, "target_price")

    if cur <= _ZERO:
        raise InvalidParameterError(
            "Current price must be positive",
            details={"current_price": str(cur)},
        )
    if tgt <= _ZERO:
        raise InvalidParameterError(
            "Target price must be positive",
            details={"target_price": str(tgt)},
        )

    diff = tgt - cur
    pct = (diff / cur) * Decimal("100")
    return pct.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def compute_pos_in_52w_range(
    current_price: Decimal | float | int | str,
    low_52w: Decimal | float | int | str,
    high_52w: Decimal | float | int | str,
) -> Decimal:
    """计算当前价格在 52 周区间内的相对位置（0.00 ~ 1.00）。

    公式：(current_price - low_52w) / (high_52w - low_52w)
    结果 clamp 在 [0.00, 1.00]，保留 2 位小数。

    边界与极值保护：
    - 若价格为负，抛出 InvalidParameterError；
    - 若 high_52w < low_52w，自动对调保护；
    - 若 high_52w == low_52w，返回 Decimal("0.50")；
    - 若 current_price <= low_52w，返回 Decimal("0.00")；
    - 若 current_price >= high_52w，返回 Decimal("1.00")。

    Args:
        current_price: 当前价格。
        low_52w: 52周最低价。
        high_52w: 52周最高价。

    Returns:
        Decimal: 0.00 至 1.00 之间的 Decimal。
    """
    cur = _to_decimal(current_price, "current_price")
    low = _to_decimal(low_52w, "low_52w")
    high = _to_decimal(high_52w, "high_52w")

    if cur < _ZERO or low < _ZERO or high < _ZERO:
        raise InvalidParameterError(
            "Prices cannot be negative",
            details={"current_price": str(cur), "low_52w": str(low), "high_52w": str(high)},
        )

    if high < low:
        low, high = high, low

    spread = high - low
    if spread == _ZERO:
        return _HALF

    if cur <= low:
        return _ZERO
    if cur >= high:
        return _ONE

    pos = (cur - low) / spread
    clamped = min(max(pos, _ZERO), _ONE)
    return clamped.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def compute_technical_trade_plan(
    current_price: Decimal | float | int | str,
    support: Decimal | float | int | str,
    resistance: Decimal | float | int | str,
    atr: Decimal | float | int | str,
) -> dict[str, Decimal]:
    """确定性生成技术面量化交易计划（入场、止损、目标、盈亏比）。

    公式（CONTRACTS.md §3）：
    - entry = current_price
    - raw_stop = max(support * Decimal("0.98"), entry - atr * Decimal("1.5"))
      确保 stop < entry，若异常则强制兜底为 entry - atr * 1.5 或 entry * 0.98；
      确保 stop > 0；
    - raw_target = min(resistance, entry + atr * Decimal("3.0"))
      确保 target > entry，若异常则强制兜底为 entry + atr * 3.0 或 entry * 1.05；
    - risk_reward = (target - entry) / (entry - stop)

    所有数值统一保留 2 位小数 Decimal（ROUND_HALF_UP）。

    Args:
        current_price: 当前现价（必须 > 0）。
        support: 支撑位。
        resistance: 阻力位。
        atr: 真实波幅均值（ATR，>= 0）。

    Returns:
        dict[str, Decimal]: 包含 entry, stop, target, risk_reward 的字典。

    Raises:
        InvalidParameterError: 当入参无效或价格 <= 0。
        QuantitativeCalculationError: 当交易计划计算产生不可恢复异常。
    """
    cur = _to_decimal(current_price, "current_price")
    supp = _to_decimal(support, "support")
    res = _to_decimal(resistance, "resistance")
    a = _to_decimal(atr, "atr")

    if cur <= _ZERO:
        raise InvalidParameterError(
            "Current price must be positive",
            details={"current_price": str(cur)},
        )
    if a < _ZERO:
        raise InvalidParameterError(
            "ATR cannot be negative",
            details={"atr": str(a)},
        )

    # 兜底支撑与阻力
    if supp <= _ZERO:
        supp = cur * Decimal("0.95")
    if res <= _ZERO:
        res = cur * Decimal("1.05")
    if a == _ZERO:
        a = cur * Decimal("0.02")

    entry = cur

    # 计算止损位（严保 stop < entry）
    stop_candidate = max(supp * Decimal("0.98"), entry - a * Decimal("1.5"))
    if stop_candidate >= entry:
        stop_candidate = entry - a * Decimal("1.5")
        if stop_candidate >= entry:
            stop_candidate = entry * Decimal("0.98")

    stop = max(stop_candidate, Decimal("0.01"))

    # 计算目标位（严保 target > entry）
    target_candidate = min(res, entry + a * Decimal("3.0"))
    if target_candidate <= entry:
        target_candidate = entry + a * Decimal("3.0")
        if target_candidate <= entry:
            target_candidate = entry * Decimal("1.05")

    target = target_candidate

    risk = entry - stop
    reward = target - entry

    if risk <= _ZERO:
        raise QuantitativeCalculationError(
            "Trade plan risk is non-positive (entry <= stop)",
            details={"entry": str(entry), "stop": str(stop)},
        )
    if reward <= _ZERO:
        raise QuantitativeCalculationError(
            "Trade plan reward is non-positive (target <= entry)",
            details={"entry": str(entry), "target": str(target)},
        )

    risk_reward = reward / risk

    return {
        "entry": entry.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP),
        "stop": stop.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP),
        "target": target.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP),
        "risk_reward": risk_reward.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP),
    }


class QuantitativeEngine:
    """确定性代码量化派生引擎实现。

    实现 ``QuantitativeEngineProtocol``，杜绝大模型臆造交易点位。
    """

    def compute_buy_decision_metrics(
        self,
        current_price: Decimal,
        target_price: Decimal,
        low_52w: Decimal,
        high_52w: Decimal,
    ) -> dict[str, Any]:
        """计算买入决策所需衍生指标。"""
        target_vs_price_pct = compute_target_vs_price_pct(current_price, target_price)
        pos_in_52w_range = compute_pos_in_52w_range(current_price, low_52w, high_52w)
        return {
            "target_vs_price_pct": target_vs_price_pct,
            "pos_in_52w_range": pos_in_52w_range,
        }

    def compute_technical_trade_plan(
        self,
        current_price: Decimal,
        support: Decimal,
        resistance: Decimal,
        atr: Decimal,
    ) -> dict[str, Any]:
        """确定性计算技术面交易计划。"""
        return compute_technical_trade_plan(current_price, support, resistance, atr)
