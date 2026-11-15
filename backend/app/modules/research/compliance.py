"""M6 & M7 AI 研究用例新手可读性与强制合规防线，`CONTRACTS.md §5`。

实现：
1. 强制合规免责声明注入；
2. 违禁承诺性盈利词汇（保本、稳赚、零风险等）智能脱敏与审计识别；
3. 财报指引与财务三表缺失项标准化标注为“数据缺失”；
4. 新手可读性校验与专业术语白话解读审查（全 7 大用例支持）；
5. 论文破裂条件（thesis_breakers）可监控性强校验（M10 可消费路径）；
6. 投资组合资产配置权重守恒与代码量化派生防篡改防线；
7. ``ComplianceGuardrail`` 统一合规守卫类。
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.logging import get_logger
from app.modules.research.exceptions import ComplianceViolationError
from app.modules.research.schemas import ResearchEnvelope

logger = get_logger("research.compliance")

__all__ = [
    "DEFAULT_DISCLAIMER",
    "FORBIDDEN_PROFIT_TERMS",
    "MISSING_DATA_PLACEHOLDER",
    "REPLACEMENT_MAP",
    "SUPPORTED_THESIS_BREAKER_DATA_FIELDS",
    "ComplianceGuardrail",
    "assert_envelope_compliance",
    "check_novice_readability",
    "contains_forbidden_terms",
    "ensure_compliance_disclaimer",
    "normalize_missing_earnings_fields",
    "sanitize_forbidden_terms",
    "sanitize_forbidden_terms_in_obj",
    "validate_compare_ranking",
    "validate_portfolio_weights",
    "validate_thesis_breakers",
    "verify_envelope_compliance",
]

DEFAULT_DISCLAIMER: str = "本内容仅供研究与学习，不构成投资建议"
MISSING_DATA_PLACEHOLDER: str = "数据缺失"

# 禁止虚假宣传与收益承诺词汇表（按词长降序排列，优先匹配长词组）
REPLACEMENT_MAP: dict[str, str] = {
    "稳赚不赔": "盈亏比较优",
    "保证保本": "追求资本保值",
    "保本保收益": "追求稳健收益",
    "零风险保本": "低风险保值",
    "100%稳赚": "高确定性胜率",
    "100%赚钱": "高确定性胜率",
    "保证翻倍": "具备增值潜力",
    "无风险高收益": "良好风险收益比",
    "只赚不赔": "盈亏比较优",
    "翻倍承诺": "长期增值空间",
    "绝对收益": "超额收益潜力",
    "包赚不亏": "具备胜率优势",
    "内幕必涨": "利好支撑上涨潜力",
    "绝不亏损": "注重下行保护",
    "保证收益": "预期收益潜力",
    "承诺保本": "追求资本保值",
    "零风险": "低风险",
    "无风险": "低风险",
    "保本": "追求资本保值",
    "稳赚": "具备确定性潜力",
    "稳赢": "胜率较高",
    "必涨": "具备上涨潜力",
}

FORBIDDEN_PROFIT_TERMS: list[str] = list(REPLACEMENT_MAP.keys())

#: 论文破裂条件支持的可观测数据源点分路径白名单（供 M10 调度器持续监控）
SUPPORTED_THESIS_BREAKER_DATA_FIELDS: set[str] = {
    "fundamentals.net_margin",
    "fundamentals.pe_trailing",
    "fundamentals.revenue_growth",
    "fundamentals.debt_to_equity",
    "fundamentals.roe",
    "fundamentals.pe_forward",
    "fundamentals.dividend_yield",
    "quote.price",
    "quote.volume",
    "technical.support",
    "technical.resistance",
}


def _to_decimal_val(val: Any) -> Decimal | None:
    """尝试将值转换为 Decimal，失败返回 None。"""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, Decimal):
        return val
    try:
        cleaned = str(val).replace("%", "").replace(",", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError, TypeError):
        return None


def contains_forbidden_terms(obj: Any) -> list[str]:
    """检查对象中是否存在任何金融合规禁用词，返回匹配到的禁用词列表（去重排序）。"""
    found: set[str] = set()

    def _scan(text: str) -> None:
        for term in FORBIDDEN_PROFIT_TERMS:
            if term in text:
                found.add(term)

    if isinstance(obj, str):
        _scan(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                _scan(k)
            found.update(contains_forbidden_terms(v))
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            found.update(contains_forbidden_terms(item))
    elif hasattr(obj, "__dict__"):
        for v in vars(obj).values():
            found.update(contains_forbidden_terms(v))

    return sorted(list(found))


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


def ensure_compliance_disclaimer(envelope_or_dict: Any) -> Any:
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


def validate_thesis_breakers(breakers: Any) -> tuple[bool, list[str]]:
    """校验 F5 长期持有论文破裂条件的可监控性与结构化完整性。

    验收标准：
    1. 破裂条件数量 >= 3 且 <= 10；
    2. 每项均包含 condition、metric、threshold、data_field；
    3. data_field 必须属于可观测的系统已知路径（SUPPORTED_THESIS_BREAKER_DATA_FIELDS）。

    Returns:
        tuple[bool, list[str]]: (是否合规达标, 违规说明列表)
    """
    issues: list[str] = []

    if not isinstance(breakers, list):
        return False, ["thesis_breakers 必须为列表结构"]

    if len(breakers) < 3:
        issues.append(
            f"thesis_breakers 数量不足：至少需要 3 条监控条件，当前仅有 {len(breakers)} 条"
        )
    elif len(breakers) > 10:
        issues.append(
            f"thesis_breakers 数量超限：最多支持 10 条监控条件，当前有 {len(breakers)} 条"
        )

    for idx, item in enumerate(breakers, start=1):
        if isinstance(item, dict):
            cond = item.get("condition")
            metric = item.get("metric")
            threshold = item.get("threshold")
            data_field = item.get("data_field")
        elif hasattr(item, "data_field"):
            cond = getattr(item, "condition", None)
            metric = getattr(item, "metric", None)
            threshold = getattr(item, "threshold", None)
            data_field = getattr(item, "data_field", None)
        else:
            issues.append(f"第 {idx} 条破裂条件格式非法，必须为字典或 ThesisBreakerItem")
            continue

        if not cond or not str(cond).strip():
            issues.append(f"第 {idx} 条破裂条件缺少 condition 白话描述")
        if not metric or not str(metric).strip():
            issues.append(f"第 {idx} 条破裂条件缺少 metric 监控指标名称")
        if not threshold or not str(threshold).strip():
            issues.append(f"第 {idx} 条破裂条件缺少 threshold 触发阈值")

        if not data_field or not str(data_field).strip():
            issues.append(f"第 {idx} 条破裂条件缺少 data_field 数据字段路径")
        elif str(data_field).strip() not in SUPPORTED_THESIS_BREAKER_DATA_FIELDS:
            issues.append(
                f"第 {idx} 条破裂条件的 data_field '{data_field}' 不在系统支持的监控路径列表中"
            )

    return len(issues) == 0, issues


def validate_portfolio_weights(
    payload: dict[str, Any],
    computed: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """校验 F8 投资组合配置权重守恒与代码量化结果一致性（防 AI 编造或篡改）。

    验收标准：
    1. 各标的权重之和与现金比例严格满足：sum(weight_pct) + cash_pct == 100.00% (容差 <= 0.01)；
    2. 各标的金额之和与现金金额满足金额守恒（容差 <= 0.05）；
    3. 若提供了 computed 块，AI 输出的标的权重、现金比例及总额必须与代码计算结果 100% 保持一致。

    Returns:
        tuple[bool, list[str]]: (是否合规通过, 违规说明列表)
    """
    issues: list[str] = []
    allocations = payload.get("allocations")

    if not isinstance(allocations, list) or len(allocations) < 2:
        return False, ["投资组合缺少 allocations 资产配置明细（至少需要 2 个标的）"]

    cash_pct = _to_decimal_val(payload.get("cash_pct"))
    if cash_pct is None:
        issues.append("投资组合缺少 cash_pct 现金比例")

    weights: list[Decimal] = []
    for idx, a in enumerate(allocations, start=1):
        raw_w = a.get("weight_pct") if isinstance(a, dict) else getattr(a, "weight_pct", None)
        w = _to_decimal_val(raw_w)
        if w is None:
            issues.append(f"第 {idx} 个标的缺少 weight_pct 配置权重")
        else:
            weights.append(w)

    if cash_pct is not None and len(weights) == len(allocations):
        total_weight = sum(weights) + cash_pct
        if abs(total_weight - Decimal("100.00")) > Decimal("0.01"):
            issues.append(
                f"资产配置权重与现金比例不守恒：各标的权重合计 {sum(weights)}%，"
                f"现金比例 {cash_pct}%，总计 {total_weight}% != 100.00%"
            )

    # 金额守恒校验
    amount = _to_decimal_val(payload.get("amount"))
    cash_amount = _to_decimal_val(payload.get("cash_amount"))
    if amount is not None and cash_amount is not None:
        amounts: list[Decimal] = []
        for a in allocations:
            raw_amt = (
                a.get("allocated_amount")
                if isinstance(a, dict)
                else getattr(a, "allocated_amount", None)
            )
            amt = _to_decimal_val(raw_amt)
            if amt is not None:
                amounts.append(amt)

        if len(amounts) == len(allocations):
            total_allocated = sum(amounts) + cash_amount
            if abs(total_allocated - amount) > Decimal("0.05"):
                issues.append(
                    f"资产配置金额不守恒：各标的金额合计 {sum(amounts)}，"
                    f"现金金额 {cash_amount}，总计 {total_allocated} != {amount}"
                )

    # 与代码量化引擎 computed 块比对（防 AI 篡改）
    if computed and isinstance(computed, dict):
        exp_cash_pct = _to_decimal_val(computed.get("cash_pct"))
        if exp_cash_pct is not None and cash_pct is not None and cash_pct != exp_cash_pct:
            issues.append(f"现金比例被篡改：AI 输出为 {cash_pct}%，代码量化计算为 {exp_cash_pct}%")

        exp_amt = _to_decimal_val(computed.get("amount"))
        if exp_amt is not None and amount is not None and amount != exp_amt:
            issues.append(f"总金额被篡改：AI 输出为 {amount}，代码量化计算为 {exp_amt}")

        comp_allocs = computed.get("allocations")
        if isinstance(comp_allocs, list):
            exp_weights: dict[str, Decimal] = {}
            for ca in comp_allocs:
                if isinstance(ca, dict):
                    sym = str(ca.get("symbol", "")).upper()
                    w = _to_decimal_val(ca.get("weight_pct"))
                    if sym and w is not None:
                        exp_weights[sym] = w

            for a in allocations:
                sym = str(
                    a.get("symbol", "") if isinstance(a, dict) else getattr(a, "symbol", "")
                ).upper()
                w = _to_decimal_val(
                    a.get("weight_pct") if isinstance(a, dict) else getattr(a, "weight_pct", None)
                )
                if sym not in exp_weights:
                    issues.append(f"标的 {sym} 不在代码量化优化标的池中")
                elif w is not None and exp_weights[sym] != w:
                    issues.append(
                        f"标的 {sym} 权重被篡改：AI 输出为 {w}%，代码量化计算为 {exp_weights[sym]}%"
                    )

    return len(issues) == 0, issues


def validate_compare_ranking(
    payload: dict[str, Any],
    computed: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """校验 F4 多股票横向对比综合排名与代码量化分位结果一致性（防篡改）。"""
    issues: list[str] = []
    ranking = payload.get("ranking")

    if not isinstance(ranking, list) or len(ranking) < 2:
        return False, ["股票对比缺少 ranking 排名列表（至少需要 2 个标的）"]

    if computed and isinstance(computed, dict):
        exp_ranking = computed.get("ranking")
        if isinstance(exp_ranking, list):
            if len(ranking) != len(exp_ranking):
                issues.append(
                    f"综合排名标的数量不一致：AI 输出 {len(ranking)} 个，"
                    f"代码量化计算为 {len(exp_ranking)} 个"
                )
            else:
                pairs = zip(ranking, exp_ranking, strict=True)
                for idx, (r_ai, r_exp) in enumerate(pairs, start=1):
                    sym_ai = str(
                        r_ai.get("symbol", "")
                        if isinstance(r_ai, dict)
                        else getattr(r_ai, "symbol", "")
                    ).upper()
                    sym_exp = str(r_exp.get("symbol", "")).upper()
                    if sym_ai != sym_exp:
                        issues.append(
                            f"第 {idx} 名标的被篡改：AI 输出为 {sym_ai}，代码计算为 {sym_exp}"
                        )

                    rank_ai = (
                        r_ai.get("rank") if isinstance(r_ai, dict) else getattr(r_ai, "rank", None)
                    )
                    rank_exp = r_exp.get("rank")
                    if rank_ai is not None and rank_exp is not None and rank_ai != rank_exp:
                        issues.append(
                            f"标的 {sym_ai} 排名被篡改：AI 输出第 {rank_ai} 名，"
                            f"代码计算为第 {rank_exp} 名"
                        )

                    score_ai = _to_decimal_val(
                        r_ai.get("total_score")
                        if isinstance(r_ai, dict)
                        else getattr(r_ai, "total_score", None)
                    )
                    score_exp = _to_decimal_val(r_exp.get("total_score"))
                    if score_ai is not None and score_exp is not None and score_ai != score_exp:
                        issues.append(
                            f"标的 {sym_ai} 综合得分被篡改：AI 输出为 {score_ai}，"
                            f"代码计算为 {score_exp}"
                        )

    return len(issues) == 0, issues


def check_novice_readability(
    payload: dict[str, Any],
    use_case: str,
) -> tuple[bool, list[str]]:
    """检查用例返回内容是否具备新手可读性与必要通俗解释（覆盖 7 大用例）。

    Returns:
        tuple[bool, list[str]]: (是否达标, 改进建议/警告列表)
    """
    suggestions: list[str] = []

    # 1. 通用检查：是否存在新手总结/通俗要点字段
    has_beginner_summary = bool(
        payload.get("beginner_summary")
        or payload.get("summary")
        or payload.get("beginner_takeaway")
        or payload.get("short_term_outlook")
        or payload.get("better_entry_note")
        or payload.get("rationale")
        or payload.get("thesis")
    )
    if not has_beginner_summary:
        suggestions.append("缺少新手专属总结 (beginner_summary / beginner_takeaway / rationale)")

    # 2. 各用例专属通俗解读审查
    if use_case == "research":
        takeaways = payload.get("beginner_takeaway")
        if not takeaways or not isinstance(takeaways, list) or len(takeaways) == 0:
            suggestions.append("股票研究报告缺少新手核心要点 (beginner_takeaway)")

    elif use_case == "buy_decision":
        if not (payload.get("beginner_summary") or payload.get("better_entry_note")):
            suggestions.append(
                "买入决策缺少新手决策通俗总结 (beginner_summary / better_entry_note)"
            )

    elif use_case == "technical":
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

    elif use_case == "compare":
        dim_notes = payload.get("dimension_notes")
        if not isinstance(dim_notes, dict):
            suggestions.append("股票横向对比缺少 8 大维度定性对比说明 (dimension_notes)")
        else:
            for dim in [
                "growth",
                "margin",
                "debt",
                "valuation",
                "moat",
                "risk",
                "dividend",
                "long_term",
            ]:
                if not dim_notes.get(dim) or not str(dim_notes.get(dim)).strip():
                    suggestions.append(f"股票横向对比缺少 {dim} 维度定性对比说明")

        fits = payload.get("fit_by_investor")
        if not fits or not isinstance(fits, list) or len(fits) == 0:
            suggestions.append("股票横向对比缺少适合与不适合投资人群画像 (fit_by_investor)")

    elif use_case == "long_term":
        pillars = payload.get("pillars")
        if not isinstance(pillars, dict):
            suggestions.append("长期持有价值缺少 7 大核心支柱评估结果 (pillars)")
        else:
            for p in [
                "moat",
                "leadership",
                "demand_stability",
                "pricing_power",
                "innovation",
                "financial_strength",
                "market_size",
            ]:
                pval = pillars.get(p)
                if isinstance(pval, dict):
                    if not pval.get("reason") or not str(pval.get("reason")).strip():
                        suggestions.append(f"长期持有核心支柱 {p} 缺少定性依据说明 (reason)")
                elif hasattr(pval, "reason"):
                    if not getattr(pval, "reason", None):
                        suggestions.append(f"长期持有核心支柱 {p} 缺少定性依据说明 (reason)")
                else:
                    suggestions.append(f"长期持有核心支柱 {p} 评估缺失")

        breakers = payload.get("thesis_breakers")
        ok_breakers, breaker_issues = validate_thesis_breakers(breakers)
        if not ok_breakers:
            suggestions.extend(breaker_issues)

    elif use_case == "portfolio":
        if not payload.get("risk_notes") or not str(payload.get("risk_notes")).strip():
            suggestions.append("投资组合建议缺少组合风险提示与对冲说明 (risk_notes)")
        if (
            not payload.get("rebalance_suggestion")
            or not str(payload.get("rebalance_suggestion")).strip()
        ):
            suggestions.append("投资组合建议缺少动态再平衡建议 (rebalance_suggestion)")

        allocs = payload.get("allocations")
        if isinstance(allocs, list):
            for a in allocs:
                sym = a.get("symbol") if isinstance(a, dict) else getattr(a, "symbol", "")
                reason = a.get("reason") if isinstance(a, dict) else getattr(a, "reason", "")
                if not reason or not str(reason).strip():
                    suggestions.append(f"标的 {sym} 配置项缺少战略定位与理由说明 (reason)")

    is_readable = len(suggestions) == 0
    return is_readable, suggestions


def verify_envelope_compliance(
    envelope: ResearchEnvelope,
    computed: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """全面校验输出信封的合规性（包括破裂条件有效性、量化一致性防篡改、禁用词、新手可读性）。

    Returns:
        tuple[bool, list[str]]: (是否合规通过, 违规事项列表)
    """
    issues: list[str] = []
    payload = envelope.payload
    uc = envelope.use_case

    # 1. 禁用词检查（严禁未脱敏的违禁收益承诺词）
    forbidden = contains_forbidden_terms(envelope.summary)
    forbidden.extend(contains_forbidden_terms(payload))
    if forbidden:
        deduped = sorted(list(set(forbidden)))
        issues.append(f"包含金融合规禁用词: {', '.join(deduped)}")

    # 2. 用例专属防篡改与完整性校验
    if uc == "long_term":
        breakers = payload.get("thesis_breakers")
        ok_b, b_issues = validate_thesis_breakers(breakers)
        if not ok_b:
            issues.extend(b_issues)
    elif uc == "portfolio":
        ok_p, p_issues = validate_portfolio_weights(payload, computed=computed)
        if not ok_p:
            issues.extend(p_issues)
    elif uc == "compare":
        ok_c, c_issues = validate_compare_ranking(payload, computed=computed)
        if not ok_c:
            issues.extend(c_issues)

    # 3. 新手可读性校验
    _, r_issues = check_novice_readability(payload, uc)
    if r_issues:
        issues.extend(r_issues)

    return len(issues) == 0, issues


def assert_envelope_compliance(
    envelope: ResearchEnvelope,
    computed: dict[str, Any] | None = None,
) -> None:
    """断言信封完全合规，若存在违规项直接抛出 ComplianceViolationError (HTTP 422)。"""
    ok, issues = verify_envelope_compliance(envelope, computed=computed)
    if not ok:
        raise ComplianceViolationError(
            f"合规防线校验失败: {'; '.join(issues)}",
            details={
                "symbol": envelope.symbol,
                "use_case": envelope.use_case,
                "issues": issues,
            },
        )


class ComplianceGuardrail:
    """新手可读性与强制合规安全防线。"""

    def __init__(
        self,
        default_disclaimer: str = DEFAULT_DISCLAIMER,
        sanitize_terms: bool = True,
        enforce_tamper_protection: bool = False,
    ) -> None:
        self._default_disclaimer = default_disclaimer
        self._sanitize_terms = sanitize_terms
        self._enforce_tamper_protection = enforce_tamper_protection

    def process_envelope(
        self,
        envelope: ResearchEnvelope,
        computed: dict[str, Any] | None = None,
        enforce_tamper_protection: bool | None = None,
    ) -> ResearchEnvelope:
        """对输出信封执行全链路合规处理与脱敏。"""
        payload = dict(envelope.payload)
        should_enforce = (
            enforce_tamper_protection
            if enforce_tamper_protection is not None
            else self._enforce_tamper_protection
        )

        # 1. 财报用例缺失字段标准化
        if envelope.use_case == "earnings":
            payload = normalize_missing_earnings_fields(payload, envelope.data_gaps)

        # 2. 违禁承诺性词汇脱敏
        summary = envelope.summary
        if self._sanitize_terms:
            summary = sanitize_forbidden_terms(summary)
            payload = sanitize_forbidden_terms_in_obj(payload)

        # 3. 组装待审计信封
        temp_envelope = envelope.model_copy(
            update={
                "summary": summary,
                "payload": payload,
                "disclaimer": self._default_disclaimer,
            }
        )

        # 4. 新手可读性与防篡改审计
        if should_enforce:
            assert_envelope_compliance(temp_envelope, computed=computed)
        else:
            _, issues = verify_envelope_compliance(temp_envelope, computed=computed)
            if issues:
                logger.debug(
                    "Compliance audit advisory for symbol={sym}, use_case={uc}: {issues}",
                    sym=envelope.symbol,
                    uc=envelope.use_case,
                    issues=issues,
                )

        # 5. 返回合规信封
        return temp_envelope
