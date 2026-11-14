"""Integration tests for Research REST API endpoints (M6 / T06).

Tests:
1. HARD-01 authentication enforcement (unauthenticated -> 401 UNAUTHENTICATED).
2. Authenticated REST endpoints:
   - POST /api/v1/ai/research (F2)
   - POST /api/v1/ai/buy-decision (F3)
   - POST /api/v1/ai/technical (F6)
   - POST /api/v1/ai/earnings (F7)
3. Alias routes compatibility (/api/v1/research/*).
4. Error handling and status mapping:
   - 404 NOT_FOUND (SymbolNotFoundError)
   - 422 DATA_UNAVAILABLE (InsufficientDataError)
   - 400 VALIDATION_ERROR (InvalidParameterError)
   - 429 QUOTA_EXCEEDED (QuotaExceededError)
   - 503 BUDGET_CIRCUIT_OPEN (BudgetCircuitOpenError)
   - 422 RequestValidationError (Pydantic schema constraints)
5. Direct helper function behavior (_extract_user_id, get_current_user, get_research_service).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.deps import current_user
from app.core.errors import Unauthenticated
from app.modules.ai.exceptions import BudgetCircuitOpenError, QuotaExceededError
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.schemas import AuthenticatedUser, UserSettings
from app.modules.research.api import (
    _extract_user_id,
    get_current_user,
    get_research_service,
    set_research_service,
    set_research_service_provider,
)
from app.modules.research.exceptions import (
    InsufficientDataError,
    InvalidParameterError,
    SymbolNotFoundError,
)
from app.modules.research.ports import ResearchServiceProtocol
from app.modules.research.schemas import (
    EvidenceItem,
    ResearchEnvelope,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def auth_user() -> AuthenticatedUser:
    """Mock authenticated user for HARD-01."""
    return AuthenticatedUser(
        id=uuid.uuid4(),
        email="trader@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(),
    )


@pytest.fixture
def sample_research_envelope() -> ResearchEnvelope:
    """Sample research envelope for F2."""
    return ResearchEnvelope(
        schema_version="1.0",
        use_case="research",
        symbol="AAPL",
        as_of=date(2026, 3, 1),
        summary="Apple has strong ecosystem moats and consistent cash flow.",
        payload={
            "business_model": "Hardware, software, and services ecosystem.",
            "revenue_sources": [{"name": "iPhone", "share_pct": "52.00", "note": "Core driver"}],
            "moats": [
                {
                    "type": "ecosystem",
                    "explanation": "High switching costs",
                    "strength": "strong",
                }
            ],
            "risks": [
                {
                    "risk": "Geopolitical",
                    "severity": "medium",
                    "plain_explanation": "Supply chain concentration",
                }
            ],
            "recent_performance": "Steady growth.",
            "debt_and_profit": "Low debt, high margin.",
            "growth_potential": "Services expansion.",
            "scenarios": {
                "bull": "AI supercycle",
                "bear": "Supply disruption",
                "neutral": "Modest growth",
            },
            "beginner_takeaway": ["苹果公司具有强大的生态壁垒与充沛现金流。"],
        },
        evidence=[
            EvidenceItem(claim="最新收盘价为 182.50", source_field="facts.quote.price"),
            EvidenceItem(
                claim="市盈率(TTM) 为 28.5",
                source_field="facts.fundamentals.pe_trailing",
            ),
        ],
        data_gaps=[],
        disclaimer="本内容仅供研究与学习，不构成投资建议",
    )


@pytest.fixture
def sample_buy_decision_envelope() -> ResearchEnvelope:
    """Sample buy decision envelope for F3."""
    return ResearchEnvelope(
        schema_version="1.0",
        use_case="buy_decision",
        symbol="AAPL",
        as_of=date(2026, 3, 1),
        summary="建议分批买入，估值处于合理偏下区间。",
        payload={
            "verdict": "buy",
            "confidence": 0.85,
            "factor_assessment": {
                "valuation": {"rating": "favorable", "reason": "PE低于历史中位数"},
                "earnings_growth": {"rating": "favorable", "reason": "净利润稳步增长"},
                "industry_trend": {"rating": "neutral", "reason": "消费电子处于平稳期"},
                "news": {"rating": "neutral", "reason": "市场情绪平稳"},
                "analyst_view": {"rating": "favorable", "reason": "多数维持买入评级"},
                "downside_risk": {"rating": "favorable", "reason": "现金流充裕下行空间有限"},
            },
            "price_position": {
                "target_vs_price_pct": Decimal("-1.09"),
                "pos_in_52w_range": Decimal("0.65"),
                "valuation_position": "合理区间",
            },
            "better_entry_note": "若回调至 175 美元附近更具安全边际",
            "key_risks": ["反垄断监管审查", "汇率波动影响"],
            "what_would_change_view": ["服务业务营收连续两季下滑"],
        },
        evidence=[
            EvidenceItem(
                claim="想买价偏差率为 -1.09%",
                source_field="facts.computed.target_vs_price_pct",
            ),
        ],
        data_gaps=[],
        disclaimer="本内容仅供研究与学习，不构成投资建议",
    )


@pytest.fixture
def sample_technical_envelope() -> ResearchEnvelope:
    """Sample technical analysis envelope for F6."""
    return ResearchEnvelope(
        schema_version="1.0",
        use_case="technical",
        symbol="AAPL",
        as_of=date(2026, 3, 1),
        summary="均线多头排列，短期趋势偏多。",
        payload={
            "trend": {"value": "bullish", "plain_explanation": "价格运行于主要均线之上"},
            "support_resistance": {
                "value": "178/190",
                "plain_explanation": "下方支撑 178，上方阻力 190",
            },
            "moving_averages": {
                "value": "MA20 > MA50",
                "plain_explanation": "短期均线穿越中长期均线",
            },
            "volume": {"value": "normal", "plain_explanation": "量能温和配合"},
            "rsi": {"value": 55.4, "plain_explanation": "RSI处于中性健康水平，未见超买"},
            "macd": {"value": "golden_cross", "plain_explanation": "MACD快线上穿慢线形成金叉"},
            "breakout": {"value": "none", "plain_explanation": "尚未发生有效区间突破"},
            "trade_plan": {
                "entry": Decimal("182.50"),
                "stop": Decimal("174.44"),
                "target": Decimal("190.00"),
                "risk_reward": Decimal("0.93"),
            },
            "beginner_takeaway": ["短期处于上升通道，可在支撑位附近观察低吸机会。"],
        },
        evidence=[
            EvidenceItem(
                claim="代码量化交易计划：入场位 182.50，止损位 174.44",
                source_field="facts.computed.trade_plan",
            ),
        ],
        data_gaps=[],
        disclaimer="本内容仅供研究与学习，不构成投资建议",
    )


@pytest.fixture
def sample_earnings_envelope() -> ResearchEnvelope:
    """Sample earnings analysis envelope for F7."""
    return ResearchEnvelope(
        schema_version="1.0",
        use_case="earnings",
        symbol="AAPL",
        as_of=date(2026, 3, 1),
        summary="财报全面超预期，服务业务创新高。",
        payload={
            "revenue": {
                "actual": "119.58B",
                "expected": "117.91B",
                "surprise_pct": "1.42%",
                "explanation": "营收超预期 1.42%，主要由服务业务拉动",
            },
            "eps": {
                "actual": "2.18",
                "expected": "2.10",
                "surprise_pct": "3.81%",
                "explanation": "每股收益超预期 3.81%",
            },
            "margins": {
                "actual": "45.9%",
                "expected": "45.2%",
                "surprise_pct": "0.70%",
                "explanation": "毛利率维持历史高位",
            },
            "guidance": "管理层指引下季度营收增速 5%-7%",
            "management_commentary": [
                "iPhone 活跃设备基数突破 22 亿台",
                "AI 布局将深度整合至下一代系统",
            ],
            "market_reaction": "盘后微涨 1.5%",
            "assessment": "strong",
            "short_term_outlook": "短期情绪受到业绩稳健提振",
            "long_term_outlook": "服务业务高毛利驱动长期股东回报",
        },
        evidence=[
            EvidenceItem(claim="最新营收为 119.58B", source_field="facts.earnings.revenue"),
        ],
        data_gaps=[],
        disclaimer="本内容仅供研究与学习，不构成投资建议",
    )


@pytest.fixture
def mock_research_service(
    sample_research_envelope: ResearchEnvelope,
    sample_buy_decision_envelope: ResearchEnvelope,
    sample_technical_envelope: ResearchEnvelope,
    sample_earnings_envelope: ResearchEnvelope,
) -> AsyncMock:
    """Mock ResearchServiceProtocol for API integration tests."""
    service = AsyncMock(spec=ResearchServiceProtocol)
    service.get_stock_research.return_value = sample_research_envelope
    service.get_buy_decision.return_value = sample_buy_decision_envelope
    service.get_technical_analysis.return_value = sample_technical_envelope
    service.get_earnings_analysis.return_value = sample_earnings_envelope
    return service


def _setup_auth_override(
    app: FastAPI,
    auth_user: AuthenticatedUser,
    mock_service: AsyncMock,
) -> None:
    """Helper to wire dependency overrides for authenticated requests."""

    async def _mock_current_user(request: Request) -> AuthenticatedUser:
        request.state.user = auth_user
        return auth_user

    app.dependency_overrides[current_user] = _mock_current_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_research_service] = lambda: mock_service


# =============================================================================
# 1. HARD-01 Authentication Guard Tests (Unauthenticated -> 401)
# =============================================================================


async def test_research_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/ai/research", json={"symbol": "AAPL"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_buy_decision_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/ai/buy-decision",
        json={
            "symbol": "AAPL",
            "target_price": "180.00",
            "horizon": "medium",
            "risk_level": "moderate",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_technical_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/ai/technical", json={"symbol": "AAPL"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_earnings_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/ai/earnings", json={"symbol": "AAPL"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_alias_research_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/research", json={"symbol": "AAPL"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_alias_buy_decision_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/research/buy-decision",
        json={"symbol": "AAPL", "target_price": "180.00"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


# =============================================================================
# 2. Authenticated Endpoints Success Flow (200 OK & Envelope Validation)
# =============================================================================


async def test_get_stock_research_success(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)

    resp = await client.post("/api/v1/ai/research", json={"symbol": "AAPL"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["schema_version"] == "1.0"
    assert data["use_case"] == "research"
    assert data["symbol"] == "AAPL"
    assert "business_model" in data["payload"]
    assert len(data["evidence"]) >= 1
    assert data["disclaimer"] == "本内容仅供研究与学习，不构成投资建议"

    # Verify service was invoked with correct user_id
    mock_research_service.get_stock_research.assert_awaited_once()
    call_kwargs = mock_research_service.get_stock_research.await_args.kwargs
    assert call_kwargs["user_id"] == auth_user.id
    assert call_kwargs["request"].symbol == "AAPL"


async def test_get_buy_decision_success(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)

    req_body = {
        "symbol": "AAPL",
        "target_price": "180.50",
        "horizon": "medium",
        "risk_level": "moderate",
    }
    resp = await client.post("/api/v1/ai/buy-decision", json=req_body)
    assert resp.status_code == 200
    data = resp.json()

    assert data["use_case"] == "buy_decision"
    assert data["symbol"] == "AAPL"
    assert data["payload"]["verdict"] == "buy"
    assert data["payload"]["confidence"] == 0.85
    assert "price_position" in data["payload"]

    mock_research_service.get_buy_decision.assert_awaited_once()
    call_kwargs = mock_research_service.get_buy_decision.await_args.kwargs
    assert call_kwargs["user_id"] == auth_user.id
    assert call_kwargs["request"].symbol == "AAPL"
    assert call_kwargs["request"].target_price == Decimal("180.50")


async def test_get_technical_analysis_success(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)

    resp = await client.post("/api/v1/ai/technical", json={"symbol": "AAPL"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["use_case"] == "technical"
    assert data["symbol"] == "AAPL"
    assert "trade_plan" in data["payload"]
    assert Decimal(str(data["payload"]["trade_plan"]["entry"])) == Decimal("182.50")

    mock_research_service.get_technical_analysis.assert_awaited_once()
    call_kwargs = mock_research_service.get_technical_analysis.await_args.kwargs
    assert call_kwargs["user_id"] == auth_user.id
    assert call_kwargs["request"].symbol == "AAPL"


async def test_get_earnings_analysis_success(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)

    resp = await client.post("/api/v1/ai/earnings", json={"symbol": "AAPL"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["use_case"] == "earnings"
    assert data["symbol"] == "AAPL"
    assert data["payload"]["assessment"] == "strong"
    assert "revenue" in data["payload"]

    mock_research_service.get_earnings_analysis.assert_awaited_once()
    call_kwargs = mock_research_service.get_earnings_analysis.await_args.kwargs
    assert call_kwargs["user_id"] == auth_user.id
    assert call_kwargs["request"].symbol == "AAPL"


# =============================================================================
# 3. Alias Routes Compatibility (/api/v1/research/*)
# =============================================================================


async def test_alias_research_endpoints(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)

    # 1. POST /api/v1/research
    r1 = await client.post("/api/v1/research", json={"symbol": "AAPL"})
    assert r1.status_code == 200
    assert r1.json()["use_case"] == "research"

    # 2. POST /api/v1/research/research
    r2 = await client.post("/api/v1/research/research", json={"symbol": "AAPL"})
    assert r2.status_code == 200
    assert r2.json()["use_case"] == "research"

    # 3. POST /api/v1/research/buy-decision
    r3 = await client.post(
        "/api/v1/research/buy-decision",
        json={"symbol": "AAPL", "target_price": "175.00"},
    )
    assert r3.status_code == 200
    assert r3.json()["use_case"] == "buy_decision"

    # 4. POST /api/v1/research/technical
    r4 = await client.post("/api/v1/research/technical", json={"symbol": "AAPL"})
    assert r4.status_code == 200
    assert r4.json()["use_case"] == "technical"

    # 5. POST /api/v1/research/earnings
    r5 = await client.post("/api/v1/research/earnings", json={"symbol": "AAPL"})
    assert r5.status_code == 200
    assert r5.json()["use_case"] == "earnings"


# =============================================================================
# 4. Error Handling and HTTP Status Code Mapping
# =============================================================================


async def test_symbol_not_found_returns_404(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)
    mock_research_service.get_stock_research.side_effect = SymbolNotFoundError(
        "股票代码 INVALID 不存在"
    )

    resp = await client.post("/api/v1/ai/research", json={"symbol": "INVALID"})
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "INVALID" in body["error"]["message"]


async def test_insufficient_data_returns_422(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)
    mock_research_service.get_technical_analysis.side_effect = InsufficientDataError(
        "K线数量不足，无法计算指标"
    )

    resp = await client.post("/api/v1/ai/technical", json={"symbol": "NEWIPO"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "DATA_UNAVAILABLE"


async def test_invalid_parameter_returns_400(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)
    mock_research_service.get_buy_decision.side_effect = InvalidParameterError(
        "目标价格不能超过现价的 10 倍"
    )

    resp = await client.post(
        "/api/v1/ai/buy-decision",
        json={"symbol": "AAPL", "target_price": "99999.00"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


async def test_quota_exceeded_returns_429(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)
    mock_research_service.get_stock_research.side_effect = QuotaExceededError(
        "今日 AI 分析次数已达上限"
    )

    resp = await client.post("/api/v1/ai/research", json={"symbol": "AAPL"})
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["code"] == "QUOTA_EXCEEDED"


async def test_budget_circuit_open_returns_503(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)
    mock_research_service.get_earnings_analysis.side_effect = BudgetCircuitOpenError(
        "全局 AI 预算熔断已开启"
    )

    resp = await client.post("/api/v1/ai/earnings", json={"symbol": "AAPL"})
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "BUDGET_CIRCUIT_OPEN"


async def test_request_validation_error_negative_price(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)

    resp = await client.post(
        "/api/v1/ai/buy-decision",
        json={"symbol": "AAPL", "target_price": "-10.00"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


async def test_request_validation_error_empty_symbol(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)

    resp = await client.post("/api/v1/ai/research", json={"symbol": ""})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


async def test_request_validation_error_invalid_enum(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_research_service: AsyncMock,
) -> None:
    _setup_auth_override(app, auth_user, mock_research_service)

    resp = await client.post(
        "/api/v1/ai/buy-decision",
        json={"symbol": "AAPL", "target_price": "180.00", "horizon": "forever"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


# =============================================================================
# 5. Direct Unit Tests for Internal Helper Functions
# =============================================================================


def test_extract_user_id_various_types() -> None:
    uid = uuid.uuid4()

    # 1. Object with UUID id
    class UserObj:
        id = uid

    assert _extract_user_id(UserObj()) == uid

    # 2. Dict with str id
    assert _extract_user_id({"id": str(uid)}) == uid

    # 3. Missing id
    with pytest.raises(Unauthenticated, match="无法获取有效的用户会话标识"):
        _extract_user_id({})

    # 4. Invalid UUID format
    with pytest.raises(Unauthenticated, match="无效的用户 ID 格式"):
        _extract_user_id({"id": "not-a-uuid"})


def test_get_current_user_no_state() -> None:
    class MockRequest:
        state = object()

    with pytest.raises(Unauthenticated, match="需要认证才能访问 AI 研究服务"):
        get_current_user(MockRequest())  # type: ignore[arg-type]


def test_get_current_user_with_user(auth_user: AuthenticatedUser) -> None:
    class MockState:
        user = auth_user

    class MockRequest:
        state = MockState()

    assert get_current_user(MockRequest()) is auth_user  # type: ignore[arg-type]


def test_get_research_service_not_configured() -> None:
    set_research_service(None)
    set_research_service_provider(None)

    with pytest.raises(RuntimeError, match="ResearchService has not been configured"):
        get_research_service(session=AsyncMock())


def test_set_research_service_and_provider() -> None:
    mock_s = AsyncMock(spec=ResearchServiceProtocol)
    set_research_service(mock_s)
    assert get_research_service(session=AsyncMock()) is mock_s

    set_research_service(None)

    def sample_provider(session: Any) -> Any:
        return mock_s

    set_research_service_provider(sample_provider)
    assert get_research_service(session=AsyncMock()) is mock_s

    # Cleanup
    set_research_service(None)
    set_research_service_provider(None)
