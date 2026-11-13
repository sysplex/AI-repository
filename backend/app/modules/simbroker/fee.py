"""M4 模拟盘费用与滑点计算引擎（T02），`CONTRACTS.md §3`。

支持零手续费、每股固定收费、比例费率（bps）及阶梯保底封顶模型。
支持可配置基点（bps）的滑点买入上滑与卖出下滑计算。
所有计算严格采用高精 Decimal 运算。
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.modules.simbroker.schemas import FeeModelConfig

__all__ = ["FeeEngine", "calculate_fee", "calculate_slippage"]

_ROUND_SCALE = Decimal("0.0001")


def calculate_fee(
    qty: Decimal,
    price: Decimal,
    config: FeeModelConfig,
) -> Decimal:
    """计算单笔交易的手续费。

    :param qty: 成交股数（必须 > 0）
    :param price: 成交单价（必须 > 0）
    :param config: 手续费模型配置
    :return: 实际手续费 Decimal（截取到 4 位小数）
    """
    if qty <= Decimal("0") or price <= Decimal("0"):
        return Decimal("0.0000")

    fee_type = config.type
    amount = qty * price

    if fee_type == "zero":
        raw_fee = Decimal("0")
    elif fee_type == "per_share":
        raw_fee = qty * config.per_share
    elif fee_type == "bps":
        raw_fee = amount * (config.bps / Decimal("10000"))
    elif fee_type == "tiered":
        # 混合阶梯模型：每股固定费 + 比例费率
        raw_fee = (qty * config.per_share) + (amount * (config.bps / Decimal("10000")))
    else:
        raw_fee = Decimal("0")

    # 保底最低收费
    if config.min_fee > Decimal("0") and raw_fee < config.min_fee:
        raw_fee = config.min_fee

    # 封顶最高收费
    if config.max_fee is not None and config.max_fee > Decimal("0") and raw_fee > config.max_fee:
        raw_fee = config.max_fee

    return raw_fee.quantize(_ROUND_SCALE, rounding=ROUND_HALF_UP)


def calculate_slippage(
    price: Decimal,
    side: Literal["buy", "sell"] | str,
    slippage_bps: Decimal,
) -> Decimal:
    """计算考虑滑点后的实际成交预期单价。

    - 买入 (buy)：向上滑点（更贵价格成交） `price * (1 + bps / 10000)`
    - 卖出 (sell)：向下滑点（更低价格成交） `max(0, price * (1 - bps / 10000))`

    :param price: 基准价格
    :param side: 交易方向 'buy' 或 'sell'
    :param slippage_bps: 滑点基点数（例如 5 bps = 0.05%）
    :return: 计入滑点后的执行价格 Decimal
    """
    if price <= Decimal("0"):
        return Decimal("0.0000")

    slippage_rate = slippage_bps / Decimal("10000")
    delta = price * slippage_rate

    side_lower = side.lower()
    exec_price = price + delta if side_lower == "buy" else max(Decimal("0.0000"), price - delta)

    return exec_price.quantize(_ROUND_SCALE, rounding=ROUND_HALF_UP)


class FeeEngine:
    """费用与滑点计算门面引擎。"""

    @staticmethod
    def compute_fee(qty: Decimal, price: Decimal, config: FeeModelConfig) -> Decimal:
        return calculate_fee(qty, price, config)

    @staticmethod
    def compute_slippage_price(
        price: Decimal, side: Literal["buy", "sell"] | str, slippage_bps: Decimal
    ) -> Decimal:
        return calculate_slippage(price, side, slippage_bps)
