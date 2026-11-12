# M2-T04 Redis 缓存代理、指数退避重试与降级（stale）

| 项 | 内容 |
|---|---|
| 波次 | Wave 3 |
| 依赖 | T01、T03 已合并 |
| 阻塞 | T05、T07 |
| 分支 | `feat/m2-t04-cache-resilience` |
| 建议规模 | 中（半天–1天） |
| 负责 Agent | _待认领_ |

## 目标
实现 `MarketDataCache` 缓存组件以及对外部数据源调用的指数退避重试与容灾降级机制。当命中缓存时阻断外部调用；当外部异常时，退避重试并降级返回标注 `stale=True` 的历史缓存；无可用数据时抛出明确的 `DataUnavailable`。

## 范围
**包含**
1. `backend/app/modules/marketdata/cache.py`：
   - 依赖 `app.core.redis.get_redis()`。
   - 实现报价、K 线、公司基本面与资料的序列化与 Redis 存取：
     - `Quote`: 交易时段 TTL 60s，非交易时段 TTL 300s（结合 `app.core.calendar` 判断是否开市）。
     - `Fundamentals` / `Profile`: TTL 86400s (24h)。
     - `Bars`: TTL 3600s (1h)。
   - 保存双份键（如当前活跃键与永久/长周期 backup 键），以便外部失败时能读取到过期的历史数据。
2. 重试与降级包装器：
   - 针对适配器网络超时/限流提供重试策略（最多 2 次重试，指数退避）。
   - 彻底失败后，查询降级缓存并设置 `stale=True` 与实际快照时间戳 `as_of`。
   - 无任何可用缓存时抛出 `DataUnavailable`（HTTP 424），严禁返回推测伪造数据。
3. 单元测试与集成测试 `backend/tests/unit/modules/marketdata/test_cache.py`：
   - 使用 `fakeredis` 测试缓存存取。
   - 测试缓存命中时，Mock Provider 调用次数严格断言为 0。
   - 测试外部故障时，成功回退降级缓存且返回结果标记 `stale=True`。
   - 测试无缓存时抛出 `DataUnavailable`。

## 文件所有权
- **创建并拥有**：
  - `backend/app/modules/marketdata/cache.py`
  - `backend/tests/unit/modules/marketdata/test_cache.py`

## 验收标准
- [ ] 缓存命中测试断言：Provider 调用次数为 0
- [ ] 外部异常重试失败后，成功回退并输出 `stale=True`
- [ ] 无缓存且数据源异常时，抛出 `DataUnavailable`
- [ ] `make check` 全部通过
