"""M5 LLM 客户端基础抽象与通用工具（T02），`CONTRACTS.md §0, §2`。

提供 BaseLLMClient 抽象基类、结构化 JSON 输出提取、Schema 提示词注入及 Token 估算。
外部商业 SDK（如 Anthropic/OpenAI）实现均置于本 adapters 目录下，严格遵循 TID251。
"""

from __future__ import annotations

import abc
import json
import re
from decimal import Decimal
from typing import Any

from app.modules.ai.pricing import DEFAULT_FALLBACK_PRICING, calculate_cost
from app.modules.ai.schemas import LLMResult

__all__ = [
    "BaseLLMClient",
    "compute_result_cost",
    "estimate_token_count",
    "extract_json_from_text",
    "inject_schema_instruction",
]

_JSON_CODE_BLOCK_PATTERN = re.compile(
    r"```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```",
    re.MULTILINE,
)


def extract_json_from_text(raw_text: str) -> dict[str, Any] | None:
    """从 LLM 原始文本中提取并解析 JSON 对象。

    支持：
    1. 纯净 JSON 字符串；
    2. Markdown 代码块包裹的 JSON（```json ... ```）；
    3. 夹杂在解释性文本中的 JSON 块（最外层大括号匹配）。
    """
    stripped = raw_text.strip()
    if not stripped:
        return None

    # 1. 尝试直接完整解析
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. 尝试从 markdown 代码块提取
    match = _JSON_CODE_BLOCK_PATTERN.search(stripped)
    if match:
        snippet = match.group(1).strip()
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. 寻找最外层的 '{' 与 '}'
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = stripped[first_brace : last_brace + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def inject_schema_instruction(
    system_prompt: str,
    output_schema: dict[str, Any] | None,
) -> str:
    """若指定 output_schema，在系统提示词末尾注入强制 JSON 结构化格式约定。"""
    if not output_schema:
        return system_prompt

    schema_str = json.dumps(output_schema, ensure_ascii=False, indent=2)
    instruction = (
        "\n\n[OUTPUT FORMAT INSTRUCTION]\n"
        "You must return ONLY a single strictly valid JSON object conforming to "
        "the following JSON Schema.\n"
        "Do not wrap your output in explanations, markdown text, or other wrappers "
        "outside the JSON.\n"
        f"JSON Schema:\n{schema_str}"
    )
    return system_prompt + instruction


def estimate_token_count(text: str) -> int:
    """估算文本的 Token 消耗（中英文混合启发式：~4 字符/Token 英文，~1.5 字符/Token 中文）。"""
    if not text:
        return 0

    cjk_count = 0
    non_cjk_count = 0
    for ch in text:
        # CJK Unified Ideographs 范围
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
            cjk_count += 1
        else:
            non_cjk_count += 1

    estimated = int((cjk_count * 0.7) + (non_cjk_count / 4.0))
    return max(1, estimated)


def compute_result_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cached_input_tokens: int = 0,
) -> Decimal:
    """安全计算 Token 成本；若模型未在注册表中，回退使用保守兜底定价。"""
    return calculate_cost(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        default_pricing=DEFAULT_FALLBACK_PRICING,
    )


class BaseLLMClient(abc.ABC):
    """大语言模型客户端抽象基类，遵循 ports.LLMClient 协议契约。"""

    name: str = "base"
    default_model: str = "mock-model"

    def __init__(
        self,
        *,
        name: str | None = None,
        default_model: str | None = None,
    ) -> None:
        if name is not None:
            self.name = name
        if default_model is not None:
            self.default_model = default_model

    @abc.abstractmethod
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
