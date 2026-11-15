# M8-T06 REST API 路由与端点交付（/screener, /themes, /watchlists, /universes）

| 项 | 内容 |
|---|---|
| 波次 | Wave 4 |
| 依赖 | T04, T05 |
| 阻塞 | T07, T08 |
| 分支 | `feat/m8-t06-rest-api-endpoints` |
| Issue | #154 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
在 `backend/app/modules/screener/api.py` 中交付 REST API 路由，并在 `backend/app/api/router.py` 挂载，暴露 `/api/v1/universes`、`/api/v1/screener/*`、`/api/v1/themes/*`、`/api/v1/watchlists/*` 端点，全面执行 HARD-01 鉴权守卫。

---

## 2. 范围
**包含**
1. 路由实现 `backend/app/modules/screener/api.py`：
   - `GET /universes`：返回可选股票池列表；
   - `POST /screener/runs`：创建异步筛选任务；
   - `GET /screener/runs/{id}`：获取筛选任务进度与结果；
   - `GET /themes`：返回热门主题列表；
   - `GET /themes/{id}`：获取指定主题详情与成分标的；
   - `POST /themes/{id}/cards`：触发并获取 AI 生成的主题股票卡片；
   - `GET /watchlists` / `POST /watchlists`：自选列表查询与新建；
   - `GET /watchlists/{id}` / `PUT /watchlists/{id}` / `DELETE /watchlists/{id}`：自选详情、改名更新与删除；
   - `POST /watchlists/{id}/items` / `DELETE /watchlists/{id}/items/{item_id}`：自选标的新增与移除；
   - `POST /watchlists/{id}/export`：一键导出标的到研究/对比。
2. 鉴权与异常处理：
   - 所有接口均强制依赖 `get_current_user`，未登录一律拦截并返回 401 UNAUTHENTICATED；
   - 映射 `UniverseNotFoundError`, `WatchlistNotFoundError` 等到 404 NOT_FOUND，`DuplicateWatchlistItemError` 到 409 STATE_CONFLICT。
3. 单元/集成测试 `backend/tests/unit/modules/screener/test_screener_api.py`：
   - 覆盖全部端点正常与异常响应；
   - 验证未登录 401 拦截。

---

## 3. 验收标准
- [ ] 所有路由端点严格对齐 `CONTRACTS.md §5`
- [ ] 严格执行 HARD-01 鉴权
- [ ] 单元/接口测试 100% 通过，`mypy --strict` 0 错误
