# 部署与本地全栈（M0-T08）

`docker compose` 一条命令拉起 `nginx + api + worker + postgres + redis`，并用一次性 `migrate` 服务先跑迁移。

## 1. 快速开始

```bash
# 1) 准备环境变量（占位值可直接跑通本地）
cp deploy/env.example deploy/.env

# 2) 构建并启动（首次约 2–4 分钟，取决于依赖下载）
make up
# 等价于：docker compose -f deploy/docker-compose.yml up -d --build

# 3) 看状态：postgres/redis/api/nginx healthy，migrate 以 0 退出
docker compose -f deploy/docker-compose.yml ps -a

# 4) 冒烟
curl -sS http://localhost:8080/healthz     # {"status":"ok"}
curl -sS http://localhost:8080/readyz      # {"status":"ok","checks":{...}}
open http://localhost:8080/docs            # API 文档
```

停止：`make down`。连同数据卷一起清掉：`docker compose -f deploy/docker-compose.yml down -v`。

## 2. 服务与端口

| 服务 | 镜像 | 是否发布到宿主 | 说明 |
|---|---|---|---|
| `nginx` | `nginx:1.27-alpine` | **是**，`NGINX_PORT`（默认 8080）→ 80 | 唯一入口 |
| `api` | 本地构建 `stockpilot-app:local` | 否，仅在 `backend` 网络 `expose 8000` | uvicorn |
| `worker` | 同上 | 否 | `arq app.worker.WorkerSettings` |
| `migrate` | 同上 | 否 | `alembic upgrade head`，`restart: "no"` |
| `postgres` | `postgres:16` | 否 | 命名卷 `pgdata` |
| `redis` | `redis:7` | 否 | 命名卷 `redisdata`，开启 AOF |

`postgres` / `redis` **不暴露宿主端口**。需要本地直连调试时用覆盖文件（已在 `.gitignore` 之外单独提供示例）：

```bash
cp deploy/docker-compose.override.example.yml deploy/docker-compose.override.yml
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml up -d
# 之后可 psql -h 127.0.0.1 -p 5432 -U stockpilot -d stockpilot
```

## 3. 查看日志与排查

```bash
COMPOSE="docker compose -f deploy/docker-compose.yml"

$COMPOSE logs -f api          # 应用日志（JSON，含 request_id）
$COMPOSE logs -f worker       # worker 日志（worker.startup / worker.shutdown）
$COMPOSE logs migrate         # 迁移输出；退出码非 0 时 api/worker 不会启动
$COMPOSE exec api id          # 确认非 root：uid=10001(app) gid=10001(app)
$COMPOSE exec api python -c "import app; print(app.__file__)"
```

常见失败：

- `POSTGRES_PASSWORD` 未设置 → compose 直接报 `请在 deploy/.env 设置 POSTGRES_PASSWORD`。
- `api` 一直 `created` 不启动 → 看 `migrate` 是否失败（`$COMPOSE logs migrate`）。
- `readyz` 503 → `$COMPOSE exec api python -c "import asyncio; from app.core.db import check_db; print(asyncio.run(check_db()))"` 定位是 DB 还是 Redis。

## 4. 验证 worker 存活任务

```bash
COMPOSE="docker compose -f deploy/docker-compose.yml"

# 入队并在 5 秒内取结果
$COMPOSE exec redis redis-cli ping
$COMPOSE exec api python - <<'PY'
import asyncio
from arq import create_pool
from arq.connections import RedisSettings

async def main() -> None:
    pool = await create_pool(RedisSettings.from_dsn("redis://redis:6379/0"))
    job = await pool.enqueue_job("ping")
    print("job:", job.job_id)
    print("result:", await job.result(timeout=5))
    await pool.aclose()

asyncio.run(main())
PY
# 期望输出：result: pong
```

## 5. 指标访问

`/metrics` 在 nginx 层做了来源限制：只允许 `127.0.0.1` 与 `10.0.0.0/8`。

```bash
# 宿主经 nginx 访问 → 403（宿主来源被 NAT 成网桥地址 172.x，未放行）
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/metrics

# nginx 容器内回环访问 → 200
docker compose -f deploy/docker-compose.yml exec nginx \
  wget -qO- http://127.0.0.1/metrics | head -5

# 同网桥内直接打 api，跳过 nginx 限制 → 200（Prometheus sidecar 用这种方式）
docker compose -f deploy/docker-compose.yml exec api \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/metrics').status)"
```

> **不要**在 nginx 放行 `172.16.0.0/12`：docker-proxy 会把宿主访问的源地址 NAT 成网桥网关（172.x），放行等于对公网开放。生产把 Prometheus 放在 `10.0.0.0/8` 管理网，或用 sidecar 直接抓 `api:8000/metrics`。

## 6. 重置数据

```bash
COMPOSE="docker compose -f deploy/docker-compose.yml"

# 只清数据（保留镜像）
$COMPOSE down -v

# 重新初始化并迁移
$COMPOSE up -d --build
```

`down -v` 会删掉 `pgdata` 与 `redisdata`，本地数据不可恢复；生产环境禁止。

## 7. 生产部署要点

1. **密钥管理**：`SECRET_KEY` 用 `openssl rand -hex 32` 生成，通过宿主机 secret（Docker secret / K8S Secret / Vault）注入，不要落在 `deploy/.env`。`deploy/.env` 权限建议 `chmod 600`。
2. **HTTPS**：`deploy/nginx/nginx.conf` 末尾有注释好的 443 段，取消注释并把证书挂到 `/etc/nginx/tls/`（`fullchain.pem`、`privkey.pem`）；80 段改为 301 跳转，并保留 HSTS。
3. **端口**：`NGINX_PORT` 只绑内网或由外层 LB 终止；不要直接把 8080 映射到公网。
4. **文档开关**：`APP_ENV=production` 且未显式设置 `DOCS_ENABLED` 时应用侧默认关闭 `/docs`。
5. **备份**：`pgdata` 是命名卷，至少每日 `pg_dump -Fc` 到独立存储；Redis 仅作队列/缓存，AOF 用于缩短重启后的任务积压。
6. **升级**：`migrate` 用 `alembic upgrade head`；回滚遵循 `backend/alembic/README.md` 的「先加后删、禁止在线重命名」约定，不要依赖 `downgrade` 处理生产数据。
7. **健康检查**：编排层用 `/readyz`（依赖就绪）而不是 `/healthz` 做流量摘除，`/healthz` 只用于存活探测。

## 8. 与 Makefile 的对应关系

| Makefile | 实际命令 |
|---|---|
| `make up` | `docker compose -f deploy/docker-compose.yml up -d --build` |
| `make down` | `docker compose -f deploy/docker-compose.yml down` |
| `make migrate` | `cd backend && uv run --frozen alembic upgrade head`（宿主直连库，不走容器） |

`Makefile` 归 T01 所有，本任务未修改；上表用于核对两者一致（`CONTRACTS.md §11`）。
