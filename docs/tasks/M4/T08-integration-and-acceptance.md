# M4-T08 全链路端到端集成验收、不变量全矩阵校验与 M4 结项报告

| 项 | 内容 |
|---|---|
| 波次 | Wave 6（M4 终局集成验收） |
| 依赖 | T01–T07 全部合入 main |
| 阻塞 | 无（完成即结项并打 Tag v0.4.0） |
| 分支 | `feat/m4-t08-integration-acceptance` |
| Issue | #92 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
对照 `docs/08-test-plan.md §6 M4` 验收清单进行端到端全链路集成验收，执行覆盖率压力测试、不变量闭环验证、撰写结项报告 `docs/acceptance/M4.md`，更新全局路线图与 CHANGELOG。

---

## 2. 范围
**包含**
1. `backend/tests/e2e/modules/simbroker/test_simbroker_e2e.py`：
   - 逐条覆盖 `docs/08-test-plan.md §6 M4` 6 大核心验收项：
     - ① 不变量属性测试全量通过（现金守恒、净值恒等、持仓非负）；
     - ② 市价/限价/止损单撮合与手算样例逐笔一致；
     - ③ 资金不足/超卖被拒，错误码正确（`INSUFFICIENT_FUNDS`, `INSUFFICIENT_POSITION`）；
     - ④ 并发重复提交只成交一次（`idempotency_key` 幂等防护）；
     - ⑤ 净值快照、回撤、胜率、盈亏比、对比 SPY 计算正确；
     - ⑥ 行情缺失时订单保持 `accepted` 并告警，绝不使用陈旧价格成交；
     - ⑦ 拆股合股后持仓市值恒定。
2. `docs/acceptance/M4.md`：
   - 官方结项验收文档（测试用例清单、覆盖率报告、架构契约审计结论）。
3. 协同更新：
   - `docs/README.md`（更新路线图 M4 状态为 `✅ Done`）。
   - `CHANGELOG.md`（记录 M4-T01 ~ T08 全部功能发布与变更）。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/tests/e2e/modules/simbroker/test_simbroker_e2e.py`
  - `docs/acceptance/M4.md`
- **协同修改**：
  - `docs/README.md`
  - `CHANGELOG.md`

---

## 4. 验收标准
- [ ] 7 项 E2E 验收用例 100% 通过
- [ ] 全局测试覆盖率 ≥ 80.0%
- [ ] `make check`（ruff check, ruff format, mypy --strict, import-linter, pip-audit）全部绿灯
- [ ] 输出完整的 `docs/acceptance/M4.md` 报告
