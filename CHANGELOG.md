# Changelog

格式遵循 Keep a Changelog；按模块分类。

> **维护归属（M0）**：本文件归协调者维护。M0 阶段 T01–T10 一律不改本文件，各任务把条目草稿放进 PR「遗留问题」段；由 T11 一次性汇总写入。见 `AGENTS.md §7` 与 `docs/tasks/M0/README.md` 所有权矩阵。

## [Unreleased]

### Added
- docs: 设计文档集（01–09）
- docs: M0 任务拆分与接口契约
- M0 地基 T01：项目骨架与工具链（Python 3.12 + `uv --frozen`、ruff / `mypy --strict` / import-linter / pytest、Makefile）
- M0 地基 T02–T03：配置校验与结构化日志、请求上下文、统一错误体系
- M0 地基 T04–T06：异步数据层与 Alembic 迁移/审计表、进程内事件总线、NYSE 日历（2024–2026）与可替换时钟
- M0 地基 T07–T08：Redis 客户端、健康探针、Prometheus 指标与生命周期；Docker Compose 全栈、Nginx 代理、非 root 镜像
- M0 地基 T09：GitHub Actions 7 个门禁 job、Dependabot、CODEOWNERS，以及私有仓库无分支保护的替代做法（`docs/ci.md §6.2`）
- M0 地基 T10：共享测试基座、覆盖率门槛 80 与测试指南
- M0 地基 T11：集成验收记录 `docs/acceptance/M0.md`、全链路冒烟与性能基线
- M1 阶段 0：任务总览、接口契约与 T01–T07 任务卡（`docs/tasks/M1/`），M1 Identity 里程碑与 #36–#42 Issue
- M1-T01（#36）：`argon2-cffi` / `PyJWT` / `email-validator` 依赖与 `uv.lock`、7 个可选认证配置项、identity 四张表的 ORM 模型与端口、`0003_identity` 迁移（含 `audit_log.user_id` 外键）、import-linter 契约修正、`docs/03 §3.1` 与环境变量模板登记
- M1-T01 并行接缝：M2-T02/T03 先行合入 `0002_marketdata` 与 `yfinance` 依赖；M1 作为后合并者把迁移改为 `0003_identity` 并指向 `0002_marketdata`，保留 M2 的 `pyproject.toml` 规则与依赖，在 `alembic/env.py` 注册 identity 模型并用 `include_object` 排除 M0 模型未声明的 `audit_log` 反射外键，使 `alembic check` 不误报；保持单一 Alembic head，同时新增单头回归测试（详见 #12）
- M1-T02（#37）：`CONTRACTS §4` 全部领域 schema（含密码复杂度校验与 `SecretStr` 脱敏）、`TenantRepository` 泛型基类与用户/刷新令牌/重置令牌/AI 用量四个仓储；新增租户隔离、SQL 谓词、令牌有效性过滤的单元与真实 PG 集成用例
- M2 数据服务 T01（#43）：领域模型（Bar、Quote、CompanyProfile、Fundamentals、FinancialStatements、EarningsEvent、EarningsHistory、NewsItem、AnalystRatings、CorporateAction、FactsSnapshot）与 DataProvider 端口协议
- M2 数据服务 T02（#45）：SQLAlchemy 2.0 异步表映射与 Alembic 0002_marketdata 迁移，覆盖 8 张核心市场数据表
- M2 数据服务 T03（#47）：YFinance 数据源适配器与离线 JSON Fixture 回放机制（AAPL/MSFT/NVDA/universes），12 个契约测试通过
- M2 数据服务 T04（#49）：MarketDataCache 缓存代理，双键架构（active + backup）、NYSE 日历动态 TTL（盘中 60s / 闭盘 300s）、指数退避重试（200ms, 400ms）与降级（stale=True）
- M2 数据服务 T05（#50）：DataService 核心编排服务与 AI 事实快照（build_facts），确定性规范化 JSON + SHA-256 哈希与 missing_fields 追踪
- M2 数据服务 T06（#51）：`/api/v1/market/*` REST API 端点与路由接入，统一错误模型与 OpenAPI 契约
- M2 数据服务 T07（#53）：全链路端到端集成验收测试 `test_marketdata_e2e.py`、NVDA 2024-06 10:1 拆股与复权验证、归档 `docs/acceptance/M2.md` 并标记 M2 里程碑结项
- M1-T03（#38）：`adapters/password_hasher.py`（argon2id，参数常量化）、`adapters/token_codec.py`（HS256，claims 仅 `sub/role/iat/exp`，显式 `now` 判过期）、`adapters/mail.py`（`InMemoryMailSender` / `LoggingMailSender`，C1 不绑定外部服务商）、`security.py`（密码组合层与不透明令牌 SHA-256 摘要）、`tokens.py`（按 `ACCESS_TOKEN_TTL_SECONDS` 颁发 access）；第三方 SDK 的 `import` 仅存在于两个 adapter，失败统一收敛为 `UNAUTHENTICATED` / `TOKEN_EXPIRED` 且不泄露库异常文本
- M1-T04（#39）：`IdentityService` 主链路（注册/登录/刷新/登出/access 校验）、`/api/v1/auth/{register,login,refresh,logout}` 四个端点、`app/api/deps.py`（Bearer 解析与 `current_user`）、Redis 登录失败限流（账号摘要键 + IP 键，429 带 `Retry-After`）、`auth.*` 审计；`docs/05 §2.1` 登记端点、成功码与错误映射（C2 路径基准）
- M1-T05（#40）：`/me`（GET/PATCH）、`/me/usage`、`/admin/users` 四个端点与 `require_role` 依赖；设置项往返与 `auth.settings_updated` 审计、当日用量只读视图（`quota` 取 `AI_DAILY_QUOTA`、`cost_usd` 字符串化）、admin 分页守卫；新增覆盖全部私有端点的越权矩阵、管理员四态（匿名/普通/管理员/禁用）与矩阵同步守卫测试
- M1-T06（#41）：密码重置闭环 `POST /auth/password/{reset-request,reset-confirm}`；`request_password_reset` 对不存在/禁用账号静默放行（同 202 响应体，不写库不发信）、`confirm_password_reset` 一次性令牌 → 吊销全部 refresh → 改密 → 写 `auth.password_changed` 审计；`make_mail_sender` 按 `APP_ENV` 选投递实现（`ci` 用内存、其余用日志并打 error 标记），Q3 拍板前不绑定任何外部邮件服务商
- M1-T07（#42）：验收记录 `docs/acceptance/M1.md`（五项清单逐项证据、越权矩阵复核、接缝检查、安全自检、偏差与遗留问题）、`docs/08 §5 M1` 五项勾选、可复现演示脚本 `scripts/m1_demo.py`（15 步全链路，支持从服务端日志读取一次性重置令牌）、`docs/README` 路线图把 M1 置为 ✅；一次性全栈探针（`docker compose up --build` + 迁移升降 + 演示脚本 + OpenAPI/CONTRACTS 接缝 + 非 root 与 `/metrics` 403）验证后删除，未进入 main；M1 结项并打 tag `m1-identity-v0.2.0`
- Q3 / Q4 裁决落地（ADR-015 / ADR-016，M1 结项后增量）：邮件服务商定为 **Gmail / Outlook SMTP over STARTTLS**，新增零第三方依赖的 `SmtpMailSender`（标准库 `smtplib` + `EmailMessage` + `asyncio.to_thread`）、8 个可选 `SMTP_*` 配置（`SecretStr` 口令、`repr` 遮蔽、半配置启动快速失败）与 `make_mail_sender` 的真实投递分支；`APP_ENV=ci` 仍强制内存实现绝不外发，日志只记收件人摘要且不含令牌/凭据，投递故障静默收敛以保账号枚举防护；`AI_DAILY_QUOTA` 默认 **20** 正式拍板并由测试锁定；`deploy/env.example` 的 SMTP 项全部注释为 `CHANGE_ME_*` 占位，默认不启用
- M3 指标与策略引擎 T01（#78）：领域数据模型（Signal、StrategyContext、TechnicalSnapshot、StrategyMetadata、TradeRecord、EquityPoint、BacktestRequest、BacktestResult）与 Strategy / StrategyRegistry 协议
- M3 指标与策略引擎 T02（#79）：纯数学技术指标库（SMA、EMA、RSI、MACD、True Range、ATR、Bollinger Bands、OBV、Swing High/Low、Support/Resistance），Decimal 高精度计算，参考误差 < 1e-6
- M3 指标与策略引擎 T03（#80）：策略注册表与技术面策略（海龟法则 turtle_20_55、道氏趋势 dow_trend、RSI 回调 pullback_rsi、123 法则反转 reversal_123）
- M3 指标与策略引擎 T04（#81）：基本面与量化选股策略（价值选股 value_basic、成长选股 growth_basic、红利防守 dividend_basic），解耦 FundamentalsLike 协议
- M3 指标与策略引擎 T05（#82）：ATR 动态止损与目标位计算（compute_atr_levels），轻量事件驱动日线回测引擎（BacktestEngine），严格逐日防未来函数，资金守恒恒等验证
- M3 指标与策略引擎 T06（#83）：StrategyService 统一编排门面与 `/api/v1/strategy/*` REST API 接入（/list, /evaluate, /scan, /technical/{symbol}, /backtest），HARD-01 鉴权守卫
- M3 指标与策略引擎 T07（#84）：全链路端到端集成验收测试 `test_strategy_e2e.py`（指标误差 < 1e-6、全部 7 策略防未来函数篡改压力测试、触发/非触发样例、数据不足兜底、回测数学闭环闭环验证）、归档 `docs/acceptance/M3.md` 并标记 M3 里程碑结项
- M4 模拟盘引擎 T01（#85）：领域数据模型（SimAccount、SimOrder、SimTrade、SimPosition、EquitySnapshot、SimTradeJournal）与 SQLAlchemy 2.0 ORM 表映射、Alembic `0004_simbroker` 迁移（含级联删除与外键索引）、Broker 接口协议与 DTO Schemas
- M4 模拟盘引擎 T02（#86）：费用模型计算（零费、每股、bps、阶梯费率）、滑点模型（固定 bps 与双向滑点）、PDT 规则引擎（典型 5 日滚动窗口、3 次日内交易限制与预警）以及订单事前验证器（OrderValidator：资金充足性、持仓非负性、最小交易单位等）
- M4 模拟盘引擎 T03（#87）：高精度撮合引擎（MatchingEngine：市价单、限价单、止损单），支持 DAY/GTC 订单有效期（TIF）、当日行情缺失安全防御（拒绝陈旧行情撮合）与审计日志追踪
- M4 模拟盘引擎 T04（#88）：实时记账引擎（AccountingEngine）与持仓状态管理（PositionState），严格执行平均成本法（Weighted Average Cost）、已实现盈亏结转与现金守恒/净值恒等/持仓非负性财务不变量
- M4 模拟盘引擎 T05（#89）：公司行动处理引擎（CorporateActionsEngine：前向拆股、反向合股、现金分红派息，持仓成本及权益严格守恒）与收盘批处理任务（MarketCloseBatch：DAY 订单过期、持仓市值重估、峰值更新与每日净值快照记录）
- M4 模拟盘引擎 T06（#90）：绩效与风险分析引擎（PerformanceAnalyzer：总回报、最大回撤、胜率、盈亏比、对比 SPY 跑赢超额收益 Alpha；RiskAnalyzer：现金水位、个股集中度、行业分布、PDT 监控）
- M4 模拟盘引擎 T07（#91）：SimService 门面服务、标准化 SimBroker 适配器（实现 `ports.Broker` 协议）与 12 个 `/api/v1/sim/*` REST API 端点（账户、资金出入金、下单、撤单、持仓、成交历史、绩效分析、持仓风险体检及复盘日记录入），严格 HARD-01 鉴权与租户数据隔离
- M4 模拟盘引擎 T08（#92）：全链路端到端集成验收测试 `test_simbroker_e2e.py`（8 大验收项、财务不变量闭环证明、手算撮合精度对齐、公司行动价值守恒、REST API 全生命周期闭环）、归档 `docs/acceptance/M4.md` 并标记 M4 里程碑结项
- M5 AI 核心框架 T01（#101）：领域数据模型（AIReport、AIUsage、AIRecommendationOutcome、DataSnapshot）、Alembic `0005_ai` 迁移（含枚举与复合索引）、Ports 协议与 DTO Schemas
- M5 AI 核心框架 T02（#102）：LLMClient 抽象适配器与 MockLLMClient、高精 Decimal 计费计算器（pricing.py，支持 GPT-4o / Claude 3.5 / DeepSeek 等主流模型）
- M5 AI 核心框架 T03（#103）：提示词仓库注册表（PromptRegistry）、多版本管理与防注入 XML CDATA 隔离模板引擎（PromptTemplate）
- M5 AI 核心框架 T04（#104）：输出 Schema 校验器（OutputSchemaValidator）、JSON 清洗与单次自动反馈重试机制（RetryableLLMCaller）
- M5 AI 核心框架 T05（#105）：数字溯源校验引擎（FactTracingEngine）、虚假幻觉数字检测、合规禁用词（保本稳赚）过滤与反向事实索引（docs/08 §4.3）
- M5 AI 核心框架 T06（#106）：配额管理服务（QuotaService，支持每日限额与原子扣减账本）、预算熔断器（BudgetCircuitBreaker，日/月预算超限自动熔断与手动干预）
- M5 AI 核心框架 T07（#107）：AIService 核心编排门面、输入快照 SHA-256 去重与多维智能缓存、`/api/v1/ai/*` 6 个 REST API 端点（/analyze, /reports, /facts, /quota, /prompts）与 HARD-01 鉴权
- M5 AI 核心框架 T08（#108）：全链路端到端集成验收测试 `test_ai_e2e.py`（7 大验收项、Mock LLM 全流程、§4.3 拦截矩阵、提示注入沙箱防御、缓存命中零成本、配额熔断拒绝、REST API 端到端闭环）、归档 `docs/acceptance/M5.md` 并标记 M5 里程碑结项
- M6 投研分析与买入决策 T01（#117）：领域模型（ResearchEnvelope、ResearchPayload、BuyDecisionPayload、TechnicalPayload、EarningsPayload）与端口协议
- M6 投研分析与买入决策 T02（#118）：提示词模板注册与输出 Schema 约束（4 大核心用例：research, buy_decision, technical, earnings）
- M6 投研分析与买入决策 T03（#119）：事实聚合器（FactAggregator）与确定性代码量化派生引擎（QuantitativeMetricsEngine：52周相对位置、溢价比率、动态交易计划）
- M6 投研分析与买入决策 T04（#120）：核心编排服务 ResearchService 门面与用例管道实现
- M6 投研分析与买入决策 T05（#121）：新手可读性校验与强制合规包装器（Novice Readability & Compliance Guardrail，0保证性禁用词，法定免责声明，数据缺失优雅降级）
- M6 投研分析与买入决策 T06（#122）：REST API 路由与端点交付（`/api/v1/ai/*` & `/api/v1/research/*` 双路径兼容与 HARD-01 鉴权）
- M6 投研分析与买入决策 T07（#123）：黄金集 5 类代表性股票多场景集成验证（AAPL, CAT, KO, PLTR, SOFI 20 组业务场景 + 5 组 REST API 端点全矩阵调用，零幻觉数字溯源通过）
- M6 投研分析与买入决策 T08（#124）：全链路端到端集成验收测试 `test_research_e2e.py`、归档 `docs/acceptance/M6.md` 并标记 M6 里程碑结项

### Changed
- CI：Dependabot 三个 ecosystem 忽略 `semver-major` 升级，避免跨大版本 PR 反复破坏 `uv --frozen` 与固定 SHA 基线（#28/#29 留待 M1 结项后评估）

### Fixed
- M0-F1（#24）：500 响应回写 `X-Request-ID` 与三项安全头，服务端生成的 `request_id` 不再丢失
- M0-F2（#25）：配置层拒绝 `CORS_ORIGINS` 通配符，避免 `allow_credentials=True` 下反射任意来源
- M0-F3（#26）：worker 改用 `load_settings_or_exit()`、关闭 uvicorn 重复访问日志、清理 T02 冗余测试兜底
- T11 接缝：`app/core/logging.py` 不再桥接 `uvicorn.access`，使 `--no-access-log` 真正生效（每次请求仅 1 条带 `request_id` 的 `http.access`）
- T09：`hashFiles()` 不得用于 job 级 `if` 导致 0 job failure，改为 step 级输出 + `needs` 守卫
- M2-T07：修复 `DataService._persist_fundamentals` 中 `FundamentalsSnapshotTable` 初始化时错误传入 `metrics` 参数导致的落库异常
