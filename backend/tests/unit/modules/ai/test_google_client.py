"""GoogleGeminiClient 适配器与集成测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.modules.ai.adapters.google import GoogleGeminiClient
from app.modules.ai.exceptions import AIServiceUnavailableError
from app.modules.ai.service import AIService


@pytest.mark.asyncio
async def test_google_gemini_client_init() -> None:
    client = GoogleGeminiClient(api_key="AQ.test_key", default_model="gemini-3.5-flash-lite")
    assert client.default_model == "gemini-3.5-flash-lite"
    assert client.api_key == "AQ.test_key"


@pytest.mark.asyncio
async def test_google_gemini_client_generate_success() -> None:
    client = GoogleGeminiClient(api_key="AQ.test_key", default_model="gemini-3.5-flash-lite")

    mock_resp_json = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": '{"result": "ok", "summary": "test"}'}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 15,
            "candidatesTokenCount": 25,
            "totalTokenCount": 40,
        },
    }

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_resp_json

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        res = await client.generate(
            system="You are an analyst.",
            user="Provide analysis.",
            output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
        )

        assert res.model == "gemini-3.5-flash-lite"
        assert res.parsed_json == {"result": "ok", "summary": "test"}
        assert res.input_tokens == 15
        assert res.output_tokens == 25
        assert res.latency_ms >= 0


@pytest.mark.asyncio
async def test_google_gemini_client_error_handling() -> None:
    client = GoogleGeminiClient(api_key="AQ.invalid_key")

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 402
    mock_response.json.return_value = {"error": {"code": 402, "message": "Prepayment required"}}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        with pytest.raises(AIServiceUnavailableError) as exc_info:
            await client.generate(system="", user="Hello")
        assert "Prepayment required" in str(exc_info.value)


def test_ai_service_create_client() -> None:
    from app.modules.ai.adapters.google import GoogleGeminiClient

    client_mock = AIService.create_client(provider="mock", api_key="")
    assert client_mock.__class__.__name__ == "MockLLMClient"

    client_google = AIService.create_client(
        provider="google", api_key="AQ.test", model="gemini-3.1-flash-lite"
    )
    assert isinstance(client_google, GoogleGeminiClient)
    assert client_google.default_model == "gemini-3.1-flash-lite"
