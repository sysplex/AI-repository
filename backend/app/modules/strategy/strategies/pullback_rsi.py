"""Uptrend RSI Pullback strategy implementation (M3 / T03).

Identifies dip-buying opportunities in an established uptrend:
- Trend filter: Price is above medium-term SMA (e.g. SMA 50 or 20).
- Pullback trigger: RSI(14) was recently oversold (<= threshold) and is now turning upwards.
- Strict lookahead protection: all bars <= ctx.as_of.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules.strategy.indicators import (
    calculate_atr,
    calculate_rsi,
    calculate_sma,
)
from app.modules.strategy.ports import Strategy
from app.modules.strategy.registry import register_strategy
from app.modules.strategy.schemas import Signal, StrategyContext


@register_strategy
class PullbackRsiStrategy(Strategy):
    """RSI Pullback in Uptrend strategy."""

    id = "pullback_rsi"
    display_name = "多头 RSI 回调企稳策略"
    category = "pullback"
    description = (
        "多头趋势（价格位于 50 日均线之上）中，寻找 RSI(14) 回调至超卖区间（<=35）后"
        "向上拐头企稳的低吸买入机会。"
    )
    requires = {"bars"}
    default_params: dict[str, Any] = {
        "trend_sma_period": 50,
        "rsi_period": 14,
        "rsi_oversold": Decimal("35.0"),
        "pullback_lookback": 5,
        "atr_period": 14,
        "stop_atr_mult": Decimal("2.0"),
        "target_atr_mult": Decimal("3.0"),
    }

    def evaluate(self, ctx: StrategyContext) -> Signal:
        """Evaluate RSI pullback signal in uptrend."""
        valid_bars = [b for b in ctx.bars if b.trade_date <= ctx.as_of]

        params = {**self.default_params, **ctx.params}
        trend_period = int(params["trend_sma_period"])
        rsi_period = int(params["rsi_period"])
        rsi_oversold = Decimal(str(params["rsi_oversold"]))
        pullback_lookback = int(params["pullback_lookback"])
        atr_period = int(params["atr_period"])
        stop_mult = Decimal(str(params["stop_atr_mult"]))
        target_mult = Decimal(str(params["target_atr_mult"]))

        # Need enough bars for SMA and RSI
        min_required = max(trend_period, rsi_period + pullback_lookback + 1)
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

        metrics: dict[str, Any] = {
            "close": current.close,
            "trend_sma": sma_trend,
        }

        # 1. Trend Filter: Current price must be above SMA trend
        if sma_trend is None or current.close < sma_trend:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=[
                    f"Trend filter failed: close {current.close} "
                    f"below SMA{trend_period} ({sma_trend})"
                ],
                metrics=metrics,
            )

        # 2. RSI Calculation: current and historical in pullback window
        rsi_curr = calculate_rsi(valid_bars, period=rsi_period)
        if rsi_curr is None:
            return Signal(
                strategy_id=self.id,
                symbol=ctx.symbol,
                as_of=ctx.as_of,
                direction="flat",
                strength=0,
                reasons=["RSI calculation failed"],
                metrics=metrics,
            )

        metrics["rsi_current"] = rsi_curr

        # Check if RSI was oversold within recent pullback_lookback bars
        # and has hooked upwards at the current bar
        recent_rsis: list[Decimal] = []
        for offset in range(pullback_lookback, 0, -1):
            sub_bars = valid_bars[:-offset]
            r = calculate_rsi(sub_bars, period=rsi_period)
            if r is not None:
                recent_rsis.append(r)

        was_oversold = any(r <= rsi_oversold for r in recent_rsis)
        prev_rsi = recent_rsis[-1] if recent_rsis else None
        is_hooking_up = prev_rsi is not None and rsi_curr > prev_rsi

        metrics["was_oversold"] = was_oversold
        metrics["prev_rsi"] = prev_rsi

        if was_oversold and is_hooking_up:
            atr = calculate_atr(valid_bars, period=atr_period)
            entry_price = current.close
            stop_price = (
                entry_price - (atr * stop_mult)
                if atr is not None
                else current.low * Decimal("0.97")
            )
            target_price = (
                entry_price + (atr * target_mult)
                if atr is not None
                else entry_price * Decimal("1.06")
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
                    f"Uptrend (> SMA{trend_period}) with RSI oversold dip (<={rsi_oversold}) "
                    f"and hook-up ({prev_rsi} -> {rsi_curr})"
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
            reasons=["No oversold pullback trigger"],
            metrics=metrics,
        )
