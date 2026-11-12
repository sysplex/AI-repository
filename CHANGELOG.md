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

### Changed
- CI：Dependabot 三个 ecosystem 忽略 `semver-major` 升级，避免跨大版本 PR 反复破坏 `uv --frozen` 与固定 SHA 基线（#28/#29 留待 M1 结项后评估）

### Fixed
- M0-F1（#24）：500 响应回写 `X-Request-ID` 与三项安全头，服务端生成的 `request_id` 不再丢失
- M0-F2（#25）：配置层拒绝 `CORS_ORIGINS` 通配符，避免 `allow_credentials=True` 下反射任意来源
- M0-F3（#26）：worker 改用 `load_settings_or_exit()`、关闭 uvicorn 重复访问日志、清理 T02 冗余测试兜底
- T11 接缝：`app/core/logging.py` 不再桥接 `uvicorn.access`，使 `--no-access-log` 真正生效（每次请求仅 1 条带 `request_id` 的 `http.access`）
- T09：`hashFiles()` 不得用于 job 级 `if` 导致 0 job failure，改为 step 级输出 + `needs` 守卫
- M2-T07：修复 `DataService._persist_fundamentals` 中 `FundamentalsSnapshotTable` 初始化时错误传入 `metrics` 参数导致的落库异常
