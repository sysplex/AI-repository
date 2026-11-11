# M0-T07 Redis 客户端、健康检查、指标与生命周期

| 项 | 内容 |
|---|---|
| 波次 | Wave 2 |
| 依赖 | **T02、T03、T04 已合并** |
| 阻塞 | T08（Compose 健康检查）、T10、T11（顺序执行下以 M0 README 附录 B 线性序列为准） |
| 分支 | `feat/m0-t07-health-metrics` |
| 建议规模 | 中 |
| 负责 Agent | _未分配_ |

## 目标
实现 `/healthz`、`/readyz`、`/metrics`，Redis 客户端，Prometheus 指标中间件，应用生命周期钩子，按 `CONTRACTS.md §8`。

## 范围
**包含**
1. `core/redis.py`：`get_redis/check_redis/close_redis`（`redis.asyncio`，`decode_responses=True`，连接/读写超时 2 秒，失败返回 False 不抛）。
2. `api/health.py`：三个根路径端点；`/readyz` 并发检查 DB 与 Redis，**整体 2 秒超时**，超时视为不就绪；响应体见契约；这些端点**不要求认证**，且**不出现在 OpenAPI**（`include_in_schema=False`）。
3. `core/metrics.py`：`install_metrics`；使用独立 `CollectorRegistry`（避免测试间重复注册）；`path_template` 使用路由模板，未匹配记为 `unmatched`；`/metrics`、`/healthz`、`/readyz` 自身不计入请求指标。
4. `core/lifecycle.py`：`on_startup`（输出启动日志含版本与环境）、`on_shutdown`（调用 `dispose_engine()` 与 `close_redis()`，任一失败仍继续另一个并记录日志）。
5. **整体重写** `api/router.py`（T01 建可运行空壳 → T07 拥有并重写，见 `CONTRACTS.md §1` 与所有权矩阵）：把 health 路由挂到 `root_router`。
6. 修改 `core/middleware.py` **仅限"指标中间件插入点"那一处**：把 T02 预留的注释替换为唯一一行 `install_metrics(app, settings)` 调用（这是 `install_metrics` 的**唯一调用点**，`main.py` 不单独调用，见 `CONTRACTS.md §3/§8/§9`）。

**不包含**：Nginx 内网限制（T08）；业务指标（后续模块）。

## 文件所有权
- **拥有**：`core/redis.py`、`core/metrics.py`、`core/lifecycle.py`、`api/health.py`
- **有限修改**：`api/router.py`（T01 建空壳后由 T07 整体重写）、`core/middleware.py`（**仅插入点一行**）
- **新增测试**：`tests/integration/test_health.py`、`tests/unit/core/test_metrics.py`、`tests/unit/core/test_redis.py`（使用 `fakeredis` 或 `REDIS_URL` 指向的测试 Redis）

## 验收标准
- [ ] `GET /healthz` 恒 200，且在 DB/Redis 全部不可用时仍 200（测试）
- [ ] `GET /readyz`：二者正常 → 200 且 `checks` 全 true；任一不可用 → 503，对应项 false（测试：模拟不可用）
- [ ] `/readyz` 在依赖卡住时 ≤ 2.5 秒返回 503（测试：模拟挂起）
- [ ] 三个端点不出现在 `/api/v1/openapi.json`
- [ ] `/metrics` 输出 Prometheus 文本；请求若干次后 `http_requests_total` 与直方图有对应样本；标签使用路由模板（测试：访问带路径参数的测试路由，断言标签为模板而非具体值）
- [ ] 访问不存在的随机路径 N 次 → 标签基数不增长（均为 `unmatched`）（测试）
- [ ] `metrics_enabled=false` → `/metrics` 返回 404（测试）
- [ ] 关闭应用时 engine 与 redis 均被关闭，一个失败不影响另一个（测试）
- [ ] 无请求时 `/healthz` 响应时间 < 50ms（粗略断言）
- [ ] `make check` 全绿；覆盖率 ≥ 90%
