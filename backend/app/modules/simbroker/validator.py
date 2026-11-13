"""M4 模拟盘订单前置校验引擎（T02），`CONTRACTS.md §3`。

实现资金充足性校验（含滑点上滑与手续费缓冲）、超卖防范、参数合法性与 PDT 限制拦截。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.modules.simbroker.fee import calculate_fee, calculate_slippage
from app.modules.simbroker.pdt import PdtEngine
from app.modules.simbroker.schemas import FeeModelConfig, OrderCreate

__all__ = ["OrderValidator", "ValidationResult"]

_SYMBOL_REGEX = re.compile(r"^[A-Za-z0-9\.\-]{1,20}$")


@dataclass(frozen=True)
class ValidationResult:
    """订单前置校验判定结果"""

    is_valid: bool
    error_code: str | None = None
    reject_reason: str | None = None
    estimated_price: Decimal | None = None
    estimated_fee: Decimal | None = None
    estimated_total_cost: Decimal | None = None


class OrderValidator:
    """订单前置校验引擎。"""

    @classmethod
    def validate(
        cls,
        order_req: OrderCreate,
        account_cash: Decimal,
        account_slippage_bps: Decimal,
        account_fee_model: FeeModelConfig,
        account_pdt_enabled: bool,
        account_equity: Decimal,
        current_position_qty: Decimal = Decimal("0"),
        current_market_price: Decimal | None = None,
        rolling_day_trades: int = 0,
        is_same_day_roundtrip: bool = False,
    ) -> ValidationResult:
        """执行全套订单前置规则校验。

        :param order_req: 客户端提交的下单请求 DTO
        :param account_cash: 账户可用现金
        :param account_slippage_bps: 账户配置的滑点基点
        :param account_fee_model: 账户手续费模型
        :param account_pdt_enabled: 账户是否开启 PDT 监控
        :param account_equity: 账户实时总净值
        :param current_position_qty: 该标的当前可用持仓数（卖单使用）
        :param current_market_price: 当前市场参考现价（市价单与参考使用）
        :param rolling_day_trades: 过去 5 个交易日内已累计的日内交易数
        :param is_same_day_roundtrip: 本笔订单是否会在今日平仓构成 Day Trade
        :return: ValidationResult
        """
        # 1. 标的代码校验
        sym = order_req.symbol.strip().upper()
        if not sym or not _SYMBOL_REGEX.match(sym):
            return ValidationResult(
                is_valid=False,
                error_code="INVALID_ORDER_PARAMS",
                reject_reason=(
                    f"INVALID_ORDER_PARAMS: Invalid stock symbol format '{order_req.symbol}'."
                ),
            )

        # 2. 数量校验
        if order_req.qty <= Decimal("0"):
            return ValidationResult(
                is_valid=False,
                error_code="INVALID_ORDER_PARAMS",
                reject_reason=(
                    f"INVALID_ORDER_PARAMS: Order quantity must be positive, got {order_req.qty}."
                ),
            )

        # 3. 价格参数校验
        if order_req.type == "limit":
            if order_req.limit_price is None or order_req.limit_price <= Decimal("0"):
                return ValidationResult(
                    is_valid=False,
                    error_code="INVALID_ORDER_PARAMS",
                    reject_reason=(
                        "INVALID_ORDER_PARAMS: Limit order requires a positive limit_price."
                    ),
                )
        elif order_req.type == "stop" and (
            order_req.stop_price is None or order_req.stop_price <= Decimal("0")
        ):
            return ValidationResult(
                is_valid=False,
                error_code="INVALID_ORDER_PARAMS",
                reject_reason="INVALID_ORDER_PARAMS: Stop order requires a positive stop_price.",
            )

        # 4. 买单资金充足性校验（包含预估滑点与手续费）
        if order_req.side == "buy":
            base_price: Decimal | None
            if order_req.type == "limit" and order_req.limit_price is not None:
                base_price = order_req.limit_price
            elif order_req.type == "stop" and order_req.stop_price is not None:
                base_price = order_req.stop_price
            else:
                base_price = current_market_price

            if base_price is None or base_price <= Decimal("0"):
                return ValidationResult(
                    is_valid=False,
                    error_code="INVALID_ORDER_PARAMS",
                    reject_reason=(
                        "INVALID_ORDER_PARAMS: Market price required for market order estimation."
                    ),
                )

            est_price = calculate_slippage(base_price, "buy", account_slippage_bps)
            est_fee = calculate_fee(order_req.qty, est_price, account_fee_model)
            required_cash = (order_req.qty * est_price) + est_fee

            if account_cash < required_cash:
                return ValidationResult(
                    is_valid=False,
                    error_code="INSUFFICIENT_FUNDS",
                    reject_reason=(
                        f"INSUFFICIENT_FUNDS: Required ${required_cash:,.2f} "
                        f"(shares: {order_req.qty} @ ${est_price:,.2f} + fee: ${est_fee:,.2f}) "
                        f"exceeds available cash ${account_cash:,.2f}."
                    ),
                    estimated_price=est_price,
                    estimated_fee=est_fee,
                    estimated_total_cost=required_cash,
                )

            return ValidationResult(
                is_valid=True,
                estimated_price=est_price,
                estimated_fee=est_fee,
                estimated_total_cost=required_cash,
            )

        # 5. 卖单超卖防范校验（禁止裸做空）
        if order_req.side == "sell":
            if current_position_qty < order_req.qty:
                return ValidationResult(
                    is_valid=False,
                    error_code="INSUFFICIENT_POSITION",
                    reject_reason=(
                        f"INSUFFICIENT_POSITION: Current position of {current_position_qty} shares "
                        f"is insufficient to sell {order_req.qty} shares."
                    ),
                )

            # 6. PDT 日内交易平仓限制校验
            pdt_status = PdtEngine.evaluate(
                equity=account_equity,
                pdt_enabled=account_pdt_enabled,
                current_day_trades_count=rolling_day_trades,
                is_closing_same_day=is_same_day_roundtrip,
            )
            if pdt_status.is_restricted:
                return ValidationResult(
                    is_valid=False,
                    error_code="PDT_RESTRICTION",
                    reject_reason=pdt_status.message,
                )

            base_price = (
                order_req.limit_price
                if order_req.type == "limit" and order_req.limit_price is not None
                else (
                    order_req.stop_price
                    if order_req.type == "stop" and order_req.stop_price is not None
                    else current_market_price
                )
            )
            est_price = (
                calculate_slippage(base_price, "sell", account_slippage_bps)
                if base_price and base_price > Decimal("0")
                else Decimal("0.0000")
            )
            est_fee = (
                calculate_fee(order_req.qty, est_price, account_fee_model)
                if est_price > Decimal("0")
                else Decimal("0.0000")
            )
            return ValidationResult(
                is_valid=True,
                estimated_price=est_price,
                estimated_fee=est_fee,
                estimated_total_cost=(order_req.qty * est_price) - est_fee,
            )

        return ValidationResult(
            is_valid=False,
            error_code="INVALID_ORDER_PARAMS",
            reject_reason=f"INVALID_ORDER_PARAMS: Unsupported order side '{order_req.side}'.",
        )
