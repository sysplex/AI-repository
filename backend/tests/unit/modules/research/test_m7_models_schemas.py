"""Unit tests for M7 domain models, DTO schemas, and ports (M7 / T01).

Validates:
1. F4: CompareRequest, CompareRankingItem, DimensionNotes, FitByInvestorItem, ComparePayload
2. F5: LongTermRequest, LongTermPillarItem, LongTermPillars, ThesisBreakerItem, LongTermPayload
3. F8: PortfolioRequest, PortfolioAllocationItem, PortfolioPayload
4. Boundary constraints (2-8 symbols, 5/10/15 years, amount > 0, thesis_breakers >= 3)
5. Protocol conformance and typing checks.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.research.ports import ResearchServiceProtocol
from app.modules.research.schemas import (
    ComparePayload,
    CompareRankingItem,
    CompareRequest,
    LongTermPayload,
    LongTermPillarItem,
    LongTermPillars,
    LongTermRequest,
    PortfolioPayload,
    PortfolioRequest,
    ThesisBreakerItem,
)

pytestmark = pytest.mark.unit


# =============================================================================
# 1. F4: Compare (股票横向对比) Schemas 测试
# =============================================================================


def test_compare_request_valid() -> None:
    """验证有效的 2–8 只股票横向对比入参。"""
    req2 = CompareRequest(symbols=["AAPL", "CAT"])
    assert len(req2.symbols) == 2
    assert req2.symbols == ["AAPL", "CAT"]

    req8 = CompareRequest(symbols=["AAPL", "CAT", "KO", "PLTR", "SOFI", "MSFT", "GOOG", "AMZN"])
    assert len(req8.symbols) == 8


def test_compare_request_boundary_violations() -> None:
    """验证不足 2 只或超过 8 只股票触发 ValidationError。"""
    # 少于 2 只
    with pytest.raises(ValidationError) as exc1:
        CompareRequest(symbols=["AAPL"])
    assert "symbols" in str(exc1.value)

    # 超过 8 只
    with pytest.raises(ValidationError) as exc2:
        CompareRequest(symbols=["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"])
    assert "symbols" in str(exc2.value)


def test_compare_payload_valid() -> None:
    """验证完整的 ComparePayload 序列化与反序列化。"""
    raw_data = {
        "symbols": ["AAPL", "CAT"],
        "ranking": [
            {
                "symbol": "AAPL",
                "rank": 1,
                "total_score": Decimal("85.50"),
                "one_line_reason": "护城河极深，自由现金流充沛",
            },
            {
                "symbol": "CAT",
                "rank": 2,
                "total_score": Decimal("72.20"),
                "one_line_reason": "重工周期景气度高，但受宏观敏感性大",
            },
        ],
        "dimension_notes": {
            "growth": "AAPL 偏温和稳健，CAT 处于周期中后段",
            "margin": "AAPL 净利润率远高于 CAT",
            "debt": "两家杠杆均处于安全可控区间",
            "valuation": "CAT PE 估值相对更低",
            "moat": "AAPL 生态系统壁垒更强",
            "risk": "CAT 宏观周期风险大于 AAPL",
            "dividend": "CAT 股息率相对更高",
            "long_term": "AAPL 长期现金流可见度更高",
        },
        "fit_by_investor": [
            {
                "symbol": "AAPL",
                "suitable_for": ["稳健型投资者", "核心底仓配置"],
                "not_suitable_for": ["短期博取高弹性的投机者"],
            },
            {
                "symbol": "CAT",
                "suitable_for": ["顺周期配置", "高股息关注者"],
                "not_suitable_for": ["风险厌恶型防守者"],
            },
        ],
        "summary": "综合来看，AAPL 在护城河与稳定性上占优，CAT 在当前估值与股息回报上具吸引力。",
    }

    payload = ComparePayload.model_validate(raw_data)
    assert payload.symbols == ["AAPL", "CAT"]
    assert payload.ranking[0].rank == 1
    assert payload.ranking[0].total_score == Decimal("85.50")
    assert payload.dimension_notes.moat == "AAPL 生态系统壁垒更强"
    assert len(payload.fit_by_investor) == 2


def test_compare_ranking_item_rank_constraint() -> None:
    """验证 CompareRankingItem 的 rank 必须大于等于 1。"""
    with pytest.raises(ValidationError):
        CompareRankingItem(
            symbol="AAPL",
            rank=0,  # 非法: ge=1
            total_score=Decimal("80.0"),
            one_line_reason="Reason",
        )


# =============================================================================
# 2. F5: LongTerm (长期持有与破裂条件) Schemas 测试
# =============================================================================


def test_long_term_request_valid() -> None:
    """验证有效的长期持有请求入参（支持 5/10/15 年）。"""
    r5 = LongTermRequest(symbol="AAPL", years=5)
    assert r5.years == 5

    r10 = LongTermRequest(symbol="KO", years=10)
    assert r10.years == 10

    r15 = LongTermRequest(symbol="CAT", years=15)
    assert r15.years == 15

    # 默认 years 为 5
    r_default = LongTermRequest(symbol="PLTR")
    assert r_default.years == 5


def test_long_term_request_invalid_years() -> None:
    """验证非法年限被拒绝。"""
    with pytest.raises(ValidationError) as exc:
        LongTermRequest(symbol="AAPL", years=3)  # type: ignore[arg-type]
    assert "years" in str(exc.value)

    with pytest.raises(ValidationError):
        LongTermRequest(symbol="AAPL", years=20)  # type: ignore[arg-type]


def test_long_term_payload_valid() -> None:
    """验证 LongTermPayload 及其 7 大支柱和破裂条件。"""
    payload_dict = {
        "symbol": "AAPL",
        "horizon_years": 10,
        "verdict": "holdable",
        "pillars": {
            "moat": {"rating": "strong", "reason": "全球超过 20 亿活跃设备网络效应"},
            "leadership": {"rating": "strong", "reason": "稳健的资本配置策略与持续回购"},
            "demand_stability": {"rating": "favorable", "reason": "消费电子高复购与服务订阅黏性"},
            "pricing_power": {"rating": "strong", "reason": "硬件与应用商店具备绝对定价权"},
            "innovation": {"rating": "moderate", "reason": "自研芯片领先，AI 端侧落地稳步推进"},
            "financial_strength": {"rating": "strong", "reason": "千亿级自由现金流"},
            "market_size": {"rating": "favorable", "reason": "穿戴设备与数字服务仍有空间"},
        },
        "thesis": "苹果公司依托 iOS 生态高转换成本与强韧的自由现金流，具备跨周期的长期复利价值。",
        "thesis_breakers": [
            {
                "condition": "活跃设备数连续两个季度净减少",
                "metric": "active_devices",
                "threshold": "< 2.0B",
                "data_field": "fundamentals.active_devices",
            },
            {
                "condition": "服务业务营收占比跌破 15%",
                "metric": "services_share_pct",
                "threshold": "< 0.15",
                "data_field": "fundamentals.services_share_pct",
            },
            {
                "condition": "净利润率收窄低于 20%",
                "metric": "net_margin",
                "threshold": "< 0.20",
                "data_field": "fundamentals.net_margin",
            },
        ],
        "summary": "10 年期可买入并长期持有，密切跟踪生态设备活跃基数。",
    }

    payload = LongTermPayload.model_validate(payload_dict)
    assert payload.symbol == "AAPL"
    assert payload.horizon_years == 10
    assert payload.verdict == "holdable"
    assert payload.pillars.moat.rating == "strong"
    assert len(payload.thesis_breakers) == 3
    assert payload.thesis_breakers[2].metric == "net_margin"


def test_long_term_payload_requires_minimum_3_breakers() -> None:
    """验证 thesis_breakers 少于 3 条时抛出 ValidationError（必须具备可监控性）。"""
    pillars = LongTermPillars(
        moat=LongTermPillarItem(rating="strong", reason="Moat"),
        leadership=LongTermPillarItem(rating="strong", reason="Leadership"),
        demand_stability=LongTermPillarItem(rating="strong", reason="Demand"),
        pricing_power=LongTermPillarItem(rating="strong", reason="Pricing"),
        innovation=LongTermPillarItem(rating="strong", reason="Innovation"),
        financial_strength=LongTermPillarItem(rating="strong", reason="Financial"),
        market_size=LongTermPillarItem(rating="strong", reason="Market"),
    )

    with pytest.raises(ValidationError) as exc:
        LongTermPayload(
            symbol="AAPL",
            horizon_years=5,
            verdict="holdable",
            pillars=pillars,
            thesis="Thesis",
            thesis_breakers=[  # 仅 2 条，要求 min_length=3
                ThesisBreakerItem(condition="C1", metric="M1", threshold="< 1", data_field="f.m1"),
                ThesisBreakerItem(condition="C2", metric="M2", threshold="< 2", data_field="f.m2"),
            ],
            summary="Summary",
        )
    assert "thesis_breakers" in str(exc.value)


# =============================================================================
# 3. F8: Portfolio (投资组合配置) Schemas 测试
# =============================================================================


def test_portfolio_request_valid() -> None:
    """验证有效的投资组合配置请求入参。"""
    req = PortfolioRequest(
        amount=Decimal("50000.00"),
        symbols=["AAPL", "CAT", "KO"],
        risk_level="conservative",
        goal="income",
    )
    assert req.amount == Decimal("50000.00")
    assert req.symbols == ["AAPL", "CAT", "KO"]
    assert req.risk_level == "conservative"
    assert req.goal == "income"


def test_portfolio_request_validations() -> None:
    """验证 PortfolioRequest 金额必须大于 0 且标的不少于 2 只。"""
    # 金额为 0
    with pytest.raises(ValidationError) as exc1:
        PortfolioRequest(
            amount=Decimal("0.00"),
            symbols=["AAPL", "CAT"],
        )
    assert "amount" in str(exc1.value)

    # 金额为负数
    with pytest.raises(ValidationError):
        PortfolioRequest(
            amount=Decimal("-1000.00"),
            symbols=["AAPL", "CAT"],
        )

    # 标的仅 1 只
    with pytest.raises(ValidationError) as exc3:
        PortfolioRequest(
            amount=Decimal("10000.00"),
            symbols=["AAPL"],
        )
    assert "symbols" in str(exc3.value)


def test_portfolio_payload_valid() -> None:
    """验证 PortfolioPayload 及其权重与金额。"""
    payload_dict = {
        "amount": Decimal("100000.00"),
        "allocations": [
            {
                "symbol": "AAPL",
                "weight_pct": Decimal("40.00"),
                "allocated_amount": Decimal("40000.00"),
                "reason": "大盘科技底仓，提供稳定的成长与质量防御",
            },
            {
                "symbol": "KO",
                "weight_pct": Decimal("30.00"),
                "allocated_amount": Decimal("30000.00"),
                "reason": "高股息防御性资产，平滑组合整体波动",
            },
            {
                "symbol": "CAT",
                "weight_pct": Decimal("15.00"),
                "allocated_amount": Decimal("15000.00"),
                "reason": "顺周期弹性卫星配置",
            },
        ],
        "cash_pct": Decimal("15.00"),
        "cash_amount": Decimal("15000.00"),
        "rationale": "构建 70% 核心底仓 + 15% 周期弹性 + 15% 现金防守的平衡型组合。",
        "risk_notes": "注意工业板块在宏观加息周期中的盈利下行压力，建议适时用现金择机补仓。",
        "rebalance_suggestion": "每季度末或任意单个标的权重偏离度超过 5% 时执行动态再平衡。",
    }

    payload = PortfolioPayload.model_validate(payload_dict)
    assert payload.amount == Decimal("100000.00")
    assert len(payload.allocations) == 3
    assert payload.cash_pct == Decimal("15.00")
    assert payload.cash_amount == Decimal("15000.00")

    # 验证权重求和恒等式
    total_weights = sum(item.weight_pct for item in payload.allocations) + payload.cash_pct
    assert total_weights == Decimal("100.00")


# =============================================================================
# 4. ResearchServiceProtocol 契约兼容性测试
# =============================================================================


def test_research_service_protocol_conformance() -> None:
    """验证 Dummy 服务类满足扩展后的 ResearchServiceProtocol 契约。"""

    class DummyResearchService:
        async def get_stock_research(self, request: Any, user_id: uuid.UUID) -> Any: ...
        async def get_buy_decision(self, request: Any, user_id: uuid.UUID) -> Any: ...
        async def get_technical_analysis(self, request: Any, user_id: uuid.UUID) -> Any: ...
        async def get_earnings_analysis(self, request: Any, user_id: uuid.UUID) -> Any: ...
        async def compare_stocks(self, request: Any, user_id: uuid.UUID) -> Any: ...
        async def get_long_term_analysis(self, request: Any, user_id: uuid.UUID) -> Any: ...
        async def generate_portfolio_allocation(self, request: Any, user_id: uuid.UUID) -> Any: ...

    dummy = DummyResearchService()
    assert isinstance(dummy, ResearchServiceProtocol)
