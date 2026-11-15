"""Unit tests for M7 cross-sectional ranking and portfolio optimization engine (M7-T03).

Covers:
1. compute_cross_sectional_ranking monotonicity, tie breaking, missing data and extreme PE
2. optimize_portfolio_weights risk level constraints, goal biases, and mathematical invariance
3. QuantitativeEngine protocol conformance
4. FactAggregator.aggregate_multi_facts multi-stock concurrent gathering and enrichment
"""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.modules.research.aggregator import (
    USE_CASE_COMPARE,
    USE_CASE_LONG_TERM,
    USE_CASE_PORTFOLIO,
    FactAggregator,
)
from app.modules.research.exceptions import (
    InvalidParameterError,
    SymbolNotFoundError,
)
from app.modules.research.ports import (
    FactAggregatorProtocol,
    QuantitativeEngineProtocol,
)
from app.modules.research.quantitative import (
    QuantitativeEngine,
    compute_cross_sectional_ranking,
    optimize_portfolio_weights,
)
from app.modules.research.schemas import (
    CompareRankingItem,
    PortfolioAllocationItem,
)

# =============================================================================
# 1. compute_cross_sectional_ranking 测试
# =============================================================================


def test_ranking_monotonic_superiority() -> None:
    """验证全面占优的标的在综合排序中得分严格高于劣势标的且排名第一。"""
    facts_superior = {
        "fundamentals": {
            "revenue_growth": 0.25,  # 优
            "net_margin": 0.30,  # 优
            "roe": 0.35,  # 优
            "dividend_yield": 0.02,  # 优
            "pe_trailing": 22.0,  # 较低（估值更优）
            "debt_to_equity": 0.40,  # 负债更低（更健康）
            "beta": 0.85,  # 波动更低
        }
    }
    facts_inferior = {
        "fundamentals": {
            "revenue_growth": 0.03,
            "net_margin": 0.08,
            "roe": 0.10,
            "dividend_yield": 0.00,
            "pe_trailing": 65.0,
            "debt_to_equity": 2.50,
            "beta": 1.45,
        }
    }

    ranking = compute_cross_sectional_ranking({"BEST": facts_superior, "WORST": facts_inferior})
    assert len(ranking) == 2
    assert ranking[0]["symbol"] == "BEST"
    assert ranking[0]["rank"] == 1
    assert ranking[1]["symbol"] == "WORST"
    assert ranking[1]["rank"] == 2
    assert ranking[0]["total_score"] > ranking[1]["total_score"]

    # 验证返回结构符合 CompareRankingItem DTO 契约
    item1 = CompareRankingItem.model_validate(ranking[0])
    assert item1.symbol == "BEST"
    assert item1.rank == 1


def test_ranking_minimum_stocks_constraint() -> None:
    """验证不足 2 只标的时抛出 InvalidParameterError。"""
    with pytest.raises(InvalidParameterError) as exc:
        compute_cross_sectional_ranking({"AAPL": {"fundamentals": {}}})
    assert "at least 2 stocks" in str(exc.value)


def test_ranking_identical_metrics_tie_breaker() -> None:
    """验证指标完全相同的标的得分完全相同，由 symbol 字母序确定性排序。"""
    identical_facts = {
        "fundamentals": {
            "revenue_growth": 0.10,
            "net_margin": 0.15,
            "roe": 0.18,
            "dividend_yield": 0.015,
            "pe_trailing": 25.0,
            "debt_to_equity": 0.8,
            "beta": 1.0,
        }
    }

    ranking = compute_cross_sectional_ranking({"MSFT": identical_facts, "AAPL": identical_facts})
    assert len(ranking) == 2
    assert ranking[0]["total_score"] == ranking[1]["total_score"]
    # 字母序 AAPL < MSFT
    assert ranking[0]["symbol"] == "AAPL"
    assert ranking[0]["rank"] == 1
    assert ranking[1]["symbol"] == "MSFT"
    assert ranking[1]["rank"] == 2


def test_ranking_negative_pe_loss_making_penalty() -> None:
    """验证市盈率 PE <= 0（亏损企业）受到深度惩罚，劣于正市盈率标的。"""
    profitable = {
        "fundamentals": {
            "revenue_growth": 0.10,
            "net_margin": 0.10,
            "roe": 0.12,
            "dividend_yield": 0.01,
            "pe_trailing": 40.0,  # 虽高但盈利
            "debt_to_equity": 1.0,
            "beta": 1.0,
        }
    }
    loss_making = {
        "fundamentals": {
            "revenue_growth": 0.10,
            "net_margin": -0.05,  # 亏损
            "roe": -0.08,
            "dividend_yield": 0.0,
            "pe_trailing": -15.0,  # 负市盈率
            "debt_to_equity": 1.0,
            "beta": 1.0,
        }
    }

    ranking = compute_cross_sectional_ranking({"PROFIT": profitable, "LOSS": loss_making})
    assert ranking[0]["symbol"] == "PROFIT"
    assert ranking[0]["total_score"] > ranking[1]["total_score"]


def test_ranking_missing_data_imputation() -> None:
    """验证部分标的数据缺失时不崩溃，安全赋予中性 50 分。"""
    full_data = {
        "fundamentals": {
            "revenue_growth": 0.15,
            "net_margin": 0.20,
            "roe": 0.25,
            "dividend_yield": 0.02,
            "pe_trailing": 20.0,
            "debt_to_equity": 0.5,
            "beta": 0.9,
        }
    }
    empty_data: dict[str, Any] = {"fundamentals": {}}

    ranking = compute_cross_sectional_ranking({"FULL": full_data, "EMPTY": empty_data})
    assert len(ranking) == 2
    assert ranking[0]["symbol"] == "FULL"
    assert ranking[1]["symbol"] == "EMPTY"
    assert ranking[1]["total_score"] > Decimal("0.00")


# =============================================================================
# 2. optimize_portfolio_weights 测试
# =============================================================================


def test_portfolio_weights_mathematical_invariance_conservative() -> None:
    """验证 conservative 风险下权重与金额的严格守恒性及约束。"""
    amount = Decimal("100000.00")
    symbols = ["AAPL", "MSFT", "NVDA", "JNJ", "PG"]

    opt = optimize_portfolio_weights(
        amount=amount,
        symbols=symbols,
        risk_level="conservative",
        goal="safety",
    )

    # 1. 守恒验证：sum(w) + cash_pct == 100.00%
    total_weights = sum(item["weight_pct"] for item in opt["allocations"]) + opt["cash_pct"]
    assert total_weights == Decimal("100.00")

    # 2. 金额守恒：sum(amount_i) + cash_amount == amount
    total_allocated = sum(item["allocated_amount"] for item in opt["allocations"])
    assert total_allocated + opt["cash_amount"] == amount

    # 3. 约束验证：稳健型 cash_pct >= 20.00%, max_weight <= 25.00%
    assert opt["cash_pct"] >= Decimal("20.00")
    for item in opt["allocations"]:
        assert item["weight_pct"] <= Decimal("25.00")
        assert item["weight_pct"] > Decimal("0.00")

    # 4. 验证 DTO 序列化
    for item in opt["allocations"]:
        p_item = PortfolioAllocationItem.model_validate(item)
        assert p_item.weight_pct > Decimal("0")


def test_portfolio_weights_moderate_and_aggressive() -> None:
    """验证 moderate 和 aggressive 风险等级的约束与守恒。"""
    amount = Decimal("50000.00")
    symbols = ["AAPL", "NVDA", "TSLA"]

    # Moderate
    opt_mod = optimize_portfolio_weights(
        amount=amount,
        symbols=symbols,
        risk_level="moderate",
        goal="growth",
    )
    assert opt_mod["cash_pct"] >= Decimal("10.00")
    for item in opt_mod["allocations"]:
        assert item["weight_pct"] <= Decimal("30.00")
    w_sum = sum(item["weight_pct"] for item in opt_mod["allocations"]) + opt_mod["cash_pct"]
    assert w_sum == Decimal("100.00")

    # Aggressive
    opt_agg = optimize_portfolio_weights(
        amount=amount,
        symbols=symbols,
        risk_level="aggressive",
        goal="growth",
    )
    assert opt_agg["cash_pct"] >= Decimal("5.00")
    for item in opt_agg["allocations"]:
        assert item["weight_pct"] <= Decimal("40.00")
    w_agg_sum = sum(item["weight_pct"] for item in opt_agg["allocations"]) + opt_agg["cash_pct"]
    assert w_agg_sum == Decimal("100.00")


def test_portfolio_weights_retirement_goal_extra_buffer() -> None:
    """验证 retirement 目标会自动增加 5% 现金防守缓冲区。"""
    opt = optimize_portfolio_weights(
        amount=Decimal("100000.00"),
        symbols=["AAPL", "MSFT", "JNJ", "KO"],
        risk_level="moderate",
        goal="retirement",
    )
    # moderate 默认 10%，加 5% 为 15%
    assert opt["cash_pct"] >= Decimal("15.00")
    total_weights = sum(item["weight_pct"] for item in opt["allocations"]) + opt["cash_pct"]
    assert total_weights == Decimal("100.00")


def test_portfolio_weights_validation_errors() -> None:
    """验证非法金额与越界标的数量被拦截。"""
    # 非法金额
    with pytest.raises(InvalidParameterError) as exc1:
        optimize_portfolio_weights(
            amount=Decimal("0.00"),
            symbols=["AAPL", "MSFT"],
        )
    assert "amount must be positive" in str(exc1.value).lower()

    # 标的太少 (< 2)
    with pytest.raises(InvalidParameterError) as exc2:
        optimize_portfolio_weights(
            amount=Decimal("10000.00"),
            symbols=["AAPL"],
        )
    assert "between 2 and 12" in str(exc2.value)

    # 标的过多 (> 12)
    too_many = [f"SYM{i}" for i in range(13)]
    with pytest.raises(InvalidParameterError) as exc3:
        optimize_portfolio_weights(
            amount=Decimal("10000.00"),
            symbols=too_many,
        )
    assert "between 2 and 12" in str(exc3.value)


# =============================================================================
# 3. QuantitativeEngine Protocol 协议与门面测试
# =============================================================================


def test_quantitative_engine_protocol_conformance() -> None:
    """验证 QuantitativeEngine 满足 QuantitativeEngineProtocol。"""
    engine = QuantitativeEngine()
    assert isinstance(engine, QuantitativeEngineProtocol)

    # 调用横向打分
    ranking = engine.compute_cross_sectional_ranking(
        {
            "AAPL": {"fundamentals": {"revenue_growth": 0.1}},
            "MSFT": {"fundamentals": {"revenue_growth": 0.15}},
        }
    )
    assert len(ranking) == 2

    # 调用组合优化
    portfolio = engine.optimize_portfolio_weights(
        amount=Decimal("20000.00"),
        symbols=["AAPL", "MSFT"],
        risk_level="moderate",
    )
    assert portfolio["amount"] == Decimal("20000.00")


# =============================================================================
# 4. FactAggregator.aggregate_multi_facts 测试
# =============================================================================


@pytest.mark.asyncio
async def test_fact_aggregator_multi_facts_compare() -> None:
    """验证 FactAggregator 对 compare 用例的多标的并发采集与排名计算。"""
    mock_data = AsyncMock()

    async def _mock_build_facts(sym: str, scope: list[str]) -> dict[str, Any]:
        return {
            "facts": {
                "symbol": sym,
                "quote": {"price": 150.0},
                "profile": {"sector": "Technology"},
                "fundamentals": {
                    "revenue_growth": 0.20 if sym == "MSFT" else 0.10,
                    "net_margin": 0.35 if sym == "MSFT" else 0.25,
                    "pe_trailing": 30.0,
                },
            },
            "missing_fields": [],
        }

    mock_data.build_facts = AsyncMock(side_effect=_mock_build_facts)
    aggregator = FactAggregator(data_service=mock_data)

    assert isinstance(aggregator, FactAggregatorProtocol)

    multi_facts, missing = await aggregator.aggregate_multi_facts(
        symbols=["AAPL", "MSFT"],
        use_case=USE_CASE_COMPARE,
    )

    assert multi_facts["use_case"] == "compare"
    assert multi_facts["symbols"] == ["AAPL", "MSFT"]
    assert "stocks" in multi_facts
    assert "AAPL" in multi_facts["stocks"] and "MSFT" in multi_facts["stocks"]
    assert "computed" in multi_facts
    assert "ranking" in multi_facts["computed"]

    ranking = multi_facts["computed"]["ranking"]
    assert len(ranking) == 2
    assert ranking[0]["symbol"] == "MSFT"
    assert ranking[0]["rank"] == 1


@pytest.mark.asyncio
async def test_fact_aggregator_multi_facts_portfolio() -> None:
    """验证 FactAggregator 对 portfolio 用例的多标的并发采集与组合优化计算。"""
    mock_data = AsyncMock()

    async def _mock_build_facts(sym: str, scope: list[str]) -> dict[str, Any]:
        return {
            "facts": {
                "symbol": sym,
                "quote": {"price": 200.0},
                "profile": {"sector": "Technology"},
                "fundamentals": {"beta": 1.0, "dividend_yield": 0.01},
            },
            "missing_fields": [],
        }

    mock_data.build_facts = AsyncMock(side_effect=_mock_build_facts)
    aggregator = FactAggregator(data_service=mock_data)

    multi_facts, missing = await aggregator.aggregate_multi_facts(
        symbols=["AAPL", "MSFT", "NVDA"],
        use_case=USE_CASE_PORTFOLIO,
        amount=Decimal("60000.00"),
        risk_level="moderate",
        goal="growth",
    )

    assert multi_facts["use_case"] == "portfolio"
    assert "computed" in multi_facts
    computed = multi_facts["computed"]
    assert computed["amount"] == Decimal("60000.00")
    assert len(computed["allocations"]) == 3
    assert computed["cash_pct"] >= Decimal("10.00")
    total_w = sum(a["weight_pct"] for a in computed["allocations"]) + computed["cash_pct"]
    assert total_w == Decimal("100.00")


@pytest.mark.asyncio
async def test_fact_aggregator_single_fact_long_term() -> None:
    """验证 FactAggregator 对 long_term 用例的富化与破裂指标检查。"""
    mock_data = AsyncMock()
    mock_data.build_facts = AsyncMock(
        return_value={
            "facts": {
                "symbol": "CAT",
                "quote": {"price": 350.0},
                "profile": {"sector": "Industrials"},
                "fundamentals": {
                    "net_margin": 0.16,
                    "pe_trailing": 17.5,
                    "revenue_growth": 0.07,
                    # 缺少 debt_to_equity
                },
            },
            "missing_fields": [],
        }
    )
    aggregator = FactAggregator(data_service=mock_data)

    facts, missing = await aggregator.aggregate_facts(
        symbol="CAT",
        use_case=USE_CASE_LONG_TERM,
        years=10,
    )

    assert facts["horizon_years"] == 10
    # debt_to_equity 缺失记录在 missing_fields 中
    assert "fundamentals.debt_to_equity" in missing


@pytest.mark.asyncio
async def test_fact_aggregator_multi_facts_symbol_not_found() -> None:
    """验证多标的聚合时若有标的不存在，准确向上抛出 SymbolNotFoundError。"""
    mock_data = AsyncMock()

    async def _mock_build_facts(sym: str, scope: list[str]) -> dict[str, Any]:
        if sym == "INVALID":
            raise SymbolNotFoundError(f"Symbol '{sym}' not found")
        return {
            "facts": {"symbol": sym, "quote": {"price": 100.0}},
            "missing_fields": [],
        }

    mock_data.build_facts = AsyncMock(side_effect=_mock_build_facts)
    aggregator = FactAggregator(data_service=mock_data)

    with pytest.raises(SymbolNotFoundError):
        await aggregator.aggregate_multi_facts(
            symbols=["AAPL", "INVALID"],
            use_case=USE_CASE_COMPARE,
        )
