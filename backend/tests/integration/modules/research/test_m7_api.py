"""M7 REST API 路由与端点集成测试（T06）。

测试覆盖：
1. HARD-01 认证拦截（未授权请求一律返回 401 UNAUTHENTICATED）；
2. 正常鉴权请求执行并返回标准 ResearchEnvelope（200 OK）：
   - POST /api/v1/ai/compare (F4)
   - POST /api/v1/ai/long-term (F5)
   - POST /api/v1/ai/portfolio (F8)
3. 别名路由双向等价验证（/api/v1/research/* 与 /api/v1/ai/* 完全一致）；
4. 请求入参 Schema 校验拦截（400 VALIDATION_ERROR）；
5. 业务异常映射（404, 422, 400, 422）。
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.deps import current_user
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.schemas import AuthenticatedUser, UserSettings
from app.modules.research.api import (
    get_current_user,
    get_research_service,
)
from app.modules.research.exceptions import (
    ComplianceViolationError,
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
        email="m7_trader@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(),
    )


@pytest.fixture
def sample_compare_envelope() -> ResearchEnvelope:
    """Sample compare envelope for F4."""
    return ResearchEnvelope(
        schema_version="1.0",
        use_case="compare",
        symbol="AAPL,MSFT",
        as_of=date(2026, 3, 1),
        summary="横向对比 AAPL 综合得分第一，MSFT 次之。",
        payload={
            "symbols": ["AAPL", "MSFT"],
            "ranking": [
                {
                    "symbol": "AAPL",
                    "rank": 1,
                    "total_score": Decimal("85.50"),
                    "one_line_reason": "核心生态壁垒深厚",
                },
                {
                    "symbol": "MSFT",
                    "rank": 2,
                    "total_score": Decimal("81.20"),
                    "one_line_reason": "云业务稳健增长",
                },
            ],
            "dimension_notes": {
                "growth": "MSFT 领先",
                "margin": "MSFT 领先",
                "debt": "AAPL 表现较优",
                "valuation": "AAPL PE 较低",
                "moat": "两家均为顶级护城河",
                "risk": "行业监管与宏观风险",
                "dividend": "持续回购与分红",
                "long_term": "长期确定性高",
            },
            "fit_by_investor": [
                {
                    "symbol": "AAPL",
                    "suitable_for": ["稳健型"],
                    "not_suitable_for": ["超高弹性投机"],
                },
                {
                    "symbol": "MSFT",
                    "suitable_for": ["成长型"],
                    "not_suitable_for": ["深度价值型"],
                },
            ],
            "summary": "横向对比 AAPL 综合得分第一，MSFT 次之。",
        },
        evidence=[
            EvidenceItem(
                claim="标的 AAPL 综合排名第 1，得分 85.50",
                source_field="facts.computed.ranking",
            ),
            EvidenceItem(
                claim="标的 MSFT 综合排名第 2，得分 81.20",
                source_field="facts.computed.ranking",
            ),
        ],
        data_gaps=[],
        disclaimer="本内容仅供研究与学习，不构成投资建议",
    )


@pytest.fixture
def sample_long_term_envelope() -> ResearchEnvelope:
    """Sample long term envelope for F5."""
    return ResearchEnvelope(
        schema_version="1.0",
        use_case="long_term",
        symbol="AAPL",
        as_of=date(2026, 3, 1),
        summary="苹果公司具备 10 年长期持有价值，生态壁垒极度稳固。",
        payload={
            "symbol": "AAPL",
            "horizon_years": 10,
            "verdict": "holdable",
            "pillars": {
                "moat": {"rating": "strong", "reason": "iOS全球软硬件一体闭环"},
                "leadership": {"rating": "strong", "reason": "资本配置稳健持续回购"},
                "demand_stability": {"rating": "favorable", "reason": "高黏性消费与服务需求"},
                "pricing_power": {"rating": "strong", "reason": "高端硬件与服务溢价能力"},
                "innovation": {"rating": "moderate", "reason": "AI终端整合与自研芯片演进"},
                "financial_strength": {"rating": "strong", "reason": "千亿级充沛自由现金流"},
                "market_size": {"rating": "favorable", "reason": "可穿戴与新兴市场渗透空间"},
            },
            "thesis": "在软硬件飞轮与高毛利服务业务支撑下具备深厚护城河。",
            "thesis_breakers": [
                {
                    "condition": "净利润率连续两个季度低于20%",
                    "metric": "net_margin",
                    "threshold": "< 0.20",
                    "data_field": "fundamentals.net_margin",
                },
                {
                    "condition": "市盈率超过45倍严重透支成长预期",
                    "metric": "pe_trailing",
                    "threshold": "> 45.0",
                    "data_field": "fundamentals.pe_trailing",
                },
                {
                    "condition": "负债权益比恶化超过3.0",
                    "metric": "debt_to_equity",
                    "threshold": "> 3.0",
                    "data_field": "fundamentals.debt_to_equity",
                },
            ],
            "summary": "苹果公司具备 10 年长期持有价值，生态壁垒极度稳固。",
        },
        evidence=[
            EvidenceItem(
                claim="市盈率(TTM) 为 31.2",
                source_field="facts.fundamentals.pe_trailing",
            ),
            EvidenceItem(
                claim="净利率为 0.26",
                source_field="facts.fundamentals.net_margin",
            ),
        ],
        data_gaps=[],
        disclaimer="本内容仅供研究与学习，不构成投资建议",
    )


@pytest.fixture
def sample_portfolio_envelope() -> ResearchEnvelope:
    """Sample portfolio allocation envelope for F8."""
    return ResearchEnvelope(
        schema_version="1.0",
        use_case="portfolio",
        symbol="AAPL,MSFT,GOOG",
        as_of=date(2026, 3, 1),
        summary="均衡配置三大科技巨头并保留10%现金缓冲。",
        payload={
            "amount": Decimal("100000.00"),
            "allocations": [
                {
                    "symbol": "AAPL",
                    "weight_pct": Decimal("40.00"),
                    "allocated_amount": Decimal("40000.00"),
                    "reason": "消费科技底座",
                },
                {
                    "symbol": "MSFT",
                    "weight_pct": Decimal("35.00"),
                    "allocated_amount": Decimal("35000.00"),
                    "reason": "企业级云与AI引擎",
                },
                {
                    "symbol": "GOOG",
                    "weight_pct": Decimal("15.00"),
                    "allocated_amount": Decimal("15000.00"),
                    "reason": "数字广告防守与算力壁垒",
                },
            ],
            "cash_pct": Decimal("10.00"),
            "cash_amount": Decimal("10000.00"),
            "rationale": "均衡配置三大科技巨头并保留10%现金缓冲。",
            "risk_notes": "需关注科技板块宏观周期逆风及反垄断监管变化。",
            "rebalance_suggestion": "建议每半年检视一次，偏离度超 5% 执行再平衡。",
        },
        evidence=[
            EvidenceItem(
                claim="标的 AAPL 建议配置权重 40.00%",
                source_field="facts.computed.allocations",
            ),
            EvidenceItem(
                claim="建议预留现金比例 10.00%",
                source_field="facts.computed.cash_pct",
            ),
        ],
        data_gaps=[],
        disclaimer="本内容仅供研究与学习，不构成投资建议",
    )


@pytest.fixture
def mock_research_service(
    sample_compare_envelope: ResearchEnvelope,
    sample_long_term_envelope: ResearchEnvelope,
    sample_portfolio_envelope: ResearchEnvelope,
) -> AsyncMock:
    """Mock ResearchServiceProtocol for M7 API integration tests."""
    service = AsyncMock(spec=ResearchServiceProtocol)
    service.compare_stocks.return_value = sample_compare_envelope
    service.get_long_term_analysis.return_value = sample_long_term_envelope
    service.generate_portfolio_allocation.return_value = sample_portfolio_envelope
    return service


def _setup_auth_override(
    app: FastAPI,
    auth_user: AuthenticatedUser,
    mock_service: AsyncMock,
) -> None:
    """Wire FastAPI dependency overrides for authenticated requests."""

    async def _mock_current_user(request: Request) -> AuthenticatedUser:
        request.state.user = auth_user
        return auth_user

    app.dependency_overrides[current_user] = _mock_current_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_research_service] = lambda: mock_service


# =============================================================================
# 1. HARD-01 未鉴权保护测试 (Unauthenticated -> 401)
# =============================================================================


class TestM7UnauthenticatedEndpoints:
    """验证未认证时所有 M7 端点均被 401 拦截。"""

    async def test_compare_unauthenticated(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/v1/ai/compare", json={"symbols": ["AAPL", "MSFT"]})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    async def test_long_term_unauthenticated(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/v1/ai/long-term", json={"symbol": "AAPL", "years": 5})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    async def test_portfolio_unauthenticated(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/ai/portfolio",
            json={
                "amount": "100000.00",
                "symbols": ["AAPL", "MSFT"],
                "risk_level": "moderate",
                "goal": "growth",
            },
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    async def test_alias_compare_unauthenticated(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/v1/research/compare", json={"symbols": ["AAPL", "MSFT"]})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    async def test_alias_long_term_unauthenticated(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/v1/research/long-term", json={"symbol": "AAPL", "years": 10})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHENTICATED"

    async def test_alias_portfolio_unauthenticated(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/research/portfolio",
            json={"amount": "50000.00", "symbols": ["AAPL", "MSFT"]},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


# =============================================================================
# 2. 正常鉴权请求与标准信封返回测试 (200 OK)
# =============================================================================


class TestM7AuthenticatedEndpoints:
    """验证认证请求正常调用 Service 并完整返回 ResearchEnvelope。"""

    async def test_compare_stocks_success(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)

        resp = await client.post("/api/v1/ai/compare", json={"symbols": ["AAPL", "MSFT"]})
        assert resp.status_code == 200
        data = resp.json()

        assert data["schema_version"] == "1.0"
        assert data["use_case"] == "compare"
        assert data["symbol"] == "AAPL,MSFT"
        assert len(data["payload"]["ranking"]) == 2
        assert "dimension_notes" in data["payload"]
        assert len(data["evidence"]) >= 2
        assert data["disclaimer"] == "本内容仅供研究与学习，不构成投资建议"

        mock_research_service.compare_stocks.assert_awaited_once()
        call_kwargs = mock_research_service.compare_stocks.await_args.kwargs
        assert call_kwargs["user_id"] == auth_user.id
        assert call_kwargs["request"].symbols == ["AAPL", "MSFT"]

    async def test_get_long_term_analysis_success(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)

        resp = await client.post("/api/v1/ai/long-term", json={"symbol": "AAPL", "years": 10})
        assert resp.status_code == 200
        data = resp.json()

        assert data["use_case"] == "long_term"
        assert data["symbol"] == "AAPL"
        assert data["payload"]["horizon_years"] == 10
        assert data["payload"]["verdict"] == "holdable"
        assert "pillars" in data["payload"]
        assert len(data["payload"]["thesis_breakers"]) >= 3
        assert len(data["evidence"]) >= 1

        mock_research_service.get_long_term_analysis.assert_awaited_once()
        call_kwargs = mock_research_service.get_long_term_analysis.await_args.kwargs
        assert call_kwargs["user_id"] == auth_user.id
        assert call_kwargs["request"].symbol == "AAPL"
        assert call_kwargs["request"].years == 10

    async def test_generate_portfolio_allocation_success(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)

        req_body = {
            "amount": "100000.00",
            "symbols": ["AAPL", "MSFT", "GOOG"],
            "risk_level": "moderate",
            "goal": "growth",
        }
        resp = await client.post("/api/v1/ai/portfolio", json=req_body)
        assert resp.status_code == 200
        data = resp.json()

        assert data["use_case"] == "portfolio"
        assert data["symbol"] == "AAPL,MSFT,GOOG"
        assert Decimal(str(data["payload"]["amount"])) == Decimal("100000.00")
        assert len(data["payload"]["allocations"]) == 3
        assert "cash_pct" in data["payload"]
        assert "rationale" in data["payload"]

        mock_research_service.generate_portfolio_allocation.assert_awaited_once()
        call_kwargs = mock_research_service.generate_portfolio_allocation.await_args.kwargs
        assert call_kwargs["user_id"] == auth_user.id
        assert call_kwargs["request"].amount == Decimal("100000.00")
        assert call_kwargs["request"].symbols == ["AAPL", "MSFT", "GOOG"]
        assert call_kwargs["request"].risk_level == "moderate"
        assert call_kwargs["request"].goal == "growth"


# =============================================================================
# 3. 双路径别名路由等价性测试 (/research/* vs /ai/*)
# =============================================================================


class TestM7AliasRoutesEquivalence:
    """验证 /api/v1/research/* 与 /api/v1/ai/* 双向兼容且返回完全等价。"""

    async def test_alias_compare_stocks_success(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)

        resp = await client.post("/api/v1/research/compare", json={"symbols": ["AAPL", "MSFT"]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["use_case"] == "compare"
        assert data["symbol"] == "AAPL,MSFT"
        mock_research_service.compare_stocks.assert_awaited_once()

    async def test_alias_long_term_analysis_success(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)

        resp = await client.post("/api/v1/research/long-term", json={"symbol": "AAPL", "years": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["use_case"] == "long_term"
        assert data["symbol"] == "AAPL"
        mock_research_service.get_long_term_analysis.assert_awaited_once()

    async def test_alias_portfolio_allocation_success(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)

        resp = await client.post(
            "/api/v1/research/portfolio",
            json={"amount": "50000.00", "symbols": ["AAPL", "MSFT"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["use_case"] == "portfolio"
        mock_research_service.generate_portfolio_allocation.assert_awaited_once()


# =============================================================================
# 4. 请求入参 Schema 校验拦截测试 (422 UNPROCESSABLE_ENTITY)
# =============================================================================


class TestM7RequestValidationErrors:
    """验证非法请求参数被统一验证处理器拦截（HTTP 400 VALIDATION_ERROR）。"""

    async def test_compare_fewer_than_2_symbols(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)
        resp = await client.post("/api/v1/ai/compare", json={"symbols": ["AAPL"]})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_compare_more_than_8_symbols(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)
        resp = await client.post(
            "/api/v1/ai/compare",
            json={"symbols": ["A", "B", "C", "D", "E", "F", "G", "H", "I"]},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_long_term_invalid_years(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)
        resp = await client.post("/api/v1/ai/long-term", json={"symbol": "AAPL", "years": 3})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_long_term_empty_symbol(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)
        resp = await client.post("/api/v1/ai/long-term", json={"symbol": "", "years": 5})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_portfolio_non_positive_amount(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)
        resp = await client.post(
            "/api/v1/ai/portfolio",
            json={"amount": "0.00", "symbols": ["AAPL", "MSFT"]},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_portfolio_fewer_than_2_symbols(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)
        resp = await client.post(
            "/api/v1/ai/portfolio",
            json={"amount": "1000.00", "symbols": ["AAPL"]},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_portfolio_invalid_risk_level(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)
        resp = await client.post(
            "/api/v1/ai/portfolio",
            json={"amount": "1000.00", "symbols": ["AAPL", "MSFT"], "risk_level": "ultra_safe"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_portfolio_invalid_goal(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)
        resp = await client.post(
            "/api/v1/ai/portfolio",
            json={"amount": "1000.00", "symbols": ["AAPL", "MSFT"], "goal": "speculation"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# =============================================================================
# 5. 业务异常状态码映射测试
# =============================================================================


class TestM7BusinessExceptionsMapping:
    """验证领域异常正确映射至标准 HTTP 状态码与 AppError 结构。"""

    async def test_compare_symbol_not_found_mapped_to_404(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)
        mock_research_service.compare_stocks.side_effect = SymbolNotFoundError(
            "标的 'UNKNOWN' 不存在"
        )

        resp = await client.post("/api/v1/ai/compare", json={"symbols": ["AAPL", "UNKNOWN"]})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_long_term_insufficient_data_mapped_to_422(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)
        mock_research_service.get_long_term_analysis.side_effect = InsufficientDataError(
            "历史财报数据不足，无法评估长期价值"
        )

        resp = await client.post("/api/v1/ai/long-term", json={"symbol": "NEWBIE", "years": 5})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "DATA_UNAVAILABLE"

    async def test_portfolio_invalid_parameter_mapped_to_400(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)
        mock_research_service.generate_portfolio_allocation.side_effect = InvalidParameterError(
            "投资组合标的池存在冲突标的"
        )

        resp = await client.post(
            "/api/v1/ai/portfolio",
            json={"amount": "10000.00", "symbols": ["AAPL", "MSFT"]},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_compliance_violation_mapped_to_422(
        self,
        app: FastAPI,
        client: httpx.AsyncClient,
        auth_user: AuthenticatedUser,
        mock_research_service: AsyncMock,
    ) -> None:
        _setup_auth_override(app, auth_user, mock_research_service)
        mock_research_service.generate_portfolio_allocation.side_effect = ComplianceViolationError(
            "投资组合资产配置权重不守恒"
        )

        resp = await client.post(
            "/api/v1/ai/portfolio",
            json={"amount": "10000.00", "symbols": ["AAPL", "MSFT"]},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "LLM_OUTPUT_INVALID"
