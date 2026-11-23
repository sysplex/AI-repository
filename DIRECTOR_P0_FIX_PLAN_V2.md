# StockPilot P0/P1 深度排查与修复迭代计划（DIRECTOR_P0_FIX_PLAN_V2.md）

> **签发角色**：项目总监（Project Director）
>
> **审计基线**：`main` 分支 [20a3753](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/commit/20a3753)（2026-11-23 跨浏览器复测反馈）
>
> **执行对象**：Antigravity
>
> **迭代策略**：分两个严格验收批次执行——**批次 A（P0 止血：模拟盘建户 + AI 提示词模板注册）** 必须先跑通并验证，再推进 **批次 B（P1/P2 彻底清零残余 Mock、筛选器、时区与 URL 联动）**。

## 一、本轮复测根因总览

| 优先级 | 复测现象 | 精确根因与代码位置 | 
| ----- | ----- | ----- | 
| **P0-1** | 创建模拟账户 3 次均报红字“服务器内部错误”，模拟盘完全不可用 | [backend/app/modules/simbroker/service.py:96](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/simbroker/service.py) 使用 `fee_model=req.fee_model.model_dump()` 写入 PostgreSQL `JSONB` 列，但 [FeeModelConfig](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/simbroker/schemas.py) 含 `Decimal` 字段，`asyncpg` 序列化 `Decimal` 到 `JSONB` 直接抛 `TypeError: Object of type Decimal is not JSON serializable` → HTTP 500。 | 
| **P0-2** | 所有股票 AI 买入决策报错 `No active prompt template version found for use_case='buy_decision'` | [backend/app/modules/research/prompts.py:590](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/research/prompts.py) 定义了 `register_research_prompts(registry)`（含 M6/M7 全部 7 个模板），但 [backend/app/core/lifecycle.py](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/backend/app/core/lifecycle.py) 与 [backend/app/api/router.py](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/backend/app/api/router.py) **从未调用它**，导致运行期 `default_prompt_registry` 为空。 | 
| **P1-1** | 深度报告 AVGO/LLY 全文照抄 NVDA（Blackwell、EPS `$0.81`、营收 `$35.08B`）；首页 NVDA 写死 `$145.89`；Themes 停在 11/15 且卡“加载中...” | `20a3753` 漏改了 7 个前端页面：[StockDeepDiveView.tsx](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/StockDeepDiveView.tsx)（第 64–100、310、322 行）、`StockCompareView`、`LongTermView`、`PortfolioView`、[ThemesView.tsx](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/ThemesView.tsx)、`WatchlistsView` 仍带静默 Mock 兜底；[DashboardPage.tsx](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/dashboard/DashboardPage.tsx) 完全未接后端 API；[`BuyDecisionView.tsx:252`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/BuyDecisionView.tsx) 仍残留 `?? 145.89`。 | 
| **P1-2** | 筛选器“开始全池策略筛选”点击无反应；标普 500 标题写 510 只、徽标写 519 只 | [`ScreenerConsoleView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/ScreenerConsoleView.tsx) 写死了 `mockStrategyOptions`（发送 `strategy_id='trend_following'`），与后端实际策略 ID 不匹配；报错时用 `window.alert()` 而非页内 Error Banner，导致看似无反应。前端静态文案与后端 [UniverseManager.list_universes()](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/screener/universe.py) 的 `symbol_count` 未统一数据源。 | 
| **P1-3** | 首页/研究页把北京时间 18:12 错标成 `18:12 (EST)` | [frontend/src/utils/format.ts:44](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/utils/format.ts) 的 `formatDateTime()` 未指定 `timeZone`（输出浏览器本地时区），而 [DataFreshnessTag.tsx:18,50](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/components/compliance/DataFreshnessTag.tsx) 硬拼了 `(EST)` 后缀。 | 
| **P2-1** | 买入决策页切换 AVGO/LLY 后地址栏仍是 `symbol=NVDA` | [ResearchPage.tsx:120](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/ResearchPage.tsx) 渲染 `<BuyDecisionView initialSymbol={currentSymbol} />` 时漏传 `onSelectSymbol={handleSelectSymbol}`，且 `BuyDecisionView` 提交表单时未同步 URL 查询参数。 | 

## 二、批次 A：P0 紧急止血修复（必须最先交付验证）

### 任务 A1（P0-1）：修复 `POST /api/v1/sim/accounts` 500 内部错误并验证全流程

1. **修复 JSONB 序列化崩溃**：

   * 修改 [backend/app/modules/simbroker/service.py](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/simbroker/service.py) 第 96 行：将 `fee_model=req.fee_model.model_dump()` 改为 `fee_model=req.fee_model.model_dump(mode="json")`。

   * 全量排查 `backend/app/modules/` 下所有写入 PostgreSQL `JSONB` 列的 `model_dump()` 调用，统一改为 `model_dump(mode="json")`，杜绝同类 `Decimal`/`UUID`/`datetime` 序列化 500 异常。

2. **补充真实 PostgreSQL 集成测试**：

   * 在 `backend/tests/integration/` 中新增基于真实 Postgres 容器的模拟盘端到端闭环测试：`POST /api/v1/sim/accounts`（`$100,000`）→ `GET /api/v1/sim/accounts` → `POST /orders`（买入 NVDA）→ `POST /orders`（卖出）→ `DELETE /orders/{id}`（撤单）→ `POST /accounts/{id}/reset`（重置账户），确保每一步 HTTP 状态码与落库数据 100% 正确。

3. **前端验证**：

   * 确认账户创建成功后，[`AccountOverviewView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/simbroker/AccountOverviewView.tsx) 的“重置账户”按钮可见且可正常触发二次确认弹窗完成重置。

### 任务 A2（P0-2）：在后端启动与路由接线时注册全部 AI 研究与主题提示词模板

1. **修复启动注册缺失**：

   * 在 [backend/app/core/lifecycle.py](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/backend/app/core/lifecycle.py) 的 `on_startup()` 及 [backend/app/api/router.py](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/backend/app/api/router.py) 初始化阶段，显式调用：

     ```
     from app.modules.ai.prompts import default_prompt_registry
     from app.modules.research.prompts import register_research_prompts
     
     register_research_prompts(default_prompt_registry)
     
     ```

   * 同时核查 `backend/app/modules/screener/prompts.py`（`theme_card` 用例）及其他 AI 用例是否已注册至 `default_prompt_registry`，避免 Themes 页生成卡片时报同样错误。

   * 确保 `register_research_prompts()` 幂等（重复调用不报错、不重复叠加版本）。

2. **补充启动自检测试**：

   * 新增测试用例，验证应用启动后 `default_prompt_registry.get_active(use_case)` 对 `research`、`buy_decision`、`technical`、`earnings`、`compare`、`long_term`、`portfolio` 全部返回有效模板（非空、不抛 `NotFound`）。

## 三、批次 B：P1/P2 全面清理与体验修复

### 任务 B1（P1-1）：清零剩余 7 个页面的静态 Mock 兜底与硬编码旧财报/旧价格

1. [**frontend/src/pages/research/StockDeepDiveView.tsx**](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/StockDeepDiveView.tsx)：

   * 删除 `researchQuery` / `earningsQuery` 中捕获异常后返回 `MOCK_RESEARCH_DATA[symbol] || MOCK_RESEARCH_DATA.NVDA` 与 `MOCK_EARNINGS_DATA.NVDA` 的兜底逻辑；删除第 99–100 行默认回退与第 310、322 行硬编码 `?? 0.81`、`?? 35.08`。

   * 请求失败时渲染明确的页内 Error Alert（含“重试”按钮与 `X-Request-ID`）；加载中显示骨架屏；严禁不同股票串用 NVDA 内容。

2. **其余研究与选股视图**：

   * 按同样标准清理 [StockCompareView.tsx](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/StockCompareView.tsx)、[LongTermView.tsx](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/LongTermView.tsx)、[PortfolioView.tsx](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/PortfolioView.tsx)、[ThemesView.tsx](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/ThemesView.tsx) 与 [WatchlistsView.tsx](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/WatchlistsView.tsx) 的生产态 Mock 回退（仅在 `VITE_ENABLE_MOCK === 'true'` 时允许使用 Mock）。

   * 修复 [`BuyDecisionView.tsx:252`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/BuyDecisionView.tsx) 的 `payload.current_price ?? 145.89`，无价格数据时显示 `'--'`。

3. [**frontend/src/pages/dashboard/DashboardPage.tsx**](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/dashboard/DashboardPage.tsx)：

   * 移除硬编码的 `marketIndices` 与 `hotStocks`（含写死的 `NVDA $145.89` 与 `2026-11-14`），改为调用后端 `/api/v1/market/*` 实时接口拉取最新指数与热门股报价，加载失败时显示错误态。

4. [**frontend/src/pages/screener/ThemesView.tsx**](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/ThemesView.tsx)：

   * 排查 `listThemes()` 导致 `isLoadingThemes` 长时间卡在“加载中...”的原因，为请求设置明确超时与错误态展示，禁止初始化写死 `2026-11-15` 卡片。

### 任务 B2（P1-2）：修复筛选器策略列表、错误反馈与标普 500 数量一致性

1. **动态加载策略列表**：在 [`ScreenerConsoleView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/ScreenerConsoleView.tsx) 中改为调用后端策略接口获取真实 `strategy_id`（严禁发送后端不存在的 `trend_following`）。

2. **页内错误与加载反馈**：用页内红色 Error Banner 替换第 194 行的 `window.alert()`，并确保点击“开始全池策略筛选”后立即展示加载态、轮询状态或明确失败原因。

3. **统一股票池数量口径**：前端所有标普 500 计数（标题、下拉框、池子徽标）统一读取后端 `GET /api/v1/screener/universes` 返回的 `symbol_count`，删除前端硬编码数字；同时核查 [backend/app/modules/screener/universe.py](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/screener/universe.py) 中 `SP500_SYMBOLS` 列表，去除重复或无效代码。

### 任务 B3（P1-3）：修复美东时区格式化错乱

1. 修改 [frontend/src/utils/format.ts](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/utils/format.ts) 的 `formatDateTime(isoString, timeZone = 'America/New_York')`，在 `toLocaleString` 中显式传入 `timeZone` 参数。

2. 修改 [frontend/src/components/compliance/DataFreshnessTag.tsx](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/components/compliance/DataFreshnessTag.tsx)，将时间戳真正转换为 `America/New_York` 时区后再标注 `(ET)`（自动匹配 EST/EDT），彻底消除“北京时间标成 EST”的错乱，并同步更新 `compliance.test.ts`。

### 任务 B4（P2-1）：修复买入决策页地址栏 `symbol` 参数联动

1. 在 [`frontend/src/pages/research/BuyDecisionView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/BuyDecisionView.tsx) 的 `BuyDecisionViewProps` 中新增 `onSelectSymbol?: (symbol: string) => void`，并在 `handleSubmit` 触发新标的评估时调用 `onSelectSymbol?.(cleanSym)`。

2. 在 [frontend/src/pages/research/ResearchPage.tsx](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/ResearchPage.tsx) 第 120 行补传 `<BuyDecisionView initialSymbol={currentSymbol} onSelectSymbol={handleSelectSymbol} />`，并确保 `BuyDecisionView` 响应 `initialSymbol` 变化。

## 四、本轮交付验收标准（Definition of Done）

部署新版本镜像前，必须全部通过以下真实环境冒烟验证（**严禁在 `VITE_ENABLE_MOCK=true` 下验收**）：

1. **模拟盘全链路（P0-1）**：新建 `Test 2026-11-23`（`$100,000`）返回 `201 Created`、刷新不消失 → 下单买入 NVDA 刷新保留 → 快速平仓/卖出生效 → 撤单生效 → 点击“重置账户”确认后清零持仓并恢复 `$100,000`。

2. **AI 买入决策与深度研报（P0-2 + P1-1）**：分别对 `NVDA`、`AVGO`、`LLY` 执行买入决策与深度研报，均不再报 `No active prompt template` 错误，三者正文、股价与财报数据完全独立且与真实最新行情/财报一致，无任何写死的 `Blackwell` / `$0.81` / `$35.08B` / `$145.89`。

3. **筛选器与 Themes（P1-2）**：点击“开始全池策略筛选”有明确进度与真实结果或页内报错；标普 500 数量全页一致；Themes 页不再卡“加载中...”且无 `2026-11-15` 静态旧戳。

4. **时区与 URL（P1-3 + P2-1）**：`DataFreshnessTag` 显示真实美东时间（`ET`）；在买入决策页切换 `AVGO` 后地址栏实时变为 `?tab=buy-decision&symbol=AVGO`。

5. **CI 与发布规范**：7 项 CI 门禁全绿，按不可变版本标签发布新镜像（禁止仅推 `latest`）并触发 Argo CD 滚动更新。

---

## 五、2026-11-23 复审打回整改清单（修绿 CI 门禁 — 最高优先级）

> **复审基线**：`main` 分支 [`189fd70`](https://github.com/sysplex/AI-repository/commit/189fd70)（`v1.2.6`），对应 [GitHub Actions #268](https://github.com/sysplex/AI-repository/actions/runs/45172732072)（5/7 通过，2 项失败）。  
> **整改纪律**：连续在 CI 红灯状态下打 `v1.2.2`–`v1.2.6` Tag 违反版本发布铁律。**本节全部 4 项修复完成并确认 GitHub Actions 7/7 全绿之前，严禁再打新版本 Tag。**

### 1. 修复 2 个失败的后端集成测试（`test` 任务阻断）

1. **`backend/tests/integration/modules/ai/test_ai_api.py::test_analyze_authenticated_cache_miss`**
   - **失败原因**：`AIService.run()` 调用签名新增了 `llm_client=None` 关键字参数传递，旧测试精确断言 `assert_called_once_with(..., prompt_version='v1')` 未包含 `llm_client=None`。
   - **修复要求**：同步更新该测试断言以匹配最新的 `llm_client=None` 参数（或检查 `call_args` 中核心参数与 `llm_client` 字段）。
2. **`backend/tests/integration/modules/identity/test_me_endpoints.py::test_patch_me_roundtrip_and_audit`**
   - **失败原因**：`UserSettings` 模型新增了 AI 配置字段（`ai_provider`、`google_api_key`、`google_model` 等），接口返回字典多了 3 个键，导致旧测试全量字典等值比对失败。
   - **修复要求**：同步更新测试预期字典，完整覆盖 `UserSettings` 新增字段的默认值与 roundtrip 校验。

### 2. 修复 3 处文档相对路径死链（`docs` 任务阻断）

CI 文档链路检查报错如下：
- `docs/acceptance/M10.md` 引用了不存在的 `../../GEMINI.md`
- `docs/tasks/M10/T07-ops-backup-runbook.md` 引用了不存在的 `../../deploy/K8S.md` 和 `../../../GEMINI.md`

**修复要求**：
- 核对仓库根目录及 `deploy/` 实际存在的文件路径（如根目录 `AGENTS.md`、`DIRECTOR_P0_FIX_PLAN_V2.md` 或 `deploy/k8s/` 下对应部署文档），将上述 3 处无效相对链接修正为真实存在的仓库文档链接（切勿将本地含敏感信息的 `GEMINI.md` 提交至公开仓库）。

### 3. 清除首页残余硬编码假信号与静态指标（`DashboardPage.tsx`）

- **问题位置**：[`frontend/src/pages/dashboard/DashboardPage.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/dashboard/DashboardPage.tsx)
- **修复要求**：
  1. 移除 `getSignalsForSymbol()` 中硬编码的虚假技术信号（`strategy_id: 'dow_trend'`、`strength: 85`、`reasons` 固定文案、`levels: '--'`），改为真实调用策略信号接口 `/api/v1/strategy/evaluate`（或 `/api/v1/strategy/scan`）；接口未就绪或加载中时展示真实加载/空状态，禁止伪造信号。
  2. 移除 `HOT_STOCKS_CONFIG` 中静态写死的 `marketCap`、`aiSignal` 与 `aiScore`（或明确标注为后端未接通字段并从接口/行情元数据获取，不得将静态评分当成实时 AI 评分展示）。

### 4. 修绿验收标准

- 本地与 GitHub Actions 跑通全部 **7/7** 检查（`lint`、`typecheck`、`architecture`、`test >= 80%`、`security`、`docker`、`docs`）。
- 7/7 全绿后，统一发布一个正式稳定版本 Tag（如 `v1.2.7`），并更新 `deploy/k8s/kustomization.yaml` 触发集群同步。
