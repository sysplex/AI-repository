# M1-T04 认证服务与 register/login/refresh/logout 端点、登录限流、审计

> Issue [#39](https://github.com/sysplex/AI-repository/issues/39)｜分支 `feat/m1-t04-auth-endpoints`｜依赖：T01–T03 已合并｜规模：大
> 权威源：`CONTRACTS.md §9/§10/§12/§14`、`docs/05-api-spec.md §2.1`、`docs/08-test-plan.md` M1 前两项。

## 1. 目标

打通「注册 → 登录 → 刷新 → 登出」全链路，并实现登录失败限流与登录审计；这是 M1 的核心路径。

## 2. 范围

**包含**
- `service.py` 主干：`IdentityService` 构造 + `CONTRACTS §9` 中 5 个 T04 方法（`register` / `login` / `refresh` / `logout` / `authenticate_access_token`）。
- `api/identity.py`：`/auth/register`、`/auth/login`、`/auth/refresh`、`/auth/logout` 四个路由；`api/deps.py` 建 `get_identity_service` 与 `current_user`（`require_role` 留给 T05）；`api/router.py` 一次性 `include_router`。
- 登录限流（Redis，键与算法见 `CONTRACTS §12`）、审计（M0 `record_audit`，action 见 `§9`）。
- `docs/05-api-spec.md §2.1` 首次登记 4 个端点 + C2 基础路径说明；`CHANGELOG.md` 追加条目。
- 集成/单元测试：完整认证流程、登出后刷新失效、限流、审计、错误码映射、密码与令牌不泄露。

**不含**
- `/me`、`/me/usage`、admin 接口、越权矩阵（T05）；密码重置（T06）；`main.py` 与任何 M0 冻结文件；新迁移。

## 3. 文件所有权

| 文件 | 动作 |
|---|---|
| `backend/app/modules/identity/service.py` | 新增（主干，T05/T06 只追加方法） |
| `backend/app/api/identity.py`、`backend/app/api/deps.py` | 新增（主干） |
| `backend/app/api/router.py` | 修改（仅 `include_router` 一行） |
| `docs/05-api-spec.md`（仅 §2.1）、`CHANGELOG.md` | 修改 |
| `backend/tests/integration/modules/identity/test_auth_flow.py`、`test_login_rate_limit.py`、`test_audit_actions.py`、`backend/tests/unit/modules/identity/test_service_auth.py` | 新增 |

## 4. 接口

严格实现 `CONTRACTS.md §9`（行为 1–4）、`§10`（4 个端点 + deps）、`§12`（限流与错误码）。成功/失败响应一律走 M0 的统一结构；不新增异常处理器。

- `/auth/register` → 201 `UserPublic`；`/auth/login`、`/auth/refresh` → 200 `TokenPair`；`/auth/logout` → 204。
- `current_user` 解析 `Authorization: Bearer`；`get_identity_service` 组装 `Settings` / `Argon2PasswordHasher` / `JWTTokenCodec` / `LoggingMailSender` / `get_redis()`，测试可用 `app.dependency_overrides` 替换。
- 路由层只做参数传递与 `Request.client.host` 取值，不写业务逻辑（`docs/07 §5`）。

## 5. 验收标准（对应 `docs/08` M1 前两项）

- [ ] **注册→登录→刷新→登出流程正确**：`test_auth_flow.py` 一条用例走完全流程；每次响应结构符合 `CONTRACTS §4`；刷新返回新的 access/refresh；旧 refresh 轮换后不可用。
- [ ] **登出后刷新令牌失效**：登出后用原 refresh 调 `/auth/refresh` 得 401 `UNAUTHENTICATED`；用已轮换的旧 refresh 同样 401。
- [ ] **登录失败限流生效**：`test_login_rate_limit.py` 连续错误密码达 `LOGIN_RATE_LIMIT_MAX` 后 429 `RATE_LIMITED` 且带 `Retry-After`；成功登录后计数清零；账号键与 IP 键分别验证；fakeredis 断言键过期时间。
- [ ] **审计记录登录**：`test_audit_actions.py` 读回 `audit_log`，`action=auth.register/auth.login/auth.refresh/auth.logout` 均有记录且 `detail` 不含密码/令牌；`user_id` 正确关联。
- [ ] 错误码映射逐项断言：弱密码/非法邮箱 400、邮箱重复 409、凭据错 401、access 过期 401 `TOKEN_EXPIRED`、限流 429；错误体含 `request_id` 且与响应头一致（回归 M0-F1）。
- [ ] `mypy --strict` / `ruff` / `ruff format --check` / `lint-imports` / `pytest` 全绿；CI test job 真实 Postgres/Redis 下同样通过。
- [ ] `docs/05 §2.1` 已登记 4 端点并注明相对 `/api/v1`；`CHANGELOG.md` 已追加；无密钥、无真实 `.env`。

## 6. DoD

- [ ] 只改 §3 列出的文件
- [ ] 公开签名与 `CONTRACTS.md` 一致
- [ ] `make check` 等价门禁全绿（覆盖率 ≥ 80）
- [ ] 文档/CHANGELOG 随 PR
- [ ] PR 四段格式 + 逐条证据

## 7. 假设与偏差（必须登记）

- `LoggingMailSender` 在 T04 仅作为构造参数注入（T06 才真正发信），避免 T06 改 service 构造签名。
- 限流不采信 `X-Forwarded-For`，只用 `Request.client.host`（nginx 反代下为网关 IP）；多租户共享出口 IP 的误伤留待上线前评估。
- 邮箱验证（注册后验证邮箱）属 `docs/07 §6` 上线门槛但不在 M1 验收清单，登记为遗留项，不擅自实现。
