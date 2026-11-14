# M5-T07 AIService 核心编排门面、智能快照缓存与 `/api/v1/ai/*` REST API

| 项 | 内容 |
|---|---|
| 波次 | Wave 5（应用门面与 API 接入） |
| 依赖 | T01–T06 |
| 阻塞 | T08 |
| 分支 | `feat/m5-t07-aiservice-cache-api` |
| Issue | #107 |
| 建议规模 | 中–大（1–1.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
构建统一的 AI 核心框架门面服务 `AIService`，实现事实快照（`DataSnapshot`）去重存储、基于 SHA-256 的多维智能缓存、全链路重试降级编排，并通过 `/api/v1/ai/*` 暴露 REST API，挂载到全局 API 路由并满足 HARD-01 鉴权。

---

## 2. 范围
**包含**
1. `backend/app/modules/ai/service.py`：
   - `AIService`：
     - ① 规范化 facts 字典并生成 SHA-256 哈希，持久化/复用 `data_snapshots` 表；
     - ② 计算 `cache_key = sha256(use_case + prompt_version + content_hash + sorted_params)`；
     - ③ 查询缓存：若存在且有效，直接返回 `cached=True` 报告，不调用 LLM、不产生成本、不消耗配额；
     - ④ 缓存未命中：Quota 检查 $\to$ 渲染提示词 $\to$ LLM 调用 $\to$ Schema 校验与单次重试 $\to$ 数字溯源校验 $\to$ 配额扣减与用量更新 $\to$ 落库持久化 `ai_reports`；
     - ⑤ 错误降级与状态归档：若失败，保存 `status="failed"` 报告，抛出结构化领域异常。
2. `backend/app/modules/ai/api.py`：
   - 依赖注入 `get_ai_service` 与 `current_user`；
   - `POST /api/v1/ai/analyze`：执行指定用例的 AI 分析；
   - `GET /api/v1/ai/reports/{report_id}`：获取单份报告详情；
   - `GET /api/v1/ai/reports`：列出当前用户名下的报告列表；
   - `GET /api/v1/ai/quota`：查询当前用户的当日配额使用状态；
   - `GET /api/v1/ai/prompts`：列出当前可用提示词模板。
3. `backend/app/api/router.py`：
   - 挂载 `ai_router`，配置 `prefix="/ai"`, `tags=["ai"]`, `dependencies=[Depends(current_user)]`。
4. `backend/tests/integration/modules/ai/test_ai_api.py`：
   - HARD-01 鉴权拦截、租户隔离测试（用户 B 无法访问用户 A 的私有报告）、缓存命中测试、配额耗尽测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/ai/service.py`
  - `backend/app/modules/ai/api.py`
  - `backend/tests/integration/modules/ai/test_ai_api.py`
- **协同修改**：
  - `backend/app/api/router.py`
  - `backend/app/modules/ai/__init__.py`

---

## 4. 验收标准
- [x] 缓存命中场景下调用次数为 0，成本为 0，且不消耗用户配额
- [x] `/api/v1/ai/*` 端点未携带有效 JWT 时一律返回 401 UNAUTHENTICATED（HARD-01）
- [x] 跨租户数据隔离测试通过（返回 404）
- [x] 单元与集成测试覆盖率 $\ge 90\%$，`make check` 全绿
