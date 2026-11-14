"""M6-T04 核心编排服务 ResearchService 单元测试。

验证：
1. ResearchService 满足 ResearchServiceProtocol；
2. 4 大核心研究用例（research, buy_decision, technical, earnings）端到端编排调用；
3. 空标的代码参数校验；
4. 业务异常（SymbolNotFoundError, AppError 等）正确透传；
5. 未预期的底层错误包装为 ResearchError；
6. ResearchEnvelope 外壳完整性（summary, evidence, data_gaps, disclaimer）；
7. 自定义与默认 evidence 佐证项组装逻辑。
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.errors import AppError, ErrorCode
from app.modules.research.exceptions import (
    InvalidParameterError,
    ResearchError,
    SymbolNotFoundError,
)
from app.modules.research.ports import ResearchServiceProtocol
from app.modules.research.schemas import (
    BuyDecisionRequest,
    EarningsAnalysisRequest,
    EvidenceItem,
    ResearchEnvelope,
    ResearchRequest,
    TechnicalAnalysisRequest,
)
from app.modules.research.service import ResearchService


class DummyAnalysisReport:
    """模拟 AIService.run 返回的 AnalysisReport 对象。"""

    def __init__(
        self,
        payload: dict[str, Any],
        use_case: str,
        created_at: datetime | None = None,
    ) -> None:
        self.id = uuid4()
        self.use_case = use_case
        self.payload = payload
        self.cached = False
        self.data_snapshot_id = "test-hash"
        self.prompt_version = "v1.0"
        self.model = "mock-model"
        self.cost_usd = Decimal("0.001")
        self.created_at = created_at


class CustomTestError(AppError):
    code = ErrorCode.VALIDATION_ERROR
    http_status = 400
    default_message = "自定义业务错误"


@pytest.fixture
def mock_ai_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_fact_aggregator() -> MagicMock:
    aggregator = MagicMock()
    # 默认返回基础事实与缺失字段
    aggregator.aggregate_facts = AsyncMock(
        return_value=(
            {
                "quote": {"symbol": "AAPL", "price": "150.00"},
                "profile": {"name": "Apple Inc."},
                "fundamentals": {"pe_trailing": "30.5", "net_margin": "0.25"},
                "computed": {
                    "pos_in_52w_range": "0.65",
                    "trade_plan": {"entry": "150.00", "stop": "145.00", "target": "165.00"},
                },
            },
            ["fundamentals.dividend_yield"],
        )
    )
    return aggregator


@pytest.fixture
def research_service(
    mock_ai_service: MagicMock,
    mock_fact_aggregator: MagicMock,
) -> ResearchService:
    return ResearchService(
        ai_service=mock_ai_service,
        fact_aggregator=mock_fact_aggregator,
    )


@pytest.mark.unit
class TestResearchServiceProtocolAndValidation:
    """服务协议实现与输入基础校验测试。"""

    def test_implements_protocol(self, research_service: ResearchService) -> None:
        assert isinstance(research_service, ResearchServiceProtocol)

    @pytest.mark.asyncio
    async def test_empty_symbol_in_request_raises_error(
        self, research_service: ResearchService
    ) -> None:
        req = ResearchRequest(symbol="   ")
        user_id = uuid4()

        with pytest.raises(InvalidParameterError) as exc_info:
            await research_service.get_stock_research(req, user_id=user_id)
        assert "Symbol must not be empty" in str(exc_info.value)


@pytest.mark.unit
class TestResearchServiceUseCases:
    """4 大用例编排执行与结果信封测试。"""

    @pytest.mark.asyncio
    async def test_get_stock_research_success(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
        mock_fact_aggregator: MagicMock,
    ) -> None:
        user_id = uuid4()
        payload = {
            "summary": "苹果公司具备强大护城河与稳健现金流。",
            "business_model": "消费电子与高毛利服务生态。",
            "beginner_takeaway": ["优质白马标的，适合长期持有"],
        }
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(
                payload=payload,
                use_case="research",
                created_at=datetime(2026, 1, 15, tzinfo=UTC),
            )
        )

        req = ResearchRequest(symbol="AAPL")
        envelope = await research_service.get_stock_research(req, user_id=user_id)

        assert isinstance(envelope, ResearchEnvelope)
        assert envelope.symbol == "AAPL"
        assert envelope.use_case == "research"
        assert envelope.summary == "苹果公司具备强大护城河与稳健现金流。"
        assert envelope.payload == payload
        assert "fundamentals.dividend_yield" in envelope.data_gaps
        assert envelope.disclaimer == "本内容仅供研究与学习，不构成投资建议"
        assert len(envelope.evidence) > 0

        # 验证透传参数
        mock_fact_aggregator.aggregate_facts.assert_awaited_once_with(
            symbol="AAPL",
            use_case="research",
        )
        mock_ai_service.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_buy_decision_success(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
        mock_fact_aggregator: MagicMock,
    ) -> None:
        user_id = uuid4()
        payload = {
            "verdict": "buy",
            "verdict_reason": "目标买入价合理，基本面支撑充足。",
            "beginner_summary": "建议分批建仓买入。",
        }
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(payload=payload, use_case="buy_decision")
        )

        req = BuyDecisionRequest(
            symbol="AAPL",
            target_price=Decimal("145.00"),
            horizon="medium",
            risk_level="moderate",
        )
        envelope = await research_service.get_buy_decision(req, user_id=user_id)

        assert envelope.use_case == "buy_decision"
        assert envelope.summary == "建议分批建仓买入。"
        assert envelope.payload["verdict"] == "buy"

        # 验证调用事实聚合器时传递了买入参数
        mock_fact_aggregator.aggregate_facts.assert_awaited_once_with(
            symbol="AAPL",
            use_case="buy_decision",
            target_price=Decimal("145.00"),
            horizon="medium",
            risk_level="moderate",
        )

    @pytest.mark.asyncio
    async def test_get_technical_analysis_success(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        user_id = uuid4()
        payload = {
            "short_term_outlook": "短期均线多头排列，量价配合良好。",
            "beginner_takeaway": ["回踩均线为良性蓄势"],
            "trade_plan": {"entry": "150.00", "stop": "145.00", "target": "165.00"},
        }
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(payload=payload, use_case="technical")
        )

        req = TechnicalAnalysisRequest(symbol="AAPL")
        envelope = await research_service.get_technical_analysis(req, user_id=user_id)

        assert envelope.use_case == "technical"
        assert envelope.summary == "短期均线多头排列，量价配合良好。"
        assert "trade_plan" in envelope.payload

    @pytest.mark.asyncio
    async def test_get_earnings_analysis_success(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        user_id = uuid4()
        payload = {
            "assessment": "strong",
            "short_term_outlook": "季报业绩全面超越预期，指引积极。",
        }
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(payload=payload, use_case="earnings")
        )

        req = EarningsAnalysisRequest(symbol="AAPL")
        envelope = await research_service.get_earnings_analysis(req, user_id=user_id)

        assert envelope.use_case == "earnings"
        assert envelope.summary == "季报业绩全面超越预期，指引积极。"


@pytest.mark.unit
class TestResearchServiceEvidenceAndSummary:
    """佐证项与摘要提取逻辑测试。"""

    @pytest.mark.asyncio
    async def test_custom_evidence_in_payload_respected(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        user_id = uuid4()
        custom_evidence = [
            {"claim": "服务收入占比达 25%", "source_field": "facts.fundamentals.net_margin"},
            EvidenceItem(claim=f"PE={30.5}", source_field="facts.fundamentals.pe_trailing"),
        ]
        payload = {
            "summary": "自定义佐证分析测试",
            "evidence": custom_evidence,
        }
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(payload=payload, use_case="research")
        )

        envelope = await research_service.get_stock_research(
            ResearchRequest(symbol="AAPL"), user_id=user_id
        )
        assert len(envelope.evidence) == 2
        assert envelope.evidence[0].claim == "服务收入占比达 25%"
        assert envelope.evidence[0].source_field == "facts.fundamentals.net_margin"
        assert envelope.evidence[1].source_field == "facts.fundamentals.pe_trailing"

    @pytest.mark.asyncio
    async def test_summary_fallback_hierarchy(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        user_id = uuid4()

        # 仅有 verdict_reason
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(
                payload={"verdict_reason": "仅有买入决策原因"},
                use_case="buy_decision",
            )
        )
        env1 = await research_service.get_buy_decision(
            BuyDecisionRequest(symbol="AAPL", target_price=Decimal("150")),
            user_id=user_id,
        )
        assert env1.summary == "仅有买入决策原因"

        # 仅有 beginner_takeaway
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(
                payload={"beginner_takeaway": ["新手要点一", "新手要点二"]},
                use_case="research",
            )
        )
        env2 = await research_service.get_stock_research(
            ResearchRequest(symbol="AAPL"),
            user_id=user_id,
        )
        assert env2.summary == "新手要点一"

    @pytest.mark.asyncio
    async def test_fallback_summary_when_no_summary_fields_present(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        user_id = uuid4()
        payload = {"data": "仅有基础字段"}
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(payload=payload, use_case="research")
        )

        envelope = await research_service.get_stock_research(
            ResearchRequest(symbol="AAPL"), user_id=user_id
        )
        assert envelope.summary == "AAPL research 分析完成"


@pytest.mark.unit
class TestResearchServiceExceptions:
    """管道异常流隔离与重抛测试。"""

    @pytest.mark.asyncio
    async def test_symbol_not_found_from_aggregator_propagates(
        self,
        research_service: ResearchService,
        mock_fact_aggregator: MagicMock,
    ) -> None:
        mock_fact_aggregator.aggregate_facts = AsyncMock(
            side_effect=SymbolNotFoundError("Symbol UNKNOWN not found")
        )
        req = ResearchRequest(symbol="UNKNOWN")

        with pytest.raises(SymbolNotFoundError):
            await research_service.get_stock_research(req, user_id=uuid4())

    @pytest.mark.asyncio
    async def test_app_error_from_ai_service_propagates_unwrapped(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        mock_ai_service.run = AsyncMock(side_effect=CustomTestError("配额已耗尽"))
        req = ResearchRequest(symbol="AAPL")

        with pytest.raises(CustomTestError) as exc_info:
            await research_service.get_stock_research(req, user_id=uuid4())
        assert "配额已耗尽" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unexpected_runtime_exception_wrapped_in_research_error(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        mock_ai_service.run = AsyncMock(side_effect=RuntimeError("GPU cluster connection lost"))
        req = ResearchRequest(symbol="AAPL")

        with pytest.raises(ResearchError) as exc_info:
            await research_service.get_stock_research(req, user_id=uuid4())
        assert "AI analysis execution failed for 'AAPL'" in str(exc_info.value)
