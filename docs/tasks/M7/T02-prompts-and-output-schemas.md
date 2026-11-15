# M7-T02 提示词模板注册与输出 Schema 约束（3 大核心用例）

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | T01 |
| 阻塞 | T04 |
| 分支 | `feat/m7-t02-prompts-output-schemas` |
| Issue | #134 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
在 `backend/app/modules/research/prompts.py` 中编写并注册 M7 的三大用例提示词模板（`compare`, `long_term`, `portfolio`），在 `backend/app/modules/ai/prompts.py` 完成注册与 Schema 挂载，并为提示词注入 XML CDATA 隔离防护沙箱。

---

## 2. 范围
**包含**
1. `backend/app/modules/research/prompts.py`：
   - `compare` 提示词模板：注入事实中的 `ranking` 与多股票指标表，严正声明 AI 不得改动得分与排名，重点阐述核心逻辑、维度对比与投资人群画像；
   - `long_term` 提示词模板：注入多年度财务/护城河事实，指导分析 7 大支柱评级并生成 $\ge 3$ 条含 `metric, threshold, data_field` 的结构化破裂条件；
   - `portfolio` 提示词模板：注入事实中的 `allocations` 确定性配置与 `cash_pct`，严禁 AI 擅自修改百分比，重点阐述配置思路、下行防守与再平衡触发器。
2. 约束输出 Schema 与 `ai.prompts.PromptRegistry` 挂载：
   - 挂载 `ComparePayload.model_json_schema()` 到 `use_case="compare"`；
   - 挂载 `LongTermPayload.model_json_schema()` 到 `use_case="long_term"`；
   - 挂载 `PortfolioPayload.model_json_schema()` 到 `use_case="portfolio"`。
3. 单元测试 `backend/tests/unit/modules/research/test_m7_prompts.py`：
   - 验证模板参数渲染正确、XML 注入防御字符转义完备、Schema 注册与验证通过。

---

## 3. 文件所有权
- **修改并拥有**：
  - `backend/app/modules/research/prompts.py`
  - `backend/app/modules/ai/prompts.py`
- **创建并拥有**：
  - `backend/tests/unit/modules/research/test_m7_prompts.py`

---

## 4. 验收标准
- [ ] 3 个用例模板结构清晰，系统指令、事实注入与输出约束分明
- [ ] 挂载至 `PromptRegistry` 且与 Pydantic 输出 Schema 100% 对应
- [ ] 包含防提示词注入与非投资建议免责声明指引
- [ ] 单元测试通过率 100%
