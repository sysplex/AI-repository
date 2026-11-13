# M4-T06 绩效分析、回撤胜率、SPY 跑赢对比与持仓风险体检诊断

| 项 | 内容 |
|---|---|
| 波次 | Wave 5 |
| 依赖 | T01、T04、T05 |
| 阻塞 | T07、T08 |
| 分支 | `feat/m4-t06-performance-and-risk` |
| Issue | #90 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
实现模拟盘投资组合的绩效表现分析计算（净值曲线、最大回撤 MDD、胜率、盈亏比、对比 SPY 跑赢基准）与持仓健康度风险诊断（单股集中度、行业分布、现金水位）。

---

## 2. 范围
**包含**
1. `backend/app/modules/simbroker/performance.py`：
   - `PerformanceAnalyzer`：
     - 从 `equity_snapshots` 提取净值曲线序列；
     - 计算最大回撤 `max_drawdown`；
     - 从已平仓交易统计胜率 `win_rate = winning_trades / total_closed_trades`；
     - 盈亏比 `profit_loss_ratio = sum(gross_profits) / abs(sum(gross_losses))`；
     - 基准跑赢分析：调取同一区间 SPY 收益率，计算账户相对跑赢比例、Alpha 与 Beta。
2. `backend/app/modules/simbroker/risk.py`：
   - `RiskAnalyzer`：
     - 单股持仓占比 `weight = position_market_value / total_equity`；
     - 前 N 大持仓集中度；
     - 行业分布汇总统计 `sector_weights`；
     - 现金仓位占比 `cash_ratio = cash / total_equity`；
     - PDT 违规与预警状态判断。
3. `backend/tests/unit/modules/simbroker/test_performance_risk.py`：
   - 单元测试覆盖各类收益曲线、盈亏比分母为 0 边界保护、胜率计算与持仓权重分布校验。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/simbroker/performance.py`
  - `backend/app/modules/simbroker/risk.py`
  - `backend/tests/unit/modules/simbroker/test_performance_risk.py`

---

## 4. 验收标准
- [ ] 净值曲线与最大回撤（MDD）与手算样例一致
- [ ] 胜率与盈亏比（Profit Factor）计算准确，无除以零异常
- [ ] 与基准 SPY 对比收益计算准确
- [ ] 单股集中度与行业板块权重求和满足比例守恒
