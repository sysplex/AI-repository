"""Unit tests for AI module domain models, Pydantic schemas, and ports (M5-T01).

Validates:
1. ORM model definitions, tablenames, columns, constraints, and indexes.
2. Pydantic schemas validation, constraints, defaults, and immutability.
3. Runtime protocol conformance for LLMClient, PromptRegistryProtocol, QuotaServiceProtocol.
4. Alembic 0005_ai migration metadata and bidirectional reversibility structure.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import ValidationError

from app.modules.ai.models import AIRecommendationOutcome, AIReport
from app.modules.ai.ports import (
    LLMClient,
    PromptRegistryProtocol,
    QuotaServiceProtocol,
)
from app.modules.ai.schemas import (
    AIAnalyzeRequest,
    AIPromptInfo,
    AIRecommendationOutcomeCreate,
    AIRecommendationOutcomeResponse,
    AIReportCreate,
    AIReportResponse,
    AnalysisReport,
    DataSnapshotCreate,
    DataSnapshotResponse,
    FactTracingResult,
    FactTracingViolation,
    LLMMessage,
    LLMResult,
    QuotaStatus,
)

pytestmark = pytest.mark.unit


# =============================================================================
# 1. ORM Model Tests
# =============================================================================


def test_ai_report_foreign_keys_and_table() -> None:
    """Verify AIReport table name, foreign keys, and indexes."""
    assert AIReport.__tablename__ == "ai_reports"
    fks = {fk.target_fullname for fk in AIReport.__table__.foreign_keys}
    assert "users.id" in fks
    assert "data_snapshots.content_hash" in fks


def test_ai_report_model_attributes() -> None:
    """Verify AIReport table name, foreign keys, indexes, and columns."""
    assert AIReport.__tablename__ == "ai_reports"
    cols = {c.name: c for c in AIReport.__table__.columns}
    expected = [
        "id",
        "user_id",
        "use_case",
        "params",
        "cache_key",
        "data_snapshot_id",
        "prompt_version",
        "model",
        "payload",
        "cost_usd",
        "status",
        "error_message",
        "created_at",
    ]
    for col in expected:
        assert col in cols

    # Verify indexes
    table: Any = AIReport.__table__
    index_names = {idx.name for idx in table.indexes}
    assert "ix_ai_reports_user_created" in index_names
    assert "ix_ai_reports_use_case_cache" in index_names


def test_ai_recommendation_outcome_model_attributes() -> None:
    """Verify AIRecommendationOutcome table name and columns."""
    assert AIRecommendationOutcome.__tablename__ == "ai_recommendation_outcomes"
    cols = {c.name: c for c in AIRecommendationOutcome.__table__.columns}
    expected = [
        "id",
        "report_id",
        "symbol",
        "verdict",
        "price_at_report",
        "ret_5d",
        "ret_20d",
        "ret_60d",
        "ret_vs_spy_20d",
        "created_at",
    ]
    for col in expected:
        assert col in cols


# =============================================================================
# 2. Pydantic Schemas Validation Tests
# =============================================================================


def test_llm_message_validation() -> None:
    """Verify LLMMessage accepts valid roles and rejects invalid roles."""
    msg = LLMMessage(role="system", content="Act as financial analyst.")
    assert msg.role == "system"
    assert msg.content == "Act as financial analyst."

    with pytest.raises(ValidationError):
        LLMMessage(role="invalid_role", content="text")


def test_llm_result_validation() -> None:
    """Verify LLMResult fields, defaults, and non-negative token/cost constraints."""
    res = LLMResult(
        parsed_json={"verdict": "buy"},
        raw_text='{"verdict": "buy"}',
        model="claude-3-5-sonnet",
        input_tokens=1500,
        output_tokens=300,
        cost_usd=Decimal("0.009000"),
        latency_ms=1200,
    )
    assert res.input_tokens == 1500
    assert res.output_tokens == 300
    assert res.cost_usd == Decimal("0.009000")
    assert res.latency_ms == 1200

    # Negative tokens should fail
    with pytest.raises(ValidationError):
        LLMResult(
            raw_text="",
            model="test",
            input_tokens=-1,
            output_tokens=0,
            latency_ms=0,
        )


def test_data_snapshot_schemas() -> None:
    """Verify DataSnapshotCreate enforces 64-char hex hash and Response serialization."""
    valid_hash = "a" * 64
    snap = DataSnapshotCreate(
        content_hash=valid_hash,
        facts={"symbol": "AAPL", "pe": 25.5},
        as_of=datetime.now(UTC),
    )
    assert snap.content_hash == valid_hash

    # Invalid hash length
    with pytest.raises(ValidationError):
        DataSnapshotCreate(
            content_hash="short_hash",
            facts={},
            as_of=datetime.now(UTC),
        )

    res = DataSnapshotResponse(
        id=uuid.uuid4(),
        content_hash=valid_hash,
        facts={"symbol": "AAPL", "pe": 25.5},
        as_of=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    assert res.content_hash == valid_hash


def test_ai_report_schemas() -> None:
    """Verify AIReportCreate and AIReportResponse serialization."""
    report_id = uuid.uuid4()
    user_id = uuid.uuid4()
    snap_id = "a" * 64
    now = datetime.now(UTC)

    create_req = AIReportCreate(
        user_id=user_id,
        use_case="stock_research",
        params={"symbol": "AAPL"},
        cache_key="ck-123456",
        data_snapshot_id=snap_id,
        prompt_version="v1.0.0",
        model="gpt-4o",
        payload={"thesis": "Solid compounder"},
        cost_usd=Decimal("0.005000"),
        status="success",
    )
    assert create_req.use_case == "stock_research"
    assert create_req.status == "success"

    resp = AIReportResponse(
        id=report_id,
        user_id=user_id,
        use_case="stock_research",
        params={"symbol": "AAPL"},
        cache_key="ck-123456",
        data_snapshot_id=snap_id,
        prompt_version="v1.0.0",
        model="gpt-4o",
        payload={"thesis": "Solid compounder"},
        cost_usd=Decimal("0.005000"),
        status="success",
        error_message=None,
        created_at=now,
    )
    assert resp.id == report_id
    assert resp.payload["thesis"] == "Solid compounder"


def test_ai_recommendation_outcome_schemas() -> None:
    """Verify AIRecommendationOutcomeCreate and OutcomeResponse."""
    rep_id = uuid.uuid4()
    create_dto = AIRecommendationOutcomeCreate(
        report_id=rep_id,
        symbol="MSFT",
        verdict="buy",
        price_at_report=Decimal("420.5000"),
        ret_5d=Decimal("2.5000"),
    )
    assert create_dto.symbol == "MSFT"
    assert create_dto.price_at_report == Decimal("420.5000")

    # price_at_report must be > 0
    with pytest.raises(ValidationError):
        AIRecommendationOutcomeCreate(
            report_id=rep_id,
            symbol="MSFT",
            verdict="buy",
            price_at_report=Decimal("0.0000"),
        )

    resp_dto = AIRecommendationOutcomeResponse(
        id=uuid.uuid4(),
        report_id=rep_id,
        symbol="MSFT",
        verdict="buy",
        price_at_report=Decimal("420.5000"),
        ret_5d=Decimal("2.5000"),
        ret_20d=None,
        ret_60d=None,
        ret_vs_spy_20d=None,
        created_at=datetime.now(UTC),
    )
    assert resp_dto.symbol == "MSFT"


def test_analysis_report_schema() -> None:
    """Verify AnalysisReport wrapper structure and immutability."""
    report = AnalysisReport(
        id=uuid.uuid4(),
        use_case="buy_decision",
        payload={"verdict": "wait", "reason": "PE stretched"},
        cached=True,
        data_snapshot_id="b" * 64,
        prompt_version="v1.0",
        model="claude-3-5-sonnet",
        cost_usd=Decimal("0.000000"),
        created_at=datetime.now(UTC),
    )
    assert report.cached is True
    assert report.cost_usd == Decimal("0.000000")

    with pytest.raises(ValidationError):
        report.cached = False  # type: ignore[misc] # Frozen


def test_quota_status_schema() -> None:
    """Verify QuotaStatus fields and values."""
    qs = QuotaStatus(
        user_id=uuid.uuid4(),
        usage_date=date(2026, 3, 1),
        calls_today=5,
        daily_quota=20,
        remaining_calls=15,
        is_exceeded=False,
    )
    assert qs.remaining_calls == 15
    assert qs.is_exceeded is False


def test_fact_tracing_schemas() -> None:
    """Verify FactTracingViolation and FactTracingResult."""
    violation = FactTracingViolation(
        field_path="financials.revenue_growth",
        claimed_value=Decimal("45.2"),
        reason="untraced_number",
    )
    res = FactTracingResult(
        valid=False,
        violations=[violation],
        checked_numbers_count=12,
    )
    assert res.valid is False
    assert len(res.violations) == 1
    assert res.violations[0].claimed_value == Decimal("45.2")


def test_ai_analyze_and_prompt_info_schemas() -> None:
    """Verify AIAnalyzeRequest and AIPromptInfo."""
    req = AIAnalyzeRequest(
        use_case="technical_analysis",
        facts={"symbol": "NVDA", "sma_50": 120.5},
        params={"risk_level": "moderate"},
    )
    assert req.use_case == "technical_analysis"

    info = AIPromptInfo(
        use_case="technical_analysis",
        version="v1.0.0",
        description="Technical chart analysis prompt",
    )
    assert info.version == "v1.0.0"


# =============================================================================
# 3. Protocol Conformance Tests
# =============================================================================


def test_llm_client_protocol_conformance() -> None:
    """Verify a concrete mock class satisfies LLMClient protocol."""

    class ConcreteLLMClient:
        name: str = "mock-client"

        async def generate(
            self,
            *,
            system: str,
            user: str,
            output_schema: dict[str, Any] | None = None,
            max_tokens: int = 2048,
            temperature: float = 0.2,
        ) -> LLMResult:
            return LLMResult(
                raw_text="mock",
                model="mock",
                input_tokens=10,
                output_tokens=10,
                latency_ms=50,
            )

    client = ConcreteLLMClient()
    assert isinstance(client, LLMClient)


def test_prompt_registry_protocol_conformance() -> None:
    """Verify a concrete mock class satisfies PromptRegistryProtocol."""

    class ConcreteRegistry:
        def get(self, use_case: str, version: str | None = None) -> Any:
            return {"use_case": use_case, "version": version or "v1"}

    reg = ConcreteRegistry()
    assert isinstance(reg, PromptRegistryProtocol)


def test_quota_service_protocol_conformance() -> None:
    """Verify a concrete mock class satisfies QuotaServiceProtocol."""

    class ConcreteQuotaService:
        async def check(self, user_id: uuid.UUID) -> QuotaStatus:
            return QuotaStatus(
                user_id=user_id,
                usage_date=date.today(),
                calls_today=0,
                daily_quota=20,
                remaining_calls=20,
                is_exceeded=False,
            )

        async def consume(
            self,
            user_id: uuid.UUID,
            tokens_in: int,
            tokens_out: int,
            cost_usd: Decimal,
        ) -> None:
            pass

    qs = ConcreteQuotaService()
    assert isinstance(qs, QuotaServiceProtocol)


# =============================================================================
# 4. Alembic Migration Structure Tests
# =============================================================================


def test_alembic_0005_ai_migration_metadata() -> None:
    """Verify 0005_ai revision ID, down_revision, and functions."""
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    rev = script.get_revision("0005_ai")
    assert rev is not None
    assert rev.revision == "0005_ai"
    assert rev.down_revision == "0004_simbroker"
    module = rev.module
    assert hasattr(module, "upgrade")
    assert callable(module.upgrade)
    assert hasattr(module, "downgrade")
    assert callable(module.downgrade)
    tables = getattr(module, "_TABLES", ())
    assert "ai_reports" in tables
    assert "ai_recommendation_outcomes" in tables
    assert len(tables) == 2
