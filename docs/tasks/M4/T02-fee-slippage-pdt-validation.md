# M4-T02 费用模型、滑点、PDT 规则与订单验证引擎

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | T01 |
| 阻塞 | T03、T07、T08 |
| 分支 | `feat/m4-t02-validation-fee-pdt` |
| Issue | #86 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | _待认领_ |

---

## 1. 目标
实现模拟盘的费用模型计算、滑点计算、美股 PDT（Pattern Day Trader）5 日滚动监控规则以及下单前置校验引擎。

---

## 2. 范围
**包含**
1. `backend/app/modules/simbroker/fee.py`：
   - `FeeEngine`：支持零手续费（`zero`）、每股固定收费（`per_share`）、交易额比例收费（`bps`）、分层保底与封顶（`min_fee`, `max_fee`）。
   - `calculate_slippage(price, side, slippage_bps) -> Decimal`：买入上滑，卖出下滑。
2. `backend/app/modules/simbroker/pdt.py`：
   - `PdtEngine`：美股标准规则，追踪过去 5 个美东交易日内"当日买入且当日卖出同一标的"的次数；当账户净值 < $25,000 且 5 日内 Day Trade 达 3 次时，第 4 次日内平仓触发拦截或警报（`pdt_warning`）。
3. `backend/app/modules/simbroker/validator.py`：
   - `OrderValidator`：
     - 买单资金校验：`cash >= qty * price + estimated_fee + slippage`，资金不足拒绝（`REJECTED`，错误码 `INSUFFICIENT_FUNDS`）。
     - 卖单超卖校验：当前可用持仓 `qty >= order_qty`，超卖拒绝（`REJECTED`，错误码 `INSUFFICIENT_POSITION`）。
     - 基础校验：标的代码格式、`qty > 0`、限价/止损价格大于 0 等。
4. `backend/tests/unit/modules/simbroker/test_fee_pdt_validator.py`：
   - 单元测试覆盖各类费用配置与滑点、PDT 边界滑窗测试、资金不足与超卖拦截测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/simbroker/fee.py`
  - `backend/app/modules/simbroker/pdt.py`
  - `backend/app/modules/simbroker/validator.py`
  - `backend/tests/unit/modules/simbroker/test_fee_pdt_validator.py`

---

## 4. 验收标准
- [ ] 各种费用模型手算对齐，精度保持 Decimal
- [ ] 滑点计算方向正确（买入推高价格，卖出压低价格）
- [ ] PDT 5 交易日滑动窗口准确识别日内回转交易（Day Trade）
- [ ] 资金不足与超卖精确拦截并返回对应错误原因
