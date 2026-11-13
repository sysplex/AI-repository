"""M4 收盘批处理与净值快照沉淀（T05），`CONTRACTS.md §3`。

实现日终收盘批处理：
1. 过期未成交的 DAY 订单（状态由 pending/accepted 转为 expired），GTC 订单保持有效；
2. 依据各持仓标的收盘价计算总市值 market_value；
3. 计算总净值 equity = cash + market_value；
4. 结合历史峰值净值计算并更新最大回撤率 drawdown = (peak_equity - equity) / peak_equity；
5. 生成并持久化 EquitySnapshot 数据快照。
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog

from app.modules.simbroker.models import EquitySnapshot
from app.modules.simbroker.ports import MarketDataFeedProtocol

logger = structlog.get_logger(__name__)

__all__ = [
    "MarketCloseBatch",
    "MarketCloseResult",
    "calculate_drawdown",
    "expire_day_orders",
    "process_market_close",
]

_DEFAULT_QUANTIZE_CASH = Decimal("0.0001")
_DEFAULT_QUANTIZE_DRAWDOWN = Decimal("0.000001")


@dataclass(frozen=True)
class MarketCloseResult:
    """收盘批处理执行快照"""

    account_id: uuid.UUID
    trade_date: date
    cash: Decimal
    market_value: Decimal
    equity: Decimal
    peak_equity: Decimal
    drawdown: Decimal
    expired_orders_count: int
    expired_order_ids: list[uuid.UUID] = field(default_factory=list)
    snapshot: EquitySnapshot | None = None


def expire_day_orders(orders: Sequence[Any]) -> list[uuid.UUID]:
    """将所有处于 pending 或 accepted 状态的 DAY 订单置为 expired。

    :param orders: 待处理订单列表
    :return: 被置为 expired 的订单 ID 列表
    """
    expired_ids: list[uuid.UUID] = []
    for order in orders:
        tif = getattr(order, "tif", "day")
        status = getattr(order, "status", "")
        if tif == "day" and status in ("pending", "accepted"):
            order.status = "expired"
            order_id = getattr(order, "id", None)
            if order_id is not None:
                expired_ids.append(order_id)
            logger.info("Expired unexecuted DAY order", order_id=str(order_id))
    return expired_ids


def calculate_drawdown(
    current_equity: Decimal,
    historical_peak_equity: Decimal | None = None,
    quantize_places: Decimal = _DEFAULT_QUANTIZE_DRAWDOWN,
) -> tuple[Decimal, Decimal]:
    """计算最新峰值净值与当前回撤率。

    :param current_equity: 当前收盘总净值
    :param historical_peak_equity: 历史最高净值（若无则取当前净值）
    :param quantize_places: 回撤量化精度（默认 6 位小数，对应 Numeric(10, 6)）
    :return: (new_peak_equity, drawdown)
    """
    prev_peak = historical_peak_equity or Decimal("0.0000")
    new_peak = max(prev_peak, current_equity)

    if new_peak <= Decimal("0.0000"):
        return Decimal("0.0000"), Decimal("0.000000")

    raw_drawdown = (new_peak - current_equity) / new_peak
    # 回撤率必须在 [0, 1] 之间
    clamped_drawdown = max(Decimal("0.000000"), min(Decimal("1.000000"), raw_drawdown))
    drawdown = clamped_drawdown.quantize(quantize_places, rounding=ROUND_HALF_UP)
    return new_peak, drawdown


def process_market_close(
    account: Any,
    positions: Sequence[Any],
    open_orders: Sequence[Any],
    trade_date: date,
    current_prices: Mapping[str, Decimal] | None = None,
    market_feed: MarketDataFeedProtocol | None = None,
    historical_peak_equity: Decimal | None = None,
    now_func: datetime | None = None,
) -> MarketCloseResult:
    """执行单个模拟盘账户的日终收盘批处理。

    :param account: 账户对象（包含 id, cash）
    :param positions: 账户当前所有持仓对象列表（包含 symbol, qty, avg_cost）
    :param open_orders: 账户所有待撮合/挂单列表
    :param trade_date: 当期交易日期
    :param current_prices: 现价字典映射（symbol -> Decimal）
    :param market_feed: 外部行情数据源协议（若 current_prices 未提供时从此查询）
    :param historical_peak_equity: 截至昨日的历史最高净值
    :param now_func: 指定当前时间戳（测试注入用）
    :return: MarketCloseResult 执行快照及 EquitySnapshot ORM 实体
    """
    account_id = getattr(account, "id", None)
    if account_id is None:
        raise ValueError("Account must have a valid 'id' attribute")

    # 1. 过期清理所有未成交的 DAY 挂单
    expired_ids = expire_day_orders(open_orders)

    # 2. 计算各持仓总市值
    total_market_value = Decimal("0.0000")
    for pos in positions:
        if pos.qty <= Decimal("0"):
            continue

        symbol = pos.symbol
        price: Decimal | None = None
        if current_prices is not None and symbol in current_prices:
            price = current_prices[symbol]
        elif market_feed is not None:
            price = market_feed.get_latest_price(symbol)

        if price is None:
            # 行情兜底：若行情缺失，记录告警并使用 avg_cost 进行估值防御
            logger.warning(
                "Missing closing price for symbol, falling back to avg_cost",
                symbol=symbol,
                account_id=str(account_id),
                trade_date=str(trade_date),
            )
            price = pos.avg_cost

        total_market_value += (pos.qty * price).quantize(
            _DEFAULT_QUANTIZE_CASH, rounding=ROUND_HALF_UP
        )

    # 3. 计算总净值
    cash = account.cash.quantize(_DEFAULT_QUANTIZE_CASH, rounding=ROUND_HALF_UP)
    equity = (cash + total_market_value).quantize(_DEFAULT_QUANTIZE_CASH, rounding=ROUND_HALF_UP)

    # 4. 计算峰值净值与回撤
    new_peak, drawdown = calculate_drawdown(
        current_equity=equity,
        historical_peak_equity=historical_peak_equity,
    )

    # 5. 构建 EquitySnapshot ORM 实体
    created_at = now_func or datetime.now(UTC)
    snapshot = EquitySnapshot(
        account_id=account_id,
        trade_date=trade_date,
        cash=cash,
        market_value=total_market_value,
        equity=equity,
        drawdown=drawdown,
        created_at=created_at,
    )

    logger.info(
        "Processed market close",
        account_id=str(account_id),
        trade_date=str(trade_date),
        cash=str(cash),
        market_value=str(total_market_value),
        equity=str(equity),
        peak_equity=str(new_peak),
        drawdown=str(drawdown),
        expired_orders=len(expired_ids),
    )

    return MarketCloseResult(
        account_id=account_id,
        trade_date=trade_date,
        cash=cash,
        market_value=total_market_value,
        equity=equity,
        peak_equity=new_peak,
        drawdown=drawdown,
        expired_orders_count=len(expired_ids),
        expired_order_ids=expired_ids,
        snapshot=snapshot,
    )


class MarketCloseBatch:
    """批量收盘处理器。"""

    @classmethod
    def execute(
        cls,
        account: Any,
        positions: Sequence[Any],
        open_orders: Sequence[Any],
        trade_date: date,
        current_prices: Mapping[str, Decimal] | None = None,
        market_feed: MarketDataFeedProtocol | None = None,
        historical_peak_equity: Decimal | None = None,
    ) -> MarketCloseResult:
        """运行收盘批处理流程。"""
        return process_market_close(
            account=account,
            positions=positions,
            open_orders=open_orders,
            trade_date=trade_date,
            current_prices=current_prices,
            market_feed=market_feed,
            historical_peak_equity=historical_peak_equity,
        )
