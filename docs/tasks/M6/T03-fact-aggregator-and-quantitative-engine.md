# M6-T03 事实聚合器与代码量化派生引擎（Quantitative Metrics & Facts Aggregator）

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | T01 |
| 阻塞 | T04, T07, T08 |
| 分支 | `feat/m6-t03-fact-aggregator-quantitative` |
| Issue | #119 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
实现 `FactAggregator`（从 marketdata/strategy 多数据源聚合事实并追踪缺失字段）与 `QuantitativeEngine`（根据数学与量化规则确定性生成买入决策相对位置与技术面交易计划）。严格杜绝让大模型凭空编造交易点位与派生百分比。

---

## 2. 范围
**包含**
1. `backend/app/modules/research/quantitative.py`：
   - `compute_target_vs_price_pct(current_price, target_price) -> Decimal`
   - `compute_pos_in_52w_range(current_price, low_52w, high_52w) -> Decimal`（含边界保护与 clamp）
   - `compute_technical_trade_plan(current_price, support, resistance, atr) -> TradePlanDict`：计算 entry, stop, target, risk_reward。
2. `backend/app/modules/research/aggregator.py`：
   - `FactAggregator`：调用 `DataService` 获取行情、资料、基本面、财报、新闻；调用 `StrategyService.compute_technical_snapshot` 获取技术指标；
   - 提取各用例专属的 `facts` 字典，组装 `computed` 区块并收集 `missing_fields` 列表。
3. `backend/tests/unit/modules/research/test_quantitative_engine.py`：
   - 包含数学精度、零除边界、52周高低点相等、极端价格波动等场景的严格属性测试。
4. `backend/tests/unit/modules/research/test_fact_aggregator.py`：
   - 模拟各底层服务响应，验证事实组装与缺失字段收集机制。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/research/quantitative.py`
  - `backend/app/modules/research/aggregator.py`
  - `backend/tests/unit/modules/research/test_quantitative_engine.py`
  - `backend/tests/unit/modules/research/test_fact_aggregator.py`

---

## 4. 验收标准
- [ ] 核心公式使用 `Decimal` 高精度计算，除零与极值场景安全降级
- [ ] 交易计划 `risk_reward = (target - entry) / (entry - stop)` 精确计算
- [ ] 事实聚合器完整映射 F2/F3/F6/F7 各用例所需数据，缺失数据正确加入 `missing_fields`
- [ ] 单元测试覆盖率 $\ge 90\%$，全部检查通过
