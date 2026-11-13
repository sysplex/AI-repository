"""M5 Token 计费器与 MockLLMClient 单元测试（T02）。

测试内容：
1. pricing.py：模型定价注册表、标准模型覆盖、高精 Decimal 计算（严格避免浮点丢失）、
   Prompt 缓存折扣、未知模型异常与默认兜底、非法参数保护；
2. adapters/base.py：JSON 结构提取（纯文本/代码块/嵌入式）、Schema 提示词注入、
   Token 启发式估算、成本计算兜底；
3. adapters/mock.py：LLMClient 协议兼容性、预设输出、调用历史记录、多轮队列消费、
   关键词路由、全部故障注入模式（超时、网络断开、500、非法 JSON、缺字段、
   越界枚举、编造数字、提示词注入）及重置恢复；
4. exceptions.py：错误码、HTTP 状态码与 AppError 统一错误体系兼容性。
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import pytest

from app.core.errors import AppError, ErrorCode, LLMFailed
from app.modules.ai.adapters.base import (
    BaseLLMClient,
    compute_result_cost,
    estimate_token_count,
    extract_json_from_text,
    inject_schema_instruction,
)
from app.modules.ai.adapters.mock import (
    DEFAULT_MOCK_PAYLOAD,
    MockCall,
    MockFaultMode,
    MockLLMClient,
)
from app.modules.ai.exceptions import (
    AIServiceError,
    AIServiceUnavailableError,
    BudgetCircuitOpenError,
    FactTracingError,
    PromptNotFoundError,
    QuotaExceededError,
    SchemaValidationError,
)
from app.modules.ai.ports import LLMClient
from app.modules.ai.pricing import (
    DEFAULT_FALLBACK_PRICING,
    ModelPricing,
    calculate_cost,
    get_model_pricing,
    list_supported_models,
    register_model_pricing,
    reset_pricing_registry,
)
from app.modules.ai.schemas import LLMResult

# =============================================================================
# 1. Token 计费与定价注册表测试（pricing.py）
# =============================================================================


@pytest.fixture(autouse=True)
def _restore_pricing_registry() -> Any:
    """每个测试执行后自动复原定价注册表，防止单测之间互相污染。"""
    yield
    reset_pricing_registry()


def test_standard_models_registered() -> None:
    """验证主流商业及 Mock 模型均已内置注册。"""
    supported = list_supported_models()
    expected = [
        "claude-3-5-sonnet",
        "claude-3-haiku",
        "gpt-4o",
        "gpt-4o-mini",
        "deepseek-chat",
        "deepseek-reasoner",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "mock",
        "mock-model",
    ]
    for m in expected:
        assert m in supported, f"Model '{m}' should be registered in pricing table"


def test_model_pricing_case_insensitivity_and_strip() -> None:
    """模型名称大小写与前后空格不敏感。"""
    pricing1 = get_model_pricing("GPT-4o")
    pricing2 = get_model_pricing("  gpt-4o  ")
    pricing3 = get_model_pricing("claude-3-5-sonnet")

    assert pricing1.model == "gpt-4o"
    assert pricing2.model == "gpt-4o"
    assert pricing3.input_price_per_1m == Decimal("3.00")


def test_hand_calculated_costs_exact_decimal() -> None:
    """严格验证手算用例的高精 Decimal 计费精度，绝无浮点数误差。"""
    # 1. Claude 3.5 Sonnet: input $3.00/1M, output $15.00/1M
    # 1000 input, 500 output -> 0.003 + 0.0075 = 0.010500
    cost_sonnet = calculate_cost("claude-3-5-sonnet", input_tokens=1000, output_tokens=500)
    assert isinstance(cost_sonnet, Decimal)
    assert cost_sonnet == Decimal("0.010500")

    # 2. GPT-4o-mini: input $0.15/1M, output $0.60/1M
    # 1234 in, 567 out -> 1234*0.15/1e6 = 0.0001851; 567*0.60/1e6 = 0.0003402
    # sum = 0.0005253 -> quantize(6) -> 0.000525
    cost_mini = calculate_cost("gpt-4o-mini", input_tokens=1234, output_tokens=567)
    assert cost_mini == Decimal("0.000525")

    # 3. DeepSeek-Chat with prompt caching:
    # input $0.14/1M, cached $0.014/1M, output $0.28/1M
    # 10000 in (8000 cached, 2000 uncached), 1000 out:
    # uncached = 2000 * 0.14 / 1e6 = 0.000280
    # cached = 8000 * 0.014 / 1e6 = 0.000112
    # output = 1000 * 0.28 / 1e6 = 0.000280
    # sum = 0.00067200 -> 0.000672
    cost_deepseek = calculate_cost(
        "deepseek-chat",
        input_tokens=10000,
        output_tokens=1000,
        cached_input_tokens=8000,
    )
    assert cost_deepseek == Decimal("0.000672")

    # 4. Mock zero-cost model
    cost_mock = calculate_cost("mock-model", input_tokens=999999, output_tokens=999999)
    assert cost_mock == Decimal("0.000000")

    # 5. Zero tokens
    cost_zero = calculate_cost("gpt-4o", input_tokens=0, output_tokens=0)
    assert cost_zero == Decimal("0.000000")


def test_pricing_invalid_token_counts() -> None:
    """非法 Token 数量必须抛出 ValueError。"""
    with pytest.raises(ValueError, match="Token counts must be non-negative"):
        calculate_cost("gpt-4o", input_tokens=-1, output_tokens=10)

    with pytest.raises(ValueError, match="Token counts must be non-negative"):
        calculate_cost("gpt-4o", input_tokens=10, output_tokens=-5)

    with pytest.raises(ValueError, match="cached_input_tokens cannot exceed total input_tokens"):
        calculate_cost("deepseek-chat", input_tokens=100, output_tokens=50, cached_input_tokens=150)


def test_unknown_model_raises_or_uses_default() -> None:
    """未知模型默认抛出 KeyError；指定 default_pricing 时回退计算。"""
    with pytest.raises(KeyError, match="Unknown model pricing: 'phantom-gpt'"):
        calculate_cost("phantom-gpt", input_tokens=100, output_tokens=100)

    # 带 default_pricing
    fallback_cost = calculate_cost(
        "phantom-gpt",
        input_tokens=1000,
        output_tokens=1000,
        default_pricing=DEFAULT_FALLBACK_PRICING,
    )
    # DEFAULT_FALLBACK_PRICING: in $2.50, out $10.00 -> 0.0025 + 0.01 = 0.012500
    assert fallback_cost == Decimal("0.012500")


def test_custom_model_registration() -> None:
    """支持动态注册自定义私有或开源模型。"""
    custom = ModelPricing(
        model="custom-llama-3.3-70b",
        input_price_per_1m=Decimal("0.85"),
        output_price_per_1m=Decimal("1.20"),
        provider="groq",
        description="Llama 3.3 70B via fast groq",
    )
    register_model_pricing(custom)

    assert "custom-llama-3.3-70b" in list_supported_models()
    cost = calculate_cost("custom-llama-3.3-70b", input_tokens=2000, output_tokens=1000)
    # 2000 * 0.85 / 1e6 = 0.001700
    # 1000 * 1.20 / 1e6 = 0.001200
    # sum = 0.002900
    assert cost == Decimal("0.002900")


# =============================================================================
# 2. 基础适配器与工具测试（adapters/base.py）
# =============================================================================


def test_extract_json_from_clean_text() -> None:
    """纯净 JSON 字符串提取。"""
    raw = '{"verdict": "buy", "score": 92}'
    parsed = extract_json_from_text(raw)
    assert parsed == {"verdict": "buy", "score": 92}


def test_extract_json_from_markdown_blocks() -> None:
    """从包含 ```json 代码块的 Markdown 文本中提取。"""
    raw_with_tag = """
Here is your analysis report:
```json
{
  "verdict": "wait",
  "confidence": "medium",
  "target_price": 185.50
}
```
Please let me know if you need more details.
"""
    parsed = extract_json_from_text(raw_with_tag)
    assert parsed is not None
    assert parsed["verdict"] == "wait"
    assert parsed["target_price"] == 185.50

    raw_without_tag = """
Analysis:
```
{"action": "sell"}
```
"""
    parsed2 = extract_json_from_text(raw_without_tag)
    assert parsed2 == {"action": "sell"}


def test_extract_json_from_embedded_text() -> None:
    """从自然语言段落中最外层匹配提取 JSON。"""
    raw_embedded = 'I have completed the review: {"status": "ok", "count": 5}. Thank you!'
    parsed = extract_json_from_text(raw_embedded)
    assert parsed == {"status": "ok", "count": 5}


def test_extract_json_invalid_returns_none() -> None:
    """非法 JSON 或纯文本返回 None。"""
    assert extract_json_from_text("") is None
    assert extract_json_from_text("   ") is None
    assert extract_json_from_text("This is purely plain English without braces.") is None
    assert extract_json_from_text("{unclosed: invalid json") is None


def test_inject_schema_instruction() -> None:
    """Schema 提示词注入。"""
    original = "You are a professional equity research assistant."
    assert inject_schema_instruction(original, None) == original
    assert inject_schema_instruction(original, {}) == original

    schema = {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["buy", "wait", "avoid"]},
        },
        "required": ["verdict"],
    }
    injected = inject_schema_instruction(original, schema)
    assert original in injected
    assert "[OUTPUT FORMAT INSTRUCTION]" in injected
    assert '"enum": [\n        "buy"' in injected


def test_estimate_token_count() -> None:
    """中英文混合启发式 Token 估算。"""
    assert estimate_token_count("") == 0
    # English
    en_count = estimate_token_count("Hello world, this is a test prompt.")
    assert 5 <= en_count <= 15
    # Chinese
    cn_count = estimate_token_count("这是一段中文测试提示词，用于股票量化分析。")
    assert 10 <= cn_count <= 25


def test_compute_result_cost_fallback() -> None:
    """未知模型安全回退兜底定价。"""
    cost = compute_result_cost("completely-unknown-model", 1000, 1000)
    assert cost > Decimal("0.000000")


# =============================================================================
# 3. 全功能 MockLLMClient 测试（adapters/mock.py）
# =============================================================================


@pytest.mark.asyncio
async def test_mock_llm_client_protocol_conformance() -> None:
    """MockLLMClient 严格实现 ports.LLMClient 协议契约。"""
    client = MockLLMClient()
    assert isinstance(client, LLMClient)
    assert isinstance(client, BaseLLMClient)
    assert client.name == "mock"


@pytest.mark.asyncio
async def test_mock_llm_client_default_successful_generation() -> None:
    """默认配置下生成标准合法响应并正确记录调用历史。"""
    client = MockLLMClient()
    assert client.call_count == 0
    assert client.last_call is None

    result = await client.generate(
        system="System prompt instruction",
        user="Analyze AAPL for Q4",
        output_schema={"type": "object"},
        max_tokens=1024,
        temperature=0.3,
    )

    # 1. 断言返回结构
    assert isinstance(result, LLMResult)
    assert result.parsed_json == DEFAULT_MOCK_PAYLOAD
    assert '"verdict": "buy"' in result.raw_text
    assert result.model == "mock-model"
    assert result.input_tokens == 150
    assert result.output_tokens == 300
    assert result.cost_usd == Decimal("0.000000")
    assert result.latency_ms == 25

    # 2. 断言调用记录
    assert client.call_count == 1
    call: MockCall = client.last_call  # type: ignore[assignment]
    assert call is not None
    assert call.system == "System prompt instruction"
    assert call.user == "Analyze AAPL for Q4"
    assert call.max_tokens == 1024
    assert call.temperature == 0.3
    assert client.last_system_prompt == "System prompt instruction"
    assert client.last_user_prompt == "Analyze AAPL for Q4"


@pytest.mark.asyncio
async def test_mock_llm_client_canned_json_and_text() -> None:
    """支持预设自定义 JSON 和纯文本响应。"""
    client = MockLLMClient()

    # 自定义 JSON
    client.set_canned_json(
        {"custom_key": "custom_value", "number": 42},
        input_tokens=80,
        output_tokens=120,
    )
    res_json = await client.generate(system="", user="")
    assert res_json.parsed_json == {"custom_key": "custom_value", "number": 42}
    assert res_json.input_tokens == 80
    assert res_json.output_tokens == 120

    # 自定义纯文本
    client.set_canned_text("Plain text analysis output")
    res_text = await client.generate(system="", user="")
    assert res_text.parsed_json is None
    assert res_text.raw_text == "Plain text analysis output"


@pytest.mark.asyncio
async def test_mock_llm_client_response_queue_fifo() -> None:
    """多轮响应队列 FIFO 依次消费并在耗尽后回退默认响应。"""
    client = MockLLMClient()
    client.enqueue_response({"turn": 1})
    client.enqueue_response({"turn": 2})

    r1 = await client.generate(system="", user="turn 1")
    assert r1.parsed_json == {"turn": 1}

    r2 = await client.generate(system="", user="turn 2")
    assert r2.parsed_json == {"turn": 2}

    # 队列已空，回退默认
    r3 = await client.generate(system="", user="turn 3")
    assert r3.parsed_json == DEFAULT_MOCK_PAYLOAD
    assert client.call_count == 3


@pytest.mark.asyncio
async def test_mock_llm_client_prompt_mapping() -> None:
    """关键词路由响应绑定。"""
    client = MockLLMClient()
    client.map_prompt("NVDA", {"company": "NVIDIA", "verdict": "buy"})
    client.map_prompt("TSLA", {"company": "TESLA", "verdict": "wait"})

    r_nvda = await client.generate(system="", user="Please evaluate NVDA fundamentals")
    assert r_nvda.parsed_json == {"company": "NVIDIA", "verdict": "buy"}

    r_tsla = await client.generate(system="", user="Please evaluate TSLA technicals")
    assert r_tsla.parsed_json == {"company": "TESLA", "verdict": "wait"}


@pytest.mark.asyncio
async def test_mock_llm_client_fault_injection_timeout() -> None:
    """故障注入：超时异常。"""
    client = MockLLMClient()
    client.set_fault(MockFaultMode.TIMEOUT)

    with pytest.raises(TimeoutError, match="Mock LLM request timed out"):
        await client.generate(system="", user="")


@pytest.mark.asyncio
async def test_mock_llm_client_fault_injection_network_error() -> None:
    """故障注入：网络中断 (AIServiceUnavailableError 503)。"""
    client = MockLLMClient()
    client.set_fault(MockFaultMode.NETWORK_ERROR)

    with pytest.raises(AIServiceUnavailableError) as exc_info:
        await client.generate(system="", user="")

    assert exc_info.value.code == ErrorCode.LLM_FAILED
    assert exc_info.value.http_status == 503


@pytest.mark.asyncio
async def test_mock_llm_client_fault_injection_server_error() -> None:
    """故障注入：服务商 500 异常 (LLMFailed)。"""
    client = MockLLMClient()
    client.set_fault(MockFaultMode.SERVER_ERROR)

    with pytest.raises(LLMFailed) as exc_info:
        await client.generate(system="", user="")

    assert exc_info.value.code == ErrorCode.LLM_FAILED
    assert exc_info.value.http_status == 502


@pytest.mark.asyncio
async def test_mock_llm_client_fault_injection_invalid_json() -> None:
    """故障注入：输出残缺非法 JSON（用于触发后续 T04 自动重试机制）。"""
    client = MockLLMClient()
    client.set_fault(MockFaultMode.INVALID_JSON)

    res = await client.generate(system="", user="")
    assert res.parsed_json is None
    assert "unclosed string without brace" in res.raw_text


@pytest.mark.asyncio
async def test_mock_llm_client_fault_injection_missing_fields() -> None:
    """故障注入：输出缺少必须字段的 JSON。"""
    client = MockLLMClient()
    client.set_fault(MockFaultMode.MISSING_FIELDS)

    res = await client.generate(system="", user="")
    assert res.parsed_json is not None
    assert "unrelated_field" in res.parsed_json
    assert "verdict" not in res.parsed_json


@pytest.mark.asyncio
async def test_mock_llm_client_fault_injection_out_of_bound_enum() -> None:
    """故障注入：输出越界非法枚举。"""
    client = MockLLMClient()
    client.set_fault(MockFaultMode.OUT_OF_BOUND_ENUM)

    res = await client.generate(system="", user="")
    assert res.parsed_json is not None
    assert res.parsed_json["verdict"] == "YOLO_TO_THE_MOON"


@pytest.mark.asyncio
async def test_mock_llm_client_fault_injection_fabricated_numbers() -> None:
    """故障注入：编造数字幻觉（用于触发后续 T05 数字溯源校验拦截）。"""
    client = MockLLMClient()
    client.set_fault(MockFaultMode.FABRICATED_NUMBERS)

    res = await client.generate(system="", user="")
    assert res.parsed_json is not None
    assert res.parsed_json["key_metrics"]["target_price"] == 999999.99


@pytest.mark.asyncio
async def test_mock_llm_client_fault_injection_prompt_injection() -> None:
    """故障注入：提示词注入攻击回显。"""
    client = MockLLMClient()
    client.set_fault(MockFaultMode.PROMPT_INJECTION_ECHO)

    res = await client.generate(system="", user="")
    assert res.parsed_json is not None
    assert res.parsed_json["verdict"] == "injected"
    assert "SYSTEM OVERRIDE" in res.parsed_json["message"]


@pytest.mark.asyncio
async def test_mock_llm_client_fault_queue_recovery() -> None:
    """故障队列测试：第 1 次调用注入非法 JSON，第 2 次调用返回成功。"""
    client = MockLLMClient()
    client.enqueue_fault(MockFaultMode.INVALID_JSON)
    client.enqueue_response({"recovered": True})

    # Call 1: invalid json
    r1 = await client.generate(system="", user="try 1")
    assert r1.parsed_json is None

    # Call 2: recovered
    r2 = await client.generate(system="", user="try 2")
    assert r2.parsed_json == {"recovered": True}
    assert client.call_count == 2


@pytest.mark.asyncio
async def test_mock_llm_client_reset() -> None:
    """调用 reset() 后所有状态被清空。"""
    client = MockLLMClient()
    client.set_fault(MockFaultMode.TIMEOUT)
    client.enqueue_response({"should_be_cleared": True})
    client.map_prompt("foo", {"bar": "baz"})

    with pytest.raises(TimeoutError):
        await client.generate(system="", user="")

    assert client.call_count == 1

    # Reset
    client.reset()
    assert client.call_count == 0
    assert client.last_call is None
    assert client.fault_mode == MockFaultMode.NONE

    # 调用后恢复正常输出
    normal = await client.generate(system="", user="fresh")
    assert normal.parsed_json == DEFAULT_MOCK_PAYLOAD
    assert client.call_count == 1


@pytest.mark.asyncio
async def test_mock_llm_client_real_delay_simulation() -> None:
    """当 simulate_real_delay 为 True 时真实休眠指定毫秒。"""
    client = MockLLMClient(default_latency_ms=30, simulate_real_delay=True)
    t0 = time.perf_counter()
    res = await client.generate(system="", user="")
    elapsed = time.perf_counter() - t0

    assert res.latency_ms == 30
    assert elapsed >= 0.025  # 至少 25ms


# =============================================================================
# 4. 异常体系测试（exceptions.py）
# =============================================================================


def test_ai_exceptions_hierarchy_and_attributes() -> None:
    """验证所有 AI 异常均继承自 AppError 并具备预期 code 与 http_status。"""
    exceptions = [
        (AIServiceError("error"), ErrorCode.INTERNAL_ERROR, 500),
        (AIServiceUnavailableError("down"), ErrorCode.LLM_FAILED, 503),
        (SchemaValidationError("invalid schema"), ErrorCode.LLM_OUTPUT_INVALID, 422),
        (FactTracingError("hallucination"), ErrorCode.LLM_OUTPUT_INVALID, 422),
        (QuotaExceededError("quota exhausted"), ErrorCode.QUOTA_EXCEEDED, 429),
        (BudgetCircuitOpenError("circuit open"), ErrorCode.BUDGET_CIRCUIT_OPEN, 503),
        (PromptNotFoundError("prompt 404"), ErrorCode.NOT_FOUND, 404),
    ]

    for exc, expected_code, expected_status in exceptions:
        assert isinstance(exc, AppError)
        assert exc.code == expected_code
        assert exc.http_status == expected_status
        assert exc.message is not None


# =============================================================================
# 5. 补充边界覆盖测试
# =============================================================================


class ConcreteLLMClient(BaseLLMClient):
    """测试用具体子类以覆盖基类初始化。"""

    async def generate(
        self,
        *,
        system: str,
        user: str,
        output_schema: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResult:
        return LLMResult(
            parsed_json={"ok": True},
            raw_text='{"ok": true}',
            model=self.default_model,
            input_tokens=10,
            output_tokens=10,
            cost_usd=Decimal("0.000000"),
            latency_ms=5,
        )


def test_base_llm_client_custom_init() -> None:
    """BaseLLMClient 自定义名称与默认模型参数初始化。"""
    client = ConcreteLLMClient(name="custom-client", default_model="claude-3-haiku")
    assert client.name == "custom-client"
    assert client.default_model == "claude-3-haiku"


def test_extract_json_edge_cases() -> None:
    """测试非 dict 类型 JSON（如列表、数字）及代码块内部残缺的处理。"""
    # 纯数字或字符串不是 dict，应忽略并返回 None
    assert extract_json_from_text("42") is None
    assert extract_json_from_text('"hello"') is None
    # 列表在直接解析时不为 dict，返回 None
    assert extract_json_from_text("[1, 2, 3]") is None

    # Markdown 代码块中包含无效 JSON
    invalid_block = "```json\n{unclosed json\n```"
    assert extract_json_from_text(invalid_block) is None

    # 最外层大括号匹配但内部残缺
    invalid_braces = "some prefix {bad: 123} some suffix"
    assert extract_json_from_text(invalid_braces) is None


@pytest.mark.asyncio
async def test_mock_llm_client_edge_branches() -> None:
    """覆盖 MockLLMClient 未调用时属性、直接入队 LLMResult 与非法类型防护。"""
    client = MockLLMClient()
    # 1. 未调用时 last_system_prompt 与 last_user_prompt
    assert client.last_system_prompt is None
    assert client.last_user_prompt is None

    # 2. set_canned_text 支持指定 token 数量
    client.set_canned_text("canned text", input_tokens=55, output_tokens=77)
    res_text = await client.generate(system="s", user="u")
    assert res_text.input_tokens == 55
    assert res_text.output_tokens == 77

    # 3. enqueue_response 支持直接入队 LLMResult 实例
    custom_res = LLMResult(
        parsed_json={"direct": True},
        raw_text='{"direct": true}',
        model="direct-model",
        input_tokens=10,
        output_tokens=20,
        cost_usd=Decimal("0.000100"),
        latency_ms=15,
    )
    client.enqueue_response(custom_res)
    res_dequeued = await client.generate(system="", user="")
    assert res_dequeued is custom_res

    # 4. enqueue_response 非法数据类型抛出 TypeError
    client.enqueue_response(12345)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Unsupported mock response item type"):
        await client.generate(system="", user="")
