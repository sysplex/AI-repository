# M10-T06: REST API 端点开放与前端提醒及复盘看板联动

> 责任人：Antigravity ｜ 依赖：M10-T03, M10-T04, M10-T05 已完成 ｜ 分支：`feat/m10-t06-api-and-ui-integration`  
> 契约参考：[`docs/tasks/M10/CONTRACTS.md§1-§5`](CONTRACTS.md) ｜ [`docs/01-prd.md§4 (F12, F13)`](../../01-prd.md) ｜ [`docs/04-modules.md#m10`](../../04-modules.md) ｜ [`docs/05-api-spec.md§2.7`](../../05-api-spec.md) ｜ [`docs/08-test-plan.md§5 M10`](../../08-test-plan.md)

---

## 1. 任务背景与目标

Milestone M10 在前五个任务中已全面交付了底层基础设施：
- **T01**：4 张核心数据库表与 Alembic 迁移；
- **T02**：多通道通知网关（Email、Webhook、In-App）及投递审计；
- **T03**：智能提醒引擎与 M7 投资论文破裂（Thesis Breakers）监控；
- **T04**：AI 投资建议事后表现评估器（无未来函数 5d/20d/60d 绝对收益与 SPY Alpha 计算）；
- **T05**：美股收盘后 DAG 批处理流水线编排器与 ARQ 异步定时调度。

本任务（**M10-T06**）负责**打通全链路前后端交互**，将上述核心能力以 RESTful API 端点正式发布，并在 Web 前端提供清晰、易用、专业的控制台与复盘数据看板：

1. **后端 REST API 端点开放**：
   - `/api/v1/alerts`：CRUD 智能提醒规则、按标的/类型/状态筛选、批量导入论文破裂规则、查询触发流水；
   - `/api/v1/notification-channels`：CRUD 用户通知渠道、即时发起渠道网络连通性测试；
   - `/api/v1/reports/daily`：按交易日检索公共大盘简报与私有持仓复盘简报详情；
   - `/api/v1/reviews/ai-outcomes`：检索 AI 投资建议历史胜率聚合统计看板与标的复盘明细。

2. **Web 前端控制台与看板建设**：
   - **智能提醒与渠道管理控制台 (`/alerts`)**：
     - Tab 1: 规则配置中心（价格/指标/财报/论文破裂规则增删改查、即时开关、冷却时间配置）；
     - Tab 2: 触发历史流水（按时间倒序展示触发时快照值、投递状态与送达渠道响应）；
     - Tab 3: 通知渠道管理（支持配置通用 Webhook、邮箱等，支持一键发送测试通知）；
   - **收盘复盘日报看板 (`/reports/daily`)**：
     - 日期选择器、宏观三大指数变动、领涨领跌、个人模拟盘资产与浮动盈亏明细可视化；
   - **AI 投资建议胜率看板 (`/reviews/ai-outcomes` / Research 集成)**：
     - Bullish/Bearish/Neutral 胜率指标 KPI 卡片、平均 5/20/60 日绝对收益率、相对 SPY 超额收益对比图表与回测明细表。

---

## 2. 研发范围与交付物

```
backend/app/
├── modules/notify/
│   └── api.py                   # /api/v1/alerts & /api/v1/notification-channels 路由
├── modules/scheduler/
│   └── api.py                   # /api/v1/reports/daily & /api/v1/scheduler/* 路由
├── modules/ai/
│   └── api.py                   # 扩充 /api/v1/reviews/ai-outcomes 路由
├── api/router.py                # 路由挂载与依赖注入装配
tests/unit/
├── modules/notify/test_api_notify.py
├── modules/scheduler/test_api_scheduler.py
└── modules/ai/test_api_reviews.py

frontend/src/
├── api/
│   ├── alerts.ts                # 提醒规则与通知渠道 API 封装
│   ├── reports.ts               # 每日简报 API 封装
│   └── reviews.ts               # AI 胜率复盘 API 封装
├── pages/alerts/
│   ├── AlertsPage.tsx           # 提醒中心主页面（3 Tab）
│   ├── AlertRulesView.tsx       # 提醒规则列表与表单模态框
│   ├── AlertHistoryView.tsx     # 触发历史日志视图
│   └── ChannelsConfigView.tsx   # 通知渠道配置与连通性测试
├── pages/reports/
│   └── DailyReportsPage.tsx     # 每日大盘与持仓简报视图
├── pages/research/
│   └── ReviewsDashboardView.tsx # AI 建议历史胜率与复盘看板
└── components/layout/Sidebar.tsx # 侧边栏菜单入口集成
```

---

## 3. 验收标准（DoD）

1. **后端 API 质量标准**：
   - 严格进行租户隔离校验（非本人数据返回 404/403）；
   - 入参出参严格对齐 Pydantic Schema；
   - 通过 `ruff check`、`mypy` 严苛类型检查与 `lint-imports` 5 项契约检查；
   - 新增 API 单元测试通过率 100%，整体覆盖率 ≥ 80%。
2. **前端交互标准**：
   - 规则与渠道的 CRUD 交互顺畅，表单支持数据校验；
   - 一键测试通知渠道提供即时 Toast/Banner 反馈；
   - 包含 StockPilot 统一合规免责声明；
   - Vitest 前端单元测试 100% 通过，无类型错误。
