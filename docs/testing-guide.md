# 测试指南（M0 / T10）

本文是 `docs/08-test-plan.md` 在 M0 骨架阶段的可执行版：所有命令在仓库根目录可直接运行（Windows 需先装 `uv` 3.12 与 GNU make；CI 为 Linux）。共享 fixture 定义见 `backend/tests/conftest.py`，录制数据规范见 `backend/tests/fixtures/README.md`。

## 1. 目录与自动打标

| 目录 | 标记 | 是否允许依赖外部服务 |
|---|---|---|
| `backend/tests/unit/**` | `unit` | **禁止**（不得用 DB / Redis / 网络） |
| `backend/tests/integration/**` | `integration` | 允许，需经 `db_engine` / `redis` fixture |
| `backend/tests/contract/**` | `contract` | 只用录制 fixture |
| `backend/tests/e2e/**` | `e2e` | M9 起启用 |

`conftest.py::pytest_collection_modifyitems` 按路径自动打标，测试文件里**不要**手写 `@pytest.mark.unit`。标记已在 `pyproject.toml` 的 `markers` 注册，`--strict-markers` 生效。

```bash
cd backend && uv run --frozen pytest -m unit --collect-only -q --no-cov
cd backend && uv run --frozen pytest -m integration --collect-only -q --no-cov
```

> 这两条等价于在 `backend/` 下直接 `pytest -m ... --collect-only`；`testpaths` 与 `markers` 都由 `backend/pyproject.toml` 提供。加 `--no-cov` 是为了只收集用例时不去算覆盖率（否则会打印一条与收集无关的 `FAIL Required test coverage` 干扰输出）。

## 2. 常用命令

```bash
make test-unit     # 只跑 tests/unit；不依赖 DB/Redis/网络
make test          # 全量 pytest + 覆盖率（fail_under = 80）
make check         # lint + mypy --strict + import-linter + test
make lint          # ruff check + ruff format --check
make typecheck     # mypy --strict app tests
make lint-imports  # 4 条架构契约
```

等价的直接调用（在 `backend/` 下）：

```bash
uv run --frozen pytest tests/unit -q
uv run --frozen pytest -q
uv run --frozen pytest tests/integration/test_infra_examples.py -q
```

## 3. 共享 fixture 速查

| fixture | 作用域 | 作用 |
|---|---|---|
| `settings` | function | 覆盖 `APP_ENV/DATABASE_URL/REDIS_URL/SECRET_KEY`，自动 `get_settings.cache_clear()` |
| `test_database_url` | session | `TEST_DATABASE_URL` 优先；无 Docker 时 `pytest.skip` 并给提示 |
| `db_engine` | session | 注入连接串、`alembic upgrade head`、结束 `downgrade base` |
| `db_session` | function | 外层事务 + `join_transaction_mode="create_savepoint"`，用例间完全隔离，被测代码 `commit()` 也不泄漏 |
| `app` / `client` | function | `create_app()` + `httpx.ASGITransport`，支持 `app.dependency_overrides` |
| `redis` | function | 默认 `fakeredis`；`REDIS_URL` 可达时自动切真实客户端 |
| `frozen_clock` | function | 固定 `2026-11-11T14:30:00Z`，结束 `reset_clock()` |
| `event_bus` | function | 每个用例一个干净 `EventBus` |

最小示例：

```python
async def test_health(client):
    response = await client.get("/healthz")
    assert response.status_code == 200

async def test_writes_are_isolated(db_session):
    await db_session.execute(text("INSERT INTO audit_log (action, detail) "
                                  "VALUES ('demo', CAST('{}' AS jsonb))"))
    await db_session.commit()   # 只提交到 savepoint，别的用例看不到
```

可直接运行范例：

```bash
cd backend && uv run --frozen pytest tests/integration/test_infra_examples.py -q
```

## 4. 真实数据库

```bash
export TEST_DATABASE_URL='postgresql+asyncpg://user@host:5432/testdb'
make test
```

未设置 `TEST_DATABASE_URL` 时，若本机有 Docker，`db_engine` 会用 `testcontainers` 临时拉起 `postgres:16`；两者都不可用则依赖 DB 的用例**明确 skip**（提示信息含具体原因），`make test-unit` 不受影响。绝不要用生产库或带真实凭据的连接串。

## 5. 时间与网络隔离

- 涉及「当前时间 / 下一交易日」的测试一律注入 `frozen_clock`，不要 `datetime.now()`；
- 交易日历用 `app.core.calendar`，时钟用 `app.core.clock.get_clock()`；
- 外部供应商响应走 `tests/fixtures/loader.py::load_fixture`，禁止在测试里发真实 HTTP；
- `client` 是 ASGI 内存传输，不监听端口；`redis` 默认 `fakeredis`。

## 6. Hypothesis profile

`conftest.py` 注册两个 profile，由 `HYPOTHESIS_PROFILE` 选择（默认 `dev`）：

| profile | max_examples | deadline |
|---|---|---|
| `dev` | 50 | None |
| `ci` | 200 | None |

```bash
cd backend && HYPOTHESIS_PROFILE=ci uv run --frozen pytest tests/unit/core/test_calendar.py -q
cd backend && uv run --frozen pytest tests/unit/core/test_calendar.py -q
```

## 7. 顺序稳定性与覆盖率门槛

项目**不依赖** `pytest-randomly`（T01 依赖清单未列该包）；下面两条命令结果应一致：

```bash
cd backend && uv run --frozen pytest -p no:randomly -q
cd backend && uv run --frozen pytest -q
```

`pyproject.toml` 自 T10 起 `fail_under = 80`（附录 A 的 E1–E7 豁免结束）。模块核心逻辑的 85/90/95% 目标用局部断言或任务卡验收项检查，不改全局门槛。

## 8. 覆盖率门槛自检（可复现，两种等价做法）

**做法一（已实测，最干净）**：临时把门槛抬高到当前覆盖率之上，跑一次应失败，随后还原。

```bash
cd backend
sed -i.bak 's/^fail_under = 80$/fail_under = 100/' pyproject.toml
grep -n fail_under pyproject.toml             # 确认已临时改成 100
uv run --frozen pytest -q; echo "exit=$?"     # 期望 exit=1
mv pyproject.toml.bak pyproject.toml          # 务必还原
grep -n fail_under pyproject.toml             # 确认回到 80
```

M0-T10 实测输出：`256 passed` 但 `FAIL Required test coverage of 100.0% not reached. Total coverage: 99.48%`，`exit=1` —— 说明门槛确实能阻断流水线，且不是"用例失败"造成的假阳性。

**做法二（更接近真实退化）**：临时移走若干测试文件，覆盖率掉到门槛以下应失败：

```bash
cd backend
mkdir -p /tmp/m0-cov-check
mv tests/unit/core/test_errors.py tests/unit/core/test_config.py \
   tests/unit/core/test_events.py /tmp/m0-cov-check/
uv run --frozen pytest -q; echo "exit=$?"     # 期望非 0
mv /tmp/m0-cov-check/*.py tests/unit/core/
uv run --frozen pytest -q                     # 恢复后全绿
```

Windows 环境建议用 `python` 脚本配合 `try/finally` 保证还原；**务必确认文件已还原再提交**（`git status` 干净）。
