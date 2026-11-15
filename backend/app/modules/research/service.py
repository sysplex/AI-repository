"""M6 AI 研究用例对外门面服务实现，`CONTRACTS.md §2`。

统一编排 4 大核心研究用例管道流程：
- F2: 个股深度研究 (research)
- F3: 买入决策评估 (buy_decision)
- F6: 技术面通俗分析与交易计划 (technical)
- F7: 财报深度解读与业绩评估 (earnings)

编排逻辑：
1. 校验输入参数；
2. 调用 FactAggregator 采集真实市场数据并追踪 missing_fields；
3. 驱动 AIService 执行大模型分析与数字溯源；
4. 抽取关键论点并绑定事实佐证 (EvidenceItem)；
5. 封装标准输出信封 ResearchEnvelope（含法定免责声明与数据缺口说明）。
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from app.core.clock import get_clock
from app.core.errors import AppError
from app.core.logging import get_logger
from app.modules.research.aggregator import (
    USE_CASE_BUY_DECISION,
    USE_CASE_EARNINGS,
    USE_CASE_RESEARCH,
    USE_CASE_TECHNICAL,
)
from app.modules.research.compliance import ComplianceGuardrail
from app.modules.research.exceptions import (
    InvalidParameterError,
    ResearchError,
)
from app.modules.research.ports import (
    AIServiceProtocol,
    FactAggregatorProtocol,
)
from app.modules.research.schemas import (
    BuyDecisionRequest,
    CompareRequest,
    EarningsAnalysisRequest,
    EvidenceItem,
    LongTermRequest,
    PortfolioRequest,
    ResearchEnvelope,
    ResearchRequest,
    TechnicalAnalysisRequest,
)

logger = get_logger("research.service")

__all__ = ["ResearchService"]


def _build_default_evidence(facts: dict[str, Any]) -> list[EvidenceItem]:
    """根据基础事实字典提取核心数字佐证项。"""
    evidence: list[EvidenceItem] = []

    quote = facts.get("quote")
    if isinstance(quote, dict) and quote.get("price") is not None:
        evidence.append(
            EvidenceItem(
                claim=f"最新收盘/行情价格为 {quote['price']}",
                source_field="facts.quote.price",
            )
        )

    funds = facts.get("fundamentals")
    if isinstance(funds, dict):
        if funds.get("pe_trailing") is not None:
            evidence.append(
                EvidenceItem(
                    claim=f"市盈率(TTM) 为 {funds['pe_trailing']}",
                    source_field="facts.fundamentals.pe_trailing",
                )
            )
        if funds.get("net_margin") is not None:
            evidence.append(
                EvidenceItem(
                    claim=f"净利率为 {funds['net_margin']}",
                    source_field="facts.fundamentals.net_margin",
                )
            )

    computed = facts.get("computed")
    if isinstance(computed, dict):
        if "trade_plan" in computed and isinstance(computed["trade_plan"], dict):
            tp = computed["trade_plan"]
            evidence.append(
                EvidenceItem(
                    claim=f"代码量化交易计划：入场位 {tp.get('entry')}，止损位 {tp.get('stop')}",
                    source_field="facts.computed.trade_plan",
                )
            )
        if "pos_in_52w_range" in computed:
            evidence.append(
                EvidenceItem(
                    claim=f"52周区间相对位置为 {computed['pos_in_52w_range']}",
                    source_field="facts.computed.pos_in_52w_range",
                )
            )

    return evidence


def _extract_summary(payload: dict[str, Any], symbol: str, use_case: str) -> str:
    """从用例专属 payload 中提取用于外层信封的一句话核心摘要。"""
    if payload.get("beginner_summary"):
        return str(payload["beginner_summary"]).strip()
    if payload.get("summary"):
        return str(payload["summary"]).strip()
    if payload.get("verdict_reason"):
        return str(payload["verdict_reason"]).strip()
    if payload.get("short_term_outlook"):
        return str(payload["short_term_outlook"]).strip()
    takeaway = payload.get("beginner_takeaway")
    if isinstance(takeaway, list) and len(takeaway) > 0 and takeaway[0]:
        return str(takeaway[0]).strip()
    return f"{symbol} {use_case} 分析完成"


class ResearchService:
    """AI 研究用例对外门面编排服务。

    实现 ``ResearchServiceProtocol``，对外部路由或上层业务提供标准化股票研究能力。
    """

    def __init__(
        self,
        ai_service: AIServiceProtocol,
        fact_aggregator: FactAggregatorProtocol,
        clock: Any | None = None,
        compliance_guardrail: ComplianceGuardrail | None = None,
    ) -> None:
        self._ai_service = ai_service
        self._fact_aggregator = fact_aggregator
        self._clock = clock or get_clock()
        self._compliance_guardrail = compliance_guardrail or ComplianceGuardrail()

    async def get_stock_research(
        self,
        request: ResearchRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F2 股票深度研究。"""
        params = {"symbol": request.symbol.strip().upper()}
        return await self._execute_pipeline(
            use_case=USE_CASE_RESEARCH,
            symbol=request.symbol,
            user_id=user_id,
            params=params,
            aggregator_kwargs={},
        )

    async def get_buy_decision(
        self,
        request: BuyDecisionRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F3 买入决策分析。"""
        params = {
            "symbol": request.symbol.strip().upper(),
            "target_price": str(request.target_price),
            "horizon": request.horizon,
            "risk_level": request.risk_level,
        }
        aggregator_kwargs = {
            "target_price": request.target_price,
            "horizon": request.horizon,
            "risk_level": request.risk_level,
        }
        return await self._execute_pipeline(
            use_case=USE_CASE_BUY_DECISION,
            symbol=request.symbol,
            user_id=user_id,
            params=params,
            aggregator_kwargs=aggregator_kwargs,
        )

    async def get_technical_analysis(
        self,
        request: TechnicalAnalysisRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F6 技术面通俗分析与交易计划生成。"""
        params = {"symbol": request.symbol.strip().upper()}
        return await self._execute_pipeline(
            use_case=USE_CASE_TECHNICAL,
            symbol=request.symbol,
            user_id=user_id,
            params=params,
            aggregator_kwargs={},
        )

    async def get_earnings_analysis(
        self,
        request: EarningsAnalysisRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F7 财报深度解读与指引评估。"""
        params = {"symbol": request.symbol.strip().upper()}
        return await self._execute_pipeline(
            use_case=USE_CASE_EARNINGS,
            symbol=request.symbol,
            user_id=user_id,
            params=params,
            aggregator_kwargs={},
        )

    async def compare_stocks(
        self,
        request: CompareRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F4 多股票横向对比分析。"""
        raise NotImplementedError("compare_stocks will be implemented in M7-T04")

    async def get_long_term_analysis(
        self,
        request: LongTermRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F5 长期持有价值与破裂条件分析。"""
        raise NotImplementedError("get_long_term_analysis will be implemented in M7-T04")

    async def generate_portfolio_allocation(
        self,
        request: PortfolioRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F8 投资组合配置建议。"""
        raise NotImplementedError("generate_portfolio_allocation will be implemented in M7-T04")

    async def _execute_pipeline(
        self,
        *,
        use_case: str,
        symbol: str,
        user_id: UUID,
        params: dict[str, Any],
        aggregator_kwargs: dict[str, Any],
    ) -> ResearchEnvelope:
        sym = symbol.strip().upper()
        if not sym:
            raise InvalidParameterError(
                "Symbol must not be empty",
                details={"symbol": symbol},
            )

        logger.info(
            "Starting research pipeline: symbol={sym}, use_case={uc}, user_id={uid}",
            sym=sym,
            uc=use_case,
            uid=str(user_id),
        )

        # 1. 事实数据聚合与缺失追踪
        facts, missing_fields = await self._fact_aggregator.aggregate_facts(
            symbol=sym,
            use_case=use_case,
            **aggregator_kwargs,
        )

        # 2. 调用下游 AI 核心框架服务
        try:
            report = await self._ai_service.run(
                use_case=use_case,
                facts=facts,
                params=params,
                user_id=user_id,
            )
        except AppError:
            raise
        except Exception as exc:
            logger.error(
                "AI analysis execution failed: symbol={sym}, use_case={uc}, err={err}",
                sym=sym,
                uc=use_case,
                err=str(exc),
            )
            raise ResearchError(
                f"AI analysis execution failed for '{sym}': {exc}",
                details={"symbol": sym, "use_case": use_case, "error": str(exc)},
            ) from exc

        # 3. 提取 payload
        payload = (
            report.payload
            if hasattr(report, "payload") and isinstance(report.payload, dict)
            else (dict(report) if isinstance(report, dict) else {})
        )

        # 4. 提取或生成摘要
        summary = _extract_summary(payload, sym, use_case)

        # 5. 组装佐证列表
        evidence: list[EvidenceItem] = []
        raw_evidence = payload.get("evidence")
        if isinstance(raw_evidence, list):
            for item in raw_evidence:
                if isinstance(item, EvidenceItem):
                    evidence.append(item)
                elif isinstance(item, dict) and "claim" in item and "source_field" in item:
                    evidence.append(
                        EvidenceItem(
                            claim=str(item["claim"]),
                            source_field=str(item["source_field"]),
                        )
                    )
        if not evidence:
            evidence = _build_default_evidence(facts)

        # 6. 计算 as_of 日期
        as_of_date: date
        if hasattr(report, "created_at") and report.created_at is not None:
            as_of_date = report.created_at.date()
        else:
            as_of_date = self._clock.now().date()

        # 7. 组装初始信封并经由合规防线处理
        raw_envelope = ResearchEnvelope(
            schema_version="1.0",
            use_case=use_case,
            symbol=sym,
            as_of=as_of_date,
            summary=summary,
            payload=payload,
            evidence=evidence,
            data_gaps=missing_fields,
            disclaimer="本内容仅供研究与学习，不构成投资建议",
        )
        envelope = self._compliance_guardrail.process_envelope(raw_envelope)

        logger.info(
            "Research pipeline completed: symbol={sym}, use_case={uc}, gaps={gaps}",
            sym=sym,
            uc=use_case,
            gaps=len(missing_fields),
        )
        return envelope
