# M10-T01: 数据模型、ORM 实体与数据库迁移

> 责任人：Antigravity ｜ 依赖：M9 结项（v0.9.0） ｜ 分支：`feat/m10-t01-models-and-migrations`  
> 契约参考：[`docs/tasks/M10/CONTRACTS.md`](CONTRACTS.md) ｜ [`docs/03-data-model.md§3.4`](../../03-data-model.md)

---

## 1. 任务背景与目标

本任务是 Milestone M10 的基础。目标是：
1. 在 `backend/app/modules/notify/` 与 `backend/app/modules/scheduler/` 建立领域实体模型与 Pydantic 校验 Schema。
2. 编写 Alembic 迁移脚本 `0007_scheduler_notify.py`，创建 `notification_channels`、`alerts`、`alert_history` 与 `daily_reports` 4 张核心表及其索引与外键级联。
3. 实现完全可逆的 `upgrade()` 与 `downgrade()`，并通过严格的离线与在线迁移自动化测试。

---

## 2. 详细研发范围

### 2.1 Notify 模块定义 (`app/modules/notify`)
- `enums.py`：定义 `ChannelType`、`AlertType`、`AlertStatus`、`PriceDirection`、`DeliveryStatus` 等枚举。
- `models.py`：
  - `NotificationChannel`：用户多通道配置模型（JSONB 加密存储密钥与配置）。
  - `Alert`：提醒规则实体（支持 price, technical_signal, earnings_date, thesis_breaker）。
  - `AlertHistory`：提醒触发历史与审计流水。
- `schemas.py`：定义 Pydantic 请求与响应验证类（`ChannelCreate`, `ChannelRead`, `AlertCreate`, `AlertUpdate`, `AlertRead`, `AlertHistoryRead` 等）。

### 2.2 Scheduler 模块定义 (`app/modules/scheduler`)
- `enums.py`：定义 `DailyReportType`、`JobStatus`。
- `models.py`：
  - `DailyReport`：每日大盘与模拟持仓日报快照实体。
- `schemas.py`：定义 `DailyReportCreate`, `DailyReportRead`, `DailyReportFilter` 等模型。

### 2.3 数据库迁移 (`backend/alembic/versions/0007_scheduler_notify.py`)
- 前驱 Revision：`0006_screener`。
- 创建 4 张表，包含 `user_id` 外键级联、复合索引、默认值。
- 更新 `backend/alembic/env.py`，注册 notify 与 scheduler 模型供比对。

---

## 3. 验收标准（DoD）

1. [x] Alembic 迁移脚本完整支持双向升级与回退（`upgrade` & `downgrade`）。
2. [x] 迁移生成的 DDL 与 `CONTRACTS.md §2` 表结构、外键与索引 100% 对齐。
3. [x] `test_offline_sql_contains_ddl` 离线断言通过。
4. [x] Pydantic Schemas 对字段、枚举及默认值有严格约束。
5. [x] 单元测试 `test_notify_models_schemas.py` 与 `test_scheduler_models_schemas.py` 覆盖率 ≥ 90%。
