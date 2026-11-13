# M3-T02 纯数学技术指标库实现与高精度参考对齐

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | T01 已合并 |
| 阻塞 | T03、T05、T06、T07 |
| 分支 | `feat/m3-t02-indicators` |
| Issue | #72 |
| 建议规模 | 中（1天） |
| 负责 Agent | _待认领_ |

---

## 1. 目标
实现纯函数无副作用的高精度技术指标计算函数库（`indicators.py`），支持边界条件与数据不足防御，指标值与标准 TA-Lib / 手算参考值误差 < 1e-6。

---

## 2. 范围
**包含**
1. `backend/app/modules/strategy/indicators.py`：
   - 均线：`calculate_sma`, `calculate_ema`
   - 震荡：`calculate_rsi`（Wilder 递归平滑）
   - 趋势：`calculate_macd` (12, 26, 9)
   - 波动率：`calculate_atr` (14), `calculate_true_range`
   - 通道：`calculate_bollinger_bands` (20, 2)
   - 量能：`calculate_obv`
   - 形态：`calculate_swing_high_low`, `calculate_support_resistance`
2. `backend/tests/unit/modules/strategy/test_indicators.py`：
   - 精度对齐测试（误差 < 1e-6）
   - 数据不足（K 线数量少于周期）边界返回 `None` 测试

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/strategy/indicators.py`
  - `backend/tests/unit/modules/strategy/test_indicators.py`

---

## 4. 验收标准
- [ ] 严格遵守 `docs/tasks/M3/CONTRACTS.md §3`
- [ ] 纯函数无外部依赖（不读 DB、不发网络）
- [ ] 误差严格控制在 1e-6 以内
- [ ] `make check` 全绿
