# M0-T10 测试基础设施

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | **T01、T02、T04、T06 已合并**（Settings、DB、冻结时钟） |
| 阻塞 | T11；M1+ 全部测试依赖本任务 |
| 分支 | `feat/m0-t10-test-infra` |
| 建议规模 | 中 |
| 负责 Agent | _未分配_ |

## 目标
提供全项目共享的测试基座：fixtures、标记、数据库隔离、冻结时钟、HTTP 客户端，以及 `docs/08-test-plan.md` 要求的"录制 fixture / 时间冻结 / 属性测试"约定，使后续模块只需写业务测试。

## 范围
**包含**
1. `tests/conftest.py` 提供：
   - `settings`：覆盖环境变量的 Settings（自动 `get_settings.cache_clear()`）
   - `db_engine`（session 级）：使用 `TEST_DATABASE_URL`，会话开始时 `alembic upgrade head`，结束清理；若变量未设置且本机有 Docker，则回退用 `testcontainers` 启动 Postgres；两者都不可用时 `pytest.skip` 并给出明确提示（`unit` 标记测试不应依赖它）
   - `db_session`（函数级）：每个测试一个事务，结束回滚（嵌套事务/savepoint 方案，确保被测代码中的 commit 不污染其他测试）
   - `client`：`httpx.AsyncClient(transport=ASGITransport(app=create_app()))`，并带依赖覆盖支持
   - `redis`：默认 `fakeredis.aioredis`；集成测试可通过 `REDIS_URL` 使用真实 Redis
   - `frozen_clock`：安装 `FrozenClock`（默认 `2026-11-11T14:30:00Z`），测试结束自动 `reset_clock()`
   - `event_bus`：每个测试一个干净的 `EventBus`
2. 自动标记：`tests/unit` → `unit`；`integration` → `integration`；`contract`；`e2e`（通过 `pytest_collection_modifyitems` 按目录自动打标）。`make test-unit` 只跑 unit 且不依赖外部服务。
3. `tests/fixtures/README.md`：录制 fixture 的目录规范（`tests/fixtures/<provider>/<symbol>/<endpoint>.json`、命名、脱敏、如何重新录制）；以及 `tests/fixtures/loader.py`（`load_fixture(path)`）。
4. `hypothesis` 配置：`tests/conftest.py` 注册 profile（`ci`：`max_examples=200, deadline=None`；`dev`：50），由环境变量 `HYPOTHESIS_PROFILE` 选择。
5. 示例测试（证明基座可用，兼作使用范例）：`tests/integration/test_infra_examples.py`（db_session 回滚隔离、client 访问 `/healthz`、frozen_clock、event_bus）。
6. 调整 `pyproject.toml` 的覆盖率门槛为 **`fail_under = 80`**（本任务**被授权修改 pyproject 的 `[tool.coverage]` 与 `[tool.pytest.ini_options]` 两段**，其余段不得改动）。
7. `docs/testing-guide.md`（新增）：如何写单元/集成/契约测试、fixture 用法、如何隔离时间与网络、命名与目录约定。

**不包含**：任何业务 fixture（行情样本归 M2）；E2E（Playwright，M9）。

## 文件所有权
- **拥有**：`backend/tests/conftest.py`、`backend/tests/fixtures/**`、`docs/testing-guide.md`、`tests/integration/test_infra_examples.py`
- **有限修改**：`backend/pyproject.toml` 的 `[tool.coverage]`、`[tool.pytest.ini_options]`
- **协调**：T04 测试里就地定义的 DB fixture，由本任务迁移为共享 fixture 并删除重复定义（**允许修改 T04 的三个测试文件，仅限替换 fixture 引用**）

## 验收标准
- [ ] 在设置了 `TEST_DATABASE_URL` 的环境运行 `make test` 全绿；未设置且无 Docker 时，依赖 DB 的测试被**明确 skip**（带提示）而非报错
- [ ] 隔离性：测试 A 写入的数据，测试 B 读不到；被测代码内 `commit()` 也不泄漏（专门测试）
- [ ] 随机顺序运行（`pytest -p no:randomly` 与随机种子各一次，或 `pytest-randomly`）结果一致
- [ ] `frozen_clock` 下 `get_clock().now()` 固定；测试结束后恢复 `SystemClock`（测试）
- [ ] `make test-unit` 不依赖 DB/Redis/网络（断开网络与服务环境下运行通过，给出证据）
- [ ] 目录自动打标正确：`pytest -m unit --collect-only` 仅含 unit 测试
- [ ] `docs/testing-guide.md` 的每个示例命令可运行
- [ ] 覆盖率门槛生效：故意删一个测试使覆盖率低于门槛 → `make test` 失败（证据，随后还原）
- [ ] T04 的三个测试文件已迁移到共享 fixture 且仍全绿
- [ ] `make check` 全绿
