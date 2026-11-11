# M0-T08 Docker、Compose、Nginx 与 Worker 空壳

| 项 | 内容 |
|---|---|
| 波次 | Wave 1（Dockerfile/Compose 可先行）→ 与 T07 合并后补全健康检查联调 |
| 依赖 | T01 已合并；联调验收需 T02、T04、T07 已合并 |
| 阻塞 | T11 |
| 分支 | `feat/m0-t08-docker-compose` |
| 建议规模 | 大 |
| 负责 Agent | _未分配_ |

## 目标
`docker compose up` 一条命令拉起 `api / worker / postgres / redis / nginx`，并提供一次性 `migrate` 服务，满足 M0 验收"一条命令启动全栈"。

## 范围
**包含**
1. `deploy/Dockerfile`：多阶段构建（uv 安装依赖 → 精简运行层）；基础镜像 `python:3.12-slim`（固定到具体小版本 tag）；**非 root 用户**；`HEALTHCHECK`；`PYTHONUNBUFFERED=1`；同一镜像供 api/worker/migrate 使用，通过 `command` 区分。
2. `deploy/docker-compose.yml`：服务
   - `postgres`（固定主版本 16，命名卷，`pg_isready` 健康检查）
   - `redis`（固定主版本 7，开启 AOF 可选，健康检查 `redis-cli ping`）
   - `migrate`（一次性：`alembic upgrade head`，依赖 postgres healthy，`restart: "no"`）
   - `api`（`uvicorn app.main:app --host 0.0.0.0 --port 8000`，依赖 migrate 成功完成与 redis healthy，健康检查 `/healthz`）
   - `worker`（`arq app.worker.WorkerSettings`，依赖同 api）
   - `nginx`（反向代理，`depends_on: api`）
   - 仅 `nginx` 对宿主暴露端口；其余服务只在内部网络；**不得暴露 postgres/redis 端口到宿主**（本地调试用 `docker-compose.override.example.yml` 示例说明）。
3. `deploy/nginx/nginx.conf`：`/api/` 与 `/docs` `/healthz` `/readyz` 反代到 api；`/metrics` **仅允许内网/回环网段**；`/` 先返回占位静态页（前端 M9 接入）；支持 `X-Request-ID` 透传；开启基本安全头与 gzip；HTTPS 配置段以注释+说明提供（证书路径挂载），本地 profile 仅 HTTP。
4. `app/worker.py`：ARQ `WorkerSettings`（`redis_settings` 取自 `Settings.redis_url`），含 `ping` 任务（返回 "pong"）、启动/关闭日志（使用 `setup_logging`）；不含业务任务。
5. `deploy/env.example`：列出 `CONTRACTS.md §10` 全部变量，**值为占位符与说明**；根 `README` 增补"快速开始"（由 T08 编写在 `deploy/README.md`，不改根 README）。
6. `deploy/README.md`：本地启动、查看日志、重置数据、生产部署要点（密钥管理、HTTPS、备份提示）。
7. `.dockerignore`。

**不包含**：CI 构建（T09）；前端镜像（M9）；真实 TLS 证书。

## 文件所有权
- **拥有**：`deploy/**`、`backend/app/worker.py`、`.dockerignore`
- **不得修改**：`Makefile`（T01）。如需新增 `make up/down` 的具体命令，已由 T01 预留为 `docker compose -f deploy/docker-compose.yml ...`，若不匹配请在 Issue 说明，由协调者处理。

## 验收标准
- [ ] `cp deploy/env.example deploy/.env`（填占位值）后 `docker compose -f deploy/docker-compose.yml up -d --build` 一条命令成功
- [ ] `docker compose ps`：postgres/redis/api/worker/nginx healthy，`migrate` 以 0 退出
- [ ] 通过 nginx 访问 `/healthz` 与 `/readyz` 均 200；停掉 redis 后 `/readyz` 变 503，恢复后变回 200（贴操作记录）
- [ ] `/metrics` 经 nginx 从宿主外网段访问被拒（403），容器内网访问成功
- [ ] worker 能执行 `ping` 任务（给出入队与结果的命令与输出）
- [ ] 容器以非 root 运行（`docker compose exec api id` 输出）
- [ ] 镜像中不含 `.env`、测试数据、`.git`（`docker run --rm <image> ls -la` 证据）
- [ ] 镜像体积合理（给出大小；超过 600MB 需说明原因）
- [ ] 宿主机仅 nginx 端口被发布（`docker compose ps` 证据）
- [ ] `env.example` 与 CONTRACTS §10 变量一一对应，且无真实密钥
- [ ] `docker compose down -v` 后重新 up 可重复成功
