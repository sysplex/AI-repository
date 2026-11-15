"""M7 黄金数据集多标的场景集成测试套件（T07）。

基于代表性标的矩阵（AAPL, CAT, KO, PLTR, SOFI）构建多场景全覆盖测试：
1. 对比矩阵（F4）：
   - 科技 vs 周期（AAPL vs CAT）
   - 防守 vs 成长（KO vs PLTR）
   - 五标的综合大比拼（AAPL, CAT, KO, PLTR, SOFI）
2. 长期投资价值矩阵（F5）：
   - 5 年期（AAPL, SOFI）、10 年期（KO, CAT）、15 年期（PLTR）
3. 投资组合配置优化矩阵（F8）：
   - 保守型（conservative / safety）
   - 平衡型（balanced / income）
   - 激进型（aggressive / growth）
   - 退休稳健型（conservative / retirement）
4. 防编造与合规铁律：
   - 0 幻觉数字（FactTracingEngine 100% 溯源通过）；
   - 0 违规禁用词（DEFAULT_BANNED_TERMS 绝不出现）；
   - 对比排名与代码分位打分 100% 匹配；
   - 组合权重和与现金比例严格恒等于 100.00%；
   - 论文破裂条件均指向有效基本面字段。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.clock import get_clock
from app.modules.ai.schemas import AnalysisReport
from app.modules.ai.tracing import DEFAULT_BANNED_TERMS, FactTracingEngine
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.schemas import AuthenticatedUser, UserSettings
from app.modules.research.aggregator import (
    USE_CASE_COMPARE,
    USE_CASE_LONG_TERM,
    USE_CASE_PORTFOLIO,
    FactAggregator,
)
from app.modules.research.compliance import (
    DEFAULT_DISCLAIMER,
    check_novice_readability,
    contains_forbidden_terms,
    validate_portfolio_weights,
    validate_thesis_breakers,
)
from app.modules.research.quantitative import (
    QuantitativeEngine,
)
from app.modules.research.schemas import (
    ComparePayload,
    CompareRequest,
    LongTermPayload,
    LongTermRequest,
    PortfolioPayload,
    PortfolioRequest,
    ResearchEnvelope,
)
from app.modules.research.service import ResearchService
from tests.integration.modules.research.fixtures.m7_golden_scenarios import (
    COMPARE_SCENARIOS,
    LONG_TERM_SCENARIOS,
    PORTFOLIO_SCENARIOS,
    CompareScenario,
    LongTermScenario,
    PortfolioScenario,
    build_m7_mock_data_service,
    build_m7_mock_strategy_service,
    generate_m7_golden_llm_response,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def auth_user() -> AuthenticatedUser:
    """Mock authenticated user for HARD-01."""
    return AuthenticatedUser(
        id=uuid.uuid4(),
        email="m7_golden_tester@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(),
    )


@pytest.fixture
def golden_m7_research_env() -> dict[str, Any]:
    """Sets up FactAggregator, AIService, and ResearchService backed by golden dataset."""
    mock_data_service = build_m7_mock_data_service()
    mock_strategy_service = build_m7_mock_strategy_service()

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
        payload = generate_m7_golden_llm_response(use_case, facts, params)

        # 核心防编造防线：执行 FactTracingEngine 反向溯源校验
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
            data_snapshot_id=f"snap_m7_{use_case}",
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
# 1. F4: 股票横向对比 (compare) 场景矩阵测试
# =============================================================================


class TestM7CompareGoldenScenarios:
    """验证 F4 股票横向对比在多标的典型场景下的全链路表现。"""

    @pytest.mark.parametrize("scenario", COMPARE_SCENARIOS, ids=lambda s: s.name)
    async def test_golden_compare_scenarios(
        self,
        scenario: CompareScenario,
        golden_m7_research_env: dict[str, Any],
        auth_user: AuthenticatedUser,
    ) -> None:
        service: ResearchService = golden_m7_research_env["service"]
        aggregator: FactAggregator = golden_m7_research_env["aggregator"]

        req = CompareRequest(symbols=scenario.symbols)
        envelope: ResearchEnvelope = await service.compare_stocks(req, user_id=auth_user.id)

        # 1. 通用信封结构断言
        assert envelope.schema_version == "1.0"
        assert envelope.use_case == USE_CASE_COMPARE
        expected_sym_repr = ",".join(scenario.symbols)
        assert envelope.symbol == expected_sym_repr
        assert envelope.disclaimer == DEFAULT_DISCLAIMER
        assert len(envelope.summary) > 0
        assert len(envelope.evidence) >= 1

        # 2. Schema 严格反序列化校验
        payload_obj = ComparePayload.model_validate(envelope.payload)
        assert payload_obj.symbols == scenario.symbols
        assert len(payload_obj.ranking) == len(scenario.symbols)
        assert len(payload_obj.fit_by_investor) == len(scenario.symbols)

        # 3. 排名与分位总分必须 100% 匹配代码量化引擎计算
        multi_facts, _ = await aggregator.aggregate_multi_facts(
            symbols=scenario.symbols,
            use_case=USE_CASE_COMPARE,
        )
        exp_ranking = multi_facts["computed"]["ranking"]
        assert len(payload_obj.ranking) == len(exp_ranking)
        for act_item, exp_item in zip(payload_obj.ranking, exp_ranking, strict=True):
            assert act_item.symbol == exp_item["symbol"]
            assert act_item.rank == exp_item["rank"]
            assert act_item.total_score == exp_item["total_score"]

        # 4. 8 大维度定性分析完整性检查
        dims = payload_obj.dimension_notes
        for dim_field in [
            "growth",
            "margin",
            "debt",
            "valuation",
            "moat",
            "risk",
            "dividend",
            "long_term",
        ]:
            val = getattr(dims, dim_field)
            assert isinstance(val, str) and len(val) > 0

        # 5. 投资者画像匹配覆盖度检查
        for fit in payload_obj.fit_by_investor:
            assert len(fit.suitable_for) >= 1
            assert len(fit.not_suitable_for) >= 1

        # 6. 新手可读性与零禁用词断言
        is_readable, suggestions = check_novice_readability(
            envelope.payload, use_case=USE_CASE_COMPARE
        )
        assert is_readable is True
        assert len(suggestions) == 0

        assert not contains_forbidden_terms(envelope.payload)
        for term in DEFAULT_BANNED_TERMS:
            assert term not in str(envelope.payload)

        # 7. FactTracingEngine 独立回溯验证
        tracing = FactTracingEngine()
        trace_res = tracing.verify(
            envelope.payload,
            multi_facts,
            computed=multi_facts.get("computed"),
        )
        assert trace_res.valid is True
        assert len(trace_res.violations) == 0


# =============================================================================
# 2. F5: 长期投资价值 (long_term) 场景矩阵测试
# =============================================================================


class TestM7LongTermGoldenScenarios:
    """验证 F5 长期持有价值与破裂条件在不同投资期限（5/10/15年）下的全链路表现。"""

    @pytest.mark.parametrize(
        "scenario", LONG_TERM_SCENARIOS, ids=lambda s: f"{s.symbol}_{s.years}y"
    )
    async def test_golden_long_term_scenarios(
        self,
        scenario: LongTermScenario,
        golden_m7_research_env: dict[str, Any],
        auth_user: AuthenticatedUser,
    ) -> None:
        service: ResearchService = golden_m7_research_env["service"]
        aggregator: FactAggregator = golden_m7_research_env["aggregator"]

        req = LongTermRequest(symbol=scenario.symbol, years=scenario.years)
        envelope: ResearchEnvelope = await service.get_long_term_analysis(req, user_id=auth_user.id)

        # 1. 通用信封结构断言
        assert envelope.schema_version == "1.0"
        assert envelope.use_case == USE_CASE_LONG_TERM
        assert envelope.symbol == scenario.symbol
        assert envelope.disclaimer == DEFAULT_DISCLAIMER
        assert len(envelope.evidence) >= 1

        # 2. Schema 严格反序列化校验
        payload_obj = LongTermPayload.model_validate(envelope.payload)
        assert payload_obj.symbol == scenario.symbol
        assert payload_obj.horizon_years == scenario.years
        assert payload_obj.verdict in {
            "holdable",
            "holdable_with_conditions",
            "not_recommended",
        }

        # 3. 7 大支柱完备性与评级有效性
        pillars = payload_obj.pillars
        valid_ratings = {
            "strong",
            "moderate",
            "weak",
            "favorable",
            "neutral",
            "unfavorable",
        }
        for pillar_name in [
            "moat",
            "leadership",
            "demand_stability",
            "pricing_power",
            "innovation",
            "financial_strength",
            "market_size",
        ]:
            item = getattr(pillars, pillar_name)
            assert item.rating in valid_ratings
            assert len(item.reason) > 0

        # 4. 论文破裂条件合规与字段可监控性（>= 3 条）
        assert len(payload_obj.thesis_breakers) >= 3
        is_valid_breakers, breaker_issues = validate_thesis_breakers(payload_obj.thesis_breakers)
        assert is_valid_breakers is True
        assert len(breaker_issues) == 0

        facts, _ = await aggregator.aggregate_facts(
            symbol=scenario.symbol,
            use_case=USE_CASE_LONG_TERM,
            years=scenario.years,
        )

        # 校验破裂条件的 data_field 均指向 facts 中真实存在的基本面路径
        for tb in payload_obj.thesis_breakers:
            assert len(tb.condition) > 0
            assert len(tb.metric) > 0
            assert len(tb.threshold) > 0
            field_tokens = tb.data_field.split(".")
            curr = facts
            for token in field_tokens:
                assert token in curr, f"Path token '{token}' from '{tb.data_field}' not in facts"
                curr = curr[token]

        # 5. 新手可读性与零禁用词断言
        is_readable, suggestions = check_novice_readability(
            envelope.payload, use_case=USE_CASE_LONG_TERM
        )
        assert is_readable is True
        assert len(suggestions) == 0

        assert not contains_forbidden_terms(envelope.payload)
        for term in DEFAULT_BANNED_TERMS:
            assert term not in str(envelope.payload)

        # 6. FactTracingEngine 独立回溯验证
        tracing = FactTracingEngine()
        trace_res = tracing.verify(
            envelope.payload,
            facts,
            computed=facts.get("computed"),
        )
        assert trace_res.valid is True
        assert len(trace_res.violations) == 0


# =============================================================================
# 3. F8: 投资组合优化 (portfolio) 场景矩阵测试
# =============================================================================


class TestM7PortfolioGoldenScenarios:
    """验证 F8 投资组合优化在不同风险偏好与投资目标下的守恒性与配置逻辑。"""

    @pytest.mark.parametrize("scenario", PORTFOLIO_SCENARIOS, ids=lambda s: s.name)
    async def test_golden_portfolio_scenarios(
        self,
        scenario: PortfolioScenario,
        golden_m7_research_env: dict[str, Any],
        auth_user: AuthenticatedUser,
    ) -> None:
        service: ResearchService = golden_m7_research_env["service"]
        aggregator: FactAggregator = golden_m7_research_env["aggregator"]

        req = PortfolioRequest(
            amount=scenario.amount,
            symbols=scenario.symbols,
            risk_level=scenario.risk_level,
            goal=scenario.goal,
        )
        envelope: ResearchEnvelope = await service.generate_portfolio_allocation(
            req, user_id=auth_user.id
        )

        # 1. 通用信封结构断言
        assert envelope.schema_version == "1.0"
        assert envelope.use_case == USE_CASE_PORTFOLIO
        assert envelope.disclaimer == DEFAULT_DISCLAIMER
        assert len(envelope.evidence) >= 1

        # 2. Schema 严格反序列化校验
        payload_obj = PortfolioPayload.model_validate(envelope.payload)
        assert payload_obj.amount == scenario.amount
        assert len(payload_obj.allocations) == len(scenario.symbols)

        # 3. 绝对守恒定律 A：标的权重和 + 现金比例 严格等于 100.00%
        sum_weights = sum(a.weight_pct for a in payload_obj.allocations)
        total_pct = sum_weights + payload_obj.cash_pct
        assert abs(total_pct - Decimal("100.00")) <= Decimal("0.01")

        # 4. 绝对守恒定律 B：各标的分配资金 + 现金金额 严格等于 总金额
        sum_amounts = sum(a.allocated_amount for a in payload_obj.allocations)
        total_allocated = sum_amounts + payload_obj.cash_amount
        assert abs(total_allocated - scenario.amount) <= Decimal("0.02")

        # 5. 与底层 FactAggregator 优化结果绝对匹配
        multi_facts, _ = await aggregator.aggregate_multi_facts(
            symbols=scenario.symbols,
            use_case=USE_CASE_PORTFOLIO,
            amount=scenario.amount,
            risk_level=scenario.risk_level,
            goal=scenario.goal,
        )
        exp_computed = multi_facts["computed"]
        assert payload_obj.cash_pct == exp_computed["cash_pct"]
        assert payload_obj.cash_amount == exp_computed["cash_amount"]

        for act_a, exp_a in zip(payload_obj.allocations, exp_computed["allocations"], strict=True):
            assert act_a.symbol == exp_a["symbol"]
            assert act_a.weight_pct == exp_a["weight_pct"]
            assert act_a.allocated_amount == exp_a["allocated_amount"]

        # 6. 代码量化与合规校验器验证
        is_valid_weights, issues = validate_portfolio_weights(
            envelope.payload,
            computed=exp_computed,
        )
        assert is_valid_weights is True
        assert len(issues) == 0

        # 7. 新手可读性与零禁用词断言
        is_readable, suggestions = check_novice_readability(
            envelope.payload, use_case=USE_CASE_PORTFOLIO
        )
        assert is_readable is True
        assert len(suggestions) == 0

        assert not contains_forbidden_terms(envelope.payload)
        for term in DEFAULT_BANNED_TERMS:
            assert term not in str(envelope.payload)

        # 8. FactTracingEngine 独立回溯验证
        tracing = FactTracingEngine()
        trace_res = tracing.verify(
            envelope.payload,
            multi_facts,
            computed=multi_facts.get("computed"),
        )
        assert trace_res.valid is True
        assert len(trace_res.violations) == 0


# =============================================================================
# 4. 防篡改与合规防线韧性测试 (Guardrail Tamper-Resistance)
# =============================================================================


class TestM7GuardrailTamperResistance:
    """验证合规防线与代码量化防篡改的坚固性。"""

    def test_compare_ranking_tamper_detection(self) -> None:
        """测试横向对比排名被恶意篡改时被合规校验精确拦截。"""
        engine = QuantitativeEngine()
        facts_dict = {
            "AAPL": {"fundamentals": {"pe_trailing": Decimal("30.0")}},
            "KO": {"fundamentals": {"pe_trailing": Decimal("25.0")}},
        }
        correct_ranking = engine.compute_cross_sectional_ranking(facts_dict)

        tampered_ranking = [
            {
                "symbol": "KO",
                "rank": 1,
                "total_score": Decimal("99.99"),
                "one_line_reason": "人为篡改得分",
            },
            {
                "symbol": "AAPL",
                "rank": 2,
                "total_score": Decimal("10.00"),
                "one_line_reason": "人为篡改得分",
            },
        ]
        from app.modules.research.compliance import validate_compare_ranking

        is_valid, issues = validate_compare_ranking(
            {"ranking": tampered_ranking},
            computed={"ranking": correct_ranking},
        )
        assert is_valid is False
        assert len(issues) >= 1

    def test_portfolio_weights_tamper_detection(self) -> None:
        """测试投资组合权重和不等于 100% 时被严格拦截。"""
        allocations = [
            {"symbol": "AAPL", "weight_pct": Decimal("40.00")},
            {"symbol": "MSFT", "weight_pct": Decimal("40.00")},
        ]
        # 现金仅 10%，总和 90% != 100%
        is_valid, issues = validate_portfolio_weights(
            {"allocations": allocations, "cash_pct": Decimal("10.00")}
        )
        assert is_valid is False
        assert len(issues) >= 1
        assert any("不守恒" in issue for issue in issues)

    def test_thesis_breakers_insufficient_detection(self) -> None:
        """测试长期持有破裂条件少于 3 条时被严格拦截。"""
        two_breakers = [
            {
                "condition": "条件1",
                "metric": "m1",
                "threshold": "< 1",
                "data_field": "fundamentals.net_margin",
            },
            {
                "condition": "条件2",
                "metric": "m2",
                "threshold": "< 2",
                "data_field": "fundamentals.pe_trailing",
            },
        ]
        is_valid, issues = validate_thesis_breakers(two_breakers)
        assert is_valid is False
        assert len(issues) >= 1
        assert any("至少需要 3 条" in issue for issue in issues)

    def test_forbidden_terms_detection(self) -> None:
        """测试任何包含承诺保证词汇的 payload 均被合规检查器拦截。"""
        for term in DEFAULT_BANNED_TERMS:
            payload = {"summary": f"该投资方案{term}，值得重点关注"}
            found = contains_forbidden_terms(payload)
            assert len(found) >= 1
            assert any(term in f for f in found)
