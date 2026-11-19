# StockPilot P0 缺陷修复与新版本迭代指令（DIRECTOR_P0_FIX_DIRECTIVES.md）

> **签发角色**：项目总监（Project Director）
>
> **适用基线**：`main` 分支 `118b41d38ed938070cf443bc5324ca29212c14ee`
>
> **执行对象**：Antigravity
>
> **目标版本**：修复完成并通过全链路验收后，按不可变版本规范发布新迭代（建议标签：`v0.6.1` 或下一 SemVer 补丁/小版本）

## 一、问题背景与根因定性

在跨浏览器端到端实测中，StockPilot 暴露出模拟盘无法持久化、操作无响应、筛选器与 AI 买入判断返回静态假数据以及日期停留在 `2026-11-15` 等严重阻塞问题。经代码审计，根因如下：

1. **生产前端存在“静默吞错 + 硬编码 Mock 兜底”反模式**：多个核心页面直接以 `mockData` 初始化状态，并在 `try/catch` 中静默吞掉 `401`/网络/服务端异常，强行回退至写死的 `$114,950` 账户、11 月 15 日时间戳、6 只写死筛选股与 `NVDA` 买入判断模板，甚至在下单与开户失败时伪造本地假成功反馈。

2. **模拟盘“快速平仓/卖出”传参链路断裂**：父组件丢弃了子组件传出的 `(symbol, 'sell')` 参数。

3. **缺少“重置账户”前后端能力**：前后端均未实现模拟盘账户重置接口与界面入口。

## 二、P0 强制修复任务清单

### 任务 1（P0-1）：彻底清除生产模式的静默 Mock 兜底与假成功反馈

必须改造以下文件，严禁在生产运行时静默降级为静态 Mock 数据（如需本地纯前端演示，仅允许通过显式环境变量 `VITE_ENABLE_MOCK=true` 开启，且默认必须为 `false`）：

1. [**`frontend/src/pages/simbroker/SimBrokerPage.tsx`**](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/simbroker/SimBrokerPage.tsx)

   * 移除 `accounts`、`overview`、`positions`、`orders`、`trades`、`performance`、`risk` 的 `mock*` 初始值，改为空数组 / `null` + `loading` / `error` 状态。

   * 移除 `loadAccounts()` 与 `loadAccountData()` 中的 `// Keep mock accounts` 和 `// Keep mock data` 静默兜底逻辑；当 `simbrokerApi.listAccounts()` 返回空数组 `[]` 时，展示真实的“暂无模拟账户，请创建账户”空状态，禁止保留 `acc-001`。

   * 移除 `handleCreateAccountSubmit()` 中的 `acc-local-${Date.now()}` 内存伪造逻辑；调用 `POST /api/v1/sim/accounts` 失败时必须展示明确错误提示并保留表单，成功后重新拉取后端账户列表并选中新建账户。

2. [**`frontend/src/pages/simbroker/OrderTradePanelView.tsx`**](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/simbroker/OrderTradePanelView.tsx)

   * 移除 `handleSubmitOrder()` 中捕获异常后弹出“订单模拟已确认”的假成功逻辑；下单失败必须原样展示后端错误原因（含校验错误、资金/持仓不足、网络或鉴权失败），禁止伪造订单成功。

3. [**`frontend/src/pages/simbroker/PositionsAndOrdersView.tsx`**](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/simbroker/PositionsAndOrdersView.tsx)

   * 移除 `handleCancelOrder()` 中吞掉错误并静默 `onRefresh()` 的逻辑；撤单失败必须弹出错误提示，撤单成功后再刷新订单与账户资产。

4. [**`frontend/src/pages/screener/ScreenerConsoleView.tsx`**](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/screener/ScreenerConsoleView.tsx)

   * 移除 `currentRun` 默认初始化为 `mockCompletedScreenerRun`（写死 `NVDA 96.5` / `AVGO 92.1` / `LLY 88.6` 与 `2026-11-15`）的逻辑，改为从真实后端接口拉取最新筛选运行记录或展示空态。

5. [**`frontend/src/pages/research/BuyDecisionView.tsx`**](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/research/BuyDecisionView.tsx)

   * 删除 `catch` 中的 `return MOCK_BUY_DECISION_DATA[activeParams.symbol] || MOCK_BUY_DECISION_DATA.NVDA` 兜底代码，杜绝任意股票（如 `AVGO`、`LLY`）退化为 `NVDA` 写死文案。

6. **全局鉴权与错误透明化（[`frontend/src/api/client.ts`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/api/client.ts)）**

   * 确保所有受保护路由在 `401`（触发 `auth:unauthorized`）时立即跳转至登录页并提示重新登录；所有 `4xx/5xx` 异常在页面通过 Toast/Alert 明确展示错误码与 `X-Request-ID`。

### 任务 2（P0-2）：修复模拟盘“快速平仓 / 卖出”参数透传

1. 在 [`frontend/src/pages/simbroker/SimBrokerPage.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/simbroker/SimBrokerPage.tsx) 中新增 `prefillOrder` 状态（包含 `symbol`、`side`、可选 `quantity`）。

2. 将传给 [`PositionsAndOrdersView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/simbroker/PositionsAndOrdersView.tsx) 的回调从 `onQuickTrade={() => setActiveTab('trade')}` 修复为接收 `(symbol, side, quantity)`，更新 `prefillOrder` 并切换至 `'trade'` 标签页。

3. 在 [`OrderTradePanelView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/simbroker/OrderTradePanelView.tsx) 中消费 `prefillOrder`，自动填入对应标的代码、选中“卖出（SELL）”方向并预填可卖数量（若传入）。

### 任务 3（P0-3）：补齐模拟盘“重置账户”前后端闭环

1. **后端（[`backend/app/modules/simbroker/api.py`](https://github.com/sysplex/AI-repository/blob/main/backend/app/modules/simbroker/api.py) 及 Service/Repository 层）**

   * 新增接口：`POST /api/v1/sim/accounts/{account_id}/reset`（需严格校验 `request.state.user` 与账户归属租户隔离）。

   * 在单个数据库事务中完成：取消全部未成交挂单、清空当前持仓、将现金余额与权益恢复为初始本金（或请求体指定的 `Decimal` 初始资金，严禁 `float`），并写入一条可审计的账户重置流水记录，返回重置后的最新 `AccountOverview`。

   * 补充单元测试与集成测试，覆盖正常重置、跨租户越权拒绝、以及重置后持仓/挂单/资金一致性校验。

2. **前端（[`frontend/src/api/simbroker.ts`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/api/simbroker.ts) 与 [`AccountOverviewView.tsx`](https://github.com/sysplex/AI-repository/blob/main/frontend/src/pages/simbroker/AccountOverviewView.tsx)）**

   * 在 `simbrokerApi` 中新增 `resetAccount(accountId, payload?)` 方法。

   * 在 `AccountOverviewView` 账户操作栏新增“重置账户”按钮，点击后弹出二次确认弹窗（提示将清空持仓与挂单并恢复初始本金），确认后调用后端接口并刷新全页资产、持仓与订单数据。

### 任务 4（P0-4）：排查并验证前后端网关代理、鉴权与实时行情日期

1. 核查 [frontend/nginx.conf](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/frontend/nginx.conf)、[deploy/docker-compose.yml](https://www.google.com/search?q=https://github.com/sysplex/AI-repository/blob/main/deploy/docker-compose.yml) 与 [`deploy/k8s/ingress.yaml`](https://github.com/sysplex/AI-repository/blob/main/deploy/k8s/ingress.yaml)，确保前端 `/api/v1/*` 请求在 Docker Compose 与 K8s Traefik Ingress 两种部署模式下均能正确转发至 `stockpilot-api:8000`，且完整保留 `Authorization` 与 `Idempotency-Key` 请求头。

2. 验证行情数据服务（`marketdata`）与筛选器/研究模块在实时联调时返回当前最新交易日数据，不得再出现静态写死的 `2026-11-15` 日期；验证 `AVGO`、`LLY`、`NVDA` 在 AI 买入判断接口返回各自独立的分析结论与事实溯源。

## 三、验收标准（Definition of Done）与版本迭代要求

在提交 PR 并发布新版本前，Antigravity 必须全部满足以下验收项：

1. **CI 7 项门禁全绿**：`lint`、`typecheck (mypy --strict)`、`architecture (import-linter)`、`test (覆盖率 >= 80%)`、`security (pip-audit + gitleaks)`、`docker`、`docs` 全部通过（合并 PR 时同步更新任务文档，避免额外提交触发 Concurrency 取消前序测试）。

2. **端到端真实持久化验证（严禁 Mock）**：

   * 新建 `$100,000` 模拟账户 → 强制刷新页面（F5）→ 账户仍存在且资产准确。

   * 提交 2 笔 `NVDA` 订单 → 强制刷新页面 → 订单与持仓在列表持久化保留。

   * 点击持仓“快速平仓/卖出” → 自动跳转并预填卖出标的与方向 → 成功提交卖单；点击挂单“撤单” → 状态实时变更且刷新后保持已撤单。

   * 点击“重置账户”并确认 → 持仓/挂单清零、资金恢复初始值、刷新后保持重置状态。

   * 分别查询 `NVDA`、`AVGO`、`LLY` 的 AI 买入判断 → 三者内容相互独立且基于各自最新行情与财报事实，数据日期为最新有效交易日。

3. **不可变版本发布**：按 `GEMINI.md` 规范打语义化新版本 Git Tag（含双标签镜像推送至 Harbor，并在 GitHub Release 说明中记录 Commit SHA 与修复清单，切勿泄露任何内网 IP 或明文凭据）。