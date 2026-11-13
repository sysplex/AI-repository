"""M5 数字溯源校验引擎与防编造防御单元测试（T05）。

依据 docs/08-test-plan.md §4.3 全面验证：
1. 路径寻址与数值提取（resolve_path_value, extract_numbers_from_text, extract_numeric_facts）；
2. 基础数值溯源：
   - 合法报告 100% 校验通过；
   - 容差与百分比自动换算（0.15 vs 15%）；
   - 通用常数与交易周期豁免；
3. 防编造违规拦截：
   - 编造未在 facts 中出现过的数字（untraced_number）；
   - 显式 source_field 指向不存在的事实路径（invalid_source_path）；
   - 显式 source_field 存在但数值不符（untraced_number）；
   - 包含非法保本/稳赚保证性禁用词（banned_guarantee_term）；
4. verify_or_raise 异常抛出与 details 结构测试。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.core.errors import AppError, ErrorCode
from app.modules.ai.exceptions import FactTracingError
from app.modules.ai.schemas import FactTracingResult
from app.modules.ai.tracing import (
    DEFAULT_BANNED_TERMS,
    FactTracingEngine,
    extract_numbers_from_text,
    extract_numeric_facts,
    resolve_path_value,
    verify_fact_tracing,
)


@pytest.fixture
def sample_facts() -> dict[str, Any]:
    """标准测试事实快照"""
    return {
        "symbol": "AAPL",
        "quote": {
            "current_price": Decimal("182.50"),
            "high_52w": Decimal("199.62"),
            "low_52w": Decimal("164.08"),
            "change_pct": Decimal("0.015"),  # 1.5%
            "volume": 48500000,
        },
        "fundamentals": {
            "pe_ratio": Decimal("28.4"),
            "pb_ratio": Decimal("35.2"),
            "revenue_growth": Decimal("0.082"),  # 8.2%
            "net_margin": Decimal("0.253"),  # 25.3%
            "market_cap": Decimal("2800000000000"),
        },
        "historical_prices": [
            {"date": "2024-01-02", "close": Decimal("185.64")},
            {"date": "2024-01-03", "close": Decimal("184.25")},
        ],
    }


@pytest.fixture
def sample_computed() -> dict[str, Any]:
    """标准技术指标与派生事实"""
    return {
        "technical": {
            "sma_20": Decimal("180.10"),
            "sma_50": Decimal("176.50"),
            "rsi_14": Decimal("58.2"),
            "atr": Decimal("2.85"),
        },
        "support_resistance": {
            "support_1": Decimal("178.00"),
            "resistance_1": Decimal("188.50"),
        },
    }


# =============================================================================
# 1. 基础工具函数测试
# =============================================================================


def test_resolve_path_value() -> None:
    """验证按点路径解析字典与列表索引。"""
    data = {
        "a": {"b": {"c": 42}},
        "items": [{"name": "first", "score": 99}],
    }
    assert resolve_path_value(data, "a.b.c") == 42
    assert resolve_path_value(data, "items.0.score") == 99
    assert resolve_path_value(data, "items.0.name") == "first"
    assert resolve_path_value(data, "non_existent.path") is None
    assert resolve_path_value(data, "items.5.score") is None
    assert resolve_path_value(data, "") is None


def test_extract_numbers_from_text() -> None:
    """验证从任意自然语言文本中提取各类数值与百分比。"""
    text = "AAPL closed at $182.50 (+1.5%), with 50-day moving average at 176.50."
    extracted = extract_numbers_from_text(text)
    values = [val for val, _ in extracted]

    assert Decimal("182.50") in values
    assert Decimal("1.5") in values
    assert Decimal("50") in values
    assert Decimal("176.50") in values
    assert extract_numbers_from_text("") == []


def test_extract_numeric_facts(sample_facts: dict[str, Any]) -> None:
    """验证从事实字典中递归扁平化提取数值与其来源路径。"""
    facts_list = extract_numeric_facts(sample_facts)
    fact_dict = {path: val for val, path in facts_list}

    assert fact_dict["quote.current_price"] == Decimal("182.50")
    assert fact_dict["fundamentals.pe_ratio"] == Decimal("28.4")
    assert fact_dict["historical_prices.0.close"] == Decimal("185.64")


# =============================================================================
# 2. 正常合法输出溯源测试
# =============================================================================


def test_valid_payload_all_numbers_traced(
    sample_facts: dict[str, Any],
    sample_computed: dict[str, Any],
) -> None:
    """合规模型输出中的全部数值均能在 facts 与 computed 中溯源。"""
    engine = FactTracingEngine()

    legit_payload = {
        "symbol": "AAPL",
        "verdict": "buy",
        "key_metrics": {
            "current_price": Decimal("182.50"),
            "pe_ratio": Decimal("28.4"),
            "sma_20": Decimal("180.10"),
            "support_price": Decimal("178.00"),
        },
        "summary": "Stock is currently trading at 182.50, above the 20-day SMA of 180.10.",
    }

    result = engine.verify(legit_payload, sample_facts, computed=sample_computed)
    assert result.valid is True
    assert result.violations == []
    assert result.checked_numbers_count > 0


def test_percentage_equivalence_and_tolerance(sample_facts: dict[str, Any]) -> None:
    """验证事实中为小数（0.015 / 0.082）时，模型输出为百分比（1.5% / 8.2%）能等价溯源。"""
    engine = FactTracingEngine()

    pct_payload = {
        "metrics": {
            "daily_gain": Decimal("1.5"),  # 等价于 facts 中的 0.015 (1.5%)
            "growth": Decimal("8.2"),  # 等价于 facts 中的 0.082 (8.2%)
        },
        "text_comment": "Revenue growth reached 8.2% with daily rise of 1.5%.",
    }

    result = engine.verify(pct_payload, sample_facts)
    assert result.valid is True
    assert result.violations == []


def test_exempt_standard_constants_ignored(sample_facts: dict[str, Any]) -> None:
    """验证标准周期常数（5, 20, 50, 200）、年份（2024）与小整数不误报编造。"""
    engine = FactTracingEngine()

    standard_text_payload = {
        "horizon_days": 20,
        "sma_period": 50,
        "calendar_year": 2024,
        "ranking": 1,
        "notes": "Looking forward to 2025 performance over 20-day horizon.",
    }

    result = engine.verify(standard_text_payload, sample_facts)
    assert result.valid is True
    assert result.violations == []


# =============================================================================
# 3. 编造数字与幻觉拦截测试（docs/08 §4.3）
# =============================================================================


def test_hallucinated_fabricated_numbers_detected(sample_facts: dict[str, Any]) -> None:
    """拦截在事实库中不存在的编造价格与虚假财务指标。"""
    engine = FactTracingEngine()

    fake_payload = {
        "symbol": "AAPL",
        "verdict": "buy",
        "key_metrics": {
            "current_price": Decimal("182.50"),  # 合法
            "phantom_target_price": Decimal("999999.99"),  # 编造虚假数值
            "hallucinated_pe": Decimal("88.88"),  # 编造虚假 PE
        },
    }

    result = engine.verify(fake_payload, sample_facts)
    assert result.valid is False
    assert len(result.violations) == 2

    reasons = [v.reason for v in result.violations]
    assert reasons == ["untraced_number", "untraced_number"]
    claimed_values = [v.claimed_value for v in result.violations]
    assert Decimal("999999.99") in claimed_values
    assert Decimal("88.88") in claimed_values


def test_hallucinated_numbers_in_free_text(sample_facts: dict[str, Any]) -> None:
    """从自然语言文本中识别并拦截编造虚假数字。"""
    engine = FactTracingEngine()

    free_text_payload = {
        "summary": "We anticipate a crazy surge to 9876.54 next week with PE of 123.45."
    }

    result = engine.verify(free_text_payload, sample_facts)
    assert result.valid is False
    assert len(result.violations) == 2
    assert all(v.reason == "untraced_number" for v in result.violations)


# =============================================================================
# 4. 显式 source_field 路径校验测试
# =============================================================================


def test_explicit_source_path_valid(sample_facts: dict[str, Any]) -> None:
    """显式 source_field 路径存在且数值一致时通过。"""
    engine = FactTracingEngine()

    payload = {
        "metrics": [
            {
                "name": "Current Price",
                "value": Decimal("182.50"),
                "source_field": "quote.current_price",
            },
            {
                "name": "P/E Ratio",
                "value": Decimal("28.4"),
                "source_path": "fundamentals.pe_ratio",
            },
        ]
    }

    result = engine.verify(payload, sample_facts)
    assert result.valid is True
    assert result.violations == []


def test_explicit_source_path_invalid_path(sample_facts: dict[str, Any]) -> None:
    """显式 source_field 指向不存在的事实路径时拦截。"""
    engine = FactTracingEngine()

    payload = {
        "metrics": [
            {
                "name": "Phantom Metric",
                "value": Decimal("182.50"),
                "source_field": "fundamentals.does_not_exist",
            }
        ]
    }

    result = engine.verify(payload, sample_facts)
    assert result.valid is False
    assert len(result.violations) == 1
    assert result.violations[0].reason == "invalid_source_path"
    assert result.violations[0].claimed_value == "fundamentals.does_not_exist"


def test_explicit_source_path_value_mismatch(sample_facts: dict[str, Any]) -> None:
    """显式 source_field 路径存在但所声称的数值与真实事实不一致时拦截。"""
    engine = FactTracingEngine()

    payload = {
        "metrics": [
            {
                "name": "Price with Lie",
                "value": Decimal("250.00"),  # 真实是 182.50
                "source_field": "quote.current_price",
            }
        ]
    }

    result = engine.verify(payload, sample_facts)
    assert result.valid is False
    assert len(result.violations) == 1
    assert result.violations[0].reason == "untraced_number"
    assert result.violations[0].claimed_value == Decimal("250.00")


# =============================================================================
# 5. 投资保证性禁用词合规拦截测试
# =============================================================================


@pytest.mark.parametrize("banned_term", DEFAULT_BANNED_TERMS[:5])
def test_banned_terms_intercepted(banned_term: str, sample_facts: dict[str, Any]) -> None:
    """拦截绝对化投资收益与保本承诺违规词汇。"""
    engine = FactTracingEngine()

    payload = {
        "symbol": "AAPL",
        "verdict": "buy",
        "recommendation": f"该投资策略{banned_term}，请立即全仓买入！",
    }

    result = engine.verify(payload, sample_facts)
    assert result.valid is False
    assert any(v.reason == "banned_guarantee_term" for v in result.violations)
    assert any(v.claimed_value == banned_term for v in result.violations)


# =============================================================================
# 6. verify_or_raise 异常与快捷入口测试
# =============================================================================


def test_verify_or_raise_success(sample_facts: dict[str, Any]) -> None:
    """合规通过时不抛出异常并返回结果。"""
    engine = FactTracingEngine()
    res = engine.verify_or_raise({"price": Decimal("182.50")}, sample_facts)
    assert isinstance(res, FactTracingResult)
    assert res.valid is True


def test_verify_or_raise_failure(sample_facts: dict[str, Any]) -> None:
    """违规时抛出统一业务异常 FactTracingError (HTTP 422)。"""
    engine = FactTracingEngine()
    with pytest.raises(FactTracingError) as exc_info:
        engine.verify_or_raise(
            {"fake_metric": Decimal("1234567.89")},
            sample_facts,
        )

    err = exc_info.value
    assert isinstance(err, AppError)
    assert err.code == ErrorCode.LLM_OUTPUT_INVALID
    assert err.http_status == 422
    assert "Fact tracing check failed" in err.message
    assert len(err.details["violations"]) == 1


def test_verify_fact_tracing_convenience_function(sample_facts: dict[str, Any]) -> None:
    """测试快捷函数 verify_fact_tracing。"""
    res = verify_fact_tracing({"price": Decimal("182.50")}, sample_facts)
    assert res.valid is True
