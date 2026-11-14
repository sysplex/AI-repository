"""Integration tests for AI REST API endpoints (M5 / T07).

Tests:
1. HARD-01 authentication enforcement (unauthenticated -> 401 UNAUTHENTICATED).
2. Authenticated REST endpoints (analyze, reports, facts, quota, prompts).
3. Cache hit vs cache miss execution.
4. Multi-tenant isolation (404 NOT_FOUND for cross-tenant access).
5. Error handling and status mapping (429 QUOTA_EXCEEDED, 503 BUDGET_CIRCUIT_OPEN, etc.).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.deps import current_user
from app.core.errors import NotFound
from app.modules.ai.api import get_ai_service, get_current_user
from app.modules.ai.exceptions import (
    BudgetCircuitOpenError,
    FactTracingError,
    PromptNotFoundError,
    QuotaExceededError,
    SchemaValidationError,
)
from app.modules.ai.schemas import (
    AIPromptInfo,
    AIReportResponse,
    AnalysisReport,
    QuotaStatus,
)
from app.modules.ai.service import AIService
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.schemas import AuthenticatedUser, UserSettings

pytestmark = pytest.mark.integration


@pytest.fixture
def auth_user() -> AuthenticatedUser:
    """Mock authenticated user for HARD-01."""
    return AuthenticatedUser(
        id=uuid.uuid4(),
        email="ai_trader@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(),
    )


@pytest.fixture
def mock_ai_service() -> AsyncMock:
    """Mock AIService for API endpoint integration tests."""
    service = AsyncMock(spec=AIService)

    report_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

    sample_analysis_report = AnalysisReport(
        id=report_id,
        use_case="stock_analysis",
        payload={
            "symbol": "AAPL",
            "verdict": "buy",
            "confidence": "high",
            "summary": "Strong momentum",
        },
        cached=False,
        data_snapshot_id="snapshot_hash_12345",
        prompt_version="v1",
        model="gpt-4o",
        cost_usd=Decimal("0.005200"),
        created_at=now,
    )
    service.run.return_value = sample_analysis_report

    sample_report_resp = AIReportResponse(
        id=report_id,
        user_id=user_id,
        use_case="stock_analysis",
        params={"risk": "moderate"},
        cache_key="cache_key_hash_abc",
        data_snapshot_id="snapshot_hash_12345",
        prompt_version="v1",
        model="gpt-4o",
        payload={
            "symbol": "AAPL",
            "verdict": "buy",
            "confidence": "high",
            "summary": "Strong momentum",
        },
        cost_usd=Decimal("0.005200"),
        status="success",
        error_message=None,
        created_at=now,
    )
    service.get_report.return_value = sample_report_resp
    service.list_reports.return_value = [sample_report_resp]

    sample_snapshot_dict: dict[str, Any] = {
        "content_hash": "snapshot_hash_12345",
        "symbol": "AAPL",
        "scope": ["price", "pe"],
        "facts": {"symbol": "AAPL", "price": 182.5, "pe": 28.5},
        "missing_fields": [],
        "as_of": now,
        "created_at": now,
    }
    service.get_snapshot.return_value = sample_snapshot_dict

    sample_quota = QuotaStatus(
        user_id=user_id,
        usage_date=date(2026, 3, 1),
        calls_today=3,
        daily_quota=20,
        remaining_calls=17,
        is_exceeded=False,
    )
    service.get_quota_status.return_value = sample_quota

    sample_prompts = [
        AIPromptInfo(
            use_case="stock_analysis",
            version="v1",
            description="Stock fundamental analysis",
            is_active=True,
            output_schema={"type": "object"},
        )
    ]
    service.list_prompts.return_value = sample_prompts

    return service


def _setup_auth_override(
    app: FastAPI,
    auth_user: AuthenticatedUser,
    mock_ai_service: AsyncMock,
) -> None:
    """Helper to wire dependency overrides for authenticated requests."""

    async def _mock_current_user(request: Request) -> AuthenticatedUser:
        request.state.user = auth_user
        return auth_user

    app.dependency_overrides[current_user] = _mock_current_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service


# =============================================================================
# 1. HARD-01 Authentication Guard Tests (Unauthenticated -> 401)
# =============================================================================


async def test_analyze_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/ai/analyze",
        json={"use_case": "stock_analysis", "facts": {"symbol": "AAPL"}},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_list_reports_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/ai/reports")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_get_report_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/ai/reports/{uuid.uuid4()}")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_get_report_facts_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/ai/reports/{uuid.uuid4()}/facts")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_get_quota_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/ai/quota")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_list_prompts_unauthenticated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/ai/prompts")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


# =============================================================================
# 2. Authenticated Endpoints Tests (200 OK)
# =============================================================================


async def test_analyze_authenticated_cache_miss(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_ai_service)

    req_body = {
        "use_case": "stock_analysis",
        "facts": {"symbol": "AAPL", "price": 182.5},
        "params": {"risk": "moderate"},
        "prompt_version": "v1",
    }
    resp = await client.post("/api/v1/ai/analyze", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["use_case"] == "stock_analysis"
    assert data["cached"] is False
    assert data["model"] == "gpt-4o"
    assert data["cost_usd"] == "0.005200"
    assert data["payload"]["verdict"] == "buy"

    mock_ai_service.run.assert_called_once_with(
        use_case="stock_analysis",
        facts={"symbol": "AAPL", "price": 182.5},
        params={"risk": "moderate"},
        user_id=auth_user.id,
        prompt_version="v1",
    )


async def test_analyze_authenticated_cache_hit(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_ai_service)

    cached_report = AnalysisReport(
        id=uuid.uuid4(),
        use_case="stock_analysis",
        payload={"verdict": "hold", "confidence": "high"},
        cached=True,
        data_snapshot_id="snap_123",
        prompt_version="v1",
        model="gpt-4o",
        cost_usd=Decimal("0.000000"),
        created_at=datetime.now(UTC),
    )
    mock_ai_service.run.return_value = cached_report

    resp = await client.post(
        "/api/v1/ai/analyze",
        json={"use_case": "stock_analysis", "facts": {"symbol": "AAPL"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cached"] is True
    assert data["cost_usd"] == "0.000000"
    assert data["payload"]["verdict"] == "hold"


async def test_list_reports_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_ai_service)

    resp = await client.get("/api/v1/ai/reports?use_case=stock_analysis&limit=10&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["use_case"] == "stock_analysis"

    mock_ai_service.list_reports.assert_called_once_with(
        user_id=auth_user.id,
        use_case="stock_analysis",
        limit=10,
        offset=0,
    )


async def test_get_report_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_ai_service)
    target_id = uuid.uuid4()

    resp = await client.get(f"/api/v1/ai/reports/{target_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["use_case"] == "stock_analysis"
    assert data["status"] == "success"

    mock_ai_service.get_report.assert_called_once_with(target_id, user_id=auth_user.id)


async def test_get_report_facts_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_ai_service)
    target_id = uuid.uuid4()

    resp = await client.get(f"/api/v1/ai/reports/{target_id}/facts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["content_hash"] == "snapshot_hash_12345"
    assert data["symbol"] == "AAPL"
    assert data["facts"]["price"] == 182.5

    mock_ai_service.get_report.assert_called_once_with(target_id, user_id=auth_user.id)
    mock_ai_service.get_snapshot.assert_called_once_with("snapshot_hash_12345")


async def test_get_quota_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_ai_service)

    resp = await client.get("/api/v1/ai/quota")
    assert resp.status_code == 200
    data = resp.json()
    assert data["calls_today"] == 3
    assert data["daily_quota"] == 20
    assert data["remaining_calls"] == 17
    assert data["is_exceeded"] is False

    mock_ai_service.get_quota_status.assert_called_once_with(auth_user.id)


async def test_list_prompts_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    _setup_auth_override(app, auth_user, mock_ai_service)

    resp = await client.get("/api/v1/ai/prompts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["use_case"] == "stock_analysis"
    assert data[0]["version"] == "v1"

    mock_ai_service.list_prompts.assert_called_once()


# =============================================================================
# 3. Multi-Tenant Isolation Tests (404 NOT_FOUND)
# =============================================================================


async def test_get_report_tenant_isolation_raises_404(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    """访问其他租户的报告返回 404 NOT_FOUND。"""
    _setup_auth_override(app, auth_user, mock_ai_service)
    mock_ai_service.get_report.side_effect = NotFound("AI report not found")

    target_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/ai/reports/{target_id}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_get_report_facts_tenant_isolation_raises_404(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    """获取不存在或非本租户报告的事实快照返回 404 NOT_FOUND。"""
    _setup_auth_override(app, auth_user, mock_ai_service)
    mock_ai_service.get_report.side_effect = NotFound("AI report not found")

    target_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/ai/reports/{target_id}/facts")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# =============================================================================
# 4. Error Handling and Status Mapping Tests
# =============================================================================


async def test_analyze_quota_exceeded_returns_429(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    """配额耗尽返回 429 QUOTA_EXCEEDED。"""
    _setup_auth_override(app, auth_user, mock_ai_service)
    mock_ai_service.run.side_effect = QuotaExceededError("Daily AI call quota exhausted")

    resp = await client.post(
        "/api/v1/ai/analyze",
        json={"use_case": "stock_analysis", "facts": {"symbol": "AAPL"}},
    )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "QUOTA_EXCEEDED"


async def test_analyze_budget_circuit_open_returns_503(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    """预算熔断返回 503 BUDGET_CIRCUIT_OPEN。"""
    _setup_auth_override(app, auth_user, mock_ai_service)
    mock_ai_service.run.side_effect = BudgetCircuitOpenError("Circuit breaker tripped")

    resp = await client.post(
        "/api/v1/ai/analyze",
        json={"use_case": "stock_analysis", "facts": {"symbol": "AAPL"}},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "BUDGET_CIRCUIT_OPEN"


async def test_analyze_schema_validation_error_returns_422(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    """Schema 校验失败返回 422 LLM_OUTPUT_INVALID。"""
    _setup_auth_override(app, auth_user, mock_ai_service)
    mock_ai_service.run.side_effect = SchemaValidationError("Output failed schema validation")

    resp = await client.post(
        "/api/v1/ai/analyze",
        json={"use_case": "stock_analysis", "facts": {"symbol": "AAPL"}},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "LLM_OUTPUT_INVALID"


async def test_analyze_fact_tracing_error_returns_422(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    """防编造校验发现幻觉数字返回 422 LLM_OUTPUT_INVALID。"""
    _setup_auth_override(app, auth_user, mock_ai_service)
    mock_ai_service.run.side_effect = FactTracingError("Untraced hallucinated numbers detected")

    resp = await client.post(
        "/api/v1/ai/analyze",
        json={"use_case": "stock_analysis", "facts": {"symbol": "AAPL"}},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "LLM_OUTPUT_INVALID"


async def test_analyze_prompt_not_found_returns_404(
    app: FastAPI,
    client: httpx.AsyncClient,
    mock_ai_service: AsyncMock,
    auth_user: AuthenticatedUser,
) -> None:
    """无效的用例或提示词模板返回 404 NOT_FOUND。"""
    _setup_auth_override(app, auth_user, mock_ai_service)
    mock_ai_service.run.side_effect = PromptNotFoundError("Prompt template unknown_case not found")

    resp = await client.post(
        "/api/v1/ai/analyze",
        json={"use_case": "unknown_case", "facts": {"symbol": "AAPL"}},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
