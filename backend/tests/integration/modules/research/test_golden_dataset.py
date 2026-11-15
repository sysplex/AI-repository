"""Golden dataset integration test suite for 5 representative stocks × 4 use cases (M6 / T07).

Validates:
1. Full 20-scenario test matrix ($5 \\text{ stocks} \\times 4 \\text{ use cases} = 20$):
   - AAPL (Large-cap tech / 大盘科技)
   - CAT (Cyclical industrial / 周期重工)
   - KO (High dividend defensive / 高分红防御)
   - PLTR (High valuation growth / 亏损/高估值成长)
   - SOFI (Small-cap high volatility / 小盘金融科技与指引缺失)
2. Schema validation compliance (100% adherence to all 4 payload schemas).
3. Fact tracing validation: all numbers in payload must trace to facts/computed (0 violations).
4. Deterministic code calculations:
   - F3: target_vs_price_pct and pos_in_52w_range match facts['computed'] 100%.
   - F6: trade_plan (entry, stop, target, risk_reward) matches facts['computed']['trade_plan'] 100%.
5. Fallback behavior:
   - SOFI missing earnings guidance normalized to '数据缺失'.
6. Novice readability & compliance:
   - Zero forbidden terms (保本, 稳赚, 零风险).
   - All envelopes carry statutory disclaimer.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.deps import current_user
from app.core.clock import get_clock
from app.modules.ai.schemas import AnalysisReport
from app.modules.ai.tracing import DEFAULT_BANNED_TERMS, FactTracingEngine
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.schemas import AuthenticatedUser, UserSettings
from app.modules.research.aggregator import (
    USE_CASE_BUY_DECISION,
    USE_CASE_EARNINGS,
    USE_CASE_RESEARCH,
    USE_CASE_TECHNICAL,
    FactAggregator,
)
from app.modules.research.api import get_current_user, get_research_service
from app.modules.research.compliance import (
    DEFAULT_DISCLAIMER,
    MISSING_DATA_PLACEHOLDER,
    check_novice_readability,
)
from app.modules.research.schemas import (
    BuyDecisionPayload,
    BuyDecisionRequest,
    EarningsAnalysisRequest,
    EarningsPayload,
    ResearchEnvelope,
    ResearchPayload,
    ResearchRequest,
    TechnicalAnalysisRequest,
    TechnicalPayload,
)
from app.modules.research.service import ResearchService
from tests.integration.modules.research.fixtures.golden_stocks import (
    build_mock_data_service,
    build_mock_strategy_service,
    generate_golden_llm_response,
    get_golden_stock,
    list_golden_symbols,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def auth_user() -> AuthenticatedUser:
    """Mock authenticated user for HARD-01."""
    return AuthenticatedUser(
        id=uuid.uuid4(),
        email="golden_tester@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(),
    )


@pytest.fixture
def golden_research_env() -> dict[str, Any]:
    """Sets up FactAggregator and mock AIService backed by golden dataset."""
    mock_data_service = build_mock_data_service()
    mock_strategy_service = build_mock_strategy_service()

    aggregator = FactAggregator(
        data_service=mock_data_service,
        strategy_service=mock_strategy_service,
    )

    mock_ai_service = AsyncMock()

    async def _mock_run(
        use_case: str,
        facts: dict[str, Any],
        params: dict[str, Any] | None = None,
        user_id: uuid.UUID | None = None,
        **kwargs: Any,
    ) -> AnalysisReport:
        sym = (params or {}).get("symbol") or facts.get("symbol") or "AAPL"
        payload = generate_golden_llm_response(sym, use_case, facts)

        # Run FactTracingEngine to enforce zero hallucination contract
        engine = FactTracingEngine()
        engine.verify_or_raise(payload=payload, facts=facts, computed=facts.get("computed"))

        return AnalysisReport(
            id=uuid.uuid4(),
            use_case=use_case,
            payload=payload,
            cached=False,
            data_snapshot_id=f"snap_{sym}_{use_case}",
            prompt_version="v1.0",
            model="gpt-4o",
            cost_usd=Decimal("0.005000"),
            created_at=get_clock().now(),
        )

    mock_ai_service.run.side_effect = _mock_run

    service = ResearchService(
        ai_service=mock_ai_service,
        fact_aggregator=aggregator,
    )

    return {
        "service": service,
        "aggregator": aggregator,
        "ai_service": mock_ai_service,
        "data_service": mock_data_service,
        "strategy_service": mock_strategy_service,
    }


# =============================================================================
# 1. F2: 股票综合研究 (research) 黄金集 5 标的验证
# =============================================================================


@pytest.mark.parametrize("symbol", list_golden_symbols())
async def test_golden_stock_research_f2(
    symbol: str,
    golden_research_env: dict[str, Any],
    auth_user: AuthenticatedUser,
) -> None:
    service: ResearchService = golden_research_env["service"]
    stock_data = get_golden_stock(symbol)

    req = ResearchRequest(symbol=symbol)
    envelope: ResearchEnvelope = await service.get_stock_research(req, user_id=auth_user.id)

    # 1. 结构与通用元数据断言
    assert envelope.schema_version == "1.0"
    assert envelope.use_case == USE_CASE_RESEARCH
    assert envelope.symbol == symbol
    assert envelope.disclaimer == DEFAULT_DISCLAIMER
    assert len(envelope.summary) > 0
    assert len(envelope.evidence) >= 1

    # 2. Schema 严格反序列化校验
    payload_obj = ResearchPayload.model_validate(envelope.payload)
    assert len(payload_obj.revenue_sources) >= 1
    assert len(payload_obj.moats) >= 1
    assert len(payload_obj.risks) >= 1
    assert len(payload_obj.beginner_takeaway) >= 1

    # 3. 股票特异性特征断言
    if stock_data.stock_type == "large_cap_tech":
        assert any(m.strength == "strong" for m in payload_obj.moats)
    elif stock_data.stock_type == "cyclical":
        assert any("宏观" in r.risk or "周期" in r.risk for r in payload_obj.risks)
    elif stock_data.stock_type == "high_dividend":
        assert stock_data.fundamentals["dividend_yield"] > Decimal("0.02")

    # 4. 新手可读性与合规检查
    is_readable, suggestions = check_novice_readability(
        envelope.payload, use_case=USE_CASE_RESEARCH
    )
    assert is_readable is True
    assert len(suggestions) == 0

    # 5. 绝对无禁用承诺词
    for term in DEFAULT_BANNED_TERMS:
        assert term not in str(envelope.payload)


# =============================================================================
# 2. F3: 买入决策评估 (buy_decision) 黄金集 5 标的验证
# =============================================================================


@pytest.mark.parametrize("symbol", list_golden_symbols())
async def test_golden_buy_decision_f3(
    symbol: str,
    golden_research_env: dict[str, Any],
    auth_user: AuthenticatedUser,
) -> None:
    service: ResearchService = golden_research_env["service"]
    aggregator: FactAggregator = golden_research_env["aggregator"]
    stock_data = get_golden_stock(symbol)

    req = BuyDecisionRequest(
        symbol=symbol,
        target_price=stock_data.target_price,
        horizon="medium",
        risk_level="moderate",
    )
    envelope: ResearchEnvelope = await service.get_buy_decision(req, user_id=auth_user.id)

    # 1. 通用元数据断言
    assert envelope.schema_version == "1.0"
    assert envelope.use_case == USE_CASE_BUY_DECISION
    assert envelope.symbol == symbol
    assert envelope.disclaimer == DEFAULT_DISCLAIMER

    # 2. Schema 严格反序列化校验
    payload_obj = BuyDecisionPayload.model_validate(envelope.payload)
    assert payload_obj.verdict in {"buy", "wait", "avoid"}
    assert 0.0 <= payload_obj.confidence <= 1.0
    assert len(payload_obj.what_would_change_view) >= 1
    assert len(payload_obj.key_risks) <= 5

    # 3. 核心计算数值与代码量化派生 100% 绝对一致防编造
    facts, _ = await aggregator.aggregate_facts(
        symbol=symbol,
        use_case=USE_CASE_BUY_DECISION,
        target_price=stock_data.target_price,
    )
    computed = facts["computed"]

    assert payload_obj.price_position.target_vs_price_pct == computed["target_vs_price_pct"]
    assert payload_obj.price_position.pos_in_52w_range == computed["pos_in_52w_range"]

    # 4. 新手可读性与合规防线
    is_readable, suggestions = check_novice_readability(
        envelope.payload, use_case=USE_CASE_BUY_DECISION
    )
    assert is_readable is True
    assert len(suggestions) == 0

    for term in DEFAULT_BANNED_TERMS:
        assert term not in str(envelope.payload)


# =============================================================================
# 3. F6: 技术面分析与交易计划 (technical) 黄金集 5 标的验证
# =============================================================================


@pytest.mark.parametrize("symbol", list_golden_symbols())
async def test_golden_technical_analysis_f6(
    symbol: str,
    golden_research_env: dict[str, Any],
    auth_user: AuthenticatedUser,
) -> None:
    service: ResearchService = golden_research_env["service"]
    aggregator: FactAggregator = golden_research_env["aggregator"]

    req = TechnicalAnalysisRequest(symbol=symbol)
    envelope: ResearchEnvelope = await service.get_technical_analysis(req, user_id=auth_user.id)

    # 1. 通用外壳断言
    assert envelope.schema_version == "1.0"
    assert envelope.use_case == USE_CASE_TECHNICAL
    assert envelope.symbol == symbol
    assert envelope.disclaimer == DEFAULT_DISCLAIMER

    # 2. Schema 严格反序列化校验
    payload_obj = TechnicalPayload.model_validate(envelope.payload)
    assert len(payload_obj.beginner_takeaway) >= 1

    # 3. 交易计划 entry/stop/target/risk_reward 与代码计算 100% 绝对一致防编造
    facts, _ = await aggregator.aggregate_facts(
        symbol=symbol,
        use_case=USE_CASE_TECHNICAL,
    )
    expected_tp = facts["computed"]["trade_plan"]

    assert payload_obj.trade_plan.entry == expected_tp["entry"]
    assert payload_obj.trade_plan.stop == expected_tp["stop"]
    assert payload_obj.trade_plan.target == expected_tp["target"]
    assert payload_obj.trade_plan.risk_reward == expected_tp["risk_reward"]

    # 交易计划数值内在有效性约束
    assert payload_obj.trade_plan.stop < payload_obj.trade_plan.entry
    assert payload_obj.trade_plan.target > payload_obj.trade_plan.entry

    # 4. 新手可读性校验
    is_readable, suggestions = check_novice_readability(
        envelope.payload, use_case=USE_CASE_TECHNICAL
    )
    assert is_readable is True
    assert len(suggestions) == 0

    for term in DEFAULT_BANNED_TERMS:
        assert term not in str(envelope.payload)


# =============================================================================
# 4. F7: 财报解读 (earnings) 黄金集 5 标的验证（含数据缺失合规）
# =============================================================================


@pytest.mark.parametrize("symbol", list_golden_symbols())
async def test_golden_earnings_analysis_f7(
    symbol: str,
    golden_research_env: dict[str, Any],
    auth_user: AuthenticatedUser,
) -> None:
    service: ResearchService = golden_research_env["service"]
    stock_data = get_golden_stock(symbol)

    req = EarningsAnalysisRequest(symbol=symbol)
    envelope: ResearchEnvelope = await service.get_earnings_analysis(req, user_id=auth_user.id)

    # 1. 通用外壳断言
    assert envelope.schema_version == "1.0"
    assert envelope.use_case == USE_CASE_EARNINGS
    assert envelope.symbol == stock_data.symbol
    assert envelope.disclaimer == DEFAULT_DISCLAIMER

    # 2. Schema 校验
    payload_obj = EarningsPayload.model_validate(envelope.payload)
    assert payload_obj.assessment in {"strong", "mixed", "weak"}
    assert len(payload_obj.management_commentary) >= 1

    # 3. 特殊场景：SOFI 指引缺失合规断言
    if symbol == "SOFI":
        assert payload_obj.guidance == MISSING_DATA_PLACEHOLDER
        assert "earnings.guidance" in envelope.data_gaps
    else:
        assert payload_obj.guidance != MISSING_DATA_PLACEHOLDER

    # 4. 可读性与合规防线
    is_readable, suggestions = check_novice_readability(
        envelope.payload, use_case=USE_CASE_EARNINGS
    )
    assert is_readable is True
    assert len(suggestions) == 0

    for term in DEFAULT_BANNED_TERMS:
        assert term not in str(envelope.payload)


# =============================================================================
# 5. REST API 端点全矩阵调用验证 (5 标的 × 4 端点 = 20 请求流)
# =============================================================================


@pytest.mark.parametrize("symbol", list_golden_symbols())
async def test_golden_dataset_rest_api_full_suite(
    symbol: str,
    app: FastAPI,
    client: httpx.AsyncClient,
    golden_research_env: dict[str, Any],
    auth_user: AuthenticatedUser,
) -> None:
    """通过完整 HTTP 请求流执行 5 标的 × 4 端点测试。"""
    service = golden_research_env["service"]
    stock_data = get_golden_stock(symbol)

    async def _mock_current_user(request: Request) -> AuthenticatedUser:
        request.state.user = auth_user
        return auth_user

    app.dependency_overrides[current_user] = _mock_current_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_research_service] = lambda: service

    # 1. POST /api/v1/ai/research
    r_research = await client.post("/api/v1/ai/research", json={"symbol": symbol})
    assert r_research.status_code == 200
    res_json = r_research.json()
    assert res_json["symbol"] == symbol
    assert res_json["use_case"] == "research"
    ResearchPayload.model_validate(res_json["payload"])

    # 2. POST /api/v1/ai/buy-decision
    r_buy = await client.post(
        "/api/v1/ai/buy-decision",
        json={"symbol": symbol, "target_price": str(stock_data.target_price)},
    )
    assert r_buy.status_code == 200
    buy_json = r_buy.json()
    assert buy_json["symbol"] == symbol
    assert buy_json["use_case"] == "buy_decision"
    BuyDecisionPayload.model_validate(buy_json["payload"])

    # 3. POST /api/v1/ai/technical
    r_tech = await client.post("/api/v1/ai/technical", json={"symbol": symbol})
    assert r_tech.status_code == 200
    tech_json = r_tech.json()
    assert tech_json["symbol"] == symbol
    assert tech_json["use_case"] == "technical"
    TechnicalPayload.model_validate(tech_json["payload"])

    # 4. POST /api/v1/ai/earnings
    r_earn = await client.post("/api/v1/ai/earnings", json={"symbol": symbol})
    assert r_earn.status_code == 200
    earn_json = r_earn.json()
    assert earn_json["symbol"] == symbol
    assert earn_json["use_case"] == "earnings"
    EarningsPayload.model_validate(earn_json["payload"])
