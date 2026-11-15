# M9-T03 基础 UI 库与金融通用组件库（Theme, Layout, Nav, Cards, Compliance）

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | T01 |
| 阻塞 | T04, T05, T06, T07 |
| 分支 | `feat/m9-t03-ui-layout-compliance` |
| Issue | #167 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
构建响应式主应用框架布局（`AppLayout`）与高复用金融通用 UI 组件库，严格实现法定免责声明、数据新鲜度指示、AI 提示词版本 Badge、涨跌着色规范与骨架屏组件。

---

## 2. 交付范围
1. **主布局框架**：
   - `AppLayout`：响应式侧边栏（导航项：仪表盘、自选与主题、策略筛选、模拟账户、AI投研、系统设置）；
   - 顶部导航条：当前市场状态指示器（开盘中/已闭市）、搜索框、用户头像下拉菜单、移动端汉堡折叠菜单。
2. **金融通用组件**：
   - `PriceDisplay`：美股价格高精度格式化、实时变动动画闪烁；
   - `ChangePercent`：涨跌幅度标签（带上下箭头，遵循用户配色方案）；
   - `MetricCard`：指标展示卡（标题、数值、变动比率、简要说明）；
   - `FinancialTable`：表格通用组件（排序、分页、紧凑排版）。
3. **强制合规与体验组件**：
   - `ComplianceDisclaimer`：法定免责声明栏；
   - `DataFreshnessTag`：标的数据生成时间与陈旧数据（Stale）警告；
   - `AIPromptVersionBadge`：AI 提示词模板版本与模型审计标识；
   - `LoadingSkeleton` 与 `QuotaExceededModal`：配额超限友好弹窗提示。
