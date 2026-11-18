"""Google Gemini API 客户端适配器实现（M5 / M10+）。

遵循 ports.LLMClient 协议契约与 TID251 规范。
支持动态传入用户个人 Google API Key、模型选择（默认 gemini-3.5-flash-lite）、
结构化 JSON 提示词增强与 Token 用量计量。
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.core.errors import LLMFailed
from app.core.logging import get_logger
from app.modules.ai.adapters.base import (
    BaseLLMClient,
    compute_result_cost,
    extract_json_from_text,
    inject_schema_instruction,
)
from app.modules.ai.exceptions import AIServiceUnavailableError
from app.modules.ai.schemas import LLMResult

logger = get_logger(__name__)

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GoogleGeminiClient(BaseLLMClient):
    """Google Gemini LLM 客户端实现。"""

    name: str = "google"
    default_model: str = "gemini-3.5-flash-lite"

    def __init__(
        self,
        api_key: str,
        *,
        default_model: str = "gemini-3.5-flash-lite",
        timeout: float = 30.0,
        proxy: str | None = None,
    ) -> None:
        super().__init__(name="google", default_model=default_model)
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.proxy = proxy

    async def generate(
        self,
        *,
        system: str,
        user: str,
        output_schema: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResult:
        """调用 Google Gemini generateContent 端点生成分析内容。"""
        if not self.api_key:
            raise LLMFailed("Google API Key 未配置，无法调用 Google Gemini 服务")

        start_time = time.perf_counter()

        # 注入 JSON Schema 约定
        effective_system = inject_schema_instruction(system, output_schema)

        url = f"{GEMINI_API_BASE_URL}/models/{self.default_model}:generateContent?key={self.api_key}"

        # 构造 Gemini 请求体
        body: dict[str, Any] = {
            "system_instruction": {
                "parts": [{"text": effective_system}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }
        if output_schema:
            body["generationConfig"]["responseMimeType"] = "application/json"

        try:
            async with httpx.AsyncClient(timeout=self.timeout, proxy=self.proxy) as client:
                resp = await client.post(url, json=body)
        except httpx.TimeoutException as exc:
            logger.error("google_gemini.timeout", model=self.default_model, timeout=self.timeout)
            raise AIServiceUnavailableError(f"Google Gemini 请求超时 ({self.timeout}s)") from exc
        except httpx.RequestError as exc:
            logger.error("google_gemini.network_error", error=str(exc))
            raise AIServiceUnavailableError(f"Google Gemini 网络连接失败: {exc}") from exc

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        if resp.status_code == 400:
            error_data = resp.json().get("error", {})
            msg = error_data.get("message", "API Key 无效或请求参数错误")
            logger.error("google_gemini.bad_request", details=msg)
            raise LLMFailed(f"Google API 参数或 Key 错误: {msg}")

        if resp.status_code in (402, 429):
            error_data = resp.json().get("error", {})
            msg = error_data.get("message", "配额耗尽或请求超频")
            logger.error("google_gemini.quota_exhausted", status=resp.status_code, details=msg)
            raise AIServiceUnavailableError(f"Google Gemini 额度耗尽或超频: {msg}")

        if resp.status_code != 200:
            logger.error("google_gemini.server_error", status=resp.status_code, body=resp.text[:300])
            raise AIServiceUnavailableError(f"Google Gemini 服务响应异常 (HTTP {resp.status_code})")

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise LLMFailed("Google Gemini 返回内容为空 (无 candidate 生成)")

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        raw_text = parts[0].get("text", "") if parts else ""

        usage = data.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)

        parsed_json = extract_json_from_text(raw_text)

        cost_usd = compute_result_cost(
            model=self.default_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        return LLMResult(
            raw_text=raw_text,
            parsed_json=parsed_json,
            model=self.default_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
