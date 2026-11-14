# M6 接口契约（CONTRACTS）

> AI 用例 A：研究 / 买入决策 / 技术面 / 财报解读（research）权威接线图。每个任务严格按本契约的**签名与行为**实现。
> 对应设计：`docs/02-architecture.md§5`、`docs/04-modules.md#m6`、`docs/05-api-spec.md§2.5`、`docs/06-ai-prompt-spec.md§4`、`docs/08-test-plan.md§4.3, §5 M6`。

---

## 0. 全局与数据约定

| 项 | 约定 |
|---|---|
| 语言/版本 | Python 3.12；必须通过 `mypy app tests`（严格模式 0 错误） |
| 金额与关键数值 | `Decimal`，严禁使用 `float`（如 `target_price`, `entry`, `stop`, `target`, `risk_reward`, `target_vs_price_pct`, `pos_in_52w_range`） |
| 日期与时间 | 时间统一为带时区的 UTC `datetime`；交易日期为 `date`（美东交易日） |
| 架构分层契约 | `research` 位于应用组装与用例层（Layer 2），仅允许消费 Layer 3 的 `marketdata.service.DataService`、`strategy.service.StrategyService`、`ai.service.AIService` 及其 `schemas` 公开面 |
| 严禁跨层依赖 | 严禁直接依赖底层 ORM 模型或具体 LLM SDK，所有大模型交互由 `AIService` 统一中转 |
| 防编造铁律（F3/F6） | **技术面进场/止损/目标数值由代码计算**，买入决策想买价相对现价/52周位置**由代码计算**并置于 facts 的 `computed` 块，AI 输出必须由 `FactTracingEngine` 严格溯源比对通过 |
| 异常规范 | 统一继承 `AppError`（如 `ResearchError`, `SymbolNotFoundError`, `InsufficientDataError`） |

---

## 1. 领域模型与 DTO（`app/modules/research/schemas.py`）

```python
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

InvestmentHorizon = Literal["short", "medium", "long"]  # short: <3m, medium: 3-12m, long: >1y
RiskLevel = Literal["conservative", "moderate", "aggressive"]
BuyVerdict = Literal["buy", "wait", "avoid"]
FactorRating = Literal["favorable", "neutral", "unfavorable"]
EarningsAssessment = Literal["strong", "mixed", "weak"]
MoatStrength = Literal["strong", "moderate", "weak"]
RiskSeverity = Literal["high", "medium", "low"]

# ---------------------------------------------------------
# 通用信封与组件
# ---------------------------------------------------------
class EvidenceItem(BaseModel):
    """事实引用佐证"""
    model_config = ConfigDict(frozen=True)
    claim: str
    source_field: str

class ResearchEnvelope(BaseModel):
    """所有 AI 研究用例通用输出外壳"""
    model_config = ConfigDict(frozen=True)
    schema_version: str = "1.0"
    use_case: str
    symbol: str
    as_of: date
    summary: str
    payload: dict[str, Any]
    evidence: list[EvidenceItem] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    disclaimer: str = "本内容仅供研究与学习，不构成投资建议"

# ---------------------------------------------------------
# F2: 股票研究 (research)
# ---------------------------------------------------------
class RevenueSourceItem(BaseModel):
    name: str
    share_pct: Decimal | None = None
    note: str

class MoatItem(BaseModel):
    type: str
    explanation: str
    strength: MoatStrength

class RiskItem(BaseModel):
    risk: str
    severity: RiskSeverity
    plain_explanation: str

class Scenarios(BaseModel):
    bull: str
    bear: str
    neutral: str

class ResearchPayload(BaseModel):
    """F2 股票研究 Payload"""
    business_model: str
    revenue_sources: list[RevenueSourceItem]
    moats: list[MoatItem]
    risks: list[RiskItem]
    recent_performance: str
    debt_and_profit: str
    growth_potential: str
    scenarios: Scenarios
    beginner_takeaway: list[str] = Field(min_length=1, max_length=5)

class ResearchRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)

# ---------------------------------------------------------
# F3: 买入决策 (buy_decision)
# ---------------------------------------------------------
class FactorItem(BaseModel):
    rating: FactorRating
    reason: str

class FactorAssessment(BaseModel):
    valuation: FactorItem
    earnings_growth: FactorItem
    industry_trend: FactorItem
    news: FactorItem
    analyst_view: FactorItem
    downside_risk: FactorItem

class PricePosition(BaseModel):
    target_vs_price_pct: Decimal  # 代码计算
    pos_in_52w_range: Decimal     # 代码计算 (0.00 ~ 1.00)
    valuation_position: str | None = None

class BuyDecisionPayload(BaseModel):
    """F3 买入决策 Payload"""
    verdict: BuyVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    factor_assessment: FactorAssessment
    price_position: PricePosition
    better_entry_note: str
    key_risks: list[str] = Field(max_length=5)
    what_would_change_view: list[str] = Field(min_length=1)

class BuyDecisionRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    target_price: Decimal = Field(gt=Decimal("0"))
    horizon: InvestmentHorizon = "medium"
    risk_level: RiskLevel = "moderate"

# ---------------------------------------------------------
# F6: 技术面分析 (technical)
# ---------------------------------------------------------
class TechnicalMetricExplanation(BaseModel):
    value: Any
    plain_explanation: str

class TradePlan(BaseModel):
    """关键交易计划数值（100% 由代码确定性计算，AI 不得篡改）"""
    entry: Decimal
    stop: Decimal
    target: Decimal
    risk_reward: Decimal

class TechnicalPayload(BaseModel):
    """F6 技术面分析 Payload"""
    trend: TechnicalMetricExplanation
    support_resistance: TechnicalMetricExplanation
    moving_averages: TechnicalMetricExplanation
    volume: TechnicalMetricExplanation
    rsi: TechnicalMetricExplanation
    macd: TechnicalMetricExplanation
    breakout: TechnicalMetricExplanation
    trade_plan: TradePlan
    beginner_takeaway: list[str] = Field(min_length=1, max_length=5)

class TechnicalAnalysisRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)

# ---------------------------------------------------------
# F7: 财报解读 (earnings)
# ---------------------------------------------------------
class EarningsMetric(BaseModel):
    actual: str | Decimal
    expected: str | Decimal
    surprise_pct: str | Decimal
    explanation: str

class EarningsPayload(BaseModel):
    """F7 财报解读 Payload"""
    revenue: EarningsMetric
    eps: EarningsMetric
    margins: EarningsMetric
    guidance: str
    management_commentary: list[str]
    market_reaction: str
    assessment: EarningsAssessment
    short_term_outlook: str
    long_term_outlook: str

class EarningsAnalysisRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
```

---

## 2. 端口与协议定义（`app/modules/research/ports.py`）

```python
from typing import Any, Protocol
from uuid import UUID
from app.modules.ai.schemas import AnalysisReport
from app.modules.research.schemas import (
    BuyDecisionRequest,
    EarningsAnalysisRequest,
    ResearchRequest,
    TechnicalAnalysisRequest,
)

class ResearchServiceProtocol(Protocol):
    """研究用例对外服务门面协议"""

    async def get_stock_research(
        self, request: ResearchRequest, user_id: UUID
    ) -> AnalysisReport: ...

    async def get_buy_decision(
        self, request: BuyDecisionRequest, user_id: UUID
    ) -> AnalysisReport: ...

    async def get_technical_analysis(
        self, request: TechnicalAnalysisRequest, user_id: UUID
    ) -> AnalysisReport: ...

    async def get_earnings_analysis(
        self, request: EarningsAnalysisRequest, user_id: UUID
    ) -> AnalysisReport: ...

class FactAggregatorProtocol(Protocol):
    """多源事实聚合器协议"""

    async def aggregate_facts(
        self, symbol: str, use_case: str
    ) -> tuple[dict[str, Any], list[str]]:
        """收集指定用例的基础事实，并返回 (facts_dict, missing_fields)"""
        ...

class QuantitativeEngineProtocol(Protocol):
    """代码量化计算派生引擎协议（防编造基础）"""

    def compute_buy_decision_metrics(
        self,
        current_price: Decimal,
        target_price: Decimal,
        low_52w: Decimal,
        high_52w: Decimal,
    ) -> dict[str, Any]: ...

    def compute_technical_trade_plan(
        self,
        current_price: Decimal,
        support: Decimal,
        resistance: Decimal,
        atr: Decimal,
    ) -> dict[str, Any]: ...
```

---

## 3. 代码量化派生引擎计算契约（`app/modules/research/quantitative.py`）

1. **想买价相对现价偏差率 (`target_vs_price_pct`)**：
   $$\text{target\_vs\_price\_pct} = \frac{\text{target\_price} - \text{current\_price}}{\text{current\_price}} \times 100$$
   保留 2 位小数 `Decimal`。

2. **52周区间位置百分比 (`pos_in_52w_range`)**：
   $$\text{pos\_in\_52w\_range} = \frac{\text{current\_price} - \text{low\_52w}}{\text{high\_52w} - \text{low\_52w}}$$
   边界保护：若 $\text{high\_52w} = \text{low\_52w}$，返回 `Decimal("0.50")`；结果 clamp 在 `[0.00, 1.00]`。

3. **确定性交易计划生成 (`trade_plan`)**：
   - 入场位 `entry = current_price`
   - 止损位 `stop = max(support * Decimal("0.98"), entry - atr * Decimal("1.5"))`，且确保 `stop < entry`
   - 目标位 `target = min(resistance, entry + atr * Decimal("3.0"))`，且确保 `target > entry`
   - 风险回报比 `risk_reward = (target - entry) / (entry - stop)`，保留 2 位小数。

---

## 4. 提示词与输出 Schema 契约（`app/modules/research/prompts.py`）

向 M5 `default_prompt_registry` 注册 4 个标准模板：
1. `research_v1.0`：输出符合 `ResearchPayload` JSON Schema；
2. `buy_decision_v1.0`：输出符合 `BuyDecisionPayload` JSON Schema；
3. `technical_v1.0`：输出符合 `TechnicalPayload` JSON Schema；
4. `earnings_v1.0`：输出符合 `EarningsPayload` JSON Schema。

每个模板的 `system_template` 必须包含：
- 语言设置：中文、通俗、新手友好。
- 严禁承诺：禁止使用“保本”、“稳赚”、“零风险”等虚假宣传词汇。
- 数字溯源约束：所有具体数值与交易计划必须严格引用 `<untrusted_facts>` 中的 `computed` 或 `facts` 字段。

---

## 5. 新手可读性与合规安全防线（`app/modules/research/compliance.py`）

1. **免责声明强制追加**：所有输出信封必须带 `disclaimer: "本内容仅供研究与学习，不构成投资建议"`。
2. **术语通俗度检查**：确保出现的金融术语（PE, PB, RSI, MACD, Moat, ATR 等）在 payload 的 `plain_explanation` 或 `beginner_takeaway` 中具备大白话解释。
3. **数据缺失合规**：财报中无指引或缺失字段，显式输出 `"数据缺失"`，严禁空缺或猜测填补。

---

## 6. REST API 端点契约（`app/modules/research/api.py`）

挂载于 `/api/v1/ai`（或通过 `api_router` 挂载）：

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| `POST` | `/api/v1/ai/research` | JWT `current_user` | 股票综合研究报告（F2） |
| `POST` | `/api/v1/ai/buy-decision` | JWT `current_user` | 买入决策评估（F3，含买/等/避开） |
| `POST` | `/api/v1/ai/technical` | JWT `current_user` | 技术面通俗分析与交易计划（F6） |
| `POST` | `/api/v1/ai/earnings` | JWT `current_user` | 最新财报解读与指引分析（F7） |

错误码约定：
- `400`：输入格式无效（非正价格、无效周期/风险等级）。
- `404`：股票代码不存在或无法获取基础数据。
- `422`：数据严重不足以完成分析。
- `429`：AI 配额耗尽。
- `503`：全局预算熔断或 LLM 适配器故障。

---

## 7. 质量门禁与测试验收要求

1. **测试覆盖率**：`tests/unit/modules/research/` 与 `tests/integration/modules/research/` 覆盖率 $\ge 90.0\%$，全局 $\ge 80.0\%$。
2. **黄金集覆盖矩阵**：5 只代表性标的（大盘科技 `AAPL`、周期 `CAT`、高分红 `KO`、亏损成长 `PLTR`、小盘 `SOFI`）× 4 个用例 = 20 个完整测试场景通过率 100%。
3. **架构静态检查**：`lint-imports` 5 契约全部保留；`mypy app tests` 0 错误；`ruff check` 0 警告。
