"""M5 LLM 客户端适配器导出，`CONTRACTS.md §2`。

外部商业 SDK 统一收敛在本包内，严格遵循 TID251。
"""

from __future__ import annotations

from app.modules.ai.adapters.base import (
    BaseLLMClient,
    compute_result_cost,
    estimate_token_count,
    extract_json_from_text,
    inject_schema_instruction,
)
from app.modules.ai.adapters.google import GoogleGeminiClient
from app.modules.ai.adapters.mock import (
    DEFAULT_MOCK_PAYLOAD,
    MockCall,
    MockFaultMode,
    MockLLMClient,
)

__all__ = [
    "DEFAULT_MOCK_PAYLOAD",
    "BaseLLMClient",
    "GoogleGeminiClient",
    "MockCall",
    "MockFaultMode",
    "MockLLMClient",
    "compute_result_cost",
    "estimate_token_count",
    "extract_json_from_text",
    "inject_schema_instruction",
]
