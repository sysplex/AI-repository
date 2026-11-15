# M9-T04 核心图表组件与行情交互（Lightweight Charts K 线与技术信号叠加）

| 项 | 内容 |
|---|---|
| 波次 | Wave 3 |
| 依赖 | T01, T03 |
| 阻塞 | T05, T07 |
| 分支 | `feat/m9-t04-lightweight-charts-signals` |
| Issue | #168 |
| 建议规模 | 中–大（1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
基于 TradingView `lightweight-charts` 深度定制高性能交互式股票 K 线图组件，支持日 K / 周 K 周期切换、成交量副图联动、常用均线指标（SMA 20/50/200）叠加，以及策略买卖点、进场价、止损位与目标位信号标记展示。

---

## 2. 交付范围
1. **Lightweight Charts 封装**：
   - `StockCandleChart`：自适应父容器宽度缩放，支持深浅色主题自适应；
   - 蜡烛图与成交量柱状图（Volume Histogram）双图联动。
2. **技术指标叠加图层**：
   - 均线叠加（SMA 20, 50, 200），支持一键开关切换；
   - 支撑位（Support）与阻力位（Resistance）水平线标注。
3. **策略信号图层（Signal Markers）**：
   - 在对应 K 线上渲染买入（BUY）/ 卖出（SELL）箭头图标；
   - 悬浮展示进场建议价格、ATR 动态止损线与止盈目标线。
