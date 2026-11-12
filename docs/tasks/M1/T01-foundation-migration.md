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
- `alembic/versions/0002_identity.py`：建 4 表、索引、外键；为 `audit_log.user_id` 补 FK（接缝 S1）；`downgrade` 完整可逆。
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
| `backend/alembic/versions/0002_identity.py` | 新增 |
| `docs/03-data-model.md`（仅 §3.1）、`deploy/env.example`、`CHANGELOG.md` | 修改 |
| `backend/tests/unit/core/test_config_m1.py`、`backend/tests/integration/core/test_migrations_m1.py`、`backend/tests/unit/modules/identity/test_models.py` | 新增 |

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
