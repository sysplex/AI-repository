# M1-T01 依赖、配置、模块骨架、identity 迁移与文档登记

> Issue [#36](https://github.com/sysplex/AI-repository/issues/36)｜分支 `feat/m1-t01-foundation`｜依赖：M0 已结项（`m0-foundation-v0.1.0`）｜规模：中–大
> 权威源：`docs/tasks/M1/CONTRACTS.md §2/§3/§5/§11/§13`、`docs/tasks/M1/README.md §3/§4/附录 A`。

## 1. 目标

把 M1 需要的**依赖、配置、表结构、端口声明与架构契约**一次性落到基线，让 T02–T07 只写业务代码、不再动 `pyproject.toml` / `uv.lock` / 迁移 / 配置文件。

## 2. 范围

**包含**
- 新增 3 个运行依赖并重算 `uv.lock`（裁定 C7）：`argon2-cffi>=23,<25`、`PyJWT>=2.9,<3`、`email-validator>=2.2,<3`。版本上界与 M0 一致用 `<major+1`；`exclude-newer` 截止日不变。三者分别只供 `adapters/password_hasher.py`、`adapters/token_codec.py`、Pydantic `EmailStr` 使用，**本任务不实现适配器**。
- `app/core/config.py` 追加 `CONTRACTS §2` 的 7 个可选字段与正整数校验；不得改 M0 既有字段、不得破坏 `load_settings_or_exit()` 的三必填变量聚合提示。
- `app/modules/identity/models.py`：`User` / `RefreshToken` / `PasswordResetToken` / `AiUsage` 四个 ORM 模型（`CONTRACTS §3`）；`app/modules/identity/ports.py`：`PasswordHasher` / `TokenCodec` / `MailSender` / `AccessClaims`（`§5`）。
- `alembic/versions/0003_identity.py`：建 4 表、索引、外键；为 `audit_log.user_id` 补 FK（接缝 S1）；`downgrade` 完整可逆。因 M2-T02 先行合入 `0002_marketdata.py`，本迁移顺延为 0003 并挂在它之后（接缝 S6）。
- `backend/pyproject.toml` 的 `[tool.importlinter]`：按 `CONTRACTS §11` 修正第四条契约并新增第五条。
- `docs/03-data-model.md §3.1` 补 4 张表说明与 C3/C6 注记；`deploy/env.example` 追加 6 个可选变量；`CHANGELOG.md` 追加本任务条目。

**不含**
- 仓储实现、密码/JWT 适配器、任何端点、任何 service 方法（分别属 T02–T06）。
- 不改 `app/main.py`、`app/api/router.py`、`app/core/**`（除 `config.py`）、`tests/conftest.py`、`docs/01/02/04/06/07/09`、`AGENTS.md`、根 `Makefile`。

## 3. 文件所有权

| 文件 | 动作 |
|---|---|
| `backend/pyproject.toml`、`backend/uv.lock` | 修改（依赖 + import-linter 契约） |
| `backend/app/core/config.py` | 修改（新增字段与校验） |
| `backend/app/modules/identity/{__init__,models,ports}.py` | 新增/修改 |
| `backend/alembic/versions/0003_identity.py` | 新增 |
| `docs/03-data-model.md`（仅 §3.1）、`deploy/env.example`、`CHANGELOG.md` | 修改 |
| `backend/tests/unit/core/test_config_m1.py`、`backend/tests/integration/core/test_migrations_m1.py`、`backend/tests/unit/modules/identity/test_identity_models.py`、`test_enums_ports.py` | 新增 |
| `backend/alembic/env.py`、`backend/tests/integration/core/test_migrations.py` | 并行接缝的最小必要修改（见 §7 D2/D3），不改动其它内容 |
| `docs/tasks/M1/{README,CONTRACTS}.md`、本任务卡 | 随 PR 修订迁移编号与接缝登记（阶段 0 代拟文档的纠错） |

## 4. 接口

严格实现 `CONTRACTS.md §2`（Settings 字段）、`§3`（表与迁移）、`§5`（端口/Claims）、`§11`（import-linter 契约）、`§13`（环境变量）。M0 的 `app.core.db.Base` / `UUIDPkMixin` / `TimestampMixin` 签名不变。

## 5. 验收标准

- [ ] `uv lock` 后 `uv sync --frozen` 与 CI 的 `make check` 均成功；`uv.lock` 中 3 个新依赖的版本满足 `exclude-newer`；`pip-audit` 无新增高危。
- [ ] 7 个新配置项全部有默认值；缺 `DATABASE_URL` / `REDIS_URL` / `SECRET_KEY` 时仍是 exit 1 且一次列出 3 个变量（回归 M0 验收项 3）。
- [ ] 三个 TTL / `login_rate_limit_max` / `window` 设为 0、负数或非整数时 `SettingsError` 给出「变量名 + 原因」，不含输入值。
- [ ] `alembic upgrade head` 在空库成功创建 4 表 + `audit_log` 外键；`downgrade base → upgrade head` 可逆；CI test job 的真实 Postgres 迁移通过。
- [ ] `audit_log` 历史孤儿 `user_id` 在迁移前置处理中被置 NULL，加 FK 不失败（测试用插入孤儿行后跑迁移断言）。
- [ ] `lint-imports --config pyproject.toml` 输出 5 条契约全部 `kept`、`0 broken`；新增契约能拦住「`app.api` 直接 import `identity.repo`」的反例（用临时反例脚本验证后删除）。
- [ ] `mypy --strict` / `ruff` / `ruff format --check` 全绿；新增单元测试覆盖配置校验与模型默认值。
- [ ] `docs/03 §3.1` 与 `deploy/env.example` 已按 `CONTRACTS §13` 更新；`CHANGELOG.md` 有本任务条目；无真实密钥、无 `.env` 入库。

## 6. DoD

- [ ] 只改 §3 列出的文件；未改 M0 冻结文件
- [ ] 公开签名与 `CONTRACTS.md` 一致
- [ ] `make check` 等价门禁全绿（覆盖率 ≥ 80）
- [ ] 文档随 PR（M1+ 已恢复常规，不再引用 `AGENTS.md §7` 的 M0 例外）
- [ ] PR 四段格式 + 逐条证据

## 7. 假设与偏差（必须登记）

- 复用 `SECRET_KEY` 作 JWT 签名密钥（C4），上线前建议拆独立 `JWT_SECRET`。
- `ai_usage` 本阶段只建表不写入（C6）；Q4 配额数值默认值 20 待 M5 前拍板（C5）。
- 补 `audit_log` 外键会改变 M0 表结构，属 M0 注释预留的接缝（S1），非越权改 M0 代码。
- 依赖版本受 `exclude-newer` 限制，若解析不到满足上界的版本，在 Issue 申请调整截止日，不私自改 `[tool.uv]`。
- **D1（并行合并，阻塞级）**：阶段 0 拆分时 M2 尚未落地，卡上写的是 `0002_identity.py`。M2-T02 先行合入 `0002_marketdata.py`（同样基于 `0001_initial`），PR #48 首轮 CI run `43188012509` 因 `MultipleHeads: 0002_identity, 0002_marketdata` 导致 13 errors + 2 failed。按 `README.md §6 S6` 约定 rebase 到 `f96a02f`，迁移改为 `0003_identity` / `down_revision = "0002_marketdata"`；合并即视为协调者追认该编号变更，已在 #12 与 Issue #36 登记。
- **D2（越出所有权，最小必要）**：`alembic/env.py` 由 M2-T02 修改用于注册 marketdata 表。若不注册 `app.modules.identity.models`，`alembic check` 会把 4 张已建表判为模型漂移并生成 DROP 语句，`test_upgrade_downgrade_upgrade_and_check` 无法通过。故追加一行 import；另按 D6 增加 `include_object` 钩子并传给两处 `context.configure`。未改动迁移执行逻辑。
- **D3（越出所有权，最小必要）**：`tests/integration/core/test_migrations.py` 是 M0 既有测试、已被 M2-T02 改过 head 断言。M1 后合并只把 `("0002_marketdata",)` 改为 `("0003_identity",)`，并把 `0003_identity.py` 加入硬编码凭据扫描列表，未改其它断言。
- **D4（`pyproject.toml` / `uv.lock` 合并）**：M2-T03 加了 `yfinance` 依赖、`adapters/**` 的 TID251 豁免并重写 lock。本 PR 完整保留，仅追加 M1 的 3 个依赖与 import-linter 契约，再用 `uv lock` 重算，不手工编辑 lock。
- **D5（测试发现）**：M2-T02 删除了 `tests/unit/modules/**/__init__.py`。本 PR 跟随删除 `identity/__init__.py`，并把 `test_models.py` 改名为 `test_identity_models.py`，避免与 `tests/unit/modules/marketdata/test_models.py` 在 pytest prepend 模式下模块名冲突。
- **D6（`alembic check` 模型漂移）**：`env.py` 注册 identity 模型后，M0 `AuditLog` 模型仍不含 `user_id` 外键，而 0003 迁移已建该约束，Alembic autogenerate 会把它判为「多余外键」并生成破坏性 `DROP CONSTRAINT`。处理方式**不改 M0 冻结文件、也不改 M0 测试**：在 `alembic/env.py` 用 Alembic 官方的 `include_object` 钩子，精确排除「`audit_log` 上反射得到的 `fk_audit_log_user_id_users`」这一条约束，其余表/列/索引/约束照常比对。曾尝试在 `models.py` 里把 FK 追加进 `AuditLog.__table__`，但该全局副作用会让 M0 的 `test_audit_log_table_matches_data_model`（断言 `foreign_keys == []`）随导入顺序失败，故放弃。新增 `test_env_registers_identity_models_and_exempts_audit_fk` 守卫。
