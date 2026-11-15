# M7-T07 黄金数据集多标的场景集成验证（横向对比、长投价值、投资组合全矩阵）

| 项 | 内容 |
|---|---|
| 波次 | Wave 5 |
| 依赖 | T04, T05, T06 |
| 阻塞 | T08 |
| 分支 | `feat/m7-t07-golden-dataset-multi-stock` |
| Issue | #139 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
依托黄金数据集 5 大代表性标的（`AAPL`, `CAT`, `KO`, `PLTR`, `SOFI`），构建多标的多场景集成验证矩阵：
1. **对比矩阵**：科技 vs 周期（AAPL vs CAT）、防守 vs 成长（KO vs PLTR）、5 标的综合大比拼；
2. **长投价值矩阵**：5 年、10 年、15 年不同期限下的支柱评级与破裂条件生成；
3. **组合配置矩阵**：保守型（高现金/低上限）、平衡型、激进型 3 种风险偏好下的全自动优化配置。

---

## 2. 范围
**包含**
1. `backend/tests/integration/modules/research/fixtures/m7_golden_scenarios.py`：
   - 固化对比测试组合、长投历史多年度参数与组合优化基准。
2. `backend/tests/integration/modules/research/test_m7_golden_dataset.py`：
   - 执行多场景矩阵测试；
   - 严密断言：
     - FactTracingEngine 100% 溯源通过（0 幻觉数字）；
     - 对比总分与代码计算 100% 匹配；
     - 组合权重和严格为 100.00%，单股上限和现金下限被完全遵守；
     - 破裂条件均包含有效可监控指标路径。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/tests/integration/modules/research/fixtures/m7_golden_scenarios.py`
  - `backend/tests/integration/modules/research/test_m7_golden_dataset.py`

---

## 4. 验收标准
- [x] 多标的集成测试矩阵全部运行通过
- [x] 0 数字幻觉违规，0 禁用词违规
- [x] 投资组合权重和恒等于 100%，资金分配金额求和精准无误差
- [x] 测试运行效率高，单测集成全绿
