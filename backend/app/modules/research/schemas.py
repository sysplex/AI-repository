"""M6 AI 研究用例领域数据模型与 DTO Schemas，`CONTRACTS.md §1`。

包含：
- F2: 股票研究 (research) 请求、响应 Payload 与明细
- F3: 买入决策 (buy_decision) 请求、评估、价格区间与建议
- F6: 技术面分析 (technical) 指标解释与确定性交易计划 (trade_plan)
- F7: 财报解读 (earnings) 业绩三表、指引、管理层评估与数据缺失标准标注
- 通用输出信封 ResearchEnvelope 与佐证项 EvidenceItem
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BuyDecisionPayload",
    "BuyDecisionRequest",
    "BuyVerdict",
    "ComparePayload",
    "CompareRankingItem",
    "CompareRequest",
    "DimensionNotes",
    "EarningsAnalysisRequest",
    "EarningsAssessment",
    "EarningsMetric",
    "EarningsPayload",
    "EvidenceItem",
    "FactorAssessment",
    "FactorItem",
    "FactorRating",
    "FitByInvestorItem",
    "InvestmentHorizon",
    "LongTermHorizonYears",
    "LongTermPayload",
    "LongTermPillarItem",
    "LongTermPillars",
    "LongTermRequest",
    "LongTermVerdict",
    "MoatItem",
    "MoatStrength",
    "PillarRating",
    "PortfolioAllocationItem",
    "PortfolioGoal",
    "PortfolioPayload",
    "PortfolioRequest",
    "PricePosition",
    "ResearchEnvelope",
    "ResearchPayload",
    "ResearchRequest",
    "RevenueSourceItem",
    "RiskItem",
    "RiskLevel",
    "RiskSeverity",
    "Scenarios",
    "TechnicalAnalysisRequest",
    "TechnicalMetricExplanation",
    "TechnicalPayload",
    "ThesisBreakerItem",
    "TradePlan",
]

# =============================================================================
# 核心枚举与字面量类型
# =============================================================================

InvestmentHorizon = Literal["short", "medium", "long"]  # short: <3m, medium: 3-12m, long: >1y
RiskLevel = Literal["conservative", "moderate", "aggressive"]
BuyVerdict = Literal["buy", "wait", "avoid"]
FactorRating = Literal["favorable", "neutral", "unfavorable"]
EarningsAssessment = Literal["strong", "mixed", "weak"]
MoatStrength = Literal["strong", "moderate", "weak"]
RiskSeverity = Literal["high", "medium", "low"]
LongTermHorizonYears = Literal[5, 10, 15]
LongTermVerdict = Literal["holdable", "holdable_with_conditions", "not_recommended"]
PillarRating = Literal["strong", "moderate", "weak", "favorable", "neutral", "unfavorable"]
PortfolioGoal = Literal["growth", "income", "safety", "retirement"]


# =============================================================================
# 通用输出信封与组件
# =============================================================================


class EvidenceItem(BaseModel):
    """事实引用佐证项，用于向 `<untrusted_facts>` 回溯校验。"""

    model_config = ConfigDict(frozen=True)

    claim: str = Field(description="论断陈述")
    source_field: str = Field(description="对应 facts 中的字段路径，如 facts.valuation.pe_ttm")


class ResearchEnvelope(BaseModel):
    """所有 AI 研究用例通用输出外壳，严格符合 docs/06-ai-prompt-spec.md §2.2。"""

    model_config = ConfigDict(frozen=True)

    schema_version: str = Field(default="1.0", description="输出结构版本号")
    use_case: str = Field(description="用例代号，如 research, buy_decision, technical, earnings")
    symbol: str = Field(description="美股代码，统一大写")
    as_of: date = Field(description="数据截至日期（美东交易日）")
    summary: str = Field(description="一句话通俗结论（新手可读）")
    payload: dict[str, Any] = Field(description="用例专属字段内容")
    evidence: list[EvidenceItem] = Field(default_factory=list, description="事实佐证列表")
    data_gaps: list[str] = Field(default_factory=list, description="缺失字段或数据缺口说明")
    disclaimer: str = Field(
        default="本内容仅供研究与学习，不构成投资建议",
        description="法定投资与模拟合规免责声明",
    )


# =============================================================================
# F2: 股票研究 (research)
# =============================================================================


class RevenueSourceItem(BaseModel):
    """收入来源分解项。"""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="业务板块或产品线名称")
    share_pct: Decimal | None = Field(
        default=None,
        description="收入占比百分比（0-100），来自事实数据，无准确数据则留空",
    )
    note: str = Field(default="", description="业务说明或增速特点")


class MoatItem(BaseModel):
    """商业护城河分析项。"""

    model_config = ConfigDict(frozen=True)

    type: str = Field(description="护城河类型：如网络效应、成本优势、无形资产、转换成本")
    explanation: str = Field(description="白话详细解释")
    strength: MoatStrength = Field(description="护城河强度评级")


class RiskItem(BaseModel):
    """关键投资风险项。"""

    model_config = ConfigDict(frozen=True)

    risk: str = Field(description="风险名称或类别")
    severity: RiskSeverity = Field(description="严重等级")
    plain_explanation: str = Field(description="通俗大白话解读，无晦涩金融行话")


class Scenarios(BaseModel):
    """看涨、看跌、中立三段情景总结。"""

    model_config = ConfigDict(frozen=True)

    bull: str = Field(description="看涨情景总结（催化剂与乐观预期）")
    bear: str = Field(description="看跌情景总结（下行风险与悲观预期）")
    neutral: str = Field(description="中立/基准情景总结")


class ResearchPayload(BaseModel):
    """F2 股票研究专属 Payload（docs/06-ai-prompt-spec.md §4.1）。"""

    model_config = ConfigDict(frozen=True)

    business_model: str = Field(description="用大白话讲清楚公司怎么赚钱")
    revenue_sources: list[RevenueSourceItem] = Field(
        default_factory=list, description="主营收入来源与构成"
    )
    moats: list[MoatItem] = Field(default_factory=list, description="护城河与竞争优势分析")
    risks: list[RiskItem] = Field(default_factory=list, description="潜在关键风险")
    recent_performance: str = Field(description="近期股价与业绩表现白话总结")
    debt_and_profit: str = Field(description="负债与盈利健康度解读")
    growth_potential: str = Field(description="未来业务增长潜力与空间")
    scenarios: Scenarios = Field(description="看涨/看跌/中立情景预演")
    beginner_takeaway: list[str] = Field(
        min_length=1,
        max_length=5,
        description="给新手的 1-3 句要点大白话总结",
    )


class ResearchRequest(BaseModel):
    """F2 股票研究请求入参。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(
        min_length=1,
        max_length=16,
        description="美股代码（如 AAPL, TSLA）",
    )


# =============================================================================
# F3: 买入决策 (buy_decision)
# =============================================================================


class FactorItem(BaseModel):
    """单维度投资因子评估项。"""

    model_config = ConfigDict(frozen=True)

    rating: FactorRating = Field(description="有利/中性/不利")
    reason: str = Field(description="该维度的具体评估理由")


class FactorAssessment(BaseModel):
    """买入决策 6 维度综合因子评估体系。"""

    model_config = ConfigDict(frozen=True)

    valuation: FactorItem = Field(description="估值水平评估")
    earnings_growth: FactorItem = Field(description="盈利与业绩增长评估")
    industry_trend: FactorItem = Field(description="所处行业与赛道趋势评估")
    news: FactorItem = Field(description="近期新闻与市场情绪评估")
    analyst_view: FactorItem = Field(description="华尔街分析师评级与目标价评估")
    downside_risk: FactorItem = Field(description="下行风险与安全边际评估")


class PricePosition(BaseModel):
    """价格相对位置（由代码确定性计算，严防模型编造）。"""

    model_config = ConfigDict(frozen=True)

    target_vs_price_pct: Decimal = Field(
        description="用户想买价相对现价偏差率百分比，如 -4.20 表示想买价比现价低 4.2%"
    )
    pos_in_52w_range: Decimal = Field(
        ge=Decimal("0.0"),
        le=Decimal("1.0"),
        description="现价在 52 周最高/最低区间所处位置（0.00 ~ 1.00）",
    )
    valuation_position: str | None = Field(
        default=None,
        description="估值相对分位描述，如 '历史 3 年 45% 分位'",
    )


class BuyDecisionPayload(BaseModel):
    """F3 买入决策专属 Payload（docs/06-ai-prompt-spec.md §4.2）。"""

    model_config = ConfigDict(frozen=True)

    verdict: BuyVerdict = Field(description="核心建议：buy(买) / wait(等) / avoid(避开)")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="结论置信度（0.0 ~ 1.0），须与理由强度一致",
    )
    factor_assessment: FactorAssessment = Field(description="6 大关键因子评估明细")
    price_position: PricePosition = Field(description="想买价与 52 周相对位置（引用 computed）")
    better_entry_note: str = Field(description="更好的入场建议与触发条件说明")
    key_risks: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="关键下行风险提示（最多 5 条）",
    )
    what_would_change_view: list[str] = Field(
        min_length=1,
        description="什么情况下改变当前建议（明确触发条件）",
    )


class BuyDecisionRequest(BaseModel):
    """F3 买入决策请求入参。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=16, description="美股代码")
    target_price: Decimal = Field(gt=Decimal("0"), description="用户计划买入的目标价")
    horizon: InvestmentHorizon = Field(default="medium", description="投资持有周期预期")
    risk_level: RiskLevel = Field(default="moderate", description="用户风险承受能力")


# =============================================================================
# F6: 技术面分析 (technical)
# =============================================================================


class TechnicalMetricExplanation(BaseModel):
    """技术指标大白话解析项。"""

    model_config = ConfigDict(frozen=True)

    value: Any = Field(description="指标原始数值或状态，如数值、金叉/死叉、超买/超卖")
    plain_explanation: str = Field(description="针对新手的通俗大白话解释")


class TradePlan(BaseModel):
    """关键交易计划点位（100% 由代码确定性量化派生，AI 不得擅自篡改数值）。"""

    model_config = ConfigDict(frozen=True)

    entry: Decimal = Field(gt=Decimal("0"), description="建议入场点位")
    stop: Decimal = Field(gt=Decimal("0"), description="止损点位（必须低于入场点）")
    target: Decimal = Field(gt=Decimal("0"), description="目标止盈点位（必须高于入场点）")
    risk_reward: Decimal = Field(gt=Decimal("0"), description="盈亏比 (target-entry)/(entry-stop)")


class TechnicalPayload(BaseModel):
    """F6 技术面分析专属 Payload（docs/06-ai-prompt-spec.md §4.3）。"""

    model_config = ConfigDict(frozen=True)

    trend: TechnicalMetricExplanation = Field(description="趋势走向（均线多头/空头/震荡）")
    support_resistance: TechnicalMetricExplanation = Field(description="关键支撑位与阻力位解析")
    moving_averages: TechnicalMetricExplanation = Field(description="均线系统状态解读")
    volume: TechnicalMetricExplanation = Field(description="成交量与量价配合情况")
    rsi: TechnicalMetricExplanation = Field(description="RSI 动量与超买超卖解读")
    macd: TechnicalMetricExplanation = Field(description="MACD 柱状图与快慢线交叉解读")
    breakout: TechnicalMetricExplanation = Field(description="形态突破与通道状态解读")
    trade_plan: TradePlan = Field(description="量化交易计划（入场/止损/目标/盈亏比）")
    beginner_takeaway: list[str] = Field(
        min_length=1,
        max_length=5,
        description="给新手的核心技术面操作要点",
    )


class TechnicalAnalysisRequest(BaseModel):
    """F6 技术面分析请求入参。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=16, description="美股代码")


# =============================================================================
# F7: 财报解读 (earnings)
# =============================================================================


class EarningsMetric(BaseModel):
    """核心财报财务指标表现项。"""

    model_config = ConfigDict(frozen=True)

    actual: str | Decimal = Field(description="实际公布值（无数据时填'数据缺失'）")
    expected: str | Decimal = Field(description="华尔街市场预期值（无数据时填'数据缺失'）")
    surprise_pct: str | Decimal = Field(description="超预期幅度百分比（无数据时填'数据缺失'）")
    explanation: str = Field(description="通俗财务解读")


class EarningsPayload(BaseModel):
    """F7 财报解读专属 Payload（docs/06-ai-prompt-spec.md §4.4）。"""

    model_config = ConfigDict(frozen=True)

    revenue: EarningsMetric = Field(description="营业收入表现与解读")
    eps: EarningsMetric = Field(description="每股收益 EPS 表现与解读")
    margins: EarningsMetric = Field(description="毛利率/净利率等盈利能力变化解读")
    guidance: str = Field(description="管理层对下一季度或全年的业绩指引解读（缺失写数据缺失）")
    management_commentary: list[str] = Field(
        default_factory=list, description="管理层电话会核心观点与亮点"
    )
    market_reaction: str = Field(description="财报公布后的市场与股价即时反应")
    assessment: EarningsAssessment = Field(description="财报整体评级：strong / mixed / weak")
    short_term_outlook: str = Field(description="短期走势预期与情绪影响")
    long_term_outlook: str = Field(description="长期基本面趋势与投资逻辑影响")


class EarningsAnalysisRequest(BaseModel):
    """F7 财报解读请求入参。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=16, description="美股代码")


# =============================================================================
# F4: 股票横向对比 (compare)
# =============================================================================


class CompareRankingItem(BaseModel):
    """对比排名单项（得分与排名由代码确定性派生）。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(description="股票代码")
    rank: int = Field(ge=1, description="横向对比综合排名")
    total_score: Decimal = Field(description="代码分位计算的综合得分")
    one_line_reason: str = Field(description="核心一句话定性原因")


class DimensionNotes(BaseModel):
    """8 大维度对比定性说明。"""

    model_config = ConfigDict(frozen=True)

    growth: str = Field(description="营收与利润增长对比说明")
    margin: str = Field(description="毛利率与盈利能力对比说明")
    debt: str = Field(description="资产负债与偿债风险对比说明")
    valuation: str = Field(description="估值倍数与安全边际对比说明")
    moat: str = Field(description="护城河与竞争壁垒对比说明")
    risk: str = Field(description="下行风险与业务脆弱性对比说明")
    dividend: str = Field(description="股息分红与股东回报对比说明")
    long_term: str = Field(description="长期成长确定性对比说明")


class FitByInvestorItem(BaseModel):
    """适合与不适合投资人群画像。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(description="股票代码")
    suitable_for: list[str] = Field(default_factory=list, description="适合的投资者类型/风险偏好")
    not_suitable_for: list[str] = Field(
        default_factory=list, description="不适合的投资者类型/风险偏好"
    )


class ComparePayload(BaseModel):
    """F4 股票对比专属 Payload（docs/06-ai-prompt-spec.md §4.5）。"""

    model_config = ConfigDict(frozen=True)

    symbols: list[str] = Field(min_length=2, max_length=8, description="对比标的列表")
    ranking: list[CompareRankingItem] = Field(
        min_length=2, max_length=8, description="综合排名列表"
    )
    dimension_notes: DimensionNotes = Field(description="8 大维度对比定性分析")
    fit_by_investor: list[FitByInvestorItem] = Field(
        min_length=2, max_length=8, description="投资者画像匹配"
    )
    summary: str = Field(description="横向对比综合总结与核心结论")


class CompareRequest(BaseModel):
    """F4 股票对比请求入参（支持 2–8 只股票）。"""

    model_config = ConfigDict(frozen=True)

    symbols: list[str] = Field(min_length=2, max_length=8, description="待对比的美股代码列表")


# =============================================================================
# F5: 长期持有价值与论文破裂条件 (long_term)
# =============================================================================


class LongTermPillarItem(BaseModel):
    """长期投资价值单项支柱评估。"""

    model_config = ConfigDict(frozen=True)

    rating: PillarRating = Field(
        description="支柱评级：strong / moderate / weak 或 favorable / neutral / unfavorable"
    )
    reason: str = Field(description="支柱定性与定量依据分析")


class LongTermPillars(BaseModel):
    """7 大核心支柱评估（docs/06-ai-prompt-spec.md §4.6）。"""

    model_config = ConfigDict(frozen=True)

    moat: LongTermPillarItem = Field(description="护城河与结构性竞争优势")
    leadership: LongTermPillarItem = Field(description="管理层战略与资本配置能力")
    demand_stability: LongTermPillarItem = Field(description="产品与服务需求的长期稳定性")
    pricing_power: LongTermPillarItem = Field(description="通胀与竞争环境下的自主提价权")
    innovation: LongTermPillarItem = Field(description="技术研发与持续产品创新能力")
    financial_strength: LongTermPillarItem = Field(description="自由现金流与资产负债表韧性")
    market_size: LongTermPillarItem = Field(description="行业 TAM 增长空间与渗透潜力")


class ThesisBreakerItem(BaseModel):
    """投资论点破裂条件（供 M10 自动化持续监控）。"""

    model_config = ConfigDict(frozen=True)

    condition: str = Field(description="破裂触发情景白话描述")
    metric: str = Field(description="监控的核心指标名称，如 net_margin, pe_trailing")
    threshold: str = Field(description="触发阈值表达式，如 '< 0.15', '> 45.0'")
    data_field: str = Field(description="对应数据快照点分路径，如 fundamentals.net_margin")


class LongTermPayload(BaseModel):
    """F5 长期持有价值专属 Payload（docs/06-ai-prompt-spec.md §4.6）。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(description="股票代码")
    horizon_years: LongTermHorizonYears = Field(description="持有期限（年）：5 / 10 / 15")
    verdict: LongTermVerdict = Field(
        description="长期持有评级：holdable / holdable_with_conditions / not_recommended"
    )
    pillars: LongTermPillars = Field(description="7 大核心支柱评估结果")
    thesis: str = Field(description="长期持有论据核心阐述")
    thesis_breakers: list[ThesisBreakerItem] = Field(
        min_length=3, max_length=10, description="供 M10 持续监控的论文破裂条件列表"
    )
    summary: str = Field(description="通俗总结与长期持有展望")


class LongTermRequest(BaseModel):
    """F5 长期持有分析请求入参。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=16, description="美股代码")
    years: LongTermHorizonYears = Field(default=5, description="持有期限（年）：5 / 10 / 15")


# =============================================================================
# F8: 投资组合配置建议 (portfolio)
# =============================================================================


class PortfolioAllocationItem(BaseModel):
    """单个标的资产配置项（权重由代码确定性给出）。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(description="股票代码")
    weight_pct: Decimal = Field(description="资产配置百分比（如 25.00 代表 25%）")
    allocated_amount: Decimal = Field(description="按总金额折算的建议资金配额")
    reason: str = Field(description="配置该标的在组合中的战略定位与理由")


class PortfolioPayload(BaseModel):
    """F8 投资组合配置专属 Payload（docs/06-ai-prompt-spec.md §4.7）。"""

    model_config = ConfigDict(frozen=True)

    amount: Decimal = Field(description="可投资总金额")
    allocations: list[PortfolioAllocationItem] = Field(min_length=2, description="各标的分配明细")
    cash_pct: Decimal = Field(description="建议预留现金比例（如 10.00 代表 10%）")
    cash_amount: Decimal = Field(description="建议预留现金绝对金额")
    rationale: str = Field(description="组合整体资产配置逻辑与风格偏向")
    risk_notes: str = Field(description="组合集中度、相关性及下行对冲风险提示")
    rebalance_suggestion: str = Field(description="定期与触发式动态再平衡建议")


class PortfolioRequest(BaseModel):
    """F8 投资组合配置请求入参。"""

    model_config = ConfigDict(frozen=True)

    amount: Decimal = Field(gt=Decimal("0"), description="投资金额")
    symbols: list[str] = Field(min_length=2, max_length=12, description="候选标的池")
    risk_level: RiskLevel = Field(
        default="moderate", description="风险等级：conservative / moderate / aggressive"
    )
    goal: PortfolioGoal = Field(
        default="growth", description="投资目标：growth / income / safety / retirement"
    )
