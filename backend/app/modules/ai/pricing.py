"""M5 Token 计费器与模型定价注册表（T02），`CONTRACTS.md §0, §1`。

严格使用高精度 Decimal 进行 Token 成本计费，杜绝浮点数精度丢失，
支持主流商业与开源大模型（Claude、GPT-4o、DeepSeek、Gemini）及 Mock 定价。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

__all__ = [
    "COST_DECIMAL_PLACES",
    "COST_QUANTIZE_EXPONENT",
    "DEFAULT_FALLBACK_PRICING",
    "ModelPricing",
    "calculate_cost",
    "get_model_pricing",
    "list_supported_models",
    "register_model_pricing",
    "reset_pricing_registry",
]

COST_DECIMAL_PLACES: int = 6
COST_QUANTIZE_EXPONENT: Decimal = Decimal("0.000001")
ONE_MILLION: Decimal = Decimal("1000000")


@dataclass(frozen=True)
class ModelPricing:
    """单个大语言模型的价格配置（每百万 Token 美元计费）。"""

    model: str
    input_price_per_1m: Decimal
    output_price_per_1m: Decimal
    cached_input_price_per_1m: Decimal | None = None
    provider: str = "generic"
    description: str = ""

    def calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        *,
        cached_input_tokens: int = 0,
    ) -> Decimal:
        """根据输入输出 Token 数量计算高精美元成本（六位小数）。"""
        if input_tokens < 0 or output_tokens < 0 or cached_input_tokens < 0:
            raise ValueError("Token counts must be non-negative integers")
        if cached_input_tokens > input_tokens:
            raise ValueError("cached_input_tokens cannot exceed total input_tokens")

        uncached_input = input_tokens - cached_input_tokens
        input_cost = (Decimal(uncached_input) * self.input_price_per_1m) / ONE_MILLION

        cached_cost = Decimal(0)
        if cached_input_tokens > 0:
            cached_rate = (
                self.cached_input_price_per_1m
                if self.cached_input_price_per_1m is not None
                else (self.input_price_per_1m / Decimal(2))
            )
            cached_cost = (Decimal(cached_input_tokens) * cached_rate) / ONE_MILLION

        output_cost = (Decimal(output_tokens) * self.output_price_per_1m) / ONE_MILLION

        total = input_cost + cached_cost + output_cost
        return total.quantize(COST_QUANTIZE_EXPONENT, rounding=ROUND_HALF_UP)


DEFAULT_FALLBACK_PRICING = ModelPricing(
    model="default-fallback",
    input_price_per_1m=Decimal("2.50"),
    output_price_per_1m=Decimal("10.00"),
    provider="generic",
    description="Fallback conservative pricing for unknown models",
)


def _build_default_pricing_table() -> dict[str, ModelPricing]:
    """构建内置标准模型定价表（单位：美元 / 1,000,000 tokens）。"""
    prices: list[ModelPricing] = [
        # Anthropic Claude 系列
        ModelPricing(
            model="claude-3-5-sonnet-20241022",
            input_price_per_1m=Decimal("3.00"),
            output_price_per_1m=Decimal("15.00"),
            cached_input_price_per_1m=Decimal("0.30"),
            provider="anthropic",
            description="Claude 3.5 Sonnet (latest)",
        ),
        ModelPricing(
            model="claude-3-5-sonnet",
            input_price_per_1m=Decimal("3.00"),
            output_price_per_1m=Decimal("15.00"),
            cached_input_price_per_1m=Decimal("0.30"),
            provider="anthropic",
            description="Claude 3.5 Sonnet alias",
        ),
        ModelPricing(
            model="claude-3-haiku-20240307",
            input_price_per_1m=Decimal("0.25"),
            output_price_per_1m=Decimal("1.25"),
            cached_input_price_per_1m=Decimal("0.025"),
            provider="anthropic",
            description="Claude 3 Haiku",
        ),
        ModelPricing(
            model="claude-3-haiku",
            input_price_per_1m=Decimal("0.25"),
            output_price_per_1m=Decimal("1.25"),
            cached_input_price_per_1m=Decimal("0.025"),
            provider="anthropic",
            description="Claude 3 Haiku alias",
        ),
        ModelPricing(
            model="claude-3-5-haiku-20241022",
            input_price_per_1m=Decimal("0.80"),
            output_price_per_1m=Decimal("4.00"),
            cached_input_price_per_1m=Decimal("0.08"),
            provider="anthropic",
            description="Claude 3.5 Haiku",
        ),
        ModelPricing(
            model="claude-3-5-haiku",
            input_price_per_1m=Decimal("0.80"),
            output_price_per_1m=Decimal("4.00"),
            cached_input_price_per_1m=Decimal("0.08"),
            provider="anthropic",
            description="Claude 3.5 Haiku alias",
        ),
        ModelPricing(
            model="claude-3-opus-20240229",
            input_price_per_1m=Decimal("15.00"),
            output_price_per_1m=Decimal("75.00"),
            cached_input_price_per_1m=Decimal("1.50"),
            provider="anthropic",
            description="Claude 3 Opus",
        ),
        ModelPricing(
            model="claude-3-opus",
            input_price_per_1m=Decimal("15.00"),
            output_price_per_1m=Decimal("75.00"),
            cached_input_price_per_1m=Decimal("1.50"),
            provider="anthropic",
            description="Claude 3 Opus alias",
        ),
        # OpenAI 系列
        ModelPricing(
            model="gpt-4o",
            input_price_per_1m=Decimal("2.50"),
            output_price_per_1m=Decimal("10.00"),
            cached_input_price_per_1m=Decimal("1.25"),
            provider="openai",
            description="GPT-4o flagship",
        ),
        ModelPricing(
            model="gpt-4o-2024-08-06",
            input_price_per_1m=Decimal("2.50"),
            output_price_per_1m=Decimal("10.00"),
            cached_input_price_per_1m=Decimal("1.25"),
            provider="openai",
            description="GPT-4o snapshot",
        ),
        ModelPricing(
            model="gpt-4o-mini",
            input_price_per_1m=Decimal("0.15"),
            output_price_per_1m=Decimal("0.60"),
            cached_input_price_per_1m=Decimal("0.075"),
            provider="openai",
            description="GPT-4o-mini fast & lightweight",
        ),
        ModelPricing(
            model="gpt-4o-mini-2024-07-18",
            input_price_per_1m=Decimal("0.15"),
            output_price_per_1m=Decimal("0.60"),
            cached_input_price_per_1m=Decimal("0.075"),
            provider="openai",
            description="GPT-4o-mini snapshot",
        ),
        ModelPricing(
            model="o1",
            input_price_per_1m=Decimal("15.00"),
            output_price_per_1m=Decimal("60.00"),
            provider="openai",
            description="OpenAI o1 reasoning model",
        ),
        ModelPricing(
            model="o1-mini",
            input_price_per_1m=Decimal("1.10"),
            output_price_per_1m=Decimal("4.40"),
            provider="openai",
            description="OpenAI o1-mini fast reasoning",
        ),
        # DeepSeek 系列
        ModelPricing(
            model="deepseek-chat",
            input_price_per_1m=Decimal("0.14"),
            output_price_per_1m=Decimal("0.28"),
            cached_input_price_per_1m=Decimal("0.014"),
            provider="deepseek",
            description="DeepSeek-V3 general model",
        ),
        ModelPricing(
            model="deepseek-v3",
            input_price_per_1m=Decimal("0.14"),
            output_price_per_1m=Decimal("0.28"),
            cached_input_price_per_1m=Decimal("0.014"),
            provider="deepseek",
            description="DeepSeek-V3 alias",
        ),
        ModelPricing(
            model="deepseek-reasoner",
            input_price_per_1m=Decimal("0.55"),
            output_price_per_1m=Decimal("2.19"),
            cached_input_price_per_1m=Decimal("0.14"),
            provider="deepseek",
            description="DeepSeek-R1 reasoning model",
        ),
        ModelPricing(
            model="deepseek-r1",
            input_price_per_1m=Decimal("0.55"),
            output_price_per_1m=Decimal("2.19"),
            cached_input_price_per_1m=Decimal("0.14"),
            provider="deepseek",
            description="DeepSeek-R1 alias",
        ),
        # Google Gemini 系列
        ModelPricing(
            model="gemini-1.5-flash",
            input_price_per_1m=Decimal("0.075"),
            output_price_per_1m=Decimal("0.30"),
            provider="google",
            description="Gemini 1.5 Flash lightweight",
        ),
        ModelPricing(
            model="gemini-1.5-pro",
            input_price_per_1m=Decimal("1.25"),
            output_price_per_1m=Decimal("5.00"),
            provider="google",
            description="Gemini 1.5 Pro multimodal",
        ),
        ModelPricing(
            model="gemini-2.0-flash",
            input_price_per_1m=Decimal("0.10"),
            output_price_per_1m=Decimal("0.40"),
            provider="google",
            description="Gemini 2.0 Flash next-gen",
        ),
        ModelPricing(
            model="gemini-3.5-flash-lite",
            input_price_per_1m=Decimal("0.05"),
            output_price_per_1m=Decimal("0.20"),
            provider="google",
            description="Gemini 3.5 Flash Lite (Free tier eligible)",
        ),
        ModelPricing(
            model="gemini-3.1-flash-lite",
            input_price_per_1m=Decimal("0.05"),
            output_price_per_1m=Decimal("0.20"),
            provider="google",
            description="Gemini 3.1 Flash Lite (Free tier eligible)",
        ),
        ModelPricing(
            model="gemini-3.8-flash",
            input_price_per_1m=Decimal("0.10"),
            output_price_per_1m=Decimal("0.40"),
            provider="google",
            description="Gemini 3.8 Flash high speed",
        ),
        # Mock / 本地零成本模型
        ModelPricing(
            model="mock",
            input_price_per_1m=Decimal("0.00"),
            output_price_per_1m=Decimal("0.00"),
            provider="mock",
            description="Zero-cost mock testing model",
        ),
        ModelPricing(
            model="mock-model",
            input_price_per_1m=Decimal("0.00"),
            output_price_per_1m=Decimal("0.00"),
            provider="mock",
            description="Zero-cost mock testing model alias",
        ),
    ]
    return {p.model.lower(): p for p in prices}


_MODEL_PRICING_REGISTRY: dict[str, ModelPricing] = _build_default_pricing_table()


def register_model_pricing(pricing: ModelPricing) -> None:
    """注册或覆盖自定义模型价格配置。"""
    key = pricing.model.lower().strip()
    _MODEL_PRICING_REGISTRY[key] = pricing


def get_model_pricing(model: str, default: ModelPricing | None = None) -> ModelPricing:
    """获取指定模型的定价配置；不存在且无 default 时抛出 KeyError。"""
    key = model.lower().strip()
    if key in _MODEL_PRICING_REGISTRY:
        return _MODEL_PRICING_REGISTRY[key]
    if default is not None:
        return default
    available = ", ".join(sorted(_MODEL_PRICING_REGISTRY.keys()))
    raise KeyError(f"Unknown model pricing: '{model}'. Supported models: [{available}]")


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cached_input_tokens: int = 0,
    default_pricing: ModelPricing | None = None,
) -> Decimal:
    """计算指定模型在给定 Token 消耗下的美元成本（精确到 6 位小数）。"""
    pricing = get_model_pricing(model, default=default_pricing)
    return pricing.calculate_cost(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
    )


def list_supported_models() -> list[str]:
    """返回当前已注册的所有支持模型列表（小写有序）。"""
    return sorted(_MODEL_PRICING_REGISTRY.keys())


def reset_pricing_registry() -> None:
    """重置定价注册表为系统默认内置配置。"""
    global _MODEL_PRICING_REGISTRY
    _MODEL_PRICING_REGISTRY = _build_default_pricing_table()
