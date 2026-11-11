# 04 模块说明书

每个模块按统一模板：**职责 / 非职责 / 对外接口 / 依赖 / 数据 / 异常与降级 / 验收标准 / 估时**。
验收细则见 [08-test-plan.md](08-test-plan.md)。开发顺序见 [README](README.md)。

---

## M0 项目骨架与部署

- **职责**：仓库结构、配置管理、日志、错误体系、数据库连接与迁移、事件总线、NYSE 交易日历、Docker Compose、CI、健康检查。
- **非职责**：任何业务逻辑。
- **对外接口**：`core.config.settings`、`core.errors.AppError`、`core.db.session`、`core.events.bus`、`core.calendar.next_trading_day()` / `is_trading_day()`、`GET /healthz`、`GET /readyz`。
- **依赖**：无。
- **数据**：Alembic 初始迁移；`audit_log` 表。
- **异常与降级**：启动时配置缺失直接失败并给出明确提示。
- **验收标准**：`docker compose up` 一条命令拉起 api/worker/postgres/redis/nginx；CI 跑通 ruff、mypy、pytest、import-linter、镜像构建；交易日历对 2024–2026 年节假日、半日市、夏令时切换用例正确。
- **估时**：约 1 周。

## M1 用户与多租户（identity）

- **职责**：注册、登录、登出、令牌刷新、密码重置（邮件）、角色、用户设置、配额策略、审计。
- **非职责**：支付与订阅（v1 不做）。
- **对外接口**：`register / login / refresh / logout / get_current_user / update_settings`；依赖注入 `current_user`；`require_role("admin")`；`TenantRepository` 基类（强制 `user_id` 过滤）。
- **依赖**：core。
- **数据**：`users`、`refresh_tokens`、`audit_log`、`ai_usage`。
- **异常与降级**：登录失败限流（IP+账号）；令牌吊销即时生效。
- **验收标准**：用户 A 无法访问用户 B 任何私有资源（自动化越权测试覆盖每个私有端点）；密码 argon2；刷新令牌可吊销；登录/改密写审计。
- **估时**：约 1 周。

## M2 数据服务（marketdata）

- **职责**：通过 `DataProvider` 获取行情/财报/新闻/评级/公司资料/股票池；缓存；落库；统一数据模型；数据新鲜度标注；公司行动。
- **非职责**：指标计算、分析解读。
- **对外接口**：`DataService.get_bars / get_quote / get_fundamentals / get_statements / get_earnings / get_news / get_ratings / get_profile / get_universe / build_facts(symbol, scope)`。
  其中 `build_facts` 输出供 AI 使用的结构化事实字典与快照 id。
- **依赖**：core。适配器：`yfinance`（v1），`polygon`/`tiingo`（预留）。
- **数据**：共享表见 03 文档 3.2。
- **异常与降级**：外部超时/限流 → 指数退避重试 → 回退缓存并返回 `stale=true` 与 `as_of`；彻底失败返回明确错误，**不返回猜测数据**。
- **验收标准**：契约测试套件对任一适配器通用；录制 fixture 回放离线可测；缓存命中不访问外部；复权价与拆股案例（如 NVDA 2024-06 拆股）正确；字段缺失显式为 `null` 并列入 `missing_fields`。
- **估时**：约 1 周。

## M3 指标与策略引擎（strategy）

- **职责**：技术指标（均线、RSI、MACD、ATR、成交量、支撑压力、波段高低点）；策略注册表；`Signal` 输出；止损/目标位计算；回测引擎（复用 Broker 接口）。
- **非职责**：AI 解读；下单。
- **对外接口**：`StrategyService.list_strategies()`、`evaluate(strategy_id, symbol, as_of, params)`、`scan(strategy_id, universe, as_of, params)`、`compute_technical_snapshot(symbol, as_of)`、`backtest(...)`。
- **v1 策略**：`turtle_20/55`、`dow_trend`（多周期趋势过滤）、`pullback_rsi`（上升趋势回调）、`reversal_123`、`value_basic`、`growth_basic`、`dividend_basic`。缠论、江恩为后续策略，仅作辅助。
- **依赖**：marketdata。
- **数据**：`screener_*` 由 M8 使用；本模块无独立业务表（回测结果可存 `backtest_runs`，M3 后期加）。
- **异常与降级**：数据不足（如不足 55 根 K 线）返回 `insufficient_data`，不产生信号。
- **验收标准**：指标与参考实现（如 TA-Lib/手算样例）误差 < 1e-6；**防未来函数测试**：对任意 `as_of`，把其后数据篡改，信号不变；每个策略有“买入/不买入”两组固定样例。
- **估时**：约 1 周（后续策略按需加）。

## M4 模拟盘引擎（simbroker）

- **职责**：虚拟账户、订单校验、撮合、持仓、盈亏、净值快照、交易日志、手续费/滑点、PDT 模拟、拆股/分红处理。
- **非职责**：信号生成、AI。
- **对外接口**：实现 `Broker`；`SimService.create_account / deposit / submit_order / cancel_order / positions / trades / performance(account_id)`；`process_market_close(trade_date)`（定时调用，撮合、更新净值）。
- **撮合规则（v1）**：
  - 市价单：下一根 K 线开盘价 ± 滑点成交。
  - 限价买：开盘价 ≤ 限价则按开盘价成交；否则当根最低价 ≤ 限价时按限价成交。限价卖对称。
  - 止损单：触及后按触发价与开盘价较不利者成交。
  - 资金不足、超卖、数量非法 → `REJECTED`；`idempotency_key` 重复返回原订单。
  - 默认手续费 0，可配置（每股/比例/最低）。
- **依赖**：marketdata、core。
- **数据**：`sim_*`、`equity_snapshots`、`trade_journal`。
- **异常与降级**：行情缺失则订单保持 `ACCEPTED` 并告警，不得用旧价成交。
- **验收标准**：不变量测试全过（现金守恒、净值恒等、不超卖）；与手算样例逐笔一致；拆股后持仓市值不变；并发重复提交只成交一次。
- **估时**：约 1 周。

## M5 AI 核心框架（ai）

- **职责**：`LLMClient` 适配器；提示词加载与版本管理；输出 Schema 校验；**数字溯源校验**；缓存；配额与预算熔断；成本统计；任务执行包装；重试与降级。
- **非职责**：具体业务用例（在 M6/M7）。
- **对外接口**：`AIService.run(use_case, facts, params, user_id) -> AnalysisReport`；`PromptRegistry.get(use_case, version)`；`QuotaService.check(user_id)`。
- **依赖**：core、identity（配额）。
- **数据**：`ai_reports`、`data_snapshots`、`ai_usage`。
- **异常与降级**：Schema 校验失败 → 带错误信息自动重试 1 次 → 仍失败标记 `failed`（不展示半成品）；LLM 不可用 → 返回任务失败，不返回缓存以外的内容；超配额 → 明确错误码。
- **验收标准**：Mock LLM 跑通全流程；故意返回缺字段/越界枚举/编造数字的 mock 均被拦截；同参数同快照命中缓存且不产生成本；配额耗尽拒绝；每次调用成本入库。
- **估时**：约 1 周。

## M6 AI 用例 A：研究 / 买入决策 / 技术面 / 财报解读（research）

- **职责**：F2、F3、F6（解释部分）、F7 的用例编排：取 facts → 调 AI → 保存 → 返回。
- **对外接口**：`ResearchService.research(symbol)`、`buy_decision(symbol, price, horizon, risk_level)`、`technical(symbol)`、`earnings(symbol)`。
- **依赖**：marketdata、strategy、ai。
- **关键约束**：
  - 技术面的进场/止损/目标**由代码给出**，AI 仅解释；
  - 买入决策的“想买价相对现价位置、相对 52 周区间位置、相对估值区间位置”由代码计算后喂入；
  - 财报解读的 EPS/收入的预期与实际来自数据源，缺失则输出“数据缺失”。
- **验收标准**：对 5 只代表性股票（大盘科技、周期、高分红、亏损成长、小盘）各用例输出通过 Schema 与数字溯源；新手可读性抽检（无未解释术语）；每份报告含免责声明、数据时间、数据来源字段。
- **估时**：约 1 周。

## M7 AI 用例 B：对比 / 长期持有 / 组合配置（research）

- **职责**：F4、F5、F8。
- **对外接口**：`compare(symbols[2..8])`、`long_term(symbol, years)`、`portfolio(amount, symbols, risk_level, goal)`。
- **关键约束**：
  - 对比：代码生成同口径指标表与各维度分位排名，AI 解释并给适合人群；
  - 长期：输出“论文破裂条件”，每条须对应可监控指标，供 M10 做持续监控；
  - 组合：配比由**代码优化**（风险平价/最小方差/约束上限，单股上限、现金下限），AI 解释理由，不得自行改数字。
- **验收标准**：配比之和 = 100%（含现金）；单股上限被遵守；破裂条件均含“指标 + 阈值 + 数据字段”。
- **估时**：约 1 周。

## M8 筛选器与主题自选（screener）

- **职责**：股票池管理（标普500、纳指100、自定义）、策略筛选任务、主题股票池（F9）、结果排名、一键送入研究/对比。
- **对外接口**：`ScreenerService.run(strategy_id, universe, params)`（异步）、`get_run(id)`、`list_themes()`、`get_theme(theme_id)`、`generate_theme_cards(theme_id)`（AI 说明，数据来自 facts）。
- **依赖**：strategy、marketdata、research。
- **数据**：`screener_runs`、`screener_results`、`watchlists`、`watchlist_items`。
- **异常与降级**：单只股票数据失败不中断整体，结果中标注失败项。
- **验收标准**：对固定历史日期筛选结果可复现；500 只股票日线筛选 < 3 分钟（缓存预热后）；主题卡片字段齐全。
- **估时**：约 1 周。

## M9 Web 前端

- **职责**：所有页面，Lightweight Charts K 线叠加信号，任务进度展示，响应式。
- **页面**：登录/注册、仪表盘（市场环境）、自选与主题、个股详情（K线/技术/AI 研究）、买入决策、对比、长期持有、组合配置、财报、筛选器、模拟账户（持仓/订单/净值/日志）、设置、（管理员）用量。
- **对外接口**：仅消费 `/api/v1`（OpenAPI 生成 TypeScript 客户端，保证契约同步）。
- **依赖**：各模块 API。
- **验收标准**：核心路径端到端（见 08 文档 E2E-01）；所有 AI 页面显示数据时间、提示词版本、免责声明；任务失败/配额耗尽/数据过期均有明确提示。
- **估时**：约 2 周，可与 M6–M8 并行迭代。

## M10 调度、提醒、日报、复盘、运维（scheduler / notify）

- **职责**：收盘后任务链（更新数据 → 撮合 → 净值快照 → 策略扫描 → 日报）；价格/信号/财报日提醒；论文破裂监控；AI 建议复盘回填；通知渠道；监控告警；备份。
- **对外接口**：`AlertService`、`ReviewService.outcomes()`、`Notifier` 实现。
- **依赖**：各业务模块、事件总线。
- **异常与降级**：任务幂等、可重跑；失败重试并告警；通知失败不阻塞主流程。
- **验收标准**：夏令时切换日调度正确；任务重复执行结果一致；复盘页能展示按 verdict 分组的 5/20/60 日平均收益与相对 SPY 超额；备份恢复演练通过。
- **估时**：约 1 周。

---

## 模块依赖速查

| 模块 | 依赖 |
|---|---|
| M0 | — |
| M1 | M0 |
| M2 | M0 |
| M3 | M2 |
| M4 | M0, M2 |
| M5 | M0, M1 |
| M6 | M2, M3, M5 |
| M7 | M2, M3, M5, M6 |
| M8 | M2, M3, M6 |
| M9 | 各 API |
| M10 | 全部 |
