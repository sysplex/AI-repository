# M2-T06 `/market/*` REST API 端点与路由接入

| 项 | 内容 |
|---|---|
| 波次 | Wave 4 |
| 依赖 | T05 已合并 |
| 阻塞 | T07 |
| 分支 | `feat/m2-t06-api-endpoints` |
| 建议规模 | 中（半天） |
| 负责 Agent | _待认领_ |

## 目标
根据 `docs/05-api-spec.md §2.2` 与 `CONTRACTS.md §7`，实现 `/api/v1/market/*` REST API 端点，并接入 FastAPI 应用主路由。

## 范围
**包含**
1. `backend/app/modules/marketdata/api.py`：
   - 依赖注入 `get_data_service`。
   - 实现以下端点：
     - `GET /quotes`（按逗号分隔查询多标的）
     - `GET /bars/{symbol}`（K 线历史）
     - `GET /profile/{symbol}`（公司资料）
     - `GET /fundamentals/{symbol}`（基本面指标）
     - `GET /news/{symbol}`（最新新闻）
     - `GET /universe/{name}`（标的池列表）
     - `POST /facts/{symbol}`（生成事实快照）
   - 所有端点使用强类型 Pydantic Schema 作为返回值，异常按统一错误体系抛出。
2. `backend/app/api/router.py`：
   - 将 `market_router` 挂载到 `api_router` 的 `/market` 路径下，标签为 `marketdata`。
3. 接口集成测试 `backend/tests/integration/modules/marketdata/test_api.py`：
   - 测试所有 `/api/v1/market/*` 路由的 200 返回值与 OpenAPI Schema。
   - 测试数据源不可用时统一返回 424 与标准错误结构。

## 文件所有权
- **创建并拥有**：
  - `backend/app/modules/marketdata/api.py`
  - `backend/tests/integration/modules/marketdata/test_api.py`
- **修改**：
  - `backend/app/api/router.py`（仅限添加 market 路由引入并挂载）

## 验收标准
- [ ] 所有 `/api/v1/market/*` 端点实现并出现在 Swagger `/docs` 中
- [ ] 参数校验与返回格式符合契约与 OpenAPI 规范
- [ ] 错误响应格式完全遵循统一错误体系（code, message, details, request_id）
- [ ] `make check` 全部通过
