"""M5 输出 Schema 校验器与 JSON 鲁棒清洗引擎（T04），`CONTRACTS.md §1, §5`。

提供多层容错 JSON 提取清洗（剥离围栏、控制字符、尾随逗号、Python 变量）、
JSON Schema 与 Pydantic 模型双模校验，并生成对大模型友好的结构化纠错诊断信息。
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

__all__ = [
    "SchemaValidationResult",
    "SchemaValidator",
    "clean_and_extract_json",
    "validate_json_schema",
]

_MARKDOWN_CODE_BLOCK_PATTERN = re.compile(
    r"```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```",
    re.MULTILINE,
)
_COMMENT_PATTERN = re.compile(r"//.*?$|/\*.*?\*/", re.MULTILINE | re.DOTALL)
_TRAILING_COMMA_PATTERN = re.compile(r",\s*([\]}])")


def _strip_comments_and_trailing_commas(text: str) -> str:
    """清理 JSON 字符串中的注释与数组/字典尾随逗号。"""
    no_comments = _COMMENT_PATTERN.sub("", text)
    no_trailing = _TRAILING_COMMA_PATTERN.sub(r"\1", no_comments)
    return no_trailing.strip()


def clean_and_extract_json(raw_text: str) -> tuple[dict[str, Any] | None, list[str]]:
    """从大模型原始输出中稳健清洗并提取 JSON 字典。

    容错策略：
    1. 直接完整 json.loads 解析；
    2. 提取 Markdown ```json 围栏；
    3. 提取最外层大括号 {...}；
    4. 清除行注释与块注释；
    5. 清除对象与数组的尾随逗号；
    6. 替换 Python 字面量 (True/False/None)；
    7. 尝试通过 ast.literal_eval 兜底解析单引号字典。
    """
    errors: list[str] = []
    stripped = raw_text.strip()
    if not stripped:
        return None, ["Empty output string received from LLM"]

    # 1. 尝试直接解析
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed, []
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. 提取 Markdown 代码块
    candidate: str | None = None
    match = _MARKDOWN_CODE_BLOCK_PATTERN.search(stripped)
    if match:
        candidate = match.group(1).strip()
    else:
        # 3. 提取最外层大括号
        first_brace = stripped.find("{")
        last_brace = stripped.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            candidate = stripped[first_brace : last_brace + 1]

    if candidate:
        # 直接尝试解析提取的候选
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed, []
        except (json.JSONDecodeError, ValueError):
            pass

        # 4 & 5. 清理注释与尾随逗号
        cleaned = _strip_comments_and_trailing_commas(candidate)
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed, []
        except (json.JSONDecodeError, ValueError):
            pass

        # 6. 处理 Python 字面量
        py_fixed = cleaned
        py_fixed = re.sub(r"\bTrue\b", "true", py_fixed)
        py_fixed = re.sub(r"\bFalse\b", "false", py_fixed)
        py_fixed = re.sub(r"\bNone\b", "null", py_fixed)
        try:
            parsed = json.loads(py_fixed)
            if isinstance(parsed, dict):
                return parsed, []
        except (json.JSONDecodeError, ValueError):
            pass

        # 7. 兜底尝试 ast.literal_eval 解析 Python 风格单引号字典
        try:
            eval_res = ast.literal_eval(cleaned)
            if isinstance(eval_res, dict):
                # 重新转成合规 JSON 字典（转换 Decimal/特殊类型）
                return json.loads(json.dumps(eval_res, default=str)), []
        except (ValueError, SyntaxError, TypeError):
            pass

    errors.append("Failed to extract or parse a valid JSON object from LLM response text")
    return None, errors


def validate_json_schema(
    data: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> list[str]:
    """轻量级递归 JSON Schema 校验器，输出人类与大模型易懂的违规信息。"""
    errors: list[str] = []
    if not isinstance(schema, dict) or not schema:
        return errors

    expected_type = schema.get("type")

    # 1. 类型校验
    if expected_type == "object":
        if not isinstance(data, dict):
            return [f"Field '{path}': expected object/dict, got {type(data).__name__}"]

        # 必填字段校验
        required = schema.get("required", [])
        for field_name in required:
            if field_name not in data or data[field_name] is None:
                errors.append(f"Missing required field: '{field_name}' at '{path}.{field_name}'")

        # 属性递归校验
        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            if prop_name in data and data[prop_name] is not None:
                sub_path = f"{path}.{prop_name}" if path != "$" else f"$.{prop_name}"
                errors.extend(validate_json_schema(data[prop_name], prop_schema, sub_path))

    elif expected_type == "array":
        if not isinstance(data, list):
            return [f"Field '{path}': expected array/list, got {type(data).__name__}"]

        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for i, item in enumerate(data):
                errors.extend(validate_json_schema(item, items_schema, f"{path}[{i}]"))

    elif expected_type == "string":
        if not isinstance(data, str):
            errors.append(f"Field '{path}': expected string, got {type(data).__name__}")
        else:
            if "enum" in schema and data not in schema["enum"]:
                errors.append(
                    f"Field '{path}': value '{data}' is not one of allowed enum values: "
                    f"{schema['enum']}"
                )

    elif expected_type in ("number", "integer"):
        if isinstance(data, bool) or not isinstance(data, (int, float)):
            errors.append(f"Field '{path}': expected {expected_type}, got {type(data).__name__}")
        else:
            if expected_type == "integer" and not isinstance(data, int):
                errors.append(f"Field '{path}': expected integer, got float ({data})")
            if "minimum" in schema and data < schema["minimum"]:
                errors.append(
                    f"Field '{path}': value {data} is less than minimum {schema['minimum']}"
                )
            if "maximum" in schema and data > schema["maximum"]:
                errors.append(
                    f"Field '{path}': value {data} is greater than maximum {schema['maximum']}"
                )

    elif expected_type == "boolean":
        if not isinstance(data, bool):
            errors.append(f"Field '{path}': expected boolean, got {type(data).__name__}")

    # 顶层 enum（若未在 type 分支触发）
    if "enum" in schema and expected_type != "string" and data not in schema["enum"]:
        errors.append(
            f"Field '{path}': value '{data}' is not one of allowed enum values: {schema['enum']}"
        )

    return errors


@dataclass(frozen=True)
class SchemaValidationResult:
    """Schema 校验结果封装。"""

    is_valid: bool
    data: dict[str, Any] | None = None
    model_instance: BaseModel | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def error_summary(self) -> str:
        """返回换行拼接的错误摘要。"""
        return "\n".join(self.errors)


class SchemaValidator:
    """统一 Schema 校验门面。"""

    @classmethod
    def clean_json(cls, raw_text: str) -> dict[str, Any] | None:
        """从字符串中提取清洗后的 JSON 对象，失败返回 None。"""
        data, _ = clean_and_extract_json(raw_text)
        return data

    @classmethod
    def validate(
        cls,
        raw_text_or_dict: str | dict[str, Any] | None,
        *,
        schema: dict[str, Any] | None = None,
        target_model: type[BaseModel] | None = None,
    ) -> SchemaValidationResult:
        """执行全套清洗与 Schema 校验。

        支持：
        1. 优先使用 target_model (Pydantic) 强类型校验；
        2. 其次使用 schema (JSON Schema dict) 规范校验；
        3. 若两者皆无，只要能够提取出有效字典即视为有效。
        """
        # 1. 规范化输入为 dict
        if raw_text_or_dict is None:
            return SchemaValidationResult(
                is_valid=False,
                errors=["Input for validation is None"],
            )

        parsed_data: dict[str, Any] | None = None
        if isinstance(raw_text_or_dict, dict):
            parsed_data = raw_text_or_dict
        elif isinstance(raw_text_or_dict, str):
            extracted, clean_errs = clean_and_extract_json(raw_text_or_dict)
            if extracted is None:
                return SchemaValidationResult(is_valid=False, errors=clean_errs)
            parsed_data = extracted
        else:
            return SchemaValidationResult(
                is_valid=False,
                errors=[f"Unsupported input type: {type(raw_text_or_dict).__name__}"],
            )

        errors: list[str] = []
        model_instance: BaseModel | None = None

        # 2. 校验 Pydantic 模型
        if target_model is not None:
            try:
                model_instance = target_model.model_validate(parsed_data)
            except ValidationError as val_err:
                for err in val_err.errors():
                    field_loc = ".".join(str(loc) for loc in err.get("loc", []))
                    msg = err.get("msg", "Invalid value")
                    errors.append(f"Field '{field_loc}': {msg}")

        # 3. 校验 JSON Schema
        if schema:
            schema_errs = validate_json_schema(parsed_data, schema)
            errors.extend(schema_errs)

        is_valid = len(errors) == 0
        return SchemaValidationResult(
            is_valid=is_valid,
            data=parsed_data if is_valid else None,
            model_instance=model_instance if is_valid else None,
            errors=errors,
        )
