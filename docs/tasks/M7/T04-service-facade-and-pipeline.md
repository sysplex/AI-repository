# M7-T04 ResearchService 门面扩充与 M7 用例编排管道实现

| 项 | 内容 |
|---|---|
| 波次 | Wave 3 |
| 依赖 | T01, T02, T03 |
| 阻塞 | T05, T06 |
| 分支 | `feat/m7-t04-service-facade-pipeline` |
| Issue | #136 |
| 建议规模 | 中–大（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
在 `ResearchService` 门面中扩展实现 M7 的三大用例编排管道：
- `compare_stocks(request, user_id)` (F4)
- `get_long_term_analysis(request, user_id)` (F5)
- `generate_portfolio_allocation(request, user_id)` (F8)

---

## 2. 范围
**包含**
1. `backend/app/modules/research/service.py`：
   - 扩充核心编排管道，将多标的事实聚合、确定性量化打分/组合优化、AI 异步调用与 Schema 校验打通；
   - 异常处理：标的不存在（`SymbolNotFoundError`）、数据严重不足（`InsufficientDataError`）、输入非法（`InvalidParameterError`）；
   - 统一通过 `wrap_research_envelope` 生成免责声明与证据溯源外壳。
2. 单元测试 `backend/tests/unit/modules/research/test_m7_service_pipeline.py`：
   - 针对三大管道进行 Mock AIService 测试；
   - 验证输入验证、事实传递、模型返回封装与异常降级分支。

---

## 3. 文件所有权
- **修改并拥有**：
  - `backend/app/modules/research/service.py`
- **创建并拥有**：
  - `backend/tests/unit/modules/research/test_m7_service_pipeline.py`

---

## 4. 验收标准
- [x] 三大方法完全符合 `ResearchServiceProtocol` 协议签名
- [x] 事实与计算结果完整注入 `facts["computed"]`
- [x] 完整异常处理分支，无未捕获异常泄露
- [x] 单元测试覆盖率 $\ge 90\%$
