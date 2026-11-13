# M3-T04 基本面与量化选股策略（价值/成长/红利）

| 项 | 内容 |
|---|---|
| 波次 | Wave 3 |
| 依赖 | T01 已合并 |
| 阻塞 | T06、T07 |
| 分支 | `feat/m3-t04-fundamental-strategies` |
| Issue | #74 |
| 建议规模 | 中（1天） |
| 负责 Agent | _待认领_ |

---

## 1. 目标
实现基于财务指标与估值的 v1 基本面选股策略，消费 `marketdata` 模块的 `Fundamentals`。

---

## 2. 范围
**包含**
1. `backend/app/modules/strategy/strategies/fundamental.py`：
   - `ValueBasicStrategy`：价值策略（PE < 20, PB < 3, ROE > 15%, Debt/Equity < 1.0）。
   - `GrowthBasicStrategy`：成长策略（连续营收/净利增长, 正自由现金流）。
   - `DividendBasicStrategy`：红利策略（股息率 > 3%, 派息比率健康, 低杠杆）。
2. `backend/tests/unit/modules/strategy/test_fundamental_strategies.py`：
   - 基本面规则评估测试。
   - 字段缺失或数据不足时的降级测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/strategy/strategies/fundamental.py`
  - `backend/tests/unit/modules/strategy/test_fundamental_strategies.py`

---

## 4. 验收标准
- [ ] 字段缺失时显式标明缺失或返回 `insufficient_data`，绝不编造
- [ ] 与 `marketdata.models.Fundamentals` 强类型解耦
- [ ] `make check` 全绿
