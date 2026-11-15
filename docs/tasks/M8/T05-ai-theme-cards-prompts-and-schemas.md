# M8-T05 AI 主题股票卡片提示词模板注册与输出 Schema 约束（ThemeCards 提示词与防编造）

| 项 | 内容 |
|---|---|
| 波次 | Wave 3 |
| 依赖 | T01, T02 |
| 阻塞 | T06 |
| 分支 | `feat/m8-t05-theme-cards-ai-prompts` |
| Issue | #153 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
遵循 `docs/06-ai-prompt-spec.md§4.8` 规范，设计并注册主题卡片（`theme_card`）的 Prompt 模板与输出 JSON Schema，实现 `ThemeCardsGenerator` 生成器，接入 `FactTracingEngine` 进行数字防编造溯源校验。

---

## 2. 范围
**包含**
1. 提示词与输出约束（`backend/app/modules/screener/prompts.py`）：
   - 系统与用户提示词模板：注入主题背景、成分股真实事实（facts）；
   - 输出 Schema：严格约束必须输出 `ThemeCardItem` 格式（`symbol`, `name`, `one_line_intro`, `why_watch`, `financial_strengths`, `main_risks`, `suitable_for`, `more_attractive_when`）；
   - 防注入标签 `<untrusted_text>` 与安全声明。
2. 溯源比对（`FactTracingEngine` 验证）：
   - 对 `financial_strengths` 中的财务数字与指标，比对输入的真实 facts，若有幻觉或数字偏差则拦截；
   - 保证 AI 仅做通俗新手向解释，不编造财务数字。
3. 单元测试 `backend/tests/unit/modules/screener/test_theme_cards_prompt.py`：
   - 验证 Prompt 渲染完整性与事实注入；
   - 验证有效输出解析与防编造校验机制。

---

## 3. 验收标准
- [ ] 严格遵循 `docs/06-ai-prompt-spec.md§4.8` 规范定义
- [ ] 提示词包含防注入与新手指导定位
- [ ] 真实事实溯源校验有效防御财务幻觉
- [ ] 单元测试覆盖率 $\ge 90\%$，`mypy --strict` 0 错误
