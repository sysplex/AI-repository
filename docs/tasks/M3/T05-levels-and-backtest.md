# M3-T05 动态止损/目标位计算与轻量事件驱动回测引擎

| 项 | 内容 |
|---|---|
| 波次 | Wave 4 |
| 依赖 | T02、T03 已合并 |
| 阻塞 | T06、T07 |
| 分支 | `feat/m3-t05-levels-and-backtest` |
| Issue | #75 |
| 建议规模 | 中–大（1-2天） |
| 负责 Agent | _待认领_ |

---

## 1. 目标
实现基于 ATR 倍数的动态止损/目标位计算，以及基于日线 Bar 的轻量事件驱动回测引擎。

---

## 2. 范围
**包含**
1. `backend/app/modules/strategy/levels.py`：
   - `compute_atr_levels`：根据方向计算 `entry`, `stop`, `target`，支持 ATR 倍数配置。
2. `backend/app/modules/strategy/backtest.py`：
   - `BacktestEngine`：基于历史 K 线按日推进，防未来函数撮合，输出交易清单与权益曲线。
   - 绩效指标计算：总收益率、年化收益率、最大回撤、胜率、盈亏比。
3. `backend/tests/unit/modules/strategy/test_levels_backtest.py`：
   - 点位手算对齐测试。
   - 回测引擎数学恒等性与逻辑测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/strategy/levels.py`
  - `backend/app/modules/strategy/backtest.py`
  - `backend/tests/unit/modules/strategy/test_levels_backtest.py`

---

## 4. 验收标准
- [ ] 止损/目标位计算与手算样例逐笔精确一致
- [ ] 回测撮合逻辑严禁未来函数
- [ ] 净值恒等、胜率与盈亏比数学公式准确
- [ ] `make check` 全绿
