"""Turtle trading breakout strategy implementation (M3 / T03).

System 1 (20-day high breakout) and System 2 (55-day high breakout).
Enforces strict lookahead bias protection: all evaluated bars satisfy trade_date <= ctx.as_of.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules.strategy.indicators import calculate_atr
from app.modules.strategy.ports import Strategy
from app.modules.strategy.registry import register_strategy
from app.modules.strategy.schemas import Signal, StrategyContext


@register_strategy
class TurtleStrategy(Strategy):
    """Turtle breakout strategy (20/55 day breakout with 10/20 day exit)."""

    id = "turtle_20_55"
    display_name = "海龟 20/55 日突破策略"
    category = "trend"
    description = (
        "海龟交易法则：突破过去 N 日最高价做多进场，跌破 M 日最低价平仓出场，"
        "并使用 2*ATR 动态止损与 3*ATR 止盈目标位。"
    )
    requires = {"bars"}
    default_params: dict[str, Any] = {
        "entry_window": 20,
        "exit_window": 10,
        "atr_period": 14,
        "stop_atr_mult": Decimal("2.0"),
        "target_atr_mult": Decimal("3.0"),
    }

    def evaluate(self, ctx: StrategyContext) -> Signal:
        """Evaluate turtle breakout signal on lookahead-safe historical bars."""
        # 1. Lookahead defense: strictly truncate bars to <= ctx.as_of
        valid_bars = [b for b in ctx.bars if b.trade_date <= ctx.as_of]

        params = {**self.default_params, **ctx.params}
        entry_window = int(params["entry_window"])
        exit_window = int(params["exit_window"])
        atr_period = int(params["atr_period"])
        stop_mult = Decimal(str(params["stop_atr_mult"]))
        target_mult = Decimal(str(params["target_atr_mult"]))

        if len(valid_bars) < entry_window + 1:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=[f"insufficient_bars: need {entry_window + 1}, got {len(valid_bars)}"],
            )

        current = valid_bars[-1]
        prior_entry_bars = valid_bars[-entry_window - 1 : -1]
        prior_high = max(b.high for b in prior_entry_bars)

        exit_lookback = min(exit_window, len(valid_bars) - 1)
        prior_exit_bars = valid_bars[-exit_lookback - 1 : -1]
        prior_exit_low = min(b.low for b in prior_exit_bars)

        atr = calculate_atr(valid_bars, period=atr_period)
        metrics: dict[str, Any] = {
            "entry_high": prior_high,
            "exit_low": prior_exit_low,
            "close": current.close,
            "atr": atr,
        }

        # 2. Breakout condition: current close breaks strictly above previous high
        if current.close > prior_high:
            entry_price = current.close
            stop_price = entry_price - (atr * stop_mult) if atr is not None else prior_exit_low
            target_price = (
                entry_price + (atr * target_mult)
                if atr is not None
                else entry_price * Decimal("1.10")
            )
            levels = {
                "entry": entry_price,
                "stop": max(Decimal("0.01"), stop_price),
                "target": target_price,
            }
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="long",
                strength=85,
                reasons=[f"Close {current.close} broke above {entry_window}-day high {prior_high}"],
                levels=levels,
                metrics=metrics,
            )

        # 3. Exit condition: current close falls below exit low
        if current.close < prior_exit_low:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=60,
                reasons=[
                    f"Close {current.close} dropped below "
                    f"{exit_window}-day exit low {prior_exit_low}"
                ],
                levels={"entry": current.close, "stop": prior_exit_low},
                metrics=metrics,
            )

        # 4. In range: no action
        return Signal(
            strategy_id=self.id,
            symbol=ctx.symbol,
            as_of=ctx.as_of,
            direction="flat",
            strength=0,
            reasons=[f"Close {current.close} within range [{prior_exit_low}, {prior_high}]"],
            metrics=metrics,
        )
