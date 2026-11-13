# M5-T05 数字溯源校验引擎与 AI 输出防编造防御（docs/08 §4.3）

| 项 | 内容 |
|---|---|
| 波次 | Wave 3（AI 防御机制） |
| 依赖 | T01, T03 |
| 阻塞 | T07 |
| 分支 | `feat/m5-t05-fact-tracing-defense` |
| Issue | #105 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
实现核心防幻觉引擎：数字溯源校验器（`FactTracingEngine`，`tracing.py`），对 AI 输出中声称的所有财务数据、指标数值进行反向溯源匹配，确保全部数字在事实上下文（`facts` / `computed`）中真实存在，严格落地 `docs/08-test-plan.md §4.3` 全部拦截规范。

---

## 2. 范围
**包含**
1. `backend/app/modules/ai/tracing.py`：
   - 数值提取器：递归扫描输出 payload（字典、列表、文本字符串中的价格与百分比）；
   - 事实索引构建器：将输入的 `facts`、`computed` 扁平化索引为高精 Decimal 集合与路径字典；
   - 溯源比对算法：
     - 若模型指明 `source_field` 路径：校验路径是否存在且数值是否匹配；
     - 若模型未指明路径：在全量事实数值索引中进行近似容差搜索（容差 $\le 10^{-4}$，支持百分比 0.15 vs 15% 自动换算）；
   - 违规拦截：发现编造未登记的数字或 `source_field` 指向不存在的字段时，生成 `FactTracingViolation` 并判定校验失败。
2. 禁用词与数据缺失防御：
   - 检查非法保证性词汇（如“保证保本”、“稳赚不赔”等）；
   - 对数据缺失字段断言输出标明“数据缺失”或 null，严禁猜测。
3. `backend/tests/unit/modules/ai/test_fact_tracing.py`：
   - 逐项测试 `docs/08-test-plan.md §4.3` 拦截用例：
     - ① 含 `facts` 中不存在的编造数字；
     - ② `source_field` 指向不存在路径；
     - ③ 含禁用词；
     - ④ 浮点与百分比等价换算正确溯源；
     - ⑤ 正常合规报告 100% 校验通过。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/ai/tracing.py`
  - `backend/tests/unit/modules/ai/test_fact_tracing.py`

---

## 4. 验收标准
- [x] 编造数字拦截率 100%
- [x] 非法 `source_field` 路径拦截率 100%
- [x] 针对真实事实中的百分比与小数等价表示能正确匹配
- [x] 单元测试覆盖率 $\ge 90\%$，`make check` 全绿
