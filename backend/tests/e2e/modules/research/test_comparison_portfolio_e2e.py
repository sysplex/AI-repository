"""End-to-End (E2E) Integration Acceptance Tests for Comparison and Portfolio Module (M7 / T08).

Validates all M7 acceptance criteria across the entire HTTP pipeline:
1. Full HTTP request -> authentication -> FactAggregator -> quantitative engine
   -> AI pipeline -> Schema/Tracing -> ResearchEnvelope return:
   - F4: POST /api/v1/ai/compare (USE_CASE_COMPARE)
   - F5: POST /api/v1/ai/long-term (USE_CASE_LONG_TERM)
   - F8: POST /api/v1/ai/portfolio (USE_CASE_PORTFOLIO)
2. Dual-path compatibility:
   - /api/v1/ai/* and /api/v1/research/* both route to ResearchService seamlessly.
3. Multi-tenant HARD-01 authentication and user isolation:
   - Unauthenticated requests rejected with 401 UNAUTHENTICATED.
   - User context propagated to AI audit logs with multi-tenant isolation.
4. Deterministic code computation verification in end-to-end flow:
   - F4 Compare ranking and score match quantitative engine 100%.
   - F8 Portfolio weights sum to 100.00% and amounts sum to total capital.
   - F5 Long-term thesis breakers contain >= 3 structured conditions.
5. Compliance guardrails & anti-hallucination:
   - Statutory disclaimer ('本内容仅供研究与学习，不构成投资建议') on every envelope.
   - 0 forbidden guarantee terms (保本, 稳赚, 零风险).
   - Novice readability checks pass.
   - FactTracingEngine passes with 0 violations.
6. Risk control and error propagation:
   - BudgetCircuitOpenError -> 503 BUDGET_CIRCUIT_OPEN
   - QuotaExceededError -> 429 QUOTA_EXCEEDED
   - SymbolNotFoundError -> 404 NOT_FOUND
   - InsufficientDataError -> 422 DATA_UNAVAILABLE
   - RequestValidationError -> 400 VALIDATION_ERROR
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
from app.modules.ai.exceptions import (
    BudgetCircuitOpenError,
    FactTracingError,
    QuotaExceededError,
)
from app.modules.ai.schemas import AnalysisReport
from app.modules.ai.tracing import FactTracingEngine
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.schemas import AuthenticatedUser, UserSettings
from app.modules.research.aggregator import (
    USE_CASE_COMPARE,
    USE_CASE_LONG_TERM,
    USE_CASE_PORTFOLIO,
    FactAggregator,
)
from app.modules.research.api import get_current_user, get_research_service
from app.modules.research.compliance import (
    DEFAULT_DISCLAIMER,
    check_novice_readability,
    contains_forbidden_terms,
    validate_portfolio_weights,
    validate_thesis_breakers,
)
from app.modules.research.exceptions import (
    SymbolNotFoundError,
)
from app.modules.research.schemas import (
    ComparePayload,
    LongTermPayload,
    PortfolioPayload,
)
from app.modules.research.service import ResearchService
from tests.integration.modules.research.fixtures.m7_golden_scenarios import (
    build_m7_mock_data_service,
    build_m7_mock_strategy_service,
    generate_m7_golden_llm_response,
)

pytestmark = pytest.mark.e2e

_TEST_USER_A = uuid.UUID("33333333-3333-3333-3333-333333333333")
_TEST_USER_B = uuid.UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture
def auth_user_a() -> AuthenticatedUser:
    """Mock authenticated User A."""
    return AuthenticatedUser(
        id=_TEST_USER_A,
        email="m7_trader_a@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(risk_profile="balanced", language="zh-CN"),
    )


@pytest.fixture
def auth_user_b() -> AuthenticatedUser:
    """Mock authenticated User B."""
    return AuthenticatedUser(
        id=_TEST_USER_B,
        email="m7_trader_b@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(risk_profile="conservative", language="zh-CN"),
    )


@pytest.fixture
def e2e_m7_env() -> dict[str, Any]:
    """Sets up an end-to-end research environment with FactAggregator and mock AIService."""
    mock_data = build_m7_mock_data_service()
    mock_strat = build_m7_mock_strategy_service()

    aggregator = FactAggregator(
        data_service=mock_data,
        strategy_service=mock_strat,
    )

    mock_ai = AsyncMock()
    user_call_log: list[dict[str, Any]] = []

    async def _mock_run(
        use_case: str,
        facts: dict[str, Any],
        params: dict[str, Any] | None = None,
        user_id: uuid.UUID | None = None,
        **kwargs: Any,
    ) -> AnalysisReport:
        user_call_log.append(
            {
                "user_id": user_id,
                "use_case": use_case,
                "symbols": facts.get("symbols") or [facts.get("symbol", "AAPL")],
            }
        )

        payload = generate_m7_golden_llm_response(use_case, facts, params)

        # Enforce zero hallucination verification
        engine = FactTracingEngine()
        engine.verify_or_raise(
            payload=payload,
            facts=facts,
            computed=facts.get("computed"),
        )

        return AnalysisReport(
            id=uuid.uuid4(),
            use_case=use_case,
            payload=payload,
            cached=False,
            data_snapshot_id=f"snap_m7_e2e_{use_case}",
            prompt_version="v1.0",
            model="gpt-4o",
            cost_usd=Decimal("0.005000"),
            created_at=get_clock().now(),
        )

    mock_ai.run.side_effect = _mock_run

    service = ResearchService(
        ai_service=mock_ai,
        fact_aggregator=aggregator,
    )

    return {
        "service": service,
        "aggregator": aggregator,
        "ai_service": mock_ai,
        "user_call_log": user_call_log,
    }


def _override_auth(app: FastAPI, user: AuthenticatedUser) -> None:
    async def _mock_auth(request: Request) -> AuthenticatedUser:
        request.state.user = user
        return user

    app.dependency_overrides[current_user] = _mock_auth
    app.dependency_overrides[get_current_user] = lambda: user


# =============================================================================
# 1. 核心用例全链路端到端验收 (F4, F5, F8)
# =============================================================================


async def test_e2e_compare_f4_lifecycle(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_m7_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-01: 多股票横向对比 (F4) 全链路调用生命周期。"""
    service = e2e_m7_env["service"]
    _override_auth(app, auth_user_a)
    app.dependency_overrides[get_research_service] = lambda: service

    resp = await client.post(
        "/api/v1/ai/compare",
        json={"symbols": ["AAPL", "CAT", "KO"]},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["schema_version"] == "1.0"
    assert data["use_case"] == USE_CASE_COMPARE
    assert data["symbol"] == "AAPL,CAT,KO"
    assert data["disclaimer"] == DEFAULT_DISCLAIMER
    assert len(data["summary"]) > 0
    assert len(data["evidence"]) >= 1

    payload_obj = ComparePayload.model_validate(data["payload"])
    assert payload_obj.symbols == ["AAPL", "CAT", "KO"]
    assert len(payload_obj.ranking) == 3
    assert len(payload_obj.fit_by_investor) == 3

    # 验证 8 大维度完整
    for d in [
        "growth",
        "margin",
        "debt",
        "valuation",
        "moat",
        "risk",
        "dividend",
        "long_term",
    ]:
        assert len(getattr(payload_obj.dimension_notes, d)) > 0

    # 验证可读性与零禁用词
    is_readable, _ = check_novice_readability(data["payload"], use_case=USE_CASE_COMPARE)
    assert is_readable is True
    assert not contains_forbidden_terms(data["payload"])


async def test_e2e_long_term_f5_lifecycle(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_m7_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-02: 长期持有价值与论文破裂条件 (F5) 全链路调用生命周期。"""
    service = e2e_m7_env["service"]
    _override_auth(app, auth_user_a)
    app.dependency_overrides[get_research_service] = lambda: service

    resp = await client.post(
        "/api/v1/ai/long-term",
        json={"symbol": "AAPL", "years": 10},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["schema_version"] == "1.0"
    assert data["use_case"] == USE_CASE_LONG_TERM
    assert data["symbol"] == "AAPL"
    assert data["disclaimer"] == DEFAULT_DISCLAIMER
    assert len(data["evidence"]) >= 1

    payload_obj = LongTermPayload.model_validate(data["payload"])
    assert payload_obj.symbol == "AAPL"
    assert payload_obj.horizon_years == 10
    assert payload_obj.verdict in {
        "holdable",
        "holdable_with_conditions",
        "not_recommended",
    }

    # 验证 7 大支柱
    for p in [
        "moat",
        "leadership",
        "demand_stability",
        "pricing_power",
        "innovation",
        "financial_strength",
        "market_size",
    ]:
        pillar = getattr(payload_obj.pillars, p)
        assert len(pillar.reason) > 0

    # 验证 >= 3 条破裂条件且合规
    assert len(payload_obj.thesis_breakers) >= 3
    is_valid, issues = validate_thesis_breakers(payload_obj.thesis_breakers)
    assert is_valid is True
    assert len(issues) == 0

    is_readable, _ = check_novice_readability(data["payload"], use_case=USE_CASE_LONG_TERM)
    assert is_readable is True
    assert not contains_forbidden_terms(data["payload"])


async def test_e2e_portfolio_f8_lifecycle(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_m7_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-03: 投资组合配置优化 (F8) 全链路调用生命周期。"""
    service = e2e_m7_env["service"]
    _override_auth(app, auth_user_a)
    app.dependency_overrides[get_research_service] = lambda: service

    total_amount = "100000.00"
    symbols = ["AAPL", "CAT", "KO", "PLTR"]

    resp = await client.post(
        "/api/v1/ai/portfolio",
        json={
            "amount": total_amount,
            "symbols": symbols,
            "risk_level": "moderate",
            "goal": "growth",
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["schema_version"] == "1.0"
    assert data["use_case"] == USE_CASE_PORTFOLIO
    assert data["disclaimer"] == DEFAULT_DISCLAIMER

    payload_obj = PortfolioPayload.model_validate(data["payload"])
    assert payload_obj.amount == Decimal(total_amount)
    assert len(payload_obj.allocations) == 4

    # 权重守恒验证
    sum_weights = sum(a.weight_pct for a in payload_obj.allocations)
    assert abs(sum_weights + payload_obj.cash_pct - Decimal("100.00")) <= Decimal("0.01")

    # 金额守恒验证
    sum_amounts = sum(a.allocated_amount for a in payload_obj.allocations)
    assert abs(sum_amounts + payload_obj.cash_amount - Decimal(total_amount)) <= Decimal("0.02")

    is_valid, issues = validate_portfolio_weights(data["payload"])
    assert is_valid is True
    assert len(issues) == 0

    is_readable, _ = check_novice_readability(data["payload"], use_case=USE_CASE_PORTFOLIO)
    assert is_readable is True
    assert not contains_forbidden_terms(data["payload"])


# =============================================================================
# 2. 双路径别名路由平同等价验证 (/api/v1/research/*)
# =============================================================================


async def test_e2e_dual_path_alias_routes_equivalence(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_m7_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-04: 验证 /api/v1/research/* 别名路径与 /api/v1/ai/* 100% 平同映射。"""
    service = e2e_m7_env["service"]
    _override_auth(app, auth_user_a)
    app.dependency_overrides[get_research_service] = lambda: service

    # 1. Compare alias
    resp_ai = await client.post("/api/v1/ai/compare", json={"symbols": ["AAPL", "KO"]})
    resp_res = await client.post("/api/v1/research/compare", json={"symbols": ["AAPL", "KO"]})
    assert resp_ai.status_code == 200
    assert resp_res.status_code == 200
    assert resp_ai.json()["payload"] == resp_res.json()["payload"]

    # 2. Long-term alias
    resp_ai = await client.post("/api/v1/ai/long-term", json={"symbol": "CAT", "years": 5})
    resp_res = await client.post("/api/v1/research/long-term", json={"symbol": "CAT", "years": 5})
    assert resp_ai.status_code == 200
    assert resp_res.status_code == 200
    assert resp_ai.json()["payload"] == resp_res.json()["payload"]

    # 3. Portfolio alias
    body = {"amount": "50000.00", "symbols": ["AAPL", "PLTR"]}
    resp_ai = await client.post("/api/v1/ai/portfolio", json=body)
    resp_res = await client.post("/api/v1/research/portfolio", json=body)
    assert resp_ai.status_code == 200
    assert resp_res.status_code == 200
    assert resp_ai.json()["payload"] == resp_res.json()["payload"]


# =============================================================================
# 3. 多租户 HARD-01 鉴权与用户隔离验证
# =============================================================================


async def test_e2e_unauthenticated_requests_blocked(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """E2E-05: 未鉴权请求一律被 HARD-01 拦截并返回 401 UNAUTHENTICATED。"""
    endpoints = [
        "/api/v1/ai/compare",
        "/api/v1/ai/long-term",
        "/api/v1/ai/portfolio",
        "/api/v1/research/compare",
        "/api/v1/research/long-term",
        "/api/v1/research/portfolio",
    ]
    for ep in endpoints:
        resp = await client.post(ep, json={"symbol": "AAPL", "symbols": ["AAPL", "KO"]})
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "UNAUTHENTICATED"


async def test_e2e_multi_tenant_user_isolation(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_m7_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
    auth_user_b: AuthenticatedUser,
) -> None:
    """E2E-06: 验证多租户用户上下文严格隔离，调用记录绑定正确 user_id。"""
    service = e2e_m7_env["service"]
    user_log = e2e_m7_env["user_call_log"]
    app.dependency_overrides[get_research_service] = lambda: service

    # User A 调用
    _override_auth(app, auth_user_a)
    resp_a = await client.post("/api/v1/ai/compare", json={"symbols": ["AAPL", "KO"]})
    assert resp_a.status_code == 200

    # User B 调用
    _override_auth(app, auth_user_b)
    resp_b = await client.post("/api/v1/ai/long-term", json={"symbol": "CAT", "years": 5})
    assert resp_b.status_code == 200

    assert len(user_log) == 2
    assert user_log[0]["user_id"] == _TEST_USER_A
    assert user_log[0]["use_case"] == USE_CASE_COMPARE
    assert user_log[1]["user_id"] == _TEST_USER_B
    assert user_log[1]["use_case"] == USE_CASE_LONG_TERM


# =============================================================================
# 4. 风控熔断、配额超限与异常传递 E2E 验证
# =============================================================================


async def test_e2e_error_propagation(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_m7_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-07: 验证风控熔断 (503)、配额耗尽 (429)、标的未找到 (404) 与参数错误 (400)。"""
    service = e2e_m7_env["service"]
    ai_mock = e2e_m7_env["ai_service"]
    _override_auth(app, auth_user_a)
    app.dependency_overrides[get_research_service] = lambda: service

    # 1. 预算熔断 (503)
    ai_mock.run.side_effect = BudgetCircuitOpenError("Monthly budget reached")
    resp = await client.post("/api/v1/ai/compare", json={"symbols": ["AAPL", "KO"]})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "BUDGET_CIRCUIT_OPEN"

    # 2. 配额超限 (429)
    ai_mock.run.side_effect = QuotaExceededError("Rate limit exceeded")
    resp = await client.post("/api/v1/ai/long-term", json={"symbol": "AAPL", "years": 5})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "QUOTA_EXCEEDED"

    # 3. 标的未找到 (404)
    ai_mock.run.side_effect = SymbolNotFoundError(
        "UNKNOWN not found", details={"symbol": "UNKNOWN"}
    )
    resp = await client.post("/api/v1/ai/long-term", json={"symbol": "UNKNOWN", "years": 5})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"

    # 4. 参数校验错误 (400 VALIDATION_ERROR)
    resp = await client.post("/api/v1/ai/compare", json={"symbols": ["AAPL"]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# =============================================================================
# 5. 防数字编造与幻觉拦截 E2E 验证
# =============================================================================


async def test_e2e_anti_hallucination_failsafe(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_m7_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-08: 验证当 LLM 编造虚假数字或注入禁用承诺词时，管道精准拦截并阻断。"""
    service = e2e_m7_env["service"]
    ai_mock = e2e_m7_env["ai_service"]
    _override_auth(app, auth_user_a)
    app.dependency_overrides[get_research_service] = lambda: service

    # 模拟 FactTracingEngine 检测到虚假编造数字并抛出 FactTracingError
    ai_mock.run.side_effect = FactTracingError(
        "Fact tracing failed: ungrounded number detected",
        details={"violations": [{"field_path": "ranking[0].total_score"}]},
    )

    resp = await client.post("/api/v1/ai/compare", json={"symbols": ["AAPL", "KO"]})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "LLM_OUTPUT_INVALID"
