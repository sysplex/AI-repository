# M10-T03: 智能提醒引擎与长期持有论文破裂监控

> 责任人：Antigravity ｜ 依赖：M10-T01, M10-T02 已完成 ｜ 分支：`feat/m10-t03-alert-and-thesis-breaker-engine`  
> 契约参考：[`docs/tasks/M10/CONTRACTS.md§2.2, §4`](CONTRACTS.md) ｜ [`docs/01-prd.md§4 (F12)`](../../01-prd.md) ｜ [`docs/04-modules.md#m10`](../../04-modules.md)

---

## 1. 任务背景与目标

在 M10-T01 和 T02 中，我们分别完成了数据持久层模型与多通道通知网关。
本任务（M10-T03）的核心目标是构建端到端的**智能提醒引擎（Alert Engine）**与**长期持有论文破裂（Thesis Breakers）监控评估体系**：

1. **核心规则评估器（Evaluators）**：
   - **价格突破评估器 (`PriceAlertEvaluator`)**：监控最新价是否穿越设定目标价格（`cross_above` 向上突破 / `cross_below` 向下跌破）。
   - **技术信号评估器 (`TechnicalSignalEvaluator`)**：监控量化指标（如 RSI 超买超卖、均线穿越、布林带触轨等），支持 `lt`, `lte`, `gt`, `gte`, `eq`。
   - **财报倒计时评估器 (`EarningsDateEvaluator`)**：监控标的即将公布财报的倒计时天数（默认提前 1 天或 3 天）。
   - **论文破裂评估器 (`ThesisBreakerEvaluator`)**：直接对接并消费 M7 F5 的 `thesis_breakers` 规格，从基本面数据快照中提取指标（支持点分路径如 `fundamentals.net_margin`），完成阈值破裂求值。

2. **规则全生命周期管理服务 (`AlertService`)**：
   - 提醒规则 CRUD 与过滤查询（按用户、状态、代码、规则类型）。
   - 支持从 M7 研报一键批量转换为监控规则：`batch_create_thesis_breakers`。
   - 冷却与频控（`cooldown_minutes`）：触发后进入冷却，到期前自动抑制二次骚扰。
   - 评估扫描主流程：接收市场与基本面行情快照，并发评估规则，触发时自动组装 `NotificationMessage` 并调用 `NotificationDispatcher` 分发。

---

## 2. 研发范围与代码架构

```
backend/app/modules/notify/
├── evaluators/
│   ├── __init__.py                # 导出所有评估器
│   ├── base.py                    # EvaluationResult, BaseAlertEvaluator
│   ├── price_evaluator.py         # PriceAlertEvaluator
│   ├── technical_evaluator.py     # TechnicalSignalEvaluator
│   ├── earnings_evaluator.py      # EarningsDateEvaluator
│   └── thesis_breaker_evaluator.py# ThesisBreakerEvaluator
├── service.py                     # AlertService（规则 CRUD、批量生成、执行扫描评估）
└── ...
```

### 2.1 评估结果实体 (`EvaluationResult`)
- `triggered: bool`：是否满足触发条件。
- `message: str`：通俗白话告警文案（如 `AAPL 毛利率跌破 40% (实际: 37.8%)，长期护城河论文受损`）。
- `triggered_value: dict[str, Any]`：触发瞬间的指标快照数据。

### 2.2 论文破裂可监控性对齐
- 必须兼容 M7 的 `SUPPORTED_THESIS_BREAKER_DATA_FIELDS`；
- 支持嵌套字典解析（点分路径提取，如 `fundamentals.net_margin` 或直接顶层 `net_margin`）；
- 数值与百分比符号容错转换（Decimal 安全计算）。

---

## 3. 验收标准（DoD）

1. [x] 四大评估器（Price, Technical, Earnings, ThesisBreaker）均通过确定性单元测试，覆盖边界与缺失数据。
2. [x] 论文破裂评估器能够准确解析 M7 产出的结构化条件并准确触发警报。
3. [x] `AlertService` 实现完整的 CRUD 与基于 `cooldown_minutes` 的冷却防抖逻辑。
4. [x] 触发告警时与 `NotificationDispatcher` 无缝联动，自动落库 `alert_history`。
5. [x] 单元测试覆盖率保持 ≥ 85%，全部测试 100% 通过。
