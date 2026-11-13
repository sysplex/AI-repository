"""M4 模拟盘美股 PDT（Pattern Day Trader）规则引擎（T02），`CONTRACTS.md §3`。

美股 FINRA / SEC 标准规则：
- 账户净值低于 $25,000 时，连续 5 个交易日内最多允许 3 次日内回转交易（Day Trade）。
- 第 4 次日内平仓构成 PDT 违规；当 pdt_enabled=True 时进行前置警报与下单拦截。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

__all__ = ["PDT_MIN_EQUITY", "PDT_WARNING_THRESHOLD", "PdtEngine", "PdtStatus"]

PDT_MIN_EQUITY = Decimal("25000.0000")
PDT_WARNING_THRESHOLD = 3
PDT_MAX_DAY_TRADES = 3  # >= 4 次即构成 PDT 限制


@dataclass(frozen=True)
class PdtStatus:
    """PDT 规则判定状态"""

    day_trades_count: int
    is_restricted: bool
    warning: bool
    equity: Decimal
    pdt_enabled: bool
    message: str | None = None


class PdtEngine:
    """美股 PDT 5 交易日滑动窗口监控与规则校验引擎。"""

    @classmethod
    def count_day_trades(
        cls,
        trades: Sequence[Any],
        trade_dates_window: Sequence[date],
    ) -> int:
        """统计在给定的交易日窗口（通常为最近 5 个交易日）内发生的日内回转交易次数。

        日内回转交易定义：同一标的在同一交易日内既存在买入（buy），又存在卖出（sell）。

        :param trades: 历史成交列表，对象需具备 executed_at / trade_date, symbol, side 属性
        :param trade_dates_window: 最近 5 个美东交易日集合
        :return: 日内交易总次数
        """
        valid_dates = set(trade_dates_window)
        # 按 (date, symbol) 分组聚合 side
        day_symbol_sides: dict[tuple[date, str], set[str]] = {}

        for tr in trades:
            t_date: date
            if hasattr(tr, "trade_date"):
                t_date = tr.trade_date
            elif hasattr(tr, "executed_at"):
                t_dt: datetime = tr.executed_at
                t_date = t_dt.date() if isinstance(t_dt, datetime) else t_dt
            else:
                continue

            if t_date not in valid_dates:
                continue

            sym = str(tr.symbol).upper()
            side = str(tr.side).lower()
            key = (t_date, sym)
            if key not in day_symbol_sides:
                day_symbol_sides[key] = set()
            day_symbol_sides[key].add(side)

        count = 0
        for sides in day_symbol_sides.values():
            if "buy" in sides and "sell" in sides:
                count += 1

        return count

    @classmethod
    def evaluate(
        cls,
        equity: Decimal,
        pdt_enabled: bool,
        current_day_trades_count: int,
        is_closing_same_day: bool = False,
    ) -> PdtStatus:
        """评估当前账户的 PDT 合规状态。

        :param equity: 账户当前实时总净值
        :param pdt_enabled: 账户是否开启 PDT 规则控制
        :param current_day_trades_count: 5 日窗口内已累计的日内交易数
        :param is_closing_same_day: 当前下单是否将完成一笔新的当日平仓回转交易
        :return: PdtStatus
        """
        if not pdt_enabled:
            return PdtStatus(
                day_trades_count=current_day_trades_count,
                is_restricted=False,
                warning=False,
                equity=equity,
                pdt_enabled=False,
                message=None,
            )

        # 账户净值达到或超过 25,000 美元不受 PDT 交易次数限制
        if equity >= PDT_MIN_EQUITY:
            return PdtStatus(
                day_trades_count=current_day_trades_count,
                is_restricted=False,
                warning=False,
                equity=equity,
                pdt_enabled=True,
                message="Account equity meets or exceeds $25,000; PDT restrictions waived.",
            )

        # 净值低于 25,000 美元
        effective_count = current_day_trades_count + (1 if is_closing_same_day else 0)

        # 当已达 3 次且当前单子将触发第 4 次日内交易时，予以拦截限制
        is_restricted = effective_count > PDT_MAX_DAY_TRADES
        warning = effective_count >= PDT_WARNING_THRESHOLD

        msg: str | None = None
        if is_restricted:
            msg = (
                f"PDT_RESTRICTION: Account equity (${equity:,.2f}) is below $25,000.00 "
                f"and executing this trade would result in {effective_count} day trades "
                f"within 5 trading days (limit is {PDT_MAX_DAY_TRADES})."
            )
        elif warning:
            msg = (
                f"PDT_WARNING: Account equity (${equity:,.2f}) is below $25,000.00 "
                f"and has accumulated {effective_count} day trades. Approaching limit."
            )

        return PdtStatus(
            day_trades_count=effective_count,
            is_restricted=is_restricted,
            warning=warning,
            equity=equity,
            pdt_enabled=True,
            message=msg,
        )
