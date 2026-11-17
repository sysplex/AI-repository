# M10-T08 全链路端到端集成验收、自动化测试体系与 v1.0 结项发布

| 项 | 内容 |
|---|---|
| 波次 | Wave 5 |
| 依赖 | T01–T07 全部完成 |
| 阻塞 | Milestone M10 结项与 StockPilot v1.0 正式发布 |
| 分支 | `feat/m10-t08-m10-acceptance-and-closeout` |
| Issue | #188 |
| 建议规模 | 中–大（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 任务背景与目标

作为 StockPilot 宏伟规划中最后一个研发里程碑（**Milestone M10**）的收官决胜任务，**M10-T08** 专注于整个平台的**全链路端到端集成验收（E2E）、自动化测试体系校验与 StockPilot v1.0 正式结项发布**：

1. **前端全链路 E2E 验收（E2E-04）**：
   - 编写 `frontend/src/__tests__/e2e/e2e_04_m10_scheduler_alerts_review.test.tsx`；
   - 覆盖：通知渠道配置（邮件/Webhook/站内信）与连通性自测 $\to$ 价格与论文破裂提醒规则建立 $\to$ 模拟盘与持仓建立 $\to$ 收盘后批处理 DAG 流水线触发与日志观察 $\to$ 全市场与用户持仓日报查阅 $\to$ AI 投资建议持续复盘（Alpha 统计、各评级胜率分布）全流程。

2. **后端全流程集成验收（Backend E2E）**：
   - 编写 `backend/tests/e2e/modules/test_m10_e2e.py`；
   - 覆盖：用户身份 $\to$ 渠道与规则落库 $\to$ 模拟交易账户资产结算 $\to$ 收盘流水线 0~6 步骤全流程执行 $\to$ 提醒触发与多渠道派发 $\to$ AI 建议收益与 SPY Alpha 回填 $\to$ 日报生成入库 $\to$ Prometheus 业务度量自增 $\to$ 重复运行幂等性保障。

3. **系统结项验收报告（Closeout Report）**：
   - 产出 `docs/acceptance/M10.md`，对齐 PRD F12/F13 与 `docs/08-test-plan.md`；
   - 更新 `docs/08-test-plan.md`、`docs/README.md` 与 `CHANGELOG.md`；
   - 准备不可变 Git 标签 `v1.0.0`。

---

## 2. 交付清单

```
AI-repository/
├── frontend/src/__tests__/e2e/
│   └── e2e_04_m10_scheduler_alerts_review.test.tsx # 前端调度、提醒与复盘 E2E 测试
├── backend/tests/e2e/modules/
│   └── test_m10_e2e.py                             # 后端全生命周期集成测试
├── docs/acceptance/
│   └── M10.md                                      # M10 完整结项验收报告
├── docs/08-test-plan.md                            # 勾选 M10 验收清单
├── docs/README.md                                  # 更新 M10 状态与架构概览
├── CHANGELOG.md                                    # 记录 v1.0.0 发布日志
└── docs/tasks/M10/
    ├── README.md
    └── T08-m10-acceptance-and-closeout.md
```

---

## 3. 验收标准（DoD）

1. **E2E 覆盖率**：前端 `e2e_04` 与后端 `test_m10_e2e` 100% 绿灯通过，真实模拟用户交互与跨模块数据流转；
2. **测试与质量红线**：
   - 后端单元测试与集成测试全量通过，代码测试覆盖率保持 ≥ 80%（目标 ≥ 89%）；
   - 前端 Vitest 测试 100% 通过，TypeScript 编译 0 错误，生产打包正常；
   - `import-linter` 5 项契约检查 100% 遵守；
3. **运维与回滚保证**：符合 `GEMINI.md` 不可变版本规范与双向可逆迁移要求。
