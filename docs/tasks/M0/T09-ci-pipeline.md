# M0-T09 CI 流水线与仓库自动化

| 项 | 内容 |
|---|---|
| 波次 | Wave 1 |
| 依赖 | T01 已合并 |
| 阻塞 | T11 |
| 分支 | `feat/m0-t09-ci` |
| 建议规模 | 中 |
| 负责 Agent | _未分配_ |

## 目标
GitHub Actions 实现 `docs/07-delivery-standard.md §3` 的 CI：静态检查、测试（含 Postgres/Redis 服务容器）、安全扫描、镜像构建。

## 范围
**包含**
1. `.github/workflows/ci.yml`，触发：`pull_request`、`push` 到 `main`。作业：
   - `lint`：`uv sync` → ruff check + format --check
   - `typecheck`：mypy --strict
   - `architecture`：import-linter
   - `test`：服务容器 `postgres:16`、`redis:7`；设置 `DATABASE_URL`、`REDIS_URL`、`TEST_DATABASE_URL`、`SECRET_KEY`（工作流内使用**仅限 CI 的随机占位值**，禁止使用任何真实密钥）；运行 `pytest --cov`，上传覆盖率报告为 artifact；覆盖率门槛读取 pyproject 配置
   - `security`：`pip-audit`（对锁定依赖）+ `gitleaks`（扫描全历史）
   - `docker`：`docker build -f deploy/Dockerfile`（不推送；T08 合并前该作业需 `if: hashFiles('deploy/Dockerfile') != ''` 守卫）
   - `docs`：Markdown 链接检查（对 `docs/**`、根 README；忽略外部站点的偶发失败时设为 non-blocking 并说明）
2. 缓存：uv 缓存、Docker 层缓存（`gha` cache）。
3. `concurrency`：同分支新提交取消旧运行。
4. 权限最小化：`permissions: contents: read`；第三方 Action **固定到完整 commit SHA**（并在注释写明对应版本）。
5. `.github/dependabot.yml`：pip（uv）、github-actions、docker 每周更新。
6. `.github/CODEOWNERS`：`* @sysplex`（如协调者另有安排以 Issue 为准）。
7. `docs/ci.md`（由本任务新增，不改 01–09）：作业说明、如何本地复现每个作业、常见失败排查、**分支保护推荐设置清单**（必须检查通过才可合并、禁止直接推送 main、需要 1 个评审——私有仓库免费版可能不支持，写明替代做法）。

**不包含**：部署（CD）；真实环境密钥配置。

## 文件所有权
- **拥有**：`.github/workflows/**`、`.github/dependabot.yml`、`.github/CODEOWNERS`、`docs/ci.md`
- **不得修改**：`.github/PULL_REQUEST_TEMPLATE.md`、`ISSUE_TEMPLATE/**`（协调者维护）

## 验收标准
- [ ] 新开 PR 自动触发全部作业并全绿（贴 Actions 运行链接/截图）
- [ ] 人为引入：ruff 违规 / 类型错误 / 架构违规 import / 失败测试 / 伪造密钥 → 对应作业**各自失败**（各给一条失败运行证据，随后还原）
- [ ] `test` 作业确实连接了 Postgres 与 Redis（日志证据）
- [ ] 所有第三方 Action 已固定 SHA；workflow 权限为最小
- [ ] `concurrency` 生效（连续推送两次，旧运行被取消）
- [ ] 工作流文件中无任何真实密钥；`gitleaks` 通过
- [ ] `docs/ci.md` 命令在本地可复现对应作业
