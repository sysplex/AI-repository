"""Unit tests for technical indicators calculation library.

Verifies:
- Numerical accuracy aligned with TA-Lib / hand-calculated mathematical reference (< 1e-6 error).
- Boundary conditions & defense for insufficient data / invalid period parameters.
- Lookahead-free deterministic pure functions without external dependencies.
- Compatibility with marketdata.models.Bar.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from app.modules.marketdata.models import Bar as MarketBar
from app.modules.strategy.indicators import (
    Bar,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_obv,
    calculate_rsi,
    calculate_sma,
    calculate_support_resistance,
    calculate_swing_high_low,
    calculate_true_range,
)


def _make_bar(
    trade_date: date,
    open_: str,
    high: str,
    low: str,
    close: str,
    volume: int = 1000,
    symbol: str = "TEST",
) -> MarketBar:
    """Helper to create real MarketBar instances for testing."""
    return MarketBar(
        symbol=symbol,
        trade_date=trade_date,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
    )


def _make_bars_from_closes(closes: Sequence[str | int | float]) -> list[MarketBar]:
    """Helper to create bars where high/low/open are derived around close."""
    bars: list[MarketBar] = []
    base_date = date(2026, 1, 1)
    for i, c in enumerate(closes):
        close_dec = Decimal(str(c))
        bars.append(
            MarketBar(
                symbol="TEST",
                trade_date=date.fromordinal(base_date.toordinal() + i),
                open=close_dec,
                high=close_dec + Decimal("1.0"),
                low=close_dec - Decimal("1.0"),
                close=close_dec,
                volume=1000 + i * 10,
            )
        )
    return bars


class TestBarProtocol:
    """Tests for Bar protocol compatibility."""

    def test_marketbar_satisfies_protocol(self) -> None:
        bar = _make_bar(date(2026, 1, 1), "100", "105", "95", "102")
        assert isinstance(bar, Bar)


class TestSMA:
    """Tests for calculate_sma."""

    def test_sma_basic(self) -> None:
        closes = ["10.0", "11.0", "12.0", "13.0", "14.0"]
        bars = _make_bars_from_closes(closes)
        # Period 3: last 3 are 12, 13, 14 -> (12 + 13 + 14) / 3 = 13.0
        result = calculate_sma(bars, 3)
        assert result is not None
        assert abs(result - Decimal("13.0")) < Decimal("1e-6")

    def test_sma_exact_length(self) -> None:
        closes = ["10.0", "20.0", "30.0"]
        bars = _make_bars_from_closes(closes)
        result = calculate_sma(bars, 3)
        assert result is not None
        assert abs(result - Decimal("20.0")) < Decimal("1e-6")

    def test_sma_insufficient_data(self) -> None:
        bars = _make_bars_from_closes(["10.0", "20.0"])
        assert calculate_sma(bars, 3) is None
        assert calculate_sma([], 1) is None

    def test_sma_invalid_period(self) -> None:
        bars = _make_bars_from_closes(["10.0", "20.0"])
        assert calculate_sma(bars, 0) is None
        assert calculate_sma(bars, -1) is None


class TestEMA:
    """Tests for calculate_ema."""

    def test_ema_ta_lib_reference(self) -> None:
        """Verify EMA follows TA-Lib seed: SMA of first `period`, then alpha = 2/(p+1)."""
        closes = ["10.0", "11.0", "12.0", "13.0", "14.0"]
        bars = _make_bars_from_closes(closes)
        # period = 3:
        # alpha = 2 / (3 + 1) = 0.5
        # seed = (10 + 11 + 12) / 3 = 11.0
        # bar 3 (close 13.0): 13.0 * 0.5 + 11.0 * 0.5 = 12.0
        # bar 4 (close 14.0): 14.0 * 0.5 + 12.0 * 0.5 = 13.0
        result = calculate_ema(bars, 3)
        assert result is not None
        assert abs(result - Decimal("13.0")) < Decimal("1e-6")

    def test_ema_constant_series(self) -> None:
        bars = _make_bars_from_closes(["50.0"] * 10)
        result = calculate_ema(bars, 5)
        assert result is not None
        assert abs(result - Decimal("50.0")) < Decimal("1e-6")

    def test_ema_insufficient_data(self) -> None:
        bars = _make_bars_from_closes(["10.0", "20.0"])
        assert calculate_ema(bars, 3) is None
        assert calculate_ema([], 1) is None

    def test_ema_invalid_period(self) -> None:
        bars = _make_bars_from_closes(["10.0", "20.0"])
        assert calculate_ema(bars, 0) is None
        assert calculate_ema(bars, -5) is None


class TestTrueRangeAndATR:
    """Tests for calculate_true_range and calculate_atr."""

    def test_true_range_first_bar(self) -> None:
        bar = _make_bar(date(2026, 1, 1), "100.0", "110.0", "95.0", "105.0")
        tr = calculate_true_range(bar, None)
        assert tr == Decimal("15.0")  # 110 - 95

    def test_true_range_gap_up(self) -> None:
        prev = _make_bar(date(2026, 1, 1), "100.0", "105.0", "98.0", "100.0")
        curr = _make_bar(date(2026, 1, 2), "112.0", "115.0", "110.0", "114.0")
        # hl = 115 - 110 = 5
        # hc = |115 - 100| = 15
        # lc = |110 - 100| = 10
        # TR = 15
        tr = calculate_true_range(curr, prev)
        assert tr == Decimal("15.0")

    def test_true_range_gap_down(self) -> None:
        prev = _make_bar(date(2026, 1, 1), "100.0", "105.0", "98.0", "100.0")
        curr = _make_bar(date(2026, 1, 2), "88.0", "90.0", "85.0", "87.0")
        # hl = 90 - 85 = 5
        # hc = |90 - 100| = 10
        # lc = |85 - 100| = 15
        # TR = 15
        tr = calculate_true_range(curr, prev)
        assert tr == Decimal("15.0")

    def test_atr_wilder_reference(self) -> None:
        """Verify ATR using Wilder's smoothing against manual derivation."""
        # Create 5 bars, period = 3
        # Bar 0: high 105, low 95, close 100
        # Bar 1: high 110, low 100, close 108 -> TR1 = max(10, 10, 0) = 10
        # Bar 2: high 115, low 105, close 112 -> TR2 = max(10, 7, 3) = 10
        # Bar 3: high 120, low 110, close 118 -> TR3 = max(10, 8, 2) = 10
        # Initial ATR (first 3 TRs: TR1, TR2, TR3): (10 + 10 + 10) / 3 = 10.0
        # Bar 4: high 125, low 105, close 120 -> TR4 = max(20, 7, 13) = 20
        # Smoothed ATR: (10.0 * 2 + 20) / 3 = 40 / 3 = 13.3333333333
        b0 = _make_bar(date(2026, 1, 1), "100", "105", "95", "100")
        b1 = _make_bar(date(2026, 1, 2), "102", "110", "100", "108")
        b2 = _make_bar(date(2026, 1, 3), "108", "115", "105", "112")
        b3 = _make_bar(date(2026, 1, 4), "112", "120", "110", "118")
        b4 = _make_bar(date(2026, 1, 5), "118", "125", "105", "120")
        bars = [b0, b1, b2, b3, b4]

        atr = calculate_atr(bars, period=3)
        assert atr is not None
        expected = Decimal("40") / Decimal("3")
        assert abs(atr - expected) < Decimal("1e-6")

    def test_atr_insufficient_data(self) -> None:
        bars = _make_bars_from_closes(["10.0", "20.0", "30.0"])
        # ATR(14) needs at least 15 bars
        assert calculate_atr(bars, 14) is None
        # ATR(3) needs at least 4 bars
        assert calculate_atr(bars, 3) is None
        assert calculate_atr([], 14) is None

    def test_atr_invalid_period(self) -> None:
        bars = _make_bars_from_closes(["10.0"] * 20)
        assert calculate_atr(bars, 0) is None
        assert calculate_atr(bars, -1) is None


class TestRSI:
    """Tests for calculate_rsi."""

    def test_rsi_wilder_textbook(self) -> None:
        """Verify RSI against J. Welles Wilder's published textbook 14-period dataset."""
        textbook_prices = [
            "44.34",
            "44.09",
            "44.15",
            "43.61",
            "44.33",
            "44.83",
            "45.10",
            "45.42",
            "45.84",
            "46.08",
            "45.89",
            "46.03",
            "45.61",
            "46.28",
            "46.28",
        ]
        bars = _make_bars_from_closes(textbook_prices)
        assert len(bars) == 15  # Exactly 14 changes

        rsi = calculate_rsi(bars, period=14)
        assert rsi is not None
        # Textbook initial RSI: ~70.4641
        expected = Decimal("70.464135")
        assert abs(rsi - expected) < Decimal("1e-4")

    def test_rsi_all_gains(self) -> None:
        """Monotonically increasing prices produce RSI = 100."""
        prices = [str(100 + i) for i in range(20)]
        bars = _make_bars_from_closes(prices)
        rsi = calculate_rsi(bars, period=14)
        assert rsi is not None
        assert abs(rsi - Decimal("100.0")) < Decimal("1e-6")

    def test_rsi_all_losses(self) -> None:
        """Monotonically decreasing prices produce RSI = 0."""
        prices = [str(200 - i) for i in range(20)]
        bars = _make_bars_from_closes(prices)
        rsi = calculate_rsi(bars, period=14)
        assert rsi is not None
        assert abs(rsi - Decimal("0.0")) < Decimal("1e-6")

    def test_rsi_flat_prices(self) -> None:
        """Flat prices produce 0.0 per TA-Lib zero change handling."""
        bars = _make_bars_from_closes(["50.0"] * 20)
        rsi = calculate_rsi(bars, period=14)
        assert rsi is not None
        assert rsi == Decimal("0.0")

    def test_rsi_insufficient_data(self) -> None:
        bars = _make_bars_from_closes(["10.0"] * 14)
        # Needs 15 bars for period=14
        assert calculate_rsi(bars, 14) is None
        assert calculate_rsi([], 14) is None

    def test_rsi_invalid_period(self) -> None:
        bars = _make_bars_from_closes(["10.0"] * 20)
        assert calculate_rsi(bars, 0) is None
        assert calculate_rsi(bars, -5) is None


class TestMACD:
    """Tests for calculate_macd."""

    def test_macd_linear_trend_analytical(self) -> None:
        """For a constant linear trend, fast-slow difference is constant, hist is zero."""
        # 35 bars: slope = 2.0
        # fast=12 lag = (12-1)/2 * 2 = 11
        # slow=26 lag = (26-1)/2 * 2 = 25
        # macd_line = 25 - 11 = 14.0
        # signal line of constant 14.0 is 14.0, hist = 0.0
        prices = [str(100 + i * 2) for i in range(35)]
        bars = _make_bars_from_closes(prices)

        macd, signal, hist = calculate_macd(bars, fast=12, slow=26, signal=9)
        assert macd is not None and signal is not None and hist is not None
        assert abs(macd - Decimal("14.0")) < Decimal("1e-6")
        assert abs(signal - Decimal("14.0")) < Decimal("1e-6")
        assert abs(hist - Decimal("0.0")) < Decimal("1e-6")

    def test_macd_flat_series(self) -> None:
        bars = _make_bars_from_closes(["100.0"] * 40)
        macd, signal, hist = calculate_macd(bars, fast=12, slow=26, signal=9)
        assert macd is not None and signal is not None and hist is not None
        assert abs(macd - Decimal("0.0")) < Decimal("1e-6")
        assert abs(signal - Decimal("0.0")) < Decimal("1e-6")
        assert abs(hist - Decimal("0.0")) < Decimal("1e-6")

    def test_macd_insufficient_data(self) -> None:
        # slow=26, signal=9 requires at least 26 + 9 - 1 = 34 bars
        bars_33 = _make_bars_from_closes(["10.0"] * 33)
        assert calculate_macd(bars_33, fast=12, slow=26, signal=9) == (None, None, None)

        bars_34 = _make_bars_from_closes(["10.0"] * 34)
        res = calculate_macd(bars_34, fast=12, slow=26, signal=9)
        assert res[0] is not None

        assert calculate_macd([], fast=12, slow=26, signal=9) == (None, None, None)

    def test_macd_invalid_parameters(self) -> None:
        bars = _make_bars_from_closes(["10.0"] * 40)
        # fast >= slow
        assert calculate_macd(bars, fast=26, slow=12, signal=9) == (None, None, None)
        assert calculate_macd(bars, fast=12, slow=12, signal=9) == (None, None, None)
        # <= 0
        assert calculate_macd(bars, fast=0, slow=26, signal=9) == (None, None, None)
        assert calculate_macd(bars, fast=12, slow=0, signal=9) == (None, None, None)
        assert calculate_macd(bars, fast=12, slow=26, signal=0) == (None, None, None)


class TestBollingerBands:
    """Tests for calculate_bollinger_bands."""

    def test_bollinger_bands_known_values(self) -> None:
        # 5 bars with closes: 10, 20, 10, 20, 10 (mean = 14)
        # mean = 14.0
        # variances: (10-14)^2=16, (20-14)^2=36, 16, 36, 16 -> sum = 120 -> var = 24
        # std = sqrt(24) = 4.898979485566356
        # upper = 14 + 2 * std = 23.7979589711
        # lower = 14 - 2 * std = 4.20204102887
        bars = _make_bars_from_closes(["10.0", "20.0", "10.0", "20.0", "10.0"])
        upper, middle, lower = calculate_bollinger_bands(bars, period=5, num_std=Decimal("2.0"))

        assert upper is not None and middle is not None and lower is not None
        assert abs(middle - Decimal("14.0")) < Decimal("1e-6")

        std_expected = Decimal("24").sqrt()
        assert abs(upper - (Decimal("14.0") + Decimal("2.0") * std_expected)) < Decimal("1e-6")
        assert abs(lower - (Decimal("14.0") - Decimal("2.0") * std_expected)) < Decimal("1e-6")

    def test_bollinger_bands_flat(self) -> None:
        bars = _make_bars_from_closes(["100.0"] * 25)
        upper, middle, lower = calculate_bollinger_bands(bars, period=20)
        assert upper is not None and middle is not None and lower is not None
        assert middle == Decimal("100.0")
        assert upper == Decimal("100.0")
        assert lower == Decimal("100.0")

    def test_bollinger_bands_insufficient_data(self) -> None:
        bars = _make_bars_from_closes(["100.0"] * 10)
        assert calculate_bollinger_bands(bars, period=20) == (None, None, None)
        assert calculate_bollinger_bands([], period=20) == (None, None, None)

    def test_bollinger_bands_invalid_params(self) -> None:
        bars = _make_bars_from_closes(["100.0"] * 25)
        assert calculate_bollinger_bands(bars, period=0) == (None, None, None)
        assert calculate_bollinger_bands(bars, period=-1) == (None, None, None)
        assert calculate_bollinger_bands(bars, period=20, num_std=Decimal("-1.0")) == (
            None,
            None,
            None,
        )


class TestOBV:
    """Tests for calculate_obv."""

    def test_obv_standard_progression(self) -> None:
        # Bar 0: close 100, vol 1000 -> OBV = 1000
        # Bar 1: close 105, vol 500  -> OBV = 1500
        # Bar 2: close 102, vol 300  -> OBV = 1200
        # Bar 3: close 102, vol 200  -> OBV = 1200
        # Bar 4: close 98,  vol 400  -> OBV = 800
        bars = [
            _make_bar(date(2026, 1, 1), "100", "105", "95", "100", volume=1000),
            _make_bar(date(2026, 1, 2), "100", "108", "99", "105", volume=500),
            _make_bar(date(2026, 1, 3), "105", "106", "101", "102", volume=300),
            _make_bar(date(2026, 1, 4), "102", "104", "100", "102", volume=200),
            _make_bar(date(2026, 1, 5), "102", "103", "97", "98", volume=400),
        ]
        assert calculate_obv(bars) == 800

    def test_obv_single_bar(self) -> None:
        bar = _make_bar(date(2026, 1, 1), "100", "105", "95", "100", volume=5000)
        assert calculate_obv([bar]) == 5000

    def test_obv_empty(self) -> None:
        assert calculate_obv([]) is None


class TestSwingHighLow:
    """Tests for calculate_swing_high_low."""

    def test_swing_high_low_detection(self) -> None:
        # Construct series with clear peak at index 3 and trough at index 7 with window=2
        # index: 0,  1,  2,  3(P), 4,  5,  6,  7(T), 8,  9
        # high: 10, 12, 14, 20,    15, 13, 11,  8,   12, 13
        # low:   8, 10, 11, 18,    13, 11,  9,  5,    9, 10
        bars: list[MarketBar] = []
        highs_raw = [10, 12, 14, 20, 15, 13, 11, 8, 12, 13]
        lows_raw = [8, 10, 11, 18, 13, 11, 9, 5, 9, 10]
        for i in range(10):
            bars.append(
                _make_bar(
                    date(2026, 1, i + 1),
                    open_=str(lows_raw[i] + 1),
                    high=str(highs_raw[i]),
                    low=str(lows_raw[i]),
                    close=str(lows_raw[i] + 1),
                )
            )

        highs, lows = calculate_swing_high_low(bars, window=2)
        assert highs == [Decimal("20")]
        assert lows == [Decimal("5")]

    def test_swing_high_low_insufficient_data(self) -> None:
        # window 3 requires at least 2 * 3 + 1 = 7 bars
        bars = _make_bars_from_closes(["10.0"] * 6)
        assert calculate_swing_high_low(bars, window=3) == ([], [])
        assert calculate_swing_high_low([], window=3) == ([], [])

    def test_swing_high_low_invalid_window(self) -> None:
        bars = _make_bars_from_closes(["10.0"] * 10)
        assert calculate_swing_high_low(bars, window=0) == ([], [])
        assert calculate_swing_high_low(bars, window=-2) == ([], [])


class TestSupportResistance:
    """Tests for calculate_support_resistance."""

    def test_support_resistance_known(self) -> None:
        # Over 5 bars, lowest low is 92.0, highest high is 115.0
        bars = [
            _make_bar(date(2026, 1, 1), "100", "105", "98", "102"),
            _make_bar(date(2026, 1, 2), "102", "110", "95", "108"),
            _make_bar(date(2026, 1, 3), "108", "115", "104", "112"),  # Highest high 115
            _make_bar(date(2026, 1, 4), "112", "114", "92", "96"),  # Lowest low 92
            _make_bar(date(2026, 1, 5), "96", "102", "94", "100"),
        ]
        sup, res = calculate_support_resistance(bars, window=5)
        assert sup == Decimal("92")
        assert res == Decimal("115")

    def test_support_resistance_recent_window(self) -> None:
        # 10 bars total, window=3 should only check last 3 bars
        bars = [
            _make_bar(date(2026, 1, 1), "50", "200", "10", "50"),  # Out of window (200, 10)
            _make_bar(date(2026, 1, 2), "50", "180", "20", "50"),
            _make_bar(date(2026, 1, 3), "50", "150", "30", "50"),
            _make_bar(date(2026, 1, 4), "50", "100", "40", "50"),
            _make_bar(date(2026, 1, 5), "50", "105", "45", "50"),
        ]
        # Last 3 bars: highs 150, 100, 105 -> max = 150; lows 30, 40, 45 -> min = 30
        sup, res = calculate_support_resistance(bars, window=3)
        assert sup == Decimal("30")
        assert res == Decimal("150")

    def test_support_resistance_insufficient_data(self) -> None:
        bars = _make_bars_from_closes(["10.0"] * 5)
        assert calculate_support_resistance(bars, window=10) == (None, None)
        assert calculate_support_resistance([], window=5) == (None, None)

    def test_support_resistance_invalid_window(self) -> None:
        bars = _make_bars_from_closes(["10.0"] * 10)
        assert calculate_support_resistance(bars, window=0) == (None, None)
        assert calculate_support_resistance(bars, window=-1) == (None, None)
