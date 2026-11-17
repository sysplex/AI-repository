# StockPilot 生产运维排障手册与故障应急预案 (RUNBOOK)

> **版本**：v1.0.0 ｜ **维护团队**：SRE & Backend Platform ｜ **更新时间**：2026-11-17  
> **基线规范**：严格遵循 [`GEMINI.md`](GEMINI.md) 基础设施拓扑与版本回滚铁律。

---

## 1. 基础设施拓扑与快速访问索引

| 组件 / 服务 | 访问地址 | 认证凭证 | 运维角色与作用 |
|---|---|---|---|
| **GitHub 代码主库** | `https://github.com/sysplex/AI-repository` | `token: github_pat_***` | 源代码主分支、CI/CD 触发源、语义化发布 Tag |
| **内网 Gitea** | `http://192.168.50.213:3000/` | `sun` / `123456` | 内网代码镜像备份、GitOps 部署清单同步 |
| **内网 Harbor 镜像库** | `http://192.168.50.36:30088/` | `admin` / `Harbor12345` | Docker 生产不可变版本镜像存储与分发 |
| **Argo CD (GitOps)** | `https://192.168.50.36:31443/` | `admin` / `12345678` | K8s 声明式发布、应用状态监控与一键秒级回滚 |
| **Jenkins 构建节点** | `http://192.168.50.213:8080/` | `sun` / `123456` | 多架构容器镜像自动化流水线构建 |
| **K8s Master 控制节点** | `192.168.50.36` | SSH / kubeconfig | 集群调度控制平面、API Server、etcd |
| **K8s Worker Node1** | `192.168.50.37` | SSH / kubeconfig | 负载运行节点 (API / Worker / Ingress) |
| **K8s Worker Node2** | `192.168.50.38` | SSH / kubeconfig | 负载运行节点 (API / Worker / Redis) |
| **K8s Worker Node3** | `192.168.50.39` | SSH / kubeconfig | 负载运行节点 (PostgreSQL / StatefulSet) |
| **单机 Docker 节点** | `192.168.50.213` (`ubuntu_tmp`) | SSH / Docker Engine | 生产备用测试节点、单机 Compose 容灾降级运行 |

---

## 2. 告警严重级别与应急响应矩阵 (Severity Matrix)

| 级别 | 定义与影响范围 | 响应时间 SLO | 典型故障示例 | 应急指挥角色 |
|---|---|---|---|---|
| **P0 (Critical)** | 核心服务全面瘫痪、数据损毁风险、用户无法交易或登录 | **< 5 分钟** 响应<br>**< 30 分钟** 恢复 | PostgreSQL 宕机、API 5xx 错误率 > 1%、收盘批处理 DAG 彻底失败 | SRE On-call + Tech Lead |
| **P1 (Major)** | 单一关键子功能降级、高延迟、部分非核心通道故障 | **< 30 分钟** 响应<br>**< 2 小时** 恢复 | API P99 延迟 > 2s、通知投递失败率 > 10%、LLM 熔断降级 | 模块主责研发工程师 |
| **P2 (Minor)** | 单点偶发异常、日常容量预警、指标抓取轻微抖动 | **< 2 小时** 响应<br>**< 1 工作日** 恢复 | 单标的财报数据源缺失、测试通道连通性偶发超时 | 日常值班人员 |

---

## 3. 六大典型生产故障排查与应急 SOP

### 场景 1：PostgreSQL 宕机 / 连接池耗尽 / 慢查询排查与恢复

#### 1. 现象与告警特征
- Prometheus 触发 `StockPilotPostgresDown` 告警；
- 业务日志密集输出 `asyncpg.exceptions.TooManyConnectionsError` 或 `SQLAlchemy TimeoutError: QueuePool limit of size 20 overflow 10 reached`；
- API `/readyz` 探针返回 HTTP 503 Service Unavailable。

#### 2. 诊断步骤
```bash
# 1. 检查数据库容器/Pod 存活性
kubectl get pods -n stockpilot -l app=postgres
kubectl logs -n stockpilot -l app=postgres --tail=100

# 2. 登录主节点检查 PostgreSQL 存活及端口监听
ssh root@192.168.50.36 "pg_isready -h 192.168.50.39 -p 5432 -U postgres"

# 3. 登录 PostgreSQL 查看活跃连接与长时间未释放的慢查询
psql -h 192.168.50.39 -U postgres -d stockpilot -c "
SELECT pid, usename, client_addr, state, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY duration DESC
LIMIT 10;
"
```

#### 3. 应急恢复处置
1. **清理长连接或死锁进程**：
   ```sql
   -- 终止超过 5 分钟的慢查询或空闲事务连接
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE state in ('idle in transaction', 'active')
     AND now() - query_start > interval '5 minutes'
     AND pid <> pg_backend_pid();
   ```
2. **连接池动态扩容或重启 Pod**：
   ```bash
   # 若数据库实例完全假死，执行重启
   kubectl rollout restart statefulset/postgres -n stockpilot
   # 或在单机环境
   docker restart stockpilot-postgres
   ```
3. **若发生数据损坏，立即执行灾备恢复**：
   ```bash
   # 从最新冷备快速恢复目标数据库
   ./scripts/restore_postgres.sh backups/postgres/stockpilot_latest.dump stockpilot
   ```

---

### 场景 2：Redis 实例故障 / 缓存击穿 / Session 失效应急

#### 1. 现象与告警特征
- Prometheus 触发 `StockPilotRedisDown` 告警；
- 用户端偶发 401 Unauthorized（Session 无法自 Redis 校验）或大量请求直接透传到底层 PostgreSQL；
- API 探针 `/readyz` 报 `redis: connection refused`。

#### 2. 诊断步骤
```bash
# 1. 检测 Redis PING 响应
redis-cli -h 192.168.50.38 -p 6379 ping

# 2. 检查 Redis 内存与持久化状态
redis-cli -h 192.168.50.38 -p 6379 info memory
redis-cli -h 192.168.50.38 -p 6379 info persistence
```

#### 3. 应急恢复处置
1. **重启 Redis 实例**：
   ```bash
   kubectl rollout restart deployment/redis -n stockpilot
   ```
2. **应用服务降级与 Session 容灾**：
   - StockPilot 内部具备 Session 优雅降级设计：当 Redis 不可用时，后端自动回落为直查数据库 `user_sessions` 表；
   - 确认后端服务日志包含 `Redis unreachable, falling back to db session lookup`；
3. **恢复缓存快照**：
   ```bash
   # 复制最新备份恢复 dump.rdb
   gzip -d -c backups/redis/redis_latest.rdb.gz > /var/lib/redis/dump.rdb
   kubectl rollout restart deployment/redis -n stockpilot
   ```

---

### 场景 3：收盘后批处理 DAG 流水线中断 / 补算 SOP

#### 1. 现象与告警特征
- Prometheus 触发 `StockPilotSchedulerPipelineFailed` 告警；
- 每日 16:30 后用户无法在「大盘复盘」页面看到当天的 `market_digest` 或 `portfolio_digest` 日报；
- 模拟盘账户净值快照（`equity_snapshots`）停留在上一交易日。

#### 2. 诊断步骤
```bash
# 1. 查看调度 Worker 最近执行日志
kubectl logs -n stockpilot -l app=stockpilot-worker --tail=200 | grep "post_market_pipeline"

# 2. 检索流水线失败步骤 (步骤 0 到 6)
kubectl logs -n stockpilot -l app=stockpilot-worker --tail=500 | grep -E "step_.*_error|daily_reports_generation_error"
```

#### 3. 应急恢复与手动补算 SOP（幂等重放）
StockPilot 收盘流水线具备**完全幂等性**设计，支持指定交易日无副作用重放：
1. **通过 API 运维通道即时触发流水线重跑**：
   ```bash
   # 获取当前系统管理员 JWT Token
   TOKEN=$(curl -s -X POST http://192.168.50.213:8088/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"admin@stockpilot.internal","password":"admin-password"}' | jq -r .access_token)

   # 调用强制补算端点（指定补算交易日并开启 force=true 绕过非开盘时段防护）
   curl -X POST "http://192.168.50.213:8088/api/v1/scheduler/run-post-market?trade_date=$(date +%Y-%m-%d)&force=true" \
     -H "Authorization: Bearer ${TOKEN}"
   ```
2. **通过容器命令行补算**：
   ```bash
   kubectl exec -it -n stockpilot deploy/stockpilot-worker -- python -m app.modules.scheduler.run_manual --trade-date=$(date +%Y-%m-%d) --force
   ```
3. **验证补算结果**：
   - 检查 `/metrics` 输出：`scheduler_pipeline_runs_total{status="completed"}` 自增；
   - 登录前端确认日报与持仓净值曲线已平滑更新。

---

### 场景 4：外部行情提供商网络超时与本地 Mock 降级

#### 1. 现象与告警特征
- 策略计算或收盘批量结算耗时严重超出预期（`StockPilotSchedulerPipelineSlow` 告警）；
- 出现大量外部网络超时异常：`httpx.ReadTimeout: The read operation timed out (api.marketdata.vendor)`。

#### 2. 诊断与应急处置
1. **确认外部连通性与限流状态**：
   ```bash
   curl -I -m 5 https://api.vendor.com/v1/quotes/AAPL
   ```
2. **启用行情源平滑 Mock 降级机制**：
   - 修改 ConfigMap 将数据源适配器切至内置离线兜底行情：
     ```bash
     kubectl patch configmap stockpilot-config -n stockpilot \
       --patch '{"data":{"MARKETDATA_PROVIDER":"mock"}}'
     # 滚动重载 Pod 生效
     kubectl rollout restart deployment/stockpilot-api deployment/stockpilot-worker -n stockpilot
     ```
   - 恢复后行情查询将基于历史快照与离线几何布朗运动模型平滑填充，避免前端交易与策略逻辑中断。

---

### 场景 5：LLM API 余额耗尽 / 熔断器跳闸与降级

#### 1. 现象与告警特征
- 用户点击「AI 深度研报」时提示 `服务暂时降级，请稍后再试`；
- 日志输出 `BudgetCircuitBreaker: monthly budget $500.00 exceeded` 或 `CircuitBreakerOpenException`；
- 外部大模型 API 返回 HTTP 429 Too Many Requests。

#### 2. 诊断步骤
```bash
# 查询当前 AI 模块配额消耗与熔断器健康状态
curl -s http://192.168.50.213:8088/api/v1/ai/status | jq .
```

#### 3. 应急恢复处置
1. **充值并重置熔断器状态**：
   - 完成服务商账单充值后，管理员可通过调用内部管理端点手动解除熔断锁：
     ```bash
     curl -X POST "http://192.168.50.213:8088/api/v1/ai/circuit-breaker/reset" \
       -H "Authorization: Bearer ${TOKEN}"
     ```
2. **降级使用本地精简大模型 / 规则生成器**：
   - 调整环境变量 `AI_PRIMARY_MODEL=rule-based` 或切至低成本备用模型，优先保障大盘收盘简报的生成不受阻断。

---

### 场景 6：版本极速回滚与数据库双向可逆迁移回退 SOP

遵循 `GEMINI.md` 铁律，StockPilot 绝不容许产生不可逆变更。发布异常时支持秒级极速回滚：

#### 模式 A：Argo CD 控制台 / CLI 一键回滚（首选 GitOps 模式）
1. 访问 Argo CD 控制台：`https://192.168.50.36:31443/`；
2. 选择应用 `stockpilot`，点击 **History and Rollback**；
3. 选择上一健康部署版本（例如 Revision 4），点击 **Rollback**；
4. 命令行一键执行方式：
   ```bash
   argocd app rollback stockpilot <TARGET_HISTORY_ID> --insecure --server 192.168.50.36:31443
   ```

#### 模式 B：Kubernetes CLI 命令行即刻回滚
```bash
# 1. 查看发布历史
kubectl rollout history deployment/stockpilot-api -n stockpilot

# 2. 一键秒级回退至上一镜像版本
kubectl rollout undo deployment/stockpilot-api -n stockpilot
kubectl rollout undo deployment/stockpilot-worker -n stockpilot

# 3. 或显式指定历史 Harbor 不可变镜像标签
kubectl set image deployment/stockpilot-api api=192.168.50.36:30088/stockpilot/stockpilot-app:v0.9.0 -n stockpilot
kubectl set image deployment/stockpilot-worker worker=192.168.50.36:30088/stockpilot/stockpilot-app:v0.9.0 -n stockpilot

# 4. 观察回滚滚动更新完成
kubectl rollout status deployment/stockpilot-api -n stockpilot
```

#### 模式 C：数据库双向可逆迁移回退（Alembic Downgrade）
若新发布版本包含了涉及数据表的结构调整，且回退旧版本镜像要求 Schema 还原：
```bash
# 1. 登录容器查看当前版本 Head 与目标回退 revision
kubectl exec -it -n stockpilot deploy/stockpilot-api -- alembic current
kubectl exec -it -n stockpilot deploy/stockpilot-api -- alembic history --verbose

# 2. 执行安全回退（如回退至 M9 的 0006_ai_outcomes 版本）
kubectl exec -it -n stockpilot deploy/stockpilot-api -- alembic downgrade 0006_ai_outcomes

# 3. 验证数据库当前 revision
kubectl exec -it -n stockpilot deploy/stockpilot-api -- alembic current
```

---

## 4. 定时冷备调度与定期容灾恢复演练规范

### 1. 生产定时冷备 Crontab 配置
在宿主管理节点（`192.168.50.213`）配置定时任务，保障数据资产全生命周期备份：
```cron
# 每天凌晨 02:00 执行 PostgreSQL 自动化冷备与清理
0 2 * * * /opt/stockpilot/scripts/backup_postgres.sh >> /var/log/stockpilot_backup_pg.log 2>&1

# 每天凌晨 02:30 执行 Redis 内存快照持久化备份与清理
30 2 * * * /opt/stockpilot/scripts/backup_redis.sh >> /var/log/stockpilot_backup_redis.log 2>&1

# 每周日凌晨 04:00 执行自动化容灾恢复演练
0 4 * * 0 /opt/stockpilot/scripts/verify_dr_restore.sh >> /var/log/stockpilot_dr_drill.log 2>&1
```

### 2. 灾备演练质量验收标准
执行 `./scripts/verify_dr_restore.sh` 演练必须全部满足以下条件：
- **SHA256 签名匹配**：归档文件未遭篡改或字节损坏；
- **临时演练库自动创建与销毁**：绝不污染生产当前库；
- **Alembic Head 一致性**：恢复库的版本号与当前代码主干一致；
- **业务表行数无损还原**：核心 13 张业务数据表均可正常读取并保持完整外键关联。
