"""M4 记账引擎、持仓管理、平均成本法与财务不变量（T04），`CONTRACTS.md §3`。

实现加权平均成本法（Weighted Average Cost）、出入金管理、并发幂等保护与三大财务核心不变量校验：
1. 现金守恒不变量：
   cash == initial_cash + sum(deposits) - sum(withdrawals) + sum(sells) - sum(buys) - sum(fees)
2. 净值恒等不变量：equity == cash + sum(qty * current_price)
3. 持仓非负不变量：对任意标的持仓 qty >= 0，严禁超卖。
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

import structlog

from app.modules.simbroker.models import SimTrade

logger = structlog.get_logger(__name__)

__all__ = [
    "AccountingEngine",
    "AccountingError",
    "AccountEquitySummary",
    "AccountState",
    "DuplicateTransactionError",
    "InsufficientCashError",
    "InsufficientPositionError",
    "InvalidAmountError",
    "InvariantsReport",
    "PositionMetrics",
    "PositionState",
    "TradeExecutionRecord",
]

_DEFAULT_QUANTIZE = Decimal("0.0001")


class AccountingError(Exception):
    """记账引擎基础异常。"""


class InsufficientCashError(AccountingError):
    """现金不足异常（买入或出金超限）。"""


class InsufficientPositionError(AccountingError):
    """持仓不足异常（超卖防范）。"""


class InvalidAmountError(AccountingError):
    """无效金额或数量异常（非正数或非法格式）。"""


class DuplicateTransactionError(AccountingError):
    """重复提交异常（幂等性拦截）。"""


@dataclass
class AccountState:
    """轻量账户状态容器（适配 SimAccount 实体或内存测试）。"""

    cash: Decimal = Decimal("100000.0000")


@dataclass
class PositionState:
    """轻量持仓状态容器（适配 SimPosition 实体或内存测试）。"""

    symbol: str
    qty: Decimal = Decimal("0.0000")
    avg_cost: Decimal = Decimal("0.0000")
    realized_pnl: Decimal = Decimal("0.0000")


@dataclass(frozen=True)
class TradeExecutionRecord:
    """单笔成交记账完整快照记录。"""

    symbol: str
    side: Literal["buy", "sell"]
    qty: Decimal
    price: Decimal
    fee: Decimal
    cash_before: Decimal
    cash_after: Decimal
    position_qty_before: Decimal
    position_qty_after: Decimal
    avg_cost_before: Decimal
    avg_cost_after: Decimal
    realized_pnl: Decimal
    executed_at: datetime
    idempotency_key: str | None = None


@dataclass(frozen=True)
class PositionMetrics:
    """单个持仓估值与浮动盈亏。"""

    symbol: str
    qty: Decimal
    avg_cost: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    realized_pnl: Decimal


@dataclass(frozen=True)
class AccountEquitySummary:
    """账户整体净值与资产汇总。"""

    cash: Decimal
    market_value: Decimal
    equity: Decimal
    cash_ratio: Decimal
    position_count: int


@dataclass(frozen=True)
class InvariantsReport:
    """财务不变量综合审计报告。"""

    is_valid: bool
    cash_conservation_valid: bool
    equity_identity_valid: bool
    non_negative_positions_valid: bool
    expected_cash: Decimal
    actual_cash: Decimal
    cash_discrepancy: Decimal
    expected_equity: Decimal
    actual_equity: Decimal
    equity_discrepancy: Decimal
    negative_positions: list[tuple[str, Decimal]] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


class AccountingEngine:
    """模拟盘加权平均成本记账与持仓管理引擎。"""

    def __init__(self, quantize_places: Decimal | None = _DEFAULT_QUANTIZE) -> None:
        """初始化记账引擎。

        :param quantize_places: 成本与金额量化精度，默认保留 4 位小数 (Numeric(18, 4))
        """
        self.quantize_places = quantize_places
        self._lock = threading.Lock()
        self._processed_keys: dict[str, TradeExecutionRecord] = {}

    def _quantize(self, val: Decimal) -> Decimal:
        if self.quantize_places is None:
            return val
        return val.quantize(self.quantize_places, rounding=ROUND_HALF_UP)

    def deposit(self, account: Any, amount: Decimal) -> Decimal:
        """账户存入现金。

        :param account: 账户对象（需包含 cash 属性）
        :param amount: 存入金额（必须 > 0）
        :return: 变动后的最新现金
        """
        if amount <= Decimal("0"):
            raise InvalidAmountError(f"Deposit amount must be positive, got {amount}")
        account.cash = self._quantize(account.cash + amount)
        return Decimal(account.cash)

    def withdraw(self, account: Any, amount: Decimal) -> Decimal:
        """账户提取现金。

        :param account: 账户对象（需包含 cash 属性）
        :param amount: 提取金额（必须 > 0 且 <= account.cash）
        :return: 变动后的最新现金
        """
        if amount <= Decimal("0"):
            raise InvalidAmountError(f"Withdrawal amount must be positive, got {amount}")
        if account.cash < amount:
            raise InsufficientCashError(
                f"Insufficient cash for withdrawal: requested {amount}, available {account.cash}"
            )
        account.cash = self._quantize(account.cash - amount)
        return Decimal(account.cash)

    def execute_buy(
        self,
        account: Any,
        symbol: str,
        qty: Decimal,
        price: Decimal,
        fee: Decimal = Decimal("0"),
        position: Any | None = None,
        idempotency_key: str | None = None,
        executed_at: datetime | None = None,
    ) -> TradeExecutionRecord:
        """执行买入记账（原子更新现金与持仓成本）。

        加权平均成本计算逻辑：
        new_qty = old_qty + qty
        new_avg_cost = (old_qty * old_cost + qty * price + fee) / new_qty
        （美股标准：将交易费用并入持仓成本）
        """
        if qty <= Decimal("0"):
            raise InvalidAmountError(f"Buy quantity must be positive, got {qty}")
        if price <= Decimal("0"):
            raise InvalidAmountError(f"Buy price must be positive, got {price}")
        if fee < Decimal("0"):
            raise InvalidAmountError(f"Fee cannot be negative, got {fee}")

        total_cost = self._quantize(qty * price + fee)

        with self._lock:
            if idempotency_key is not None and idempotency_key in self._processed_keys:
                raise DuplicateTransactionError(
                    f"Transaction with idempotency key '{idempotency_key}' already processed"
                )

            if account.cash < total_cost:
                raise InsufficientCashError(
                    f"Insufficient cash for buy: required {total_cost}, available {account.cash}"
                )

            cash_before = account.cash
            cash_after = self._quantize(account.cash - total_cost)

            old_qty = Decimal("0") if position is None else position.qty
            old_cost = Decimal("0") if position is None else position.avg_cost

            new_qty = old_qty + qty
            # 加权成本：(old_qty * old_cost + qty * price + fee) / new_qty
            total_basis = (old_qty * old_cost) + (qty * price) + fee
            new_cost = self._quantize(total_basis / new_qty)

            account.cash = cash_after

            if position is not None:
                position.qty = new_qty
                position.avg_cost = new_cost

            ts = executed_at or datetime.now(UTC)
            record = TradeExecutionRecord(
                symbol=symbol,
                side="buy",
                qty=qty,
                price=price,
                fee=fee,
                cash_before=cash_before,
                cash_after=cash_after,
                position_qty_before=old_qty,
                position_qty_after=new_qty,
                avg_cost_before=old_cost,
                avg_cost_after=new_cost,
                realized_pnl=Decimal("0.0000"),
                executed_at=ts,
                idempotency_key=idempotency_key,
            )

            if idempotency_key is not None:
                self._processed_keys[idempotency_key] = record

            return record

    def execute_sell(
        self,
        account: Any,
        symbol: str,
        qty: Decimal,
        price: Decimal,
        fee: Decimal = Decimal("0"),
        position: Any | None = None,
        idempotency_key: str | None = None,
        executed_at: datetime | None = None,
    ) -> TradeExecutionRecord:
        """执行卖出记账（原子更新现金、持仓数量并结转已实现盈亏）。

        已实现盈亏结转逻辑：
        realized_pnl = (price - avg_cost) * qty - fee
        若清仓（持仓数量归 0），avg_cost 归 0。
        """
        if qty <= Decimal("0"):
            raise InvalidAmountError(f"Sell quantity must be positive, got {qty}")
        if price <= Decimal("0"):
            raise InvalidAmountError(f"Sell price must be positive, got {price}")
        if fee < Decimal("0"):
            raise InvalidAmountError(f"Fee cannot be negative, got {fee}")

        if position is None:
            raise InsufficientPositionError(f"No position found for {symbol} to sell")

        with self._lock:
            if idempotency_key is not None and idempotency_key in self._processed_keys:
                raise DuplicateTransactionError(
                    f"Transaction with idempotency key '{idempotency_key}' already processed"
                )

            if position.qty < qty:
                raise InsufficientPositionError(
                    f"Insufficient position for {symbol}: requested {qty}, available {position.qty}"
                )

            cash_before = account.cash
            net_proceeds = self._quantize(qty * price - fee)
            cash_after = self._quantize(account.cash + net_proceeds)

            old_qty = position.qty
            old_cost = position.avg_cost
            new_qty = old_qty - qty

            # 结转已实现盈亏
            gross_pnl = (price - old_cost) * qty
            trade_realized_pnl = self._quantize(gross_pnl - fee)

            new_cost = Decimal("0.0000") if new_qty == Decimal("0") else old_cost

            account.cash = cash_after
            position.qty = new_qty
            position.avg_cost = new_cost
            position.realized_pnl = self._quantize(position.realized_pnl + trade_realized_pnl)

            ts = executed_at or datetime.now(UTC)
            record = TradeExecutionRecord(
                symbol=symbol,
                side="sell",
                qty=qty,
                price=price,
                fee=fee,
                cash_before=cash_before,
                cash_after=cash_after,
                position_qty_before=old_qty,
                position_qty_after=new_qty,
                avg_cost_before=old_cost,
                avg_cost_after=new_cost,
                realized_pnl=trade_realized_pnl,
                executed_at=ts,
                idempotency_key=idempotency_key,
            )

            if idempotency_key is not None:
                self._processed_keys[idempotency_key] = record

            return record

    def execute_trade(
        self,
        account: Any,
        symbol: str,
        side: Literal["buy", "sell"],
        qty: Decimal,
        price: Decimal,
        fee: Decimal = Decimal("0"),
        position: Any | None = None,
        idempotency_key: str | None = None,
        executed_at: datetime | None = None,
    ) -> TradeExecutionRecord:
        """统一成交记账入口。"""
        if side == "buy":
            return self.execute_buy(
                account=account,
                symbol=symbol,
                qty=qty,
                price=price,
                fee=fee,
                position=position,
                idempotency_key=idempotency_key,
                executed_at=executed_at,
            )
        elif side == "sell":
            return self.execute_sell(
                account=account,
                symbol=symbol,
                qty=qty,
                price=price,
                fee=fee,
                position=position,
                idempotency_key=idempotency_key,
                executed_at=executed_at,
            )
        else:
            raise ValueError(f"Unsupported trade side: {side}")

    def calculate_unrealized_pnl(
        self,
        qty: Decimal,
        avg_cost: Decimal,
        current_price: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """计算持仓浮动盈亏金额与百分比。"""
        if qty == Decimal("0"):
            return Decimal("0.0000"), Decimal("0.0000")
        unrealized_pnl = self._quantize((current_price - avg_cost) * qty)
        if avg_cost > Decimal("0"):
            pct = self._quantize(((current_price - avg_cost) / avg_cost) * Decimal("100"))
        else:
            pct = Decimal("0.0000")
        return unrealized_pnl, pct

    def calculate_position_metrics(
        self,
        position: Any,
        current_price: Decimal,
    ) -> PositionMetrics:
        """计算指定持仓的实时估值与盈亏指标。"""
        market_val = self._quantize(position.qty * current_price)
        unrealized_pnl, unrealized_pct = self.calculate_unrealized_pnl(
            qty=position.qty,
            avg_cost=position.avg_cost,
            current_price=current_price,
        )
        return PositionMetrics(
            symbol=position.symbol,
            qty=position.qty,
            avg_cost=position.avg_cost,
            current_price=current_price,
            market_value=market_val,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pct,
            realized_pnl=position.realized_pnl,
        )

    def calculate_equity_summary(
        self,
        account: Any,
        positions: Sequence[Any],
        current_prices: Mapping[str, Decimal],
    ) -> AccountEquitySummary:
        """计算账户整体净值与持仓市值。"""
        total_market_value = Decimal("0.0000")
        active_positions = 0
        for pos in positions:
            if pos.qty > Decimal("0"):
                active_positions += 1
                price = current_prices.get(pos.symbol, pos.avg_cost)
                total_market_value += pos.qty * price

        total_market_value = self._quantize(total_market_value)
        total_equity = self._quantize(account.cash + total_market_value)
        if total_equity > Decimal("0"):
            cash_ratio = self._quantize((account.cash / total_equity) * Decimal("100"))
        else:
            cash_ratio = Decimal("0.0000")

        return AccountEquitySummary(
            cash=account.cash,
            market_value=total_market_value,
            equity=total_equity,
            cash_ratio=cash_ratio,
            position_count=active_positions,
        )

    def verify_cash_conservation(
        self,
        initial_cash: Decimal,
        deposits: Iterable[Decimal],
        withdrawals: Iterable[Decimal],
        trade_records: Iterable[TradeExecutionRecord],
        current_cash: Decimal,
    ) -> bool:
        """校验现金守恒不变量：
        cash == initial_cash + sum(deposits) - sum(withdrawals) + sum(sells) - sum(buys) - sum(fees)
        """
        dep_sum = sum(deposits, Decimal("0"))
        wtd_sum = sum(withdrawals, Decimal("0"))

        buy_gross = Decimal("0")
        sell_gross = Decimal("0")
        fee_sum = Decimal("0")

        for tr in trade_records:
            fee_sum += tr.fee
            gross = tr.qty * tr.price
            if tr.side == "buy":
                buy_gross += gross
            elif tr.side == "sell":
                sell_gross += gross

        expected = self._quantize(
            initial_cash + dep_sum - wtd_sum + sell_gross - buy_gross - fee_sum
        )
        return self._quantize(current_cash) == expected

    def verify_equity_identity(
        self,
        equity: Decimal,
        cash: Decimal,
        market_value: Decimal,
    ) -> bool:
        """校验净值恒等不变量：equity == cash + market_value。"""
        return self._quantize(equity) == self._quantize(cash + market_value)

    def verify_non_negative_positions(self, positions: Iterable[Any]) -> bool:
        """校验持仓非负不变量：对任意持仓数量 qty >= 0。"""
        return all(pos.qty >= Decimal("0") for pos in positions)

    def audit_invariants(
        self,
        initial_cash: Decimal,
        deposits: Iterable[Decimal],
        withdrawals: Iterable[Decimal],
        trade_records: Iterable[TradeExecutionRecord],
        positions: Sequence[Any],
        current_prices: Mapping[str, Decimal],
        account: Any,
    ) -> InvariantsReport:
        """综合审计并生成财务不变量报告。"""
        dep_list = list(deposits)
        wtd_list = list(withdrawals)
        trades_list = list(trade_records)

        dep_sum = sum(dep_list, Decimal("0"))
        wtd_sum = sum(wtd_list, Decimal("0"))

        buy_gross = Decimal("0")
        sell_gross = Decimal("0")
        fee_sum = Decimal("0")

        for tr in trades_list:
            fee_sum += tr.fee
            gross = tr.qty * tr.price
            if tr.side == "buy":
                buy_gross += gross
            elif tr.side == "sell":
                sell_gross += gross

        expected_cash = self._quantize(
            initial_cash + dep_sum - wtd_sum + sell_gross - buy_gross - fee_sum
        )
        actual_cash = self._quantize(account.cash)
        cash_discrepancy = actual_cash - expected_cash
        cash_valid = cash_discrepancy == Decimal("0")

        summary = self.calculate_equity_summary(account, positions, current_prices)
        expected_equity = self._quantize(summary.cash + summary.market_value)
        actual_equity = summary.equity
        equity_discrepancy = actual_equity - expected_equity
        equity_valid = equity_discrepancy == Decimal("0")

        negative_positions: list[tuple[str, Decimal]] = []
        for pos in positions:
            if pos.qty < Decimal("0"):
                negative_positions.append((pos.symbol, pos.qty))
        non_negative_valid = len(negative_positions) == 0

        violations: list[str] = []
        if not cash_valid:
            violations.append(
                f"Cash conservation broken: expected {expected_cash}, "
                f"got {actual_cash} (diff={cash_discrepancy})"
            )
        if not equity_valid:
            violations.append(
                f"Equity identity broken: expected {expected_equity}, "
                f"got {actual_equity} (diff={equity_discrepancy})"
            )
        if not non_negative_valid:
            violations.append(
                f"Non-negative position invariant violated: negative positions={negative_positions}"
            )

        is_all_valid = cash_valid and equity_valid and non_negative_valid

        return InvariantsReport(
            is_valid=is_all_valid,
            cash_conservation_valid=cash_valid,
            equity_identity_valid=equity_valid,
            non_negative_positions_valid=non_negative_valid,
            expected_cash=expected_cash,
            actual_cash=actual_cash,
            cash_discrepancy=cash_discrepancy,
            expected_equity=expected_equity,
            actual_equity=actual_equity,
            equity_discrepancy=equity_discrepancy,
            negative_positions=negative_positions,
            violations=violations,
        )

    def has_processed_key(self, idempotency_key: str) -> bool:
        """检查指定幂等键是否已记账。"""
        with self._lock:
            return idempotency_key in self._processed_keys

    def get_processed_record(self, idempotency_key: str) -> TradeExecutionRecord | None:
        """获取已记账幂等记录。"""
        with self._lock:
            return self._processed_keys.get(idempotency_key)

    def clear_idempotency_keys(self) -> None:
        """清空内存幂等注册表。"""
        with self._lock:
            self._processed_keys.clear()

    @staticmethod
    def create_sim_trade(
        record: TradeExecutionRecord,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        order_id: uuid.UUID,
    ) -> SimTrade:
        """基于记账结果构建 SimTrade ORM 实体。"""
        return SimTrade(
            user_id=user_id,
            account_id=account_id,
            order_id=order_id,
            symbol=record.symbol,
            side=record.side,
            qty=record.qty,
            price=record.price,
            fee=record.fee,
            realized_pnl=record.realized_pnl,
            executed_at=record.executed_at,
        )
