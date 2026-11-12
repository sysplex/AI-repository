# M1-T03 argon2 密码哈希、JWT access、令牌哈希与吊销

> Issue [#38](https://github.com/sysplex/AI-repository/issues/38)｜分支 `feat/m1-t03-password-tokens`｜依赖：T01、T02 已合并｜规模：中
> 权威源：`CONTRACTS.md §5/§6/§8`、`docs/07-delivery-standard.md §6`、`docs/02-architecture.md §4`。

## 1. 目标

把密码学与令牌编解码封装进 `adapters/`，业务层只见 `Ports`；所有过期判断走 `app.core.clock.get_clock()`，可用 `frozen_clock` 确定性测试。

## 2. 范围

**包含**
- `adapters/password_hasher.py`：`Argon2PasswordHasher`（唯一 `import argon2` 的位置），参数常量化，`verify` 对畸形哈希返回 `False` 不抛异常。
- `adapters/token_codec.py`：`JWTTokenCodec(secret, algorithm)`（唯一 `import jwt` 的位置），HS256，claims 仅 `sub/role/iat/exp`；解码失败统一转成 M0 的 `Unauthenticated` / `TokenExpired`，不泄露库异常文本。
- `adapters/mail.py`：`MailMessage` dataclass + `InMemoryMailSender` / `LoggingMailSender`（裁定 C1，供 T06 使用；本任务只建实现，不接线）。
- `adapters/__init__.py`、`security.py`、`tokens.py`（`CONTRACTS §8` 全部函数）。
- 单元测试：哈希往返、错误密码、畸形哈希、令牌签发/解码、过期（冻结时钟）、篡改/换密钥/缺字段、不透明令牌随机性与 SHA-256 摘要固定长度、邮件适配器只记录不外发。
- `CHANGELOG.md` 追加本任务条目。

**不含**
- service / 路由 / 限流 / 审计（T04 起）、任何迁移、任何 `core/**` 改动、生产邮件服务商接入。

## 3. 文件所有权

| 文件 | 动作 |
|---|---|
| `backend/app/modules/identity/adapters/{__init__,password_hasher,token_codec,mail}.py` | 新增 |
| `backend/app/modules/identity/{security,tokens}.py` | 新增 |
| `backend/tests/unit/modules/identity/test_password_hasher.py`、`test_token_codec.py`、`test_security_tokens.py`、`test_mail_adapter.py` | 新增 |
| `CHANGELOG.md` | 追加条目 |

## 4. 接口

严格实现 `CONTRACTS.md §5`（`PasswordHasher` / `TokenCodec` / `MailSender` / `AccessClaims`）、`§6`（适配器表）、`§8`（函数签名）。`issue_access(codec, *, user_id, role, settings, now) -> tuple[str, int]` 返回 `(access_token, expires_in)`。

## 5. 验收标准

- [ ] `Argon2PasswordHasher.hash` 输出以 `$argon2` 开头、同一密码两次哈希不同；`verify` 对正确密码 True、错误/畸形哈希 False 且不抛异常。
- [ ] 源码扫描：`argon2` / `jwt` 的 `import` 只出现在 `adapters/` 两个文件里（`grep -rn` 证据贴 PR）。
- [ ] `JWTTokenCodec` 签发的 token 解码回 `AccessClaims` 且 `user_id/role/iat/exp` 一致；`exp` 严格等于 `now + ttl`（`frozen_clock`）。
- [ ] 过期、篡改签名、换密钥、缺 `sub`、非法 `role` 五类均抛 `Unauthenticated` / `TokenExpired`，响应体不含异常文本。
- [ ] `new_opaque_token()` 两次不同且 URL-safe；`hash_opaque_token()` 恒为 64 位十六进制；明文令牌不写日志（用 caplog 断言）。
- [ ] `InMemoryMailSender.messages` 可断言；`LoggingMailSender` 不发起任何网络调用。
- [ ] `mypy --strict` / `ruff` / `ruff format --check` / `lint-imports`（含 T01 新增的「适配器不得跨模块引用」契约）/ `pytest` 全绿。
- [ ] `CHANGELOG.md` 已追加条目；未改 T01/T02 与 M0 文件。

## 6. DoD

- [ ] 只改 §3 列出的文件
- [ ] 公开签名与 `CONTRACTS.md` 一致
- [ ] `make check` 等价门禁全绿
- [ ] 文档/CHANGELOG 随 PR
- [ ] PR 四段格式 + 逐条证据

## 7. 假设与偏差（必须登记）

- Q3 邮件服务商未拍板，本任务只交付端口实现，不接外部服务（C1）；日志适配器输出含重置令牌，仅限本地/测试环境，生产必须换真实 adapter 并关闭日志输出。
- JWT 签名复用 `SECRET_KEY`（C4）；`JWTTokenCodec` 构造时校验密钥长度 ≥ 32，与 M0 `Settings` 一致。
- PyJWT 若在某些版本缺 `py.typed`，用 `# type: ignore[import-untyped]` 并说明理由，或在 Issue 申请补 stub 依赖；不得关掉 `mypy --strict`。
