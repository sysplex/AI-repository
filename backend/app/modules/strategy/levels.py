"""Dynamic stop loss and target level calculations based on ATR multiples (M3 / T05).

Provides deterministic level calculations for risk management adhering strictly to CONTRACTS.md §4.
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.strategy.schemas import SignalDirection


def compute_atr_levels(
    entry_price: Decimal,
    atr: Decimal,
    direction: SignalDirection,
    stop_mult: Decimal = Decimal("2.0"),
    target_mult: Decimal = Decimal("3.0"),
) -> dict[str, Decimal]:
    """Calculate entry, stop loss, and profit target price levels based on ATR.

    Formulas (CONTRACTS.md §4):
    - When direction == 'long':
        stop = entry_price - (atr * stop_mult)
        target = entry_price + (atr * target_mult)
    - When direction == 'short':
        stop = entry_price + (atr * stop_mult)
        target = entry_price - (atr * target_mult)
    - When direction == 'flat':
        stop = entry_price
        target = entry_price

    Safeguards:
    - Long stop is bounded below by Decimal("0.01") to avoid negative price levels.
    - Short target is bounded below by Decimal("0.01").

    Args:
        entry_price: The trade entry price as Decimal.
        atr: Current Average True Range as Decimal.
        direction: Signal direction ('long', 'short', or 'flat').
        stop_mult: ATR multiplier for stop loss (default 2.0).
        target_mult: ATR multiplier for target (default 3.0).

    Returns:
        Dictionary with keys 'entry', 'stop', 'target' mapped to Decimal prices.
    """
    if direction == "long":
        raw_stop = entry_price - (atr * stop_mult)
        target = entry_price + (atr * target_mult)
        stop = max(Decimal("0.01"), raw_stop)
        return {"entry": entry_price, "stop": stop, "target": target}

    if direction == "short":
        stop = entry_price + (atr * stop_mult)
        raw_target = entry_price - (atr * target_mult)
        target = max(Decimal("0.01"), raw_target)
        return {"entry": entry_price, "stop": stop, "target": target}

    # flat
    return {"entry": entry_price, "stop": entry_price, "target": entry_price}
