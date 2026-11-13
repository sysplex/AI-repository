# M4-T01 领域数据模型、SQLAlchemy 实体、Alembic 迁移（0004_simbroker）与 DTO Schema

| 项 | 内容 |
|---|---|
| 波次 | Wave 1（M4 第一张卡） |
| 依赖 | M3 已结项 |
| 阻塞 | T02、T03、T04、T05、T06、T07、T08 |
| 分支 | `feat/m4-t01-models-schemas-migration` |
| Issue | #85 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
定义 M4 模拟盘引擎的核心领域模型、SQLAlchemy ORM 实体（`models.py`）、Pydantic DTO Schema（`schemas.py`）与系统级协议端口契约（`ports.py`），并提供可逆数据库迁移脚本 `0004_simbroker.py`。

---

## 2. 范围
**包含**
1. `backend/app/modules/simbroker/models.py`：
   - `SimAccount`：`sim_accounts` 表映射（id, user_id FK, name, initial_cash, cash, fee_model, slippage_bps, pdt_enabled, status, created_at, updated_at）。
   - `SimOrder`：`sim_orders` 表映射（id, user_id FK, account_id FK, symbol, side, type, qty, limit_price, stop_price, tif, status, idempotency_key, source, ai_report_id, note, reject_reason, created_at, updated_at）。唯一约束 `(account_id, idempotency_key)`。
   - `SimTrade`：`sim_trades` 表映射（id, user_id FK, account_id FK, order_id FK, symbol, side, qty, price, fee, realized_pnl, executed_at）。
   - `SimPosition`：`sim_positions` 表映射（id, user_id FK, account_id FK, symbol, qty, avg_cost, realized_pnl, created_at, updated_at）。唯一约束 `(account_id, symbol)`。
   - `EquitySnapshot`：`equity_snapshots` 表映射（account_id FK, trade_date, cash, market_value, equity, drawdown, created_at）。主键/复合唯一 `(account_id, trade_date)`。
   - `TradeJournal`：`trade_journal` 表映射（id, trade_id FK 唯一, notes, tags, emotion, created_at, updated_at）。
2. `backend/alembic/versions/0004_simbroker.py`：
   - 依赖 `0003_identity`，完整创建上述 6 张表，带索引、外键与级联规则。
   - 严格实现 `upgrade()` 与 `downgrade()`，满足双向可逆迁移。
3. `backend/app/modules/simbroker/schemas.py`：
   - 按 `docs/tasks/M4/CONTRACTS.md §1` 声明所有强类型 DTO。
4. `backend/app/modules/simbroker/ports.py`：
   - 按 `docs/tasks/M4/CONTRACTS.md §2` 声明 `Broker`、`MarketDataFeedProtocol`、`CorporateActionFeedProtocol` 等协议接口。
5. `backend/tests/unit/modules/simbroker/test_models_schemas.py`：
   - 覆盖所有 ORM 模型实例化、Schema 校验、`Decimal` 精度与迁移语法校验。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/simbroker/models.py`
  - `backend/alembic/versions/0004_simbroker.py`
  - `backend/app/modules/simbroker/schemas.py`
  - `backend/app/modules/simbroker/ports.py`
  - `backend/tests/unit/modules/simbroker/test_models_schemas.py`

---

## 4. 验收标准
- [ ] 严格遵守 `docs/tasks/M4/CONTRACTS.md §1` 与 `§2`
- [ ] 6 张核心数据表在 SQLite/PostgreSQL 测试引擎上成功建表与逆向回滚
- [ ] 唯一约束 `(account_id, idempotency_key)`、`(account_id, symbol)`、`(account_id, trade_date)` 准确生效
- [ ] 所有金额、价格、成本计算采用 `Decimal`
- [ ] `uv run ruff check .` / `uv run mypy` 全绿
