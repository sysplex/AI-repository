# M8-T03 策略筛选引擎与容错并发执行器（ScreenerExecutor：批量策略扫描与确定性排序）

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | T01 |
| 阻塞 | T04 |
| 分支 | `feat/m8-t03-screener-executor-sorting` |
| Issue | #151 |
| 建议规模 | 中–大（1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
实现 `ScreenerExecutor`，利用依赖注入消费策略引擎（`StrategyServiceProtocol`）和市场数据引擎（`MarketDataServiceProtocol`），并发批量扫描股票池中数百只标的，实现单标的异常隔离与容错、基于策略打分的确定性排序与信号过滤。

---

## 2. 范围
**包含**
1. `backend/app/modules/screener/executor.py`：
   - 实现 `ScreenerExecutor`，符合 `ScreenerExecutorProtocol`；
   - 依赖注入消费 `StrategyServiceProtocol` 与 `MarketDataServiceProtocol`；
   - 异步并发控制（`asyncio.Semaphore` 限制并发度，防内存暴涨或连接打满）；
   - 单标的异常捕获与隔离：单标的缺少行情或计算抛错时，记录为失败项并累加 `failed_count`，不崩溃全局批次；
   - 结果过滤与确定性排序：按 score 降序排序，相同分值按 symbol 升序二级排序，保证 100% 确定可复现；
   - 生成 `ScreenerResultItem` 列表与失败汇总列表。
2. 单元测试 `backend/tests/unit/modules/screener/test_screener_executor.py`：
   - 模拟正常标的策略打分并验证排序确定性；
   - 模拟部分标的抛出异常，验证异常被捕获且计入 `failed_items`；
   - 验证并发控制和信号过滤逻辑。

---

## 3. 验收标准
- [x] 策略筛选 100% 由代码规则驱动，无任何 LLM 编造
- [x] 具备单标的故障隔离机制，失败标的不阻断全局扫描
- [x] 排序结果在相同输入下 100% 确定可复现
- [x] 单元测试覆盖率 $\ge 90\%$，`mypy --strict` 0 错误
