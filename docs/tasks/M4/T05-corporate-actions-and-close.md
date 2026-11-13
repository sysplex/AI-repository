# M4-T05 公司行动（拆股/分红）、收盘批处理与净值快照

| 项 | 内容 |
|---|---|
| 波次 | Wave 4 |
| 依赖 | T01、T04 |
| 阻塞 | T06、T07、T08 |
| 分支 | `feat/m4-t05-corporate-actions-and-close` |
| Issue | #89 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | _待认领_ |

---

## 1. 目标
实现公司行动（拆股/合股后市值恒定、现金分红到账）以及收盘定时批处理流程（撮合挂单、清理过期订单、计算并沉淀每日净值快照）。

---

## 2. 范围
**包含**
1. `backend/app/modules/simbroker/corporate_actions.py`：
   - `apply_stock_split(position, split_ratio)`：
     - 正向拆股（如 2:1，ratio=2.0）或反向合股（如 1:4，ratio=0.25）：
     - `new_qty = position.qty * split_ratio`
     - `new_avg_cost = position.avg_cost / split_ratio`
     - 断言拆股前后瞬间市值恒等：`qty * cost == new_qty * new_cost`。
   - `apply_cash_dividend(account, position, dividend_per_share)`：
     - `dividend_amount = position.qty * dividend_per_share`
     - 增加账户现金，记录资金流水。
2. `backend/app/modules/simbroker/market_close.py`：
   - `process_market_close(account_id, trade_date, market_feed)`：
     - 触发日终撮合处理，将未成交的 DAY 订单标记为 `expired`；
     - 获取各持仓当日收盘价，计算总持仓市值 `market_value`；
     - 计算当日总净值 `equity = cash + market_value`；
     - 结合历史峰值净值更新回撤 `drawdown = (peak_equity - equity) / peak_equity`；
     - 持久化至 `equity_snapshots` 数据表。
3. `backend/tests/unit/modules/simbroker/test_corporate_actions_close.py`：
   - 拆股/合股无损市值校验测试、分红派息测试、日终收盘净值与回撤快照落地测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/simbroker/corporate_actions.py`
  - `backend/app/modules/simbroker/market_close.py`
  - `backend/tests/unit/modules/simbroker/test_corporate_actions_close.py`

---

## 4. 验收标准
- [ ] 拆股与合股前后持仓总市值保持 Decimal 精度级恒等不变
- [ ] 现金分红准确计入现金
- [ ] 收盘批处理正确过期 DAY 订单，并持久化 `equity_snapshots`
- [ ] 回撤计算（Drawdown）与手算样例一致
