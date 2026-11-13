"""M5 输出 Schema 校验与单次反馈自动重试包装器（T04），`CONTRACTS.md §1, §5`。

执行包装器：
1. 初次调用 LLM 进行结构化文本/JSON 生成；
2. 执行 Schema 校验（缺字段、越界枚举、格式畸形）；
3. 若失败，生成明确的诊断纠错指引，向大模型自动发起 1 次反馈重试修正；
4. 累加各轮 Token 与成本开销，确保风控与审计准确；
5. 重试仍失败则抛出 SchemaValidationError（HTTP 422），杜绝残缺半成品流出。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.modules.ai.exceptions import SchemaValidationError
from app.modules.ai.ports import LLMClient
from app.modules.ai.schemas import LLMResult
from app.modules.ai.validator import SchemaValidationResult, SchemaValidator

__all__ = [
    "RetryableLLMCaller",
    "ValidatedLLMResult",
    "execute_with_retry",
]


class ValidatedLLMResult(LLMResult):
    """经过 Schema 校验（及可选反馈重试）的结构化 LLM 生成结果。"""

    retries_used: int = Field(default=0, ge=0)
    validation_errors: list[str] = Field(default_factory=list)
    model_instance: Any = None


async def execute_with_retry(
    client: LLMClient,
    *,
    system: str,
    user: str,
    output_schema: dict[str, Any] | None = None,
    target_model: type[BaseModel] | None = None,
    max_retries: int = 1,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> ValidatedLLMResult:
    """包装大模型调用，执行 Schema 校验与单次自动反馈重试修正。"""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: Decimal = Decimal("0.000000")
    total_latency_ms: int = 0

    current_user_prompt = user
    attempt = 0
    last_result: LLMResult | None = None
    last_val_result: SchemaValidationResult | None = None

    while attempt <= max_retries:
        attempt += 1

        # 1. 调用 LLM 生成
        result = await client.generate(
            system=system,
            user=current_user_prompt,
            output_schema=output_schema,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        last_result = result

        # 2. 累计 Token 消耗与成本
        total_input_tokens += result.input_tokens
        total_output_tokens += result.output_tokens
        total_cost_usd += result.cost_usd
        total_latency_ms += result.latency_ms

        # 3. 校验输出 Schema
        raw_to_validate = result.parsed_json if result.parsed_json is not None else result.raw_text
        val_result = SchemaValidator.validate(
            raw_to_validate,
            schema=output_schema,
            target_model=target_model,
        )
        last_val_result = val_result

        # 4. 校验成功直接返回
        if val_result.is_valid:
            retries_used = attempt - 1
            return ValidatedLLMResult(
                parsed_json=val_result.data or {},
                raw_text=result.raw_text,
                model=result.model,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                cost_usd=total_cost_usd,
                latency_ms=total_latency_ms,
                retries_used=retries_used,
                validation_errors=[],
                model_instance=val_result.model_instance,
            )

        # 5. 若校验失败且尚有重试机会，构造纠错反馈消息
        if attempt <= max_retries:
            errors_str = "\n".join(f"- {e}" for e in val_result.errors)
            correction_feedback = (
                "\n\n[SCHEMA VALIDATION ERROR CORRECTION]\n"
                "Your previous response was rejected due to schema validation errors:\n"
                f"{errors_str}\n\n"
                "Your previous raw response was:\n"
                f"{result.raw_text}\n\n"
                "Please fix all the above errors and return ONLY a strictly valid JSON object."
            )
            current_user_prompt = f"{user}{correction_feedback}"

    # 6. 重试耗尽仍然失败，抛出 SchemaValidationError
    err_list = last_val_result.errors if last_val_result is not None else ["Unknown schema failure"]
    raise SchemaValidationError(
        f"LLM output failed schema validation after {max_retries} retry: {'; '.join(err_list)}",
        details={
            "errors": err_list,
            "raw_text": last_result.raw_text if last_result else "",
            "retries_used": attempt - 1,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cost_usd": str(total_cost_usd),
        },
    )


class RetryableLLMCaller:
    """包装大模型并内置 Schema 自动纠错重试的客户端服务类。"""

    def __init__(
        self,
        client: LLMClient,
        *,
        max_retries: int = 1,
        default_max_tokens: int = 2048,
        default_temperature: float = 0.2,
    ) -> None:
        self.client = client
        self.max_retries = max_retries
        self.default_max_tokens = default_max_tokens
        self.default_temperature = default_temperature

    async def call(
        self,
        *,
        system: str,
        user: str,
        output_schema: dict[str, Any] | None = None,
        target_model: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ValidatedLLMResult:
        """执行带校验与重试的大模型调用。"""
        return await execute_with_retry(
            self.client,
            system=system,
            user=user,
            output_schema=output_schema,
            target_model=target_model,
            max_retries=self.max_retries,
            max_tokens=max_tokens if max_tokens is not None else self.default_max_tokens,
            temperature=temperature if temperature is not None else self.default_temperature,
        )
