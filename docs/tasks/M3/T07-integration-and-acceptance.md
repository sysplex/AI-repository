# M3-T07 全链路集成验收、防未来函数全策略校验与 M3 结项报告

| 项 | 内容 |
|---|---|
| 波次 | Wave 5（M3 收官任务） |
| 依赖 | T01–T06 全部合并 |
| 阻塞 | M3 结项里程碑 |
| 分支 | `feat/m3-t07-integration-acceptance` |
| Issue | #77 |
| 建议规模 | 中（1天） |
| 负责 Agent | _待认领_ |

---

## 1. 目标
完成 M3 策略引擎全链路端到端集成验收，对照 `docs/08-test-plan.md §5 M3` 逐项核验并归档结项。

---

## 2. 范围
**包含**
1. `backend/tests/e2e/modules/strategy/test_strategy_e2e.py`：
   - 全链路端到端集成场景测试。
   - 全部策略防未来函数全面复核。
2. 编写 M3 验收报告 `docs/acceptance/M3.md`：
   - 逐项记录 `docs/08-test-plan.md §5 M3` 的 6 项要求及执行证据。
3. 状态更新：
   - 更新 `docs/README.md` 将 M3 标记为 `✅ Done`。
   - 更新 `CHANGELOG.md`。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/tests/e2e/modules/strategy/test_strategy_e2e.py`
  - `docs/acceptance/M3.md`
- **修改**：
  - `docs/README.md`
  - `CHANGELOG.md`

---

## 4. 验收标准
- [ ] `docs/08-test-plan.md §5 M3` 六项验收标准全部通过
- [ ] 全库测试覆盖率 >= 80%
- [ ] `make check` 全绿
