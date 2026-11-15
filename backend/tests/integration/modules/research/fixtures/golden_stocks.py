"""Golden dataset static fixtures for 5 representative stocks across 4 use cases (M6 / T07).

Representative Stock Matrix:
1. AAPL: Large-cap tech (大盘科技) - Solid cash flow, hardware/services ecosystem.
2. CAT: Cyclical industrial (周期重工) - Heavy machinery, capex-sensitive.
3. KO: High dividend / defensive (高分红消费防御) - Stable dividend yield (~3.1%), low beta.
4. PLTR: High valuation growth (高估值成长股) - High revenue growth, premium valuation.
5. SOFI: Small-cap / high volatility (小盘高波动金融科技) - Missing earnings guidance scenario.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock


@dataclass(frozen=True)
class GoldenStockData:
    symbol: str
    name: str
    stock_type: str
    quote: dict[str, Any]
    profile: dict[str, Any]
    fundamentals: dict[str, Any]
    technical_snapshot: dict[str, Any]
    earnings_data: dict[str, Any]
    target_price: Decimal
    bars: list[dict[str, Any]] = field(default_factory=list)


# -----------------------------------------------------------------------------
# 1. AAPL: 大盘科技 (Large-cap Tech)
# -----------------------------------------------------------------------------
AAPL_DATA = GoldenStockData(
    symbol="AAPL",
    name="Apple Inc.",
    stock_type="large_cap_tech",
    quote={
        "price": Decimal("225.00"),
        "change": Decimal("1.50"),
        "change_pct": Decimal("0.67"),
        "volume": 54321000,
        "high_52w": Decimal("237.23"),
        "low_52w": Decimal("164.08"),
        "open": Decimal("223.50"),
        "previous_close": Decimal("223.50"),
        "as_of": "2026-11-10T20:00:00Z",
    },
    profile={
        "name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "description": "Apple designs and markets smartphones, personal computers, and services.",
        "country": "US",
        "employees": 161000,
    },
    fundamentals={
        "pe_trailing": Decimal("34.20"),
        "pe_forward": Decimal("28.50"),
        "pb": Decimal("48.60"),
        "ps": Decimal("8.70"),
        "net_margin": Decimal("0.24"),
        "roe": Decimal("1.52"),
        "debt_to_equity": Decimal("1.87"),
        "market_cap": Decimal("3400000000000"),
        "dividend_yield": Decimal("0.005"),
        "beta": Decimal("1.08"),
    },
    technical_snapshot={
        "support": Decimal("215.00"),
        "resistance": Decimal("235.00"),
        "atr_14": Decimal("4.50"),
        "rsi_14": Decimal("58.20"),
        "sma_20": Decimal("220.50"),
        "sma_50": Decimal("216.00"),
        "sma_200": Decimal("195.00"),
        "macd": Decimal("2.10"),
    },
    earnings_data={
        "revenue": "94.93B",
        "eps": "1.64",
        "margins": "24.0%",
        "guidance": "Expected 5% to 10% revenue growth next quarter",
        "management_commentary": [
            "服务业务营收创下历史新高",
            "活跃设备生态基础持续扩大突破 20 亿台",
        ],
    },
    target_price=Decimal("220.00"),
    bars=[
        {
            "open": Decimal("220.00"),
            "high": Decimal("237.23"),
            "low": Decimal("164.08"),
            "close": Decimal("225.00"),
            "volume": 50000000,
        }
    ],
)


# -----------------------------------------------------------------------------
# 2. CAT: 周期重工 (Cyclical Industrial)
# -----------------------------------------------------------------------------
CAT_DATA = GoldenStockData(
    symbol="CAT",
    name="Caterpillar Inc.",
    stock_type="cyclical",
    quote={
        "price": Decimal("380.00"),
        "change": Decimal("-2.50"),
        "change_pct": Decimal("-0.65"),
        "volume": 2840000,
        "high_52w": Decimal("418.00"),
        "low_52w": Decimal("224.00"),
        "open": Decimal("382.00"),
        "previous_close": Decimal("382.50"),
        "as_of": "2026-11-10T20:00:00Z",
    },
    profile={
        "name": "Caterpillar Inc.",
        "sector": "Industrials",
        "industry": "Farm & Heavy Construction Machinery",
        "description": "Leading manufacturer of construction and mining equipment.",
        "country": "US",
        "employees": 113000,
    },
    fundamentals={
        "pe_trailing": Decimal("17.80"),
        "pe_forward": Decimal("16.50"),
        "pb": Decimal("8.20"),
        "ps": Decimal("2.80"),
        "net_margin": Decimal("0.16"),
        "roe": Decimal("0.55"),
        "debt_to_equity": Decimal("2.10"),
        "market_cap": Decimal("185000000000"),
        "dividend_yield": Decimal("0.015"),
        "beta": Decimal("1.25"),
    },
    technical_snapshot={
        "support": Decimal("360.00"),
        "resistance": Decimal("400.00"),
        "atr_14": Decimal("8.20"),
        "rsi_14": Decimal("48.50"),
        "sma_20": Decimal("375.00"),
        "sma_50": Decimal("368.00"),
        "sma_200": Decimal("340.00"),
        "macd": Decimal("0.85"),
    },
    earnings_data={
        "revenue": "16.11B",
        "eps": "5.17",
        "margins": "16.0%",
        "guidance": "Full-year dealer inventory normalization expected",
        "management_commentary": [
            "Mining equipment sales discipline held firm",
            "Construction machinery experienced geographic divergence",
        ],
    },
    target_price=Decimal("365.00"),
    bars=[
        {
            "open": Decimal("370.00"),
            "high": Decimal("418.00"),
            "low": Decimal("224.00"),
            "close": Decimal("380.00"),
            "volume": 3000000,
        }
    ],
)


# -----------------------------------------------------------------------------
# 3. KO: 高分红消费防御 (High Dividend / Defensive)
# -----------------------------------------------------------------------------
KO_DATA = GoldenStockData(
    symbol="KO",
    name="The Coca-Cola Company",
    stock_type="high_dividend",
    quote={
        "price": Decimal("65.00"),
        "change": Decimal("0.20"),
        "change_pct": Decimal("0.31"),
        "volume": 14200000,
        "high_52w": Decimal("73.50"),
        "low_52w": Decimal("57.00"),
        "open": Decimal("64.80"),
        "previous_close": Decimal("64.80"),
        "as_of": "2026-11-10T20:00:00Z",
    },
    profile={
        "name": "The Coca-Cola Company",
        "sector": "Consumer Defensive",
        "industry": "Beverages - Non-Alcoholic",
        "description": "Manufactures and sells non-alcoholic beverages worldwide.",
        "country": "US",
        "employees": 79100,
    },
    fundamentals={
        "pe_trailing": Decimal("25.40"),
        "pe_forward": Decimal("22.10"),
        "pb": Decimal("10.50"),
        "ps": Decimal("6.10"),
        "net_margin": Decimal("0.23"),
        "roe": Decimal("0.41"),
        "debt_to_equity": Decimal("1.45"),
        "market_cap": Decimal("280000000000"),
        "dividend_yield": Decimal("0.031"),
        "beta": Decimal("0.55"),
    },
    technical_snapshot={
        "support": Decimal("62.50"),
        "resistance": Decimal("68.00"),
        "atr_14": Decimal("0.95"),
        "rsi_14": Decimal("52.00"),
        "sma_20": Decimal("64.20"),
        "sma_50": Decimal("64.80"),
        "sma_200": Decimal("62.00"),
        "macd": Decimal("0.12"),
    },
    earnings_data={
        "revenue": "11.95B",
        "eps": "0.77",
        "margins": "23.0%",
        "guidance": "Full-year organic revenue growth of 5% to 10%",
        "management_commentary": [
            "Price and product mix drove 10% gain",
            "Unit volume rose 1% in international markets",
        ],
    },
    target_price=Decimal("63.00"),
    bars=[
        {
            "open": Decimal("64.00"),
            "high": Decimal("73.50"),
            "low": Decimal("57.00"),
            "close": Decimal("65.00"),
            "volume": 15000000,
        }
    ],
)


# -----------------------------------------------------------------------------
# 4. PLTR: 亏损成长/高估值高成长 (High Growth / High Valuation)
# -----------------------------------------------------------------------------
PLTR_DATA = GoldenStockData(
    symbol="PLTR",
    name="Palantir Technologies Inc.",
    stock_type="growth",
    quote={
        "price": Decimal("60.00"),
        "change": Decimal("3.20"),
        "change_pct": Decimal("5.63"),
        "volume": 78200000,
        "high_52w": Decimal("66.00"),
        "low_52w": Decimal("19.50"),
        "open": Decimal("58.00"),
        "previous_close": Decimal("56.80"),
        "as_of": "2026-11-10T20:00:00Z",
    },
    profile={
        "name": "Palantir Technologies Inc.",
        "sector": "Technology",
        "industry": "Software - Infrastructure",
        "description": "Builds software platforms for enterprise big data and AI operations.",
        "country": "US",
        "employees": 3800,
    },
    fundamentals={
        "pe_trailing": Decimal("115.00"),
        "pe_forward": Decimal("85.00"),
        "pb": Decimal("28.00"),
        "ps": Decimal("45.00"),
        "net_margin": Decimal("0.18"),
        "roe": Decimal("0.12"),
        "debt_to_equity": Decimal("0.05"),
        "market_cap": Decimal("135000000000"),
        "dividend_yield": Decimal("0.000"),
        "beta": Decimal("1.85"),
    },
    technical_snapshot={
        "support": Decimal("54.00"),
        "resistance": Decimal("65.00"),
        "atr_14": Decimal("2.80"),
        "rsi_14": Decimal("64.50"),
        "sma_20": Decimal("58.00"),
        "sma_50": Decimal("52.00"),
        "sma_200": Decimal("36.00"),
        "macd": Decimal("1.45"),
    },
    earnings_data={
        "revenue": "725.5M",
        "eps": "0.10",
        "margins": "18.0%",
        "guidance": "US commercial revenue expected to grow over 50%",
        "management_commentary": [
            "AIP bootcamps driving customer expansion",
            "Closed multiple deals above 1 million dollars each",
        ],
    },
    target_price=Decimal("55.00"),
    bars=[
        {
            "open": Decimal("55.00"),
            "high": Decimal("66.00"),
            "low": Decimal("19.50"),
            "close": Decimal("60.00"),
            "volume": 75000000,
        }
    ],
)


# -----------------------------------------------------------------------------
# 5. SOFI: 小盘金融科技高波动，含指引缺失场景 (Small-cap / High Volatility / Missing Guidance)
# -----------------------------------------------------------------------------
SOFI_DATA = GoldenStockData(
    symbol="SOFI",
    name="SoFi Technologies, Inc.",
    stock_type="small_cap",
    quote={
        "price": Decimal("14.50"),
        "change": Decimal("-0.40"),
        "change_pct": Decimal("-2.68"),
        "volume": 42100000,
        "high_52w": Decimal("16.80"),
        "low_52w": Decimal("6.40"),
        "open": Decimal("14.90"),
        "previous_close": Decimal("14.90"),
        "as_of": "2026-11-10T20:00:00Z",
    },
    profile={
        "name": "SoFi Technologies, Inc.",
        "sector": "Financial Services",
        "industry": "Credit Services",
        "description": "Provides digital financial and lending services.",
        "country": "US",
        "employees": 4400,
    },
    fundamentals={
        "pe_trailing": Decimal("45.00"),
        "pe_forward": Decimal("26.00"),
        "pb": Decimal("2.40"),
        "ps": Decimal("5.20"),
        "net_margin": Decimal("0.08"),
        "roe": Decimal("0.05"),
        "debt_to_equity": Decimal("0.85"),
        "market_cap": Decimal("15000000000"),
        "dividend_yield": Decimal("0.000"),
        "beta": Decimal("2.10"),
    },
    technical_snapshot={
        "support": Decimal("12.80"),
        "resistance": Decimal("16.00"),
        "atr_14": Decimal("0.75"),
        "rsi_14": Decimal("46.00"),
        "sma_20": Decimal("14.10"),
        "sma_50": Decimal("13.50"),
        "sma_200": Decimal("9.80"),
        "macd": Decimal("-0.15"),
    },
    earnings_data={
        "revenue": "697.1M",
        "eps": "0.05",
        "margins": "8.0%",
        "guidance": None,  # 测试财报指引缺失场景
        "management_commentary": [
            "Added new members reaching new record in the quarter",
            "Financial Services segment revenue surged over 100%",
        ],
    },
    target_price=Decimal("13.00"),
    bars=[
        {
            "open": Decimal("14.00"),
            "high": Decimal("16.80"),
            "low": Decimal("6.40"),
            "close": Decimal("14.50"),
            "volume": 40000000,
        }
    ],
)


GOLDEN_STOCKS: dict[str, GoldenStockData] = {
    "AAPL": AAPL_DATA,
    "CAT": CAT_DATA,
    "KO": KO_DATA,
    "PLTR": PLTR_DATA,
    "SOFI": SOFI_DATA,
}


def list_golden_symbols() -> list[str]:
    """获取黄金数据集 5 只股票代码。"""
    return list(GOLDEN_STOCKS.keys())


def get_golden_stock(symbol: str) -> GoldenStockData:
    """获取指定股票代码的静态快照数据。"""
    sym = symbol.strip().upper()
    if sym not in GOLDEN_STOCKS:
        raise KeyError(f"Symbol '{sym}' not in golden stocks dataset")
    return GOLDEN_STOCKS[sym]


def build_mock_data_service() -> Any:
    """构建用于黄金集测试的 Mock DataService。"""
    mock_service = AsyncMock()

    async def _build_facts(symbol: str, scope: list[str] | None = None) -> dict[str, Any]:
        data = get_golden_stock(symbol)
        facts: dict[str, Any] = {
            "symbol": data.symbol,
            "quote": dict(data.quote),
            "profile": dict(data.profile),
            "fundamentals": dict(data.fundamentals),
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


def build_mock_strategy_service() -> Any:
    """构建用于黄金集测试的 Mock StrategyService。"""
    mock_strategy = AsyncMock()

    class SnapshotWrapper:
        def __init__(self, data: dict[str, Any]) -> None:
            for k, v in data.items():
                setattr(self, k, v)

    async def _compute_technical_snapshot(symbol: str, as_of: Any = None) -> Any:
        data = get_golden_stock(symbol)
        return SnapshotWrapper(data.technical_snapshot)

    mock_strategy.compute_technical_snapshot.side_effect = _compute_technical_snapshot
    return mock_strategy


def generate_golden_llm_response(
    symbol: str,
    use_case: str,
    facts: dict[str, Any],
) -> dict[str, Any]:
    """生成符合数字溯源与 Schema 约束的黄金集大模型输出。

    必须满足：
    1. 所有具体数值（除了豁免常数）均严格来自 facts / computed；
    2. 无任何禁用违规词汇；
    3. F6 技术面进场/止损/目标/盈亏比与 facts['computed']['trade_plan'] 100% 绝对一致；
    4. F3 买入决策想买价偏差与 52 周位置与 facts['computed'] 100% 绝对一致；
    5. F7 指引若缺失则输出'数据缺失'。
    """
    data = get_golden_stock(symbol)
    computed = facts.get("computed", {})

    if use_case == "research":
        return {
            "business_model": f"{data.name} 核心商业模式稳固，涵盖软硬件与行业服务生态。",
            "revenue_sources": [
                {
                    "name": "核心主力产品与服务",
                    "share_pct": Decimal("50.00"),
                    "note": "稳固的收入支柱",
                },
                {"name": "创新增长业务", "share_pct": Decimal("50.00"), "note": "高增速引擎"},
            ],
            "moats": [
                {
                    "type": "品牌壁垒",
                    "explanation": f"{data.name} 拥有深厚的品牌认可度与高转换成本",
                    "strength": "strong",
                },
                {
                    "type": "分销网络",
                    "explanation": "全球销售渠道网络健全且难以替代",
                    "strength": "moderate",
                },
            ],
            "risks": [
                {
                    "risk": "宏观经济波动",
                    "severity": "medium",
                    "plain_explanation": "全球经济放缓可能对需求构成阶段性压力",
                },
                {
                    "risk": "行业竞争加剧",
                    "severity": "low",
                    "plain_explanation": "同行业对手加大投入可能影响边际增速",
                },
            ],
            "recent_performance": "近期业务稳健运行，各项关键财务指标保持健康。",
            "debt_and_profit": "资产负债率可控，利润率处于合理偏上区间。",
            "growth_potential": "新业务探索与国际市场渗透持续注入中长期增长动能。",
            "scenarios": {
                "bull": "宏观回暖与新品超预期爆发带动估值中枢上移",
                "bear": "供应链成本上升或下游需求走弱压制盈利释放",
                "neutral": "基本面按既定规划平稳推进，业绩平稳增长",
            },
            "beginner_takeaway": [
                f"{data.name} 属于行业成熟标的，基本面健康。",
                "适合中长期投资者结合估值回调节奏分批布局。",
            ],
        }

    if use_case == "buy_decision":
        target_vs_price = computed.get("target_vs_price_pct", Decimal("0.00"))
        pos_in_52w = computed.get("pos_in_52w_range", Decimal("0.50"))
        verdict = "buy" if target_vs_price <= Decimal("0") else "wait"

        return {
            "verdict": verdict,
            "confidence": 1.0,
            "factor_assessment": {
                "valuation": {"rating": "favorable", "reason": "估值水平与历史均值相比具备性价比"},
                "earnings_growth": {"rating": "favorable", "reason": "利润增长稳健，现金流充沛"},
                "industry_trend": {"rating": "neutral", "reason": "行业处于成熟景气周期"},
                "news": {"rating": "neutral", "reason": "近期无重大负面事件"},
                "analyst_view": {"rating": "favorable", "reason": "多数卖方维持买入或增持评级"},
                "downside_risk": {
                    "rating": "favorable",
                    "reason": "资产负债表健康，下行防御边际充足",
                },
            },
            "price_position": {
                "target_vs_price_pct": target_vs_price,
                "pos_in_52w_range": pos_in_52w,
                "valuation_position": "处于合理估值区间",
            },
            "better_entry_note": "若价格回调至支撑位附近，将提供更优的风险收益比",
            "key_risks": ["宏观利率变动风险", "行业竞争压力"],
            "what_would_change_view": ["核心业务营收连续两季出现下滑", "净利润率大幅收窄超过 20%"],
        }

    if use_case == "technical":
        tp = computed.get("trade_plan", {})
        return {
            "trend": {
                "value": "bullish",
                "plain_explanation": "主要均线保持良性多头排列，中期趋势良好",
            },
            "support_resistance": {
                "value": "支撑位与阻力位明确",
                "plain_explanation": "关键支撑位与阻力位区间结构完整",
            },
            "moving_averages": {
                "value": "MA20 > MA50",
                "plain_explanation": "短期均线位于中期均线上方",
            },
            "volume": {"value": "正常量能", "plain_explanation": "换手率与量能配合温和"},
            "rsi": {
                "value": Decimal("50.0"),
                "plain_explanation": "RSI处于中性健康水平，未出现超买",
            },
            "macd": {"value": "金叉形态", "plain_explanation": "MACD柱状线处于零轴上方"},
            "breakout": {
                "value": "区间整理",
                "plain_explanation": "价格运行于关键箱体内部，等待方向选择",
            },
            "trade_plan": {
                "entry": tp.get("entry", data.quote["price"]),
                "stop": tp.get("stop", data.quote["price"] * Decimal("0.95")),
                "target": tp.get("target", data.quote["price"] * Decimal("1.05")),
                "risk_reward": tp.get("risk_reward", Decimal("2.00")),
            },
            "beginner_takeaway": [
                "技术结构处于健康上升通道中，可逢回调观察企稳机会。",
                "切忌追高，严格按照交易计划执行止损纪律。",
            ],
        }

    if use_case == "earnings":
        ed = data.earnings_data
        guidance_text = ed.get("guidance") if ed.get("guidance") is not None else "数据缺失"
        return {
            "revenue": {
                "actual": ed.get("revenue", "数据缺失"),
                "expected": ed.get("revenue", "数据缺失"),
                "surprise_pct": "0.0%",
                "explanation": "季度营收保持平稳，符合市场先前预期",
            },
            "eps": {
                "actual": ed.get("eps", "数据缺失"),
                "expected": ed.get("eps", "数据缺失"),
                "surprise_pct": "0.0%",
                "explanation": "每股收益表现稳健，盈利质量符合预期",
            },
            "margins": {
                "actual": ed.get("margins", "数据缺失"),
                "expected": ed.get("margins", "数据缺失"),
                "surprise_pct": "0.0%",
                "explanation": "营业利润率维持在历史合理中位数水平",
            },
            "guidance": guidance_text,
            "management_commentary": ed.get(
                "management_commentary", ["管理层维持既定稳健运营战略"]
            ),
            "market_reaction": "业绩发布后股价波动平稳，市场反应理性",
            "assessment": "strong" if ed.get("guidance") is not None else "mixed",
            "short_term_outlook": "短期市场情绪偏稳健，关注后续订单交付进度",
            "long_term_outlook": "长期护城河与竞争优势持续稳固",
        }

    raise ValueError(f"Unknown use case: {use_case}")
