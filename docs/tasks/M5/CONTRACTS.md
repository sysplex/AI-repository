# M5 接口契约（CONTRACTS）

> AI 核心框架（ai）权威接线图。每个任务严格按本契约的**签名与行为**实现。
> 对应设计：`docs/02-architecture.md§5`、`docs/03-data-model.md§3.4`、`docs/04-modules.md#m5`、`docs/05-api-spec.md§2.5`、`docs/08-test-plan.md§4.3, §5 M5`。

---

## 0. 全局与数据约定

| 项 | 约定 |
|---|---|
| 语言/版本 | Python 3.12；必须通过 `mypy --strict` |
| 金额与费用 | `Decimal`，严禁使用 `float`（如 `cost_usd`, `price_at_report`, 收益率等） |
| 日期与时间 | 时间为带时区的 UTC `datetime`；日期为 `date`（美东交易日） |
| 架构边界 | `ai` 模块遵循六边形架构，核心服务与仓储不直接依赖具体商业 LLM SDK（仅允许置于 `adapters/`），通过 `LLMClient` 协议解耦 |
| 外部 SDK 约束 | 根据 `docs/02 §4` 规则 5 与 `pyproject.toml (TID251)`，`anthropic`, `openai` 等外部 SDK 仅允许出现在 `app/modules/ai/adapters/` |
| 异常规范 | 统一抛出 `AppError`（如 `QuotaExceededError`, `BudgetCircuitOpenError`, `SchemaValidationError`, `FactTracingError`, `AIServiceUnavailableError`） |

---

## 1. 领域模型与 DTO（`app/modules/ai/schemas.py`）

```python
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

ReportStatus = Literal["pending", "processing", "success", "failed"]

class LLMMessage(BaseModel):
    """LLM 输入消息"""
    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str

class LLMResult(BaseModel):
    """LLM 调用返回结果"""
    model_config = ConfigDict(frozen=True)

    parsed_json: dict[str, Any] | None = None
    raw_text: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: Decimal = Field(default=Decimal("0.000000"), ge=0)
    latency_ms: int = Field(ge=0)

class DataSnapshotCreate(BaseModel):
    """数据快照创建"""
    content_hash: str = Field(min_length=64, max_length=64)
    facts: dict[str, Any]
    as_of: datetime

class DataSnapshotResponse(BaseModel):
    """数据快照返回"""
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    content_hash: str
    facts: dict[str, Any]
    as_of: datetime
    created_at: datetime

class AIReportCreate(BaseModel):
    """创建 AI 报告记录"""
    user_id: UUID
    use_case: str
    params: dict[str, Any] = Field(default_factory=dict)
    cache_key: str
    data_snapshot_id: UUID
    prompt_version: str
    model: str
    payload: dict[str, Any] = Field(default_factory=dict)
    cost_usd: Decimal = Field(default=Decimal("0.000000"), ge=0)
    status: ReportStatus = "pending"
    error_message: str | None = None

class AIReportResponse(BaseModel):
    """AI 报告基本响应"""
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    user_id: UUID
    use_case: str
    params: dict[str, Any]
    cache_key: str
    data_snapshot_id: UUID
    prompt_version: str
    model: str
    payload: dict[str, Any]
    cost_usd: Decimal
    status: ReportStatus
    error_message: str | None = None
    created_at: datetime

class AnalysisReport(BaseModel):
    """对外统一分析报告封装（含缓存标记）"""
    model_config = ConfigDict(frozen=True)

    id: UUID
    use_case: str
    payload: dict[str, Any]
    cached: bool
    data_snapshot_id: UUID
    prompt_version: str
    model: str
    cost_usd: Decimal
    created_at: datetime

class QuotaStatus(BaseModel):
    """用户当日配额状态"""
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    usage_date: date
    calls_today: int
    daily_quota: int
    remaining_calls: int
    is_exceeded: bool

class FactTracingViolation(BaseModel):
    """数字溯源违规详情"""
    model_config = ConfigDict(frozen=True)

    field_path: str
    claimed_value: Decimal | str
    reason: str  # "untraced_number", "invalid_source_path", "missing_fact"

class FactTracingResult(BaseModel):
    """数字溯源校验结果"""
    model_config = ConfigDict(frozen=True)

    valid: bool
    violations: list[FactTracingViolation] = Field(default_factory=list)
    checked_numbers_count: int = 0
```

---

## 2. 核心端口协议（`app/modules/ai/ports.py`）

```python
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from app.modules.ai.schemas import LLMResult, QuotaStatus

@runtime_checkable
class LLMClient(Protocol):
    """大语言模型客户端统一协议"""
    name: str

    async def generate(
        self,
        *,
        system: str,
        user: str,
        output_schema: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResult:
        """执行结构化文本或 JSON 生成。"""
        ...

@runtime_checkable
class PromptRegistryProtocol(Protocol):
    """提示词仓库管理协议"""
    def get(self, use_case: str, version: str | None = None) -> Any:
        """获取指定用例与版本的提示词模板。"""
        ...

@runtime_checkable
class QuotaServiceProtocol(Protocol):
    """配额与成本审计协议"""
    async def check(self, user_id: UUID) -> QuotaStatus:
        """检查用户当日 AI 配额。"""
        ...

    async def consume(
        self,
        user_id: UUID,
        tokens_in: int,
        tokens_out: int,
        cost_usd: Decimal,
    ) -> None:
        """扣减配额并落库 ai_usage。"""
        ...
```

---

## 3. 数据库持久化实体（`app/modules/ai/models.py`）

数据表依据 `docs/03-data-model.md §3.4`：
1. `data_snapshots`：
   - `id`: UUID (PK)
   - `content_hash`: String(64) (UK, SHA-256)
   - `facts`: JSONB
   - `as_of`: DateTime(timezone=True)
   - `created_at`: DateTime(timezone=True)
2. `ai_reports`：
   - `id`: UUID (PK)
   - `user_id`: UUID (FK `users.id` CASCADE)
   - `use_case`: String(64)
   - `params`: JSONB
   - `cache_key`: String(128) (Index)
   - `data_snapshot_id`: UUID (FK `data_snapshots.id` CASCADE)
   - `prompt_version`: String(32)
   - `model`: String(64)
   - `payload`: JSONB
   - `cost_usd`: Numeric(18, 6)
   - `status`: String(32)
   - `error_message`: Text (nullable)
   - `created_at`: DateTime(timezone=True)
3. `ai_recommendation_outcomes`：
   - `id`: UUID (PK)
   - `report_id`: UUID (FK `ai_reports.id` CASCADE)
   - `symbol`: String(16)
   - `verdict`: String(32)
   - `price_at_report`: Numeric(18, 4)
   - `ret_5d`: Numeric(10, 4) (nullable)
   - `ret_20d`: Numeric(10, 4) (nullable)
   - `ret_60d`: Numeric(10, 4) (nullable)
   - `ret_vs_spy_20d`: Numeric(10, 4) (nullable)
   - `created_at`: DateTime(timezone=True)

---

## 4. 核心服务接口（`app/modules/ai/service.py`）

```python
class AIService:
    """AI 核心框架服务门面"""

    async def run(
        self,
        use_case: str,
        facts: dict[str, Any],
        params: dict[str, Any] | None = None,
        user_id: UUID | None = None,
        as_of: datetime | None = None,
    ) -> AnalysisReport:
        """执行端到端 AI 分析：
        1. 验证事实快照并计算 content_hash；
        2. 计算 cache_key，若命中缓存则直接返回（无成本、不扣配额）；
        3. 检查用户配额与预算熔断；
        4. 加载提示词模板并渲染；
        5. 调用 LLMClient 生成；
        6. Schema 校验（失败自动重试 1 次）；
        7. 数字溯源校验（杜绝编造幻觉）；
        8. 扣减配额并记账更新 ai_usage；
        9. 保存数据快照与报告记录，返回 AnalysisReport。
        """
        ...
```

---

## 5. 错误码与异常映射（`app/core/errors.py`）

| 异常类 | 错误码 (code) | HTTP 状态码 | 说明 |
|---|---|---|---|
| `QuotaExceededError` | `QUOTA_EXCEEDED` | 429 | 用户当日 AI 配额已耗尽 |
| `BudgetCircuitOpenError` | `BUDGET_CIRCUIT_OPEN` | 503 | 全局或用户预算熔断器触发，暂停外部 LLM 请求 |
| `SchemaValidationError` | `SCHEMA_VALIDATION_FAILED` | 422 | LLM 输出不符合预设 JSON Schema 且重试失败 |
| `FactTracingError` | `FACT_TRACING_FAILED` | 422 | AI 输出包含编造的虚假数字或不存在的事实路径 |
| `AIServiceUnavailableError` | `AI_SERVICE_UNAVAILABLE` | 503 | LLM 外部服务网络异常/超时/不可用 |
| `PromptNotFoundError` | `PROMPT_NOT_FOUND` | 404 | 找不到对应 use_case 或版本的提示词模板 |
