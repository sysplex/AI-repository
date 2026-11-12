# M2-T05 DataService 核心编排服务与 AI 事实快照（build_facts）

| 项 | 内容 |
|---|---|
| 波次 | Wave 3 |
| 依赖 | T01、T02、T03、T04 已合并 |
| 阻塞 | T06、T07 |
| 分支 | `feat/m2-t05-data-service-facts` |
| 建议规模 | 中–大（1天） |
| 负责 Agent | _待认领_ |

## 目标
实现 M2 核心门面服务 `DataService`，整合适配器、缓存与数据库持久化；实现专供后续 AI 分析模块（M5/M6）消费的 `build_facts(symbol, scope)`，输出结构化事实快照、缺失字段记录与防篡改 SHA-256 哈希。

## 范围
**包含**
1. `backend/app/modules/marketdata/service.py`：
   - 实现 `DataService`，构造函数注入 `DataProvider`、`MarketDataCache` 与可选的 `async_sessionmaker`。
   - 统一对外暴露方法：
     - `get_bars`、`get_quote`、`get_quotes`、`get_fundamentals`、`get_profile`、`get_news`、`get_universe`。
     - 获取到的数据视配置写入共享数据表（`bars_daily`、`fundamentals_snapshots`、`symbols` 等）。
   - 实现核心方法 `build_facts(symbol, scope)`：
     - 聚合行情、基本面、三表、财报事件等数据；
     - 缺失字段显式标记为 `null`，并列入 `missing_fields`；
     - 对标准 JSON 键排序序列化计算 SHA-256 哈希得到 `content_hash`；
     - 将事实快照落库存储至 `data_snapshots` 表，返回 `FactsSnapshot`。
2. 单元与集成测试 `backend/tests/unit/modules/marketdata/test_service.py`：
   - 验证 `build_facts` 输出格式与不可变哈希计算。
   - 验证缺失数据场景下 `missing_fields` 的完整记录与 `null` 表现。
   - 验证对缓存层与数据库层的协同调用。

## 文件所有权
- **创建并拥有**：
  - `backend/app/modules/marketdata/service.py`
  - `backend/tests/unit/modules/marketdata/test_service.py`

## 验收标准
- [ ] `build_facts` 成功生成确定性 `content_hash`，多次相同输入哈希一致
- [ ] 缺失字段在 facts 字典中显式体现为 `None` / `null`，并列入 `missing_fields`
- [ ] 事实快照能成功持久化到 `data_snapshots`
- [ ] `make check` 全部通过
