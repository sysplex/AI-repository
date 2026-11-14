"""Unit tests for research module schemas, exceptions, and DTO contracts (M6-T01)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.errors import ErrorCode
from app.modules.research.exceptions import (
    InsufficientDataError,
    InvalidParameterError,
    QuantitativeCalculationError,
    ResearchError,
    SymbolNotFoundError,
)
from app.modules.research.schemas import (
    BuyDecisionPayload,
    BuyDecisionRequest,
    EarningsAnalysisRequest,
    EarningsMetric,
    EarningsPayload,
    EvidenceItem,
    FactorAssessment,
    FactorItem,
    MoatItem,
    PricePosition,
    ResearchEnvelope,
    ResearchPayload,
    ResearchRequest,
    RevenueSourceItem,
    RiskItem,
    Scenarios,
    TechnicalAnalysisRequest,
    TechnicalMetricExplanation,
    TechnicalPayload,
    TradePlan,
)

# =============================================================================
# 1. 通用组件测试
# =============================================================================


def test_evidence_item_and_envelope_valid() -> None:
    evidence = EvidenceItem(
        claim="PE ratio higher than peers",
        source_field="facts.valuation.pe_ttm",
    )
    assert evidence.claim == "PE ratio higher than peers"
    assert evidence.source_field == "facts.valuation.pe_ttm"

    envelope = ResearchEnvelope(
        use_case="research",
        symbol="AAPL",
        as_of=date(2026, 11, 14),
        summary="Apple continues to demonstrate robust free cash flow and services growth.",
        payload={"sample_key": "sample_val"},
        evidence=[evidence],
        data_gaps=["analyst.price_target_median"],
    )

    assert envelope.schema_version == "1.0"
    assert envelope.symbol == "AAPL"
    assert envelope.as_of == date(2026, 11, 14)
    assert envelope.disclaimer == "本内容仅供研究与学习，不构成投资建议"
    assert len(envelope.evidence) == 1
    assert envelope.data_gaps == ["analyst.price_target_median"]


def test_envelope_immutability() -> None:
    envelope = ResearchEnvelope(
        use_case="research",
        symbol="AAPL",
        as_of=date(2026, 11, 14),
        summary="Summary",
        payload={},
    )
    with pytest.raises(ValidationError):
        envelope.symbol = "MSFT"  # type: ignore[misc]


# =============================================================================
# 2. F2: 股票研究 (research) Schemas 测试
# =============================================================================


def test_research_request_valid() -> None:
    req = ResearchRequest(symbol="AAPL")
    assert req.symbol == "AAPL"


def test_research_request_invalid_symbol() -> None:
    with pytest.raises(ValidationError):
        ResearchRequest(symbol="")
    with pytest.raises(ValidationError):
        ResearchRequest(symbol="A" * 17)


def test_research_payload_valid() -> None:
    payload = ResearchPayload(
        business_model="Apple sells premium consumer devices and subscription services.",
        revenue_sources=[
            RevenueSourceItem(name="iPhone", share_pct=Decimal("52.5"), note="Flagship phone"),
            RevenueSourceItem(name="Services", share_pct=Decimal("22.1"), note="App store, iCloud"),
        ],
        moats=[
            MoatItem(
                type="Switching Costs",
                explanation="iOS ecosystem creates high switching cost.",
                strength="strong",
            ),
            MoatItem(type="Brand", explanation="Recognizable premium brand.", strength="strong"),
        ],
        risks=[
            RiskItem(
                risk="Supply Chain",
                severity="medium",
                plain_explanation="Concentration in APAC.",
            )
        ],
        recent_performance="Stock up 15% year-to-date driven by AI features.",
        debt_and_profit="Net cash neutral target, exceptional free cash flow.",
        growth_potential="Growth expected from wearables, AI devices, and enterprise services.",
        scenarios=Scenarios(
            bull="AI upgrade cycle supercharges iPhone sales.",
            bear="Antitrust headwinds hurt App Store margin.",
            neutral="Single digit revenue growth with steady share repurchases.",
        ),
        beginner_takeaway=[
            "Apple is a cash generator with massive brand loyalty.",
            "Growth is steady rather than explosive.",
        ],
    )

    assert payload.business_model.startswith("Apple")
    assert len(payload.revenue_sources) == 2
    assert payload.revenue_sources[0].share_pct == Decimal("52.5")
    assert len(payload.moats) == 2
    assert payload.scenarios.bull.startswith("AI upgrade")
    assert len(payload.beginner_takeaway) == 2


def test_research_payload_invalid_strength_and_takeaway() -> None:
    with pytest.raises(ValidationError):
        MoatItem(type="Brand", explanation="Good brand", strength="super_strong")

    with pytest.raises(ValidationError):
        ResearchPayload(
            business_model="Model",
            revenue_sources=[],
            moats=[],
            risks=[],
            recent_performance="Perf",
            debt_and_profit="Debt",
            growth_potential="Growth",
            scenarios=Scenarios(bull="b", bear="be", neutral="n"),
            beginner_takeaway=[],  # Empty list violates min_length=1
        )


# =============================================================================
# 3. F3: 买入决策 (buy_decision) Schemas 测试
# =============================================================================


def test_buy_decision_request_valid() -> None:
    req = BuyDecisionRequest(
        symbol="AAPL",
        target_price=Decimal("180.50"),
        horizon="medium",
        risk_level="moderate",
    )
    assert req.symbol == "AAPL"
    assert req.target_price == Decimal("180.50")
    assert req.horizon == "medium"
    assert req.risk_level == "moderate"


def test_buy_decision_request_invalid_price_and_enum() -> None:
    with pytest.raises(ValidationError):
        BuyDecisionRequest(symbol="AAPL", target_price=Decimal("0.0"))

    with pytest.raises(ValidationError):
        BuyDecisionRequest(symbol="AAPL", target_price=Decimal("-10.0"))

    with pytest.raises(ValidationError):
        BuyDecisionRequest(
            symbol="AAPL",
            target_price=Decimal("100.0"),
            horizon="ultra_long",
        )


def test_buy_decision_payload_valid() -> None:
    assessment = FactorAssessment(
        valuation=FactorItem(rating="neutral", reason="PE is near 5-year average"),
        earnings_growth=FactorItem(rating="favorable", reason="Expected 10% EPS growth"),
        industry_trend=FactorItem(rating="favorable", reason="Consumer electronics recovering"),
        news=FactorItem(rating="neutral", reason="Neutral product launch reviews"),
        analyst_view=FactorItem(rating="favorable", reason="Median price target $240"),
        downside_risk=FactorItem(rating="neutral", reason="Strong cash buffer limits downside"),
    )
    price_pos = PricePosition(
        target_vs_price_pct=Decimal("-5.25"),
        pos_in_52w_range=Decimal("0.72"),
        valuation_position="Historical 3-year 55th percentile",
    )
    payload = BuyDecisionPayload(
        verdict="buy",
        confidence=0.85,
        factor_assessment=assessment,
        price_position=price_pos,
        better_entry_note="Consider scaling in if price drops below $175 (support).",
        key_risks=["Macro consumer spending slowdown", "China market competitive pressure"],
        what_would_change_view=[
            "iPhone revenue contraction exceeds 5% for two consecutive quarters"
        ],
    )

    assert payload.verdict == "buy"
    assert payload.confidence == 0.85
    assert payload.price_position.target_vs_price_pct == Decimal("-5.25")
    assert payload.price_position.pos_in_52w_range == Decimal("0.72")
    assert payload.factor_assessment.valuation.rating == "neutral"


def test_buy_decision_payload_invalid_confidence_and_range() -> None:
    # 1. PricePosition 52w range > 1.0 validation
    with pytest.raises(ValidationError):
        PricePosition(
            target_vs_price_pct=Decimal("0"),
            pos_in_52w_range=Decimal("1.5"),  # Exceeds 1.0
        )

    # 2. BuyDecisionPayload confidence > 1.0 validation
    assessment = FactorAssessment(
        valuation=FactorItem(rating="neutral", reason="r"),
        earnings_growth=FactorItem(rating="neutral", reason="r"),
        industry_trend=FactorItem(rating="neutral", reason="r"),
        news=FactorItem(rating="neutral", reason="r"),
        analyst_view=FactorItem(rating="neutral", reason="r"),
        downside_risk=FactorItem(rating="neutral", reason="r"),
    )
    price_pos = PricePosition(
        target_vs_price_pct=Decimal("0"),
        pos_in_52w_range=Decimal("0.5"),
    )
    with pytest.raises(ValidationError):
        BuyDecisionPayload(
            verdict="buy",
            confidence=1.2,  # Exceeds 1.0
            factor_assessment=assessment,
            price_position=price_pos,
            better_entry_note="note",
            key_risks=[],
            what_would_change_view=["condition"],
        )


# =============================================================================
# 4. F6: 技术面分析 (technical) Schemas 测试
# =============================================================================


def test_technical_analysis_request_and_payload_valid() -> None:
    req = TechnicalAnalysisRequest(symbol="TSLA")
    assert req.symbol == "TSLA"

    trade_plan = TradePlan(
        entry=Decimal("220.00"),
        stop=Decimal("205.00"),
        target=Decimal("265.00"),
        risk_reward=Decimal("3.00"),
    )
    assert trade_plan.risk_reward == Decimal("3.00")

    payload = TechnicalPayload(
        trend=TechnicalMetricExplanation(
            value="Bullish",
            plain_explanation="Stock trading above 50-day and 200-day moving averages.",
        ),
        support_resistance=TechnicalMetricExplanation(
            value={"support": 210, "resistance": 250},
            plain_explanation="Strong floor at 210, ceiling at 250.",
        ),
        moving_averages=TechnicalMetricExplanation(
            value="Golden Cross",
            plain_explanation="50-day SMA crossed above 200-day SMA.",
        ),
        volume=TechnicalMetricExplanation(
            value="Above Average",
            plain_explanation="Higher buying volume on up days indicates interest.",
        ),
        rsi=TechnicalMetricExplanation(
            value=58.5,
            plain_explanation="Healthy momentum, neither overbought nor oversold.",
        ),
        macd=TechnicalMetricExplanation(
            value="Bullish Crossover",
            plain_explanation="MACD line crossed above signal line.",
        ),
        breakout=TechnicalMetricExplanation(
            value="Ascending Triangle",
            plain_explanation="Forming higher lows, testing resistance.",
        ),
        trade_plan=trade_plan,
        beginner_takeaway=[
            "Trend is your friend: momentum currently favors buyers.",
            "Strictly respect the $205 stop-loss to manage downside.",
        ],
    )

    assert payload.trend.value == "Bullish"
    assert payload.trade_plan.entry == Decimal("220.00")
    assert payload.trade_plan.stop == Decimal("205.00")
    assert payload.trade_plan.target == Decimal("265.00")
    assert len(payload.beginner_takeaway) == 2


def test_trade_plan_validation() -> None:
    with pytest.raises(ValidationError):
        TradePlan(
            entry=Decimal("-10.00"),
            stop=Decimal("5.00"),
            target=Decimal("20.00"),
            risk_reward=Decimal("2.0"),
        )


# =============================================================================
# 5. F7: 财报解读 (earnings) Schemas 测试
# =============================================================================


def test_earnings_analysis_request_and_payload_valid() -> None:
    req = EarningsAnalysisRequest(symbol="NVDA")
    assert req.symbol == "NVDA"

    payload = EarningsPayload(
        revenue=EarningsMetric(
            actual=Decimal("30.04"),
            expected=Decimal("28.70"),
            surprise_pct=Decimal("4.67"),
            explanation="Record data center revenue propelled top-line beat.",
        ),
        eps=EarningsMetric(
            actual=Decimal("0.68"),
            expected=Decimal("0.64"),
            surprise_pct=Decimal("6.25"),
            explanation="Strong gross margins delivered higher bottom-line profit.",
        ),
        margins=EarningsMetric(
            actual="75.1%",
            expected="74.8%",
            surprise_pct="0.3%",
            explanation="Gross margin expansion demonstrates formidable pricing power.",
        ),
        guidance="Next quarter revenue guidance $32.5B vs consensus $31.8B.",
        management_commentary=[
            "Blackwell chip demand is extraordinary with capacity booked.",
            "Enterprise AI adoption accelerating across sovereign AI initiatives.",
        ],
        market_reaction="Up 2.8% in post-market trading.",
        assessment="strong",
        short_term_outlook="Bullish sentiment likely to sustain near-term momentum.",
        long_term_outlook="Structural tailwinds in accelerated computing intact.",
    )

    assert payload.assessment == "strong"
    assert payload.revenue.actual == Decimal("30.04")
    assert payload.margins.actual == "75.1%"
    assert len(payload.management_commentary) == 2


def test_earnings_missing_fields_representation() -> None:
    # When data is missing, "数据缺失" is used
    payload = EarningsPayload(
        revenue=EarningsMetric(
            actual="数据缺失",
            expected="数据缺失",
            surprise_pct="数据缺失",
            explanation="数据缺失",
        ),
        eps=EarningsMetric(
            actual="数据缺失",
            expected="数据缺失",
            surprise_pct="数据缺失",
            explanation="数据缺失",
        ),
        margins=EarningsMetric(
            actual="数据缺失",
            expected="数据缺失",
            surprise_pct="数据缺失",
            explanation="数据缺失",
        ),
        guidance="数据缺失",
        management_commentary=[],
        market_reaction="数据缺失",
        assessment="mixed",
        short_term_outlook="数据缺失",
        long_term_outlook="数据缺失",
    )
    assert payload.assessment == "mixed"
    assert payload.revenue.actual == "数据缺失"


# =============================================================================
# 6. 异常类层级与状态码测试
# =============================================================================


def test_research_exceptions_hierarchy_and_codes() -> None:
    err_base = ResearchError("base error")
    assert err_base.code == ErrorCode.INTERNAL_ERROR
    assert err_base.http_status == 500

    err_symbol = SymbolNotFoundError("Symbol XYZ not found", details={"symbol": "XYZ"})
    assert isinstance(err_symbol, ResearchError)
    assert err_symbol.code == ErrorCode.NOT_FOUND
    assert err_symbol.http_status == 404
    assert err_symbol.details == {"symbol": "XYZ"}

    err_data = InsufficientDataError("Insufficient bars", details={"bars": 2})
    assert isinstance(err_data, ResearchError)
    assert err_data.code == ErrorCode.DATA_UNAVAILABLE
    assert err_data.http_status == 422

    err_param = InvalidParameterError("Invalid target_price", details={"price": -1})
    assert isinstance(err_param, ResearchError)
    assert err_param.code == ErrorCode.VALIDATION_ERROR
    assert err_param.http_status == 400

    err_quant = QuantitativeCalculationError("Zero division in 52w range")
    assert isinstance(err_quant, ResearchError)
    assert err_quant.code == ErrorCode.INTERNAL_ERROR
    assert err_quant.http_status == 500
