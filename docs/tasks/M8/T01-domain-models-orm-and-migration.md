# M8-T01 领域数据模型、SQLAlchemy ORM 表与 Alembic 0006_screener 迁移

| 项 | 内容 |
|---|---|
| 波次 | Wave 1 |
| 依赖 | M7 结项 |
| 阻塞 | T02, T03, T04, T05 |
| 分支 | `feat/m8-t01-models-orm-migration` |
| Issue | #149 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
在 `backend/app/modules/screener/` 中建立核心领域数据模型（Pydantic Schemas）、SQLAlchemy ORM 实体（`screener_runs`, `screener_results`, `watchlists`, `watchlist_items`），编写 Alembic 迁移脚本 `0006_screener.py`（单 head，down_revision 为 `0005_ai`），定义 ports 协议与业务异常基类。

---

## 2. 范围
**包含**
1. `backend/app/modules/screener/schemas.py`：
   - 股票池模型：`UniverseInfo`, `ThemeStockItem`, `ThemeInfo`；
   - 筛选任务模型：`ScreenerRunCreate`, `ScreenerResultItem`, `ScreenerRunRead`, `ScreenerRunStatus`；
   - 主题卡片模型：`ThemeCardItem`, `ThemeCardsResponse`；
   - 自选清单模型：`WatchlistCreate`, `WatchlistUpdate`, `WatchlistRead`, `WatchlistItemCreate`, `WatchlistItemUpdate`, `WatchlistItemRead`, `ExportToResearchRequest`；
   - 所有金额与分值采用 `Decimal`。
2. `backend/app/modules/screener/models.py`：
   - `ScreenerRun`：`user_id`（FK users CASCADE）、`strategy_id`、`universe`、`params`（JSONB）、`status`、`total_symbols`、`matched_count`、`failed_count`、`error_message`、`created_at`、`completed_at`；
   - `ScreenerResult`：`run_id`（FK screener_runs CASCADE）、`symbol`、`rank`、`score`（Numeric 10,4）、`signal`、`metrics_snapshot`（JSONB）、`created_at`；
   - `Watchlist`：`user_id`（FK users CASCADE）、`name`、`description`、`is_default`、`created_at`、`updated_at`；
   - `WatchlistItem`：`watchlist_id`（FK watchlists CASCADE）、`symbol`、`notes`、`target_price`（Numeric 12,4）、`theme_tags`（JSONB）、`created_at`。
3. `backend/app/modules/screener/ports.py` 与 `exceptions.py`：
   - 依赖倒置协议：`UniverseManagerProtocol`, `ScreenerExecutorProtocol`, `ScreenerRepositoryProtocol`, `WatchlistRepositoryProtocol`, `ScreenerServiceProtocol`；
   - 业务异常体系：`ScreenerError`, `UniverseNotFoundError`, `StrategyNotFoundError`, `ThemeNotFoundError`, `ScreenerRunNotFoundError`, `WatchlistNotFoundError`, `WatchlistItemNotFoundError`, `DuplicateWatchlistItemError`, `ScreenerExecutionError`。
4. `backend/alembic/versions/0006_screener.py`：
   - 实现 4 张表的 `upgrade()` 与 `downgrade()`；
   - 在 `backend/alembic/env.py` 注册 `app.modules.screener.models`。
5. 单元测试 `backend/tests/unit/modules/screener/test_screener_models_schemas.py` 与更新迁移测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/screener/models.py`
  - `backend/app/modules/screener/schemas.py`
  - `backend/app/modules/screener/ports.py`
  - `backend/app/modules/screener/exceptions.py`
  - `backend/alembic/versions/0006_screener.py`
  - `backend/tests/unit/modules/screener/test_screener_models_schemas.py`
- **修改并拥有**：
  - `backend/app/modules/screener/__init__.py`
  - `backend/alembic/env.py`
  - `backend/tests/integration/core/test_migrations.py`
  - `backend/tests/integration/core/test_migrations_m1.py`

---

## 4. 验收标准
- [x] 所有 Pydantic 模型、ORM 实体与 DTO 定义完备，严格遵循 `CONTRACTS.md`
- [x] Alembic 迁移脚本 `0006_screener.py` 可执行双向无损迁移，`alembic check` 0 差异
- [x] 唯一单 head 保证为 `0006_screener`
- [x] 单元与集成测试 100% 通过，`mypy --strict` 0 错误，`ruff check` 0 警告
