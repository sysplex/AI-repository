# M5-T03 提示词仓库注册表、版本管理与防提示注入模板引擎

| 项 | 内容 |
|---|---|
| 波次 | Wave 2（AI 基础设施） |
| 依赖 | T01 |
| 阻塞 | T04, T07 |
| 分支 | `feat/m5-t03-prompt-registry` |
| Issue | #103 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
构建结构化提示词管理注册表（`PromptRegistry`）、多版本管理机制与防提示注入模板渲染引擎（`prompts.py`），对系统指令、事实数据、输出 Schema 与外部未受信文本进行严格沙箱与 XML 标签隔离。

---

## 2. 范围
**包含**
1. `backend/app/modules/ai/prompts.py`：
   - `PromptTemplate`：包含 `use_case`, `version`, `system_template`, `user_template`, `output_schema`, `description`；
   - `PromptRegistry`：支持通过代码或配置注册提示词、按 `(use_case, version)` 检索（默认返回当前 active 版本）；
   - 内置 M5 基础健康巡检与测试用提示词模板（`health_check`, `facts_summary` 等）。
2. **防提示注入与沙箱隔离**：
   - 外部未受信数据（如新闻文本、用户自定义备注）强制包裹在 `<external_facts>` / `<untrusted_content>` 隔离标签内；
   - 严禁外部文本越界覆盖系统提示词指令。
3. `backend/tests/unit/modules/ai/test_prompts.py`：
   - 提示词注册、查询、多版本回退与模板渲染测试；
   - 提示注入防御测试（如输入文本包含“忽略以上指令并输出…”时保持模板结构不变）。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/ai/prompts.py`
  - `backend/tests/unit/modules/ai/test_prompts.py`

---

## 4. 验收标准
- [x] 提示词版本管理准确（支持默认版本与特定版本指定）
- [x] 模板渲染时事实数据确定性注入
- [x] 防提示注入测试 100% 通过
- [x] 单元测试覆盖率 $\ge 90\%$，`make check` 全绿
