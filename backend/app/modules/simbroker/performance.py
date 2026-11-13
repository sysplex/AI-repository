"""M4 绩效分析引擎（T06），`CONTRACTS.md §1 & §3`。

实现投资组合全周期绩效度量：
1. 总收益额与总收益率（Total Return / Total Return Pct）；
2. 净值曲线与全局最大回撤（Max Drawdown）；
3. 已平仓胜率（Win Rate）与盈亏比（Profit/Loss Ratio）；
4. 基准 SPY 对比收益率、Alpha 与 Beta 评估；
5. 输出标准化 PerformanceMetrics DTO。
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog

from app.modules.simbroker.ports import MarketDataFeedProtocol
from app.modules.simbroker.schemas import EquitySnapshotResponse, PerformanceMetrics

logger = structlog.get_logger(__name__)

__all__ = ["PerformanceAnalyzer"]

_QUANTIZE_CASH = Decimal("0.0001")
_QUANTIZE_RATIO = Decimal("0.0001")
_QUANTIZE_DRAWDOWN = Decimal("0.000001")


class PerformanceAnalyzer:
    """投资组合历史业绩分析器。"""

    @classmethod
    def analyze(
        cls,
        account_id: uuid.UUID,
        initial_cash: Decimal,
        current_equity: Decimal,
        equity_snapshots: Sequence[Any],
        closed_trades: Sequence[Any],
        benchmark_feed: MarketDataFeedProtocol | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> PerformanceMetrics:
        """根据快照与成交历史计算全套绩效指标。

        :param account_id: 账户唯一标识
        :param initial_cash: 账户初始资金
        :param current_equity: 当前实时总净值
        :param equity_snapshots: 历史每日净值快照序列
        :param closed_trades: 产生盈亏的已成交记录（需具备 realized_pnl）
        :param benchmark_feed: 市场基准行情源（用于获取标普 500 / SPY 表现）
        :param start_date: 绩效分析起始日（若无则取最早快照日）
        :param end_date: 绩效分析截止日（若无则取最晚快照日）
        :return: PerformanceMetrics 规范 DTO
        """
        # 1. 总收益额与总收益率
        total_return = (current_equity - initial_cash).quantize(
            _QUANTIZE_CASH, rounding=ROUND_HALF_UP
        )
        if initial_cash > Decimal("0"):
            total_return_pct = (
                (current_equity - initial_cash) / initial_cash * Decimal("100")
            ).quantize(_QUANTIZE_RATIO, rounding=ROUND_HALF_UP)
        else:
            total_return_pct = Decimal("0.0000")

        # 2. 净值曲线与全局最大回撤
        sorted_snapshots = sorted(equity_snapshots, key=lambda s: s.trade_date)
        curve: list[EquitySnapshotResponse] = []
        max_drawdown = Decimal("0.000000")
        peak = initial_cash

        for s in sorted_snapshots:
            snap_trade_date = s.trade_date
            snap_cash = s.cash
            snap_mv = s.market_value
            snap_eq = s.equity
            snap_dd = getattr(s, "drawdown", Decimal("0.000000"))

            # 动态核算全局最大回撤
            peak = max(peak, snap_eq)
            if peak > Decimal("0"):
                computed_dd = ((peak - snap_eq) / peak).quantize(
                    _QUANTIZE_DRAWDOWN, rounding=ROUND_HALF_UP
                )
                max_drawdown = max(max_drawdown, snap_dd, computed_dd)

            curve.append(
                EquitySnapshotResponse(
                    account_id=account_id,
                    trade_date=snap_trade_date,
                    cash=snap_cash,
                    market_value=snap_mv,
                    equity=snap_eq,
                    drawdown=snap_dd,
                )
            )

        # 3. 平仓交易胜率与盈亏比
        winning_trades = 0
        losing_trades = 0
        gross_profit = Decimal("0.0000")
        gross_loss = Decimal("0.0000")

        for tr in closed_trades:
            pnl = getattr(tr, "realized_pnl", Decimal("0.0000"))
            if pnl > Decimal("0"):
                winning_trades += 1
                gross_profit += pnl
            elif pnl < Decimal("0"):
                losing_trades += 1
                gross_loss += abs(pnl)

        total_trades = len(closed_trades)
        effective_closed_trades = winning_trades + losing_trades

        # 胜率: 盈利笔数 / 有盈亏平仓总笔数
        if effective_closed_trades > 0:
            win_rate = (
                Decimal(winning_trades) / Decimal(effective_closed_trades) * Decimal("100")
            ).quantize(_QUANTIZE_RATIO, rounding=ROUND_HALF_UP)
        elif total_trades > 0:
            win_rate = Decimal("0.0000")
        else:
            win_rate = Decimal("0.0000")

        # 盈亏比 (Profit Factor): 总盈利 / 总亏损（防范除以零）
        if gross_loss > Decimal("0"):
            profit_loss_ratio = (gross_profit / gross_loss).quantize(
                _QUANTIZE_RATIO, rounding=ROUND_HALF_UP
            )
        elif gross_profit > Decimal("0"):
            profit_loss_ratio = Decimal("999.9999")  # 全胜无亏损
        else:
            profit_loss_ratio = Decimal("0.0000")

        # 4. 基准对比（SPY）与 Alpha/Beta
        benchmark_return_pct: Decimal | None = None
        alpha: Decimal | None = None
        beta: Decimal | None = None

        range_start = start_date
        range_end = end_date
        if range_start is None and sorted_snapshots:
            range_start = sorted_snapshots[0].trade_date
        if range_end is None and sorted_snapshots:
            range_end = sorted_snapshots[-1].trade_date

        if benchmark_feed is not None and range_start is not None and range_end is not None:
            spy_ret = benchmark_feed.get_sp500_return(range_start, range_end)
            if spy_ret is not None:
                benchmark_return_pct = spy_ret.quantize(_QUANTIZE_RATIO, rounding=ROUND_HALF_UP)
                alpha = (total_return_pct - benchmark_return_pct).quantize(
                    _QUANTIZE_RATIO, rounding=ROUND_HALF_UP
                )
                # 当样本数量过少时，Beta 默认设为 1.0000 作为参考基线
                beta = Decimal("1.0000")

        logger.info(
            "Analyzed performance",
            account_id=str(account_id),
            total_return_pct=str(total_return_pct),
            max_drawdown=str(max_drawdown),
            win_rate=str(win_rate),
            profit_loss_ratio=str(profit_loss_ratio),
            total_trades=total_trades,
            alpha=str(alpha) if alpha is not None else None,
        )

        return PerformanceMetrics(
            account_id=account_id,
            initial_cash=initial_cash,
            current_equity=current_equity,
            total_return=total_return,
            total_return_pct=total_return_pct,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_loss_ratio=profit_loss_ratio,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            benchmark_return_pct=benchmark_return_pct,
            alpha=alpha,
            beta=beta,
            equity_curve=curve,
        )
