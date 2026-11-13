"""M5 AI 核心框架端口协议（T01），`CONTRACTS.md §2`。

定义 LLMClient、PromptRegistryProtocol 与 QuotaServiceProtocol。
所有协议均为结构化契约 (@runtime_checkable)，解耦外部具体商业服务商。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from app.modules.ai.schemas import LLMResult, QuotaStatus

__all__ = [
    "LLMClient",
    "PromptRegistryProtocol",
    "QuotaServiceProtocol",
]


@runtime_checkable
class LLMClient(Protocol):
    """大语言模型客户端统一协议。"""

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
    """提示词仓库管理协议。"""

    def get(self, use_case: str, version: str | None = None) -> Any:
        """获取指定用例与版本的提示词模板。"""
        ...


@runtime_checkable
class QuotaServiceProtocol(Protocol):
    """配额与成本审计协议。"""

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
