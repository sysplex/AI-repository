"""M6 AI 研究用例新手可读性与强制合规防线，`CONTRACTS.md §5`。

实现：
1. 强制合规免责声明注入；
2. 违禁承诺性盈利词汇（保本、稳赚、零风险等）智能脱敏；
3. 财报指引与财务三表缺失项标准化标注为“数据缺失”；
4. 新手可读性校验与专业术语白话解读审查；
5. ``ComplianceGuardrail`` 统一合规守卫类。
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.modules.research.schemas import ResearchEnvelope

logger = get_logger("research.compliance")

__all__ = [
    "DEFAULT_DISCLAIMER",
    "FORBIDDEN_PROFIT_TERMS",
    "MISSING_DATA_PLACEHOLDER",
    "REPLACEMENT_MAP",
    "ComplianceGuardrail",
    "check_novice_readability",
    "ensure_compliance_disclaimer",
    "normalize_missing_earnings_fields",
    "sanitize_forbidden_terms",
    "sanitize_forbidden_terms_in_obj",
]

DEFAULT_DISCLAIMER: str = "本内容仅供研究与学习，不构成投资建议"
MISSING_DATA_PLACEHOLDER: str = "数据缺失"

# 禁止虚假宣传与收益承诺词汇表（docs/06-ai-prompt-spec.md §4）
REPLACEMENT_MAP: dict[str, str] = {
    "保本": "追求资本保值",
    "稳赚": "具备确定性潜力",
    "零风险": "低风险",
    "无风险": "低风险",
    "必涨": "具备上涨潜力",
    "稳赢": "胜率较高",
    "只赚不赔": "盈亏比较优",
    "翻倍承诺": "长期增值空间",
    "绝对收益": "超额收益潜力",
}

FORBIDDEN_PROFIT_TERMS: list[str] = list(REPLACEMENT_MAP.keys())


def sanitize_forbidden_terms(text: str) -> str:
    """替换文本中禁止使用的收益承诺与虚假宣传词汇。"""
    if not text:
        return text
    sanitized = text
    for forbidden, replacement in REPLACEMENT_MAP.items():
        if forbidden in sanitized:
            sanitized = re.sub(re.escape(forbidden), replacement, sanitized)
    return sanitized


def sanitize_forbidden_terms_in_obj(obj: Any) -> Any:
    """递归遍历数据结构并对字符串执行承诺词汇脱敏。"""
    if isinstance(obj, str):
        return sanitize_forbidden_terms(obj)
    if isinstance(obj, dict):
        return {k: sanitize_forbidden_terms_in_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_forbidden_terms_in_obj(item) for item in obj]
    return obj


def ensure_compliance_disclaimer(
    envelope_or_dict: Any,
) -> Any:
    """确保信封中必须包含法定免责声明。"""
    if isinstance(envelope_or_dict, ResearchEnvelope):
        if envelope_or_dict.disclaimer == DEFAULT_DISCLAIMER:
            return envelope_or_dict
        return envelope_or_dict.model_copy(update={"disclaimer": DEFAULT_DISCLAIMER})
    if isinstance(envelope_or_dict, dict):
        res = dict(envelope_or_dict)
        res["disclaimer"] = DEFAULT_DISCLAIMER
        return res
    return envelope_or_dict


def normalize_missing_earnings_fields(
    payload: dict[str, Any],
    missing_fields: list[str] | None = None,
) -> dict[str, Any]:
    """标准化财报缺失字段为'数据缺失'。

    严格遵循 CONTRACTS.md §5:
    财报中无指引或缺失字段，显式输出 '数据缺失'，严禁空缺或猜测填补。
    """
    normalized = dict(payload)
    missing = set(missing_fields or [])

    # 规范化核心三表指标（revenue, eps, margins）
    for metric_name in ["revenue", "eps", "margins"]:
        metric_val = normalized.get(metric_name)
        if metric_val is None or not isinstance(metric_val, dict):
            normalized[metric_name] = {
                "actual": MISSING_DATA_PLACEHOLDER,
                "expected": MISSING_DATA_PLACEHOLDER,
                "surprise_pct": MISSING_DATA_PLACEHOLDER,
                "explanation": f"{metric_name} 数据缺失",
            }
        else:
            m = dict(metric_val)
            for subfield in ["actual", "expected", "surprise_pct"]:
                val = m.get(subfield)
                if val is None or str(val).strip() in ("", "None", "null", "N/A", "缺失"):
                    m[subfield] = MISSING_DATA_PLACEHOLDER
            if not m.get("explanation"):
                m["explanation"] = f"{metric_name} 数据缺失"
            normalized[metric_name] = m

    # 规范化 guidance 指引
    guidance = normalized.get("guidance")
    if (
        guidance is None
        or str(guidance).strip() in ("", "None", "null", "N/A", "无", "未提供")
        or "earnings.guidance" in missing
    ):
        normalized["guidance"] = MISSING_DATA_PLACEHOLDER

    # 规范化 management_commentary 管理层评论
    commentary = normalized.get("management_commentary")
    if (
        not commentary
        or not isinstance(commentary, list)
        or len(commentary) == 0
        or "earnings.management_commentary" in missing
    ):
        normalized["management_commentary"] = [MISSING_DATA_PLACEHOLDER]

    return normalized


def check_novice_readability(
    payload: dict[str, Any],
    use_case: str,
) -> tuple[bool, list[str]]:
    """检查用例返回内容是否具备新手可读性与必要通俗解释。

    Returns:
        tuple[bool, list[str]]: (是否达标, 改进建议/警告列表)
    """
    suggestions: list[str] = []

    # 1. 检查是否存在新手总结/通俗要点字段
    has_beginner_summary = bool(
        payload.get("beginner_summary")
        or payload.get("summary")
        or payload.get("beginner_takeaway")
        or payload.get("short_term_outlook")
    )
    if not has_beginner_summary:
        suggestions.append("缺少新手专属总结 (beginner_summary / beginner_takeaway)")

    # 2. 检查特定用例的关键通俗解释字段
    if use_case == "research":
        takeaways = payload.get("beginner_takeaway")
        if not takeaways or not isinstance(takeaways, list) or len(takeaways) == 0:
            suggestions.append("股票研究报告缺少新手核心要点 (beginner_takeaway)")

    elif use_case == "buy_decision":
        if not payload.get("beginner_summary"):
            suggestions.append("买入决策缺少新手决策通俗总结 (beginner_summary)")

    elif use_case == "technical":
        # 检查 7 大指标是否包含 plain_explanation
        for dim in [
            "trend",
            "support_resistance",
            "moving_averages",
            "volume",
            "rsi",
            "macd",
            "breakout",
        ]:
            val = payload.get(dim)
            if isinstance(val, dict) and not val.get("plain_explanation"):
                suggestions.append(f"技术指标 {dim} 缺少通俗白话解读 (plain_explanation)")

    elif use_case == "earnings":
        for metric in ["revenue", "eps", "margins"]:
            val = payload.get(metric)
            if isinstance(val, dict) and not val.get("explanation"):
                suggestions.append(f"财报指标 {metric} 缺少通俗解读 (explanation)")

    is_readable = len(suggestions) == 0
    return is_readable, suggestions


class ComplianceGuardrail:
    """新手可读性与强制合规安全防线。"""

    def __init__(
        self,
        default_disclaimer: str = DEFAULT_DISCLAIMER,
        sanitize_terms: bool = True,
    ) -> None:
        self._default_disclaimer = default_disclaimer
        self._sanitize_terms = sanitize_terms

    def process_envelope(self, envelope: ResearchEnvelope) -> ResearchEnvelope:
        """对输出信封执行全链路合规处理与脱敏。"""
        payload = dict(envelope.payload)

        # 1. 财报用例缺失字段标准化
        if envelope.use_case == "earnings":
            payload = normalize_missing_earnings_fields(payload, envelope.data_gaps)

        # 2. 违禁承诺性词汇脱敏
        summary = envelope.summary
        if self._sanitize_terms:
            summary = sanitize_forbidden_terms(summary)
            payload = sanitize_forbidden_terms_in_obj(payload)

        # 3. 新手可读性校验
        _, suggestions = check_novice_readability(payload, envelope.use_case)
        if suggestions:
            logger.debug(
                "Novice readability suggestions for symbol={sym}, use_case={uc}: {sug}",
                sym=envelope.symbol,
                uc=envelope.use_case,
                sug=suggestions,
            )

        # 4. 免责声明强制合规
        return envelope.model_copy(
            update={
                "summary": summary,
                "payload": payload,
                "disclaimer": self._default_disclaimer,
            }
        )
