"""M6-T05 新手可读性与强制合规防线单元测试。

验证：
1. 强制免责声明注入（ensure_compliance_disclaimer）；
2. 违禁承诺性盈利词汇脱敏（sanitize_forbidden_terms）；
3. 财报缺失指标与指引标准化为“数据缺失”（normalize_missing_earnings_fields）；
4. 新手通俗可读性检查（check_novice_readability）；
5. ComplianceGuardrail 综合防御守卫。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.modules.research.compliance import (
    DEFAULT_DISCLAIMER,
    MISSING_DATA_PLACEHOLDER,
    ComplianceGuardrail,
    check_novice_readability,
    ensure_compliance_disclaimer,
    normalize_missing_earnings_fields,
    sanitize_forbidden_terms,
    sanitize_forbidden_terms_in_obj,
)
from app.modules.research.schemas import ResearchEnvelope


@pytest.fixture
def sample_envelope() -> ResearchEnvelope:
    return ResearchEnvelope(
        use_case="research",
        symbol="AAPL",
        as_of=date(2026, 1, 15),
        summary="该股票保本稳赚，零风险买入。",
        payload={
            "summary": "必涨翻倍承诺，只赚不赔。",
            "beginner_takeaway": ["新手要点一"],
        },
        disclaimer="旧的无效免责声明",
    )


@pytest.mark.unit
class TestEnsureComplianceDisclaimer:
    """测试强制免责声明。"""

    def test_replaces_invalid_disclaimer_on_envelope(
        self, sample_envelope: ResearchEnvelope
    ) -> None:
        updated = ensure_compliance_disclaimer(sample_envelope)
        assert isinstance(updated, ResearchEnvelope)
        assert updated.disclaimer == DEFAULT_DISCLAIMER

    def test_already_compliant_envelope_unchanged(self, sample_envelope: ResearchEnvelope) -> None:
        compliant = sample_envelope.model_copy(update={"disclaimer": DEFAULT_DISCLAIMER})
        res = ensure_compliance_disclaimer(compliant)
        assert res is compliant

    def test_dict_disclaimer_injection(self) -> None:
        data = {"symbol": "AAPL", "summary": "test"}
        res = ensure_compliance_disclaimer(data)
        assert isinstance(res, dict)
        assert res["disclaimer"] == DEFAULT_DISCLAIMER

    def test_non_dict_non_envelope_passthrough(self) -> None:
        val: Any = 12345
        assert ensure_compliance_disclaimer(val) == 12345


@pytest.mark.unit
class TestForbiddenTermsSanitization:
    """测试承诺性盈利词汇智能脱敏。"""

    def test_sanitize_forbidden_terms_in_text(self) -> None:
        raw = "此标的保本稳赚，可以说是零风险且必涨的无风险投资，稳赢翻倍承诺，只赚不赔。"
        sanitized = sanitize_forbidden_terms(raw)
        assert "保本" not in sanitized
        assert "稳赚" not in sanitized
        assert "零风险" not in sanitized
        assert "必涨" not in sanitized
        assert "追求资本保值" in sanitized
        assert "具备确定性潜力" in sanitized
        assert "低风险" in sanitized

    def test_empty_string_passthrough(self) -> None:
        assert sanitize_forbidden_terms("") == ""

    def test_sanitize_forbidden_terms_in_nested_structure(self) -> None:
        nested = {
            "title": "稳赚策略",
            "points": ["保本收益", "零风险操作"],
            "meta": {"note": "只赚不赔", "count": 10},
        }
        sanitized = sanitize_forbidden_terms_in_obj(nested)
        assert sanitized["title"] == "具备确定性潜力策略"
        assert sanitized["points"] == ["追求资本保值收益", "低风险操作"]
        assert sanitized["meta"]["note"] == "盈亏比较优"
        assert sanitized["meta"]["count"] == 10


@pytest.mark.unit
class TestNormalizeMissingEarningsFields:
    """测试财报缺失字段标准化。"""

    def test_complete_earnings_payload_kept(self) -> None:
        payload = {
            "revenue": {
                "actual": Decimal("100"),
                "expected": Decimal("95"),
                "surprise_pct": Decimal("5.26"),
                "explanation": "超预期增长",
            },
            "eps": {
                "actual": "1.50",
                "expected": "1.40",
                "surprise_pct": "7.14",
                "explanation": "超预期",
            },
            "margins": {
                "actual": "25%",
                "expected": "24%",
                "surprise_pct": "1%",
                "explanation": "改善",
            },
            "guidance": "预计下季度营收增长 10%",
            "management_commentary": ["执行效率提升"],
        }
        res = normalize_missing_earnings_fields(payload)
        assert res["revenue"]["actual"] == Decimal("100")
        assert res["guidance"] == "预计下季度营收增长 10%"
        assert res["management_commentary"] == ["执行效率提升"]

    def test_missing_subfields_standardized_to_placeholder(self) -> None:
        payload: dict[str, Any] = {
            "revenue": {
                "actual": None,
                "expected": "null",
                "surprise_pct": "   ",
                "explanation": "",
            },
            "eps": None,
            "guidance": "无",
            "management_commentary": [],
        }
        res = normalize_missing_earnings_fields(
            payload, missing_fields=["earnings.guidance", "earnings.management_commentary"]
        )

        # revenue 子字段全部填补为“数据缺失”
        assert res["revenue"]["actual"] == MISSING_DATA_PLACEHOLDER
        assert res["revenue"]["expected"] == MISSING_DATA_PLACEHOLDER
        assert res["revenue"]["surprise_pct"] == MISSING_DATA_PLACEHOLDER
        assert res["revenue"]["explanation"] == "revenue 数据缺失"

        # None 指标整体填补
        assert res["eps"]["actual"] == MISSING_DATA_PLACEHOLDER
        assert res["margins"]["actual"] == MISSING_DATA_PLACEHOLDER

        # guidance 和 commentary 填补
        assert res["guidance"] == MISSING_DATA_PLACEHOLDER
        assert res["management_commentary"] == [MISSING_DATA_PLACEHOLDER]


@pytest.mark.unit
class TestCheckNoviceReadability:
    """测试新手可读性校验与通俗解释覆盖。"""

    def test_research_use_case_readability(self) -> None:
        valid_payload = {
            "summary": "业务简明概括",
            "beginner_takeaway": ["重点一：现金流充沛", "重点二：护城河稳固"],
        }
        ok, sug = check_novice_readability(valid_payload, "research")
        assert ok is True
        assert len(sug) == 0

        invalid_payload = {"summary": "仅有概要"}
        ok, sug = check_novice_readability(invalid_payload, "research")
        assert ok is False
        assert any("beginner_takeaway" in s for s in sug)

    def test_buy_decision_use_case_readability(self) -> None:
        valid_payload = {"beginner_summary": "建议当前价格观望"}
        ok, sug = check_novice_readability(valid_payload, "buy_decision")
        assert ok is True

        invalid_payload = {"verdict": "buy"}
        ok, sug = check_novice_readability(invalid_payload, "buy_decision")
        assert ok is False
        assert any("beginner_summary" in s for s in sug)

    def test_technical_use_case_readability(self) -> None:
        valid_payload = {
            "summary": "走势良好",
            "trend": {"value": "bullish", "plain_explanation": "均线呈现向上多头排列"},
            "rsi": {"value": "55", "plain_explanation": "买卖处于健康温和区间"},
        }
        ok, _ = check_novice_readability(valid_payload, "technical")
        assert ok is True

        invalid_payload = {
            "summary": "走势良好",
            "trend": {"value": "bullish", "plain_explanation": ""},
        }
        ok, sug = check_novice_readability(invalid_payload, "technical")
        assert ok is False
        assert any("trend 缺少通俗白话解读" in s for s in sug)

    def test_earnings_use_case_readability(self) -> None:
        invalid_payload = {
            "summary": "季报概览",
            "revenue": {"actual": "100B", "explanation": ""},
        }
        ok, sug = check_novice_readability(invalid_payload, "earnings")
        assert ok is False
        assert any("revenue 缺少通俗解读" in s for s in sug)


@pytest.mark.unit
class TestComplianceGuardrailClass:
    """测试综合合规守卫 ComplianceGuardrail。"""

    def test_process_envelope_full_compliance(self, sample_envelope: ResearchEnvelope) -> None:
        guardrail = ComplianceGuardrail()
        processed = guardrail.process_envelope(sample_envelope)

        # 1. 免责声明强制重置为法定文案
        assert processed.disclaimer == DEFAULT_DISCLAIMER

        # 2. 收益承诺词汇脱敏
        assert "保本" not in processed.summary
        assert "稳赚" not in processed.summary
        assert "追求资本保值" in processed.summary
        assert "必涨" not in processed.payload["summary"]

    def test_process_earnings_envelope_normalizes_missing(self) -> None:
        earnings_envelope = ResearchEnvelope(
            use_case="earnings",
            symbol="AAPL",
            as_of=date(2026, 1, 15),
            summary="财报简讯",
            payload={
                "revenue": {"actual": None, "explanation": "收入详情"},
                "guidance": None,
                "management_commentary": [],
            },
            data_gaps=["earnings.guidance"],
        )

        guardrail = ComplianceGuardrail()
        processed = guardrail.process_envelope(earnings_envelope)

        assert processed.payload["revenue"]["actual"] == MISSING_DATA_PLACEHOLDER
        assert processed.payload["guidance"] == MISSING_DATA_PLACEHOLDER
        assert processed.payload["management_commentary"] == [MISSING_DATA_PLACEHOLDER]
