"""End-to-End (E2E) Integration Acceptance Tests for Research Module (M6 / T08).

Validates all M6 acceptance criteria across the entire pipeline:
1. Full HTTP request -> authentication -> FactAggregator -> quantitative engine
   -> AI pipeline -> Schema/Tracing -> ResearchEnvelope return:
   - F2: POST /api/v1/ai/research (USE_CASE_RESEARCH)
   - F3: POST /api/v1/ai/buy-decision (USE_CASE_BUY_DECISION)
   - F6: POST /api/v1/ai/technical (USE_CASE_TECHNICAL)
   - F7: POST /api/v1/ai/earnings (USE_CASE_EARNINGS)
2. Dual-path compatibility:
   - /api/v1/ai/* and /api/v1/research/* both route to ResearchService seamlessly.
3. Multi-tenant HARD-01 authentication and user isolation:
   - Unauthenticated requests rejected with 401 UNAUTHENTICATED.
   - User context propagated to AI audit logs with multi-tenant isolation.
4. Deterministic code computation verification in end-to-end flow:
   - Technical trade plan (entry, stop, target, risk_reward) matches quantitative engine 100%.
   - Buy decision relative price position (target_vs_price_pct, pos_in_52w_range) matches 100%.
5. Graceful fallback for missing data:
   - Missing guidance normalized to '数据缺失' (MISSING_DATA_PLACEHOLDER).
   - Missing fields recorded in data_gaps.
6. Compliance guardrails:
   - Statutory disclaimer ('本内容仅供研究与学习，不构成投资建议') on every envelope.
   - 0 forbidden guarantee terms (保本, 稳赚, 零风险).
   - Novice readability checks pass.
7. Risk control and error propagation:
   - BudgetCircuitOpenError -> 503 BUDGET_CIRCUIT_OPEN
   - QuotaExceededError -> 429 QUOTA_EXCEEDED
   - SymbolNotFoundError -> 404 NOT_FOUND
   - InsufficientDataError -> 422 DATA_UNAVAILABLE
8. Anti-hallucination failsafe:
   - FactTracingError -> 422 UNPROCESSABLE_ENTITY when ungrounded numbers or banned terms occur.
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
from app.modules.research.exceptions import (
    InsufficientDataError,
    SymbolNotFoundError,
)
from app.modules.research.schemas import (
    BuyDecisionPayload,
    EarningsPayload,
    ResearchPayload,
    TechnicalPayload,
)
from app.modules.research.service import ResearchService
from tests.integration.modules.research.fixtures.golden_stocks import (
    build_mock_data_service,
    build_mock_strategy_service,
    generate_golden_llm_response,
)

pytestmark = pytest.mark.e2e

_TEST_USER_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
_TEST_USER_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def auth_user_a() -> AuthenticatedUser:
    """Mock authenticated User A."""
    return AuthenticatedUser(
        id=_TEST_USER_A,
        email="trader_a@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(risk_profile="balanced", language="zh-CN"),
    )


@pytest.fixture
def auth_user_b() -> AuthenticatedUser:
    """Mock authenticated User B."""
    return AuthenticatedUser(
        id=_TEST_USER_B,
        email="trader_b@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(risk_profile="conservative", language="zh-CN"),
    )


@pytest.fixture
def e2e_research_env() -> dict[str, Any]:
    """Sets up an end-to-end research environment with FactAggregator and mock AIService."""
    mock_data = build_mock_data_service()
    mock_strat = build_mock_strategy_service()

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
        sym = (params or {}).get("symbol") or facts.get("symbol") or "AAPL"
        user_call_log.append(
            {
                "user_id": user_id,
                "use_case": use_case,
                "symbol": sym,
            }
        )

        payload = generate_golden_llm_response(sym, use_case, facts)

        # Enforce zero hallucination verification
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
# 1. 核心用例全链路端到端验收 (F2, F3, F6, F7)
# =============================================================================


async def test_e2e_research_f2_stock_research_lifecycle(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_research_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-01: 股票综合研究 (F2) 全生命周期调用。"""
    service = e2e_research_env["service"]
    _override_auth(app, auth_user_a)
    app.dependency_overrides[get_research_service] = lambda: service

    resp = await client.post("/api/v1/ai/research", json={"symbol": "AAPL"})
    assert resp.status_code == 200
    data = resp.json()

    # 外壳元数据契约
    assert data["schema_version"] == "1.0"
    assert data["use_case"] == USE_CASE_RESEARCH
    assert data["symbol"] == "AAPL"
    assert data["disclaimer"] == DEFAULT_DISCLAIMER
    assert len(data["summary"]) > 0
    assert len(data["evidence"]) >= 1

    # Payload 契约反序列化
    payload = ResearchPayload.model_validate(data["payload"])
    assert len(payload.revenue_sources) >= 1
    assert len(payload.moats) >= 1
    assert len(payload.risks) >= 1
    assert len(payload.beginner_takeaway) >= 1

    # 新手可读性与禁用词检查
    is_readable, suggestions = check_novice_readability(data["payload"], use_case=USE_CASE_RESEARCH)
    assert is_readable is True
    assert len(suggestions) == 0

    for term in DEFAULT_BANNED_TERMS:
        assert term not in str(data["payload"])


async def test_e2e_research_f3_buy_decision_lifecycle(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_research_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-02: 买入决策评估 (F3) 全生命周期调用与确定性计算校验。"""
    service = e2e_research_env["service"]
    aggregator: FactAggregator = e2e_research_env["aggregator"]
    _override_auth(app, auth_user_a)
    app.dependency_overrides[get_research_service] = lambda: service

    req_body = {
        "symbol": "AAPL",
        "target_price": "230.00",
        "horizon": "medium",
        "risk_level": "moderate",
    }
    resp = await client.post("/api/v1/ai/buy-decision", json=req_body)
    assert resp.status_code == 200
    data = resp.json()

    assert data["use_case"] == USE_CASE_BUY_DECISION
    assert data["symbol"] == "AAPL"

    payload = BuyDecisionPayload.model_validate(data["payload"])
    assert payload.verdict in {"buy", "wait", "avoid"}
    assert 0.0 <= payload.confidence <= 1.0
    assert len(payload.what_would_change_view) >= 1

    # 验证代码量化确定性计算 100% 绝对一致防编造
    facts, _ = await aggregator.aggregate_facts(
        symbol="AAPL",
        use_case=USE_CASE_BUY_DECISION,
        target_price=Decimal("230.00"),
    )
    computed = facts["computed"]
    assert payload.price_position.target_vs_price_pct == computed["target_vs_price_pct"]
    assert payload.price_position.pos_in_52w_range == computed["pos_in_52w_range"]

    is_readable, suggestions = check_novice_readability(
        data["payload"], use_case=USE_CASE_BUY_DECISION
    )
    assert is_readable is True
    assert len(suggestions) == 0


async def test_e2e_research_f6_technical_analysis_lifecycle(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_research_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-03: 技术面分析与交易计划 (F6) 全生命周期调用与确定性交易计划校验。"""
    service = e2e_research_env["service"]
    aggregator: FactAggregator = e2e_research_env["aggregator"]
    _override_auth(app, auth_user_a)
    app.dependency_overrides[get_research_service] = lambda: service

    resp = await client.post("/api/v1/ai/technical", json={"symbol": "CAT"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["use_case"] == USE_CASE_TECHNICAL
    assert data["symbol"] == "CAT"

    payload = TechnicalPayload.model_validate(data["payload"])

    # 确定性交易计划防编造
    facts, _ = await aggregator.aggregate_facts(symbol="CAT", use_case=USE_CASE_TECHNICAL)
    expected_plan = facts["computed"]["trade_plan"]
    assert payload.trade_plan.entry == expected_plan["entry"]
    assert payload.trade_plan.stop == expected_plan["stop"]
    assert payload.trade_plan.target == expected_plan["target"]
    assert payload.trade_plan.risk_reward == expected_plan["risk_reward"]

    # 交易计划内在逻辑约束：止损 < 进场 < 目标
    assert payload.trade_plan.stop < payload.trade_plan.entry
    assert payload.trade_plan.target > payload.trade_plan.entry

    is_readable, suggestions = check_novice_readability(
        data["payload"], use_case=USE_CASE_TECHNICAL
    )
    assert is_readable is True
    assert len(suggestions) == 0


async def test_e2e_research_f7_earnings_analysis_with_missing_guidance(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_research_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-04: 财报解读 (F7) 全生命周期调用与 SOFI 指引缺失降级合规。"""
    service = e2e_research_env["service"]
    _override_auth(app, auth_user_a)
    app.dependency_overrides[get_research_service] = lambda: service

    resp = await client.post("/api/v1/ai/earnings", json={"symbol": "SOFI"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["use_case"] == USE_CASE_EARNINGS
    assert data["symbol"] == "SOFI"

    payload = EarningsPayload.model_validate(data["payload"])
    assert payload.assessment in {"strong", "mixed", "weak"}

    # 验证数据缺失降级占位符与缺失字段追踪
    assert payload.guidance == MISSING_DATA_PLACEHOLDER
    assert "earnings.guidance" in data["data_gaps"]

    is_readable, suggestions = check_novice_readability(data["payload"], use_case=USE_CASE_EARNINGS)
    assert is_readable is True
    assert len(suggestions) == 0


# =============================================================================
# 2. 别名路由兼容性验证 (/api/v1/research/*)
# =============================================================================


async def test_e2e_research_alias_routes_parity(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_research_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-05: 验证 /api/v1/research/* 别名路由与 /api/v1/ai/* 端点完全等价。"""
    service = e2e_research_env["service"]
    _override_auth(app, auth_user_a)
    app.dependency_overrides[get_research_service] = lambda: service

    # 1. POST /api/v1/research (根别名)
    r1 = await client.post("/api/v1/research", json={"symbol": "AAPL"})
    assert r1.status_code == 200
    assert r1.json()["use_case"] == USE_CASE_RESEARCH

    # 2. POST /api/v1/research/buy-decision
    r2 = await client.post(
        "/api/v1/research/buy-decision",
        json={"symbol": "AAPL", "target_price": "230.00"},
    )
    assert r2.status_code == 200
    assert r2.json()["use_case"] == USE_CASE_BUY_DECISION

    # 3. POST /api/v1/research/technical
    r3 = await client.post("/api/v1/research/technical", json={"symbol": "AAPL"})
    assert r3.status_code == 200
    assert r3.json()["use_case"] == USE_CASE_TECHNICAL

    # 4. POST /api/v1/research/earnings
    r4 = await client.post("/api/v1/research/earnings", json={"symbol": "AAPL"})
    assert r4.status_code == 200
    assert r4.json()["use_case"] == USE_CASE_EARNINGS


# =============================================================================
# 3. HARD-01 鉴权与多租户隔离验证
# =============================================================================


async def test_e2e_hard01_unauthenticated_requests_rejected(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """E2E-06: 未鉴权请求必须返回 401 UNAUTHENTICATED。"""
    # 清空所有认证 override 模拟未登录请求
    app.dependency_overrides.pop(current_user, None)
    app.dependency_overrides.pop(get_current_user, None)

    endpoints = [
        "/api/v1/ai/research",
        "/api/v1/ai/buy-decision",
        "/api/v1/ai/technical",
        "/api/v1/ai/earnings",
        "/api/v1/research",
        "/api/v1/research/research",
        "/api/v1/research/buy-decision",
        "/api/v1/research/technical",
        "/api/v1/research/earnings",
    ]
    for ep in endpoints:
        resp = await client.post(ep, json={"symbol": "AAPL"})
        assert resp.status_code == 401
        err = resp.json()["error"]
        assert err["code"] == "UNAUTHENTICATED"


async def test_e2e_hard01_multi_tenant_user_isolation(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_research_env: dict[str, Any],
    auth_user_a: AuthenticatedUser,
    auth_user_b: AuthenticatedUser,
) -> None:
    """E2E-07: 验证多租户调用上下文隔离，User A 与 User B 调用独立入账。"""
    service = e2e_research_env["service"]
    user_call_log: list[dict[str, Any]] = e2e_research_env["user_call_log"]
    app.dependency_overrides[get_research_service] = lambda: service

    # 1. User A 发起请求
    _override_auth(app, auth_user_a)
    r_a = await client.post("/api/v1/ai/research", json={"symbol": "AAPL"})
    assert r_a.status_code == 200

    # 2. User B 发起请求
    _override_auth(app, auth_user_b)
    r_b = await client.post("/api/v1/ai/research", json={"symbol": "CAT"})
    assert r_b.status_code == 200

    # 检查调用日志，确认两者的调用完全隔离在各自的 user_id 下
    assert len(user_call_log) >= 2
    assert user_call_log[-2]["user_id"] == _TEST_USER_A
    assert user_call_log[-2]["symbol"] == "AAPL"
    assert user_call_log[-1]["user_id"] == _TEST_USER_B
    assert user_call_log[-1]["symbol"] == "CAT"


# =============================================================================
# 4. 异常处理与风控熔断错误映射
# =============================================================================


async def test_e2e_error_handling_and_circuit_breaker(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-08: 验证风控熔断、配额超限与数据缺失映射到正确的 HTTP 状态码。"""
    _override_auth(app, auth_user_a)
    mock_service = AsyncMock(spec=ResearchService)

    app.dependency_overrides[get_research_service] = lambda: mock_service

    # 1. 预算熔断 -> 503 BUDGET_CIRCUIT_OPEN
    mock_service.get_stock_research.side_effect = BudgetCircuitOpenError(
        "Monthly budget exceeded",
        details={"circuit": "monthly"},
    )
    r_503 = await client.post("/api/v1/ai/research", json={"symbol": "AAPL"})
    assert r_503.status_code == 503
    assert r_503.json()["error"]["code"] == "BUDGET_CIRCUIT_OPEN"

    # 2. 配额超限 -> 429 QUOTA_EXCEEDED
    mock_service.get_stock_research.side_effect = QuotaExceededError(
        "Daily quota exhausted",
        details={"quota": 20},
    )
    r_429 = await client.post("/api/v1/ai/research", json={"symbol": "AAPL"})
    assert r_429.status_code == 429
    assert r_429.json()["error"]["code"] == "QUOTA_EXCEEDED"

    # 3. 股票不存在 -> 404 NOT_FOUND
    mock_service.get_stock_research.side_effect = SymbolNotFoundError(
        "Symbol NOTEXIST not found",
        details={"symbol": "NOTEXIST"},
    )
    r_404 = await client.post("/api/v1/ai/research", json={"symbol": "NOTEXIST"})
    assert r_404.status_code == 404
    assert r_404.json()["error"]["code"] == "NOT_FOUND"

    # 4. 数据不足 -> 422 DATA_UNAVAILABLE
    mock_service.get_stock_research.side_effect = InsufficientDataError(
        "Missing price data",
        details={"symbol": "AAPL"},
    )
    r_422 = await client.post("/api/v1/ai/research", json={"symbol": "AAPL"})
    assert r_422.status_code == 422
    assert r_422.json()["error"]["code"] == "DATA_UNAVAILABLE"


# =============================================================================
# 5. 防编造与合规防线拦截 (Anti-Hallucination Failsafe)
# =============================================================================


async def test_e2e_anti_hallucination_and_compliance_interception(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-09: 验证模型生成虚假数字或非法保证词时被 FactTracing 拦截。"""
    _override_auth(app, auth_user_a)
    mock_service = AsyncMock(spec=ResearchService)
    app.dependency_overrides[get_research_service] = lambda: mock_service

    # 模拟 FactTracingEngine 侦测到编造数值
    mock_service.get_stock_research.side_effect = FactTracingError(
        "Fact tracing check failed: 1 violation detected: $.price untraced_number (999.99)",
        details={"violations": [{"field_path": "$.price", "claimed_value": "999.99"}]},
    )

    resp = await client.post("/api/v1/ai/research", json={"symbol": "AAPL"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "LLM_OUTPUT_INVALID"
    assert "999.99" in str(err)
