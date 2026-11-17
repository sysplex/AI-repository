# M10-T02: 多通道通知分发网关与告警调度器

> 责任人：Antigravity ｜ 依赖：M10-T01 已完成 ｜ 分支：`feat/m10-t02-notification-dispatcher`  
> 契约参考：[`docs/tasks/M10/CONTRACTS.md`](CONTRACTS.md) ｜ [`docs/01-prd.md§4 (F12)`](../../01-prd.md)

---

## 1. 任务背景与目标

在 M10-T01 中，我们已建立了 `notification_channels`、`alerts`、`alert_history` 的数据模型与数据库表。
本任务（M10-T02）的目标是：
1. 定义统一的通知接口 `Notifier` 端口与结构化通知消息模型 `NotificationMessage`、投递结果模型 `NotificationResult`。
2. 实现多通道适配器：
   - **`EmailNotifier`**：集成美股金融风格的 HTML 模板，支持标准 SMTP 与非网络环境下的测试/日志降级。
   - **`WebhookNotifier`**：集成 HTTP 客户端（`httpx.AsyncClient`），支持通用 Webhook、飞书/企微/Discord/Slack 格式，具备超时控制与安全容错。
   - **`InAppNotifier`**：系统站内信投递与本地降级。
3. 实现多渠道分发调度器 **`NotificationDispatcher`**：
   - 支持并发多渠道推送（`asyncio.gather`）。
   - 自动查询用户生效的通知渠道。
   - 记录投递审计流水至 `alert_history` 表。
   - **核心非阻塞安全铁律**：无论邮件、Webhook 等外部网络调用成功与否，绝不抛出异常阻断核心撮合、估值与数据同步流程。

---

## 2. 研发范围

### 2.1 端口与核心实体 (`backend/app/modules/notify/ports.py`)
- `NotificationMessage`：含标题、正文、HTML正文、关联标的、触发快照、元数据。
- `NotificationResult`：单渠道投递成败、错误原因、时间戳。
- `BaseNotifier(ABC)`：抽象基类与标准 `send` 方法。

### 2.2 多渠道适配器实现 (`backend/app/modules/notify/adapters/`)
- `email_notifier.py`：
  - 具备专业精美的 Financial Alert HTML 邮件排版。
  - 支持从全局配置读取 SMTP，测试环境下内存捕获。
- `webhook_notifier.py`：
  - 支持飞书（Lark Interactive Card）、企业微信（Markdown）、Discord（Embeds）、通用 JSON Webhook。
  - 自动识别 Webhook 域名并转换适配合适的 Payload 格式。
- `in_app_notifier.py`：
  - 站内信流水记录。

### 2.3 分发服务 (`backend/app/modules/notify/dispatcher.py`)
- `NotificationDispatcher`：
  - 渠道路由映射与过滤。
  - 审计流水 `AlertHistory` 写入与状态汇总（`sent` / `partial` / `failed`）。

---

## 3. 验收标准（DoD）

1. [x] `EmailNotifier` 在有配置时走 SMTP，无配置时安全回退至内存/日志模式，零未捕获异常。
2. [x] `WebhookNotifier` 支持通用、企微、飞书、Discord 结构化卡片，网络超时自动捕获返回失败结果，不崩毁调用栈。
3. [x] `NotificationDispatcher` 支持多渠道并发分发与审计流水落库。
4. [x] 单元测试 `test_email_notifier.py`、`test_webhook_notifier.py`、`test_dispatcher.py` 全部通过，覆盖率 ≥ 90%。
