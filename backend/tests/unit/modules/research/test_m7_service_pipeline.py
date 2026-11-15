"""M7-T04 核心编排服务 ResearchService M7 用例扩展单元测试。

验证：
1. ResearchService 满足 ResearchServiceProtocol；
2. M7 核心用例（compare, long_term, portfolio）端到端编排调用；
3. 参数校验（标的池数量越界、空标的、重复标的去重、投资金额非正等）；
4. 业务异常（SymbolNotFoundError, AppError 等）正确透传；
5. 未预期的底层错误包装为 ResearchError；
6. ResearchEnvelope 外壳完整性（summary, evidence, data_gaps, disclaimer）；
7. 派生数字与量化结果（ranking, allocations, cash_pct）作为 evidence 的提取逻辑。
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
    CompareRequest,
    EvidenceItem,
    LongTermRequest,
    PortfolioRequest,
    ResearchEnvelope,
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
        self.data_snapshot_id = "test-hash-m7"
        self.prompt_version = "v1.0"
        self.model = "mock-model"
        self.cost_usd = Decimal("0.002")
        self.created_at = created_at


class CustomM7AppError(AppError):
    code = ErrorCode.VALIDATION_ERROR
    http_status = 400
    default_message = "M7 自定义业务异常"


@pytest.fixture
def mock_ai_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_fact_aggregator() -> MagicMock:
    aggregator = MagicMock()
    # 默认单标的事实返回
    aggregator.aggregate_facts = AsyncMock(
        return_value=(
            {
                "quote": {"symbol": "AAPL", "price": "185.00"},
                "profile": {"name": "Apple Inc."},
                "fundamentals": {
                    "pe_trailing": "31.2",
                    "net_margin": "0.26",
                    "debt_to_equity": "1.8",
                },
                "computed": {},
            },
            ["fundamentals.revenue_growth"],
        )
    )
    # 默认多标的事实返回
    aggregator.aggregate_multi_facts = AsyncMock(
        return_value=(
            {
                "symbols": ["AAPL", "MSFT"],
                "use_case": "compare",
                "stocks": {
                    "AAPL": {
                        "quote": {"price": "185.00"},
                        "fundamentals": {"pe_trailing": "31.2", "net_margin": "0.26"},
                    },
                    "MSFT": {
                        "quote": {"price": "420.00"},
                        "fundamentals": {"pe_trailing": "35.0", "net_margin": "0.35"},
                    },
                },
                "computed": {
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
                            "one_line_reason": "云与AI高增长驱动",
                        },
                    ],
                },
            },
            ["MSFT.fundamentals.dividend_yield"],
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
class TestM7ServiceProtocol:
    """协议实现验证。"""

    def test_implements_protocol(self, research_service: ResearchService) -> None:
        assert isinstance(research_service, ResearchServiceProtocol)


@pytest.mark.unit
class TestCompareStocksPipeline:
    """F4 多股票横向对比分析管道测试。"""

    @pytest.mark.asyncio
    async def test_compare_stocks_success(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
        mock_fact_aggregator: MagicMock,
    ) -> None:
        user_id = uuid4()
        payload = {
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
                    "one_line_reason": "云与AI高增长驱动",
                },
            ],
            "dimension_notes": {
                "growth": "MSFT 领先",
                "margin": "MSFT 领先",
                "debt": "AAPL 表现较好",
                "valuation": "AAPL PE 略低于 MSFT",
                "moat": "两家均具备顶级护城河",
                "risk": "反垄断与宏观下行",
                "dividend": "均具备稳定分红与回购",
                "long_term": "确定性均极高",
            },
            "fit_by_investor": [
                {
                    "symbol": "AAPL",
                    "suitable_for": ["稳健白马型"],
                    "not_suitable_for": ["超高弹性投机"],
                },
                {
                    "symbol": "MSFT",
                    "suitable_for": ["科技成长型"],
                    "not_suitable_for": ["深度价值型"],
                },
            ],
            "summary": "综合对比 AAPL 综合得分第一，MSFT 次之，均具备高确定性。",
        }
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(
                payload=payload,
                use_case="compare",
                created_at=datetime(2026, 2, 20, 10, 0, tzinfo=UTC),
            )
        )

        req = CompareRequest(symbols=["AAPL", "MSFT"])
        envelope = await research_service.compare_stocks(req, user_id=user_id)

        assert isinstance(envelope, ResearchEnvelope)
        assert envelope.use_case == "compare"
        assert envelope.symbol == "AAPL,MSFT"
        assert envelope.as_of == datetime(2026, 2, 20).date()
        assert envelope.summary == "综合对比 AAPL 综合得分第一，MSFT 次之，均具备高确定性。"
        assert envelope.payload == payload
        assert "MSFT.fundamentals.dividend_yield" in envelope.data_gaps
        assert envelope.disclaimer == "本内容仅供研究与学习，不构成投资建议"

        # 检查佐证项已包含排名
        assert len(envelope.evidence) >= 2
        claim_texts = [e.claim for e in envelope.evidence]
        assert any("AAPL" in c and "第 1" in c for c in claim_texts)

        # 验证透传参数
        mock_fact_aggregator.aggregate_multi_facts.assert_awaited_once_with(
            symbols=["AAPL", "MSFT"],
            use_case="compare",
        )
        mock_ai_service.run.assert_awaited_once_with(
            use_case="compare",
            facts=mock_fact_aggregator.aggregate_multi_facts.return_value[0],
            params={"symbols": ["AAPL", "MSFT"]},
            user_id=user_id,
        )

    @pytest.mark.asyncio
    async def test_compare_stocks_whitespace_and_deduplication(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
        mock_fact_aggregator: MagicMock,
    ) -> None:
        user_id = uuid4()
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(
                payload={"summary": "两标的对比完成"},
                use_case="compare",
            )
        )

        # 包含空白字符和大小写重复：["  aapl  ", "AAPL", "msft  "] -> ["AAPL", "MSFT"]
        req = CompareRequest(symbols=["  aapl  ", "AAPL", "msft  "])
        envelope = await research_service.compare_stocks(req, user_id=user_id)

        assert envelope.symbol == "AAPL,MSFT"
        mock_fact_aggregator.aggregate_multi_facts.assert_awaited_once_with(
            symbols=["AAPL", "MSFT"],
            use_case="compare",
        )

    @pytest.mark.asyncio
    async def test_compare_stocks_validation_errors(
        self,
        research_service: ResearchService,
    ) -> None:
        user_id = uuid4()

        # 去重后只有 1 个有效标的
        req_single = CompareRequest(symbols=["AAPL", "AAPL"])
        with pytest.raises(InvalidParameterError) as exc_single:
            await research_service.compare_stocks(req_single, user_id=user_id)
        assert "Compare use case requires 2 to 8 unique valid symbols" in str(exc_single.value)

        # 全为空白字符
        req_blank = CompareRequest.model_construct(symbols=["   ", "  "])
        with pytest.raises(InvalidParameterError) as exc_blank:
            await research_service.compare_stocks(req_blank, user_id=user_id)
        assert "Compare use case requires 2 to 8 unique valid symbols" in str(exc_blank.value)

        # 超过 8 个标的
        req_too_many = CompareRequest.model_construct(
            symbols=["A", "B", "C", "D", "E", "F", "G", "H", "I"]
        )
        with pytest.raises(InvalidParameterError) as exc_too_many:
            await research_service.compare_stocks(req_too_many, user_id=user_id)
        assert "Compare use case requires 2 to 8 unique valid symbols" in str(exc_too_many.value)

    @pytest.mark.asyncio
    async def test_compare_stocks_propagates_symbol_not_found(
        self,
        research_service: ResearchService,
        mock_fact_aggregator: MagicMock,
    ) -> None:
        mock_fact_aggregator.aggregate_multi_facts = AsyncMock(
            side_effect=SymbolNotFoundError("Symbol 'UNKNOWN' not found")
        )
        req = CompareRequest(symbols=["AAPL", "UNKNOWN"])
        with pytest.raises(SymbolNotFoundError):
            await research_service.compare_stocks(req, user_id=uuid4())

    @pytest.mark.asyncio
    async def test_compare_stocks_propagates_app_error(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        mock_ai_service.run = AsyncMock(side_effect=CustomM7AppError("对比配额超限"))
        req = CompareRequest(symbols=["AAPL", "MSFT"])
        with pytest.raises(CustomM7AppError) as exc_info:
            await research_service.compare_stocks(req, user_id=uuid4())
        assert "对比配额超限" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_compare_stocks_wraps_unexpected_exception(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        mock_ai_service.run = AsyncMock(side_effect=RuntimeError("AI worker timeout"))
        req = CompareRequest(symbols=["AAPL", "MSFT"])
        with pytest.raises(ResearchError) as exc_info:
            await research_service.compare_stocks(req, user_id=uuid4())
        assert "AI analysis execution failed for 'AAPL,MSFT'" in str(exc_info.value)


@pytest.mark.unit
class TestLongTermAnalysisPipeline:
    """F5 长期持有价值与破裂条件分析管道测试。"""

    @pytest.mark.asyncio
    async def test_long_term_analysis_success(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
        mock_fact_aggregator: MagicMock,
    ) -> None:
        user_id = uuid4()
        payload = {
            "symbol": "AAPL",
            "horizon_years": 10,
            "verdict": "holdable",
            "pillars": {
                "moat": {"rating": "strong", "reason": "全球iOS闭环软硬件一体生态"},
                "leadership": {"rating": "strong", "reason": "稳健的资本配置与股票回购"},
                "demand_stability": {"rating": "favorable", "reason": "高黏性消费与服务需求"},
                "pricing_power": {"rating": "strong", "reason": "高端硬件溢价与服务订阅提价权"},
                "innovation": {"rating": "moderate", "reason": "AI终端整合与自研芯片演进"},
                "financial_strength": {"rating": "strong", "reason": "超千亿美元充沛自由现金流"},
                "market_size": {"rating": "favorable", "reason": "新兴市场渗透与可穿戴空间"},
            },
            "thesis": "苹果公司在软硬件飞轮与高毛利服务业务支撑下具备深厚护城河。",
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
            "summary": "苹果公司具备长期10年持有价值，核心生态极度稳固。",
        }
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(
                payload=payload,
                use_case="long_term",
                created_at=datetime(2026, 3, 1, 9, 30, tzinfo=UTC),
            )
        )

        req = LongTermRequest(symbol="AAPL", years=10)
        envelope = await research_service.get_long_term_analysis(req, user_id=user_id)

        assert isinstance(envelope, ResearchEnvelope)
        assert envelope.use_case == "long_term"
        assert envelope.symbol == "AAPL"
        assert envelope.as_of == datetime(2026, 3, 1).date()
        assert envelope.summary == "苹果公司具备长期10年持有价值，核心生态极度稳固。"
        assert envelope.payload == payload
        assert "fundamentals.revenue_growth" in envelope.data_gaps
        assert envelope.disclaimer == "本内容仅供研究与学习，不构成投资建议"

        # 验证调用事实聚合器时传递了 years
        mock_fact_aggregator.aggregate_facts.assert_awaited_once_with(
            symbol="AAPL",
            use_case="long_term",
            years=10,
        )
        mock_ai_service.run.assert_awaited_once_with(
            use_case="long_term",
            facts=mock_fact_aggregator.aggregate_facts.return_value[0],
            params={"symbol": "AAPL", "years": 10},
            user_id=user_id,
        )

    @pytest.mark.asyncio
    async def test_long_term_analysis_empty_symbol_raises_error(
        self,
        research_service: ResearchService,
    ) -> None:
        user_id = uuid4()
        req = LongTermRequest.model_construct(symbol="   ", years=5)
        with pytest.raises(InvalidParameterError) as exc_info:
            await research_service.get_long_term_analysis(req, user_id=user_id)
        assert "Symbol must not be empty" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_long_term_analysis_propagates_symbol_not_found(
        self,
        research_service: ResearchService,
        mock_fact_aggregator: MagicMock,
    ) -> None:
        mock_fact_aggregator.aggregate_facts = AsyncMock(
            side_effect=SymbolNotFoundError("Symbol NOTFOUND not found")
        )
        req = LongTermRequest(symbol="NOTFOUND", years=5)
        with pytest.raises(SymbolNotFoundError):
            await research_service.get_long_term_analysis(req, user_id=uuid4())

    @pytest.mark.asyncio
    async def test_long_term_analysis_propagates_app_error(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        mock_ai_service.run = AsyncMock(side_effect=CustomM7AppError("长期分析配额不足"))
        req = LongTermRequest(symbol="AAPL", years=5)
        with pytest.raises(CustomM7AppError):
            await research_service.get_long_term_analysis(req, user_id=uuid4())

    @pytest.mark.asyncio
    async def test_long_term_analysis_wraps_unexpected_exception(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        mock_ai_service.run = AsyncMock(side_effect=ConnectionResetError("AI peer reset"))
        req = LongTermRequest(symbol="AAPL", years=5)
        with pytest.raises(ResearchError) as exc_info:
            await research_service.get_long_term_analysis(req, user_id=uuid4())
        assert "AI analysis execution failed for 'AAPL'" in str(exc_info.value)


@pytest.mark.unit
class TestPortfolioAllocationPipeline:
    """F8 投资组合配置建议管道测试。"""

    @pytest.mark.asyncio
    async def test_portfolio_allocation_success(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
        mock_fact_aggregator: MagicMock,
    ) -> None:
        user_id = uuid4()
        # 准备多标的事实与量化组合结果
        portfolio_computed = {
            "amount": Decimal("100000.00"),
            "allocations": [
                {
                    "symbol": "AAPL",
                    "weight_pct": Decimal("30.00"),
                    "allocated_amount": Decimal("30000.00"),
                },
                {
                    "symbol": "MSFT",
                    "weight_pct": Decimal("30.00"),
                    "allocated_amount": Decimal("30000.00"),
                },
                {
                    "symbol": "GOOG",
                    "weight_pct": Decimal("30.00"),
                    "allocated_amount": Decimal("30000.00"),
                },
            ],
            "cash_pct": Decimal("10.00"),
            "cash_amount": Decimal("10000.00"),
        }
        mock_fact_aggregator.aggregate_multi_facts = AsyncMock(
            return_value=(
                {
                    "symbols": ["AAPL", "MSFT", "GOOG"],
                    "use_case": "portfolio",
                    "stocks": {
                        "AAPL": {"quote": {"price": "180.00"}},
                        "MSFT": {"quote": {"price": "420.00"}},
                        "GOOG": {"quote": {"price": "175.00"}},
                    },
                    "computed": portfolio_computed,
                },
                [],
            )
        )

        payload = {
            "amount": Decimal("100000.00"),
            "allocations": [
                {
                    "symbol": "AAPL",
                    "weight_pct": Decimal("30.00"),
                    "allocated_amount": Decimal("30000.00"),
                    "reason": "消费科技基石",
                },
                {
                    "symbol": "MSFT",
                    "weight_pct": Decimal("30.00"),
                    "allocated_amount": Decimal("30000.00"),
                    "reason": "企业软件与云引擎",
                },
                {
                    "symbol": "GOOG",
                    "weight_pct": Decimal("30.00"),
                    "allocated_amount": Decimal("30000.00"),
                    "reason": "数字广告与AI底座",
                },
            ],
            "cash_pct": Decimal("10.00"),
            "cash_amount": Decimal("10000.00"),
            "rationale": "均衡配置三大科技巨头，各配置 30%，保留 10% 现金缓冲。",
            "risk_notes": "科技巨头同质化风险偏高，需警惕反垄断监管变化。",
            "rebalance_suggestion": "建议每半年检视一次，偏离度超 5% 执行再平衡。",
        }
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(
                payload=payload,
                use_case="portfolio",
                created_at=datetime(2026, 3, 5, 14, 0, tzinfo=UTC),
            )
        )

        req = PortfolioRequest(
            amount=Decimal("100000.00"),
            symbols=["AAPL", "MSFT", "GOOG"],
            risk_level="moderate",
            goal="growth",
        )
        envelope = await research_service.generate_portfolio_allocation(req, user_id=user_id)

        assert isinstance(envelope, ResearchEnvelope)
        assert envelope.use_case == "portfolio"
        assert envelope.symbol == "AAPL,MSFT,GOOG"
        assert envelope.as_of == datetime(2026, 3, 5).date()
        assert envelope.summary == "均衡配置三大科技巨头，各配置 30%，保留 10% 现金缓冲。"
        assert envelope.payload == payload
        assert envelope.disclaimer == "本内容仅供研究与学习，不构成投资建议"

        # 检查 evidence 中已包含代码量化派生的配比与现金缓冲
        claim_texts = [e.claim for e in envelope.evidence]
        assert any("建议预留现金比例 10.00%" in c for c in claim_texts)
        assert any("AAPL" in c and "30.00%" in c for c in claim_texts)

        # 验证透传参数
        mock_fact_aggregator.aggregate_multi_facts.assert_awaited_once_with(
            symbols=["AAPL", "MSFT", "GOOG"],
            use_case="portfolio",
            amount=Decimal("100000.00"),
            risk_level="moderate",
            goal="growth",
        )
        mock_ai_service.run.assert_awaited_once_with(
            use_case="portfolio",
            facts=mock_fact_aggregator.aggregate_multi_facts.return_value[0],
            params={
                "symbols": ["AAPL", "MSFT", "GOOG"],
                "amount": "100000.00",
                "risk_level": "moderate",
                "goal": "growth",
            },
            user_id=user_id,
        )

    @pytest.mark.asyncio
    async def test_portfolio_allocation_validation_errors(
        self,
        research_service: ResearchService,
    ) -> None:
        user_id = uuid4()

        # 金额小于等于 0
        req_zero = PortfolioRequest.model_construct(
            amount=Decimal("0.00"),
            symbols=["AAPL", "MSFT"],
            risk_level="moderate",
            goal="growth",
        )
        with pytest.raises(InvalidParameterError) as exc_zero:
            await research_service.generate_portfolio_allocation(req_zero, user_id=user_id)
        assert "Portfolio amount must be greater than 0" in str(exc_zero.value)

        req_neg = PortfolioRequest.model_construct(
            amount=Decimal("-100.00"),
            symbols=["AAPL", "MSFT"],
            risk_level="moderate",
            goal="growth",
        )
        with pytest.raises(InvalidParameterError) as exc_neg:
            await research_service.generate_portfolio_allocation(req_neg, user_id=user_id)
        assert "Portfolio amount must be greater than 0" in str(exc_neg.value)

        # 标的数去重后不足 2
        req_single = PortfolioRequest(
            amount=Decimal("50000.00"),
            symbols=["AAPL", "AAPL"],
            risk_level="moderate",
            goal="growth",
        )
        with pytest.raises(InvalidParameterError) as exc_single:
            await research_service.generate_portfolio_allocation(req_single, user_id=user_id)
        assert "Portfolio use case requires 2 to 12 unique valid symbols" in str(exc_single.value)

        # 标的数超过 12
        req_too_many = PortfolioRequest.model_construct(
            amount=Decimal("50000.00"),
            symbols=[f"S{i}" for i in range(13)],
            risk_level="moderate",
            goal="growth",
        )
        with pytest.raises(InvalidParameterError) as exc_too_many:
            await research_service.generate_portfolio_allocation(req_too_many, user_id=user_id)
        assert "Portfolio use case requires 2 to 12 unique valid symbols" in str(exc_too_many.value)

    @pytest.mark.asyncio
    async def test_portfolio_allocation_propagates_symbol_not_found(
        self,
        research_service: ResearchService,
        mock_fact_aggregator: MagicMock,
    ) -> None:
        mock_fact_aggregator.aggregate_multi_facts = AsyncMock(
            side_effect=SymbolNotFoundError("Symbol AAPL not found")
        )
        req = PortfolioRequest(
            amount=Decimal("10000.00"),
            symbols=["AAPL", "MSFT"],
            risk_level="moderate",
            goal="growth",
        )
        with pytest.raises(SymbolNotFoundError):
            await research_service.generate_portfolio_allocation(req, user_id=uuid4())

    @pytest.mark.asyncio
    async def test_portfolio_allocation_propagates_app_error(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        mock_ai_service.run = AsyncMock(side_effect=CustomM7AppError("组合模型服务故障"))
        req = PortfolioRequest(
            amount=Decimal("10000.00"),
            symbols=["AAPL", "MSFT"],
            risk_level="moderate",
            goal="growth",
        )
        with pytest.raises(CustomM7AppError):
            await research_service.generate_portfolio_allocation(req, user_id=uuid4())

    @pytest.mark.asyncio
    async def test_portfolio_allocation_wraps_unexpected_exception(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        mock_ai_service.run = AsyncMock(side_effect=KeyError("Missing AI response field"))
        req = PortfolioRequest(
            amount=Decimal("10000.00"),
            symbols=["AAPL", "MSFT"],
            risk_level="moderate",
            goal="growth",
        )
        with pytest.raises(ResearchError) as exc_info:
            await research_service.generate_portfolio_allocation(req, user_id=uuid4())
        assert "AI analysis execution failed for 'AAPL,MSFT'" in str(exc_info.value)


@pytest.mark.unit
class TestEvidenceAndSummaryM7:
    """佐证项注入与摘要后备降级测试。"""

    @pytest.mark.asyncio
    async def test_custom_evidence_in_m7_payload_respected(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        user_id = uuid4()
        custom_evidence = [
            {"claim": "AAPL 综合排名第一", "source_field": "facts.computed.ranking"},
            EvidenceItem(claim="MSFT 云业务增长 28%", source_field="facts.stocks.MSFT.quote.price"),
        ]
        payload = {
            "summary": "自定义佐证对比测试",
            "evidence": custom_evidence,
        }
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(payload=payload, use_case="compare")
        )

        envelope = await research_service.compare_stocks(
            CompareRequest(symbols=["AAPL", "MSFT"]), user_id=user_id
        )
        assert len(envelope.evidence) == 2
        assert envelope.evidence[0].claim == "AAPL 综合排名第一"
        assert envelope.evidence[0].source_field == "facts.computed.ranking"
        assert envelope.evidence[1].source_field == "facts.stocks.MSFT.quote.price"

    @pytest.mark.asyncio
    async def test_summary_fallback_when_fields_missing(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        user_id = uuid4()
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(payload={}, use_case="compare")
        )

        envelope = await research_service.compare_stocks(
            CompareRequest(symbols=["AAPL", "MSFT"]), user_id=user_id
        )
        assert envelope.summary == "AAPL,MSFT compare 分析完成"

    @pytest.mark.asyncio
    async def test_as_of_date_fallback_to_clock(
        self,
        research_service: ResearchService,
        mock_ai_service: MagicMock,
    ) -> None:
        user_id = uuid4()
        # report.created_at 为 None 时使用 clock.now().date()
        mock_ai_service.run = AsyncMock(
            return_value=DummyAnalysisReport(
                payload={"summary": "无创建时间报告"},
                use_case="long_term",
                created_at=None,
            )
        )

        envelope = await research_service.get_long_term_analysis(
            LongTermRequest(symbol="AAPL", years=5), user_id=user_id
        )
        assert envelope.as_of is not None

    @pytest.mark.asyncio
    async def test_execute_multi_pipeline_fallback_validation(
        self,
        research_service: ResearchService,
    ) -> None:
        with pytest.raises(InvalidParameterError) as exc_info:
            await research_service._execute_multi_pipeline(
                use_case="custom_multi",
                symbols=["AAPL"],
                user_id=uuid4(),
                params={},
                aggregator_kwargs={},
            )
        err_msg = "Multi-stock pipeline requires at least 2 unique valid symbols"
        assert err_msg in str(exc_info.value)
