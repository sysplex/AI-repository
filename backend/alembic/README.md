# 数据库迁移规范（M0 / T04）

所有命令在 `backend/` 目录执行；`DATABASE_URL` 由环境变量提供，**不写入任何文件**。
仓库根提供 `make migrate` / `make revision m="..."` 快捷目标（Makefile 归 T01）。

## 环境

```bash
export DATABASE_URL='postgresql+asyncpg://user@host:5432/db'
cd backend
uv run --frozen alembic current          # 查看当前版本
uv run --frozen alembic history --verbose
```

## 生成与执行

```bash
# 生成（生成后必须人工审阅，禁止直接提交未审阅的 autogenerate 结果）
uv run --frozen alembic revision --autogenerate -m "add_watchlists"

# 升级 / 回滚 / 漂移检查
uv run --frozen alembic upgrade head
uv run --frozen alembic downgrade base
uv run --frozen alembic check            # 模型与迁移是否一致
```

`alembic/env.py` 使用异步引擎（asyncpg），`target_metadata = Base.metadata`，
开启 `compare_type=True`；扩展连接串从 `Settings.database_url` 注入，不落盘。

## 命名规则

- 文件名 `NNNN_描述.py`，例如 `0001_initial.py`、`0002_add_users.py`；`NNNN` 四位递增。
- `revision` 与文件名前缀一致，`down_revision` 指向上一版；禁止分叉（需要分支时用 `branch_labels` 并在 PR 说明）。
- 保留 T01 创建的 `versions/.gitkeep`，不要删除。

## 向前兼容原则

1. **先加后删**：新增可空列 / 表 → 部署 → 回填 → 再加非空约束 → 后续版本才删旧列。
2. **禁止在线重命名 / 删列**：重命名拆成「加新列 + 双写 + 回填 + 切读 + 删旧列」多个版本。
3. **每个迁移必须可逆**：`downgrade()` 必须能完整回到上一状态；不可逆操作要在 PR 里显式说明。
4. **索引与约束显式命名**：依赖 `Base.metadata` 的 `naming_convention`（`ix_/uq_/ck_/fk_/pk_`），避免 autogenerate 产生随机名。
5. **一次迁移一件事**，便于单独回滚；不要在迁移里写业务数据修复脚本。

## 回滚

```bash
uv run --frozen alembic downgrade -1     # 回退一个版本
uv run --frozen alembic downgrade base   # 回到空库
uv run --frozen alembic upgrade head     # 重新升级
```

回滚前先备份；生产环境由 T08 的 `migrate` 一次性服务执行 `upgrade head`，
应用容器只在迁移成功后启动（`depends_on: migrate: condition: service_completed_successfully`）。
