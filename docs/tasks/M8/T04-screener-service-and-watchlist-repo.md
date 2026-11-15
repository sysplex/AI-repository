# M8-T04 ScreenerService 核心门面与 Watchlist 仓储服务实现

| 项 | 内容 |
|---|---|
| 波次 | Wave 3 |
| 依赖 | T01, T02, T03 |
| 阻塞 | T06, T07 |
| 分支 | `feat/m8-t04-service-watchlist-repo` |
| Issue | #152 |
| 建议规模 | 中–大（1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
实现 `ScreenerService` 统一服务门面与 `WatchlistRepository`、`ScreenerRepository` 仓储层，管理筛选运行历史、自选清单与标的增删改查，严格保障多租户数据隔离，提供一键导出选股结果到研究/对比的业务逻辑。

---

## 2. 范围
**包含**
1. `backend/app/modules/screener/repo.py`：
   - 实现 `ScreenerRepository` 与 `WatchlistRepository`；
   - 包含多租户保护（所有 SQL 查询与更新操作强制以 `user_id` 为约束条件）；
   - 自选清单与标的 CRUD：创建清单、更新信息、删除清单（级联删除子项）、添加标的、删除标的；
   - 重复添加相同标的防御（抛出 `DuplicateWatchlistItemError`）。
2. `backend/app/modules/screener/service.py`：
   - 实现 `ScreenerService`，符合 `ScreenerServiceProtocol`；
   - 编排筛选任务创建、异步执行、状态落库（`pending` -> `running` -> `succeeded`/`failed`）；
   - 提供 `get_screener_run` 读取任务结果；
   - 转发股票池与主题查询；
   - 自选清单业务管理。
3. 单元测试 `backend/tests/unit/modules/screener/test_screener_service.py` 与 `test_watchlist_repo.py`：
   - 验证多租户隔离（租户 A 无法操作租户 B 的清单或筛选记录）；
   - 验证筛选任务全生命周期流转。

---

## 3. 验收标准
- [ ] 多租户隔离 100% 落实，无越权风险
- [ ] 自选清单支持完整的增删改查与去重保护
- [ ] 门面管道流转正确记录任务状态与失败明细
- [ ] 单元测试覆盖率 $\ge 90\%$，`mypy --strict` 0 错误
