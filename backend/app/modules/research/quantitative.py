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
    "compute_cross_sectional_ranking",
    "compute_pos_in_52w_range",
    "compute_target_vs_price_pct",
    "compute_technical_trade_plan",
    "optimize_portfolio_weights",
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


_NEUTRAL_BENCHMARKS: dict[str, float] = {
    "revenue_growth": 0.05,
    "net_margin": 0.10,
    "roe": 0.12,
    "dividend_yield": 0.015,
    "pe_trailing": 22.0,
    "debt_to_equity": 1.0,
    "beta": 1.0,
}


def _extract_metric_float(facts: dict[str, Any], field: str) -> float | None:
    """从股票事实快照中提取浮点数值。"""
    funds = facts.get("fundamentals")
    quote = facts.get("quote")
    profile = facts.get("profile")

    val = None
    if isinstance(funds, dict) and field in funds and funds[field] is not None:
        val = funds[field]
    elif isinstance(quote, dict) and field in quote and quote[field] is not None:
        val = quote[field]
    elif isinstance(profile, dict) and field in profile and profile[field] is not None:
        val = profile[field]

    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def compute_cross_sectional_ranking(
    stocks_facts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """计算横向多标的标准化分位得分与确定性综合排序（docs/tasks/M7/CONTRACTS.md §3.1）。

    正向指标（越大越优）：
    - revenue_growth: 营收增速 (权重 20%)
    - net_margin: 净利润率 (权重 20%)
    - roe: 净资产收益率 (权重 15%)
    - dividend_yield: 股息率 (权重 10%)

    负向指标（越小越优）：
    - pe_trailing: 市盈率 (权重 15%，非正值深度惩罚)
    - debt_to_equity: 资产负债率 (权重 10%)
    - beta: 波动率 (权重 10%)

    统一计算百分位分值（0~100 分），按加权总分从高到低确定性排序（同分按 symbol 字母升序）。
    """
    if len(stocks_facts) < 2:
        raise InvalidParameterError(
            "Cross-sectional ranking requires at least 2 stocks",
            details={"stock_count": len(stocks_facts)},
        )

    symbols = sorted(list(stocks_facts.keys()))
    n = len(symbols)

    # 1. 提取各标的 7 大核心指标配置
    metrics_spec: list[dict[str, Any]] = [
        {"name": "revenue_growth", "weight": Decimal("0.20"), "higher_is_better": True},
        {"name": "net_margin", "weight": Decimal("0.20"), "higher_is_better": True},
        {"name": "roe", "weight": Decimal("0.15"), "higher_is_better": True},
        {"name": "dividend_yield", "weight": Decimal("0.10"), "higher_is_better": True},
        {"name": "pe_trailing", "weight": Decimal("0.15"), "higher_is_better": False},
        {"name": "debt_to_equity", "weight": Decimal("0.10"), "higher_is_better": False},
        {"name": "beta", "weight": Decimal("0.10"), "higher_is_better": False},
    ]

    scores: dict[str, Decimal] = {s: Decimal("0.00") for s in symbols}

    for spec in metrics_spec:
        m_name = str(spec["name"])
        m_weight: Decimal = spec["weight"]
        higher_better: bool = bool(spec["higher_is_better"])

        # 提取或补齐中性基准值
        raw_values: dict[str, float] = {}
        for s in symbols:
            extracted = _extract_metric_float(stocks_facts[s], m_name)
            raw_values[s] = (
                extracted if extracted is not None else _NEUTRAL_BENCHMARKS.get(m_name, 0.0)
            )

        items = list(raw_values.items())

        # 特殊处理市盈率：PE <= 0 代表亏损，评级排在所有正 PE 之后（最劣）
        if m_name == "pe_trailing":

            def _pe_key(item: tuple[str, float]) -> tuple[int, float]:
                v = item[1]
                if v > 0:
                    return (0, v)
                return (1, 0.0)

            valid_sorted = sorted(items, key=_pe_key)
            total_valid = len(valid_sorted)
            val_ranks: dict[str, float] = {
                sym: float(total_valid - idx) for idx, (sym, _) in enumerate(valid_sorted)
            }
        else:
            valid_sorted = sorted(items, key=lambda x: x[1])
            val_ranks = {}
            for idx, (sym, _) in enumerate(valid_sorted):
                if higher_better:
                    val_ranks[sym] = float(idx + 1)
                else:
                    val_ranks[sym] = float(len(valid_sorted) - idx)

        # 映射分位数 [0.0, 100.0]，使用统计学标准中点经验分位数公式 (rank - 0.5) / N * 100
        unique_vals = set(v for _, v in items)
        if len(unique_vals) <= 1:
            for s in symbols:
                scores[s] += Decimal("50.00") * m_weight
        else:
            for s, r in val_ranks.items():
                pct = ((r - 0.5) / float(n)) * 100.0
                scores[s] += Decimal(str(round(pct, 2))) * m_weight

    # 2. 组装排序结果（按加权总分降序，同分按 symbol 升序）
    ranked_symbols = sorted(
        symbols,
        key=lambda s: (-scores[s], s),
    )

    ranking_list: list[dict[str, Any]] = []
    for rank_idx, sym in enumerate(ranked_symbols, start=1):
        tot = scores[sym].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ranking_list.append(
            {
                "symbol": sym,
                "rank": rank_idx,
                "total_score": tot,
                "one_line_reason": f"综合得分 {tot:.2f}，在 {n} 只对比标的中位列第 {rank_idx}",
            }
        )

    return ranking_list


def optimize_portfolio_weights(
    amount: Decimal | float | int | str,
    symbols: list[str],
    risk_level: str = "moderate",
    goal: str = "growth",
    stocks_facts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """计算满足约束条件与权重守恒的确定性投资组合配置（docs/tasks/M7/CONTRACTS.md §3.2）。

    约束条件：
    - conservative: min_cash_pct >= 20.00%, max_stock_weight <= 25.00%
    - moderate: min_cash_pct >= 10.00%, max_stock_weight <= 30.00%
    - aggressive: min_cash_pct >= 5.00%, max_stock_weight <= 40.00%

    守恒公式：
    - sum(weight_pct) + cash_pct == 100.00%
    - sum(allocated_amount) + cash_amount == amount
    """
    total_amount = _to_decimal(amount, "amount")
    if total_amount <= _ZERO:
        raise InvalidParameterError(
            "Portfolio amount must be positive",
            details={"amount": str(total_amount)},
        )

    clean_symbols = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
    if len(clean_symbols) < 2 or len(clean_symbols) > 12:
        raise InvalidParameterError(
            "Portfolio symbols count must be between 2 and 12",
            details={"symbols_count": len(clean_symbols)},
        )

    r_level = risk_level.strip().lower()
    if r_level == "conservative":
        min_cash_pct = Decimal("20.00")
        max_stock_weight = Decimal("25.00")
    elif r_level == "aggressive":
        min_cash_pct = Decimal("5.00")
        max_stock_weight = Decimal("40.00")
    else:
        min_cash_pct = Decimal("10.00")
        max_stock_weight = Decimal("30.00")

    g_goal = goal.strip().lower()
    if g_goal == "retirement":
        # 退休目标增加 5% 现金防守垫
        min_cash_pct = min(min_cash_pct + Decimal("5.00"), Decimal("40.00"))

    # 可分配股票预算上限
    equity_budget = Decimal("100.00") - min_cash_pct
    max_possible_equity = Decimal(str(len(clean_symbols))) * max_stock_weight
    allocatable_equity = min(equity_budget, max_possible_equity)

    # 计算各标的相对吸引力得分 a_i
    raw_weights: dict[str, Decimal] = {}
    for s in clean_symbols:
        a_i = Decimal("1.00")
        if stocks_facts and s in stocks_facts:
            f = stocks_facts[s]
            beta = _extract_metric_float(f, "beta") or 1.0
            div_yield = _extract_metric_float(f, "dividend_yield") or 0.0
            rev_growth = _extract_metric_float(f, "revenue_growth") or 0.05

            inv_vol = 1.0 / max(beta, 0.2)
            if g_goal in ("conservative", "safety", "retirement"):
                factor = inv_vol * (1.0 + 3.0 * max(div_yield, 0.0))
            elif g_goal == "income":
                factor = 1.0 + 8.0 * max(div_yield, 0.0)
            elif g_goal == "growth":
                factor = (1.0 + max(rev_growth, -0.2)) * max(beta, 0.5)
            else:
                factor = inv_vol
            a_i = max(Decimal(str(round(factor, 4))), Decimal("0.10"))
        raw_weights[s] = a_i

    # 循环约束投影：若有标的超出 max_stock_weight 则封顶并将多余权重二次分配
    capped: set[str] = set()
    assigned_weights: dict[str, Decimal] = {}
    remaining_equity = allocatable_equity

    while True:
        uncapped = [s for s in clean_symbols if s not in capped]
        if not uncapped:
            break
        sum_uncapped_raw = sum(raw_weights[s] for s in uncapped)
        newly_capped = False
        for s in uncapped:
            w = remaining_equity * (raw_weights[s] / sum_uncapped_raw)
            if w > max_stock_weight:
                assigned_weights[s] = max_stock_weight
                capped.add(s)
                remaining_equity -= max_stock_weight
                newly_capped = True
                break
        if not newly_capped:
            for s in uncapped:
                assigned_weights[s] = remaining_equity * (raw_weights[s] / sum_uncapped_raw)
            break

    # 四舍五入保留 2 位小数
    rounded_weights: dict[str, Decimal] = {}
    for s in clean_symbols:
        rounded_weights[s] = assigned_weights[s].quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    # 确保单股不超过上限且大于 0
    for s in clean_symbols:
        if rounded_weights[s] > max_stock_weight:
            rounded_weights[s] = max_stock_weight
        elif rounded_weights[s] < _TWO_PLACES:
            rounded_weights[s] = _TWO_PLACES

    # 严格计算现金比例以保证恒等于 100.00%
    sum_stock_weights = sum(rounded_weights.values())
    cash_pct = Decimal("100.00") - sum_stock_weights

    # 若由于进位导致 cash_pct < min_cash_pct，从最大持仓逐步扣减 0.01
    while cash_pct < min_cash_pct:
        max_sym = max(clean_symbols, key=lambda s: rounded_weights[s])
        rounded_weights[max_sym] -= _TWO_PLACES
        cash_pct += _TWO_PLACES

    # 计算各标的分配资金与现金金额
    allocations_list: list[dict[str, Any]] = []
    total_allocated_stocks = _ZERO
    for s in clean_symbols:
        w_pct = rounded_weights[s]
        amt_i = (total_amount * (w_pct / Decimal("100"))).quantize(
            _TWO_PLACES, rounding=ROUND_HALF_UP
        )
        total_allocated_stocks += amt_i
        allocations_list.append(
            {
                "symbol": s,
                "weight_pct": w_pct,
                "allocated_amount": amt_i,
                "reason": f"{s} 建议配置权重 {w_pct}%，资金配额 ${amt_i}",
            }
        )

    cash_amount = total_amount - total_allocated_stocks

    return {
        "amount": total_amount,
        "allocations": allocations_list,
        "cash_pct": cash_pct,
        "cash_amount": cash_amount,
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

    def compute_cross_sectional_ranking(
        self,
        stocks_facts: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """计算横向多标的标准化分位得分与确定性综合排序。"""
        return compute_cross_sectional_ranking(stocks_facts)

    def optimize_portfolio_weights(
        self,
        amount: Decimal,
        symbols: list[str],
        risk_level: str = "moderate",
        goal: str = "growth",
        stocks_facts: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """计算满足约束条件与权重守恒的确定性投资组合配置。"""
        return optimize_portfolio_weights(
            amount=amount,
            symbols=symbols,
            risk_level=risk_level,
            goal=goal,
            stocks_facts=stocks_facts,
        )
