# CI 流水线（M0-T09）

工作流文件：`.github/workflows/ci.yml`。对应 `docs/07-delivery-standard.md §3` 的实现，本文是它的操作手册。

## 1. 作业总览

| 作业 | 名称 | 做什么 | 失败含义 |
|---|---|---|---|
| `lint` | lint (ruff) | `ruff check .` + `ruff format --check .`；并用 step 级 `hashFiles` 输出 `dockerfile_present` 供 docker 守卫使用 | 风格或静态问题 |
| `typecheck` | typecheck (mypy --strict) | `mypy --strict app tests` | 类型不严格 |
| `architecture` | architecture (import-linter) | `lint-imports`，4 条分层/独立/禁止契约 | 跨层引用或模块越界 |
| `test` | test (pytest + postgres + redis) | 服务容器 `postgres:16`、`redis:7`；`pytest` 全量 + 覆盖率（门槛取 `pyproject.toml` 的 `fail_under`） | 用例失败或覆盖率不足 |
| `security` | security (pip-audit + gitleaks) | 锁定依赖漏洞扫描 + 全历史密钥扫描 | 已知漏洞或疑似密钥 |
| `docker` | docker build | `needs: lint`，由 lint 的 step 级 `hashFiles` 输出驱动 job 级守卫；`docker build -f deploy/Dockerfile`（不推送）+ 镜像冒烟（非 root、无 `.env/.git/tests`） | 镜像构建或镜像内容不合规；T08 未合并时为 skipped |
| `docs` | docs (markdown links) | `docs/**` 与根 `README.md` 的相对链接存在性（阻断）+ 外链探测（非阻断） | 文档里有断链 |

触发：`pull_request`（任意分支）与 `push` 到 `main`。

## 2. 并发、权限与 Action 版本

- **并发**：`concurrency: ci-${{ github.workflow }}-${{ github.ref }}` + `cancel-in-progress: true`。同一 PR/分支连续推送时，旧运行被取消（可在 Actions 里看到 `cancelled`）。
- **权限**：顶层 `permissions: contents: read`，不授予写 PR、写包、推镜像的能力。
- **Action 固定 SHA**：所有第三方 Action 都固定到完整 commit SHA，行尾注释给出对应版本。升级由 dependabot 提 PR。

| Action | 版本 | 用途 |
|---|---|---|
| `actions/checkout` | v4.2.2 | 拉代码（`security` 作业用 `fetch-depth: 0` 取全历史） |
| `astral-sh/setup-uv` | v5.4.2 | 安装 uv + 缓存（`cache-dependency-glob: backend/uv.lock`） |
| `actions/upload-artifact` | v4.4.3 | 上传覆盖率报告 |
| `docker/setup-buildx-action` | v3.7.1 | Buildx |
| `docker/build-push-action` | v6.9.0 | 构建镜像（`cache-from/to: type=gha`） |

`gitleaks` 不走官方 Action：其 v2 Action 对私有仓库需要付费 license，因此 `security` 作业直接下载固定版本 `8.24.0` 的 CLI 二进制运行。

### 2.1 docker 守卫为何分两步（GitHub 表达式限制）

GitHub 的上下文可用性表里，`hashFiles()` **只允许**出现在 `jobs.<job_id>.steps.*` 的若干键中，**不能**用于 `jobs.<job_id>.if`——该位置只允许 `github`、`needs`、`vars`、`inputs` 和 `always/cancelled/success/failure`。把 `if: hashFiles(...)` 写在 job 级会让**整个工作流解析失败**，Actions 里表现为一个 0 job、创建即 `failure` 的运行（本地 `actionlint` 能直接报出）。

因此 `ci.yml` 用两步等价实现任务卡要求的守卫，作业数仍为 7 个：

1. `lint` 在 checkout 后用 step 级 `if: hashFiles('deploy/Dockerfile') != ''` 检测，命中时把 `present=true` 写入 step output，并暴露为 job output `dockerfile_present`；
2. `docker` 作业 `needs: lint`，用 job 级 `if: ${{ needs.lint.outputs.dockerfile_present == 'true' }}` 判断。

`deploy/Dockerfile` 不存在（T08 未合并）→ 检测 step 被跳过、输出为空 → `docker` 作业 **skipped** 而不是凭空失败；文件存在 → 作业实跑构建与冒烟。守卫表达式 `hashFiles('deploy/Dockerfile') != ''` 仍保留在文件中，只是落在 GitHub 允许的 step 级位置。若 `lint` 失败，`needs` 不满足也会使 `docker` 为 skipped，属 GitHub 的正常依赖语义。

## 3. 本地复现每个作业

以下命令都在仓库根执行，Windows 需 GNU make + uv（或直接在 `backend/` 下用等价的 `uv run --frozen ...`）。

```bash
# workflow 静态校验（可选工具，捕获 GitHub 表达式/上下文限制，如 job 级 hashFiles）
actionlint .github/workflows/ci.yml

# lint
cd backend && uv run --frozen ruff check . && uv run --frozen ruff format --check .

# typecheck
cd backend && uv run --frozen mypy --strict app tests

# architecture
cd backend && uv run --frozen lint-imports

# test（需要真实 Postgres/Redis；没有则用下面的单行启动容器）
docker run -d --rm --name m0-pg -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=ci -p 5432:5432 postgres:16
docker run -d --rm --name m0-redis -p 6379:6379 redis:7
export APP_ENV=ci
export DATABASE_URL='postgresql+asyncpg://postgres@localhost:5432/ci'
export TEST_DATABASE_URL='postgresql+asyncpg://postgres@localhost:5432/ci'
export REDIS_URL='redis://localhost:6379/0'
export SECRET_KEY='ci-only-placeholder-secret-not-a-real-credential'
cd backend && uv run --frozen pytest -q --cov-report=xml

# security
cd backend && uv run --frozen pip-audit --progress-spinner off
curl -sSfL https://github.com/gitleaks/gitleaks/releases/download/v8.24.0/gitleaks_8.24.0_linux_x64.tar.gz | tar -xz -C /tmp gitleaks
/tmp/gitleaks detect --source . --log-opts="--all" --redact --verbose

# docker
docker build -f deploy/Dockerfile -t stockpilot-ci:local .
docker run --rm stockpilot-ci:local id          # uid=10001(app)
docker run --rm stockpilot-ci:local ls -a /app

# docs
python3 -c "print('见 ci.yml 的 docs 作业内联脚本')"   # 相对链接检查逻辑内联在工作流里
```

CI 里的连接串刻意写成 `postgresql+asyncpg://postgres@localhost:5432/ci`（trust 认证、**无口令**），`SECRET_KEY` 是仅 CI 使用的占位串，两者都不构成凭据。

## 4. 常见失败排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `lint` 报 `Would reformat` | 本地没跑 `make fmt` | `cd backend && uv run --frozen ruff format .` 后重推 |
| `typecheck` 在 CI 失败但本地通过 | 本地 `.venv` 有未同步的包 | `uv sync --frozen` 后重跑；确认 `uv.lock` 已提交 |
| `test` 报连接被拒 | 服务容器未就绪 | 已配 `--health-cmd`，若仍偶发，检查 `options` 里 health 参数是否被改动 |
| `test` 覆盖率卡在门槛 | 删了测试或新代码未覆盖 | 本地 `uv run --frozen pytest` 看 `Missing` 列，补用例；门槛在 `pyproject.toml` 的 `[tool.coverage.report] fail_under` |
| `test` 报 `未设置 TEST_DATABASE_URL` 而 skip | 环境变量没注入 | 检查 `test` 作业的 `env:` 段；`db_engine` fixture 在没有 `TEST_DATABASE_URL` 且无 docker 时会 skip |
| `security` pip-audit 报新 CVE | 上游依赖出现漏洞 | 升级该依赖并同步 `uv.lock`；若暂无修复版本，在 PR 里注明并加 `--ignore-vuln`（需协调者批准） |
| `security` gitleaks 命中 | 提交里出现疑似密钥 | **不要**在 CI 里加 allowlist 掩盖；轮换该密钥并从历史移除（`git filter-repo`），再重推 |
| Actions 运行 0 个 job 且创建即 failure | workflow 解析失败，典型是把 `hashFiles()` 写在 job 级 `if` | 本地 `actionlint .github/workflows/ci.yml` 可直接报出；按 §2.1 把守卫拆到 step 级 |
| `docker` 作业 skipped | `deploy/Dockerfile` 不存在（T08 未合并），或 `lint` 失败使 `needs` 未满足 | T08 未合并时属预期；T08 合并后必须实际运行。若因 lint 红而 skipped，先修 lint |
| `docker` 构建慢 | 缓存未命中 | 首次运行正常；后续依赖 `type=gha` 缓存，改动 `uv.lock` 会让依赖层失效 |
| `docs` 相对链接失败 | 文件被移动/删除 | 按报错的 `文件: 目标` 修正路径；外链探测失败不影响结论 |

## 5. 覆盖率与产物

- 门槛来自 `backend/pyproject.toml`：`[tool.coverage.report] fail_under = 80`，CI 不覆盖该值。
- 产物 `coverage-report`（`backend/coverage.xml`、`backend/.coverage`）保留 7 天，可在 run 页面下载。
- 需要 HTML 报告时本地跑：`cd backend && uv run --frozen pytest --cov-report=html`。

## 6. 分支保护：推荐设置与**免费版替代做法（R12）**

### 6.1 推荐设置（仓库支持时）

在 Settings → Branches → Branch protection rules，对 `main` 开启：

- [ ] Require a pull request before merging（必需评审数 ≥ 1）
- [ ] Require status checks to pass before merging
  - 必选检查：`lint (ruff)`、`typecheck (mypy --strict)`、`architecture (import-linter)`、`test (pytest + postgres + redis)`、`security (pip-audit + gitleaks)`、`docker build`、`docs (markdown links)`
  - [ ] Require branches to be up to date before merging
- [ ] Require conversation resolution before merging
- [ ] Do not allow bypassing the above settings（含管理员）
- [ ] Restrict who can push to matching branches（只留发布机器人）
- [ ] Require linear history（配合 squash merge）

### 6.2 私有仓库免费版无法设置分支保护时的替代做法

fine-grained PAT 调用分支保护 API 返回 `403 Resource not accessible`，且私有仓库免费套餐不提供 branch protection。此时靠**流程约束 + 可审计证据**兜底，逐条对应上面的设置项：

1. **PR 必过 CI 的团队约定（替代 "Require status checks"）**
   - `main` 只接受 PR 合并，禁止本地 `git push origin main`。
   - 合并前必须在 PR 页面确认 7 个作业全绿；任一红/黄（含 skipped 的 `docker`）都不得合并。
   - PR 模板的「DoD 自检」里保留 `make check` 与 CI 链接两栏，作为人工核对点。
2. **CODEOWNERS（替代 "Require review from Code Owners"）**
   - `.github/CODEOWNERS` 指定 `* @sysplex`。免费版不会强制，但 PR 会自动请求该评审人，形成可见的待办。
3. **协调者人工评审清单（替代 "Require approvals"）**
   合并前逐项打勾并留在 PR 评论里：
   - [ ] 7 个作业全绿，且 `docker` 为实跑（非 skipped）
   - [ ] PR 正文四段齐全：完成内容 / 验收证据 / 假设与偏差 / 遗留问题
   - [ ] 只修改了任务卡「文件所有权」内的文件（`git diff --stat` 核对）
   - [ ] 无密钥、无真实 `.env`、无大文件（`detect-secrets` + gitleaks 双绿）
   - [ ] 接口签名与 `CONTRACTS.md` 一致
   - [ ] squash merge，提交标题带 `(#PR)`
4. **禁止直推 `main`（替代 "Restrict who can push"）**
   - 本地配置兜底（开发者各自执行一次）：
     ```bash
     git config --local branch.main.pushRemote no_push
     ```
   - 误推后的补救：`git revert` 生成反向 PR，不用 `push --force` 掩盖历史。
5. **线性历史（替代 "Require linear history"）**
   - 统一 squash merge；`main` 上每次合并只留一个提交。
6. **可审计性**
   - 每次合并的记录留在 PR（CI 链接 + 评审清单 + merge commit SHA），可回溯"当时确实全绿"。
   - 里程碑收尾（T11）把关键运行的 Actions 链接汇总进 `docs/acceptance/M0.md`。

> 一旦仓库升级套餐或改用组织仓库，按 §6.1 直接开启对应规则即可，流程无需改动。

## 7. 依赖更新

`.github/dependabot.yml` 每周一凌晨（Asia/Shanghai）检查三类依赖：

- `uv`（`/backend`）：Python 运行时与开发依赖，分 `python-runtime` / `python-dev` 两组，减少 PR 数量。
- `github-actions`（`/`）：更新 Action 的 commit SHA 与注释版本号。
- `docker`（`/deploy`）：`Dockerfile` 里的基础镜像 tag。

合并要求：CI 全绿 + 变更仅涉及依赖/锁文件；涉及主版本升级需在 PR 里说明影响面，并在本地跑一次 `make check` 与 `docker compose build`。

## 8. 与本地 `make check` 的对应关系

| CI 作业 | 本地等价 |
|---|---|
| `lint` | `make lint` |
| `typecheck` | `make typecheck` |
| `architecture` | `make lint-imports` |
| `test` | `make test`（需 `TEST_DATABASE_URL` 才能真正跑 DB 用例） |
| `security` | `cd backend && uv run --frozen pip-audit` + gitleaks CLI |
| `docker` | `docker build -f deploy/Dockerfile .` |
| `docs` | 见 §3 最后一条 |

`make check` = `lint` + `typecheck` + `lint-imports` + `test`，是提交前必须全绿的最小集合。
