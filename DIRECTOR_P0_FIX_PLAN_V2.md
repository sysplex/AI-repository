# StockPilot P0/P1 深度排查与修复迭代计划（DIRECTOR_P0_FIX_PLAN_V2.md）

> **签发角色**：项目总监（Project Director）  
> **审计基线**：`main` 分支 [`20a3753`](https://github.com/sysplex/AI-repository/commit/20a3753)（2026-11-23 跨浏览器复测反馈）  
> **执行对象**：Antigravity  
> **迭代策略**：分两个严格验收批次执行——**批次 A（P0 止血：模拟盘建户 + AI 提示词模板注册）** 必须先跑通并验证，再推进 **批次 B（P1/P2 彻底清零残余 Mock、筛选器、时区与 URL 联动）**。

---

## 一、本轮复测根因总览

| 优先级 | 复测现象 | 精确根因与代码位置 |
| :---: | :--- | :--- |
| **P0-1** | 创建模拟账户 3 次均报红字“服务器内部错误”，模拟盘完全不可用 | [`backend/app/modules/simbroker/service.py:96`](https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/simbroker/service.py) 使用 `fee_model=req.fee_model.model_dump()` 写入 PostgreSQL `JSONB` 列，但 [`FeeModelConfig`](https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/simbroker/schemas.py) 含 `Decimal` 字段，`asyncpg` 序列化 `Decimal` 到 `JSONB` 直接抛 `TypeError: Object of type Decimal is not JSON serializable` → HTTP 500。 |
| **P0-2** | 所有股票 AI 买入决策报错 `No active prompt template version found for use_case='buy_decision'` | [`backend/app/modules/research/prompts.py:590`](https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/research/prompts.py) 定义了 `register_research_prompts(registry)`（含 M6/M7 全部 7 个模板），但 [`backend/app/core/lifecycle.py`](https://github.com/sysplex/AI-repository/blob/main/backend/app/core/lifecycle.py) 与 [`backend/app/api/router.py`](https://github.com/sysplex/AI-repository/blob/main/backend/app/api/router.py) **从未调用它**，导致运行期 `default_prompt_registry` 为空。 |
| **P1-1** | 深度报告 AVGO/LLY 全文照抄 NVDA（Blackwell、EPS `$0.81`、营收 `$35.08B`）；首页 NVDA 写死 `$145.89`；Themes 停在 11/15 且卡“加载中...” | `20a3753` 漏改了 7 个前端页面：[`StockDeepDiveView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/StockDeepDiveView.tsx)（第 64–100、310、322 行）、`StockCompareView`、`LongTermView`、`PortfolioView`、[`ThemesView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/ThemesView.tsx)、`WatchlistsView` 仍带静默 Mock 兜底；[`DashboardPage.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/dashboard/DashboardPage.tsx) 完全未接后端 API；[`BuyDecisionView.tsx:252`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/BuyDecisionView.tsx) 仍残留 `?? 145.89`。 |
| **P1-2** | 筛选器“开始全池策略筛选”点击无反应；标普 500 标题写 510 只、徽标写 519 只 | [`ScreenerConsoleView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/ScreenerConsoleView.tsx) 写死了 `mockStrategyOptions`（发送 `strategy_id='trend_following'`），与后端实际策略 ID 不匹配；报错时用 `window.alert()` 而非页内 Error Banner，导致看似无反应。前端静态文案与后端 [`UniverseManager.list_universes()`](https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/screener/universe.py) 的 `symbol_count` 未统一数据源。 |
| **P1-3** | 首页/研究页把北京时间 18:12 错标成 `18:12 (EST)` | [`frontend/src/utils/format.ts:44`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/utils/format.ts) 的 `formatDateTime()` 未指定 `timeZone`（输出浏览器本地时区），而 [`DataFreshnessTag.tsx:18,50`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/components/compliance/DataFreshnessTag.tsx) 硬拼了 `(EST)` 后缀。 |
| **P2-1** | 买入决策页切换 AVGO/LLY 后地址栏仍是 `symbol=NVDA` | [`ResearchPage.tsx:120`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/ResearchPage.tsx) 渲染 `<BuyDecisionView initialSymbol={currentSymbol} />` 时漏传 `onSelectSymbol={handleSelectSymbol}`，且 `BuyDecisionView` 提交表单时未同步 URL 查询参数。 |

---

## 二、批次 A：P0 紧急止血修复（必须最先交付验证）

### 任务 A1（P0-1）：修复 `POST /api/v1/sim/accounts` 500 内部错误并验证全流程

1. **修复 JSONB 序列化崩溃**：
   - 修改 [`backend/app/modules/simbroker/service.py`](https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/simbroker/service.py) 第 96 行：将 `fee_model=req.fee_model.model_dump()` 改为 `fee_model=req.fee_model.model_dump(mode="json")`。
   - 全量排查 `backend/app/modules/` 下所有写入 PostgreSQL `JSONB` 列的 `model_dump()` 调用，统一改为 `model_dump(mode="json")`，杜绝同类 `Decimal`/`UUID`/`datetime` 序列化 500 异常。
2. **补充真实 PostgreSQL 集成测试**：
   - 在 `backend/tests/integration/` 中新增基于真实 Postgres 容器的模拟盘端到端闭环测试：`POST /api/v1/sim/accounts`（`$100,000`）→ `GET /api/v1/sim/accounts` → `POST /orders`（买入 NVDA）→ `POST /orders`（卖出）→ `DELETE /orders/{id}`（撤单）→ `POST /accounts/{id}/reset`（重置账户），确保每一步 HTTP 状态码与落库数据 100% 正确。
3. **前端验证**：
   - 确认账户创建成功后，[`AccountOverviewView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/simbroker/AccountOverviewView.tsx) 的“重置账户”按钮可见且可正常触发二次确认弹窗完成重置。

### 任务 A2（P0-2）：在后端启动与路由接线时注册全部 AI 研究与主题提示词模板

1. **修复启动注册缺失**：
   - 在 [`backend/app/core/lifecycle.py`](https://github.com/sysplex/AI-repository/blob/main/backend/app/core/lifecycle.py) 的 `on_startup()` 及 [`backend/app/api/router.py`](https://github.com/sysplex/AI-repository/blob/main/backend/app/api/router.py) 初始化阶段，显式调用：
     ```python
     from app.modules.ai.prompts import default_prompt_registry
     from app.modules.research.prompts import register_research_prompts

     register_research_prompts(default_prompt_registry)
     ```
   - 同时核查 `backend/app/modules/screener/prompts.py`（`theme_card` 用例）及其他 AI 用例是否已注册至 `default_prompt_registry`，避免 Themes 页生成卡片时报同样错误。
   - 确保 `register_research_prompts()` 幂等（重复调用不报错、不重复叠加版本）。
2. **补充启动自检测试**：
   - 新增测试用例，验证应用启动后 `default_prompt_registry.get_active(use_case)` 对 `research`、`buy_decision`、`technical`、`earnings`、`compare`、`long_term`、`portfolio` 全部返回有效模板（非空、不抛 `NotFound`）。

---

## 三、批次 B：P1/P2 全面清理与体验修复

### 任务 B1（P1-1）：清零剩余 7 个页面的静态 Mock 兜底与硬编码旧财报/旧价格

1. **[`frontend/src/pages/research/StockDeepDiveView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/StockDeepDiveView.tsx)**：
   - 删除 `researchQuery` / `earningsQuery` 中捕获异常后返回 `MOCK_RESEARCH_DATA[symbol] || MOCK_RESEARCH_DATA.NVDA` 与 `MOCK_EARNINGS_DATA.NVDA` 的兜底逻辑；删除第 99–100 行默认回退与第 310、322 行硬编码 `?? 0.81`、`?? 35.08`。
   - 请求失败时渲染明确的页内 Error Alert（含“重试”按钮与 `X-Request-ID`）；加载中显示骨架屏；严禁不同股票串用 NVDA 内容。
2. **其余研究与选股视图**：
   - 按同样标准清理 [`StockCompareView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/StockCompareView.tsx)、[`LongTermView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/LongTermView.tsx)、[`PortfolioView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/PortfolioView.tsx)、[`ThemesView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/ThemesView.tsx) 与 [`WatchlistsView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/WatchlistsView.tsx) 的生产态 Mock 回退（仅在 `VITE_ENABLE_MOCK === 'true'` 时允许使用 Mock）。
   - 修复 [`BuyDecisionView.tsx:252`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/BuyDecisionView.tsx) 的 `payload.current_price ?? 145.89`，无价格数据时显示 `'--'`。
3. **[`frontend/src/pages/dashboard/DashboardPage.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/dashboard/DashboardPage.tsx)**：
   - 移除硬编码的 `marketIndices` 与 `hotStocks`（含写死的 `NVDA $145.89` 与 `2026-11-14`），改为调用后端 `/api/v1/market/*` 实时接口拉取最新指数与热门股报价，加载失败时显示错误态。
4. **[`frontend/src/pages/screener/ThemesView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/ThemesView.tsx)**：
   - 排查 `listThemes()` 导致 `isLoadingThemes` 长时间卡在“加载中...”的原因，为请求设置明确超时与错误态展示，禁止初始化写死 `2026-11-15` 卡片。

### 任务 B2（P1-2）：修复筛选器策略列表、错误反馈与标普 500 数量一致性

1. **动态加载策略列表**：在 [`ScreenerConsoleView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/ScreenerConsoleView.tsx) 中改为调用后端策略接口获取真实 `strategy_id`（严禁发送后端不存在的 `trend_following`）。
2. **页内错误与加载反馈**：用页内红色 Error Banner 替换第 194 行的 `window.alert()`，并确保点击“开始全池策略筛选”后立即展示加载态、轮询状态或明确失败原因。
3. **统一股票池数量口径**：前端所有标普 500 计数（标题、下拉框、池子徽标）统一读取后端 `GET /api/v1/screener/universes` 返回的 `symbol_count`，删除前端硬编码数字；同时核查 [`backend/app/modules/screener/universe.py`](https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/screener/universe.py) 中 `SP500_SYMBOLS` 列表，去除重复或无效代码。

### 任务 B3（P1-3）：修复美东时区格式化错乱

1. 修改 [`frontend/src/utils/format.ts`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/utils/format.ts) 的 `formatDateTime(isoString, timeZone = 'America/New_York')`，在 `toLocaleString` 中显式传入 `timeZone` 参数。
2. 修改 [`frontend/src/components/compliance/DataFreshnessTag.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/components/compliance/DataFreshnessTag.tsx)，将时间戳真正转换为 `America/New_York` 时区后再标注 `(ET)`（自动匹配 EST/EDT），彻底消除“北京时间标成 EST”的错乱，并同步更新 `compliance.test.ts`。

### 任务 B4（P2-1）：修复买入决策页地址栏 `symbol` 参数联动

1. 在 [`frontend/src/pages/research/BuyDecisionView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/BuyDecisionView.tsx) 的 `BuyDecisionViewProps` 中新增 `onSelectSymbol?: (symbol: string) => void`，并在 `handleSubmit` 触发新标的评估时调用 `onSelectSymbol?.(cleanSym)`。
2. 在 [`frontend/src/pages/research/ResearchPage.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/ResearchPage.tsx) 第 120 行补传 `<BuyDecisionView initialSymbol={currentSymbol} onSelectSymbol={handleSelectSymbol} />`，并确保 `BuyDecisionView` 响应 `initialSymbol` 变化。

---

## 四、本轮交付验收标准（Definition of Done）

部署新版本镜像前，必须全部通过以下真实环境冒烟验证（**严禁在 `VITE_ENABLE_MOCK=true` 下验收**）：

1. **模拟盘全链路（P0-1）**：新建 `Test 2026-11-23`（`$100,000`）返回 `201 Created`、刷新不消失 → 下单买入 NVDA 刷新保留 → 快速平仓/卖出生效 → 撤单生效 → 点击“重置账户”确认后清零持仓并恢复 `$100,000`。
2. **AI 买入决策与深度研报（P0-2 + P1-1）**：分别对 `NVDA`、`AVGO`、`LLY` 执行买入决策与深度研报，均不再报 `No active prompt template` 错误，三者正文、股价与财报数据完全独立且与真实最新行情/财报一致，无任何写死的 `Blackwell` / `$0.81` / `$35.08B` / `$145.89`。
3. **筛选器与 Themes（P1-2）**：点击“开始全池策略筛选”有明确进度与真实结果或页内报错；标普 500 数量全页一致；Themes 页不再卡“加载中...”且无 `2026-11-15` 静态旧戳。
4. **时区与 URL（P1-3 + P2-1）**：`DataFreshnessTag` 显示真实美东时间（`ET`）；在买入决策页切换 `AVGO` 后地址栏实时变为 `?tab=buy-decision&symbol=AVGO`。
5. **CI 与发布规范**：7 项 CI 门禁全绿，按不可变版本标签发布新镜像（禁止仅推 `latest`）并触发 Argo CD 滚动更新。
