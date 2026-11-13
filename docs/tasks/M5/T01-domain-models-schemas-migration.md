# M5-T01 领域数据模型、SQLAlchemy 实体、Alembic 迁移（0005_ai）与 DTO Schema

| 项 | 内容 |
|---|---|
| 波次 | Wave 1（M5 地基） |
| 依赖 | M4 已结项 |
| 阻塞 | T02–T08 |
| 分支 | `feat/m5-t01-models-schemas-migration` |
| Issue | #101 |
| 建议规模 | 中（0.5–1 天） |
| 负责 Agent | Antigravity |

---

## 1. 目标
实现 `ai` 模块核心数据底座：SQLAlchemy 2.0 ORM 实体（`data_snapshots`, `ai_reports`, `ai_recommendation_outcomes`）、Alembic 迁移脚本 `0005_ai.py`、Pydantic v2 DTO Schemas 与 `ports.py` 核心端口协议。

---

## 2. 范围
**包含**
1. `backend/app/modules/ai/models.py`：
   - `DataSnapshot`：`id`, `content_hash` (UK), `facts` (JSONB), `as_of`, `created_at`
   - `AIReport`：`id`, `user_id` (FK `users.id` CASCADE), `use_case`, `params` (JSONB), `cache_key` (Index), `data_snapshot_id` (FK `data_snapshots.id` CASCADE), `prompt_version`, `model`, `payload` (JSONB), `cost_usd`, `status`, `error_message`, `created_at`
   - `AIRecommendationOutcome`：`id`, `report_id` (FK `ai_reports.id` CASCADE), `symbol`, `verdict`, `price_at_report`, `ret_5d`, `ret_20d`, `ret_60d`, `ret_vs_spy_20d`, `created_at`
2. `backend/alembic/versions/0005_ai.py`：
   - 依赖 `0004_simbroker`；
   - 包含完整的 `upgrade()` 与 `downgrade()`，创建上述 3 张表及唯一索引、外键级联。
3. `backend/app/modules/ai/schemas.py`：
   - `LLMMessage`, `LLMResult`, `DataSnapshotCreate`, `DataSnapshotResponse`, `AIReportCreate`, `AIReportResponse`, `AnalysisReport`, `QuotaStatus`, `FactTracingResult`, `FactTracingViolation`
4. `backend/app/modules/ai/ports.py`：
   - `LLMClient`, `PromptRegistryProtocol`, `QuotaServiceProtocol`
5. `backend/tests/unit/modules/ai/test_models_schemas.py`：
   - 针对 ORM 模型、Schema 验证、序列化往返的单元测试。

---

## 3. 文件所有权
- **创建并拥有**：
  - `backend/app/modules/ai/models.py`
  - `backend/app/modules/ai/schemas.py`
  - `backend/app/modules/ai/ports.py`
  - `backend/alembic/versions/0005_ai.py`
  - `backend/tests/unit/modules/ai/test_models_schemas.py`
- **协同修改**：
  - `backend/app/modules/ai/__init__.py`

---

## 4. 验收标准
- [ ] ORM 实体字段类型与 `docs/03-data-model.md §3.4` 及 `CONTRACTS.md` 100% 对齐
- [ ] Alembic 迁移 `upgrade()` 与 `downgrade()` 双向可逆测试通过
- [ ] Pydantic Schemas 严格校验与不可变性生效
- [ ] 单元测试覆盖率 $\ge 90\%$，`make check` 全绿
