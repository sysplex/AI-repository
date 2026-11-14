"""M6-T03 代码量化派生引擎单元测试。

验证：
1. 想买价相对现价偏差率精度与正负方向；
2. 52周区间位置计算、高低点重合保护与 clamp；
3. 确定性技术面交易计划（入场、止损、目标、盈亏比）及倒挂关口安全兜底；
4. 异常参数校验（负数、零除、非法格式）。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.research.exceptions import (
    InvalidParameterError,
    QuantitativeCalculationError,
)
from app.modules.research.ports import QuantitativeEngineProtocol
from app.modules.research.quantitative import (
    QuantitativeEngine,
    compute_pos_in_52w_range,
    compute_target_vs_price_pct,
    compute_technical_trade_plan,
)


@pytest.mark.unit
class TestComputeTargetVsPricePct:
    """测试 target_vs_price_pct 计算。"""

    def test_target_higher_than_current(self) -> None:
        pct = compute_target_vs_price_pct(Decimal("100.00"), Decimal("125.00"))
        assert pct == Decimal("25.00")

    def test_target_lower_than_current(self) -> None:
        pct = compute_target_vs_price_pct(Decimal("100.00"), Decimal("85.00"))
        assert pct == Decimal("-15.00")

    def test_target_equals_current(self) -> None:
        pct = compute_target_vs_price_pct(Decimal("150.50"), Decimal("150.50"))
        assert pct == Decimal("0.00")

    def test_decimal_rounding_half_up(self) -> None:
        # 100 -> 100.005 => 0.005% -> rounds to 0.01%
        pct = compute_target_vs_price_pct(Decimal("100.00"), Decimal("100.005"))
        assert pct == Decimal("0.01")

    def test_float_and_int_inputs_conversion(self) -> None:
        pct = compute_target_vs_price_pct(100, 110)
        assert pct == Decimal("10.00")

    def test_invalid_negative_or_zero_current_price(self) -> None:
        with pytest.raises(InvalidParameterError) as exc_info:
            compute_target_vs_price_pct(Decimal("0.00"), Decimal("100.00"))
        assert "Current price must be positive" in str(exc_info.value)

        with pytest.raises(InvalidParameterError):
            compute_target_vs_price_pct(Decimal("-10.00"), Decimal("100.00"))

    def test_invalid_negative_or_zero_target_price(self) -> None:
        with pytest.raises(InvalidParameterError) as exc_info:
            compute_target_vs_price_pct(Decimal("100.00"), Decimal("0.00"))
        assert "Target price must be positive" in str(exc_info.value)

        with pytest.raises(InvalidParameterError):
            compute_target_vs_price_pct(Decimal("100.00"), Decimal("-5.00"))

    def test_invalid_string_format(self) -> None:
        with pytest.raises(InvalidParameterError):
            compute_target_vs_price_pct("invalid", Decimal("100.00"))


@pytest.mark.unit
class TestComputePosIn52wRange:
    """测试 pos_in_52w_range 计算及边界保护。"""

    def test_midpoint_calculation(self) -> None:
        pos = compute_pos_in_52w_range(Decimal("150.00"), Decimal("100.00"), Decimal("200.00"))
        assert pos == Decimal("0.50")

    def test_fractional_position(self) -> None:
        pos = compute_pos_in_52w_range(Decimal("165.00"), Decimal("100.00"), Decimal("200.00"))
        assert pos == Decimal("0.65")

    def test_clamped_at_lower_bound(self) -> None:
        pos_exact = compute_pos_in_52w_range(
            Decimal("100.00"), Decimal("100.00"), Decimal("200.00")
        )
        assert pos_exact == Decimal("0.00")

        pos_below = compute_pos_in_52w_range(Decimal("80.00"), Decimal("100.00"), Decimal("200.00"))
        assert pos_below == Decimal("0.00")

    def test_clamped_at_upper_bound(self) -> None:
        pos_exact = compute_pos_in_52w_range(
            Decimal("200.00"), Decimal("100.00"), Decimal("200.00")
        )
        assert pos_exact == Decimal("1.00")

        pos_above = compute_pos_in_52w_range(
            Decimal("250.00"), Decimal("100.00"), Decimal("200.00")
        )
        assert pos_above == Decimal("1.00")

    def test_high_equals_low_protection(self) -> None:
        # CONTRACTS.md §3: 若 high_52w == low_52w，返回 Decimal("0.50")
        pos = compute_pos_in_52w_range(Decimal("100.00"), Decimal("100.00"), Decimal("100.00"))
        assert pos == Decimal("0.50")

    def test_inverted_high_and_low_auto_swapped(self) -> None:
        # low=200, high=100 -> auto swap to low=100, high=200
        pos = compute_pos_in_52w_range(Decimal("150.00"), Decimal("200.00"), Decimal("100.00"))
        assert pos == Decimal("0.50")

    def test_negative_price_raises_error(self) -> None:
        with pytest.raises(InvalidParameterError):
            compute_pos_in_52w_range(Decimal("-10.00"), Decimal("100.00"), Decimal("200.00"))


@pytest.mark.unit
class TestComputeTechnicalTradePlan:
    """测试确定性交易计划生成与倒挂极值兜底。"""

    def test_standard_bullish_trade_plan(self) -> None:
        cur = Decimal("100.00")
        supp = Decimal("95.00")
        res = Decimal("110.00")
        atr = Decimal("2.00")

        # entry = 100.00
        # raw_stop = max(95 * 0.98, 100 - 2 * 1.5) = max(93.10, 97.00) = 97.00
        # raw_target = min(110, 100 + 2 * 3.0) = min(110, 106.00) = 106.00
        # risk_reward = (106 - 100) / (100 - 97) = 6.00 / 3.00 = 2.00
        plan = compute_technical_trade_plan(cur, supp, res, atr)
        assert plan["entry"] == Decimal("100.00")
        assert plan["stop"] == Decimal("97.00")
        assert plan["target"] == Decimal("106.00")
        assert plan["risk_reward"] == Decimal("2.00")

    def test_support_higher_than_entry_safeguard(self) -> None:
        # 当支撑位倒挂异常（如 supp=105 >= entry=100）
        cur = Decimal("100.00")
        supp = Decimal("105.00")
        res = Decimal("120.00")
        atr = Decimal("2.00")

        plan = compute_technical_trade_plan(cur, supp, res, atr)
        assert plan["stop"] < plan["entry"]
        assert plan["target"] > plan["entry"]
        assert plan["risk_reward"] > Decimal("0")

    def test_resistance_lower_than_entry_safeguard(self) -> None:
        # 当阻力位倒挂异常（如 res=95 <= entry=100）
        cur = Decimal("100.00")
        supp = Decimal("90.00")
        res = Decimal("95.00")
        atr = Decimal("2.00")

        plan = compute_technical_trade_plan(cur, supp, res, atr)
        assert plan["stop"] < plan["entry"]
        assert plan["target"] > plan["entry"]
        assert plan["risk_reward"] > Decimal("0")

    def test_zero_or_negative_support_and_resistance_fallbacks(self) -> None:
        # 支撑和阻力为 0 时自动兜底为现价的 0.95 与 1.05
        cur = Decimal("100.00")
        supp = Decimal("0.00")
        res = Decimal("0.00")
        atr = Decimal("1.50")

        plan = compute_technical_trade_plan(cur, supp, res, atr)
        assert plan["stop"] < plan["entry"]
        assert plan["target"] > plan["entry"]
        assert plan["risk_reward"] > Decimal("0")

    def test_zero_atr_fallback(self) -> None:
        # 当 atr 为 0 时，自动采用 2% 价格作为 atr 兜底
        cur = Decimal("100.00")
        supp = Decimal("95.00")
        res = Decimal("110.00")
        atr = Decimal("0.00")

        plan = compute_technical_trade_plan(cur, supp, res, atr)
        assert plan["entry"] == Decimal("100.00")
        assert plan["stop"] < plan["entry"]
        assert plan["target"] > plan["entry"]
        assert plan["risk_reward"] > Decimal("0")

    def test_tiny_price_risk_non_positive_raises_error(self) -> None:
        # 当价格极小达到最低边界 0.01，stop 无法小于 entry
        cur = Decimal("0.01")
        supp = Decimal("0.01")
        res = Decimal("0.02")
        atr = Decimal("0.001")

        with pytest.raises(QuantitativeCalculationError) as exc_info:
            compute_technical_trade_plan(cur, supp, res, atr)
        assert "Trade plan risk is non-positive" in str(exc_info.value)

    def test_negative_current_price_raises_error(self) -> None:
        with pytest.raises(InvalidParameterError):
            compute_technical_trade_plan(
                Decimal("-10.00"), Decimal("90.00"), Decimal("110.00"), Decimal("2.00")
            )

    def test_negative_atr_raises_error(self) -> None:
        with pytest.raises(InvalidParameterError):
            compute_technical_trade_plan(
                Decimal("100.00"), Decimal("90.00"), Decimal("110.00"), Decimal("-1.00")
            )


@pytest.mark.unit
class TestQuantitativeEngineClass:
    """测试 QuantitativeEngine 类及其契约合规性。"""

    def test_implements_protocol(self) -> None:
        engine = QuantitativeEngine()
        assert isinstance(engine, QuantitativeEngineProtocol)

    def test_compute_buy_decision_metrics(self) -> None:
        engine = QuantitativeEngine()
        res = engine.compute_buy_decision_metrics(
            current_price=Decimal("150.00"),
            target_price=Decimal("165.00"),
            low_52w=Decimal("100.00"),
            high_52w=Decimal("200.00"),
        )
        assert res["target_vs_price_pct"] == Decimal("10.00")
        assert res["pos_in_52w_range"] == Decimal("0.50")

    def test_compute_technical_trade_plan(self) -> None:
        engine = QuantitativeEngine()
        res = engine.compute_technical_trade_plan(
            current_price=Decimal("100.00"),
            support=Decimal("95.00"),
            resistance=Decimal("110.00"),
            atr=Decimal("2.00"),
        )
        assert res["entry"] == Decimal("100.00")
        assert res["stop"] == Decimal("97.00")
        assert res["target"] == Decimal("106.00")
        assert res["risk_reward"] == Decimal("2.00")
