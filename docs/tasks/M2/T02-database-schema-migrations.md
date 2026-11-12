# M2-T02 M2 共享行情表结构与 Alembic 迁移（0002）

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | T01 已合并 |
| 阻塞 | T05、T07 |
| 分支 | `feat/m2-t02-db-tables` |
| 建议规模 | 中（半天–1天） |
| 负责 Agent | _待认领_ |

## 目标
根据 `docs/03-data-model.md §3.2` 与 `CONTRACTS.md §3`，设计并实现 M2 共享行情数据表映射（SQLAlchemy 2.0 ORM）以及 Alembic 增量迁移脚本 `0002_marketdata.py`。

## 范围
**包含**
1. `backend/app/modules/marketdata/tables.py`：
   - 继承 `app.core.db.Base` 定义 8 张共享参考表：
     - `symbols`
     - `bars_daily`
     - `corporate_actions`
     - `fundamentals_snapshots`
     - `financial_statements`
     - `earnings_events`
     - `news_items`
     - `data_snapshots`
   - 正确设置主键、复合主键及索引，金额与价格使用 `sa.Numeric(18, 6)`，时间使用 `sa.DateTime(timezone=True)`。
2. `backend/alembic/versions/0002_marketdata.py`：
   - `down_revision = "0001_initial"`。
   - `upgrade()` 包含 8 张表的创建与相应索引。
   - `downgrade()` 严格可逆，支持升降往返测试。
3. 集成测试 `backend/tests/integration/modules/marketdata/test_tables.py`：
   - 验证迁移升降往返（`upgrade head` -> `downgrade 0001_initial` -> `upgrade head`）。
   - 验证 ORM 模型的插入、查询及复合主键唯一性约束。

## 文件所有权
- **创建并拥有**：
  - `backend/app/modules/marketdata/tables.py`
  - `backend/alembic/versions/0002_marketdata.py`
  - `backend/tests/integration/modules/marketdata/test_tables.py`
  - `backend/tests/integration/modules/marketdata/__init__.py`
  - `backend/tests/integration/modules/__init__.py`

## 验收标准
- [ ] Alembic 迁移脚本执行成功，升降往返测试通过（`upgrade` 与 `downgrade` 无报错）
- [ ] 表字段、主键与索引与 `CONTRACTS.md §3` 严格一致
- [ ] 价格/金额使用 `Numeric(18, 6)`，无 `FLOAT` 类型使用
- [ ] `make check` 全部通过
