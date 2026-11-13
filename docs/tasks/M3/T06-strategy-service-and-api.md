# M3-T06 StrategyService 门面服务与 /strategy/* REST API 路由接入

| 项 | 内容 |
|---|---|
| 波次 | Wave 4 |
| 依赖 | T01–T05 已合并 |
| 阻塞 | T07 |
| 分支 | `feat/m3-t06-service-and-api` |
| Issue | #76 |
| 建议规模 | 中（1天） |
| 负责 Agent | _待认领_ |

---

## 1. 目标
实现 StrategyService 统一编排门面，依赖注入 DataService，并暴露 REST API 路由 `/api/v1/strategy/*`。

---

## 2. 范围
**包含**
1. `backend/app/modules/strategy/service.py`：
   - `StrategyService` 核心用例（`list_strategies`, `evaluate`, `scan`, `compute_technical_snapshot`, `backtest`）。
2. `backend/app/modules/strategy/api.py`：
   - FastAPI 路由端点（`/api/v1/strategy/*`）。
3. `backend/app/api/router.py`：
   - 挂载 strategy router。
4. `backend/tests/integration/modules/strategy/test_strategy_api.py`：
   - API 鉴权、参数校验与端点集成测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/strategy/service.py`
  - `backend/app/modules/strategy/api.py`
  - `backend/tests/integration/modules/strategy/test_strategy_api.py`
- **修改**：
  - `backend/app/api/router.py`（仅挂载 strategy router）

---

## 4. 验收标准
- [ ] 接口符合 `docs/05-api-spec.md` 规范，包含输入参数校验
- [ ] 符合 HARD-01 安全规范（必须登录用户身份访问）
- [ ] import-linter 架构分层契约 100% 保持
- [ ] `make check` 全绿
