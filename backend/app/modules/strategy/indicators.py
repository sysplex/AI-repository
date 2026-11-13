"""Pure technical indicator calculation functions using high-precision Decimal arithmetic.

All indicators are implemented as pure, deterministic functions without side effects
(no DB, no network, no state mutation). Calculations adhere to standard financial
formulas (aligned with TA-Lib / standard technical analysis) with error < 1e-6.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable


@runtime_checkable
class Bar(Protocol):
    """Protocol for candlestick bars used in technical indicator calculations."""

    @property
    def trade_date(self) -> date: ...

    @property
    def open(self) -> Decimal: ...

    @property
    def high(self) -> Decimal: ...

    @property
    def low(self) -> Decimal: ...

    @property
    def close(self) -> Decimal: ...

    @property
    def volume(self) -> int: ...


def calculate_sma(bars: Sequence[Bar], period: int) -> Decimal | None:
    """Calculate Simple Moving Average (SMA) of close prices over `period`.

    Args:
        bars: Chronologically sorted sequence of Bar objects (oldest to newest).
        period: Lookback window length (must be > 0).

    Returns:
        SMA as Decimal, or None if data is insufficient or period <= 0.
    """
    if period <= 0 or len(bars) < period:
        return None
    window = bars[-period:]
    return sum((b.close for b in window), Decimal(0)) / Decimal(period)


def calculate_ema(bars: Sequence[Bar], period: int) -> Decimal | None:
    """Calculate Exponential Moving Average (EMA) of close prices over `period`.

    Follows standard TA-Lib convention:
    - Initial value is the SMA of the first `period` bars.
    - Multiplier alpha = 2 / (period + 1).
    - Recursive formula: EMA_t = Close_t * alpha + EMA_{t-1} * (1 - alpha).

    Args:
        bars: Chronologically sorted sequence of Bar objects (oldest to newest).
        period: Lookback window length (must be > 0).

    Returns:
        EMA as Decimal, or None if data is insufficient or period <= 0.
    """
    if period <= 0 or len(bars) < period:
        return None

    # Initial SMA seed over the first `period` bars
    alpha = Decimal(2) / Decimal(period + 1)
    one_minus_alpha = Decimal(1) - alpha
    ema = sum((bars[i].close for i in range(period)), Decimal(0)) / Decimal(period)

    # Recursive smoothing for subsequent bars
    for i in range(period, len(bars)):
        ema = (bars[i].close * alpha) + (ema * one_minus_alpha)

    return ema


def calculate_true_range(current: Bar, previous: Bar | None) -> Decimal:
    """Calculate True Range (TR) for a candlestick bar.

    TR = max(high - low, abs(high - previous_close), abs(low - previous_close)).
    If previous is None, TR = high - low.

    Args:
        current: The current Bar.
        previous: The preceding Bar, or None if current is the first bar.

    Returns:
        True Range as Decimal.
    """
    hl = current.high - current.low
    if previous is None:
        return hl

    prev_close = previous.close
    hc = abs(current.high - prev_close)
    lc = abs(current.low - prev_close)
    return max(hl, hc, lc)


def calculate_atr(bars: Sequence[Bar], period: int = 14) -> Decimal | None:
    """Calculate Average True Range (ATR) over `period` using Wilder's smoothing.

    Follows J. Welles Wilder Jr. / TA-Lib specification:
    - Requires at least `period + 1` bars to produce the first `period` True Ranges.
    - Initial ATR is the Simple Moving Average of the first `period` True Ranges.
    - Subsequent values are smoothed: ATR_t = (ATR_{t-1} * (period - 1) + TR_t) / period.

    Args:
        bars: Chronologically sorted sequence of Bar objects.
        period: Lookback period (default 14, must be > 0).

    Returns:
        ATR as Decimal, or None if data is insufficient or period <= 0.
    """
    if period <= 0 or len(bars) < period + 1:
        return None

    # Calculate True Range series starting from index 1
    tr_series = [calculate_true_range(bars[i], bars[i - 1]) for i in range(1, len(bars))]

    # Initial ATR seed (SMA of first `period` True Ranges)
    atr = sum(tr_series[:period], Decimal(0)) / Decimal(period)
    p_minus_1 = Decimal(period - 1)
    p_dec = Decimal(period)

    # Wilder's smoothing recursion
    for i in range(period, len(tr_series)):
        atr = (atr * p_minus_1 + tr_series[i]) / p_dec

    return atr


def calculate_rsi(bars: Sequence[Bar], period: int = 14) -> Decimal | None:
    """Calculate Relative Strength Index (RSI) over `period` using Wilder's smoothing.

    Follows J. Welles Wilder Jr. / TA-Lib specification:
    - Requires at least `period + 1` bars (to compute `period` price changes).
    - Initial average gain/loss is SMA of the first `period` changes.
    - Subsequent averages use Wilder's recursion:
        avg_gain_t = (avg_gain_{t-1} * (period - 1) + gain_t) / period
        avg_loss_t = (avg_loss_{t-1} * (period - 1) + loss_t) / period
    - RSI = 100 * (avg_gain / (avg_gain + avg_loss)).
    - If avg_gain + avg_loss == 0, returns Decimal("0.0") (per TA-Lib behavior).

    Args:
        bars: Chronologically sorted sequence of Bar objects.
        period: Lookback period (default 14, must be > 0).

    Returns:
        RSI as Decimal (0 to 100), or None if data is insufficient or period <= 0.
    """
    if period <= 0 or len(bars) < period + 1:
        return None

    # Price differences
    deltas = [bars[i].close - bars[i - 1].close for i in range(1, len(bars))]

    # Initial SMA over first `period` changes
    zero = Decimal(0)
    avg_gain = sum((d for d in deltas[:period] if d > zero), zero) / Decimal(period)
    avg_loss = sum((-d for d in deltas[:period] if d < zero), zero) / Decimal(period)

    p_minus_1 = Decimal(period - 1)
    p_dec = Decimal(period)

    # Wilder's smoothing recursion
    for i in range(period, len(deltas)):
        d = deltas[i]
        gain = d if d > zero else zero
        loss = -d if d < zero else zero
        avg_gain = (avg_gain * p_minus_1 + gain) / p_dec
        avg_loss = (avg_loss * p_minus_1 + loss) / p_dec

    total = avg_gain + avg_loss
    if total == zero:
        return zero

    return (Decimal(100) * avg_gain) / total


def calculate_macd(
    bars: Sequence[Bar],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Calculate Moving Average Convergence/Divergence (MACD).

    Follows TA-Lib lockstep EMA computation:
    - Fast EMA and Slow EMA are computed starting at their respective lookback indices.
    - MACD Line = Fast EMA - Slow EMA (defined from index `slow - 1` onwards).
    - Signal Line = EMA of MACD Line over `signal` periods.
    - Histogram = MACD Line - Signal Line.

    Requires at least `slow + signal - 1` bars to produce a valid MACD triple.

    Args:
        bars: Chronologically sorted sequence of Bar objects.
        fast: Fast EMA period (default 12, must be > 0 and < slow).
        slow: Slow EMA period (default 26, must be > fast).
        signal: Signal EMA period (default 9, must be > 0).

    Returns:
        tuple (macd, macd_signal, macd_hist) or (None, None, None) if insufficient.
    """
    if fast <= 0 or slow <= 0 or signal <= 0 or fast >= slow:
        return (None, None, None)

    min_required = slow + signal - 1
    if len(bars) < min_required:
        return (None, None, None)

    n = len(bars)
    prices = [b.close for b in bars]

    # 1. Fast EMA series
    fast_alpha = Decimal(2) / Decimal(fast + 1)
    fast_one_minus = Decimal(1) - fast_alpha
    fast_ema = [Decimal(0)] * n
    fast_ema[fast - 1] = sum(prices[:fast], Decimal(0)) / Decimal(fast)
    for i in range(fast, n):
        fast_ema[i] = (prices[i] * fast_alpha) + (fast_ema[i - 1] * fast_one_minus)

    # 2. Slow EMA series
    slow_alpha = Decimal(2) / Decimal(slow + 1)
    slow_one_minus = Decimal(1) - slow_alpha
    slow_ema = [Decimal(0)] * n
    slow_ema[slow - 1] = sum(prices[:slow], Decimal(0)) / Decimal(slow)
    for i in range(slow, n):
        slow_ema[i] = (prices[i] * slow_alpha) + (slow_ema[i - 1] * slow_one_minus)

    # 3. MACD line series (from index slow - 1 to n - 1)
    macd_line: list[Decimal] = []
    for i in range(slow - 1, n):
        macd_line.append(fast_ema[i] - slow_ema[i])

    # 4. Signal line EMA of macd_line over `signal` period
    sig_alpha = Decimal(2) / Decimal(signal + 1)
    sig_one_minus = Decimal(1) - sig_alpha
    sig_ema = sum(macd_line[:signal], Decimal(0)) / Decimal(signal)
    for j in range(signal, len(macd_line)):
        sig_ema = (macd_line[j] * sig_alpha) + (sig_ema * sig_one_minus)

    macd_val = macd_line[-1]
    signal_val = sig_ema
    hist_val = macd_val - signal_val

    return (macd_val, signal_val, hist_val)


def calculate_bollinger_bands(
    bars: Sequence[Bar],
    period: int = 20,
    num_std: Decimal = Decimal("2.0"),
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Calculate Bollinger Bands (upper, middle, lower).

    Follows standard formulation (John Bollinger / TA-Lib):
    - Middle band = SMA(period).
    - Standard deviation = population standard deviation over the last `period` bars.
    - Upper band = Middle + num_std * std.
    - Lower band = Middle - num_std * std.

    Args:
        bars: Chronologically sorted sequence of Bar objects.
        period: Lookback window (default 20, must be > 0).
        num_std: Multiplier for standard deviation (default 2.0, must be >= 0).

    Returns:
        tuple (upper, middle, lower) as Decimal, or (None, None, None) if insufficient.
    """
    if period <= 0 or num_std < Decimal(0) or len(bars) < period:
        return (None, None, None)

    window = bars[-period:]
    period_dec = Decimal(period)
    middle = sum((b.close for b in window), Decimal(0)) / period_dec

    variance = sum(((b.close - middle) ** 2 for b in window), Decimal(0)) / period_dec
    std = variance.sqrt()

    upper = middle + (num_std * std)
    lower = middle - (num_std * std)

    return (upper, middle, lower)


def calculate_obv(bars: Sequence[Bar]) -> int | None:
    """Calculate On-Balance Volume (OBV).

    Follows Joe Granville / TA-Lib specification:
    - Cumulative running sum of volume based on close price direction.
    - OBV_0 = Volume_0.
    - If Close_t > Close_{t-1}: OBV_t = OBV_{t-1} + Volume_t
    - If Close_t < Close_{t-1}: OBV_t = OBV_{t-1} - Volume_t
    - If Close_t == Close_{t-1}: OBV_t = OBV_{t-1}

    Args:
        bars: Chronologically sorted sequence of Bar objects.

    Returns:
        Cumulative OBV as int, or None if bars is empty.
    """
    if not bars:
        return None

    obv = bars[0].volume
    for i in range(1, len(bars)):
        curr_close = bars[i].close
        prev_close = bars[i - 1].close
        vol = bars[i].volume
        if curr_close > prev_close:
            obv += vol
        elif curr_close < prev_close:
            obv -= vol

    return obv


def calculate_swing_high_low(
    bars: Sequence[Bar],
    window: int = 5,
) -> tuple[list[Decimal], list[Decimal]]:
    """Identify confirmed swing highs (peaks) and swing lows (troughs).

    Strictly lookahead-safe: a swing point at index `i` is evaluated only
    using `window` bars before and `window` bars after `i` that are already
    present in the historical dataset (i.e. `window <= i <= len(bars) - 1 - window`).

    A bar `i` is a Swing High if:
        high_i > high_j for all j in [i - window, i)
        high_i >= high_j for all j in (i, i + window]

    A bar `i` is a Swing Low if:
        low_i < low_j for all j in [i - window, i)
        low_i <= low_j for all j in (i, i + window]

    Args:
        bars: Chronologically sorted sequence of Bar objects.
        window: Margin window on each side (default 5, must be > 0).

    Returns:
        tuple (swing_highs, swing_lows) in chronological order.
    """
    if window <= 0 or len(bars) < 2 * window + 1:
        return ([], [])

    highs: list[Decimal] = []
    lows: list[Decimal] = []
    n = len(bars)

    for i in range(window, n - window):
        curr_high = bars[i].high
        is_high = all(curr_high > bars[j].high for j in range(i - window, i)) and all(
            curr_high >= bars[j].high for j in range(i + 1, i + window + 1)
        )
        if is_high:
            highs.append(curr_high)

        curr_low = bars[i].low
        is_low = all(curr_low < bars[j].low for j in range(i - window, i)) and all(
            curr_low <= bars[j].low for j in range(i + 1, i + window + 1)
        )
        if is_low:
            lows.append(curr_low)

    return (highs, lows)


def calculate_support_resistance(
    bars: Sequence[Bar],
    window: int = 20,
) -> tuple[Decimal | None, Decimal | None]:
    """Calculate key support and resistance levels over the most recent `window` bars.

    - Support = lowest Low within the lookback window.
    - Resistance = highest High within the lookback window.

    Args:
        bars: Chronologically sorted sequence of Bar objects.
        window: Lookback window length (default 20, must be > 0).

    Returns:
        tuple (support, resistance) as Decimal, or (None, None) if insufficient.
    """
    if window <= 0 or len(bars) < window:
        return (None, None)

    window_bars = bars[-window:]
    support = min(b.low for b in window_bars)
    resistance = max(b.high for b in window_bars)

    return (support, resistance)
