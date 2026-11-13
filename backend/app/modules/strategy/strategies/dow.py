"""Dow Theory trend-following strategy implementation (M3 / T03).

Identifies trends through Higher Highs (HH) & Higher Lows (HL) for uptrends,
and Lower Highs (LH) & Lower Lows (LL) for downtrends.
Strictly lookahead-bias safe: all bars <= ctx.as_of.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules.strategy.indicators import calculate_swing_high_low
from app.modules.strategy.ports import Strategy
from app.modules.strategy.registry import register_strategy
from app.modules.strategy.schemas import Signal, StrategyContext


@register_strategy
class DowTrendStrategy(Strategy):
    """Dow theory trend filtering and breakout strategy."""

    id = "dow_trend"
    display_name = "道氏趋势突破策略"
    category = "trend"
    description = (
        "道氏理论趋势策略：识别波段高低点抬升（Higher Highs & Higher Lows）确立上升趋势，"
        "向上突破最新波段高点触发买入，跌破最新波段低点平仓防守。"
    )
    requires = {"bars"}
    default_params: dict[str, Any] = {
        "swing_window": 5,
        "risk_reward_ratio": Decimal("2.0"),
    }

    def evaluate(self, ctx: StrategyContext) -> Signal:
        """Evaluate Dow trend and breakout signals."""
        valid_bars = [b for b in ctx.bars if b.trade_date <= ctx.as_of]

        params = {**self.default_params, **ctx.params}
        swing_window = int(params["swing_window"])
        rrr = Decimal(str(params["risk_reward_ratio"]))

        min_required = 2 * swing_window + 1
        if len(valid_bars) < min_required:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=[f"insufficient_bars: need {min_required}, got {len(valid_bars)}"],
            )

        highs, lows = calculate_swing_high_low(valid_bars, window=swing_window)
        current = valid_bars[-1]

        metrics: dict[str, Any] = {
            "swing_highs_count": len(highs),
            "swing_lows_count": len(lows),
            "close": current.close,
        }

        # Need at least 2 highs and 2 lows to establish higher-high / higher-low sequence
        if len(highs) < 2 or len(lows) < 2:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=["insufficient_swing_points: need >= 2 swing highs and 2 swing lows"],
                metrics=metrics,
            )

        last_high = highs[-1]
        prev_high = highs[-2]
        last_low = lows[-1]
        prev_low = lows[-2]

        metrics.update(
            {
                "last_high": last_high,
                "prev_high": prev_high,
                "last_low": last_low,
                "prev_low": prev_low,
            }
        )

        is_uptrend = last_high > prev_high and last_low > prev_low
        is_downtrend = last_high < prev_high and last_low < prev_low

        # 1. Uptrend breakout: price exceeds latest confirmed swing high
        if is_uptrend and current.close > last_high:
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
                strength=85,
                reasons=[
                    f"Dow uptrend (HH: {last_high}>{prev_high}, HL: {last_low}>{prev_low}) "
                    f"and close {current.close} broke above swing high {last_high}"
                ],
                levels=levels,
                metrics=metrics,
            )

        # 2. Downtrend warning: lower highs and lower lows
        if is_downtrend:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=10,
                reasons=[f"Dow downtrend (LH: {last_high}<{prev_high}, LL: {last_low}<{prev_low})"],
                metrics=metrics,
            )

        # 3. Consolidation or within range
        return Signal(
            strategy_id=self.id,
            symbol=ctx.symbol,
            as_of=ctx.as_of,
            direction="flat",
            strength=0,
            reasons=["Dow consolidation or no active breakout"],
            metrics=metrics,
        )
