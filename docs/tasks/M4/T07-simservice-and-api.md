# M4-T07 SimService 门面服务、Broker 适配器与 /api/v1/sim/* REST API 路由

| 项 | 内容 |
|---|---|
| 波次 | Wave 5 |
| 依赖 | T01–T06 |
| 阻塞 | T08 |
| 分支 | `feat/m4-t07-simservice-and-api` |
| Issue | #91 |
| 建议规模 | 中–大（1 天） |
| 负责 Agent | _待认领_ |

---

## 1. 目标
构建 `SimService` 高层门面服务与 `SimBroker` 适配器（实现统一 `Broker` 端口），并对外暴露 12 个 `/api/v1/sim/*` REST API 端点，接入全局鉴权与依赖注入。

---

## 2. 范围
**包含**
1. `backend/app/modules/simbroker/service.py`：
   - `SimService` 门面服务：
     - `create_account(user_id, req)` / `list_accounts(user_id)` / `get_account(account_id)`
     - `deposit(account_id, amount)`
     - `submit_order(user_id, account_id, req, idempotency_key)`
     - `cancel_order(account_id, order_id)`
     - `get_positions(account_id)` / `get_trades(account_id)`
     - `get_performance(account_id)` / `get_risk(account_id)`
     - `update_trade_journal(trade_id, journal_req)`
     - `process_market_close(account_id, trade_date)`
2. `backend/app/modules/simbroker/adapter.py`：
   - `SimBroker` 适配器类：实现 `Broker` 协议（`submit_order`, `cancel_order`, `get_account`, `get_positions`, `process_bar`）。
3. `backend/app/modules/simbroker/api.py`：
   - FastAPI 路由：
     - `POST /api/v1/sim/accounts`：创建模拟账户
     - `GET /api/v1/sim/accounts`：查询名下账户列表
     - `GET /api/v1/sim/accounts/{id}`：账户实时概览
     - `POST /api/v1/sim/accounts/{id}/deposit`：出入金充值
     - `POST /api/v1/sim/accounts/{id}/orders`：下单（必须带 `Idempotency-Key` 头）
     - `GET /api/v1/sim/accounts/{id}/orders`：订单列表与状态过滤
     - `DELETE /api/v1/sim/accounts/{id}/orders/{oid}`：撤单
     - `GET /api/v1/sim/accounts/{id}/positions`：持仓列表
     - `GET /api/v1/sim/accounts/{id}/trades`：成交明细
     - `GET /api/v1/sim/accounts/{id}/performance`：业绩表现
     - `GET /api/v1/sim/accounts/{id}/risk`：持仓风险诊断
     - `PUT /api/v1/sim/trades/{tid}/journal`：交易日志录入
4. `backend/app/api/router.py`：
   - 挂载 `sim_router`，配置 `dependencies=[Depends(current_user)]`（HARD-01 鉴权规范）。
5. `backend/tests/integration/modules/simbroker/test_simbroker_api.py`：
   - 接口集成测试，覆盖认证、幂等性、下单撤单全流程、持仓与业绩查询。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/simbroker/service.py`
  - `backend/app/modules/simbroker/adapter.py`
  - `backend/app/modules/simbroker/api.py`
  - `backend/tests/integration/modules/simbroker/test_simbroker_api.py`
- **协同修改**：
  - `backend/app/api/router.py`（仅挂载 sim router）

---

## 4. 验收标准
- [ ] 12 个 REST 端点均正常工作，状态码与响应体符合 `docs/05-api-spec.md §2.4`
- [ ] 未登录请求统一被 HARD-01 拦截返回 401 UNAUTHENTICATED
- [ ] `Idempotency-Key` 重复提交返回原订单且无重复撮合
- [ ] `Broker` 端口适配器完整实现 `ports.Broker` 协议
- [ ] `import-linter` 5 项架构契约保持 100% 通过
