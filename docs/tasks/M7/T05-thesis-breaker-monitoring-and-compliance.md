# M7-T05 论文破裂条件（thesis_breakers）监控元数据与合规包装器

| 项 | 内容 |
|---|---|
| 波次 | Wave 4 |
| 依赖 | T01, T04 |
| 阻塞 | T06, T07 |
| 分支 | `feat/m7-t05-thesis-breaker-compliance` |
| Issue | #137 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
在 `compliance.py` 中扩充针对 M7 专属特性的合规校验与审计守卫：
1. **破裂条件可监控性强校验**：针对 F5 长期持有报告，确保 `thesis_breakers` 包含 $\ge 3$ 条具备可观测数据源路径的结构化条件；
2. **组合权重确定性防篡改防线**：针对 F8 投资组合，利用 `FactTracingEngine` 严格核实 AI 吐出的 `weight_pct` 与 `cash_pct` 100% 取自代码计算；
3. **新手通俗化与零禁用词**：检查 `compare` / `long_term` / `portfolio` 输出中不得含有任何保证性收益词汇。

---

## 2. 范围
**包含**
1. `backend/app/modules/research/compliance.py`：
   - 扩充 `check_novice_readability` 支持 M7 三大用例；
   - 实现 `validate_thesis_breakers(breakers) -> tuple[bool, list[str]]`，验证 `metric`、`threshold` 与 `data_field` 在支持的数据路径字典中；
   - 强化组合配比一致性校验。
2. 单元测试 `backend/tests/unit/modules/research/test_m7_compliance.py`：
   - 测试各类合法/非法破裂条件场景；
   - 测试 AI 试图篡改组合权重或打分时的拦截；
   - 测试金融禁用词拦截。

---

## 3. 文件所有权
- **修改并拥有**：
  - `backend/app/modules/research/compliance.py`
- **创建并拥有**：
  - `backend/tests/unit/modules/research/test_m7_compliance.py`

---

## 4. 验收标准
- [x] 破裂条件可监控性校验有效，能被后续 M10 调度器直接消费
- [x] AI 任何对组合权重、现金比例、对比总分的篡改均被拦截
- [x] 零保证性禁用词合规把关有效
- [x] 单元测试通过率 100%
