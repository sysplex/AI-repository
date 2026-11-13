"""M4 统一 Broker 端口协议适配器（T07），`CONTRACTS.md §2` 与 `docs/02-architecture.md §5`。

实现系统统一定义的 `Broker` 端口协议，供策略回测引擎（BacktestEngine）
与高层交易调度器统一调用。
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

import structlog

from app.core.errors import NotFound, StateConflict
from app.modules.simbroker.accounting import AccountingEngine, PositionState
from app.modules.simbroker.matcher import MatchingEngine
from app.modules.simbroker.ports import BarProtocol, MarketDataFeedProtocol
from app.modules.simbroker.schemas import (
    AccountOverview,
    FeeModelConfig,
    OrderCreate,
    OrderResponse,
    PositionResponse,
    TradeResponse,
)
from app.modules.simbroker.validator import OrderValidator

logger = structlog.get_logger(__name__)

__all__ = ["SimBroker"]

_QUANTIZE_CASH = Decimal("0.0001")


class SimBroker:
    """系统统一 Broker 端口协议在模拟盘/回测环境的适配器。"""

    name: str = "SimBroker"

    def __init__(
        self,
        initial_cash: Decimal = Decimal("100000.0000"),
        fee_model: FeeModelConfig | None = None,
        slippage_bps: Decimal = Decimal("5.0"),
        pdt_enabled: bool = True,
        market_feed: MarketDataFeedProtocol | None = None,
    ) -> None:
        self.initial_cash = initial_cash
        self.fee_model = fee_model or FeeModelConfig()
        self.slippage_bps = slippage_bps
        self.pdt_enabled = pdt_enabled
        self.market_feed = market_feed

        self.accounting = AccountingEngine()

        # 内存状态容器
        self._accounts: dict[str, Decimal] = {}  # account_id -> cash
        # (account_id, symbol) -> PositionState
        self._positions: dict[tuple[str, str], PositionState] = {}
        # account_id -> {order_id: OrderResponse}
        self._orders: dict[str, dict[str, OrderResponse]] = {}
        # (account_id, idem_key) -> order_id
        self._idempotency_map: dict[tuple[str, str], str] = {}
        self._trades: dict[str, list[TradeResponse]] = {}  # account_id -> [TradeResponse]

    def _ensure_account(self, account_id: str) -> None:
        if account_id not in self._accounts:
            self._accounts[account_id] = self.initial_cash
            self._orders[account_id] = {}
            self._trades[account_id] = []

    def submit_order(
        self, account_id: str, req: OrderCreate, idempotency_key: str
    ) -> OrderResponse:
        """提交订单。"""
        self._ensure_account(account_id)

        # 1. 幂等检测
        idem_key = (account_id, idempotency_key)
        if idem_key in self._idempotency_map:
            existing_oid = self._idempotency_map[idem_key]
            return self._orders[account_id][existing_oid]

        current_cash = self._accounts[account_id]
        pos_key = (account_id, req.symbol)
        pos = self._positions.get(pos_key)
        pos_qty = pos.qty if pos is not None else Decimal("0.0000")

        current_price = None
        if self.market_feed is not None:
            current_price = self.market_feed.get_latest_price(req.symbol)

        overview = self.get_account(account_id)

        # 2. 规则校验
        val_res = OrderValidator.validate(
            order_req=req,
            account_cash=current_cash,
            account_slippage_bps=self.slippage_bps,
            account_fee_model=self.fee_model,
            account_pdt_enabled=self.pdt_enabled,
            account_equity=overview.equity,
            current_position_qty=pos_qty,
            current_market_price=current_price,
            rolling_day_trades=0,
        )

        order_id = uuid.uuid4()
        now = datetime.now(UTC)
        status = "accepted" if val_res.is_valid else "rejected"
        reject_reason = val_res.reject_reason

        order_resp = OrderResponse(
            id=order_id,
            user_id=uuid.UUID(int=1),
            account_id=uuid.UUID(account_id) if len(account_id) == 36 else uuid.uuid4(),
            symbol=req.symbol,
            side=req.side,
            type=req.type,
            qty=req.qty,
            limit_price=req.limit_price,
            stop_price=req.stop_price,
            tif=req.tif,
            status=status,
            idempotency_key=idempotency_key,
            source=req.source,
            ai_report_id=req.ai_report_id,
            note=req.note,
            reject_reason=reject_reason,
            created_at=now,
            updated_at=now,
        )

        self._orders[account_id][str(order_id)] = order_resp
        self._idempotency_map[idem_key] = str(order_id)
        return order_resp

    def cancel_order(self, account_id: str, order_id: str) -> OrderResponse:
        """撤销挂单。"""
        self._ensure_account(account_id)
        if order_id not in self._orders[account_id]:
            raise NotFound(f"Order {order_id} not found")

        order = self._orders[account_id][order_id]
        if order.status in ("filled", "cancelled", "rejected", "expired"):
            raise StateConflict(f"Cannot cancel order in state {order.status}")

        updated_order = OrderResponse(
            id=order.id,
            user_id=order.user_id,
            account_id=order.account_id,
            symbol=order.symbol,
            side=order.side,
            type=order.type,
            qty=order.qty,
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            tif=order.tif,
            status="cancelled",
            idempotency_key=order.idempotency_key,
            source=order.source,
            ai_report_id=order.ai_report_id,
            note=order.note,
            reject_reason=order.reject_reason,
            created_at=order.created_at,
            updated_at=datetime.now(UTC),
        )
        self._orders[account_id][order_id] = updated_order
        return updated_order

    def get_account(self, account_id: str) -> AccountOverview:
        """查询账户概况。"""
        self._ensure_account(account_id)
        cash = self._accounts[account_id]

        total_market_value = Decimal("0.0000")
        for (acc, sym), pos in self._positions.items():
            if acc == account_id and pos.qty > Decimal("0"):
                price = None
                if self.market_feed is not None:
                    price = self.market_feed.get_latest_price(sym)
                if price is None:
                    price = pos.avg_cost
                total_market_value += (pos.qty * price).quantize(
                    _QUANTIZE_CASH, rounding=ROUND_HALF_UP
                )

        equity = (cash + total_market_value).quantize(_QUANTIZE_CASH, rounding=ROUND_HALF_UP)
        total_pnl = (equity - self.initial_cash).quantize(_QUANTIZE_CASH, rounding=ROUND_HALF_UP)
        total_pnl_pct = (
            (total_pnl / self.initial_cash * Decimal("100")).quantize(
                _QUANTIZE_CASH, rounding=ROUND_HALF_UP
            )
            if self.initial_cash > Decimal("0")
            else Decimal("0.0000")
        )

        acc_uuid = uuid.UUID(account_id) if len(account_id) == 36 else uuid.uuid4()
        return AccountOverview(
            id=acc_uuid,
            name="SimBroker Account",
            status="active",
            initial_cash=self.initial_cash,
            cash=cash,
            market_value=total_market_value,
            equity=equity,
            daily_pnl=total_pnl,
            daily_pnl_pct=total_pnl_pct,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            pdt_day_trades_count=0,
            pdt_warning=False,
        )

    def get_positions(self, account_id: str) -> Sequence[PositionResponse]:
        """查询活跃持仓列表。"""
        self._ensure_account(account_id)
        overview = self.get_account(account_id)
        total_equity = overview.equity

        result: list[PositionResponse] = []
        for (acc, sym), pos in self._positions.items():
            if acc == account_id and pos.qty > Decimal("0"):
                price = None
                if self.market_feed is not None:
                    price = self.market_feed.get_latest_price(sym)
                if price is None:
                    price = pos.avg_cost

                market_val = (pos.qty * price).quantize(_QUANTIZE_CASH, rounding=ROUND_HALF_UP)
                unrealized_pnl = ((price - pos.avg_cost) * pos.qty).quantize(
                    _QUANTIZE_CASH, rounding=ROUND_HALF_UP
                )
                unrealized_pnl_pct = (
                    ((price - pos.avg_cost) / pos.avg_cost * Decimal("100")).quantize(
                        _QUANTIZE_CASH, rounding=ROUND_HALF_UP
                    )
                    if pos.avg_cost > Decimal("0")
                    else Decimal("0.0000")
                )
                weight_pct = (
                    (market_val / total_equity * Decimal("100")).quantize(
                        _QUANTIZE_CASH, rounding=ROUND_HALF_UP
                    )
                    if total_equity > Decimal("0")
                    else Decimal("0.0000")
                )

                result.append(
                    PositionResponse(
                        id=uuid.uuid4(),
                        account_id=overview.id,
                        symbol=sym,
                        qty=pos.qty,
                        avg_cost=pos.avg_cost,
                        current_price=price,
                        market_value=market_val,
                        unrealized_pnl=unrealized_pnl,
                        unrealized_pnl_pct=unrealized_pnl_pct,
                        realized_pnl=pos.realized_pnl,
                        weight_pct=weight_pct,
                    )
                )

        return result

    def process_bar(self, account_id: str, bar_time: datetime) -> Sequence[TradeResponse]:
        """根据当前 Bar 时间进行订单撮合与记账结转。"""
        self._ensure_account(account_id)
        executed: list[TradeResponse] = []

        open_orders = [
            o for o in self._orders[account_id].values() if o.status in ("pending", "accepted")
        ]

        class _AccountWrap:
            def __init__(self, cash: Decimal) -> None:
                self.cash = cash

        acc_wrap = _AccountWrap(self._accounts[account_id])

        for ord_info in open_orders:
            bar: BarProtocol | None = None
            if self.market_feed is not None:
                bar = self.market_feed.get_daily_bar(ord_info.symbol, bar_time.date())

            match_res = MatchingEngine.match_order(
                order=ord_info,
                bar=bar,
                slippage_bps=self.slippage_bps,
                fee_model=self.fee_model,
                execution_time=bar_time,
            )

            if match_res.status == "filled" and match_res.fill_price is not None:
                pos_key = (account_id, ord_info.symbol)
                if pos_key not in self._positions:
                    self._positions[pos_key] = PositionState(symbol=ord_info.symbol)
                pos = self._positions[pos_key]

                rec = self.accounting.execute_trade(
                    account=acc_wrap,
                    symbol=ord_info.symbol,
                    side=ord_info.side,
                    qty=match_res.filled_qty,
                    price=match_res.fill_price,
                    fee=match_res.fee,
                    position=pos,
                    executed_at=bar_time,
                )

                self._accounts[account_id] = acc_wrap.cash

                # 更新订单状态为 filled
                updated_ord = OrderResponse(
                    id=ord_info.id,
                    user_id=ord_info.user_id,
                    account_id=ord_info.account_id,
                    symbol=ord_info.symbol,
                    side=ord_info.side,
                    type=ord_info.type,
                    qty=ord_info.qty,
                    limit_price=ord_info.limit_price,
                    stop_price=ord_info.stop_price,
                    tif=ord_info.tif,
                    status="filled",
                    idempotency_key=ord_info.idempotency_key,
                    source=ord_info.source,
                    ai_report_id=ord_info.ai_report_id,
                    note=ord_info.note,
                    reject_reason=ord_info.reject_reason,
                    created_at=ord_info.created_at,
                    updated_at=bar_time,
                )
                self._orders[account_id][str(ord_info.id)] = updated_ord

                trade_resp = TradeResponse(
                    id=uuid.uuid4(),
                    user_id=ord_info.user_id,
                    account_id=ord_info.account_id,
                    order_id=ord_info.id,
                    symbol=ord_info.symbol,
                    side=ord_info.side,
                    qty=match_res.filled_qty,
                    price=match_res.fill_price,
                    fee=match_res.fee,
                    realized_pnl=rec.realized_pnl,
                    executed_at=bar_time,
                )
                self._trades[account_id].append(trade_resp)
                executed.append(trade_resp)

        return executed
