# M10 调度、提醒、日报、复盘与运维架构契约（CONTRACTS.md）

> 状态：规范生效 ｜ 适用范围：M10 所有 Task（T01–T08）  
> 关联文档：[`docs/01-prd.md`](../../01-prd.md) ｜ [`docs/03-data-model.md§3.4`](../../03-data-model.md) ｜ [`docs/04-modules.md#m10`](../../04-modules.md) ｜ [`docs/05-api-spec.md§2.7`](../../05-api-spec.md) ｜ [`docs/08-test-plan.md§5 M10`](../../08-test-plan.md)

---

## 1. 模块划分与边界

```
app.api (路由聚合与入参校验)
   │
   ▼
app.modules.scheduler (收盘任务链 DAG、定时触发器、美股日历对齐、日报生成)
   │
   ▼
app.modules.notify (提醒规则评估、论文破裂监控、多通道告警分发、告警历史)
   │
   ▼
app.modules.ai / simbroker / screener / marketdata / identity (各下层领域能力)
   │
   ▼
app.core / app.domain (基础工具：数据库、时钟、加密、日志、事件总线)
```

- **`notify` 模块**（Layer 3）：专注于提醒规则存储、触发判定、论文破裂条件求值、通知渠道配置与分发（Email、Webhook、In-App）。
- **`scheduler` 模块**（Layer 2）：专注于交易日历与定时调度、收盘全流程 DAG 编排（行情同步 → 模拟撮合 → 净值快照 → 策略扫描 → 提醒检测 → 复盘回填 → 日报生成）。
- **`ai` 模块中的 Outcomes**：`ai_recommendation_outcomes` 表已在 M5 创建，M10 调度器负责调用 `ReviewService` 执行历史价格回填与超额收益计算。

---

## 2. 数据库实体与表结构设计

### 2.1 用户通知渠道表 (`notification_channels`)

存储用户的告警接收渠道（Email / Webhook / In-App）。

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | PK, 默认 `gen_random_uuid()` | 渠道唯一 ID |
| `user_id` | `UUID` | FK `users.id` CASCADE, Not Null, Index | 多租户所属用户 |
| `channel_type` | `VARCHAR(32)` | Not Null | 渠道类型：`email`, `webhook`, `in_app` |
| `name` | `VARCHAR(128)` | Not Null | 渠道友好展示名（如“我的飞书机器人”） |
| `config` | `JSONB` | Not Null, Default `'{}'` | 加密存储的配置（Webhook URL、密钥、目标邮箱等） |
| `is_enabled` | `BOOLEAN` | Not Null, Default `TRUE` | 是否启用 |
| `created_at` | `TIMESTAMPTZ`| Not Null, Default `now()` | 创建时间 |
| `updated_at` | `TIMESTAMPTZ`| Not Null, Default `now()` | 更新时间 |

* **索引**：
  - `ix_notification_channels_user_id` (`user_id`)
  - `ix_notification_channels_user_type` (`user_id`, `channel_type`)

---

### 2.2 智能提醒规则表 (`alerts`)

存储用户设置的各类提醒规则，包含价格、技术信号、财报日前夕以及**长期投资论文破裂条件**。

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | PK, 默认 `gen_random_uuid()` | 提醒唯一 ID |
| `user_id` | `UUID` | FK `users.id` CASCADE, Not Null, Index | 所属用户 |
| `symbol` | `VARCHAR(16)` | Nullable, Index | 关联股票代码（标的级规则；若为大盘全局规则可为 NULL） |
| `alert_type` | `VARCHAR(32)` | Not Null | 提醒类型：`price`, `technical_signal`, `earnings_date`, `thesis_breaker` |
| `title` | `VARCHAR(256)` | Not Null | 提醒简述（如“AAPL 突破 $230 阻力位”） |
| `conditions` | `JSONB` | Not Null, Default `'{}'` | 规则参数（阈值、方向、指标、论文破裂指标名与阈值等） |
| `channel_ids` | `JSONB` | Not Null, Default `'[]'` | 发送的目标渠道 ID 列表（空列表表示走默认渠道） |
| `status` | `VARCHAR(32)` | Not Null, Default `'active'` | 状态：`active`, `triggered`, `disabled`, `cooldown` |
| `last_triggered_at` | `TIMESTAMPTZ` | Nullable | 最近一次触发时间 |
| `trigger_count` | `INTEGER` | Not Null, Default `0` | 累计触发次数 |
| `cooldown_minutes` | `INTEGER` | Not Null, Default `1440` | 冷却时间（分钟，默认 24 小时防止同一交易日重复骚扰） |
| `created_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 创建时间 |
| `updated_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 更新时间 |

* **索引**：
  - `ix_alerts_user_id` (`user_id`)
  - `ix_alerts_symbol` (`symbol`)
  - `ix_alerts_status` (`status`)
  - `ix_alerts_type_status` (`alert_type`, `status`)

---

### 2.3 提醒触发历史日志表 (`alert_history`)

记录每一次提醒被成功或失败触发与投递的审计流水。

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | PK, 默认 `gen_random_uuid()` | 流水 ID |
| `alert_id` | `UUID` | FK `alerts.id` CASCADE, Not Null, Index | 关联的规则 ID |
| `user_id` | `UUID` | FK `users.id` CASCADE, Not Null, Index | 所属用户 |
| `symbol` | `VARCHAR(16)` | Nullable | 标的代码 |
| `alert_type` | `VARCHAR(32)` | Not Null | 触发时的提醒类型 |
| `triggered_value` | `JSONB` | Not Null, Default `'{}'` | 触发时的快照数据（现价、指标值、触发时财务指标） |
| `message` | `TEXT` | Not Null | 最终推送的提示文案 |
| `delivery_status` | `VARCHAR(32)` | Not Null, Default `'sent'` | 发送状态：`sent`, `partial`, `failed` |
| `delivered_channels` | `JSONB` | Not Null, Default `'[]'` | 实际送达的渠道明细与响应状态 |
| `created_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 触发入库时间 |

* **索引**：
  - `ix_alert_history_alert_id` (`alert_id`)
  - `ix_alert_history_user_created` (`user_id`, `created_at`)

---

### 2.4 每日投研与持仓简报表 (`daily_reports`)

存储收盘后自动生成的每日市场概览或用户私有持仓复盘简报。

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `UUID` | PK, 默认 `gen_random_uuid()` | 报告 ID |
| `user_id` | `UUID` | FK `users.id` CASCADE, Nullable, Index | 所属用户（NULL 为系统级公共大盘简报） |
| `report_date` | `DATE` | Not Null, Index | 所属美股交易日（YYYY-MM-DD） |
| `report_type` | `VARCHAR(32)` | Not Null | 报告类型：`market_digest`, `portfolio_digest` |
| `title` | `VARCHAR(256)` | Not Null | 日报标题 |
| `summary` | `TEXT` | Not Null | 核心摘要 markdown/text |
| `payload` | `JSONB` | Not Null, Default `'{}'` | 结构化内容（三大指数、领涨领跌、模拟盘当日盈亏、预警汇总） |
| `created_at` | `TIMESTAMPTZ` | Not Null, Default `now()` | 生成时间 |

* **索引**：
  - `ix_daily_reports_date_type` (`report_date`, `report_type`)
  - `ix_daily_reports_user_date` (`user_id`, `report_date`)

---

## 3. 枚举规范与 Pydantic 字典

### 3.1 渠道类型 (`ChannelType`)
- `EMAIL` = `"email"`：邮件通知
- `WEBHOOK` = `"webhook"`：外部通用 HTTP Webhook（飞书/企微/Discord/Slack）
- `IN_APP` = `"in_app"`：系统内站内信

### 3.2 提醒类型 (`AlertType`)
- `PRICE` = `"price"`：价格穿越（高于/低于指定阈值）
- `TECHNICAL_SIGNAL` = `"technical_signal"`：技术形态异动（如 RSI 超买超卖、MA 交叉突破）
- `EARNINGS_DATE` = `"earnings_date"`：财报发布日倒计时
- `THESIS_BREAKER` = `"thesis_breaker"`：长期投资论文破裂指标触发

### 3.3 提醒状态 (`AlertStatus`)
- `ACTIVE` = `"active"`：监控中
- `TRIGGERED` = `"triggered"`：已触发
- `DISABLED` = `"disabled"`：已禁用
- `COOLDOWN` = `"cooldown"`：触发后冷却保护中

---

## 4. 论文破裂（Thesis-Breaker）监控规约

在 M7 阶段，`ThesisEvaluation` 输出的 `thesis_breakers` 为结构化指标定义：
```json
{
  "metric": "gross_margin",
  "operator": "lt",
  "threshold": 0.40,
  "description": "毛利率若跌破 40% 说明护城河受损"
}
```
M10 提醒引擎将自动解析该结构，将其转换为 `thesis_breaker` 类型的 `Alert` 规则：
- 规则中记录 `metric`、`operator`（`lt`, `lte`, `gt`, `gte`, `eq`）、`threshold`。
- 每次获取到最新财报或财务快照时，进行自动求值匹配；若满足破裂条件，立即生成警报并推送。

---

## 5. AI 复盘收益计算与评估模型

针对已出具的 AI 买入/卖出/观望报告，定义无未来函数的复盘收益率计算标准：

1. **出具时基准价格**：$P_0$ 为报告出具日次日开盘价（或出具时现价）。
2. **5 日累计收益**：$R_{5d} = \frac{P_{T+5} - P_0}{P_0}$。
3. **20 日累计收益**：$R_{20d} = \frac{P_{T+20} - P_0}{P_0}$。
4. **60 日累计收益**：$R_{60d} = \frac{P_{T+60} - P_0}{P_0}$。
5. **20 日相对 SPY 超额 Alpha**：
   $$\text{Alpha}_{20d} = R_{20d, \text{Stock}} - R_{20d, \text{SPY}}$$

定时任务在满足交易日要求后，自动写入 `ai_recommendation_outcomes` 表。
