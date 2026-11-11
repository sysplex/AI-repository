# M0-T05 进程内事件总线与领域事件

| 项 | 内容 |
|---|---|
| 波次 | Wave 1 |
| 依赖 | T01 已合并 |
| 阻塞 | 无（M4/M5/M10 将使用） |
| 分支 | `feat/m0-t05-event-bus` |
| 建议规模 | 小 |
| 负责 Agent | _未分配_ |

## 目标
实现类型安全、错误隔离的进程内异步事件总线，及首批领域事件，按 `CONTRACTS.md §6`。用于后续通知、复盘、审计解耦（见 `docs/02-architecture.md §8`）。

## 范围
**包含**
1. `core/events.py`：`Event` 基类、`EventBus`（subscribe/unsubscribe/publish）、`get_event_bus()`。
2. 多态订阅：订阅父类事件可收到子类事件。
3. 处理器按订阅顺序串行 `await`；单个处理器异常被捕获并 `ERROR` 日志（含事件类型、处理器名、event_id），**不影响其他处理器，也不抛给发布者**。
4. 处理器超时保护：单个处理器超过 5 秒（可通过 `EventBus(handler_timeout=...)` 配置）记录 `WARNING` 并取消，继续后续处理器。
5. `domain/events.py`：`OrderFilled`、`ReportCreated`、`SignalTriggered`（字段见契约）；`Decimal` 序列化友好（`model_dump(mode="json")` 输出字符串）。
6. 重复订阅同一处理器忽略（幂等）；`unsubscribe` 不存在的订阅不报错。

**不包含**：跨进程/Redis Streams（后续 ADR）；持久化（outbox）。

## 文件所有权
- **拥有**：`backend/app/core/events.py`、`backend/app/domain/events.py`
- **新增测试**：`backend/tests/unit/core/test_events.py`、`tests/unit/domain/test_domain_events.py`
- **不得修改**：其他文件

## 验收标准
- [ ] 订阅/发布基本流程；处理器按订阅顺序执行（测试断言顺序）
- [ ] 订阅父类 `Event` 可收到所有子类事件；订阅子类不会收到兄弟类事件（测试）
- [ ] 一个处理器抛异常 → 其余处理器仍执行、`publish` 不抛、日志有 ERROR（测试）
- [ ] 处理器超时被取消且不阻塞后续（测试，使用短超时）
- [ ] 重复订阅幂等；取消订阅后不再收到；取消不存在的订阅不报错（测试）
- [ ] 事件不可变（修改字段抛错）；`occurred_at` 带 UTC 时区（测试）
- [ ] 领域事件 JSON 序列化：`Decimal` 为字符串，`UUID`/`date` 正确（测试）
- [ ] 并发发布（`asyncio.gather` 多个 publish）互不干扰（测试）
- [ ] `make check` 全绿；覆盖率 ≥ 95%
