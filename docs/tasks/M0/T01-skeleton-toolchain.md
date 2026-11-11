# M0-T01 仓库骨架与工具链

| 项 | 内容 |
|---|---|
| 波次 | **Wave 0（阻塞所有任务，最先完成并合并）** |
| 依赖 | 无 |
| 阻塞 | T02–T11 |
| 分支 | `feat/m0-t01-skeleton` |
| 建议规模 | 小（半天） |
| 负责 Agent | _未分配_ |

## 目标
建立可运行的后端骨架：目录结构、依赖、工具链、质量门禁、以及供后续任务填充的**空壳（stub）文件**，使 `make check` 与 `uvicorn app.main:app` 在空壳状态下即可通过/启动。

## 范围
**包含**
1. 按 `CONTRACTS.md §1` 创建全部目录与 `__init__.py`（`modules/*` 仅空包）。
2. `backend/pyproject.toml`：Python 3.12；**一次性声明 M0 全部依赖**（避免后续任务改此文件）：
   - 运行：`fastapi` `uvicorn[standard]` `pydantic>=2` `pydantic-settings` `sqlalchemy[asyncio]>=2` `asyncpg` `alembic` `structlog` `redis` `arq` `prometheus-client` `exchange-calendars` `httpx`
   - 开发：`pytest` `pytest-asyncio` `pytest-cov` `hypothesis` `testcontainers[postgres]` `fakeredis` `ruff` `mypy` `import-linter` `pip-audit` `pre-commit`
   - 版本选择：取稳定版本，**避开发布不足 14 天的版本**；生成并提交 `uv.lock`。
3. 工具配置（均在 pyproject 内）：
   - `ruff`：lint + format，行宽 100，启用 `E,F,I,UP,B,SIM,ASYNC,S`（`tests/` 允许 `S101`）。
   - `mypy`：`strict = true`，插件 pydantic；`tests/` 可放宽但仍需类型标注。
   - `pytest`：`asyncio_mode = "auto"`，注册标记 `unit integration contract e2e`，`--strict-markers`。
   - `coverage`：`source = app`，`fail_under = 80`（T10 之后生效；T01 阶段可先设为 0 并在注释说明由 T10 调整——**以 T10 卡为准**）。
   - `import-linter`（`[tool.importlinter]`）按 `docs/02-architecture.md §4` 配置契约：
     a. 分层契约：`app.api` → `app.modules.{research,screener,scheduler}` → `app.modules.{identity,marketdata,strategy,simbroker,ai,notify}` → `app.domain` → `app.core`；
     b. 独立契约：`marketdata`、`ai`、`identity` 互不依赖且不依赖其他业务模块；
     c. 禁止契约：任何模块不得引用其他模块的 `repo` / `models` / `adapters`；
     d. 禁止契约：`yfinance`、`anthropic`、`alpaca*` 仅允许出现在 `app.modules.*.adapters` 中。
4. `Makefile`（目标**与命令实现**见 `CONTRACTS.md §11`，`up/down/migrate/revision` 一次写全，T08 不改本文件）、`.editorconfig`、`.pre-commit-config.yaml`（ruff、ruff-format、基本文件检查、**gitleaks 或 detect-secrets**）。
5. **空壳文件**（最小可运行，no-op，签名遵守 CONTRACTS）：
   `core/config.py`（仅 `Settings` 含 app_env/app_name/app_version + `get_settings()`，**不校验三必填变量**）、`core/logging.py`（**不导出** `request_id_var` 等三个 ContextVar，归 T02）、`core/middleware.py`（`install_middlewares` 空实现 + 保留「指标中间件插入点」注释占位，**不调用** `install_metrics`）、`core/errors.py`（`register_exception_handlers` 空实现）、`core/lifecycle.py`（空 `on_startup/on_shutdown`）、`api/router.py`（空 `root_router`、`api_router`）；另建 `alembic/versions/.gitkeep`（git 不保留空目录，T04 提交迁移时保留该文件）。
6. `app/main.py`：严格按 `CONTRACTS.md §9` 实现 `create_app()` **与 `lifespan`**（签名与 no-op 实现见 §9），`app = create_app()`；空壳期 `lifespan` 可直接 `yield`，避免 `NameError`。
7. 一个冒烟测试 `tests/unit/test_smoke.py`：`create_app()` 可构建且 `/docs` 可访问（用 httpx ASGITransport）。

**不包含**：任何真实业务/配置/日志/错误/DB 逻辑（归 T02–T07）；Docker（T08）；CI（T09）；`conftest.py`（T10）。

## 文件所有权
- **创建并拥有**：`backend/pyproject.toml`、`backend/uv.lock`、`Makefile`（含 `up/down/migrate/revision` 完整命令）、`.editorconfig`、`.pre-commit-config.yaml`、`backend/app/main.py`、全部 `__init__.py`、`backend/alembic/versions/.gitkeep`、`backend/tests/unit/test_smoke.py`
- **创建空壳（之后移交）**：见上第 5 点（移交给 T02/T03/T07）
- **不得修改**：`docs/**`、`AGENTS.md`、`.github/**`

## 验收标准
- [ ] 目录与 CONTRACTS §1 一致（给出 `tree` 输出）
- [ ] `make install` 在干净环境成功
- [ ] `make lint`、`make typecheck`、`make lint-imports`、`make test` 全部通过
- [ ] 故意制造一个违规 import（如 `identity` 引用 `marketdata.repo`）→ `make lint-imports` **失败**，证据贴 PR（随后还原）
- [ ] `uvicorn app.main:app` 能启动（**T01 阶段**：空壳 `Settings` 不要求 `DATABASE_URL`/`REDIS_URL`/`SECRET_KEY`，不带占位也能启动；该行为在 **T02 合并后**反转为「缺失即启动失败」，阶段切换点见 `CONTRACTS.md §2`，评审勿跨阶段套用）
- [ ] `pre-commit run --all-files` 通过，且能拦截一个伪造的密钥样例（证据贴 PR，随后还原）
- [ ] `uv.lock` 已提交；无发布不足 14 天的依赖版本（给出检查方式说明）

## 交接说明
合并后在 Issue 评论 "T01 已合并 @ <commit>"，协调者会放行 Wave 1。
