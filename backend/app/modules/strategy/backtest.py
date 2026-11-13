"""Lightweight event-driven backtesting engine (M3 / T05).

Simulates trading day-by-day on historical candlestick bars.
Strictly eliminates lookahead bias by feeding StrategyContext with data
only up to the simulated date.
Computes execution records and performance metrics:
- Total Return %, Annualized Return %
- Max Drawdown %
- Win Rate %
- Profit Factor
- Daily Equity Curve
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.modules.strategy.indicators import Bar
from app.modules.strategy.ports import Strategy
from app.modules.strategy.schemas import (
    BacktestRequest,
    BacktestResult,
    EquityPoint,
    StrategyContext,
    TradeRecord,
)


class BacktestEngine:
    """Lightweight event-driven backtesting engine for daily bars."""

    def __init__(self, strategy: Strategy) -> None:
        self._strategy = strategy

    def run(self, bars: Sequence[Bar], req: BacktestRequest) -> BacktestResult:
        """Run daily bar simulation."""
        # 1. Sort bars chronologically
        sorted_bars = sorted(bars, key=lambda b: b.trade_date)

        # Simulation window
        sim_bars = [b for b in sorted_bars if req.start <= b.trade_date <= req.end]

        if not sim_bars:
            return BacktestResult(
                strategy_id=req.strategy_id,
                symbol=req.symbol,
                start=req.start,
                end=req.end,
                initial_capital=req.initial_capital,
                final_equity=req.initial_capital,
                total_return_pct=Decimal("0.0"),
                annualized_return_pct=Decimal("0.0"),
                max_drawdown_pct=Decimal("0.0"),
                win_rate=Decimal("0.0"),
                profit_factor=Decimal("0.0"),
                total_trades=0,
                trades=[],
                equity_curve=[],
            )

        cash = req.initial_capital
        position_shares = 0
        entry_amount = Decimal("0.0")
        active_stop: Decimal | None = None
        active_target: Decimal | None = None
        peak_equity = req.initial_capital

        trades: list[TradeRecord] = []
        equity_curve: list[EquityPoint] = []

        for curr_bar in sim_bars:
            curr_date = curr_bar.trade_date
            close_price = curr_bar.close

            # 2. Check Stop Loss / Take Profit for open position before new evaluation
            if position_shares > 0:
                stop_hit = active_stop is not None and curr_bar.low <= active_stop
                target_hit = active_target is not None and curr_bar.high >= active_target

                if stop_hit:
                    # Execute stop loss (slippage / gap down protection)
                    exec_price = min(curr_bar.open, active_stop) if active_stop else curr_bar.low
                    sell_amount = Decimal(position_shares) * exec_price
                    pnl = sell_amount - entry_amount
                    pnl_pct = (
                        (pnl / entry_amount * Decimal("100"))
                        if entry_amount > Decimal(0)
                        else Decimal(0)
                    )
                    cash += sell_amount

                    trades.append(
                        TradeRecord(
                            trade_date=curr_date,
                            action="sell",
                            price=exec_price,
                            shares=position_shares,
                            amount=sell_amount,
                            pnl=pnl,
                            pnl_pct=pnl_pct,
                            reason="stop_loss",
                        )
                    )
                    position_shares = 0
                    entry_amount = Decimal(0)
                    active_stop = None
                    active_target = None

                elif target_hit:
                    # Execute take profit
                    exec_price = (
                        max(curr_bar.open, active_target) if active_target else curr_bar.high
                    )
                    sell_amount = Decimal(position_shares) * exec_price
                    pnl = sell_amount - entry_amount
                    pnl_pct = (
                        (pnl / entry_amount * Decimal("100"))
                        if entry_amount > Decimal(0)
                        else Decimal(0)
                    )
                    cash += sell_amount

                    trades.append(
                        TradeRecord(
                            trade_date=curr_date,
                            action="sell",
                            price=exec_price,
                            shares=position_shares,
                            amount=sell_amount,
                            pnl=pnl,
                            pnl_pct=pnl_pct,
                            reason="take_profit",
                        )
                    )
                    position_shares = 0
                    entry_amount = Decimal(0)
                    active_stop = None
                    active_target = None

            # 3. Strategy evaluation strictly lookahead-free (data up to curr_date)
            history_bars = [b for b in sorted_bars if b.trade_date <= curr_date]
            ctx = StrategyContext(
                symbol=req.symbol,
                as_of=curr_date,
                bars=history_bars,
                params=req.params,
            )
            signal = self._strategy.evaluate(ctx)

            # 4. Act on signal
            if signal.direction == "long" and position_shares == 0:
                # Use 95% of available cash for position sizing
                alloc_cash = cash * Decimal("0.95")
                shares = int(alloc_cash // close_price)
                if shares > 0:
                    buy_amount = Decimal(shares) * close_price
                    cash -= buy_amount
                    position_shares = shares
                    entry_amount = buy_amount
                    active_stop = signal.levels.get("stop")
                    active_target = signal.levels.get("target")

                    trades.append(
                        TradeRecord(
                            trade_date=curr_date,
                            action="buy",
                            price=close_price,
                            shares=shares,
                            amount=buy_amount,
                            pnl=None,
                            pnl_pct=None,
                            reason=signal.reasons[0] if signal.reasons else "buy_signal",
                        )
                    )

            elif (signal.direction == "flat" and signal.strength > 0 and position_shares > 0) or (
                signal.direction == "short" and position_shares > 0
            ):
                # Strategy exit signal
                sell_amount = Decimal(position_shares) * close_price
                pnl = sell_amount - entry_amount
                pnl_pct = (
                    (pnl / entry_amount * Decimal("100"))
                    if entry_amount > Decimal(0)
                    else Decimal(0)
                )
                cash += sell_amount

                trades.append(
                    TradeRecord(
                        trade_date=curr_date,
                        action="sell",
                        price=close_price,
                        shares=position_shares,
                        amount=sell_amount,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        reason=signal.reasons[0] if signal.reasons else "strategy_exit",
                    )
                )
                position_shares = 0
                entry_amount = Decimal(0)
                active_stop = None
                active_target = None

            # 5. Daily equity sampling
            current_equity = cash + (Decimal(position_shares) * close_price)
            if current_equity > peak_equity:
                peak_equity = current_equity

            drawdown_pct = (
                ((peak_equity - current_equity) / peak_equity * Decimal("100"))
                if peak_equity > Decimal(0)
                else Decimal(0)
            )
            equity_curve.append(
                EquityPoint(
                    trade_date=curr_date,
                    equity=current_equity,
                    cash=cash,
                    drawdown_pct=drawdown_pct,
                )
            )

        # 6. Close any remaining open position at backtest termination
        if position_shares > 0:
            last_bar = sim_bars[-1]
            last_date = last_bar.trade_date
            close_price = last_bar.close
            sell_amount = Decimal(position_shares) * close_price
            pnl = sell_amount - entry_amount
            pnl_pct = (
                (pnl / entry_amount * Decimal("100")) if entry_amount > Decimal(0) else Decimal(0)
            )
            cash += sell_amount

            trades.append(
                TradeRecord(
                    trade_date=last_date,
                    action="sell",
                    price=close_price,
                    shares=position_shares,
                    amount=sell_amount,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    reason="end_of_backtest",
                )
            )
            position_shares = 0
            if equity_curve:
                equity_curve[-1] = EquityPoint(
                    trade_date=last_date,
                    equity=cash,
                    cash=cash,
                    drawdown_pct=equity_curve[-1].drawdown_pct,
                )

        # 7. Compute Summary Performance Metrics
        final_equity = equity_curve[-1].equity if equity_curve else req.initial_capital
        total_return_pct = (
            ((final_equity - req.initial_capital) / req.initial_capital * Decimal("100"))
            if req.initial_capital > Decimal(0)
            else Decimal(0)
        )

        days_count = (req.end - req.start).days
        years = Decimal(days_count) / Decimal("365.25") if days_count > 0 else Decimal(1)
        if years > Decimal(0) and final_equity > Decimal(0) and req.initial_capital > Decimal(0):
            # Compound Annual Growth Rate (CAGR)
            ratio = float(final_equity / req.initial_capital)
            cagr = (Decimal(str(ratio ** (1.0 / float(years)))) - Decimal("1.0")) * Decimal("100")
            annualized_return_pct = cagr
        else:
            annualized_return_pct = total_return_pct

        max_dd = max((pt.drawdown_pct for pt in equity_curve), default=Decimal(0))

        closed_trades = [t for t in trades if t.action == "sell"]
        win_trades = [t for t in closed_trades if t.pnl is not None and t.pnl > Decimal(0)]
        loss_trades = [t for t in closed_trades if t.pnl is not None and t.pnl < Decimal(0)]

        win_rate = (
            (Decimal(len(win_trades)) / Decimal(len(closed_trades)) * Decimal("100"))
            if closed_trades
            else Decimal(0)
        )

        total_profit = sum((t.pnl for t in win_trades if t.pnl is not None), Decimal(0))
        total_loss = abs(sum((t.pnl for t in loss_trades if t.pnl is not None), Decimal(0)))

        if total_loss > Decimal(0):
            profit_factor = total_profit / total_loss
        elif total_profit > Decimal(0):
            profit_factor = Decimal("999.0")
        else:
            profit_factor = Decimal("0.0")

        return BacktestResult(
            strategy_id=req.strategy_id,
            symbol=req.symbol,
            start=req.start,
            end=req.end,
            initial_capital=req.initial_capital,
            final_equity=final_equity,
            total_return_pct=total_return_pct,
            annualized_return_pct=annualized_return_pct,
            max_drawdown_pct=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=len(closed_trades),
            trades=trades,
            equity_curve=equity_curve,
        )
