# M7-T06 REST API 路由与端点交付（/compare, /long-term, /portfolio）

| 项 | 内容 |
|---|---|
| 波次 | Wave 5 |
| 依赖 | T04, T05 |
| 阻塞 | T07, T08 |
| 分支 | `feat/m7-t06-rest-api-endpoints` |
| Issue | #138 |
| 建议规模 | 中（0.5 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
在 `backend/app/modules/research/api.py` 中挂载 M7 的 3 个 REST API 核心端点，并在 `backend/app/api/router.py` 中保持 `/api/v1/ai/*` 与 `/api/v1/research/*` 双路径平同兼容，受 `HARD-01` 强鉴权保护。

---

## 2. 范围
**包含**
1. `backend/app/modules/research/api.py`：
   - `POST /api/v1/ai/compare` (F4)
   - `POST /api/v1/ai/long-term` (F5)
   - `POST /api/v1/ai/portfolio` (F8)
2. `backend/app/api/router.py`：
   - 保持 `/api/v1/research/compare`、`/api/v1/research/long-term`、`/api/v1/research/portfolio` 别名路由兼容映射。
3. 集成测试 `backend/tests/integration/modules/research/test_m7_api.py`：
   - HARD-01 鉴权（未授权返回 401）；
   - 参数校验（股票数不足 2 或超过 8、非法期限、金额非正数返回 422/400）；
   - 正常鉴权请求返回完整 `ResearchEnvelope`；
   - 别名路由双向验证。

---

## 3. 文件所有权
- **修改并拥有**：
  - `backend/app/modules/research/api.py`
  - `backend/app/api/router.py`
- **创建并拥有**：
  - `backend/tests/integration/modules/research/test_m7_api.py`

---

## 4. 验收标准
- [ ] 3 个新端点均挂载生效，OpenAPI 文档完备
- [ ] HARD-01 未鉴权一律 401 UNAUTHENTICATED
- [ ] 双路径路由访问结果完全等价
- [ ] 集成测试通过率 100%
