# M8-T08 全链路端到端验收（E2E）、文档与 M8 结项报告

| 项 | 内容 |
|---|---|
| 波次 | Wave 6 |
| 依赖 | T01–T07 全部完成 |
| 阻塞 | M8 结项发布 |
| 分支 | `feat/m8-t08-e2e-acceptance-closeout` |
| Issue | #156 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
编写真实 HTTP 全链路端到端（E2E）验收测试，覆盖多租户自选隔离、筛选任务全流程与导出投研，更新产品与架构文档，产出 M8 正式结项验收报告 `docs/acceptance/M8.md`，打上 Git 语义化标签 `v0.8.0` 并发布。

---

## 2. 范围
**包含**
1. E2E 测试 `backend/tests/e2e/modules/screener/test_screener_e2e.py`：
   - 用户创建自选清单 -> 添加标的 -> 修改备注与目标价 -> 一键导出；
   - 筛选器创建任务 -> 轮询查询结果 -> 筛选标的加入自选；
   - 跨用户多租户越权攻击测试（404/403 严格阻断）；
   - 未登录测试（401 严格阻断）。
2. 文档更新：
   - 结项报告 `docs/acceptance/M8.md`；
   - 更新 `docs/README.md`，将 M8 状态标记为 `✅ Done`；
   - 更新 `CHANGELOG.md` 与 `docs/tasks/M8/README.md`。
3. 版本发布：
   - 发布 Git 标签 `v0.8.0` 与 GitHub Release `v0.8.0`。

---

## 3. 验收标准
- [ ] E2E 真实端到端测试 100% 通过
- [ ] `docs/acceptance/M8.md` 验收报告完备详实
- [ ] 全量回归测试通过，覆盖率保持高位
- [ ] 遵循 `GEMINI.md` 发布 `v0.8.0` 版本标签与 Release
