# M10-T04: AI 投资建议持续复盘与超额收益评估器

> 责任人：Antigravity ｜ 依赖：M10-T01 已完成 ｜ 分支：`feat/m10-t04-ai-recommendation-evaluator`  
> 契约参考：[`docs/tasks/M10/CONTRACTS.md§5`](CONTRACTS.md) ｜ [`docs/01-prd.md§4 (F13)`](../../01-prd.md) ｜ [`docs/04-modules.md#m10`](../../04-modules.md) ｜ [`docs/08-test-plan.md§5 M10`](../../08-test-plan.md)

---

## 1. 任务背景与目标

在 M5 阶段，我们在数据库中预建了 `ai_recommendation_outcomes` 实体表。
本任务（M10-T04）的目标是实现**AI 投资建议持续复盘与超额收益评估器（`ReviewService`）**：

1. **历史价格与收益率回填引擎（Backfill Evaluator）**：
   - 扫描历史出具的已完成 AI 研报（`AIReport`），提取其推荐评级（`verdict`，如买入/观望/避开/长期持有等）与出具时基准价格 $P_0$；
   - 结合美股交易日历（`app.core.calendar`），计算严格的 $T+5$、$T+20$、$T+60$ 交易日锚点；
   - 计算无未来函数的累计收益率：
     - $R_{5d} = \frac{P_{T+5} - P_0}{P_0}$
     - $R_{20d} = \frac{P_{T+20} - P_0}{P_0}$
     - $R_{60d} = \frac{P_{T+60} - P_0}{P_0}$
   - 计算 20 交易日相对标普 500 指数 ETF（`SPY`）的超额 Alpha 收益率：
     $$\text{Alpha}_{20d} = R_{20d, \text{Stock}} - R_{20d, \text{SPY}}$$
   - **渐进回填与幂等性保障**：随交易日推进，先到期者先行填入，未到期者保留 `None`；多次重复执行结果完全一致，绝不重复生成多余记录。

2. **多维度复盘统计聚合服务 (`ReviewService.outcomes()`)**：
   - 支持按标的、评级、时间区间筛选统计；
   - 输出全局与按评级（`buy` / `wait` / `avoid` 等）分组的统计分析：
     - 样本数、已评估周期数；
     - 5d / 20d / 60d 平均绝对收益率；
     - 20d 相对 SPY 平均超额 Alpha；
     - 各评级对应的推荐准确率与胜率（Win Rate）。

---

## 2. 研发范围与架构设计

```
backend/app/modules/ai/
├── review_service.py       # ReviewService 核心实现（收益率计算、回填扫描、聚合统计）
├── schemas.py              # 扩展复盘看板 DTO（ReviewSummaryResponse, VerdictStats）
└── ports.py                # PriceFeedProtocol 抽象行情查询端口
```

### 2.1 端口抽象与行情解耦 (`PriceFeedProtocol`)
为确保架构整洁与模块解耦，定义抽象价格供给接口：
- `get_price(symbol: str, trade_date: date) -> Decimal | None`
- `get_benchmark_prices(dates: Sequence[date], benchmark_symbol: str = "SPY") -> dict[date, Decimal]`

### 2.2 收益率量化标准与截断
- 收益率统一保留 4 位小数（Numeric(10, 4)），例如 `0.0512` 表示 +5.12%；
- $P_0$ 必须大于 0，若数据源缺失则安全跳过本次回填。

---

## 3. 验收标准（DoD）

1. [x] $T+5$、$T+20$、$T+60$ 严格基于美股交易日历计算，排除周末与法定节假日。
2. [x] 超额收益 $\text{Alpha}_{20d} = R_{20d, \text{Stock}} - R_{20d, \text{SPY}}$ 计算严密，无未来函数。
3. [x] 扫描回填逻辑具备幂等性与渐进式更新能力。
4. [x] 复盘聚合统计接口 `ReviewService.outcomes()` 按评级输出胜率、平均收益与明细。
5. [x] 单元测试 100% 覆盖各类收益与 Alpha 计算边界，全系统单元测试保持 ≥ 80% 覆盖率。
