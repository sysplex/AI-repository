# M5-T08 全链路端到端集成验收、防编造压力拦截与 M5 结项报告

| 项 | 内容 |
|---|---|
| 波次 | Wave 6（M5 终局集成验收） |
| 依赖 | T01–T07 全部合入 main |
| 阻塞 | 无（完成即结项并打 Tag v0.5.0） |
| 分支 | `feat/m5-t08-integration-acceptance` |
| Issue | #108 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
对照 `docs/08-test-plan.md §4.3` 与 `§5 M5` 验收清单进行端到端全链路集成验收，执行全套防编造压力拦截测试、缓存与配额双重校验、撰写结项报告 `docs/acceptance/M5.md`，更新全局路线图与 CHANGELOG。

---

## 2. 范围
**包含**
1. `backend/tests/e2e/modules/ai/test_ai_e2e.py`：
   - 逐条覆盖验收清单：
     - ① Mock LLM 全流程通过；
     - ② 4.3 全部拦截用例通过（缺字段、枚举越界、含 `facts` 中不存在的数字、含禁用词、`source_field` 指向不存在路径均被拦截）；
     - ③ 提示注入攻击防御（外部文本含指令覆盖时不受影响）；
     - ④ 缓存命中无成本、不扣配额；
     - ⑤ 配额耗尽拒绝（`QUOTA_EXCEEDED`）与预算熔断（`BUDGET_CIRCUIT_OPEN`）；
     - ⑥ 每次调用成本、tokens、提示词版本入库；
     - ⑦ 全链路 REST API 端到端生命周期与 HARD-01 鉴权。
2. `docs/acceptance/M5.md`：
   - 官方结项验收文档（测试用例清单、覆盖率报告、架构契约审计结论、防幻觉拦截证明）。
3. 协同更新：
   - `docs/README.md`（更新路线图 M5 状态为 `✅ Done`）。
   - `CHANGELOG.md`（记录 M5-T01 ~ T08 全部功能发布与变更）。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/tests/e2e/modules/ai/test_ai_e2e.py`
  - `docs/acceptance/M5.md`
- **协同修改**：
  - `docs/README.md`
  - `CHANGELOG.md`

---

## 4. 验收标准
- [ ] 验收用例 100% 通过
- [ ] 全局测试覆盖率 $\ge 80.0\%$
- [ ] `make check`（ruff check, ruff format, mypy --strict, import-linter, pip-audit）全部绿灯
- [ ] 输出完整的 `docs/acceptance/M5.md` 报告
