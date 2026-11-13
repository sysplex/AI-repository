# M4-T03 撮合引擎（市价/限价/止损单规则、TIF 与行情缺失防御）

| 项 | 内容 |
|---|---|
| 波次 | Wave 3 |
| 依赖 | T01、T02 |
| 阻塞 | T04、T07、T08 |
| 分支 | `feat/m4-t03-matching-engine` |
| Issue | #87 |
| 建议规模 | 中–大（1 天） |
| 负责 Agent | _待认领_ |

---

## 1. 目标
实现核心订单撮合引擎（`MatchingEngine`），完整实现市价单、限价单、止损单的确定性撮合规则、TIF（DAY/GTC）有效期管理，以及严格的行情缺失防御机制。

---

## 2. 范围
**包含**
1. `backend/app/modules/simbroker/matcher.py`：
   - `MatchingEngine`：
     - **市价单（Market）**：按下一根 Bar Open ± 滑点成交。
     - **限价买（Limit Buy）**：若 `bar.open <= limit_price`，按 `bar.open` 成交；否则若 `bar.low <= limit_price`，按 `limit_price` 成交；否则未撮合。
     - **限价卖（Limit Sell）**：若 `bar.open >= limit_price`，按 `bar.open` 成交；否则若 `bar.high >= limit_price`，按 `limit_price` 成交；否则未撮合。
     - **止损单（Stop Order）**：买单 `bar.high >= stop_price` 触发，按 `max(stop_price, bar.open)` 成交；卖单 `bar.low <= stop_price` 触发，按 `min(stop_price, bar.open)` 不利价成交。
     - **TIF 有效期**：`day` 订单在当日收盘未成交自动置为 `expired`；`gtc` 订单保持 `accepted` 状态跨日保留。
     - **行情缺失防御**：当 Bar 行情缺失时，订单**严格保持 `accepted` 状态**并发出警报日志，严禁使用陈旧历史价格搓合成交。
2. `backend/tests/unit/modules/simbroker/test_matching_engine.py`：
   - 包含市价/限价/止损单逐笔手算样例对齐测试、跳空高开/低开穿透测试、未触发边界测试、缺失行情防御测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/simbroker/matcher.py`
  - `backend/tests/unit/modules/simbroker/test_matching_engine.py`

---

## 4. 验收标准
- [ ] 严格遵守 `docs/tasks/M4/CONTRACTS.md §3` 撮合规则
- [ ] 市价单/限价单/止损单手算样例 100% 逐笔吻合
- [ ] 行情缺失时订单保持 `accepted` 并记录 warning，无陈旧价格成交
- [ ] DAY 订单到期正确置为 `expired`
