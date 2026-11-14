# M6-T01 领域数据模型、DTO Schemas 与端口协议（schemas & ports）

| 项 | 内容 |
|---|---|
| 波次 | Wave 1（M6 地基） |
| 依赖 | M5 已结项 |
| 阻塞 | T02–T08 |
| 分支 | `feat/m6-t01-models-schemas-ports` |
| Issue | #117 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
定义 `research` 模块核心数据契约：Pydantic v2 DTO Schemas、ResearchEnvelope、F2 股票研究、F3 买入决策、F6 技术面分析、F7 财报解读各用例的 Payload 结构，以及 `ports.py` 核心协议抽象（`ResearchServiceProtocol`, `FactAggregatorProtocol`, `QuantitativeEngineProtocol`）。

---

## 2. 范围
**包含**
1. `backend/app/modules/research/schemas.py`：
   - 核心枚举：`InvestmentHorizon`, `RiskLevel`, `BuyVerdict`, `FactorRating`, `EarningsAssessment`, `MoatStrength`, `RiskSeverity`
   - 通用组件：`EvidenceItem`, `ResearchEnvelope`
   - F2 结构：`RevenueSourceItem`, `MoatItem`, `RiskItem`, `Scenarios`, `ResearchPayload`, `ResearchRequest`
   - F3 结构：`FactorItem`, `FactorAssessment`, `PricePosition`, `BuyDecisionPayload`, `BuyDecisionRequest`
   - F6 结构：`TechnicalMetricExplanation`, `TradePlan`, `TechnicalPayload`, `TechnicalAnalysisRequest`
   - F7 结构：`EarningsMetric`, `EarningsPayload`, `EarningsAnalysisRequest`
2. `backend/app/modules/research/ports.py`：
   - `ResearchServiceProtocol`
   - `FactAggregatorProtocol`
   - `QuantitativeEngineProtocol`
3. `backend/app/modules/research/exceptions.py`：
   - `ResearchError`
   - `SymbolNotFoundError` (404)
   - `InsufficientDataError` (422)
   - `QuantitativeCalculationError` (500)
4. `backend/tests/unit/modules/research/test_research_schemas.py`：
   - 针对各用例 Schema 验证、不可变性与序列化反序列化进行严密单元测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/research/schemas.py`
  - `backend/app/modules/research/ports.py`
  - `backend/app/modules/research/exceptions.py`
  - `backend/tests/unit/modules/research/__init__.py`
  - `backend/tests/unit/modules/research/test_research_schemas.py`
- **协同修改**：
  - `backend/app/modules/research/__init__.py`

---

## 4. 验收标准
- [ ] 所有 Schema 定义与 `docs/tasks/M6/CONTRACTS.md §1, §2` 100% 对齐
- [ ] 关键金额与数值字段全部使用 `Decimal`，禁止使用 `float` 造成精度损失
- [ ] 单元测试覆盖所有边界情况（非法枚举、缺失必填项、负数限制等）
- [ ] 模块单测覆盖率 $\ge 90\%$，`mypy` 严格模式 0 错误
