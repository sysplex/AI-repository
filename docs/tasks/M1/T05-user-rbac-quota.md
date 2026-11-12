# M1-T05 current_user / require_role / me / usage / admin 与越权矩阵

> Issue [#40](https://github.com/sysplex/AI-repository/issues/40)｜分支 `feat/m1-t05-user-rbac-quota`｜依赖：T04 已合并｜规模：大
> 权威源：`CONTRACTS.md §9/§10/§14`、`docs/08-test-plan.md` M1 第 3/5 项、`docs/07-delivery-standard.md §6`（越权返回 404）。

## 1. 目标

补齐用户自助接口与管理员守卫，并用**覆盖全部私有端点的自动化越权矩阵**证明多租户隔离真实生效。

## 2. 范围

**包含**
- `api/deps.py` 追加 `require_role(role)`；`api/identity.py` 追加 `GET /me`、`PATCH /me`、`GET /me/usage`、`GET /admin/users`。
- `service.py` 追加 `CONTRACTS §9` 的 4 个 T05 方法（`get_profile` / `update_settings` / `get_usage` / `list_users`）；**不得改 T04 已发布的方法签名**。
- `docs/05-api-spec.md §2.1` 追加 4 个端点行；`CHANGELOG.md` 追加条目。
- 越权矩阵测试：两个普通用户 + 一个 admin + 一个 disabled 用户，逐端点断言。
- 审计：`auth.settings_updated` 写入（改密审计在 T06）。

**不含**
- 密码重置（T06）、`ai_usage` 写入与全局预算熔断（M5）、任何迁移、任何 `core/**` 改动。

## 3. 文件所有权

| 文件 | 动作 |
|---|---|
| `backend/app/api/identity.py`、`backend/app/api/deps.py`、`backend/app/modules/identity/service.py` | 仅追加（不得改已发布签名） |
| `docs/05-api-spec.md`（仅 §2.1）、`CHANGELOG.md` | 修改 |
| `backend/tests/integration/modules/identity/test_tenant_isolation.py`、`test_admin_guard.py`、`test_me_endpoints.py` | 新增 |

## 4. 接口

严格实现 `CONTRACTS.md §9`（行为 5）、`§10` 表中 4 个 T05 端点、`§12` 错误码映射（越权 404、角色不足 403）。`require_role` 返回的依赖在角色不足时抛 `Forbidden`；`disabled` 用户一律 `Unauthenticated`。

`/me/usage` 读 `AiUsageRepository`（继承 `TenantRepository`），无记录返回 `UsageResponse` 全 0 + `quota=settings.ai_daily_quota`；`cost_usd` 序列化为字符串（`docs/05 §1`）。`/admin/users` 用 `UserRepository.list_paginated` 返回 `{items,total,page,page_size}`。

## 5. 验收标准（对应 `docs/08` M1 第 3/5 项）

- [ ] **越权测试覆盖全部私有端点**：`test_tenant_isolation.py` 用参数化矩阵逐行列出 `/auth/logout`、`/me`、`PATCH /me`、`/me/usage`、`/admin/users`（以及 T06 合入后的两个重置端点由 T07 复核），断言用户 A 拿用户 B 的 `user_id`/资源 ID 访问返回 `404 NOT_FOUND`，且响应不泄露 B 的数据。矩阵行数与端点清单一一对应，PR 里贴出清单。
- [ ] **管理员接口仅管理员可访问**：`test_admin_guard.py` 覆盖匿名 401、普通用户 403、admin 200、disabled 401；`require_role` 单测覆盖两种角色。
- [ ] `/me` GET/PATCH：设置项（风险偏好、语言、`default_account_id`）往返一致；PATCH 写 `audit_log` action `auth.settings_updated`；非法枚举 400。
- [ ] `/me/usage`：无记录返回全 0 且 `quota` 来自配置；`Decimal` 以字符串返回；用户 A 与 B 的用量互不串读。
- [ ] 越权路径的错误体为 M0 统一结构且 `request_id` 一致；日志不含令牌/密码。
- [ ] `mypy --strict` / `ruff` / `ruff format --check` / `lint-imports` / `pytest` 全绿；CI 真实库通过。
- [ ] `docs/05 §2.1` 已追加 4 端点；`CHANGELOG.md` 已追加；未改 T01–T04 既有签名。

## 6. DoD

- [ ] 只改 §3 列出的文件，且 `service.py` / `deps.py` / `identity.py` 只有追加
- [ ] 公开签名与 `CONTRACTS.md` 一致
- [ ] `make check` 等价门禁全绿（覆盖率 ≥ 80）
- [ ] 文档/CHANGELOG 随 PR
- [ ] PR 四段格式 + 逐条证据（贴越权矩阵用例名与结果）

## 7. 假设与偏差（必须登记）

- 越权统一 404（C10 / `docs/07 §6`），与 `docs/05 §1.2` 一致；不返回 403 以免暴露资源存在性。
- `ai_daily_quota` 只是可读默认值（C5），M1 不实现配额扣减或熔断。
- `/admin/users` 目前是 M1 唯一 admin 端点；将来新增 admin 端点必须同步扩充越权矩阵，登记为维护约定。
