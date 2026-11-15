# M9-T07 模拟盘全功能工作台与交易日志（SimBroker Console & Trading Journal）

| 项 | 内容 |
|---|---|
| 波次 | Wave 4 |
| 依赖 | T02, T03, T04 |
| 阻塞 | T08 |
| 分支 | `feat/m9-t07-simbroker-console-journal` |
| Issue | #171 |
| 建议规模 | 中–大（1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
构建逼真模拟交易操作台与复盘工作流，展示账户实时资产净值走势图、持仓盈亏、多委托类型下单交易面板、购买力与 PDT 规则预警，以及结构化交易复盘日志。

---

## 2. 交付范围
1. **资产概览与净值走势** (`/simbroker`)：
   - 账户资产看板（总资产、可用现金、持仓市值、当日盈亏、累计盈亏回报率）；
   - 每日净值曲线图（与基准 SPY 对比 Alpha 走势）；
   - 出入金操作弹窗。
2. **交易下单面板**：
   - 支持市价单（MARKET）、限价单（LIMIT）、止损单（STOP）；
   - 买入/卖出数量与金额即时测算、最大可买股数测算；
   - 资金充足性检查、PDT 剩余次数预警、交易确认模态框。
3. **持仓明细与订单成交历史** (`/simbroker/orders`)：
   - 持仓列表（持仓股数、平均成本、最新市价、浮动盈亏）；
   - 当前挂单与历史成交记录（状态：SUBMITTED, FILLED, CANCELLED, EXPIRED），支持一键撤单。
4. **交易复盘日志** (`/simbroker/journal`)：
   - 每笔交易关联入场理由与策略标签；
   - 盈亏复盘回填与交易总结。

---

## 3. 验收与交付记录

- **状态**：✅ 已完成
- **PR**：PR #179 (`feat/m9-t07-simbroker-console-journal` -> `main`)
- **交付物**：
  1. `frontend/src/api/simbroker.ts`：13 个 REST API 方法封装，包含幂等键 `Idempotency-Key` 自动注入、出入金、下单、撤单、持仓、订单、成交历史、绩效分析、实时风控及交易日志复盘更新。
  2. `frontend/src/pages/simbroker/mockData.ts`：完备的 Mock 数据集，严格遵循 OpenAPI 契约结构（包括 `FeeModelConfig-Output`）。
  3. `frontend/src/pages/simbroker/AccountOverviewView.tsx`：资产总览、每日净值走势曲线与 SPY Alpha 走势对比、PDT 5 日 3 次监管监控与豁免线提示、风控指标与前四大重仓集中度。
  4. `frontend/src/pages/simbroker/OrderTradePanelView.tsx`：多委托类型（市价/限价/止损）与有效期（DAY/GTC）、最大可买测算、资金充足性与 PDT 预警、二次确认防误触模态框。
  5. `frontend/src/pages/simbroker/PositionsAndOrdersView.tsx`：当前持仓明细（均价、现价、浮盈、仓位占比）、挂单与成交历史列表、一键快速撤单。
  6. `frontend/src/pages/simbroker/TradingJournalView.tsx`：历史成交清单、平仓实现盈亏、结构化复盘卡片（情绪、策略标签、反思笔记）与录入/编辑模态框。
  7. `frontend/src/pages/simbroker/SimBrokerPage.tsx`：多视图统一顶部 Tab 切换与路由参数双向同步、出入金与新建账户模态框、法定免责声明。
  8. 测试套件：`frontend/src/api/__tests__/simbroker.test.ts`（13 个 API 单元测试）与 `frontend/src/pages/simbroker/__tests__/simbroker_views.test.tsx`（5 个全视图渲染与交互断言测试）。
- **门禁验证**：TypeScript strict 0 警告、13/13 Vitest 测试文件（109 个用例）全部通过、Vite 生产构建成功、后端 Ruff 检查通过。
