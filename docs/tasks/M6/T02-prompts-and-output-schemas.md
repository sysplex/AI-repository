# M6-T02 提示词模板注册与输出 Schema 约束（4 大核心用例）

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | T01 |
| 阻塞 | T04, T07, T08 |
| 分支 | `feat/m6-t02-prompts-output-schemas` |
| Issue | #118 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
编写并向 `PromptRegistry` 注册 4 大 AI 研究核心用例的标准提示词模板与 JSON 输出 Schema 约束：`research_v1.0` (F2)、`buy_decision_v1.0` (F3)、`technical_v1.0` (F6)、`earnings_v1.0` (F7)。落实防注入 XML 沙箱、通俗易懂指引与数字溯源强约束。

---

## 2. 范围
**包含**
1. `backend/app/modules/research/prompts.py`：
   - `RESEARCH_V1_TEMPLATE`：系统指令约束中文、通俗生动、三段情景、商业模式；输出 Schema 映射 `ResearchPayload`。
   - `BUY_DECISION_V1_TEMPLATE`：约束输出 verdict (buy/wait/avoid)、6 维度评分理由、必须引用 computed 52周位置；输出 Schema 映射 `BuyDecisionPayload`。
   - `TECHNICAL_V1_TEMPLATE`：约束指标大白话解释、交易计划 entry/stop/target/risk_reward 必须 100% 照搬 computed 数值；输出 Schema 映射 `TechnicalPayload`。
   - `EARNINGS_V1_TEMPLATE`：约束实际/预期/惊喜率、指引解读、缺失项标注“数据缺失”、assessment (strong/mixed/weak)；输出 Schema 映射 `EarningsPayload`。
   - `register_research_prompts()`：自注册到 M5 的 `default_prompt_registry`。
2. `backend/tests/unit/modules/research/test_research_prompts.py`：
   - 验证 4 大模板在全局注册表中的注册与检索；
   - 验证模板参数渲染与 `<untrusted_facts>` XML 沙箱防注入包裹；
   - 验证 SchemaValidator 与生成的 JSON Schema 严格兼容。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/research/prompts.py`
  - `backend/tests/unit/modules/research/test_research_prompts.py`

---

## 4. 验收标准
- [ ] 4 大核心模板均包含明确的系统与用户指令、防注入 XML 隔离沙箱与输出格式约束
- [ ] 模板成功注册到 M5 `default_prompt_registry`，可通过 `get("research", "v1.0")` 等平滑检索
- [ ] 单元测试验证模板渲染与 Schema 校验正确，覆盖率 $\ge 90\%$
