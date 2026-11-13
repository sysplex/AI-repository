"""M5 输出 Schema 校验器与自动反馈重试引擎单元测试（T04）。

测试内容：
1. clean_and_extract_json：Markdown 代码块提取、注释剥离、尾随逗号清洗、
   Python 字面量修正与单引号容错；
2. validate_json_schema：对象、数组、必填项、枚举限制、数值极值约束与嵌套字段路径追踪；
3. SchemaValidator：Pydantic 实体与 JSON Schema 双重校验、格式化纠错信息提炼；
4. execute_with_retry：
   - 首次成功：零重试正常返回，计费与 Token 统计正确；
   - 首次失败、反馈重试成功：捕获缺失字段/越界枚举，向模型发送诊断信息，累加两轮开销；
   - 重试耗尽失败：抛出 SchemaValidationError（HTTP 422），详细记录错误与开销；
   - Pydantic 模型实例结构化返回；
   - RetryableLLMCaller 客户端门面测试。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel, Field

from app.core.errors import AppError, ErrorCode
from app.modules.ai.adapters.mock import MockFaultMode, MockLLMClient
from app.modules.ai.exceptions import SchemaValidationError
from app.modules.ai.retry import (
    RetryableLLMCaller,
    ValidatedLLMResult,
    execute_with_retry,
)
from app.modules.ai.validator import (
    SchemaValidationResult,
    SchemaValidator,
    clean_and_extract_json,
    validate_json_schema,
)

# =============================================================================
# 测试模型与 Schema
# =============================================================================


class SampleStockVerdict(BaseModel):
    """测试用 Pydantic 校验模型"""

    symbol: str
    verdict: str = Field(pattern=r"^(buy|wait|avoid)$")
    target_price: Decimal = Field(gt=0)
    confidence: str


SAMPLE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["verdict", "confidence", "summary"],
    "properties": {
        "verdict": {"type": "string", "enum": ["buy", "wait", "avoid"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "summary": {"type": "string"},
        "pe_ratio": {"type": "number", "minimum": 0, "maximum": 500},
        "tags": {"type": "array", "items": {"type": "string"}},
        "nested": {
            "type": "object",
            "required": ["score"],
            "properties": {"score": {"type": "integer"}},
        },
    },
}


# =============================================================================
# 1. clean_and_extract_json 鲁棒清洗测试
# =============================================================================


def test_clean_and_extract_clean_json() -> None:
    """标准 JSON 正常解析。"""
    raw = '{"verdict": "buy", "score": 90}'
    data, errs = clean_and_extract_json(raw)
    assert errs == []
    assert data == {"verdict": "buy", "score": 90}


def test_clean_and_extract_markdown_fence() -> None:
    """提取 Markdown 代码块中的 JSON 并忽略外围文本。"""
    raw = """
Here is your analysis:
```json
{
  "verdict": "wait",
  "confidence": "medium"
}
```
Hope this helps!
"""
    data, errs = clean_and_extract_json(raw)
    assert errs == []
    assert data == {"verdict": "wait", "confidence": "medium"}


def test_clean_and_extract_comments_and_trailing_commas() -> None:
    """自动清理单行/多行注释与对象、数组的尾随逗号。"""
    raw = """
    {
      // Investment verdict
      "verdict": "buy",
      /* Confidence level */
      "confidence": "high",
      "items": [1, 2, 3,],
    }
    """
    data, errs = clean_and_extract_json(raw)
    assert errs == []
    assert data is not None
    assert data["verdict"] == "buy"
    assert data["items"] == [1, 2, 3]


def test_clean_and_extract_python_literals_and_single_quotes() -> None:
    """自动纠正 Python 风格的 True/False/None 与单引号字典。"""
    # 1. Python 字面量
    raw_py = '{"is_bullish": True, "stop_loss": None, "is_risky": False}'
    data, errs = clean_and_extract_json(raw_py)
    assert errs == []
    assert data == {"is_bullish": True, "stop_loss": None, "is_risky": False}

    # 2. 单引号字典
    raw_single_quotes = "{'symbol': 'AAPL', 'price': 175.5}"
    data2, errs2 = clean_and_extract_json(raw_single_quotes)
    assert errs2 == []
    assert data2 == {"symbol": "AAPL", "price": 175.5}


def test_clean_and_extract_invalid_returns_errors() -> None:
    """空白或完全损坏的字符串返回明确错误。"""
    data, errs = clean_and_extract_json("")
    assert data is None
    assert "Empty output" in errs[0]

    data2, errs2 = clean_and_extract_json("Random gibberish without braces")
    assert data2 is None
    assert "Failed to extract" in errs2[0]


# =============================================================================
# 2. validate_json_schema 校验器测试
# =============================================================================


def test_validate_json_schema_valid() -> None:
    """完全符合 Schema 的字典无任何错误。"""
    valid_data = {
        "verdict": "buy",
        "confidence": "high",
        "summary": "Solid fundamentals",
        "pe_ratio": 24.5,
        "tags": ["tech", "ai"],
        "nested": {"score": 95},
    }
    errors = validate_json_schema(valid_data, SAMPLE_JSON_SCHEMA)
    assert errors == []


def test_validate_json_schema_missing_required() -> None:
    """检测缺失的必填字段。"""
    incomplete = {
        "verdict": "buy",
        # missing confidence and summary
    }
    errors = validate_json_schema(incomplete, SAMPLE_JSON_SCHEMA)
    assert any("confidence" in err for err in errors)
    assert any("summary" in err for err in errors)


def test_validate_json_schema_enum_and_range_violations() -> None:
    """检测越界枚举与数值超出范围。"""
    violated = {
        "verdict": "YOLO_MOON",  # invalid enum
        "confidence": "high",
        "summary": "test",
        "pe_ratio": -10,  # below minimum 0
    }
    errors = validate_json_schema(violated, SAMPLE_JSON_SCHEMA)
    assert any("YOLO_MOON" in err for err in errors)
    assert any("minimum" in err for err in errors)


def test_validate_json_schema_nested_and_array_types() -> None:
    """检测嵌套对象与数组元素类型违规。"""
    invalid_nested = {
        "verdict": "buy",
        "confidence": "high",
        "summary": "ok",
        "tags": ["valid", 12345],  # array item should be string
        "nested": {"score": "not_an_int"},  # should be integer
    }
    errors = validate_json_schema(invalid_nested, SAMPLE_JSON_SCHEMA)
    assert any("tags[1]" in err for err in errors)
    assert any("nested.score" in err for err in errors)


# =============================================================================
# 3. SchemaValidator 门面测试
# =============================================================================


def test_schema_validator_with_pydantic_model() -> None:
    """使用 Pydantic 模型作为 target_model 进行强类型强约束校验。"""
    valid_dict = {
        "symbol": "NVDA",
        "verdict": "buy",
        "target_price": "145.50",
        "confidence": "high",
    }
    res = SchemaValidator.validate(valid_dict, target_model=SampleStockVerdict)
    assert res.is_valid is True
    assert res.model_instance is not None
    assert isinstance(res.model_instance, SampleStockVerdict)
    assert res.model_instance.target_price == Decimal("145.50")

    # 违规用例（target_price <= 0，verdict 不在正则内）
    invalid_dict = {
        "symbol": "NVDA",
        "verdict": "unknown_action",
        "target_price": -5,
        "confidence": "high",
    }
    res2 = SchemaValidator.validate(invalid_dict, target_model=SampleStockVerdict)
    assert res2.is_valid is False
    assert len(res2.errors) >= 2


def test_schema_validator_clean_json_helper() -> None:
    """测试 clean_json 辅助快捷方法。"""
    res = SchemaValidator.clean_json('{"key": 1,}')
    assert res == {"key": 1}
    assert SchemaValidator.clean_json("invalid") is None


def test_validate_json_schema_additional_types_and_branches() -> None:
    """覆盖非 dict schema、类型不匹配、布尔类型、极值与顶层 enum 分支。"""
    # 1. 非 dict schema
    assert validate_json_schema("data", "not_a_dict") == []  # type: ignore[arg-type]

    # 2. 期望 object 但输入非 dict
    err_obj = validate_json_schema("not_a_dict", {"type": "object"})
    assert any("expected object/dict" in e for e in err_obj)

    # 3. 期望 array 但输入非 list
    err_arr = validate_json_schema("not_a_list", {"type": "array"})
    assert any("expected array/list" in e for e in err_arr)

    # 4. 期望 string 但输入数字
    err_str = validate_json_schema(12345, {"type": "string"})
    assert any("expected string" in e for e in err_str)

    # 5. 期望 integer 但输入 float，或超出 maximum
    err_int = validate_json_schema(12.34, {"type": "integer"})
    assert any("expected integer, got float" in e for e in err_int)

    err_max = validate_json_schema(200, {"type": "number", "maximum": 100})
    assert any("greater than maximum" in e for e in err_max)

    # 6. 期望 boolean 但输入字符串
    err_bool = validate_json_schema("true", {"type": "boolean"})
    assert any("expected boolean" in e for e in err_bool)

    # 7. 非 string 类型的顶层 enum
    err_enum = validate_json_schema(5, {"type": "integer", "enum": [1, 2, 3]})
    assert any("not one of allowed enum" in e for e in err_enum)


def test_schema_validation_result_error_summary() -> None:
    """测试 SchemaValidationResult.error_summary 属性。"""
    res = SchemaValidationResult(is_valid=False, errors=["Error 1", "Error 2"])
    assert res.error_summary == "Error 1\nError 2"


# =============================================================================
# 4. execute_with_retry & RetryableLLMCaller 测试
# =============================================================================


@pytest.mark.asyncio
async def test_execute_with_retry_first_attempt_success() -> None:
    """首次调用即符合 Schema：0 次重试成功，正常累计 Token 与开销。"""
    client = MockLLMClient()
    client.set_canned_json(
        {
            "verdict": "buy",
            "confidence": "high",
            "summary": "Valid summary",
            "pe_ratio": 20.0,
        },
        input_tokens=100,
        output_tokens=200,
    )

    res: ValidatedLLMResult = await execute_with_retry(
        client,
        system="System prompt",
        user="Analyze AAPL",
        output_schema=SAMPLE_JSON_SCHEMA,
    )

    assert isinstance(res, ValidatedLLMResult)
    assert res.retries_used == 0
    assert res.parsed_json is not None
    assert res.parsed_json["verdict"] == "buy"
    assert res.input_tokens == 100
    assert res.output_tokens == 200
    assert client.call_count == 1


@pytest.mark.asyncio
async def test_execute_with_retry_second_attempt_success() -> None:
    """首次返回缺字段/非法枚举，自动带纠错信息发起重试，第 2 次返回成功。"""
    client = MockLLMClient()

    # 1. 注入第 1 次故障：缺必填字段
    client.enqueue_fault(MockFaultMode.MISSING_FIELDS)
    # 2. 注入第 2 次成功返回
    client.enqueue_response(
        {
            "verdict": "wait",
            "confidence": "medium",
            "summary": "Recovered valid summary after feedback",
        }
    )

    res = await execute_with_retry(
        client,
        system="System prompt",
        user="Analyze TSLA",
        output_schema=SAMPLE_JSON_SCHEMA,
        max_retries=1,
    )

    # 1. 结果断言
    assert res.retries_used == 1
    assert res.parsed_json is not None
    assert res.parsed_json["verdict"] == "wait"
    assert "Recovered valid summary" in res.parsed_json["summary"]

    # 2. 调用次数断言：执行了 2 次调用
    assert client.call_count == 2

    # 3. 验证第 2 次调用的 user 提示词中包含了纠错反馈信息
    last_call_user = client.last_user_prompt
    assert last_call_user is not None
    assert "[SCHEMA VALIDATION ERROR CORRECTION]" in last_call_user
    assert "Missing required field" in last_call_user


@pytest.mark.asyncio
async def test_execute_with_retry_exhausted_raises_schema_validation_error() -> None:
    """重试耗尽仍然违规：抛出 SchemaValidationError (HTTP 422)，累计两轮开销。"""
    client = MockLLMClient()
    # 连续注入两次非法越界枚举
    client.enqueue_fault(MockFaultMode.OUT_OF_BOUND_ENUM)
    client.enqueue_fault(MockFaultMode.OUT_OF_BOUND_ENUM)

    with pytest.raises(SchemaValidationError) as exc_info:
        await execute_with_retry(
            client,
            system="System",
            user="Analyze NVDA",
            output_schema=SAMPLE_JSON_SCHEMA,
            max_retries=1,
        )

    # 1. 异常属性断言
    err = exc_info.value
    assert isinstance(err, AppError)
    assert err.code == ErrorCode.LLM_OUTPUT_INVALID
    assert err.http_status == 422
    assert "failed schema validation after 1 retry" in err.message

    # 2. details 中记录了累加消耗与两轮错误信息
    assert err.details["retries_used"] == 1
    assert len(err.details["errors"]) > 0
    assert client.call_count == 2


@pytest.mark.asyncio
async def test_execute_with_retry_with_target_model() -> None:
    """使用 target_model 参数，重试成功后返回包含 model_instance 的结果。"""
    client = MockLLMClient()
    # 首次返回缺少 target_price
    client.enqueue_response({"symbol": "AAPL", "verdict": "buy", "confidence": "high"})
    # 第二次返回合规数据
    client.enqueue_response(
        {
            "symbol": "AAPL",
            "verdict": "buy",
            "target_price": "220.00",
            "confidence": "high",
        }
    )

    res = await execute_with_retry(
        client,
        system="System",
        user="AAPL request",
        target_model=SampleStockVerdict,
        max_retries=1,
    )

    assert res.retries_used == 1
    assert res.model_instance is not None
    assert isinstance(res.model_instance, SampleStockVerdict)
    assert res.model_instance.symbol == "AAPL"
    assert res.model_instance.target_price == Decimal("220.00")


@pytest.mark.asyncio
async def test_retryable_llm_caller_facade() -> None:
    """测试 RetryableLLMCaller 门面调用。"""
    client = MockLLMClient()
    caller = RetryableLLMCaller(client, max_retries=1)

    client.set_canned_json(
        {
            "verdict": "avoid",
            "confidence": "low",
            "summary": "Bearish trend",
        }
    )

    res = await caller.call(
        system="System",
        user="Analyze speculative penny stock",
        output_schema=SAMPLE_JSON_SCHEMA,
    )

    assert res.parsed_json is not None
    assert res.parsed_json["verdict"] == "avoid"
    assert res.retries_used == 0
    assert client.call_count == 1
