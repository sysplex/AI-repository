# M5-T06 配额管理服务、成本追踪统计与预算熔断器

| 项 | 内容 |
|---|---|
| 波次 | Wave 4（配额与财务风控） |
| 依赖 | T01, T02 |
| 阻塞 | T07 |
| 分支 | `feat/m5-t06-quota-budget-breaker` |
| Issue | #106 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
实现用户级 AI 调用日配额检查、用量记录与扣减服务（`QuotaService`），以及全局和用户级预算熔断器（`BudgetCircuitBreaker`），保障 AI 调用的成本可控与服务可用性。

---

## 2. 范围
**包含**
1. `backend/app/modules/ai/quota.py`：
   - `QuotaService`：
     - 实现 `ports.QuotaServiceProtocol`；
     - 检查当日调用次数：基于 `AI_DAILY_QUOTA`（默认 20）以及 `ai_usage` 表；
     - 超额拦截：超出配额直接抛出 `QuotaExceededError`（HTTP 429）；
     - 原子扣减与记账：调用完成后在数据库事务中原子更新 `ai_usage` 的 `calls`, `tokens_in`, `tokens_out`, `cost_usd`。
2. `backend/app/modules/ai/circuit_breaker.py`：
   - `BudgetCircuitBreaker`：
     - 监控日度与月度总成本消耗；
     - 当达到设定阈值时自动触发熔断状态（OPEN），拒绝非缓存调用，抛出 `BudgetCircuitOpenError`（HTTP 503）；
     - 支持管理员手动重置或阈值配置。
3. `backend/tests/unit/modules/ai/test_quota_circuit_breaker.py`：
   - 正常配额检查与扣减、超配额 429 拦截、预算熔断 503 拦截、并发扣减原子性测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/ai/quota.py`
  - `backend/app/modules/ai/circuit_breaker.py`
  - `backend/tests/unit/modules/ai/test_quota_circuit_breaker.py`

---

## 4. 验收标准
- [ ] 超出当日配额立即抛出 `QUOTA_EXCEEDED` 错误
- [ ] 熔断器触发后立即抛出 `BUDGET_CIRCUIT_OPEN`
- [ ] 每次真实调用消耗的 tokens 与成本准确持久化入库 `ai_usage`
- [ ] 单元测试覆盖率 $\ge 90\%$，`make check` 全绿
