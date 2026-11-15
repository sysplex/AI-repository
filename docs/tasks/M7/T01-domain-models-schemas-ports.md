# M7-T01 领域数据模型、DTO Schemas 与端口协议（compare, long_term, portfolio）

| 项 | 内容 |
|---|---|
| 波次 | Wave 1 |
| 依赖 | M6 结项 |
| 阻塞 | T02, T03, T04 |
| 分支 | `feat/m7-t01-models-schemas-ports` |
| Issue | #133 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
在 `backend/app/modules/research/schemas.py` 与 `backend/app/modules/research/ports.py` 中扩充 M7 三大能力用例（F4 对比、F5 长期持有、F8 投资组合）的数据模型、请求响应 DTO 以及服务门面抽象协议。

---

## 2. 范围
**包含**
1. `backend/app/modules/research/schemas.py`：
   - F4 对比：`CompareRequest`（2–8 标的校验）、`CompareRankingItem`、`DimensionNotes`、`FitByInvestorItem`、`ComparePayload`；
   - F5 长期持有：`LongTermRequest`（5/10/15年校验）、`LongTermPillarItem`、`LongTermPillars`、`ThesisBreakerItem`（可监控破裂条件）、`LongTermPayload`；
   - F8 组合配置：`PortfolioRequest`（金额、标的池、风险等级、投资目标）、`PortfolioAllocationItem`、`PortfolioPayload`（权重、金额、现金比例、再平衡建议）；
   - 所有模型属性类型严格声明，金额与百分比 100% 采用 `Decimal`。
2. `backend/app/modules/research/ports.py`：
   - 扩充 `ResearchServiceProtocol`：`compare_stocks`、`get_long_term_analysis`、`generate_portfolio_allocation` 方法签名。
3. 单元测试 `backend/tests/unit/modules/research/test_m7_models_schemas.py`：
   - 覆盖所有 Schema 的合法序列化/反序列化与边界检验（如 2–8 只股票范围约束、5/10/15 年限定、金额大于 0、破裂条件最少 3 条等）。

---

## 3. 文件所有权
- **修改并拥有**：
  - `backend/app/modules/research/schemas.py`
  - `backend/app/modules/research/ports.py`
- **创建并拥有**：
  - `backend/tests/unit/modules/research/test_m7_models_schemas.py`

---

## 4. 验收标准
- [x] 所有请求与 Payload 结构体定义完备，严格遵循 `docs/tasks/M7/CONTRACTS.md`
- [x] 边界校验有效：股票数量（2–8）、投资期限（5/10/15）、投资金额（>0）等非法输入时被 Pydantic 拦截
- [x] `ports.py` 扩展完整
- [x] 单元测试 100% 通过，`mypy --strict` 0 错误
