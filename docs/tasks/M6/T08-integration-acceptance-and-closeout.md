# M6-T08 全链路端到端验收、文档与 M6 结项报告

| 项 | 内容 |
|---|---|
| 波次 | Wave 6（M6 结项） |
| 依赖 | T01–T07 |
| 阻塞 | 进入 M7 |
| 分支 | `feat/m6-t08-integration-acceptance` |
| Issue | #124 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
完成 Milestone M6 全链路端到端系统验收，编写官方结项报告 `docs/acceptance/M6.md`，更新路线图与变更日志，执行 CI 质量门禁与镜像/Tag 发布准备。

---

## 2. 范围
**包含**
1. `backend/tests/e2e/modules/research/test_research_e2e.py`：
   - 全链路端到端测试：从 HTTP 客户端发起请求 -> 鉴权 -> 事实聚合 -> 量化派生 -> AI 执行 -> Schema/溯源拦截 -> 数据库持久化审计 -> 响应返回；
   - 包含多租户 HARD-01 隔离验证、缓存复用测试、错误处理测试。
2. `docs/acceptance/M6.md`：
   - 官方结项报告、测试矩阵、覆盖率报告、架构契约验证。
3. 文档与路线图更新：
   - `docs/README.md`：M6 置为 `✅ Done`。
   - `CHANGELOG.md`：记录 M6 交付特性。
   - `docs/tasks/M6/README.md`：更新所有任务状态。
4. 遵循 `GEMINI.md §2`：
   - 不可变 Tag：`v0.6.0`、`m6-research-v0.6.0`；
   - GitHub Release。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/tests/e2e/modules/research/__init__.py`
  - `backend/tests/e2e/modules/research/test_research_e2e.py`
  - `docs/acceptance/M6.md`
- **协同修改**：
  - `docs/README.md`
  - `CHANGELOG.md`
  - `docs/tasks/M6/README.md`
  - `docs/tasks/M6/T08-integration-acceptance-and-closeout.md`

---

## 4. 验收标准
- [ ] E2E 测试全部通过，验证真实调用链路完整闭环
- [ ] 架构契约保持 5 kept, 0 broken；`mypy` 0 错误；`ruff` 0 警告；`pip-audit` 0 漏洞
- [ ] `docs/acceptance/M6.md` 齐备
- [ ] 代码合并入 `main`，打标 `v0.6.0` 与发布 Release
