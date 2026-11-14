# M6-T07 黄金集 5 类代表性股票多场景集成验证（Golden Dataset Integration）

| 项 | 内容 |
|---|---|
| 波次 | Wave 5 |
| 依赖 | T04, T05, T06 |
| 阻塞 | T08 |
| 分支 | `feat/m6-t07-golden-dataset-validation` |
| Issue | #123 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
落实 `docs/04-modules.md#m6` 与 `docs/08-test-plan.md §4.3, §5 M6` 的验收铁律：
在由 5 只代表性股票（大盘科技 `AAPL`、周期 `CAT`、高分红 `KO`、亏损成长 `PLTR`、小盘 `SOFI`）构成的黄金数据集上，对 4 个核心用例执行 $5 \times 4 = 20$ 组全矩阵验证，确保 Schema 校验与数字溯源通过率达到 100%。

---

## 2. 范围
**包含**
1. `backend/tests/integration/modules/research/fixtures/golden_stocks.py`：
   - 固化 5 只代表性标的的静态行情、基本面、财报与技术指标快照数据。
2. `backend/tests/integration/modules/research/test_golden_dataset.py`：
   - 遍历 5 股 × 4 用例：
     1. 大盘科技 `AAPL`：商业模式、高毛利、稳定自由现金流。
     2. 周期股 `CAT`：宏观周期影响、重资产、资本开支敏感度。
     3. 高分红防御股 `KO`：稳定股息率、提价权、低 beta 属性。
     4. 亏损/高估值成长股 `PLTR`：高增长、毛利率、无分红或负 EPS 处理。
     5. 小盘股 `SOFI`：高波动、技术面支撑阻力敏感、财报指引易缺失场景。
   - 断言矩阵：
     - 输出 Schema 100% 合法无缺失；
     - 溯源引擎验证所有数字均能回溯至 facts/computed；
     - 交易计划 entry/stop/target/risk_reward 与代码计算 100% 绝对一致；
     - 财报缺失项均显示为“数据缺失”；
     - 每份报告均含免责声明与数据时间。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/tests/integration/modules/research/fixtures/__init__.py`
  - `backend/tests/integration/modules/research/fixtures/golden_stocks.py`
  - `backend/tests/integration/modules/research/test_golden_dataset.py`

---

## 4. 验收标准
- [ ] 20 组测试场景全部运行通过，首次或单次重试后通过率 100%
- [ ] 覆盖 5 大股票类型的特殊指标场景（负利润、高股息、周期波幅等）
- [ ] 测试运行时间合理，单测集成全通过
