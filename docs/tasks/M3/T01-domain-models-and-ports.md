# M3-T01 领域数据模型、DTO Schema 与 Strategy 协议契约

| 项 | 内容 |
|---|---|
| 波次 | Wave 1（M3 第一张卡） |
| 依赖 | M2 已结项 |
| 阻塞 | T02、T03、T04、T05、T06、T07 |
| 分支 | `feat/m3-t01-models-ports` |
| Issue | #71 |
| 建议规模 | 小–中（半天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
定义 M3 策略引擎的核心领域模型、DTO Schema 与 Strategy 协议接口（`ports.py`, `schemas.py`），提供强类型、不可变（`frozen=True`）的领域对象支撑。

---

## 2. 范围
**包含**
1. `backend/app/modules/strategy/ports.py`：
   - `Strategy` Protocol 声明：`id`, `display_name`, `category`, `description`, `requires`, `default_params`, `evaluate(ctx)`。
   - `StrategyRegistry` Protocol 声明：`register`, `get`, `list_all`。
2. `backend/app/modules/strategy/schemas.py`：
   - `SignalDirection` 枚举字面量 (`"long"`, `"flat"`, `"short"`)。
   - `Signal`：策略评估信号输出（含 entry, stop, target 等关键点位）。
   - `TechnicalSnapshot`：单股特定日期的技术面全景快照。
   - `StrategyContext`：传递给策略的上下文数据包。
   - `StrategyMetadata`：策略描述元数据。
   - `TradeRecord`、`EquityPoint`、`BacktestRequest`、`BacktestResult`：回测输入与汇总输出。
3. `backend/tests/unit/modules/strategy/test_schemas_ports.py`：
   - 单元测试，覆盖模型序列化、反序列化、`Decimal` 精度、只读不可变校验。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/strategy/ports.py`
  - `backend/app/modules/strategy/schemas.py`
  - `backend/tests/unit/modules/strategy/test_schemas_ports.py`

---

## 4. 验收标准
- [ ] 严格遵守 `docs/tasks/M3/CONTRACTS.md §1` 与 `§2`
- [ ] 所有金额、价格使用 `Decimal`；时间使用 UTC `datetime`
- [ ] 单元测试覆盖率 100%
- [ ] `uv run ruff check .` / `uv run mypy` 全绿
