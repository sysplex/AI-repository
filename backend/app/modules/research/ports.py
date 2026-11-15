"""M6 AI 研究用例端口协议抽象，`CONTRACTS.md §2`。

定义 research 模块依赖倒置契约：
- ``ResearchServiceProtocol``：对外统一研究门面协议（返回 ResearchEnvelope）
- ``FactAggregatorProtocol``：多源市场数据事实聚合协议
- ``QuantitativeEngineProtocol``：代码量化衍生指标与交易计划计算协议
- ``AIServiceProtocol``：大模型编排与执行依赖协议
- ``MarketDataServiceProtocol``：底层市场数据源依赖协议
- ``StrategyServiceProtocol``：技术分析与指标计算依赖协议
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from app.modules.research.schemas import (
    BuyDecisionRequest,
    CompareRequest,
    EarningsAnalysisRequest,
    LongTermRequest,
    PortfolioRequest,
    ResearchEnvelope,
    ResearchRequest,
    TechnicalAnalysisRequest,
)

__all__ = [
    "AIServiceProtocol",
    "FactAggregatorProtocol",
    "MarketDataServiceProtocol",
    "QuantitativeEngineProtocol",
    "ResearchServiceProtocol",
    "StrategyServiceProtocol",
]


@runtime_checkable
class AIServiceProtocol(Protocol):
    """AI 核心框架服务协议（解耦 research 对 ai 模块具体实现的直接依赖）。"""

    async def run(
        self,
        use_case: str,
        facts: dict[str, Any],
        params: dict[str, Any] | None = None,
        user_id: UUID | None = None,
        as_of: datetime | None = None,
        prompt_version: str | None = None,
    ) -> Any:
        """驱动大模型完成特定用例的分析并返回报告。"""
        ...


@runtime_checkable
class MarketDataServiceProtocol(Protocol):
    """行情与基本面数据服务协议。"""

    async def get_quote(self, symbol: str) -> Any: ...

    async def get_profile(self, symbol: str) -> Any: ...

    async def get_fundamentals(self, symbol: str) -> Any: ...

    async def get_news(self, symbol: str) -> Any: ...

    async def build_facts(
        self,
        symbol: str,
        scope: list[str] | None = None,
    ) -> Any: ...


@runtime_checkable
class StrategyServiceProtocol(Protocol):
    """技术指标与策略计算服务协议。"""

    async def compute_technical_snapshot(
        self,
        symbol: str,
        as_of: date | None = None,
    ) -> Any: ...


@runtime_checkable
class ResearchServiceProtocol(Protocol):
    """研究用例对外服务门面协议。"""

    async def get_stock_research(
        self,
        request: ResearchRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F2 股票深度研究。"""
        ...

    async def get_buy_decision(
        self,
        request: BuyDecisionRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F3 买入决策分析。"""
        ...

    async def get_technical_analysis(
        self,
        request: TechnicalAnalysisRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F6 技术面通俗分析与交易计划生成。"""
        ...

    async def get_earnings_analysis(
        self,
        request: EarningsAnalysisRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F7 财报深度解读与指引评估。"""
        ...

    async def compare_stocks(
        self,
        request: CompareRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F4 多股票横向对比分析。"""
        ...

    async def get_long_term_analysis(
        self,
        request: LongTermRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F5 长期持有价值与破裂条件分析。"""
        ...

    async def generate_portfolio_allocation(
        self,
        request: PortfolioRequest,
        user_id: UUID,
    ) -> ResearchEnvelope:
        """执行 F8 投资组合配置建议。"""
        ...


@runtime_checkable
class FactAggregatorProtocol(Protocol):
    """多源市场事实聚合器协议。"""

    async def aggregate_facts(
        self,
        symbol: str,
        use_case: str,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], list[str]]:
        """为特定用例从各基础模块收集 facts 数据字典及 missing_fields 列表。"""
        ...


@runtime_checkable
class QuantitativeEngineProtocol(Protocol):
    """代码量化计算派生引擎协议（防大模型编造点位的基础）。"""

    def compute_buy_decision_metrics(
        self,
        current_price: Decimal,
        target_price: Decimal,
        low_52w: Decimal,
        high_52w: Decimal,
    ) -> dict[str, Any]:
        """计算买入决策所需衍生指标（想买价偏差率、52周位置区间）。"""
        ...

    def compute_technical_trade_plan(
        self,
        current_price: Decimal,
        support: Decimal,
        resistance: Decimal,
        atr: Decimal,
    ) -> dict[str, Any]:
        """确定性计算技术面交易计划（入场、止损、目标、盈亏比）。"""
        ...
