# M3-T03 策略引擎注册表与 v1 技术面策略实现

| 项 | 内容 |
|---|---|
| 波次 | Wave 3 |
| 依赖 | T01、T02 已合并 |
| 阻塞 | T05、T06、T07 |
| 分支 | `feat/m3-t03-technical-strategies` |
| Issue | #73 |
| 建议规模 | 中–大（1-2天） |
| 负责 Agent | _待认领_ |

---

## 1. 目标
实现策略注册机制与 4 组经典技术面策略（海龟/道氏/RSI回调/123反转），并通过严格的防未来函数（Lookahead Bias）检验。

---

## 2. 范围
**包含**
1. `backend/app/modules/strategy/registry.py`：
   - 策略注册表与装饰器 `@register_strategy`。
2. 4 组技术面策略实现（`backend/app/modules/strategy/strategies/`）：
   - `turtle.py`：海龟 20/55 日突破。
   - `dow.py`：道氏趋势高低点抬升/降低过滤突破。
   - `pullback_rsi.py`：上升趋势中 RSI 超卖回调企稳买入。
   - `reversal_123.py`：123 法则反转突破。
3. `backend/tests/unit/modules/strategy/test_technical_strategies.py`：
   - 每种策略各包含 ≥2 组"应触发/不应触发"真实 fixture 测试。
   - 防未来函数测试：对任意 `as_of`，裁剪其后数据，评估结果 100% 一致。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/strategy/registry.py`
  - `backend/app/modules/strategy/strategies/turtle.py`
  - `backend/app/modules/strategy/strategies/dow.py`
  - `backend/app/modules/strategy/strategies/pullback_rsi.py`
  - `backend/app/modules/strategy/strategies/reversal_123.py`
  - `backend/tests/unit/modules/strategy/test_technical_strategies.py`

---

## 4. 验收标准
- [ ] 每个策略有≥2组'应触发/不应触发'真实 fixture 测试
- [ ] 防未来函数测试全绿
- [ ] `make check` 全绿
