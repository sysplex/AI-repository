# M10-T07: 运维容灾、监控告警体系与故障应急手册

> 责任人：Antigravity ｜ 依赖：M10-T05, M10-T06 已完成 ｜ 分支：`feat/m10-t07-ops-backup-runbook`  
> 契约参考：[`docs/tasks/M10/CONTRACTS.md`](CONTRACTS.md) ｜ [`docs/02-architecture.md`](../../02-architecture.md) ｜ [`docs/05-api-spec.md§2.9`](../../05-api-spec.md) ｜ [`deploy/K8S.md`](../../../deploy/K8S.md) ｜ [`AGENTS.md`](../../../AGENTS.md)

---

## 1. 任务背景与目标

作为 StockPilot v1.0 上线生产前的最后一道运维保障防线，本任务（**M10-T07**）专注于系统的**高可用运维、监控告警闭环与容灾恢复体系**：

1. **Prometheus 业务与运行指标体系（Observability）**：
   - 扩充核心业务监控指标：收盘 DAG 批处理耗时与执行状态、模拟盘订单/成交量、提醒规则评估与触发频次、多通道通知投递失败率、AI 研报产出量；
   - 保证指标记录轻量、线程安全、非阻塞，且在指标关闭时零开销；
   - 配置 Prometheus Alertmanager 告警规则清单（API 5xx、P99 延迟、收盘批处理失败、DB/Redis 宕机、投递失败率告警）。

2. **数据库与缓存容灾备份及快速恢复演练（Disaster Recovery）**：
   - 自动化 PostgreSQL 定时冷备脚本（`pg_dump`，支持压缩、时间戳版本化、保留周期与校验）；
   - PostgreSQL 应急恢复脚本与临时演练数据库自动校验；
   - Redis RDB/AOF 备份与恢复脚本；
   - 验证数据无损恢复与 Alembic 迁移版本一致性。

3. **生产运维故障排查手册（Production Runbook）**：
   - 沉淀完善的运维应急与故障排查手册（`RUNBOOK.md`）；
   - 覆盖 6 大典型生产故障场景的 SOP（标准作业流程）：
     - 场景 1：PostgreSQL 宕机 / 连接池耗尽 / 慢查询排查与恢复；
     - 场景 2：Redis 实例故障 / 缓存穿透 / Session 失效应急；
     - 场景 3：收盘后批处理 DAG 流水线中断 / 补算 SOP；
     - 场景 4：外部行情提供商网络超时与本地 Mock 降级；
     - 场景 5：LLM API 余额耗尽 / 熔断器跳闸与降级；
     - 场景 6：版本极速回滚与数据库双向可逆迁移回退 SOP。

---

## 2. 交付清单

```
AI-repository/
├── backend/app/core/
│   └── metrics.py                # 扩展 Prometheus 业务指标与非阻塞埋点接口
├── backend/tests/unit/core/
│   └── test_metrics_extended.py  # 验证业务指标与直方图收集
├── deploy/monitoring/
│   ├── prometheus-alerts.yaml    # Alertmanager 告警规则定义
│   └── grafana-dashboard.json    # Grafana 核心监控仪表盘模板
├── scripts/
│   ├── backup_postgres.sh        # PostgreSQL 自动备份脚本
│   ├── restore_postgres.sh       # PostgreSQL 恢复与健康检查脚本
│   ├── backup_redis.sh           # Redis 快照持久化脚本
│   └── verify_dr_restore.sh      # 容灾恢复演练与数据一致性自动验证
├── RUNBOOK.md                    # 生产运维排障手册与故障应急 SOP
└── docs/tasks/M10/
    └── T07-ops-backup-runbook.md
```

---

## 3. 验收标准（DoD）

1. **指标全面性**：`/metrics` 能够稳定输出业务与系统运行指标，符合 Prometheus 规范，无标签基数爆炸风险；
2. **容灾可靠性**：备份脚本支持版本归档与过期清理；恢复脚本在目标库上能够无损恢复数据并保持 Schema 完整；
3. **手册完备性**：`RUNBOOK.md` 针对 P0/P1 故障提供明确的检查命令、诊断手段与恢复步骤；
4. **测试覆盖率**：后端整体单元测试保持 ≥ 80%，新测试 100% 通过。
