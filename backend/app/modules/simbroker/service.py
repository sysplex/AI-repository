"""M4 模拟盘核心门面服务（T07），`CONTRACTS.md §1 & §2`。

编排校验、撮合、记账、公司行动、收盘批处理、绩效与风险诊断能力，
提供完整的异步持久化业务接口。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, StateConflict
from app.core.metrics import record_simbroker_order, record_simbroker_trade
from app.modules.simbroker.accounting import AccountingEngine, InsufficientCashError
from app.modules.simbroker.market_close import MarketCloseBatch, MarketCloseResult
from app.modules.simbroker.matcher import MatchingEngine
from app.modules.simbroker.models import (
    EquitySnapshot,
    SimAccount,
    SimOrder,
    SimPosition,
    SimTrade,
    TradeJournal,
)
from app.modules.simbroker.pdt import PdtEngine
from app.modules.simbroker.performance import PerformanceAnalyzer
from app.modules.simbroker.ports import (
    BarProtocol,
    CorporateActionFeedProtocol,
    MarketDataFeedProtocol,
)
from app.modules.simbroker.risk import RiskAnalyzer
from app.modules.simbroker.schemas import (
    AccountCreate,
    AccountOverview,
    AccountResponse,
    FeeModelConfig,
    OrderCreate,
    OrderResponse,
    PerformanceMetrics,
    PositionResponse,
    RiskOverview,
    TradeJournalResponse,
    TradeJournalUpdate,
    TradeResponse,
)
from app.modules.simbroker.validator import OrderValidator

logger = structlog.get_logger(__name__)

__all__ = ["SimService"]

_QUANTIZE_CASH = Decimal("0.0001")


class SimService:
    """模拟盘门面服务。"""

    def __init__(
        self,
        session: AsyncSession,
        market_feed: MarketDataFeedProtocol | None = None,
        corporate_feed: CorporateActionFeedProtocol | None = None,
    ) -> None:
        self.session = session
        self.market_feed = market_feed
        self.corporate_feed = corporate_feed
        self.accounting = AccountingEngine()

    async def get_account_entity(
        self, account_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> SimAccount:
        """根据 ID 加载 SimAccount 实体并校验租户权限。"""
        stmt = select(SimAccount).where(SimAccount.id == account_id)
        res = await self.session.execute(stmt)
        account = res.scalar_one_or_none()
        if account is None:
            raise NotFound(f"SimAccount {account_id} not found")
        if user_id is not None and account.user_id != user_id:
            # 越权与不存在同码（C10）
            raise NotFound(f"SimAccount {account_id} not found")
        return account

    async def create_account(self, user_id: uuid.UUID, req: AccountCreate) -> AccountResponse:
        """创建新的模拟盘账户。"""
        account = SimAccount(
            user_id=user_id,
            name=req.name,
            initial_cash=req.initial_cash,
            cash=req.initial_cash,
            fee_model=req.fee_model.model_dump(),
            slippage_bps=req.slippage_bps,
            pdt_enabled=req.pdt_enabled,
            status="active",
        )
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)
        return AccountResponse.model_validate(account)

    async def list_accounts(self, user_id: uuid.UUID) -> list[AccountResponse]:
        """获取当前用户所有模拟账户列表。"""
        stmt = select(SimAccount).where(SimAccount.user_id == user_id)
        res = await self.session.execute(stmt)
        accounts = res.scalars().all()
        return [AccountResponse.model_validate(a) for a in accounts]

    async def get_account_overview(
        self, account_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> AccountOverview:
        """获取账户实时概览（含市值、净值、盈亏及 PDT 状态）。"""
        account = await self.get_account_entity(account_id, user_id)

        # 加载持仓计算实时市值
        pos_stmt = select(SimPosition).where(
            SimPosition.account_id == account_id, SimPosition.qty > Decimal("0")
        )
        pos_res = await self.session.execute(pos_stmt)
        positions = pos_res.scalars().all()

        total_market_value = Decimal("0.0000")
        for pos in positions:
            price = None
            if self.market_feed is not None:
                price = self.market_feed.get_latest_price(pos.symbol)
            if price is None:
                price = pos.avg_cost
            total_market_value += (pos.qty * price).quantize(_QUANTIZE_CASH, rounding=ROUND_HALF_UP)

        equity = (account.cash + total_market_value).quantize(
            _QUANTIZE_CASH, rounding=ROUND_HALF_UP
        )
        total_pnl = (equity - account.initial_cash).quantize(_QUANTIZE_CASH, rounding=ROUND_HALF_UP)
        total_pnl_pct = (
            (total_pnl / account.initial_cash * Decimal("100")).quantize(
                _QUANTIZE_CASH, rounding=ROUND_HALF_UP
            )
            if account.initial_cash > Decimal("0")
            else Decimal("0.0000")
        )

        # 当日盈亏：从昨日快照对比（若无昨日快照则对比 initial_cash）
        snap_stmt = (
            select(EquitySnapshot)
            .where(EquitySnapshot.account_id == account_id)
            .order_by(EquitySnapshot.trade_date.desc())
            .limit(1)
        )
        snap_res = await self.session.execute(snap_stmt)
        last_snap = snap_res.scalar_one_or_none()
        baseline_equity = last_snap.equity if last_snap is not None else account.initial_cash

        daily_pnl = (equity - baseline_equity).quantize(_QUANTIZE_CASH, rounding=ROUND_HALF_UP)
        daily_pnl_pct = (
            (daily_pnl / baseline_equity * Decimal("100")).quantize(
                _QUANTIZE_CASH, rounding=ROUND_HALF_UP
            )
            if baseline_equity > Decimal("0")
            else Decimal("0.0000")
        )

        # PDT 状态
        pdt_count = 0
        pdt_warn = False
        if account.pdt_enabled:
            trades_stmt = select(SimTrade).where(SimTrade.account_id == account_id)
            trades_res = await self.session.execute(trades_stmt)
            trades = list(trades_res.scalars().all())
            today = date.today()
            window_dates = [today - timedelta(days=i) for i in range(7)]
            pdt_count = PdtEngine.count_day_trades(trades, window_dates)
            status_eval = PdtEngine.evaluate(
                equity=equity,
                pdt_enabled=account.pdt_enabled,
                current_day_trades_count=pdt_count,
            )
            pdt_warn = status_eval.warning

        return AccountOverview(
            id=account.id,
            name=account.name,
            status=account.status,
            initial_cash=account.initial_cash,
            cash=account.cash,
            market_value=total_market_value,
            equity=equity,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            pdt_day_trades_count=pdt_count,
            pdt_warning=pdt_warn,
        )

    async def deposit(
        self, account_id: uuid.UUID, amount: Decimal, user_id: uuid.UUID | None = None
    ) -> Decimal:
        """账户存入资金。"""
        account = await self.get_account_entity(account_id, user_id)
        new_cash = self.accounting.deposit(account, amount)
        await self.session.commit()
        return new_cash

    async def withdraw(
        self, account_id: uuid.UUID, amount: Decimal, user_id: uuid.UUID | None = None
    ) -> Decimal:
        """账户提取资金。"""
        account = await self.get_account_entity(account_id, user_id)
        try:
            new_cash = self.accounting.withdraw(account, amount)
        except InsufficientCashError as exc:
            raise StateConflict(str(exc)) from exc
        await self.session.commit()
        return new_cash

    async def reset_account(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        initial_cash: Decimal | None = None,
    ) -> AccountOverview:
        """重置模拟盘账户（单事务原子完成）。

        1. 严格校验租户隔离；
        2. 取消所有未完全成交的挂单（pending / accepted / submitted）；
        3. 清空所有标的持仓；
        4. 恢复现金余额与权益为初始本金（或指定本金）；
        5. 记录审计日志并返回最新概览。
        """
        account = await self.get_account_entity(account_id, user_id)

        # 1. 恢复初始本金与现金
        if initial_cash is not None:
            if initial_cash <= Decimal("0"):
                raise ValueError("Initial cash must be positive")
            account.initial_cash = initial_cash.quantize(_QUANTIZE_CASH, rounding=ROUND_HALF_UP)
        account.cash = account.initial_cash

        # 2. 取消所有未成交委托挂单
        open_orders_stmt = select(SimOrder).where(
            SimOrder.account_id == account_id,
            SimOrder.status.in_(["pending", "accepted", "submitted"]),
        )
        orders_res = await self.session.execute(open_orders_stmt)
        for order in orders_res.scalars().all():
            order.status = "cancelled"
            order.reject_reason = "Account reset"
            record_simbroker_order(status="cancelled")

        # 3. 清空当前所有标的持仓
        pos_stmt = select(SimPosition).where(SimPosition.account_id == account_id)
        pos_res = await self.session.execute(pos_stmt)
        for pos in pos_res.scalars().all():
            await self.session.delete(pos)

        # 4. 更新/生成当日净值快照基准
        today = date.today()
        snap_stmt = select(EquitySnapshot).where(
            EquitySnapshot.account_id == account_id,
            EquitySnapshot.trade_date == today,
        )
        snap_res = await self.session.execute(snap_stmt)
        today_snap = snap_res.scalar_one_or_none()
        if today_snap is not None:
            today_snap.cash = account.cash
            today_snap.market_value = Decimal("0.0000")
            today_snap.equity = account.cash
            today_snap.drawdown = Decimal("0.000000")

        # 5. 提交原子事务并审计记录
        await self.session.commit()
        await self.session.refresh(account)

        logger.info(
            "simbroker.account_reset_success",
            account_id=str(account_id),
            user_id=str(user_id),
            initial_cash=str(account.initial_cash),
            cash=str(account.cash),
        )

        return await self.get_account_overview(account_id, user_id)

    async def submit_order(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        req: OrderCreate,
        idempotency_key: str,
    ) -> OrderResponse:
        """提交订单（具备幂等拦截、前置风控校验与挂单落库）。"""
        account = await self.get_account_entity(account_id, user_id)

        # 1. 幂等性检测：若已有相同 idempotency_key，直接返回历史订单
        idem_stmt = select(SimOrder).where(
            SimOrder.account_id == account_id,
            SimOrder.idempotency_key == idempotency_key,
        )
        idem_res = await self.session.execute(idem_stmt)
        existing_order = idem_res.scalar_one_or_none()
        if existing_order is not None:
            logger.info(
                "Idempotent order replay",
                account_id=str(account_id),
                order_id=str(existing_order.id),
                idempotency_key=idempotency_key,
            )
            return OrderResponse.model_validate(existing_order)

        # 2. 查询该标的持仓情况
        pos_stmt = select(SimPosition).where(
            SimPosition.account_id == account_id,
            SimPosition.symbol == req.symbol,
        )
        pos_res = await self.session.execute(pos_stmt)
        pos = pos_res.scalar_one_or_none()
        pos_qty = pos.qty if pos is not None else Decimal("0.0000")

        # 3. 行情参考价与总净值
        market_price = None
        if self.market_feed is not None:
            market_price = self.market_feed.get_latest_price(req.symbol)

        overview = await self.get_account_overview(account_id, user_id)

        # 4. 执行前置规则校验
        fee_config = FeeModelConfig.model_validate(account.fee_model)
        val_result = OrderValidator.validate(
            order_req=req,
            account_cash=account.cash,
            account_slippage_bps=account.slippage_bps,
            account_fee_model=fee_config,
            account_pdt_enabled=account.pdt_enabled,
            account_equity=overview.equity,
            current_position_qty=pos_qty,
            current_market_price=market_price,
            rolling_day_trades=overview.pdt_day_trades_count,
        )

        order_status = "accepted" if val_result.is_valid else "rejected"
        reject_reason = val_result.reject_reason

        # 5. 落库持久化订单
        order = SimOrder(
            user_id=user_id,
            account_id=account_id,
            symbol=req.symbol,
            side=req.side,
            type=req.type,
            qty=req.qty,
            limit_price=req.limit_price,
            stop_price=req.stop_price,
            tif=req.tif,
            status=order_status,
            idempotency_key=idempotency_key,
            source=req.source,
            ai_report_id=req.ai_report_id,
            note=req.note,
            reject_reason=reject_reason,
        )
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)

        record_simbroker_order(status=order_status)

        logger.info(
            "Submitted order",
            order_id=str(order.id),
            symbol=order.symbol,
            side=order.side,
            qty=str(order.qty),
            status=order.status,
            reject_reason=reject_reason,
        )

        return OrderResponse.model_validate(order)

    async def cancel_order(
        self,
        account_id: uuid.UUID,
        order_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> OrderResponse:
        """撤销挂单。"""
        await self.get_account_entity(account_id, user_id)

        stmt = select(SimOrder).where(
            SimOrder.id == order_id,
            SimOrder.account_id == account_id,
        )
        res = await self.session.execute(stmt)
        order = res.scalar_one_or_none()
        if order is None:
            raise NotFound(f"Order {order_id} not found")

        if order.status in ("filled", "cancelled", "rejected", "expired"):
            raise StateConflict(f"Cannot cancel order in terminal status '{order.status}'")

        order.status = "cancelled"
        await self.session.commit()
        await self.session.refresh(order)
        record_simbroker_order(status="cancelled")
        return OrderResponse.model_validate(order)

    async def list_orders(
        self,
        account_id: uuid.UUID,
        status: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[OrderResponse]:
        """查询订单列表。"""
        await self.get_account_entity(account_id, user_id)

        stmt = select(SimOrder).where(SimOrder.account_id == account_id)
        if status:
            stmt = stmt.where(SimOrder.status == status)
        stmt = stmt.order_by(SimOrder.created_at.desc())

        res = await self.session.execute(stmt)
        orders = res.scalars().all()
        return [OrderResponse.model_validate(o) for o in orders]

    async def get_positions(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> list[PositionResponse]:
        """获取当前活跃持仓列表。"""
        await self.get_account_entity(account_id, user_id)

        stmt = (
            select(SimPosition)
            .where(
                SimPosition.account_id == account_id,
                SimPosition.qty > Decimal("0"),
            )
            .order_by(SimPosition.symbol)
        )
        res = await self.session.execute(stmt)
        positions = res.scalars().all()

        overview = await self.get_account_overview(account_id, user_id)
        total_equity = overview.equity

        result: list[PositionResponse] = []
        for p in positions:
            price = None
            if self.market_feed is not None:
                price = self.market_feed.get_latest_price(p.symbol)
            if price is None:
                price = p.avg_cost

            market_val = (p.qty * price).quantize(_QUANTIZE_CASH, rounding=ROUND_HALF_UP)
            unrealized_pnl = ((price - p.avg_cost) * p.qty).quantize(
                _QUANTIZE_CASH, rounding=ROUND_HALF_UP
            )
            unrealized_pnl_pct = (
                ((price - p.avg_cost) / p.avg_cost * Decimal("100")).quantize(
                    _QUANTIZE_CASH, rounding=ROUND_HALF_UP
                )
                if p.avg_cost > Decimal("0")
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
                    id=p.id,
                    account_id=p.account_id,
                    symbol=p.symbol,
                    qty=p.qty,
                    avg_cost=p.avg_cost,
                    current_price=price,
                    market_value=market_val,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                    realized_pnl=p.realized_pnl,
                    weight_pct=weight_pct,
                )
            )

        return result

    async def get_trades(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> list[TradeResponse]:
        """获取成交明细列表。"""
        await self.get_account_entity(account_id, user_id)

        stmt = (
            select(SimTrade)
            .where(SimTrade.account_id == account_id)
            .order_by(SimTrade.executed_at.desc())
        )
        res = await self.session.execute(stmt)
        trades = res.scalars().all()
        return [TradeResponse.model_validate(t) for t in trades]

    async def get_performance(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> PerformanceMetrics:
        """计算全周期投资绩效。"""
        account = await self.get_account_entity(account_id, user_id)
        overview = await self.get_account_overview(account_id, user_id)

        snap_stmt = (
            select(EquitySnapshot)
            .where(EquitySnapshot.account_id == account_id)
            .order_by(EquitySnapshot.trade_date)
        )
        snap_res = await self.session.execute(snap_stmt)
        snapshots = snap_res.scalars().all()

        trades_stmt = select(SimTrade).where(SimTrade.account_id == account_id)
        trades_res = await self.session.execute(trades_stmt)
        trades = trades_res.scalars().all()

        return PerformanceAnalyzer.analyze(
            account_id=account_id,
            initial_cash=account.initial_cash,
            current_equity=overview.equity,
            equity_snapshots=snapshots,
            closed_trades=trades,
            benchmark_feed=self.market_feed,
        )

    async def get_risk(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> RiskOverview:
        """获取持仓风险体检诊断报告。"""
        account = await self.get_account_entity(account_id, user_id)
        overview = await self.get_account_overview(account_id, user_id)

        pos_stmt = select(SimPosition).where(
            SimPosition.account_id == account_id, SimPosition.qty > Decimal("0")
        )
        pos_res = await self.session.execute(pos_stmt)
        positions = pos_res.scalars().all()

        return RiskAnalyzer.analyze(
            account_id=account_id,
            account_cash=account.cash,
            positions=positions,
            market_feed=self.market_feed,
            rolling_day_trades=overview.pdt_day_trades_count,
            pdt_warning=overview.pdt_warning,
        )

    async def update_trade_journal(
        self,
        trade_id: uuid.UUID,
        req: TradeJournalUpdate,
        user_id: uuid.UUID | None = None,
    ) -> TradeJournalResponse:
        """更新交易复盘日志。"""
        trade_stmt = select(SimTrade).where(SimTrade.id == trade_id)
        trade_res = await self.session.execute(trade_stmt)
        trade = trade_res.scalar_one_or_none()
        if trade is None:
            raise NotFound(f"Trade {trade_id} not found")

        if user_id is not None and trade.user_id != user_id:
            raise NotFound(f"Trade {trade_id} not found")

        journal_stmt = select(TradeJournal).where(TradeJournal.trade_id == trade_id)
        journal_res = await self.session.execute(journal_stmt)
        journal = journal_res.scalar_one_or_none()

        now = datetime.now(UTC)
        if journal is None:
            journal = TradeJournal(
                trade_id=trade_id,
                notes=req.notes,
                tags=req.tags,
                emotion=req.emotion,
            )
            self.session.add(journal)
        else:
            journal.notes = req.notes
            journal.tags = req.tags
            journal.emotion = req.emotion
            journal.updated_at = now

        await self.session.commit()
        await self.session.refresh(journal)
        return TradeJournalResponse.model_validate(journal)

    async def process_market_close(
        self,
        account_id: uuid.UUID,
        trade_date: date,
        user_id: uuid.UUID | None = None,
    ) -> MarketCloseResult:
        """执行日终收盘批处理。"""
        account = await self.get_account_entity(account_id, user_id)

        pos_stmt = select(SimPosition).where(SimPosition.account_id == account_id)
        pos_res = await self.session.execute(pos_stmt)
        positions = pos_res.scalars().all()

        order_stmt = select(SimOrder).where(
            SimOrder.account_id == account_id,
            SimOrder.status.in_(["pending", "accepted"]),
        )
        order_res = await self.session.execute(order_stmt)
        open_orders = order_res.scalars().all()

        snap_stmt = (
            select(EquitySnapshot)
            .where(EquitySnapshot.account_id == account_id)
            .order_by(EquitySnapshot.equity.desc())
            .limit(1)
        )
        snap_res = await self.session.execute(snap_stmt)
        peak_snap = snap_res.scalar_one_or_none()
        hist_peak = peak_snap.equity if peak_snap is not None else account.initial_cash

        res = MarketCloseBatch.execute(
            account=account,
            positions=positions,
            open_orders=open_orders,
            trade_date=trade_date,
            market_feed=self.market_feed,
            historical_peak_equity=hist_peak,
        )

        if res.snapshot is not None:
            self.session.add(res.snapshot)
        await self.session.commit()
        return res

    async def process_bar(
        self,
        account_id: uuid.UUID,
        symbol: str,
        bar: BarProtocol,
        user_id: uuid.UUID | None = None,
    ) -> list[TradeResponse]:
        """根据单根 K 线撮合挂单并完成记账落地。"""
        account = await self.get_account_entity(account_id, user_id)

        order_stmt = select(SimOrder).where(
            SimOrder.account_id == account_id,
            SimOrder.symbol == symbol,
            SimOrder.status.in_(["pending", "accepted"]),
        )
        order_res = await self.session.execute(order_stmt)
        orders = order_res.scalars().all()

        fee_config = FeeModelConfig.model_validate(account.fee_model)
        executed_trades: list[TradeResponse] = []

        for ord in orders:
            match_res = MatchingEngine.match_order(
                order=ord,
                bar=bar,
                slippage_bps=account.slippage_bps,
                fee_model=fee_config,
            )

            if match_res.status == "filled" and match_res.fill_price is not None:
                # 加载持仓
                pos_stmt = select(SimPosition).where(
                    SimPosition.account_id == account_id,
                    SimPosition.symbol == symbol,
                )
                pos_res = await self.session.execute(pos_stmt)
                pos = pos_res.scalar_one_or_none()
                if pos is None:
                    pos = SimPosition(
                        user_id=account.user_id,
                        account_id=account.id,
                        symbol=symbol,
                        qty=Decimal("0.0000"),
                        avg_cost=Decimal("0.0000"),
                        realized_pnl=Decimal("0.0000"),
                    )
                    self.session.add(pos)
                    await self.session.flush()

                rec = self.accounting.execute_trade(
                    account=account,
                    symbol=symbol,
                    side=ord.side,  # type: ignore[arg-type]
                    qty=match_res.filled_qty,
                    price=match_res.fill_price,
                    fee=match_res.fee,
                    position=pos,
                    executed_at=match_res.executed_at,
                )

                trade = AccountingEngine.create_sim_trade(
                    record=rec,
                    user_id=account.user_id,
                    account_id=account.id,
                    order_id=ord.id,
                )
                self.session.add(trade)
                ord.status = "filled"
                await self.session.flush()
                await self.session.refresh(trade)
                executed_trades.append(TradeResponse.model_validate(trade))

        await self.session.commit()
        if executed_trades:
            record_simbroker_trade(len(executed_trades))
            for _ in executed_trades:
                record_simbroker_order(status="filled")
        return executed_trades
