# M9 Web 前端接口契约与开发规范（CONTRACTS.md）

> 约束对象：`frontend/` 前端应用、路由页面、图表组件、API 客户端及 E2E 测试。  
> 核心原则：**类型零漂移（OpenAPI CodeGen）、Clean Component Architecture、严格合规与金融精确性**。

---

## 1. 架构与工程规范

### 1.1 目录组织结构

```text
frontend/
├── index.html                   # HTML 模板入口
├── package.json                 # 依赖声明与 npm scripts
├── vite.config.ts               # Vite 构建与反代配置
├── tsconfig.json                # TypeScript 严格模式配置
├── tailwind.config.js           # Tailwind CSS 颜色与样式配置
├── src/
│   ├── main.tsx                 # 应用挂载入口
│   ├── App.tsx                  # 顶级路由与 Provider 装配
│   ├── api/                     # API 通信层
│   │   ├── client.ts            # 统一 HTTP Client 实例（含拦截器）
│   │   ├── openapi.ts           # 自动生成的 OpenAPI 类型声明与客户端
│   │   └── types.ts             # 扩展业务 DTO 与分页辅助类型
│   ├── contexts/                # 全局上下文
│   │   ├── AuthContext.tsx      # 认证状态、令牌轮转与用户信息
│   │   └── ThemeContext.tsx     # 主题配色（红绿涨跌偏好等）
│   ├── components/              # 通用组件
│   │   ├── layout/              # 布局（AppLayout, Sidebar, Navbar, MobileMenu）
│   │   ├── common/              # 基础 UI（Button, Input, Card, Modal, Badge, Skeleton）
│   │   ├── financial/           # 金融组件（PriceDisplay, MetricCard, FinancialTable）
│   │   ├── compliance/          # 合规组件（ComplianceDisclaimer, DataFreshnessTag）
│   │   └── chart/               # 行情图表（StockCandleChart, IndicatorOverlay）
│   ├── pages/                   # 业务路由页面
│   │   ├── auth/                # 登录、注册、找回密码
│   │   ├── dashboard/           # 市场环境仪表盘
│   │   ├── stock/               # 个股详情（K线、技术面、AI深度研报）
│   │   ├── research/            # 买入决策、对比、长期持有、投资组合
│   │   ├── screener/            # 策略筛选器与主题自选
│   │   ├── simbroker/           # 模拟盘（持仓、下单、净值、交易复盘日志）
│   │   └── settings/            # 用户设置与管理员用量
│   ├── hooks/                   # 业务自定义 Hooks
│   │   ├── useAuth.ts           # 用户与权限
│   │   ├── useMarketData.ts     # 行情与指标
│   │   └── useResearch.ts       # AI 研报与轮询
│   └── utils/                   # 工具函数
│       ├── format.ts            # 金融数字、百分比与日期格式化
│       ├── storage.ts           # 本地存储安全包装
│       └── errors.ts            # API 错误码解析与友好消息
```

---

## 2. API 消费与契约同步（OpenAPI CodeGen）

1. **零手写接口契约**：
   - 前端所有 API 请求与响应类型必须基于后端 `/openapi.json` 导出生成；
   - 严禁在前端随意手动声明后端 DTO，防止后端字段调整导致隐性运行时 Bug。
2. **统一拦截器规范**：
   - **请求拦截**：自动从安全存储中获取 Access Token，注入 `Authorization: Bearer <token>` 请求头；若有则透传 `X-Request-ID`。
   - **响应拦截**：
     - `401 UNAUTHENTICATED`: 自动尝试静默刷新令牌（`/api/v1/auth/refresh`），刷新失败则清空会话并重定向至 `/login`；
     - `429 QUOTA_EXCEEDED`: 弹出友好提示（"今日 AI 额度已达上限，请明日重试或联系管理员提升额度"）；
     - `503 BUDGET_CIRCUIT_OPEN`: 弹出全局熔断提示（"系统预算熔断已开启，请稍后再试"）；
     - 业务错误：解析规范错误体 `{ "error": { "code": "...", "message": "...", "details": ... } }`。

---

## 3. 金融与视觉规范

1. **涨跌色彩偏好（Color Scheme）**：
   - 默认遵循美股国际规范：**绿色代表上涨（#10b981 / green-500），红色代表下跌（#ef4444 / red-500）**；
   - 支持用户在设置中心切换为 A 股习惯（红涨绿跌）。
2. **金融数值格式化精度**：
   - 价格（Price）：标准美股显示 2 位或 4 位小数（如 `$182.50`，小盘分厘股 `$0.1250`）；
   - 百分比（Percentage）：统一带符号显示 2 位小数（如 `+2.45%`，`-0.85%`）；
   - 成交量与市值：使用紧凑单位显示（`K`, `M`, `B`, `T`），悬浮显示精确数值。

---

## 4. 强制合规防线（Compliance Guardrails）

所有涉及 AI 生成建议或预测的视图必须强制渲染以下 3 个关键要素：
1. **法定免责声明（Legal Disclaimer）**：
   - 固定文字：`"本内容仅供研究与模拟学习，不构成任何投资建议。市场有风险，投资需谨慎。"`；
   - 位于每份 AI 研报、买入建议、对比结论、组合建议底部显著位置。
2. **数据新鲜度标签（Data Freshness）**：
   - 明确标注标的事实数据生成时刻：`"数据截至: 2026-11-15 16:00:00 (EST)"`；
   - 若数据为降级陈旧数据（`stale=True`），必须高亮显示黄/橙色 `[数据可能延迟]` 警告。
3. **模型与提示词版本 Badge**：
   - 标明生成引擎与版本：`"AI 引擎: gpt-4o | 模板: v1.0.0"`，满足审计要求。
