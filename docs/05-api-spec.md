# 05 API 规格

> 权威契约以 FastAPI 自动生成的 OpenAPI 为准（`/api/v1/openapi.json`）。本文定义约定与端点清单，开发前先评审本文，再写代码。

## 1. 通用约定

| 项 | 约定 |
|---|---|
| 基础路径 | `/api/v1`，破坏性变更升 `/api/v2`，旧版本至少并行保留一个迭代周期 |
| 认证 | `Authorization: Bearer <access_token>`；公开端点仅注册/登录/健康检查 |
| 格式 | JSON，字段 `snake_case`；金额用字符串（Decimal）避免浮点误差；时间 ISO 8601 UTC |
| 请求追踪 | 响应头 `X-Request-ID`；客户端可传入 |
| 幂等 | 下单等写操作要求 `Idempotency-Key` 头 |
| 分页 | `?page=1&page_size=20`，返回 `{items, total, page, page_size}` |
| 限流 | 超限返回 `429` + `Retry-After` |
| 语言 | `Accept-Language: zh-CN`（默认）影响 AI 输出语言与错误消息 |

### 1.1 统一响应

成功：直接返回资源对象，或 `{items, total, ...}`。

失败：

```json
{
  "error": {
    "code": "QUOTA_EXCEEDED",
    "message": "今日 AI 分析次数已用完",
    "details": {"limit": 20, "used": 20, "resets_at": "2026-11-12T00:00:00Z"},
    "request_id": "7f3c..."
  }
}
```

### 1.2 错误码

| HTTP | code | 含义 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 参数不合法 |
| 401 | `UNAUTHENTICATED` / `TOKEN_EXPIRED` | 未登录/令牌过期 |
| 403 | `FORBIDDEN` | 无权限 |
| 404 | `NOT_FOUND` | 资源不存在或不属于当前用户（不区分，防探测） |
| 409 | `IDEMPOTENCY_CONFLICT` / `STATE_CONFLICT` | 幂等键冲突/状态不允许 |
| 422 | `INSUFFICIENT_FUNDS` / `INSUFFICIENT_POSITION` / `INVALID_ORDER` | 业务规则拒绝 |
| 424 | `DATA_UNAVAILABLE` | 数据源不可用且无可用缓存 |
| 429 | `RATE_LIMITED` / `QUOTA_EXCEEDED` | 限流/配额 |
| 502 | `LLM_FAILED` / `LLM_OUTPUT_INVALID` | AI 调用失败/输出未通过校验 |
| 503 | `BUDGET_CIRCUIT_OPEN` | 全局 AI 预算熔断 |

### 1.3 异步任务模式

长耗时接口（AI 分析、筛选、回测）统一：

```
POST /ai/research            → 202 {"task_id": "...", "status": "queued"}
GET  /tasks/{task_id}        → {"status":"queued|running|succeeded|failed",
                                "progress": 0-100, "result_ref": {"type":"ai_report","id":"..."},
                                "error": {...}}
GET  /tasks/{task_id}/stream → SSE 推送进度（可选，前端可退化为轮询）
```

命中缓存时直接 `200` 返回报告，并带 `"cached": true`。

## 2. 端点清单

### 2.1 认证与用户（M1）

> **路径基准（裁定 C2）**：本节及以下各节的路径均**相对 `/api/v1`**，完整地址为
> `/api/v1` + 表中路径（如 `/api/v1/auth/login`）。响应遵循 §1.1 统一结构，
> 错误码遵循 §1.2；认证失败一律 401，且不区分「账号不存在」与「密码错误」。

| 方法 | 路径 | 成功 | 认证 | 说明 |
|---|---|---|---|---|
| POST | `/auth/register` | 201 `UserPublic` | 公开 | 注册；邮箱重复 409 `STATE_CONFLICT`，密码不满足复杂度 400 `VALIDATION_ERROR`；注册后**不自动登录** |
| POST | `/auth/login` | 200 `TokenPair` | 公开 | 登录，返回 access/refresh；失败 401 `UNAUTHENTICATED`，超过 `LOGIN_RATE_LIMIT_MAX` 次 429 `RATE_LIMITED` + `Retry-After` |
| POST | `/auth/refresh` | 200 `TokenPair` | refresh 令牌 | 轮换：旧 refresh 立即吊销，返回全新一对；失效 401，过期 401 `TOKEN_EXPIRED` |
| POST | `/auth/logout` | 204 空 | Bearer access | 吊销提交的 refresh 令牌（幂等），需有效 access |
| POST | `/auth/password/reset-request` | 202 `{"status":"accepted"}` | 公开 | 重置密码：无论账号是否存在都返回 202，不泄露枚举信息 |
| POST | `/auth/password/reset-confirm` | 204 空 | 重置令牌 | 令牌一次性；成功后吊销该用户全部 refresh 令牌 |
| GET | `/me` | 200 `UserPublic` | Bearer | 个人信息与设置（风险偏好、语言） |
| PATCH | `/me` | 200 `UserPublic` | Bearer | 更新设置 |
| GET | `/me/usage` | 200 `UsageResponse` | Bearer | 我的 AI 用量与配额（M1 只读，数据由 M6/M7 写入） |
| GET | `/admin/users?page&page_size` | 200 `PaginatedUsers` | admin | 用户列表；非 admin 403 `FORBIDDEN` |

实现归属：前 4 项由 M1-T04 交付，`/me*` 与 `/admin/users` 由 M1-T05，密码重置两项由 M1-T06。

补充约定（M1-T05 落地）：
- **越权与不存在同码（C10）**：访问他人私有资源一律 404 `NOT_FOUND`，不返回 403，避免探测资源是否存在；角色不足（非 admin 访问 `/admin/users`）才返回 403 `FORBIDDEN`。
- `/me/usage` 的 `quota` 取自 `AI_DAILY_QUOTA`（裁定 C5；Q4 已裁决默认 **20**，M1 只读、不扣减，见 ADR-016）；`quota_used` 等于当日 `calls`；`cost_usd` 按 §1 以字符串返回（`Numeric(18,6)`）。
- `/admin/users` 的 `page ≥ 1`、`1 ≤ page_size ≤ 100`，越界或非整数一律 400 `VALIDATION_ERROR`。

补充约定（M1-T06 落地）：
- **账号枚举防护**：`/auth/password/reset-request` 无论邮箱是否存在、账号是否被禁用，都返回同一个 `202 {"status":"accepted"}`，且不透露是否发信；只有存在且启用的账号才会落库一次性令牌并经 `MailSender` 投递。
- **令牌语义**：明文令牌只出现在邮件正文一次，库中仅存 SHA-256 摘要；有效期 `PASSWORD_RESET_TTL_SECONDS`（默认 3600 s），仅可使用一次。`/reset-confirm` 对「无效 / 过期 / 已用 / 伪造」一律 401 `UNAUTHENTICATED`，不区分原因。
- **改密后的会话**：该用户此前签发的全部 refresh 令牌立即失效；已签发的 access 令牌按原 TTL 自然过期（M1 不引入全局 token version，见 `docs/tasks/M1/T06` 偏差 D3）。
- **投递实现（Q3 于 2026-11-13 裁决，ADR-015）**：`MailSender` 端口共三种实现，由 `make_mail_sender` 选择 —— ① `APP_ENV=ci` 强制 `InMemoryMailSender`，**绝不外发**；② 已配置 `SMTP_USER` + `SMTP_PASSWORD` 时用 `SmtpMailSender`（`SMTP_PROVIDER=gmail` → `smtp.gmail.com:587`，`outlook` → `smtp.office365.com:587`，STARTTLS，凭据全部来自环境变量）；③ 未配置时 `local` 用 `LoggingMailSender` 便于联调，`staging`/`production` 仍回落日志实现但打 `mail.adapter.placeholder` error 标记。真实投递的成功日志只记收件人 SHA-256 前缀，**绝不记录含令牌的正文**；投递故障收敛为 `mail.smtp.failed` 并静默返回，保证「存在 / 不存在邮箱」响应一致（账号枚举防护）。`LoggingMailSender` 仍**严禁直接用于生产**。

### 2.2 行情与数据（M2）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/market/quotes?symbols=AAPL,MSFT` | 报价（含 `as_of`、`delayed_seconds`、`stale`） |
| GET | `/market/bars/{symbol}?start&end&interval` | K 线 |
| GET | `/market/profile/{symbol}` | 公司资料 |
| GET | `/market/fundamentals/{symbol}` | 基本面指标 |
| GET | `/market/earnings/{symbol}` | 财报历史与日历 |
| GET | `/market/news/{symbol}` | 新闻 |
| GET | `/market/environment` | 市场环境（SPY 趋势、VIX、仓位上限建议） |
| GET | `/market/calendar?from&to` | 交易日历 |

### 2.3 策略与技术面（M3）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/strategies` | 策略列表（含参数 Schema，前端据此渲染表单） |
| POST | `/strategies/{id}/evaluate` | 对单只股票评估，返回 `Signal` |
| GET | `/technical/{symbol}` | 技术快照（指标、支撑压力、进场/止损/目标） |
| POST | `/backtests` | 创建回测（异步） |
| GET | `/backtests/{id}` | 回测结果 |

### 2.4 模拟盘（M4）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST/GET | `/sim/accounts` | 创建/列出账户 |
| GET | `/sim/accounts/{id}` | 账户概览（现金、市值、净值、当日盈亏、总盈亏） |
| POST | `/sim/accounts/{id}/orders` | 下单（需 `Idempotency-Key`） |
| GET | `/sim/accounts/{id}/orders` | 订单列表 |
| DELETE | `/sim/accounts/{id}/orders/{oid}` | 撤单 |
| GET | `/sim/accounts/{id}/positions` | 持仓（成本、现价、浮盈浮亏、占比） |
| GET | `/sim/accounts/{id}/trades` | 成交记录 |
| GET | `/sim/accounts/{id}/performance` | 净值曲线、回撤、胜率、盈亏比、收益 vs SPY |
| GET | `/sim/accounts/{id}/risk` | 持仓体检：行业集中度、单股占比、相关性 |
| PUT | `/sim/trades/{tid}/journal` | 写交易日志 |

下单请求示例：

```json
{ "symbol": "AAPL", "side": "buy", "qty": "10", "type": "limit",
  "limit_price": "180.50", "tif": "day",
  "note": "回踩 50 日均线", "ai_report_id": "optional-uuid" }
```

### 2.5 AI 分析（M6 / M7）
| 方法 | 路径 | 请求体要点 |
|---|---|---|
| POST | `/ai/research` | `{symbol}` |
| POST | `/ai/buy-decision` | `{symbol, target_price, horizon, risk_level}` |
| POST | `/ai/technical` | `{symbol}` |
| POST | `/ai/earnings` | `{symbol}` |
| POST | `/ai/compare` | `{symbols[2..8]}` |
| POST | `/ai/long-term` | `{symbol, years: 5\|10\|15}` |
| POST | `/ai/portfolio` | `{amount, symbols[], risk_level, goal}` |
| GET | `/ai/reports` | 历史报告列表（可按 symbol、用例过滤） |
| GET | `/ai/reports/{id}` | 报告详情（含数据快照引用、提示词版本、成本） |
| GET | `/ai/reports/{id}/facts` | 该报告所用的数据快照（可复盘） |

枚举：`horizon ∈ {short(<3m), medium(3-12m), long(>1y)}`；`risk_level ∈ {conservative, moderate, aggressive}`；`goal ∈ {growth, income, safety, retirement}`。

### 2.6 筛选、主题、自选（M8）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/universes` | 股票池列表 |
| POST | `/screener/runs` | 创建筛选（策略、股票池、参数）异步 |
| GET | `/screener/runs/{id}` | 结果（排名、信号、失败项） |
| GET | `/themes` `/themes/{id}` | 主题及成分 |
| POST | `/themes/{id}/cards` | 生成主题股票卡片（AI，异步） |
| CRUD | `/watchlists` `/watchlists/{id}/items` | 自选清单 |

### 2.7 提醒、复盘、日报（M10）
| 方法 | 路径 | 说明 |
|---|---|---|
| CRUD | `/alerts` | 价格/信号/财报日提醒 |
| GET | `/reviews/ai-outcomes` | AI 建议复盘统计（按 verdict/用例分组） |
| GET | `/reports/daily?date=` | 每日报告 |
| CRUD | `/notification-channels` | 通知渠道配置 |

### 2.8 管理（admin）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/usage` | 全局用量与成本 |
| PATCH | `/admin/users/{id}` | 启停用户、调整配额 |
| GET | `/admin/providers/health` | 数据源/LLM 健康状态 |

### 2.9 运维
`GET /healthz`（进程存活）、`GET /readyz`（依赖就绪：DB/Redis）、`GET /metrics`（Prometheus，仅内网）。

## 3. 响应中的"可信度字段"

所有行情与 AI 响应必须携带，前端必须展示：

```json
{ "as_of": "2026-11-10T21:00:00Z", "stale": false,
  "source": "yfinance", "disclaimer_id": "not_investment_advice_v1" }
```

AI 报告额外含 `prompt_version`、`model`、`data_snapshot_id`、`cached`。
