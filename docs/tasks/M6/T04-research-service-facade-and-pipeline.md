# M6-T04 核心编排服务 ResearchService 门面与用例管道实现

| 项 | 内容 |
|---|---|
| 波次 | Wave 3 |
| 依赖 | T01, T02, T03 |
| 阻塞 | T05, T06, T07, T08 |
| 分支 | `feat/m6-t04-research-service-facade` |
| Issue | #120 |
| 建议规模 | 中–大（1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
实现 `ResearchService` 领域门面服务。统一编排 4 大 AI 研究用例全流程：参数校验 -> 事实聚合 -> 量化派生 -> AIService 驱动大模型 -> Schema 深度校验 -> 数字溯源拦截 -> 审计与组装返回。

---

## 2. 范围
**包含**
1. `backend/app/modules/research/service.py`：
   - `ResearchService` 实现 `ResearchServiceProtocol`：
     - `get_stock_research(request, user_id) -> AnalysisReport`
     - `get_buy_decision(request, user_id) -> AnalysisReport`
     - `get_technical_analysis(request, user_id) -> AnalysisReport`
     - `get_earnings_analysis(request, user_id) -> AnalysisReport`
   - 与 `AIService.run` 协同集成：透传 `use_case`、`facts`、`params`、`user_id`；
   - 捕获下游异常并映射为领域错误。
2. `backend/tests/unit/modules/research/test_research_service.py`：
   - 结合 MockLLMClient 对 4 个用例执行全流程编排单测；
   - 验证缓存命中穿透、配额扣减协同与报告生成。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/research/service.py`
  - `backend/tests/unit/modules/research/test_research_service.py`

---

## 4. 验收标准
- [x] 4 个用例的管道编排完整顺畅，数据流与异常流完全隔离
- [x] 依赖调用通过抽象接口注入，符合 Layer 2 架构规范
- [x] 单测用例覆盖率 $\ge 90\%$，代码无 lint/type 问题
