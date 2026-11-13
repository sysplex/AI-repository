# M4-T04 记账引擎、持仓管理、平均成本法与财务不变量

| 项 | 内容 |
|---|---|
| 波次 | Wave 4 |
| 依赖 | T01、T03 |
| 阻塞 | T05、T06、T07、T08 |
| 分支 | `feat/m4-t04-accounting-and-positions` |
| Issue | #88 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | _待认领_ |

---

## 1. 目标
实现持仓加权平均成本管理、资金划转流水记账，并通过属性测试严密验证三大财务核心不变量（现金守恒、净值恒等、持仓非负）。

---

## 2. 范围
**包含**
1. `backend/app/modules/simbroker/accounting.py`：
   - `AccountingEngine`：
     - 买入记账：原子扣减现金 `cash -= (qty * price + fee)`；按加权平均法更新持仓数量 `new_qty = old_qty + qty`，`new_avg_cost = (old_qty * old_cost + qty * price + fee) / new_qty`（费用计入成本）。
     - 卖出记账：原子增加现金 `cash += (qty * price - fee)`；扣减持仓数量；按加权成本结转已实现盈亏 `realized_pnl = (price - avg_cost) * qty - fee` 并累加至持仓与成交记录。
     - 出入金操作：`deposit` 增加现金；`withdraw` 减少现金（超提校验）。
2. `backend/tests/unit/modules/simbroker/test_accounting_invariants.py`：
   - 基于 Hypothesis 或大量随机交易序列的财务不变量测试：
     1. **现金守恒不变量**：`cash == initial_cash + sum(deposits) - sum(withdrawals) + sum(sell_proceeds) - sum(buy_costs) - sum(fees)`
     2. **净值恒等不变量**：`equity == cash + sum(qty * current_price)`
     3. **持仓非负不变量**：对任意持仓 `qty >= 0`
     4. **幂等性测试**：并发使用同一 `idempotency_key` 提交，保证有且仅有一次记账成功。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/simbroker/accounting.py`
  - `backend/tests/unit/modules/simbroker/test_accounting_invariants.py`

---

## 4. 验收标准
- [ ] 严格遵守加权平均成本法（Weighted Average Cost）
- [ ] 现金守恒不变量在复杂长序列买卖后 100% 成立
- [ ] 净值恒等式与持仓非负性 100% 成立
- [ ] 单次成交记账满足原子性与幂等性
