# M6-T06 REST API 路由与端点交付（/api/v1/ai/* & /api/v1/research/*）

| 项 | 内容 |
|---|---|
| 波次 | Wave 5 |
| 依赖 | T04, T05 |
| 阻塞 | T07, T08 |
| 分支 | `feat/m6-t06-rest-api-endpoints` |
| Issue | #122 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
在 FastAPI 应用层交付 REST API 端点，支持身份认证、租户隔离、请求体强校验、配额与熔断异常映射，全面符合 `docs/05-api-spec.md §2.5`。

---

## 2. 范围
**包含**
1. `backend/app/modules/research/api.py`：
   - `POST /api/v1/ai/research`：执行股票综合研究
   - `POST /api/v1/ai/buy-decision`：执行买入决策评估
   - `POST /api/v1/ai/technical`：执行技术面通俗分析与计划
   - `POST /api/v1/ai/earnings`：执行财报深度解读
   - 依赖注入与挂载：集成到 `app/api/router.py`，受 `Depends(current_user)` 保护。
2. 异常转换与响应：
   - 400：参数校验失败
   - 404：标的不存在
   - 429：AI 日配额耗尽
   - 503：预算熔断开启
3. `backend/tests/integration/modules/research/test_research_api.py`：
   - 使用 `TestClient` 测试完整 HTTP 请求流；
   - 覆盖匿名拒绝 (401)、无效参数 (422)、配额耗尽 (429) 与正常成功调用 (200/202)。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/research/api.py`
  - `backend/tests/integration/modules/research/__init__.py`
  - `backend/tests/integration/modules/research/test_research_api.py`
- **协同修改**：
  - `backend/app/api/router.py`

---

## 4. 验收标准
- [x] 4 大端点路径与请求/响应结构 100% 遵照 API 规范
- [x] 严格遵守 HARD-01 规范，私有报告与配额租户隔离
- [x] 集成测试覆盖率 $\ge 90\%$，通过全套测试（api.py 100% 覆盖率）
