# M7-T03 跨标的事实聚合与代码量化优化引擎（指标分位打分与组合约束优化）

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | T01 |
| 阻塞 | T04 |
| 分支 | `feat/m7-t03-fact-aggregator-quantitative` |
| Issue | #135 |
| 建议规模 | 中–大（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
在 `FactAggregator` 中支持多标的并发数据提取与结构化聚合，并在 `QuantitativeMetricsEngine` 中实现：
1. **多标的同口径指标分位打分与确定性排名计算**（用于 F4 对比，防 AI 随意打分）；
2. **投资组合约束权重优化分配算法**（用于 F8 组合，约束：单股上限、现金下限、波动率目标，权重和严格恒等 100%）。

---

## 2. 范围
**包含**
1. `backend/app/modules/research/aggregator.py`：
   - 扩充 `aggregate_multi_facts(symbols, use_case, ...)` 或重载支持列表并发聚合；
   - 提取跨标的统一行情、基本面与衍生指标；
   - 组装 `computed` 块（`ranking`、`allocations`、`cash_pct`、`cash_amount`）。
2. `backend/app/modules/research/quantitative.py`：
   - `compute_cross_sectional_ranking(facts_dict) -> list[dict[str, Any]]`：
     - 正向指标（营收增长、净利润率、ROE、股息率）；
     - 负向指标（市盈率 PE、负债率、Beta）；
     - 计算各指标在样本池中的分位百分比并加权得出确定性 `total_score` 与 `rank`。
   - `optimize_portfolio_weights(amount, symbols, risk_level, goal, facts_dict) -> dict[str, Any]`：
     - 根据风险等级设定 `max_weight` 与 `min_cash_pct`；
     - 逆波动率/风险平价启发式分配基础权重；
     - 投影至上下界约束；
     - 严格保证 $\sum \text{weight\_pct} + \text{cash\_pct} == 100.00\%$ 与金额精确取整求和恒等。
3. 单元测试 `backend/tests/unit/modules/research/test_m7_quantitative_optimization.py`：
   - 严格测试分位算法单调性、极端值防御、权重守恒性、约束遵守性。

---

## 3. 文件所有权
- **修改并拥有**：
  - `backend/app/modules/research/aggregator.py`
  - `backend/app/modules/research/quantitative.py`
- **创建并拥有**：
  - `backend/tests/unit/modules/research/test_m7_quantitative_optimization.py`

---

## 4. 验收标准
- [x] 多标的并发聚合健壮，缺失项按规范记入 `missing_fields`
- [x] 对比总分与排名 100% 由代码计算给出，算法确定可复现
- [x] 投资组合权重和（含现金）严格恒等于 100.00%，单股上限与现金下限 100% 遵守
- [x] 单元测试通过率 100%
