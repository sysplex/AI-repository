"""M5 数字溯源校验引擎与 AI 输出防编造防御（T05），`CONTRACTS.md §1, §5` 与 `docs/08 §4.3`。

实现反向数字溯源比对：
1. 递归提取 AI 报告 payload 中声称的全部数值、百分比与价格；
2. 扁平化索引 facts/computed 事实上下文，建立高精度 Decimal 数值倒排索引；
3. 支持精准 source_field 路径校验与全量数值近似匹配（容差 <= 1e-4，支持小数与百分比等价换算）；
4. 严格拦截编造虚假数字、非法 source 路径、缺失字段猜测及投资保证性禁用词（如保本稳赚）。
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.modules.ai.exceptions import FactTracingError
from app.modules.ai.schemas import FactTracingResult, FactTracingViolation

__all__ = [
    "DEFAULT_BANNED_TERMS",
    "DEFAULT_EXEMPT_NUMBERS",
    "DEFAULT_TOLERANCE",
    "FactTracingEngine",
    "extract_numeric_facts",
    "extract_numbers_from_text",
    "resolve_path_value",
    "verify_fact_tracing",
]

DEFAULT_TOLERANCE: Decimal = Decimal("0.0001")

#: 金融合规禁用词（严禁绝对化与保本保收益承诺）
DEFAULT_BANNED_TERMS: list[str] = [
    "保证保本",
    "稳赚不赔",
    "保本保收益",
    "零风险保本",
    "100%赚钱",
    "100%稳赚",
    "保证翻倍",
    "无风险高收益",
    "绝不亏损",
    "内幕必涨",
    "包赚不亏",
]

#: 默认豁免校验的通用序数、标准交易周期日与年份常数
DEFAULT_EXEMPT_NUMBERS: set[Decimal] = {
    Decimal("0"),
    Decimal("1"),
    Decimal("2"),
    Decimal("3"),
    Decimal("4"),
    Decimal("5"),
    Decimal("10"),
    Decimal("20"),
    Decimal("50"),
    Decimal("60"),
    Decimal("100"),
    Decimal("200"),
    Decimal("252"),
    *(Decimal(str(year)) for year in range(2020, 2031)),
}

_NUMBER_REGEX = re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")


def resolve_path_value(data: dict[str, Any], path: str) -> Any:
    """按点分隔路径解析字典/列表中的属性值，不存在返回 None。"""
    if not path or not isinstance(data, dict):
        return None

    tokens = path.split(".")
    curr: Any = data
    for token in tokens:
        if isinstance(curr, dict) and token in curr:
            curr = curr[token]
        elif isinstance(curr, (list, tuple)) and token.isdigit():
            idx = int(token)
            if 0 <= idx < len(curr):
                curr = curr[idx]
            else:
                return None
        else:
            return None
    return curr


def to_decimal(val: Any) -> Decimal | None:
    """尝试将值转换为高精度 Decimal，失败返回 None。"""
    if isinstance(val, bool):
        return None
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    if isinstance(val, str):
        cleaned = val.replace(",", "").strip()
        is_pct = cleaned.endswith("%")
        if is_pct:
            cleaned = cleaned[:-1].strip()
        try:
            d = Decimal(cleaned)
            return d
        except InvalidOperation:
            return None
    return None


def extract_numbers_from_text(text: str) -> list[tuple[Decimal, str]]:
    """从文本中提取所有包含的数值与原始匹配字符串。"""
    if not text:
        return []
    results: list[tuple[Decimal, str]] = []
    for match in _NUMBER_REGEX.finditer(text):
        raw_match = match.group(0)
        dec = to_decimal(raw_match)
        if dec is not None:
            results.append((dec, raw_match))
    return results


def extract_numeric_facts(
    data: Any,
    prefix: str = "",
) -> list[tuple[Decimal, str]]:
    """递归遍历事实字典/列表，扁平化提取全部数值及其来源路径。"""
    results: list[tuple[Decimal, str]] = []
    if isinstance(data, dict):
        for k, v in data.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            results.extend(extract_numeric_facts(v, path))
    elif isinstance(data, (list, tuple)):
        for idx, item in enumerate(data):
            path = f"{prefix}.{idx}" if prefix else str(idx)
            results.extend(extract_numeric_facts(item, path))
    else:
        dec = to_decimal(data)
        if dec is not None:
            results.append((dec, prefix))
        elif isinstance(data, str):
            for num, _ in extract_numbers_from_text(data):
                results.append((num, prefix))
    return results


class FactTracingEngine:
    """AI 输出数字溯源与防编造校验引擎。"""

    def __init__(
        self,
        *,
        tolerance: Decimal = DEFAULT_TOLERANCE,
        banned_terms: list[str] | None = None,
        exempt_numbers: set[Decimal] | None = None,
    ) -> None:
        self.tolerance = tolerance
        self.banned_terms = banned_terms if banned_terms is not None else DEFAULT_BANNED_TERMS
        self.exempt_numbers = (
            exempt_numbers if exempt_numbers is not None else DEFAULT_EXEMPT_NUMBERS
        )

    def verify(
        self,
        payload: dict[str, Any] | str,
        facts: dict[str, Any],
        *,
        computed: dict[str, Any] | None = None,
        strict_paths: bool = True,
    ) -> FactTracingResult:
        """执行端到端数字溯源与合规校验。

        1. 构建事实库与计算指标的数值倒排索引；
        2. 扫描 payload 中是否存在保证性禁用词；
        3. 检查显式标注的 source_field / source_path 路径是否存在且数值相符；
        4. 递归检查 payload 中的所有数值能否在 facts 中溯源，杜绝编造幻觉。
        """
        combined_facts: dict[str, Any] = dict(facts)
        if computed:
            combined_facts["computed"] = computed

        # 1. 扁平化事实数值索引
        indexed_facts = extract_numeric_facts(combined_facts)

        violations: list[FactTracingViolation] = []

        # 2. 检查禁用词
        self._check_banned_terms(payload, violations)

        # 3. 递归溯源校验数值
        self._trace_payload(
            payload=payload,
            combined_facts=combined_facts,
            indexed_facts=indexed_facts,
            violations=violations,
            checked_tracker={"count": 0},
            strict_paths=strict_paths,
            path="$",
        )

        return FactTracingResult(
            valid=len(violations) == 0,
            violations=violations,
            checked_numbers_count=self._total_checked_count,
        )

    def verify_or_raise(
        self,
        payload: dict[str, Any] | str,
        facts: dict[str, Any],
        *,
        computed: dict[str, Any] | None = None,
    ) -> FactTracingResult:
        """执行校验并在发现违规时直接抛出 FactTracingError (HTTP 422)。"""
        res = self.verify(payload, facts, computed=computed)
        if not res.valid:
            viol_summaries = [
                f"{v.field_path}: {v.reason} ({v.claimed_value})" for v in res.violations
            ]
            summary_str = "; ".join(viol_summaries)
            n_viols = len(res.violations)
            msg = f"Fact tracing check failed: {n_viols} violation(s) detected: {summary_str}"
            raise FactTracingError(
                msg,
                details={
                    "violations": [v.model_dump() for v in res.violations],
                    "checked_numbers_count": res.checked_numbers_count,
                },
            )
        return res

    # -------------------------------------------------------------------------
    # 内部检测辅助方法
    # -------------------------------------------------------------------------

    def _check_banned_terms(
        self,
        data: Any,
        violations: list[FactTracingViolation],
        path: str = "$",
    ) -> None:
        """递归扫描文本中的非法保证性禁用词。"""
        if isinstance(data, str):
            for term in self.banned_terms:
                if term in data:
                    violations.append(
                        FactTracingViolation(
                            field_path=path,
                            claimed_value=term,
                            reason="banned_guarantee_term",
                        )
                    )
        elif isinstance(data, dict):
            for k, v in data.items():
                sub_path = f"{path}.{k}"
                self._check_banned_terms(k, violations, f"{sub_path}#key")
                self._check_banned_terms(v, violations, sub_path)
        elif isinstance(data, (list, tuple)):
            for idx, item in enumerate(data):
                self._check_banned_terms(item, violations, f"{path}[{idx}]")

    def _trace_payload(
        self,
        payload: Any,
        combined_facts: dict[str, Any],
        indexed_facts: list[tuple[Decimal, str]],
        violations: list[FactTracingViolation],
        checked_tracker: dict[str, int],
        strict_paths: bool,
        path: str,
    ) -> None:
        """递归遍历 payload 检验各数值是否能溯源到事实库。"""
        self._total_checked_count = checked_tracker.get("count", 0)

        # 1. 字典节点：特殊处理显式 source_field 声明
        if isinstance(payload, dict):
            source_path = payload.get("source_field") or payload.get("source_path")
            has_value = "value" in payload or "price" in payload or "metric_value" in payload

            if source_path and isinstance(source_path, str) and has_value:
                # 显式路径校验
                if "value" in payload:
                    claimed_val_raw = payload.get("value")
                elif "price" in payload:
                    claimed_val_raw = payload.get("price")
                else:
                    claimed_val_raw = payload.get("metric_value")

                self._verify_explicit_source_path(
                    claimed_val_raw=claimed_val_raw,
                    source_path=source_path,
                    combined_facts=combined_facts,
                    violations=violations,
                    checked_tracker=checked_tracker,
                    path=path,
                )
                return

            for k, v in payload.items():
                sub_path = f"{path}.{k}"
                self._trace_payload(
                    payload=v,
                    combined_facts=combined_facts,
                    indexed_facts=indexed_facts,
                    violations=violations,
                    checked_tracker=checked_tracker,
                    strict_paths=strict_paths,
                    path=sub_path,
                )
            return

        # 2. 列表节点
        if isinstance(payload, (list, tuple)):
            for idx, item in enumerate(payload):
                sub_path = f"{path}[{idx}]"
                self._trace_payload(
                    payload=item,
                    combined_facts=combined_facts,
                    indexed_facts=indexed_facts,
                    violations=violations,
                    checked_tracker=checked_tracker,
                    strict_paths=strict_paths,
                    path=sub_path,
                )
            return

        # 3. 基础数值节点 (int, float, Decimal)
        dec_val = to_decimal(payload)
        if dec_val is not None:
            if dec_val in self.exempt_numbers:
                return

            checked_tracker["count"] += 1
            self._total_checked_count = checked_tracker["count"]

            match_found = self._is_value_in_facts(dec_val, indexed_facts)
            if not match_found:
                violations.append(
                    FactTracingViolation(
                        field_path=path,
                        claimed_value=dec_val,
                        reason="untraced_number",
                    )
                )
            return

        # 4. 字符串节点中内嵌的数值（如 "Target price is 182.52"）
        if isinstance(payload, str):
            extracted = extract_numbers_from_text(payload)
            for dec, raw_sub in extracted:
                if dec in self.exempt_numbers:
                    continue

                checked_tracker["count"] += 1
                self._total_checked_count = checked_tracker["count"]

                match_found = self._is_value_in_facts(dec, indexed_facts)
                if not match_found:
                    violations.append(
                        FactTracingViolation(
                            field_path=f"{path}('{raw_sub}')",
                            claimed_value=dec,
                            reason="untraced_number",
                        )
                    )

    def _verify_explicit_source_path(
        self,
        claimed_val_raw: Any,
        source_path: str,
        combined_facts: dict[str, Any],
        violations: list[FactTracingViolation],
        checked_tracker: dict[str, int],
        path: str,
    ) -> None:
        """显式 source_path 的存在性与数值一致性校验。"""
        checked_tracker["count"] += 1
        self._total_checked_count = checked_tracker["count"]

        fact_val = resolve_path_value(combined_facts, source_path)
        if fact_val is None:
            violations.append(
                FactTracingViolation(
                    field_path=f"{path}.source_field",
                    claimed_value=source_path,
                    reason="invalid_source_path",
                )
            )
            return

        dec_claimed = to_decimal(claimed_val_raw)
        dec_fact = to_decimal(fact_val)
        if dec_claimed is None or dec_fact is None:
            violations.append(
                FactTracingViolation(
                    field_path=f"{path}.value",
                    claimed_value=str(claimed_val_raw),
                    reason="untraced_number",
                )
            )
            return

        if not self._is_numeric_match(dec_claimed, dec_fact):
            violations.append(
                FactTracingViolation(
                    field_path=f"{path}.value",
                    claimed_value=dec_claimed,
                    reason="untraced_number",
                )
            )

    def _is_value_in_facts(
        self,
        claimed: Decimal,
        indexed_facts: list[tuple[Decimal, str]],
    ) -> bool:
        """检查声称的数值是否存在于事实倒排索引中（含等价百分比转换）。"""
        return any(self._is_numeric_match(claimed, fact_val) for fact_val, _ in indexed_facts)

    def _is_numeric_match(self, a: Decimal, b: Decimal) -> bool:
        """高精度数值比对：直接绝对差、百分比乘除100等价匹配。"""
        # 1. 直接数值容差
        if abs(a - b) <= self.tolerance:
            return True

        # 2. 百分比等价: a 是 15 (15%), b 是 0.15
        if abs(a - (b * Decimal(100))) <= self.tolerance:
            return True

        # 3. 百分比等价: a 是 0.15, b 是 15 (15%)
        return abs((a * Decimal(100)) - b) <= self.tolerance


def verify_fact_tracing(
    payload: dict[str, Any] | str,
    facts: dict[str, Any],
    *,
    computed: dict[str, Any] | None = None,
    tolerance: Decimal = DEFAULT_TOLERANCE,
) -> FactTracingResult:
    """快捷执行数字溯源与防编造校验。"""
    engine = FactTracingEngine(tolerance=tolerance)
    return engine.verify(payload, facts, computed=computed)
