"""M4 核心订单撮合引擎（T03），`CONTRACTS.md §3`。

实现市价单、限价单、止损单的确定性撮合、TIF（DAY/GTC）有效期管理与严格行情缺失防御。
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import structlog

from app.modules.simbroker.fee import calculate_fee, calculate_slippage
from app.modules.simbroker.ports import BarProtocol
from app.modules.simbroker.schemas import FeeModelConfig

__all__ = ["MatchResult", "MatchingEngine"]

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class MatchResult:
    """单个订单撮合结果"""

    order_id: uuid.UUID
    status: Literal["filled", "accepted", "expired", "cancelled"]
    filled_qty: Decimal = Decimal("0.0000")
    fill_price: Decimal | None = None
    fee: Decimal = Decimal("0.0000")
    message: str | None = None
    executed_at: datetime | None = None


class MatchingEngine:
    """模拟盘撮合引擎。"""

    @classmethod
    def match_order(
        cls,
        order: Any,
        bar: BarProtocol | None,
        slippage_bps: Decimal,
        fee_model: FeeModelConfig,
        is_market_close: bool = False,
        execution_time: datetime | None = None,
    ) -> MatchResult:
        """根据单根行情 K 线撮合单笔处于 accepted 状态的订单。

        :param order: 订单对象（需具备 id, symbol, side, type, qty, limit_price, stop_price）
        :param bar: 当期 K 线（trade_date, open, high, low, close），若缺失传入 None
        :param slippage_bps: 滑点基点
        :param fee_model: 手续费模型
        :param is_market_close: 是否处于收盘批处理时段（收盘时未成交的 DAY 订单将置为 expired）
        :param execution_time: 成交时间戳，默认当前 UTC
        :return: MatchResult
        """
        oid = order.id if isinstance(order.id, uuid.UUID) else uuid.UUID(str(order.id))
        exec_time = execution_time or datetime.now(UTC)

        # 仅撮合 accepted 状态的订单
        if order.status != "accepted":
            return MatchResult(
                order_id=oid,
                status=order.status,
                message=f"Order {oid} status is '{order.status}', not 'accepted'.",
            )

        # 行情缺失防御：严格保持 accepted 并发出警告日志，禁止使用陈旧价格
        if bar is None:
            logger.warning(
                "simbroker.matcher.missing_bar",
                order_id=str(oid),
                symbol=order.symbol,
                msg="Market bar missing for symbol; order remains accepted, no fill allowed.",
            )
            return MatchResult(
                order_id=oid,
                status="accepted",
                message=f"Market data missing for symbol {order.symbol}; order remains accepted.",
            )

        side: str = str(order.side).lower()
        order_type: str = str(order.type).lower()
        qty: Decimal = order.qty
        tif: str = str(order.tif).lower()

        # 1. 市价单（Market Order）
        if order_type == "market":
            base_price = bar.open
            fill_price = calculate_slippage(base_price, side, slippage_bps)
            fee = calculate_fee(qty, fill_price, fee_model)
            return MatchResult(
                order_id=oid,
                status="filled",
                filled_qty=qty,
                fill_price=fill_price,
                fee=fee,
                executed_at=exec_time,
            )

        # 2. 限价单（Limit Order）
        if order_type == "limit":
            limit_price: Decimal = order.limit_price or Decimal("0")
            if side == "buy":
                # 开盘跳空穿透：open <= limit_price 按开盘价更优成交
                if bar.open <= limit_price:
                    fill_price = bar.open
                    fee = calculate_fee(qty, fill_price, fee_model)
                    return MatchResult(
                        order_id=oid,
                        status="filled",
                        filled_qty=qty,
                        fill_price=fill_price,
                        fee=fee,
                        executed_at=exec_time,
                    )
                # 盘中触及：最低价 low <= limit_price 按限价成交
                if bar.low <= limit_price:
                    fill_price = limit_price
                    fee = calculate_fee(qty, fill_price, fee_model)
                    return MatchResult(
                        order_id=oid,
                        status="filled",
                        filled_qty=qty,
                        fill_price=fill_price,
                        fee=fee,
                        executed_at=exec_time,
                    )
            elif side == "sell":
                # 开盘跳空穿透：open >= limit_price 按开盘价更优成交
                if bar.open >= limit_price:
                    fill_price = bar.open
                    fee = calculate_fee(qty, fill_price, fee_model)
                    return MatchResult(
                        order_id=oid,
                        status="filled",
                        filled_qty=qty,
                        fill_price=fill_price,
                        fee=fee,
                        executed_at=exec_time,
                    )
                # 盘中触及：最高价 high >= limit_price 按限价成交
                if bar.high >= limit_price:
                    fill_price = limit_price
                    fee = calculate_fee(qty, fill_price, fee_model)
                    return MatchResult(
                        order_id=oid,
                        status="filled",
                        filled_qty=qty,
                        fill_price=fill_price,
                        fee=fee,
                        executed_at=exec_time,
                    )

            # 未满足撮合条件
            if is_market_close and tif == "day":
                return MatchResult(
                    order_id=oid,
                    status="expired",
                    message="DAY limit order expired at market close.",
                )
            return MatchResult(order_id=oid, status="accepted")

        # 3. 止损单（Stop Order）
        if order_type == "stop":
            stop_price: Decimal = order.stop_price or Decimal("0")
            if side == "buy" and bar.high >= stop_price:
                # 突破止损买入：当 high >= stop_price 触发
                base_price = max(stop_price, bar.open)
                fill_price = calculate_slippage(base_price, "buy", slippage_bps)
                fee = calculate_fee(qty, fill_price, fee_model)
                return MatchResult(
                    order_id=oid,
                    status="filled",
                    filled_qty=qty,
                    fill_price=fill_price,
                    fee=fee,
                    executed_at=exec_time,
                )
            if side == "sell" and bar.low <= stop_price:
                # 跌破止损卖出：当 low <= stop_price 触发
                base_price = min(stop_price, bar.open)
                fill_price = calculate_slippage(base_price, "sell", slippage_bps)
                fee = calculate_fee(qty, fill_price, fee_model)
                return MatchResult(
                    order_id=oid,
                    status="filled",
                    filled_qty=qty,
                    fill_price=fill_price,
                    fee=fee,
                    executed_at=exec_time,
                )

            # 未触发止损
            if is_market_close and tif == "day":
                return MatchResult(
                    order_id=oid,
                    status="expired",
                    message="DAY stop order expired at market close.",
                )
            return MatchResult(order_id=oid, status="accepted")

        return MatchResult(
            order_id=oid,
            status="accepted",
            message=f"Unsupported order type '{order_type}'.",
        )

    @classmethod
    def match_orders(
        cls,
        orders: Sequence[Any],
        bars_by_symbol: Mapping[str, BarProtocol | None],
        slippage_bps: Decimal,
        fee_model: FeeModelConfig,
        is_market_close: bool = False,
        execution_time: datetime | None = None,
    ) -> list[MatchResult]:
        """批量撮合订单序列。"""
        results: list[MatchResult] = []
        for ord in orders:
            sym = str(ord.symbol).upper()
            bar = bars_by_symbol.get(sym)
            res = cls.match_order(
                order=ord,
                bar=bar,
                slippage_bps=slippage_bps,
                fee_model=fee_model,
                is_market_close=is_market_close,
                execution_time=execution_time,
            )
            results.append(res)
        return results
