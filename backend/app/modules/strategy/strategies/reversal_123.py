"""1-2-3 Trend Reversal strategy implementation (M3 / T03).

Victor Sperandeo's 1-2-3 Rule for Trend Reversal:
1. Trendline break: Price crosses above the downward trend moving average (SMA 20).
2. Test & Higher Low: Retest fails to create a lower low; higher low formed (lows[-1] > lows[-2]).
3. Peak breakout: Price breaks strictly above intermediate swing high (highs[-1]).

Strictly lookahead-bias safe: all bars <= ctx.as_of.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules.strategy.indicators import (
    calculate_sma,
    calculate_swing_high_low,
)
from app.modules.strategy.ports import Strategy
from app.modules.strategy.registry import register_strategy
from app.modules.strategy.schemas import Signal, StrategyContext


@register_strategy
class Reversal123Strategy(Strategy):
    """Victor Sperandeo 1-2-3 reversal rule strategy."""

    id = "reversal_123"
    display_name = "123 法则反转突破策略"
    category = "reversal"
    description = (
        "Victor Sperandeo 123 法则反转策略：1-价格突破下行均线；"
        "2-回踩不创新低形成更高低点（Higher Low）；"
        "3-突破中间反弹高点确认反转买入。"
    )
    requires = {"bars"}
    default_params: dict[str, Any] = {
        "trend_period": 20,
        "swing_window": 3,
        "risk_reward_ratio": Decimal("2.0"),
    }

    def evaluate(self, ctx: StrategyContext) -> Signal:
        """Evaluate 1-2-3 reversal conditions."""
        valid_bars = [b for b in ctx.bars if b.trade_date <= ctx.as_of]

        params = {**self.default_params, **ctx.params}
        trend_period = int(params["trend_period"])
        swing_window = int(params["swing_window"])
        rrr = Decimal(str(params["risk_reward_ratio"]))

        min_required = max(trend_period, 2 * swing_window + 1)
        if len(valid_bars) < min_required:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=[f"insufficient_bars: need {min_required}, got {len(valid_bars)}"],
            )

        current = valid_bars[-1]
        sma_trend = calculate_sma(valid_bars, period=trend_period)
        highs, lows = calculate_swing_high_low(valid_bars, window=swing_window)

        metrics: dict[str, Any] = {
            "close": current.close,
            "trend_sma": sma_trend,
            "swing_highs_count": len(highs),
            "swing_lows_count": len(lows),
        }

        # Step 1: Must be above downward trend SMA
        rule_1_met = sma_trend is not None and current.close > sma_trend
        if not rule_1_met:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=["Rule 1 failed: close not above trendline SMA"],
                metrics=metrics,
            )

        # Step 2: Must have at least 2 swing lows with lows[-1] > lows[-2] (Higher Low)
        if len(lows) < 2:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=["Rule 2 failed: insufficient swing lows to verify higher low"],
                metrics=metrics,
            )

        last_low = lows[-1]
        prev_low = lows[-2]
        rule_2_met = last_low > prev_low
        metrics.update({"last_low": last_low, "prev_low": prev_low})

        if not rule_2_met:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=[f"Rule 2 failed: low not higher ({last_low} <= {prev_low})"],
                metrics=metrics,
            )

        # Step 3: Must have at least 1 intermediate swing high, and current close > last_high
        if len(highs) < 1:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=["Rule 3 failed: no intermediate swing high identified"],
                metrics=metrics,
            )

        last_high = highs[-1]
        rule_3_met = current.close > last_high
        metrics["last_high"] = last_high

        if rule_1_met and rule_2_met and rule_3_met:
            entry_price = current.close
            stop_price = last_low
            risk = entry_price - stop_price
            target_price = (
                entry_price + (risk * rrr) if risk > Decimal(0) else entry_price * Decimal("1.10")
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
                strength=80,
                reasons=[
                    f"1-2-3 Reversal confirmed: 1) Close {current.close} > SMA{trend_period}; "
                    f"2) Higher Low {last_low} > {prev_low}; "
                    f"3) Breakout above swing high {last_high}"
                ],
                levels=levels,
                metrics=metrics,
            )

        return Signal(
            strategy_id=self.id,
            symbol=ctx.symbol,
            as_of=ctx.as_of,
            direction="flat",
            strength=0,
            reasons=["Rule 3 pending: close has not broken above intermediate high"],
            metrics=metrics,
        )
