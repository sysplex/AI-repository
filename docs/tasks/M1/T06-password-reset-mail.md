# M1-T06 MailSender 端口、本地适配器与密码重置两端点

> Issue [#41](https://github.com/sysplex/AI-repository/issues/41)｜分支 `feat/m1-t06-password-reset`｜依赖：T04、T05 已合并｜规模：中
> 权威源：`CONTRACTS.md §9`（行为 6–7）、`§10`、`README.md §4` 裁定 C1、`docs/09-adr.md` Q3。

## 1. 目标

实现「请求重置 → 邮件适配器输出一次性令牌 → 确认重置 → 旧会话全部失效」闭环，同时**不绑定任何外部邮件服务商**（Q3 未拍板）。

## 2. 范围

**包含**
- `service.py` 追加 `request_password_reset` / `confirm_password_reset`（不得改已发布签名）。
- `api/identity.py` 追加 `POST /auth/password/reset-request`（202）与 `/reset-confirm`（204）。
- 把 T03 的 `MailSender` 实现接入 `get_identity_service`：`APP_ENV=local/ci` 用 `InMemoryMailSender`（测试可注入）或 `LoggingMailSender`，由配置决定；不读任何外部密钥。
- `docs/05-api-spec.md §2.1` 追加 2 个端点行；`CHANGELOG.md` 追加条目。
- 审计 `auth.password_reset_requested` / `auth.password_changed`；改密写审计（满足 `docs/08` M1 第 4 项「审计日志记录改密」）。
- 测试：全流程、账号枚举防护、令牌一次性/过期、改密后旧 refresh 全部吊销、邮件正文含令牌但日志不含明文。

**不含**
- 真实 SMTP/SaaS 适配器、注册邮箱验证（属上线门槛）、任何迁移、任何 `core/**` 改动。

## 3. 文件所有权

| 文件 | 动作 |
|---|---|
| `backend/app/modules/identity/service.py`、`backend/app/api/identity.py`、`backend/app/api/deps.py` | 仅追加（不得改已发布签名；deps 只调整 mail 适配器选择） |
| `docs/05-api-spec.md`（仅 §2.1）、`CHANGELOG.md` | 修改 |
| `backend/tests/integration/modules/identity/test_password_reset.py`、`backend/tests/unit/modules/identity/test_reset_service.py` | 新增 |

## 4. 接口

严格实现 `CONTRACTS.md §9` 行为 6–7 与 `§10` 表中 2 个端点。

- `request_password_reset`：账号不存在也返回 202 `{"status":"accepted"}`；存在时生成 `new_opaque_token()`、存 SHA-256 摘要、经 `MailSender.send(to, subject, body)` 输出带令牌的正文；响应体与日志都不含令牌。
- `confirm_password_reset`：校验摘要 → `mark_used` → `revoke_all_for_user` → 改密码 → 写审计；无效/过期/已用一律 401 `UNAUTHENTICATED`（不区分原因）。
- 重置成功后，该用户此前签发的全部 refresh 令牌立即不可用；access 令牌按原 TTL 自然过期（M1 不引入全局 token version，登记为偏差）。

## 5. 验收标准（对应 `docs/08` M1 第 4 项）

- [ ] `test_password_reset.py` 完整流程：请求 → 从 `InMemoryMailSender.messages` 取令牌 → 确认 → 旧密码登录 401、新密码登录 200。
- [ ] 账号枚举防护：不存在的邮箱与存在的邮箱返回完全相同的 202 响应体/耗时数量级，且都不写审计里的邮箱明文。
- [ ] 令牌一次性、过期（`frozen_clock` 推进超过 `PASSWORD_RESET_TTL_SECONDS`）、重复使用、伪造摘要四类均 401；`password_reset_tokens.used_at` 被正确写入。
- [ ] 改密后旧 refresh 调 `/auth/refresh` 返回 401；`audit_log` 出现 `auth.password_changed`，且 `detail` 不含密码/令牌。
- [ ] 源码与配置扫描：无任何外部邮件服务商 SDK / API Key / SMTP 口令；`deploy/env.example` 未新增密钥项。
- [ ] `mypy --strict` / `ruff` / `ruff format --check` / `lint-imports` / `pytest` 全绿；CI 真实库通过。
- [ ] `docs/05 §2.1` 已追加 2 端点；`CHANGELOG.md` 已追加；未改 T01–T05 既有签名。

## 6. DoD

- [ ] 只改 §3 列出的文件
- [ ] 公开签名与 `CONTRACTS.md` 一致
- [ ] `make check` 等价门禁全绿（覆盖率 ≥ 80）
- [ ] 文档/CHANGELOG 随 PR
- [ ] PR 四段格式 + 逐条证据

## 7. 假设与偏差（必须登记）

- **Q3 未拍板**：本任务以端口 + 本地适配器满足 M1 验收，真实投递属上线前工作；协调者选定服务商后只需新增一个 `adapters/*` 实现并在 `deps.py` 切换，不改 service 签名（C1）。
- `LoggingMailSender` 会把含令牌的正文写进本地日志，**严禁在生产启用**；在 PR 与 `CHANGELOG` 明确标注。
- 改密不主动吊销未过期的 access token（无全局 token version），建议上线前评估；不属 `docs/08` M1 验收项。
