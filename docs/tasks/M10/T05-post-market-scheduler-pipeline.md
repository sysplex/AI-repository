# M10-T05: 收盘后全流程自动化批处理工作流与 ARQ 调度编排

> 责任人：Antigravity ｜ 依赖：M10-T02, M10-T03, M10-T04 已完成 ｜ 分支：`feat/m10-t05-post-market-scheduler-pipeline`  
> 契约参考：[`docs/tasks/M10/CONTRACTS.md§1-§2`](CONTRACTS.md) ｜ [`docs/01-prd.md§4 (F12, F13)`](../../01-prd.md) ｜ [`docs/04-modules.md#m10`](../../04-modules.md) ｜ [`docs/08-test-plan.md§5 M10`](../../08-test-plan.md)

---

## 1. 任务背景与目标

在 M10 前序任务中，我们已经分别构建了：
- T01: ORM 模型与数据库迁移（`daily_reports`, `alerts`, `alert_history`, `notification_channels`）；
- T02: 多通道通知网关（`NotificationDispatcher`）；
- T03: 智能提醒与长期持有论文破裂引擎（`AlertService`）；
- T04: AI 投资建议持续复盘与超额收益评估器（`ReviewService`）。

本任务（M10-T05）作为整个系统的**核心批处理调度中枢（Post-Market DAG Pipeline）**，负责将上述分散的领域能力串联为严密、具备强幂等性与容错能力的美股收盘后自动化批处理任务链：

1. **时区与交易日日历守卫（Trading Calendar Guard）**：
   - 严格采用 `America/New_York` 美股交易时区，自动感知夏令时（EDT）与冬令时（EST）；
   - 自动识别半日市（13:00 ET 收盘）与全日市（16:00 ET 收盘）；
   - 非交易日自动挂起，绝不误触发。

2. **收盘后全流程 DAG 编排（Pipeline Steps）**：
   ```mermaid
   flowchart TD
       Start[触发: 16:15 ET 定时器 / 手动重跑] --> CheckDay{是否美股交易日?}
       CheckDay -- 否 --> Skip[跳过并记录非交易日]
       CheckDay -- 是 --> Step1[Step 1: 行情收盘价与基准同步校验]
       Step1 --> Step2[Step 2: 模拟盘过期撤单、资产估值与净值快照]
       Step2 --> Step3[Step 3: 策略筛选池扫描更新]
       Step3 --> Step4[Step 4: 提醒规则与论文破裂全量扫描与通知分发]
       Step4 --> Step5[Step 5: 历史 AI 建议无未来函数复盘回填与 Alpha 计算]
       Step5 --> Step6[Step 6: 每日市场大盘与用户模拟盘持仓简报生成]
       Step6 --> End[流水线完成，记录 Pipeline 状态快照]
   ```

3. **每日简报自动生成（Daily Reports Generator）**：
   - **大盘简报 (`market_digest`)**：三大指数收盘表现、领涨领跌、全市场触发的重要告警汇总；
   - **个人持仓简报 (`portfolio_digest`)**：用户账户当日净值波动、最大回撤、当日交易流水与当前持仓表现。

4. **ARQ 生产级后台调度接入**：
   - 在 `app.worker.WorkerSettings` 中注册收盘批处理 Cron 作业与异步 Worker 函数；
   - 提供幂等性防护，多次触发结果完全一致，绝不重复插入脏快照或重复发送骚扰通知。

---

## 2. 研发范围与架构设计

```
backend/app/
├── modules/scheduler/
│   ├── pipeline.py          # PostMarketPipeline 核心编排服务
│   ├── reports.py           # 每日大盘与用户持仓简报生成器
│   ├── service.py           # SchedulerService 门面（CRUD、触发、状态查询）
│   ├── ports.py             # 扩展 ReviewServiceProtocol, MarketFeedProtocol 等端口
│   └── schemas.py           # 扩展 PipelineRunResult, PipelineStepStatus
├── worker.py                # 注册 run_post_market_pipeline 与 ARQ Cron 作业
```

---

## 3. 验收标准（DoD）

1. [x] 美股交易日历判定严格可靠，非交易日与节假日不执行；
2. [x] 收盘任务链各步骤按 DAG 顺序执行，单步失败提供清晰审计日志；
3. [x] 模拟盘收盘快照、告警扫描与 AI 复盘回填无缝串联；
4. [x] 成功生成 `market_digest` 与 `portfolio_digest` 并落库 `daily_reports`；
5. [x] ARQ Worker 入口与定时任务配置完备；
6. [x] 单元测试覆盖率 ≥ 85%，全系统单元测试保持 ≥ 80% 门禁。
