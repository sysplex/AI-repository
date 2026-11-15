# M7 接口契约（CONTRACTS）

> AI 用例 B：股票对比 / 长期持有 / 投资组合配置（research）权威接线图。每个任务严格按本契约的**签名与行为**实现。
> 对应设计：`docs/02-architecture.md§5`、`docs/04-modules.md#m7`、`docs/05-api-spec.md§2.5`、`docs/06-ai-prompt-spec.md§4`、`docs/08-test-plan.md§4.3, §5 M7`。

---

## 0. 全局与数据约定

| 项 | 约定 |
|---|---|
| 语言/版本 | Python 3.12；必须通过 `mypy app tests`（严格模式 0 错误） |
| 金额与关键数值 | 核心数值严格采用 `Decimal`，严禁使用 `float`（如权重比率 `weight_pct`、现金比率 `cash_pct`、投资金额 `amount`、各维度指标与分位得分） |
| 架构分层契约 | `research` 位于应用组装与用例能力层（Layer 2），仅允许消费 Layer 3 的 `marketdata.service.DataService`、`strategy.service.StrategyService`、`ai.service.AIService` 及其 `schemas` 公开面 |
| 严禁跨层依赖 | 严禁直接依赖底层 ORM 实体或第三方 LLM SDK，所有大模型交互由 `AIService` 统一中转 |
| 防编造铁律（F4/F8） | **股票对比的各维度分位得分与综合排名 100% 由代码计算**，AI 不得自行打分；**投资组合权重配比（含现金比例）100% 由代码算法优化**，AI 仅解释配置思路与风险，严禁自行篡改数字；输出必须由 `FactTracingEngine` 严格溯源比对通过 |
| 长期破裂条件（F5） | `thesis_breakers` 必须具备可监控性，每条须提供结构化字段：`condition`（通俗描述）、`metric`（指标名）、`threshold`（触发阈值表达式）、`data_field`（对应数据源路径，供 M10 自动化监控轮询） |
| 组合守恒不变量 | 组合各标的 `weight_pct` 与 `cash_pct` 之和必须严格恒等于 `100.00%`（误差 $\le 0.01\%$），且严格遵守单股上限与现金下限约束 |

---

## 1. 领域模型与 DTO（`app/modules/research/schemas.py` 增量）

```python
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

LongTermHorizonYears = Literal[5, 10, 15]
LongTermVerdict = Literal["holdable", "holdable_with_conditions", "not_recommended"]
PillarRating = Literal["strong", "moderate", "weak", "favorable", "neutral", "unfavorable"]
PortfolioGoal = Literal["growth", "income", "safety", "retirement"]

# ---------------------------------------------------------
# F4: 股票横向对比 (compare)
# ---------------------------------------------------------
class CompareRankingItem(BaseModel):
    """对比排名单项（总分来自代码派生）"""
    model_config = ConfigDict(frozen=True)
    symbol: str
    rank: int = Field(ge=1)
    total_score: Decimal = Field(description="代码分位计算的总分")
    one_line_reason: str = Field(description="核心一句话定性原因")

class DimensionNotes(BaseModel):
    """8 大维度对比定性说明"""
    model_config = ConfigDict(frozen=True)
    growth: str
    margin: str
    debt: str
    valuation: str
    moat: str
    risk: str
    dividend: str
    long_term: str

class FitByInvestorItem(BaseModel):
    """适合与不适合投资人群画像"""
    model_config = ConfigDict(frozen=True)
    symbol: str
    suitable_for: list[str] = Field(default_factory=list)
    not_suitable_for: list[str] = Field(default_factory=list)

class ComparePayload(BaseModel):
    """F4 股票对比 Payload"""
    symbols: list[str] = Field(min_length=2, max_length=8)
    ranking: list[CompareRankingItem]
    dimension_notes: DimensionNotes
    fit_by_investor: list[FitByInvestorItem]
    summary: str

class CompareRequest(BaseModel):
    symbols: list[str] = Field(min_length=2, max_length=8)

# ---------------------------------------------------------
# F5: 长期持有价值与论文破裂条件 (long_term)
# ---------------------------------------------------------
class LongTermPillarItem(BaseModel):
    """长期 7 大支柱评估单项"""
    model_config = ConfigDict(frozen=True)
    rating: PillarRating
    reason: str

class LongTermPillars(BaseModel):
    """7 大核心支柱评估"""
    model_config = ConfigDict(frozen=True)
    moat: LongTermPillarItem
    leadership: LongTermPillarItem
    demand_stability: LongTermPillarItem
    pricing_power: LongTermPillarItem
    innovation: LongTermPillarItem
    financial_strength: LongTermPillarItem
    market_size: LongTermPillarItem

class ThesisBreakerItem(BaseModel):
    """论文破裂条件（供 M10 自动化持续监控）"""
    model_config = ConfigDict(frozen=True)
    condition: str = Field(description="破裂触发情景白话描述")
    metric: str = Field(description="监控的核心指标名称，如 net_margin, pe_trailing")
    threshold: str = Field(description="触发阈值表达式，如 '< 0.15', '> 45.0'")
    data_field: str = Field(description="对应数据快照点分路径，如 fundamentals.net_margin")

class LongTermPayload(BaseModel):
    """F5 长期持有价值 Payload"""
    symbol: str
    horizon_years: LongTermHorizonYears
    verdict: LongTermVerdict
    pillars: LongTermPillars
    thesis: str = Field(description="长期持有论据核心阐述")
    thesis_breakers: list[ThesisBreakerItem] = Field(min_length=3, max_length=10)
    summary: str

class LongTermRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    years: LongTermHorizonYears = 5

# ---------------------------------------------------------
# F8: 投资组合配置建议 (portfolio)
# ---------------------------------------------------------
class PortfolioAllocationItem(BaseModel):
    """单个标的资产配置（权重由代码确定性给出）"""
    model_config = ConfigDict(frozen=True)
    symbol: str
    weight_pct: Decimal = Field(description="资产配置百分比，如 Decimal('25.00')")
    allocated_amount: Decimal = Field(description="按总金额折算的建议资金")
    reason: str = Field(description="配置该标的在组合中的战略定位与理由")

class PortfolioPayload(BaseModel):
    """F8 投资组合配置 Payload"""
    amount: Decimal = Field(description="可投资总金额")
    allocations: list[PortfolioAllocationItem]
    cash_pct: Decimal = Field(description="建议预留现金比例")
    cash_amount: Decimal = Field(description="建议预留现金绝对金额")
    rationale: str = Field(description="组合整体资产配置逻辑与风格偏向")
    risk_notes: str = Field(description="组合集中度、相关性及下行对冲风险提示")
    rebalance_suggestion: str = Field(description="定期与触发式动态再平衡建议")

class PortfolioRequest(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"), description="投资金额")
    symbols: list[str] = Field(min_length=2, max_length=12, description="候选标的池")
    risk_level: Literal["conservative", "moderate", "aggressive"] = "moderate"
    goal: PortfolioGoal = "growth"
```

---

## 2. 核心编排服务协议扩展（`ResearchServiceProtocol`）

```python
class ResearchServiceProtocol(Protocol):
    # --- M6 原有能力 ---
    async def get_stock_research(self, request: ResearchRequest, user_id: UUID | None = None) -> ResearchEnvelope: ...
    async def get_buy_decision(self, request: BuyDecisionRequest, user_id: UUID | None = None) -> ResearchEnvelope: ...
    async def get_technical_analysis(self, request: TechnicalAnalysisRequest, user_id: UUID | None = None) -> ResearchEnvelope: ...
    async def get_earnings_analysis(self, request: EarningsAnalysisRequest, user_id: UUID | None = None) -> ResearchEnvelope: ...

    # --- M7 扩展能力 ---
    async def compare_stocks(
        self,
        request: CompareRequest,
        user_id: UUID | None = None,
    ) -> ResearchEnvelope:
        """执行多股票横向综合对比分析 (F4)"""
        ...

    async def get_long_term_analysis(
        self,
        request: LongTermRequest,
        user_id: UUID | None = None,
    ) -> ResearchEnvelope:
        """执行股票 5/10/15 年长期投资价值与破裂条件评估 (F5)"""
        ...

    async def generate_portfolio_allocation(
        self,
        request: PortfolioRequest,
        user_id: UUID | None = None,
    ) -> ResearchEnvelope:
        """执行基于约束优化的确定性投资组合配置 (F8)"""
        ...
```

---

## 3. 代码量化与优化算法规范（`QuantitativeMetricsEngine` 扩充）

### 3.1 横向对比标准化指标分位打分（`compute_cross_sectional_ranking`）
1. 输入：$N$ 只股票的基本面快照字典；
2. 跨股票指标标准化（Percentile Ranking）：
   - 正向指标（越大越好）：营收增速、净利润率、ROE、股息率；
   - 负向指标（越小越好）：市盈率（PE）、负债权益比（Debt/Equity）、Beta 波动率；
   - 统一计算每个指标在横向标的中的百分位分值（0–100 分）；
3. 综合加权总分计算：
   $$\text{Total Score} = \sum_{d} w_d \times \text{Score}_d$$
4. 产出确定性排序与字典放入 facts 的 `computed` 块：
   ```python
   computed["ranking"] = [
       {"symbol": "AAPL", "rank": 1, "total_score": Decimal("84.50")},
       {"symbol": "CAT", "rank": 2, "total_score": Decimal("72.00")},
       ...
   ]
   ```

### 3.2 投资组合约束权重分配引擎（`optimize_portfolio_weights`）
1. 风险与目标映射参数约束：
   - `conservative`：现金下限 $\ge 20\%$，单股上限 $\le 25\%$，倾向低 Beta 与高股息标的；
   - `moderate`：现金下限 $\ge 10\%$，单股上限 $\le 30\%$，风险平价与逆波动率加权；
   - `aggressive`：现金下限 $\ge 5\%$，单股上限 $\le 40\%$，倾向高成长与进攻型标的；
2. 守恒公式：
   $$\sum_{i=1}^M \text{weight\_pct}_i + \text{cash\_pct} = 100.00\%$$
   $$\text{allocated\_amount}_i = \text{round}(\text{amount} \times \frac{\text{weight\_pct}_i}{100}, 2)$$
   $$\text{cash\_amount} = \text{amount} - \sum \text{allocated\_amount}_i$$
3. 算法产出绝对置于 facts 的 `computed` 块，`AIService` 必须严格原样输出对应数字，AI 随意修改数字将直接触发 `FactTracingError`。

---

## 4. 论文破裂条件可监控性规范（`thesis_breakers`）
每个破裂条件必须包含 `data_field`，且必须精确对应系统的已知指标快照点分路径：
- `fundamentals.net_margin`（净利润率）
- `fundamentals.pe_trailing`（市盈率）
- `fundamentals.revenue_growth`（营收增长率）
- `fundamentals.debt_to_equity`（负债率）
- `quote.price`（价格）
- `technical.support`（关键支撑位跌破）

缺少 `data_field` 或字段无法被 M10 监控引擎识别的报告将被合规检查层判定不合格。
