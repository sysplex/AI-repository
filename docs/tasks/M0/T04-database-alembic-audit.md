# M0-T04 数据库、迁移与审计表

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | **T01、T02 已合并**（`Settings.database_url`） |
| 阻塞 | T07、T10 |
| 分支 | `feat/m0-t04-db-alembic` |
| 建议规模 | 中–大 |
| 负责 Agent | _未分配_ |

## 目标
实现异步数据库层（SQLAlchemy 2 + asyncpg）、Alembic 异步迁移、`audit_log` 表与 `record_audit`，按 `CONTRACTS.md §5`。

## 范围
**包含**
1. `core/db.py`：`Base`（含 naming convention）、`UUIDPkMixin`、`TimestampMixin`、`get_engine/get_session_factory/get_session/check_db/dispose_engine`。引擎参数：`pool_pre_ping=True`，连接池大小可由 Settings 扩展项控制（如需新增 Settings 字段，在 Issue 申请，由 T02 加）；**时区统一 UTC**（连接级 `timezone=UTC`）。
2. `get_session`：作为 FastAPI 依赖，正常结束 commit，异常 rollback，最后 close。
3. `core/audit.py`：`AuditLog` 模型与 `record_audit`（只增不改；`detail` 为 JSONB；对 `detail` 做大小限制，超过 8KB 抛 `ValueError`）。
4. `backend/alembic.ini`、`backend/alembic/env.py`（异步，URL 取自 Settings，`target_metadata=Base.metadata`，开启 `compare_type`）、`script.py.mako`。
5. 初始迁移 `0001_initial`：创建 `audit_log` 与索引（见契约）；`downgrade` 完整可逆。
6. 迁移规范文档 `backend/alembic/README.md`：命名规则（`NNNN_描述`）、向前兼容原则（先加后删、禁止在线重命名/删列）、如何生成与回滚。

**不包含**：用户表与外键（M1）；多租户 Repository 基类（M1）；容器编排（T08）。

## 文件所有权
- **拥有**：`backend/app/core/db.py`、`core/audit.py`、`backend/alembic.ini`、`backend/alembic/**`
- **新增测试**：`backend/tests/integration/core/test_db.py`、`test_audit.py`、`test_migrations.py`
- **不得修改**：`tests/conftest.py`（归 T10）。本任务测试需要的数据库 fixture **在测试文件内就地定义**（使用环境变量 `TEST_DATABASE_URL`；T10 合并后可迁移为共享 fixture，由 T10 负责）。

## 验收标准
- [ ] 空库执行 `alembic upgrade head` 成功；`alembic downgrade base` 成功；再 `upgrade head` 成功（测试自动化）
- [ ] 迁移后 `audit_log` 表结构与 `docs/03-data-model.md` 一致，两个索引存在（测试查询 `pg_indexes`）
- [ ] `alembic check`（模型与迁移无漂移）通过
- [ ] `get_session`：正常 commit、异常 rollback（测试：写入后抛异常，数据不存在）
- [ ] `check_db()`：库可用 True；停库/错误 URL → False 且不抛异常（测试）
- [ ] `record_audit` 写入并可读回；`detail` 超限抛错（测试）
- [ ] 时间字段为 `timestamptz`，读回为带 UTC 时区的 datetime（测试）
- [ ] `make check` 全绿；覆盖率 ≥ 85%
- [ ] 无硬编码连接串/密码

## 交接说明
给协调者：贴出 `alembic upgrade head` 的输出与 `\d audit_log` 结果。
