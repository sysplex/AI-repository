"""M7-T05 论文破裂条件监控元数据与确定性防篡改合规防线单元测试。

验证：
1. 长期持有论文破裂条件可监控性强校验（validate_thesis_breakers）；
2. 投资组合资产配置权重与金额守恒校验（validate_portfolio_weights）；
3. 投资组合防 AI 篡改防线（对比 computed 块）；
4. 股票横向对比综合排名与得分防篡改防线（validate_compare_ranking）；
5. M7 三大用例的新手通俗可读性校验（check_novice_readability）；
6. 扩展的金融收益承诺禁用词检出与脱敏（contains_forbidden_terms）；
7. ComplianceGuardrail 综合防御与 ComplianceViolationError 拦截。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.modules.research.compliance import (
    DEFAULT_DISCLAIMER,
    SUPPORTED_THESIS_BREAKER_DATA_FIELDS,
    ComplianceGuardrail,
    assert_envelope_compliance,
    check_novice_readability,
    contains_forbidden_terms,
    sanitize_forbidden_terms_in_obj,
    validate_compare_ranking,
    validate_portfolio_weights,
    validate_thesis_breakers,
    verify_envelope_compliance,
)
from app.modules.research.exceptions import ComplianceViolationError
from app.modules.research.schemas import ResearchEnvelope, ThesisBreakerItem


@pytest.fixture
def valid_thesis_breakers() -> list[dict[str, str]]:
    """3 条完全合法的论文破裂条件。"""
    return [
        {
            "condition": "净利润率连续两个季度低于20%",
            "metric": "net_margin",
            "threshold": "< 0.20",
            "data_field": "fundamentals.net_margin",
        },
        {
            "condition": "市盈率超过45倍严重透支成长预期",
            "metric": "pe_trailing",
            "threshold": "> 45.0",
            "data_field": "fundamentals.pe_trailing",
        },
        {
            "condition": "股价跌破200日关键牛熊支撑位",
            "metric": "support",
            "threshold": "< 160.00",
            "data_field": "technical.support",
        },
    ]


@pytest.fixture
def valid_portfolio_payload() -> dict[str, Any]:
    """完全合规的投资组合 Payload。"""
    return {
        "amount": Decimal("100000.00"),
        "allocations": [
            {
                "symbol": "AAPL",
                "weight_pct": Decimal("40.00"),
                "allocated_amount": Decimal("40000.00"),
                "reason": "消费电子护城河与现金流基石",
            },
            {
                "symbol": "MSFT",
                "weight_pct": Decimal("35.00"),
                "allocated_amount": Decimal("35000.00"),
                "reason": "企业级云与AI生产力双飞轮",
            },
            {
                "symbol": "GOOG",
                "weight_pct": Decimal("15.00"),
                "allocated_amount": Decimal("15000.00"),
                "reason": "广告估值防守与长远算力壁垒",
            },
        ],
        "cash_pct": Decimal("10.00"),
        "cash_amount": Decimal("10000.00"),
        "rationale": "均衡布局核心科技白马并保留10%现金缓冲",
        "risk_notes": "需关注科技行业宏观逆风与反垄断监管变化",
        "rebalance_suggestion": "建议每半年检视一次，偏离度超5%执行再平衡",
    }


@pytest.fixture
def valid_portfolio_computed() -> dict[str, Any]:
    """来自定量引擎的确定性投资组合计算块。"""
    return {
        "amount": Decimal("100000.00"),
        "allocations": [
            {
                "symbol": "AAPL",
                "weight_pct": Decimal("40.00"),
                "allocated_amount": Decimal("40000.00"),
            },
            {
                "symbol": "MSFT",
                "weight_pct": Decimal("35.00"),
                "allocated_amount": Decimal("35000.00"),
            },
            {
                "symbol": "GOOG",
                "weight_pct": Decimal("15.00"),
                "allocated_amount": Decimal("15000.00"),
            },
        ],
        "cash_pct": Decimal("10.00"),
        "cash_amount": Decimal("10000.00"),
    }


# =============================================================================
# 1. 论文破裂条件校验测试
# =============================================================================


@pytest.mark.unit
class TestValidateThesisBreakers:
    """测试论文破裂条件可监控性校验。"""

    def test_valid_breakers_dict_list(self, valid_thesis_breakers: list[dict[str, str]]) -> None:
        ok, issues = validate_thesis_breakers(valid_thesis_breakers)
        assert ok is True
        assert len(issues) == 0

    def test_valid_breakers_pydantic_items(
        self, valid_thesis_breakers: list[dict[str, str]]
    ) -> None:
        items = [ThesisBreakerItem.model_validate(b) for b in valid_thesis_breakers]
        ok, issues = validate_thesis_breakers(items)
        assert ok is True
        assert len(issues) == 0

    def test_breakers_not_a_list(self) -> None:
        ok, issues = validate_thesis_breakers("not_a_list")
        assert ok is False
        assert any("必须为列表结构" in s for s in issues)

    def test_breakers_too_few(self) -> None:
        short_list = [
            {
                "condition": "净利率下跌",
                "metric": "net_margin",
                "threshold": "< 0.1",
                "data_field": "fundamentals.net_margin",
            },
            {
                "condition": "PE过高",
                "metric": "pe_trailing",
                "threshold": "> 50",
                "data_field": "fundamentals.pe_trailing",
            },
        ]
        ok, issues = validate_thesis_breakers(short_list)
        assert ok is False
        assert any("至少需要 3 条监控条件" in s for s in issues)

    def test_breakers_too_many(self, valid_thesis_breakers: list[dict[str, str]]) -> None:
        too_many = valid_thesis_breakers * 4  # 12 条
        ok, issues = validate_thesis_breakers(too_many)
        assert ok is False
        assert any("最多支持 10 条监控条件" in s for s in issues)

    def test_missing_fields_in_breaker(self) -> None:
        incomplete = [
            {
                "condition": "",
                "metric": "net_margin",
                "threshold": "< 0.2",
                "data_field": "fundamentals.net_margin",
            },
            {
                "condition": "有描述",
                "metric": "",
                "threshold": "> 40",
                "data_field": "fundamentals.pe_trailing",
            },
            {
                "condition": "有描述",
                "metric": "pe_trailing",
                "threshold": "",
                "data_field": "fundamentals.pe_trailing",
            },
        ]
        ok, issues = validate_thesis_breakers(incomplete)
        assert ok is False
        assert any("缺少 condition" in s for s in issues)
        assert any("缺少 metric" in s for s in issues)
        assert any("缺少 threshold" in s for s in issues)

    def test_unsupported_data_field_path(self) -> None:
        invalid_path = [
            {
                "condition": "管理层离职",
                "metric": "ceo_left",
                "threshold": "== True",
                "data_field": "unsupported.random.field",
            },
            {
                "condition": "净利率下跌",
                "metric": "net_margin",
                "threshold": "< 0.2",
                "data_field": "fundamentals.net_margin",
            },
            {
                "condition": "PE过高",
                "metric": "pe_trailing",
                "threshold": "> 45",
                "data_field": "fundamentals.pe_trailing",
            },
        ]
        ok, issues = validate_thesis_breakers(invalid_path)
        assert ok is False
        assert any("不在系统支持的监控路径列表中" in s for s in issues)

    def test_all_supported_data_fields_recognized(self) -> None:
        for field in SUPPORTED_THESIS_BREAKER_DATA_FIELDS:
            sample = [
                {
                    "condition": f"测试 {field}",
                    "metric": field.split(".")[-1],
                    "threshold": "> 0",
                    "data_field": field,
                }
            ] * 3
            ok, issues = validate_thesis_breakers(sample)
            assert ok is True, f"字段 {field} 应该被识别为合法监控路径: {issues}"


# =============================================================================
# 2. 投资组合配置权重守恒与防篡改测试
# =============================================================================


@pytest.mark.unit
class TestValidatePortfolioWeights:
    """测试组合权重守恒与代码量化结果比对防篡改。"""

    def test_valid_portfolio_passes(
        self,
        valid_portfolio_payload: dict[str, Any],
        valid_portfolio_computed: dict[str, Any],
    ) -> None:
        ok, issues = validate_portfolio_weights(
            valid_portfolio_payload, computed=valid_portfolio_computed
        )
        assert ok is True
        assert len(issues) == 0

    def test_weights_sum_not_100_percent(self, valid_portfolio_payload: dict[str, Any]) -> None:
        payload = dict(valid_portfolio_payload)
        # 将现金比例改成 15%，总计 105% 不守恒
        payload["cash_pct"] = Decimal("15.00")
        ok, issues = validate_portfolio_weights(payload)
        assert ok is False
        assert any("资产配置权重与现金比例不守恒" in s for s in issues)

    def test_amount_sum_not_conserved(self, valid_portfolio_payload: dict[str, Any]) -> None:
        payload = dict(valid_portfolio_payload)
        # 将现金金额改成 5000，导致总金额 95000 != 100000
        payload["cash_amount"] = Decimal("5000.00")
        ok, issues = validate_portfolio_weights(payload)
        assert ok is False
        assert any("资产配置金额不守恒" in s for s in issues)

    def test_ai_tampered_stock_weight(
        self,
        valid_portfolio_payload: dict[str, Any],
        valid_portfolio_computed: dict[str, Any],
    ) -> None:
        payload = dict(valid_portfolio_payload)
        # AI 擅自篡改 AAPL 权重为 45%，GOOG 改为 10%（虽然总和仍为 100%，但篡改了代码优化结果）
        payload["allocations"] = [
            {
                "symbol": "AAPL",
                "weight_pct": Decimal("45.00"),
                "allocated_amount": Decimal("45000.00"),
            },
            {
                "symbol": "MSFT",
                "weight_pct": Decimal("35.00"),
                "allocated_amount": Decimal("35000.00"),
            },
            {
                "symbol": "GOOG",
                "weight_pct": Decimal("10.00"),
                "allocated_amount": Decimal("10000.00"),
            },
        ]
        ok, issues = validate_portfolio_weights(payload, computed=valid_portfolio_computed)
        assert ok is False
        assert any("标的 AAPL 权重被篡改" in s for s in issues)
        assert any("标的 GOOG 权重被篡改" in s for s in issues)

    def test_ai_tampered_cash_percentage(
        self,
        valid_portfolio_payload: dict[str, Any],
        valid_portfolio_computed: dict[str, Any],
    ) -> None:
        payload = dict(valid_portfolio_payload)
        payload["cash_pct"] = Decimal("8.00")
        payload["allocations"][0]["weight_pct"] = Decimal("42.00")
        ok, issues = validate_portfolio_weights(payload, computed=valid_portfolio_computed)
        assert ok is False
        assert any("现金比例被篡改" in s for s in issues)

    def test_ai_introduced_unoptimized_symbol(
        self,
        valid_portfolio_payload: dict[str, Any],
        valid_portfolio_computed: dict[str, Any],
    ) -> None:
        payload = dict(valid_portfolio_payload)
        payload["allocations"] = [
            {"symbol": "TSLA", "weight_pct": Decimal("50.00")},
            {"symbol": "AAPL", "weight_pct": Decimal("40.00")},
        ]
        payload["cash_pct"] = Decimal("10.00")
        ok, issues = validate_portfolio_weights(payload, computed=valid_portfolio_computed)
        assert ok is False
        assert any("标的 TSLA 不在代码量化优化标的池中" in s for s in issues)


# =============================================================================
# 3. 股票横向对比综合排名防篡改测试
# =============================================================================


@pytest.mark.unit
class TestValidateCompareRanking:
    """测试对比排名与得分比对防篡改。"""

    @pytest.fixture
    def valid_compare_computed(self) -> dict[str, Any]:
        return {
            "ranking": [
                {
                    "symbol": "AAPL",
                    "rank": 1,
                    "total_score": Decimal("85.50"),
                    "one_line_reason": "核心优势显著",
                },
                {
                    "symbol": "MSFT",
                    "rank": 2,
                    "total_score": Decimal("81.20"),
                    "one_line_reason": "云业务稳健",
                },
            ]
        }

    def test_matching_ranking_passes(self, valid_compare_computed: dict[str, Any]) -> None:
        payload = {"ranking": list(valid_compare_computed["ranking"])}
        ok, issues = validate_compare_ranking(payload, computed=valid_compare_computed)
        assert ok is True
        assert len(issues) == 0

    def test_ai_swapped_symbols_ranking(self, valid_compare_computed: dict[str, Any]) -> None:
        payload = {
            "ranking": [
                {
                    "symbol": "MSFT",
                    "rank": 1,
                    "total_score": Decimal("85.50"),
                },
                {
                    "symbol": "AAPL",
                    "rank": 2,
                    "total_score": Decimal("81.20"),
                },
            ]
        }
        ok, issues = validate_compare_ranking(payload, computed=valid_compare_computed)
        assert ok is False
        assert any("第 1 名标的被篡改" in s for s in issues)

    def test_ai_tampered_score(self, valid_compare_computed: dict[str, Any]) -> None:
        payload = {
            "ranking": [
                {
                    "symbol": "AAPL",
                    "rank": 1,
                    "total_score": Decimal("99.90"),
                },
                {
                    "symbol": "MSFT",
                    "rank": 2,
                    "total_score": Decimal("81.20"),
                },
            ]
        }
        ok, issues = validate_compare_ranking(payload, computed=valid_compare_computed)
        assert ok is False
        assert any("标的 AAPL 综合得分被篡改" in s for s in issues)


# =============================================================================
# 4. 新手通俗可读性校验测试 (M7 用例扩展)
# =============================================================================


@pytest.mark.unit
class TestCheckNoviceReadabilityM7:
    """测试 M7 三大用例通俗可读性审查。"""

    def test_compare_readability_complete(self) -> None:
        payload = {
            "summary": "横向对比概要",
            "dimension_notes": {
                "growth": "营收增长良好",
                "margin": "毛利率高",
                "debt": "资产负债稳健",
                "valuation": "估值合理",
                "moat": "护城河深厚",
                "risk": "政策与行业风险",
                "dividend": "分红稳定",
                "long_term": "长期确定性高",
            },
            "fit_by_investor": [
                {"symbol": "AAPL", "suitable_for": ["稳健型"], "not_suitable_for": ["高杠杆投机"]}
            ],
        }
        ok, suggestions = check_novice_readability(payload, "compare")
        assert ok is True
        assert len(suggestions) == 0

    def test_compare_missing_dimension_notes(self) -> None:
        payload = {
            "summary": "横向对比概要",
            "dimension_notes": {"growth": "仅有增速"},
            "fit_by_investor": [{"symbol": "AAPL"}],
        }
        ok, suggestions = check_novice_readability(payload, "compare")
        assert ok is False
        assert any("缺少 margin 维度定性对比说明" in s for s in suggestions)

    def test_long_term_readability_complete(
        self, valid_thesis_breakers: list[dict[str, str]]
    ) -> None:
        payload = {
            "summary": "长期持有价值概要",
            "pillars": {
                "moat": {"rating": "strong", "reason": "商业模式闭环"},
                "leadership": {"rating": "strong", "reason": "管理层资本配置卓越"},
                "demand_stability": {"rating": "favorable", "reason": "消费需求刚性"},
                "pricing_power": {"rating": "strong", "reason": "具备极强自主提价权"},
                "innovation": {"rating": "moderate", "reason": "研发投入充足"},
                "financial_strength": {"rating": "strong", "reason": "充沛自由现金流"},
                "market_size": {"rating": "favorable", "reason": "TAM 空间巨大"},
            },
            "thesis_breakers": valid_thesis_breakers,
        }
        ok, suggestions = check_novice_readability(payload, "long_term")
        assert ok is True
        assert len(suggestions) == 0

    def test_portfolio_readability_complete(self, valid_portfolio_payload: dict[str, Any]) -> None:
        ok, suggestions = check_novice_readability(valid_portfolio_payload, "portfolio")
        assert ok is True
        assert len(suggestions) == 0

    def test_portfolio_missing_risk_notes_or_rebalance(
        self, valid_portfolio_payload: dict[str, Any]
    ) -> None:
        payload = dict(valid_portfolio_payload)
        payload["risk_notes"] = ""
        payload["rebalance_suggestion"] = ""
        ok, suggestions = check_novice_readability(payload, "portfolio")
        assert ok is False
        assert any("缺少组合风险提示与对冲说明" in s for s in suggestions)
        assert any("缺少动态再平衡建议" in s for s in suggestions)


# =============================================================================
# 5. 金融合规禁用词检出与脱敏测试
# =============================================================================


@pytest.mark.unit
class TestForbiddenProfitTerms:
    """测试金融承诺与虚假宣传词汇。"""

    def test_contains_forbidden_terms_direct_and_nested(self) -> None:
        text = "这是一个保证保本且稳赚不赔的零风险保本方案，必定100%赚钱！"
        found = contains_forbidden_terms(text)
        assert "保证保本" in found
        assert "稳赚不赔" in found
        assert "100%赚钱" in found
        assert "零风险保本" in found

        nested = {
            "advice": "保证收益，包赚不亏",
            "list": ["内幕必涨", "绝不亏损"],
            "normal": "正常内容",
        }
        found_nested = contains_forbidden_terms(nested)
        assert "保证收益" in found_nested
        assert "包赚不亏" in found_nested
        assert "内幕必涨" in found_nested
        assert "绝不亏损" in found_nested

    def test_sanitize_forbidden_terms_eliminates_all(self) -> None:
        raw_structure = {
            "title": "稳赚策略",
            "desc": "零风险保本，保证保本且稳赚不赔，绝对收益！",
            "takeaway": ["100%稳赚", "内幕必涨"],
        }
        sanitized = sanitize_forbidden_terms_in_obj(raw_structure)
        assert len(contains_forbidden_terms(sanitized)) == 0


# =============================================================================
# 6. ComplianceGuardrail 与异常拦截测试
# =============================================================================


@pytest.mark.unit
class TestComplianceGuardrailEnforcement:
    """测试合规防线异常拦截。"""

    def test_assert_envelope_compliance_success(
        self,
        valid_portfolio_payload: dict[str, Any],
        valid_portfolio_computed: dict[str, Any],
    ) -> None:
        envelope = ResearchEnvelope(
            use_case="portfolio",
            symbol="AAPL,MSFT,GOOG",
            as_of=date(2026, 2, 20),
            summary="稳健组合配置建议",
            payload=valid_portfolio_payload,
            disclaimer=DEFAULT_DISCLAIMER,
        )
        # 1. verify_envelope_compliance 检查
        ok, issues = verify_envelope_compliance(envelope, computed=valid_portfolio_computed)
        assert ok is True
        assert len(issues) == 0

        # 2. assert_envelope_compliance 不抛异常即为成功
        assert_envelope_compliance(envelope, computed=valid_portfolio_computed)

    def test_assert_envelope_compliance_raises_on_tampering(
        self,
        valid_portfolio_payload: dict[str, Any],
        valid_portfolio_computed: dict[str, Any],
    ) -> None:
        tampered_payload = dict(valid_portfolio_payload)
        tampered_payload["cash_pct"] = Decimal("20.00")  # 篡改现金比例

        envelope = ResearchEnvelope(
            use_case="portfolio",
            symbol="AAPL,MSFT,GOOG",
            as_of=date(2026, 2, 20),
            summary="稳健组合配置建议",
            payload=tampered_payload,
            disclaimer=DEFAULT_DISCLAIMER,
        )
        with pytest.raises(ComplianceViolationError) as exc_info:
            assert_envelope_compliance(envelope, computed=valid_portfolio_computed)
        assert "合规防线校验失败" in str(exc_info.value)
        assert "现金比例被篡改" in str(exc_info.value)

    def test_guardrail_enforce_tamper_protection_blocks_invalid_breaker(self) -> None:
        invalid_long_term_payload = {
            "summary": "苹果公司长期分析",
            "pillars": {
                "moat": {"rating": "strong", "reason": "护城河深厚"},
                "leadership": {"rating": "strong", "reason": "管理层卓越"},
                "demand_stability": {"rating": "favorable", "reason": "刚需"},
                "pricing_power": {"rating": "strong", "reason": "提价权强"},
                "innovation": {"rating": "moderate", "reason": "持续研发"},
                "financial_strength": {"rating": "strong", "reason": "现金流充沛"},
                "market_size": {"rating": "favorable", "reason": "空间广阔"},
            },
            "thesis_breakers": [
                {
                    "condition": "净利率下跌",
                    "metric": "net_margin",
                    "threshold": "< 0.1",
                    "data_field": "illegal.path",
                }
            ],  # 仅 1 条且路径非法
        }
        envelope = ResearchEnvelope(
            use_case="long_term",
            symbol="AAPL",
            as_of=date(2026, 2, 20),
            summary="长投结论",
            payload=invalid_long_term_payload,
            disclaimer=DEFAULT_DISCLAIMER,
        )

        guardrail = ComplianceGuardrail(enforce_tamper_protection=True)
        with pytest.raises(ComplianceViolationError) as exc_info:
            guardrail.process_envelope(envelope)
        assert "至少需要 3 条监控条件" in str(exc_info.value)
        assert "不在系统支持的监控路径列表中" in str(exc_info.value)

    def test_guardrail_sanitizes_forbidden_words_on_valid_envelope(
        self,
        valid_portfolio_payload: dict[str, Any],
        valid_portfolio_computed: dict[str, Any],
    ) -> None:
        payload_with_banned = dict(valid_portfolio_payload)
        payload_with_banned["rationale"] = "这套组合保本稳赚，具备超额确定性"

        envelope = ResearchEnvelope(
            use_case="portfolio",
            symbol="AAPL,MSFT,GOOG",
            as_of=date(2026, 2, 20),
            summary="保本收益建议",
            payload=payload_with_banned,
            disclaimer="旧免责声明",
        )
        guardrail = ComplianceGuardrail(sanitize_terms=True, enforce_tamper_protection=True)
        processed = guardrail.process_envelope(envelope, computed=valid_portfolio_computed)

        assert processed.disclaimer == DEFAULT_DISCLAIMER
        assert "保本" not in processed.summary
        assert "追求资本保值" in processed.summary
        assert "保本" not in processed.payload["rationale"]
        assert "稳赚" not in processed.payload["rationale"]

    def test_verify_envelope_compliance_with_forbidden_words(self) -> None:
        envelope = ResearchEnvelope(
            use_case="research",
            symbol="AAPL",
            as_of=date(2026, 2, 20),
            summary="本股票承诺稳赚保本",
            payload={"summary": "100%赚钱"},
            disclaimer=DEFAULT_DISCLAIMER,
        )
        ok, issues = verify_envelope_compliance(envelope)
        assert ok is False
        assert any("包含金融合规禁用词" in s for s in issues)

    def test_verify_envelope_compliance_with_compare_tampering(self) -> None:
        envelope = ResearchEnvelope(
            use_case="compare",
            symbol="AAPL,MSFT,GOOG",
            as_of=date(2026, 2, 20),
            summary="对比概要",
            payload={
                "summary": "对比概要",
                "ranking": [
                    {"symbol": "AAPL", "rank": 1, "total_score": Decimal("85.00")},
                    {"symbol": "MSFT", "rank": 2, "total_score": Decimal("80.00")},
                    {"symbol": "GOOG", "rank": 3, "total_score": Decimal("75.00")},
                ],
                "dimension_notes": {
                    "growth": "g",
                    "margin": "m",
                    "debt": "d",
                    "valuation": "v",
                    "moat": "mo",
                    "risk": "r",
                    "dividend": "div",
                    "long_term": "lt",
                },
                "fit_by_investor": [{"symbol": "AAPL"}],
            },
            disclaimer=DEFAULT_DISCLAIMER,
        )
        computed = {
            "ranking": [
                {"symbol": "AAPL", "rank": 1, "total_score": Decimal("85.00")},
                {"symbol": "MSFT", "rank": 2, "total_score": Decimal("80.00")},
            ]
        }
        ok, issues = verify_envelope_compliance(envelope, computed=computed)
        assert ok is False
        assert any("综合排名标的数量不一致" in s for s in issues)

    def test_edge_cases_and_malformed_structures(self) -> None:
        # 1. validate_thesis_breakers: 非法 item 类型
        ok, issues = validate_thesis_breakers([123, "abc", None])
        assert ok is False
        assert any("格式非法" in s for s in issues)

        # 2. validate_portfolio_weights: 缺少 cash_pct 或 weight_pct
        ok_p, p_issues = validate_portfolio_weights(
            {
                "allocations": [{"symbol": "AAPL", "weight_pct": None}, {"symbol": "MSFT"}],
                "cash_pct": None,
            }
        )
        assert ok_p is False
        assert any("缺少 cash_pct" in s for s in p_issues)
        assert any("缺少 weight_pct" in s for s in p_issues)

        # 3. check_novice_readability: compare 缺少维度字典或投资者画像
        ok_c, c_sug = check_novice_readability(
            {"summary": "ok", "dimension_notes": "not_a_dict", "fit_by_investor": []},
            "compare",
        )
        assert ok_c is False
        assert any("缺少 8 大维度定性对比说明" in s for s in c_sug)
        assert any("缺少适合与不适合投资人群画像" in s for s in c_sug)

        # 4. check_novice_readability: long_term 缺少 pillars 字典
        ok_l, l_sug = check_novice_readability(
            {"summary": "ok", "pillars": "not_a_dict", "thesis_breakers": []},
            "long_term",
        )
        assert ok_l is False
        assert any("缺少 7 大核心支柱评估结果" in s for s in l_sug)

        # 5. check_novice_readability: portfolio 配置项缺少 reason
        ok_pf, pf_sug = check_novice_readability(
            {
                "summary": "ok",
                "risk_notes": "rn",
                "rebalance_suggestion": "rb",
                "allocations": [{"symbol": "AAPL", "reason": ""}],
            },
            "portfolio",
        )
        assert ok_pf is False
        assert any("缺少战略定位与理由说明" in s for s in pf_sug)
