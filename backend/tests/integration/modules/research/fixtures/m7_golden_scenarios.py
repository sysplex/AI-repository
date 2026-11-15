"""M7 黄金数据集多标的场景测试固件与 Mock 服务（T07）。

基于 5 大代表性股票标的（AAPL, CAT, KO, PLTR, SOFI），固化：
1. 横向对比矩阵场景（科技 vs 周期、防守 vs 成长、5 标的综合大比拼）；
2. 长期持有价值与破裂条件矩阵场景（5 年、10 年、15 年多年度）；
3. 投资组合优化配置场景（保守型、平衡型、激进型、养老型）；
4. 面向 M7 的 FactTracingEngine 兼容型 Mock AIService 生成器。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

from tests.integration.modules.research.fixtures.golden_stocks import (
    GOLDEN_STOCKS,
    get_golden_stock,
)

__all__ = [
    "COMPARE_SCENARIOS",
    "CompareScenario",
    "LONG_TERM_SCENARIOS",
    "LongTermScenario",
    "M7_FUNDAMENTALS_ADDITIONS",
    "PORTFOLIO_SCENARIOS",
    "PortfolioScenario",
    "build_m7_mock_data_service",
    "build_m7_mock_strategy_service",
    "generate_m7_golden_llm_response",
]

#: 补充 M7 核心量化横向对比所需的营收增速等指标（与各标的财报基本面一致）
M7_FUNDAMENTALS_ADDITIONS: dict[str, dict[str, Decimal]] = {
    "AAPL": {"revenue_growth": Decimal("0.08")},
    "CAT": {"revenue_growth": Decimal("0.04")},
    "KO": {"revenue_growth": Decimal("0.05")},
    "PLTR": {"revenue_growth": Decimal("0.30")},
    "SOFI": {"revenue_growth": Decimal("0.25")},
}


@dataclass(frozen=True)
class CompareScenario:
    """F4 股票横向对比测试场景。"""

    name: str
    symbols: list[str]
    description: str


@dataclass(frozen=True)
class LongTermScenario:
    """F5 长期持有价值测试场景。"""

    symbol: str
    years: int
    description: str


@dataclass(frozen=True)
class PortfolioScenario:
    """F8 投资组合配置优化测试场景。"""

    name: str
    amount: Decimal
    symbols: list[str]
    risk_level: str
    goal: str
    description: str


#: 1. F4 对比矩阵场景定义
COMPARE_SCENARIOS: list[CompareScenario] = [
    CompareScenario(
        name="tech_vs_cyclical",
        symbols=["AAPL", "CAT"],
        description="大盘科技龙头 vs 重工周期龙头横向对决",
    ),
    CompareScenario(
        name="defensive_vs_growth",
        symbols=["KO", "PLTR"],
        description="高分红消费防御 vs 高估值成长标的风格对决",
    ),
    CompareScenario(
        name="all_five_stocks",
        symbols=["AAPL", "CAT", "KO", "PLTR", "SOFI"],
        description="全谱系 5 大代表性标的综合大比拼与确定性排序",
    ),
]

#: 2. F5 长期持有矩阵场景定义
LONG_TERM_SCENARIOS: list[LongTermScenario] = [
    LongTermScenario(
        symbol="AAPL",
        years=5,
        description="苹果公司 5 年期长期持有价值与软硬件生态评估",
    ),
    LongTermScenario(
        symbol="KO",
        years=10,
        description="可口可乐 10 年期高分红防御价值与提价权评估",
    ),
    LongTermScenario(
        symbol="PLTR",
        years=15,
        description="Palantir 15 年期软件基础设施远期成长空间评估",
    ),
    LongTermScenario(
        symbol="CAT",
        years=10,
        description="卡特彼勒 10 年期跨越宏观周期的持有韧性评估",
    ),
    LongTermScenario(
        symbol="SOFI",
        years=5,
        description="SoFi 5 年期金融科技小盘高波动成长评估",
    ),
]

#: 3. F8 投资组合配置矩阵场景定义
PORTFOLIO_SCENARIOS: list[PortfolioScenario] = [
    PortfolioScenario(
        name="conservative",
        amount=Decimal("100000.00"),
        symbols=["AAPL", "CAT", "KO"],
        risk_level="conservative",
        goal="safety",
        description="保守型组合：高现金储备与防御型标的高配额",
    ),
    PortfolioScenario(
        name="balanced",
        amount=Decimal("50000.00"),
        symbols=["AAPL", "KO", "PLTR"],
        risk_level="moderate",
        goal="income",
        description="平衡型组合：稳健股息与适度成长兼顾",
    ),
    PortfolioScenario(
        name="aggressive",
        amount=Decimal("200000.00"),
        symbols=["AAPL", "CAT", "KO", "PLTR", "SOFI"],
        risk_level="aggressive",
        goal="growth",
        description="激进型组合：全标的高权重配置追求长期资本增值",
    ),
    PortfolioScenario(
        name="retirement",
        amount=Decimal("500000.00"),
        symbols=["AAPL", "CAT", "KO", "PLTR"],
        risk_level="conservative",
        goal="retirement",
        description="退休型大额组合：稳健资本保全与低波动",
    ),
]


def build_m7_mock_data_service() -> Any:
    """构建专用于 M7 多标的黄金测试的 Mock DataService。"""
    mock_service = AsyncMock()

    async def _build_facts(symbol: str, scope: list[str] | None = None) -> dict[str, Any]:
        sym = symbol.strip().upper()
        if sym not in GOLDEN_STOCKS:
            raise KeyError(f"Symbol '{sym}' not in golden stocks dataset")
        data = get_golden_stock(sym)

        funds = dict(data.fundamentals)
        if sym in M7_FUNDAMENTALS_ADDITIONS:
            funds.update(M7_FUNDAMENTALS_ADDITIONS[sym])

        facts: dict[str, Any] = {
            "symbol": data.symbol,
            "quote": dict(data.quote),
            "profile": dict(data.profile),
            "fundamentals": funds,
            "bars": list(data.bars),
            "earnings": dict(data.earnings_data),
            "news": [
                {
                    "title": f"{data.name} posts solid results",
                    "summary": f"Recent update for {data.symbol}",
                    "source": "Financial Wire",
                }
            ],
        }
        return {
            "facts": facts,
            "missing_fields": []
            if data.earnings_data.get("guidance") is not None
            else ["earnings.guidance"],
        }

    mock_service.build_facts.side_effect = _build_facts
    return mock_service


def build_m7_mock_strategy_service() -> Any:
    """构建专用于 M7 测试的 Mock StrategyService。"""
    mock_strategy = AsyncMock()

    class SnapshotWrapper:
        def __init__(self, data: dict[str, Any]) -> None:
            for k, v in data.items():
                setattr(self, k, v)

    async def _compute_technical_snapshot(symbol: str, as_of: Any = None) -> Any:
        sym = symbol.strip().upper()
        data = get_golden_stock(sym)
        return SnapshotWrapper(data.technical_snapshot)

    mock_strategy.compute_technical_snapshot.side_effect = _compute_technical_snapshot
    return mock_strategy


def generate_m7_golden_llm_response(
    use_case: str,
    facts: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成符合 M7 数字溯源与防编造契约的黄金大模型输出 Payload。

    质量与合规契约：
    1. 零幻觉数字：所有涉及数值均严格来自 facts / computed 或通用豁免常数；
    2. 零禁用承诺词：完全杜绝'保证保本'、'稳赚不赔'等违规表述；
    3. F4 排名与总分 100% 与 facts['computed']['ranking'] 一致；
    4. F8 资产配置与现金比例 100% 与 facts['computed']['allocations'] 一致；
    5. F5 包含 >= 3 条结构化破裂条件，路径精准指向 fundamentals。
    """
    params = params or {}
    computed = facts.get("computed", {})

    if use_case == "compare":
        symbols = facts.get("symbols", [])
        ranking = computed.get("ranking", [])
        ranking_items = [
            {
                "symbol": r["symbol"],
                "rank": r["rank"],
                "total_score": r["total_score"],
                "one_line_reason": r.get(
                    "one_line_reason",
                    f"标的综合评分排名第 {r['rank']}",
                ),
            }
            for r in ranking
        ]

        fit_by_investor = []
        for s in symbols:
            if s == "AAPL":
                fit_by_investor.append(
                    {
                        "symbol": "AAPL",
                        "suitable_for": ["稳健成长型投资者", "中长期价值持有者"],
                        "not_suitable_for": ["超高弹性短线投机者"],
                    }
                )
            elif s == "CAT":
                fit_by_investor.append(
                    {
                        "symbol": "CAT",
                        "suitable_for": ["周期行业投资者", "宏观复苏交易者"],
                        "not_suitable_for": ["极度厌恶波动者"],
                    }
                )
            elif s == "KO":
                fit_by_investor.append(
                    {
                        "symbol": "KO",
                        "suitable_for": ["防御型收息投资者", "低风险偏好者"],
                        "not_suitable_for": ["追求翻倍高弹性增长者"],
                    }
                )
            elif s == "PLTR":
                fit_by_investor.append(
                    {
                        "symbol": "PLTR",
                        "suitable_for": ["高成长风险偏好者", "科技前沿投资者"],
                        "not_suitable_for": ["保守型红利投资者"],
                    }
                )
            elif s == "SOFI":
                fit_by_investor.append(
                    {
                        "symbol": "SOFI",
                        "suitable_for": ["激进型弹性投机者", "金融科技关注者"],
                        "not_suitable_for": ["风险厌恶型退休账户"],
                    }
                )
            else:
                fit_by_investor.append(
                    {
                        "symbol": s,
                        "suitable_for": ["均衡配置型投资者"],
                        "not_suitable_for": ["单一极端风格投资者"],
                    }
                )

        first_sym = ranking[0]["symbol"] if ranking else (symbols[0] if symbols else "AAPL")

        return {
            "symbols": symbols,
            "ranking": ranking_items,
            "dimension_notes": {
                "growth": "对比各标的营收与利润增速，成长型标的高弹性扩张，周期防御偏平稳。",
                "margin": "大盘科技与高分红消费保持较高净利率，小盘与重工受阶段成本影响。",
                "debt": "各公司资产负债结构分化，轻资产软件负债率较低，重工业企业负债较高。",
                "valuation": "估值倍数呈现明显梯队分布，成长享有溢价，消费制造处于合理区间。",
                "moat": "大盘核心资产具备全球品牌与生态网络壁垒，细分龙头在特定赛道有优势。",
                "risk": "需重点防范宏观经济需求波动、利率变动以及下游市场竞争加剧的潜在风险。",
                "dividend": "防御标的提供持续稳定的股息回报与自由现金流，成长标的倾向再投资。",
                "long_term": "长期确定性取决于护城河深度与产品定价权，优质标的具备复利能力。",
            },
            "fit_by_investor": fit_by_investor,
            "summary": f"横向对比各标的综合基本面与代码量化评分，标的 {first_sym} 综合排序居首。",
        }

    if use_case == "long_term":
        sym = facts.get("symbol") or params.get("symbol") or "AAPL"
        years = facts.get("horizon_years") or params.get("years", 5)
        data = get_golden_stock(sym)
        funds = facts.get("fundamentals") or {}

        pe_val = funds.get("pe_trailing", Decimal("30.00"))
        margin_val = funds.get("net_margin", Decimal("0.20"))
        debt_val = funds.get("debt_to_equity", Decimal("1.50"))

        verdict = (
            "holdable"
            if sym in ("AAPL", "KO")
            else ("holdable_with_conditions" if sym in ("CAT", "PLTR") else "not_recommended")
        )

        thesis_breakers = [
            {
                "condition": "净利润率连续两个季度低于安全边界",
                "metric": "net_margin",
                "threshold": f"< {margin_val}",
                "data_field": "fundamentals.net_margin",
            },
            {
                "condition": "市盈率极端透支超出合理估值极值",
                "metric": "pe_trailing",
                "threshold": f"> {pe_val}",
                "data_field": "fundamentals.pe_trailing",
            },
            {
                "condition": "资产负债率恶化超出财务安全边界",
                "metric": "debt_to_equity",
                "threshold": f"> {debt_val}",
                "data_field": "fundamentals.debt_to_equity",
            },
        ]

        return {
            "symbol": sym,
            "horizon_years": years,
            "verdict": verdict,
            "pillars": {
                "moat": {
                    "rating": "strong" if sym in ("AAPL", "KO") else "favorable",
                    "reason": f"{data.name} 具备深厚的品牌与客户黏性壁垒",
                },
                "leadership": {
                    "rating": "strong",
                    "reason": "管理层资本配置能力审慎稳健，聚焦核心主业运营",
                },
                "demand_stability": {
                    "rating": "strong" if sym in ("KO", "AAPL") else "neutral",
                    "reason": "下游终端需求保持相对平稳与韧性",
                },
                "pricing_power": {
                    "rating": "strong" if sym == "KO" else "favorable",
                    "reason": "在通胀与成本上涨环境下具备自主提价能力",
                },
                "innovation": {
                    "rating": "strong" if sym in ("AAPL", "PLTR") else "moderate",
                    "reason": "持续研发投入支撑技术迭代与产品线演进",
                },
                "financial_strength": {
                    "rating": "strong" if sym in ("AAPL", "KO") else "favorable",
                    "reason": "资产负债表健康，自由现金流充沛能够抵御逆周期",
                },
                "market_size": {
                    "rating": "favorable",
                    "reason": "全球化目标可触达市场 TAM 空间充足",
                },
            },
            "thesis": f"{data.name} 凭借核心护城河与审慎资本配置，具备长期持有价值。",
            "thesis_breakers": thesis_breakers,
            "summary": f"{data.name} 在长期维度内具备稳健基本面支撑，但需持续跟踪核心破裂条件。",
        }

    if use_case == "portfolio":
        amt = computed.get("amount", Decimal("100000.00"))
        raw_allocs = computed.get("allocations", [])
        cash_pct = computed.get("cash_pct", Decimal("10.00"))
        cash_amount = computed.get("cash_amount", Decimal("10000.00"))

        allocations = [
            {
                "symbol": a["symbol"],
                "weight_pct": a["weight_pct"],
                "allocated_amount": a["allocated_amount"],
                "reason": a.get(
                    "reason",
                    f"标的 {a['symbol']} 建议配置权重 {a['weight_pct']}%",
                ),
            }
            for a in raw_allocs
        ]

        return {
            "amount": amt,
            "allocations": allocations,
            "cash_pct": cash_pct,
            "cash_amount": cash_amount,
            "rationale": "根据用户风险偏好与投资目标，采用风险平价与波动率优化算法生成配置方案。",
            "risk_notes": "组合严格遵守单标的权重上限与最低现金储备约束，分散单一标的风险暴露。",
            "rebalance_suggestion": "建议每季度定期再平衡，或当权重偏离阈值时触发动态调仓。",
        }

    raise ValueError(f"Unsupported M7 use case: {use_case}")
