# M2-T07 集成验收、拆股/复权验证与 M2 结项文档

| 项 | 内容 |
|---|---|
| 波次 | Wave 5（M2 收官任务） |
| 依赖 | T01–T06 全部合并 |
| 阻塞 | M2 结项里程碑 |
| 分支 | `feat/m2-t07-integration-acceptance` |
| 建议规模 | 中（半天–1天） |
| 负责 Agent | _待认领_ |

## 目标
执行 M2 数据模块的全链路端到端集成验收，对照 `docs/08-test-plan.md §5 M2 数据服务` 进行逐项测试，验证真实场景（如 NVDA 2024-06 拆股、缓存断言、降级链路），归档验收报告 `docs/acceptance/M2.md` 并更新模块状态。

## 范围
**包含**
1. 端到端集成测试 `backend/tests/e2e/modules/marketdata/test_marketdata_e2e.py`：
   - 验证：冷启动请求 -> 数据入库 + 写入 Redis 缓存 -> 二次请求命中缓存（外部适配器调用为 0）。
   - 验证：拆股复权案例（NVDA 2024-06 拆股 10:1），确认复权价格与动作记录吻合。
   - 验证：外部数据源故障触发重试 -> 降级历史缓存返回 `stale=True`。
   - 验证：`build_facts` 产生快照落库，再次对同一 facts 计算哈希严格相同。
2. 编写 M2 验收记录文档 `docs/acceptance/M2.md`：
   - 逐条列出 `docs/08-test-plan.md` 中 M2 的 5 项验收要求与实际测试结果。
   - 附带各项证据（测试用例名称、命令输出日志）。
3. 状态更新：
   - 将 `docs/README.md` 中 M2 的状态更新为 `✅ Done`。
   - 更新 `CHANGELOG.md` 记录 M2 核心成果。

## 文件所有权
- **创建并拥有**：
  - `backend/tests/e2e/modules/marketdata/test_marketdata_e2e.py`
  - `docs/acceptance/M2.md`
- **更新**：
  - `docs/README.md`（仅更新 M2 状态行）
  - `CHANGELOG.md`

## 验收标准
- [ ] `docs/08-test-plan.md §5` 中 M2 验收清单全部勾选并通过
- [ ] 端到端测试与集成测试全绿
- [ ] `make check`（覆盖率 ≥ 80%）全绿
- [ ] `docs/acceptance/M2.md` 验收报告记录完整
