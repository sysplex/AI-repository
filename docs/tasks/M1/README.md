# M1 任务总览与调度（identity）

> 协调者：仓库所有者｜执行：AI Agent｜验收：协调者
>
> **阶段 0 由执行方代拟**：M0 结项时仓库只有 `docs/01–09` 设计文档，没有 `docs/tasks/M1/*`、没有 M1 Issue。本目录按 `docs/04-modules.md` M1 说明书、`docs/05-api-spec.md §2.1`、`docs/03-data-model.md §3.1/§4.6`、`docs/08-test-plan.md` M1 清单与 `docs/02-architecture.md §4/§8` 代拟，待协调者追认；合并阶段 0 PR 视为追认。
>
> 必读顺序：`AGENTS.md` → 本文件 → `CONTRACTS.md` → 自己的任务卡 → 按需 `docs/02`、`docs/07`、`docs/08`。
> `AGENTS.md §7` 的适用期已随 T11 结项结束：**M1+ 恢复常规「文档更新随 PR」**，即涉及表/API 的 PR 直接更新 `docs/03` / `docs/05`，并按 DoD #11 更新 `CHANGELOG.md`。

## 1. 目标与边界

- **职责**（`docs/04` M1）：注册、登录、登出、令牌刷新、密码重置（邮件）、角色、用户设置、配额策略、审计。
- **非职责**：支付与订阅；行情/AI/模拟盘等业务模块；真实邮件投递与生产 SMTP 配置（见 §4 Q3 裁定）。
- **M1 验收清单**（`docs/08-test-plan.md` M1 小节，5 项）：注册→登录→刷新→登出流程正确且登出后刷新失效；登录失败限流生效；越权测试覆盖全部私有端点；审计记录登录/改密；管理员接口仅管理员可访问。

## 2. 任务清单（固定线性序列）

顺序执行，一任务一分支一 PR，前一个 PR `MERGED` 后才切下一个分支；不派并发 Agent。

| ID | 任务 | 分支 | 依赖 | 规模 | 状态 |
|---|---|---|---|---|---|
| [T01](T01-foundation-migration.md) | 依赖、配置、模块骨架、identity 迁移与文档登记 | `feat/m1-t01-foundation` | M0 已结项（`m0-foundation-v0.1.0`） | 中–大 | Todo |
| [T02](T02-tenant-repository.md) | `TenantRepository` 强制租户过滤与用户仓储、领域 schema | `feat/m1-t02-tenant-repository` | T01 | 中 | Todo |
| [T03](T03-password-tokens.md) | argon2 密码哈希、JWT access、刷新/重置令牌哈希与吊销 | `feat/m1-t03-password-tokens` | T01、T02 | 中 | Todo |
| [T04](T04-auth-endpoints.md) | 认证服务与 `register/login/refresh/logout` 端点、登录限流、审计 | `feat/m1-t04-auth-endpoints` | T01–T03 | 大 | Todo |
| [T05](T05-user-rbac-quota.md) | `current_user` / `require_role` / `/me` / `/me/usage` / admin 接口与越权矩阵 | `feat/m1-t05-user-rbac-quota` | T04 | 大 | Todo |
| [T06](T06-password-reset-mail.md) | `MailSender` 端口 + 本地/日志适配器 + 密码重置两端点 | `feat/m1-t06-password-reset` | T04、T05 | 中 | Todo |
| [T07](T07-acceptance.md) | 集成验收、越权全端点复核、演示脚本、结项文档与 tag | `chore/m1-t07-acceptance` | T01–T06 | 中 | Todo |

```
T01 → T02 → T03 → T04 → T05 → T06 → T07
```

## 3. 文件所有权矩阵（防冲突）

| 文件/目录 | 所有者 | 其他任务 |
|---|---|---|
| `backend/pyproject.toml`、`backend/uv.lock` | T01 | 其余任务不得改；新依赖一律在 T01 一次引入 |
| `backend/app/core/config.py` | T01 | 其余任务只读 `Settings`，不得加字段 |
| `backend/app/modules/identity/models.py`、`ports.py`、`__init__.py` | T01 | 后续任务只读 |
| `backend/alembic/versions/0003_identity.py` | T01 | 其余任务不得新增迁移；需要改表先在 Issue 申请；M2 后续迁移从 0004 起编号 |
| `docs/03-data-model.md §3.1`、`deploy/env.example` | T01 | T05/T06 仅可在登记新端点时改 `docs/05` |
| `backend/app/modules/identity/schemas.py`、`repo.py` | T02 | T04–T06 可扩展 `schemas.py`（不得改已发布签名），`repo.py` 只读 |
| `backend/app/modules/identity/security.py`、`tokens.py`、`adapters/**` | T03 | 其余任务只读 |
| `backend/app/modules/identity/service.py` | T04 建主干 | T05/T06 只允许追加方法，不得改已发布签名 |
| `backend/app/api/identity.py`、`backend/app/api/deps.py` | T04 建主干 | T05/T06 只允许追加路由/依赖 |
| `backend/app/api/router.py` | T04（接线一次） | 其余任务不得改 |
| `docs/05-api-spec.md §2.1` | T04 首次登记 | T05/T06 追加端点行 |
| `backend/tests/**`（新增 M1 用例） | 各任务自己的测试文件 | 不得改 M0 既有测试；`tests/conftest.py` 归 T10（M0），M1 不得改 |
| `docs/08-test-plan.md` M1 清单 | T07 | 其余任务不得改 |
| `CHANGELOG.md` | 每个任务各追加自己的条目 | 不得改别人条目 |
| `docs/README.md` 路线图状态行 | T07 | 其余任务不得改 |
| `docs/acceptance/M1.md`、`scripts/m1_demo.py` | T07 | — |
| `.github/dependabot.yml`、`.github/workflows/**`、`docs/ci.md` | 阶段 0（本次） | 其余任务不得改 |
| `docs/01`、`02`、`04`、`06`、`07`、`09`、`AGENTS.md`、根 `Makefile` | 协调者 | **M1 期间仍不得改**；需要变更走 Issue 提案 |
| `backend/app/core/**`（除 `config.py`）、`app/main.py`、`deploy/**`（除 `env.example`） | M0 冻结 | M1 不得改；缺口登记为偏差 |
| 矩阵未列出的文件 | 协调者 | 需改先在 Issue 申请 |

> **与 M0 矩阵的差异说明**：M0 把 `app/main.py` 与 `docs/01–09` 完全冻结；M1 需要在 `api/router.py` 挂业务路由（`main.py` 已预留 `api_router` 挂载点，无需改 `main.py`），并需要在 PR 内更新 `docs/03` / `docs/05`（`AGENTS.md §7` 到期后恢复常规）。因此本矩阵把这些文件重新分配给 M1 的特定任务，**仍不授权修改 `docs/01/02/04/06/07/09` 与 `AGENTS.md`**。

## 4. 阶段 0 裁定（代拟，待追认）

| 编号 | 事项 | 裁定 |
|---|---|---|
| C1 | **Q3 邮件服务商**（`docs/09-adr.md` 待决） | M1 不绑定任何外部服务商：`MailSender` 放进 `ports.py`，实现放 `adapters/mail.py`（`InMemoryMailSender` 供测试、`LoggingMailSender` 供本地）。`reset-request` 返回 202 且不泄露账号是否存在，重置链接/令牌只经适配器输出。Q3 推迟到上线前拍板，届时只新增一个 adapter，不改 service 签名。 |
| C2 | **API 基础路径** | `docs/05` 表格中的 `/auth/*`、`/me` 均相对基础路径 `/api/v1`（`main.py` 已把 `api_router` 挂在 `/api/v1`）。T04 在 `docs/05 §2.1` 表头补一行说明，不改已列路径。 |
| C3 | **密码重置令牌存储** | 新增 `password_reset_tokens` 表（只存 SHA-256 摘要、过期时间、`used_at`），不复用 `refresh_tokens`；`docs/03 §3.1` 由 T01 登记。 |
| C4 | **签名密钥** | 复用 M0 的 `SECRET_KEY`（HS256），不新增必填变量，保证 M0「三个必填变量」验收不被破坏。上线前建议拆出独立 `JWT_SECRET` 并轮换，已登记为遗留建议。 |
| C5 | **AI 配额 Q4** | M1 只提供可配置的 `AI_DAILY_QUOTA`（默认 20）与 `/me/usage` 只读视图，不实现全局预算熔断（属 M5）。Q4 仍按 ADR 留到 M5 前拍板。 |
| C6 | **`ai_usage` 表** | T01 建表（按 `docs/03 §3.1`），M1 只读、不写入（写入属 M5），`/me/usage` 在无记录时返回全 0。 |
| C7 | **新依赖** | 仅 3 个：`argon2-cffi`、`PyJWT`、`email-validator`。全部由 T01 一次写入 `pyproject.toml` 并 `uv lock` 更新 `uv.lock`；`[tool.uv] exclude-newer` 截止日不变。理由与版本约束见 T01 卡。 |
| C8 | **import-linter 接缝** | M0 的「禁止契约：模块只能引用对方的 service / schemas 公开面」把 `app.api` 列为 source、把整个 `app.modules.identity` 列为 forbidden，M1 路由层将无法调用 identity service。T01 修正该契约：把 `app.api` 移出 source，另加一条禁止 `app.api` / 其它业务模块引用 `identity.repo / models / adapters / ports` 的契约，保留「公开面 = service + schemas」语义。详见 `CONTRACTS.md §11`。 |
| C9 | **覆盖率** | 全局 `fail_under=80` 不变（M0 T10 起固定）；`docs/07 §1.2` 的 85/90/95 是模块核心逻辑目标。M1 各任务新增代码须有测试，不另设阶段性豁免。 |
| C10 | **越权返回码** | 私有资源越权一律 `404 NOT_FOUND`（不区分「不存在 / 不属于你」，防探测，见 `docs/07 §6`）；角色不足用 `403 FORBIDDEN`。 |

## 5. 协调规则

1. 严格按 §2 线性序列；每个 PR 核实 `MERGED` 后才创建下一分支。
2. 接口以 `CONTRACTS.md` 为准；认为契约有问题，在对应 Issue 提出，由协调者裁决，不自行改签名。
3. 每个 PR 按模板四段 + DoD 自检填写，逐条贴验收证据（命令输出 / 测试名 / CI run）。
4. `make check` 等价门禁全绿（`ruff` / `ruff format --check` / `mypy --strict` / `lint-imports` / `pytest` 覆盖率 ≥ 80）后才合并；CI 7/7 job success。
5. 疑问写在对应 Issue 评论；阻塞超过 30 分钟上报。
6. 私有仓库免费版无分支保护，继续按 `docs/ci.md §6.2` 的团队约定执行（PR 必过 CI、CODEOWNERS、人工评审清单、禁止直推 `main`、线性历史）。

## 6. 附录 A：M0 → M1 接缝登记

| 编号 | 发现 | 处理 |
|---|---|---|
| S1 | `audit_log.user_id` 在 `0001_initial.py` 无外键（注释写「M1 再补」） | T01 的 `0003_identity.py` 补 `users` 外键（`ON DELETE SET NULL`），`downgrade` 先删约束。历史孤儿行由迁移前置检查处理，见 T01 验收项 |
| S2 | C8 的 import-linter 契约冲突 | T01 修正 `pyproject.toml`，`lint-imports` 断言 5 条契约全 kept |
| S3 | `app/core/config.py` 归 M0 T02，M1 需新增 7 个可选配置项 | 由本矩阵重新分配给 T01；全部带默认值，不改变三必填变量语义 |
| S4 | `api/router.py` 的 `api_router` 是空壳 | T04 一次性 `include_router` 接入，M1 后续任务只在自己的 `api/identity.py` 里追加路由 |
| S5 | Dependabot #28/#29 跨大版本升级会破坏 `--frozen` 与固定 SHA 基线 | 阶段 0 在 `.github/dependabot.yml` 为三个 ecosystem 加 `semver-major` ignore（协调者 #12 建议）；两个 PR 保持 open，M1 结项后统一评估 |
| S6 | M2-T02 先行合入 `0002_marketdata.py`，与 T01 原计划的 `0002_identity.py` 形成 Alembic 多头 | T01 作为后合并者 rebase 到最新 `main`，迁移改名 `0003_identity` 且 `down_revision = "0002_marketdata"`；同步更新契约、任务卡、`docs/03`、`CHANGELOG`、`test_migrations.py` 的 head 断言；新增 `test_alembic_has_single_head` 回归用例。CI run `43188012509` 的 `MultipleHeads` 失败由此闭环 |
| S7 | M2-T03 在 `pyproject.toml` 加 `yfinance` 依赖与 `app/modules/*/adapters/**` 的 TID251 豁免，并重写 `uv.lock` | T01 rebase 时保留 M2 全部改动，仅追加自己的 3 个依赖与 import-linter 契约；用 `uv lock` 重新生成合并后的 lock，不手工编辑 |
| S8 | M2-T02 修改 `alembic/env.py` 注册 marketdata 表、删除 `tests/unit/modules/**/__init__.py` | T01 在 `env.py` 追加 `app.modules.identity.models` 注册（否则 `alembic check` 误报模型漂移）；测试侧跟随移除 `identity/__init__.py`，并把 `test_models.py` 改名为 `test_identity_models.py`，避免与 `tests/unit/modules/marketdata/test_models.py` 的模块名冲突 |
| S9 | 0003 迁移给 `audit_log.user_id` 加了外键，但 M0 `AuditLog` 模型无此约束，`command.check` 会生成破坏性 `DROP CONSTRAINT` | T01 不改 M0 冻结文件与 M0 测试，在 `alembic/env.py` 用 `include_object` 钩子精确排除该反射外键；`test_env_registers_identity_models_and_exempts_audit_fk` 守卫 |

## 7. 附录 B：M1 数据来源与验证方式

- 门禁：本机 `make check` 等价命令 + GitHub Actions `ci.yml` 7 个 job（test job 带真实 Postgres 16 / Redis 7）。
- 集成测试：复用 M0 `tests/conftest.py` 的 `db_session` / `client` / `redis` / `frozen_clock` / `settings` fixture，不修改 conftest。
- 迁移可升可降：T01 迁移在 CI test job 的 `alembic upgrade head` 中实跑；T07 复跑 `downgrade base → upgrade head` 后 `/readyz` 仍 200。
- 端到端：T07 用一次性 runner 工作流（本机无 Docker）验证 compose 从零启动 + M1 全链路；探针不进入最终 main。
