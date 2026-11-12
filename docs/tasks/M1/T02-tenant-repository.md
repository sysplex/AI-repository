# M1-T02 TenantRepository 强制租户过滤与用户仓储、领域 schema

> Issue [#37](https://github.com/sysplex/AI-repository/issues/37)｜分支 `feat/m1-t02-tenant-repository`｜依赖：T01 已合并｜规模：中
> 权威源：`CONTRACTS.md §4/§7`、`docs/03-data-model.md §4.6`、`docs/07-delivery-standard.md §6`。

## 1. 目标

实现 M1 的多租户地基：`TenantRepository` 让「忘了带 `user_id`」在代码层面不可能发生；同时落齐所有公开 schema 与用户/令牌/用量仓储，供 T03–T06 直接调用。

## 2. 范围

**包含**
- `schemas.py`：`CONTRACTS §4` 全部类型（`UserRole` / `UserStatus` / `UserSettings` / 7 个请求体 / `UserPublic` / `AuthenticatedUser` / `TokenPair` / `UsageResponse` / `PaginatedUsers`），含 `RegisterRequest.password` 复杂度校验。
- `repo.py`：`TenantRepository[ModelT]` 泛型基类 + `UserRepository` / `RefreshTokenRepository` / `PasswordResetTokenRepository` / `AiUsageRepository`（`CONTRACTS §7` 全部签名）。
- 单元测试：租户隔离（两个 `user_id` 互相读不到）、`_scoped()` 强制注入、分页、按摘要查询、过期/吊销过滤、schema 校验边界。
- `CHANGELOG.md` 追加本任务条目。

**不含**
- 密码哈希 / JWT 编解码（T03）、service、路由、事件发布、任何迁移、任何 `core/**` 改动。

## 3. 文件所有权

| 文件 | 动作 |
|---|---|
| `backend/app/modules/identity/schemas.py`、`repo.py` | 新增 |
| `backend/tests/unit/modules/identity/test_schemas.py`、`test_repository.py` | 新增 |
| `backend/tests/integration/modules/identity/test_tenant_isolation_db.py` | 新增（用 `db_session` fixture，无库时 skip） |
| `CHANGELOG.md` | 追加条目 |

## 4. 接口

严格实现 `CONTRACTS.md §4`、`§7`。要点：
- `TenantRepository.__init__` 必须显式传 `user_id`，缺失/为空抛 `ValueError`。
- `_scoped()` 无条件追加 `where(self.model.user_id == self._user_id())`；`get_by_id` / `list_for_user` 一律经它。
- `RefreshTokenRepository.get_active_by_hash(token_hash, *, now)` 只返回 `revoked_at IS NULL AND expires_at > now` 的记录。
- `PasswordResetTokenRepository.get_active_by_hash` 同理，额外要求 `used_at IS NULL`。
- `UserRepository.create` 的 `settings` 参数是普通 dict，不接收 ORM 对象。

## 5. 验收标准

- [ ] 参数化用例：用户 A 的 `TenantRepository` 读用户 B 的 `AiUsage` 返回 `None`；`list_for_user` 不含 B 的行；越权写入抛错或影响 0 行。
- [ ] 反例断言：任何绕过 `_scoped()` 的查询在 code review / 测试中可被发现；`_scoped()` 单测断言生成 SQL 含 `user_id` 谓词。
- [ ] `RefreshTokenRepository` / `PasswordResetTokenRepository` 的过期、已吊销、已用、不存在四类均返回 `None`；`revoke_all_for_user` 返回受影响行数。
- [ ] `RegisterRequest` 对弱密码（<12 位、缺大小写/数字）与非法邮箱抛 Pydantic 校验错误；`SecretStr` 不出现在 `repr` / `model_dump()` 明文里。
- [ ] `mypy --strict` / `ruff` / `ruff format --check` / `lint-imports` / `pytest` 全绿；新增代码覆盖率不拉低全局 80 门槛。
- [ ] `CHANGELOG.md` 已追加条目；未改 T01 与 M0 文件。

## 6. DoD

- [ ] 只改 §3 列出的文件
- [ ] 公开签名与 `CONTRACTS.md` 一致
- [ ] `make check` 等价门禁全绿
- [ ] 文档/CHANGELOG 随 PR
- [ ] PR 四段格式 + 逐条证据（贴越权用例名与输出）

## 7. 假设与偏差（必须登记）

- `refresh_tokens` / `password_reset_tokens` 按哈希查询不走租户过滤（哈希本身是秘密），但按用户吊销必须带 `user_id`；理由与 `CONTRACTS §7` 一致，需在 PR 写清。
- 集成用例在无 `TEST_DATABASE_URL` 且无 Docker 时 skip，不能伪造通过；CI test job 有真实 Postgres，必须实跑。
