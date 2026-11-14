"""M6-T03 事实聚合器单元测试。

验证：
1. FactAggregator 实现 FactAggregatorProtocol；
2. 输入参数校验（空代码、非法用例名）；
3. 标的不存在或数据服务异常时抛出 SymbolNotFoundError；
4. 4 个标准用例（research, buy_decision, technical, earnings）的事实组装与缺失字段追踪；
5. 买入决策中确定性指标生成（target_vs_price_pct, pos_in_52w_range）；
6. 技术面中确定性交易计划生成（trade_plan）与指标映射；
7. 缺少关键现价时抛出 InsufficientDataError。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.research.aggregator import (
    USE_CASE_BUY_DECISION,
    USE_CASE_EARNINGS,
    USE_CASE_RESEARCH,
    USE_CASE_TECHNICAL,
    FactAggregator,
)
from app.modules.research.exceptions import (
    InsufficientDataError,
    InvalidParameterError,
    SymbolNotFoundError,
)
from app.modules.research.ports import FactAggregatorProtocol


@dataclass
class DummySnapshot:
    facts: dict[str, Any]
    missing_fields: list[str]
    symbol: str = "AAPL"


@dataclass
class DummyTechnicalSnapshot:
    symbol: str = "AAPL"
    as_of: date = date(2026, 1, 1)
    sma_20: Decimal | None = Decimal("150.00")
    sma_50: Decimal | None = Decimal("145.00")
    sma_200: Decimal | None = Decimal("135.00")
    ema_12: Decimal | None = Decimal("152.00")
    ema_26: Decimal | None = Decimal("148.00")
    rsi_14: Decimal | None = Decimal("62.50")
    macd: Decimal | None = Decimal("2.50")
    macd_signal: Decimal | None = Decimal("2.10")
    macd_hist: Decimal | None = Decimal("0.40")
    atr_14: Decimal | None = Decimal("3.20")
    bb_upper: Decimal | None = Decimal("158.00")
    bb_middle: Decimal | None = Decimal("150.00")
    bb_lower: Decimal | None = Decimal("142.00")
    obv: int | None = 15000000
    support: Decimal | None = Decimal("145.00")
    resistance: Decimal | None = Decimal("160.00")


@pytest.fixture
def base_facts() -> dict[str, Any]:
    return {
        "quote": {
            "symbol": "AAPL",
            "price": "150.00",
            "change": "2.50",
            "change_pct": "1.69",
            "volume": 50000000,
        },
        "profile": {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "description": "Tech giant producing smartphones and personal computers.",
            "website": "https://apple.com",
        },
        "fundamentals": {
            "pe_trailing": "30.5",
            "pe_forward": "28.0",
            "pb": "45.0",
            "roe": "1.50",
            "net_margin": "0.25",
            "debt_to_equity": "1.8",
            "market_cap": "3000000000000",
        },
        "bars": [
            {"date": "2026-01-01", "close": "140.00", "low": "120.00", "high": "145.00"},
            {"date": "2026-01-02", "close": "150.00", "low": "138.00", "high": "180.00"},
        ],
        "news": [{"title": "Apple announces quarterly results", "publisher": "Reuters"}],
    }


@pytest.mark.unit
class TestFactAggregatorProtocolAndValidation:
    """协议实现与入参校验测试。"""

    def test_implements_protocol(self) -> None:
        mock_data_service = MagicMock()
        aggregator = FactAggregator(data_service=mock_data_service)
        assert isinstance(aggregator, FactAggregatorProtocol)

    @pytest.mark.asyncio
    async def test_empty_symbol_raises_error(self) -> None:
        mock_data_service = MagicMock()
        aggregator = FactAggregator(data_service=mock_data_service)

        with pytest.raises(InvalidParameterError) as exc_info:
            await aggregator.aggregate_facts("", USE_CASE_RESEARCH)
        assert "Symbol must not be empty" in str(exc_info.value)

        with pytest.raises(InvalidParameterError):
            await aggregator.aggregate_facts("   ", USE_CASE_RESEARCH)

    @pytest.mark.asyncio
    async def test_unsupported_use_case_raises_error(self) -> None:
        mock_data_service = MagicMock()
        aggregator = FactAggregator(data_service=mock_data_service)

        with pytest.raises(InvalidParameterError) as exc_info:
            await aggregator.aggregate_facts("AAPL", "unsupported_case")
        assert "Unsupported use case" in str(exc_info.value)


@pytest.mark.unit
class TestFactAggregatorDataServiceInteraction:
    """与市场数据服务交互及异常测试。"""

    @pytest.mark.asyncio
    async def test_symbol_not_found_when_quote_and_profile_are_none(self) -> None:
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(
                facts={"quote": None, "profile": None},
                missing_fields=["quote", "profile"],
            )
        )
        aggregator = FactAggregator(data_service=mock_data_service)

        with pytest.raises(SymbolNotFoundError) as exc_info:
            await aggregator.aggregate_facts("UNKNOWN", USE_CASE_RESEARCH)
        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_data_service_exception_raises_symbol_not_found(self) -> None:
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(side_effect=RuntimeError("Provider timed out"))
        aggregator = FactAggregator(data_service=mock_data_service)

        with pytest.raises(SymbolNotFoundError) as exc_info:
            await aggregator.aggregate_facts("AAPL", USE_CASE_RESEARCH)
        assert "Provider timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fallback_when_data_service_lacks_build_facts(self) -> None:
        # 兼容无 build_facts，但具备 get_quote, get_profile 等的简单数据服务
        mock_data_service = MagicMock(
            spec=["get_quote", "get_profile", "get_fundamentals", "get_news"]
        )
        mock_data_service.get_quote = AsyncMock(return_value={"symbol": "AAPL", "price": "150.00"})
        mock_data_service.get_profile = AsyncMock(
            return_value={"symbol": "AAPL", "name": "Apple Inc."}
        )
        mock_data_service.get_fundamentals = AsyncMock(return_value={"pe_trailing": "30.0"})
        mock_data_service.get_news = AsyncMock(return_value=[{"title": "Apple news"}])

        aggregator = FactAggregator(data_service=mock_data_service)
        facts, missing = await aggregator.aggregate_facts("AAPL", USE_CASE_RESEARCH)

        assert facts["quote"]["price"] == "150.00"
        assert facts["profile"]["name"] == "Apple Inc."
        assert isinstance(missing, list)

    @pytest.mark.asyncio
    async def test_fallback_when_data_service_methods_fail(self) -> None:
        mock_data_service = MagicMock(
            spec=["get_quote", "get_profile", "get_fundamentals", "get_news"]
        )
        # get_quote succeeds so symbol is considered found
        mock_data_service.get_quote = AsyncMock(return_value={"price": "100.00"})
        # but other methods raise exceptions
        mock_data_service.get_profile = AsyncMock(side_effect=RuntimeError("profile fail"))
        mock_data_service.get_fundamentals = AsyncMock(side_effect=RuntimeError("fund fail"))
        mock_data_service.get_news = AsyncMock(side_effect=RuntimeError("news fail"))

        aggregator = FactAggregator(data_service=mock_data_service)
        facts, missing = await aggregator.aggregate_facts("AAPL", USE_CASE_RESEARCH)

        assert facts["quote"]["price"] == "100.00"
        assert facts["profile"] is None
        assert "profile" in missing
        assert "fundamentals" in missing
        assert "news" in missing

    @pytest.mark.asyncio
    async def test_build_facts_dict_payload_compatibility(self) -> None:
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value={
                "facts": {"quote": {"price": "150.00"}, "profile": {"name": "Apple"}},
                "missing_fields": ["quote.volume"],
            }
        )
        aggregator = FactAggregator(data_service=mock_data_service)
        facts, missing = await aggregator.aggregate_facts("AAPL", USE_CASE_RESEARCH)
        assert facts["quote"]["price"] == "150.00"
        assert "quote.volume" in missing


@pytest.mark.unit
class TestFactAggregatorUseCases:
    """针对 4 大用例的事实组装与字段提取。"""

    @pytest.mark.asyncio
    async def test_aggregate_research_use_case(self, base_facts: dict[str, Any]) -> None:
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(
                facts=base_facts,
                missing_fields=["fundamentals.dividend_yield"],
            )
        )
        aggregator = FactAggregator(data_service=mock_data_service)

        facts, missing = await aggregator.aggregate_facts("AAPL", USE_CASE_RESEARCH)
        assert facts["quote"]["symbol"] == "AAPL"
        assert facts["profile"]["name"] == "Apple Inc."
        assert "fundamentals.dividend_yield" in missing

    @pytest.mark.asyncio
    async def test_aggregate_research_with_missing_fields_in_profile_and_fundamentals(
        self, base_facts: dict[str, Any]
    ) -> None:
        base_facts["fundamentals"] = {"pe_trailing": None}
        base_facts["profile"] = {"name": "Apple Inc.", "sector": None, "industry": ""}
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(facts=base_facts, missing_fields=[])
        )
        aggregator = FactAggregator(data_service=mock_data_service)

        facts, missing = await aggregator.aggregate_facts("AAPL", USE_CASE_RESEARCH)
        assert "fundamentals.pe_trailing" in missing
        assert "profile.sector" in missing
        assert "profile.industry" in missing

    @pytest.mark.asyncio
    async def test_aggregate_buy_decision_use_case(self, base_facts: dict[str, Any]) -> None:
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(facts=base_facts, missing_fields=[])
        )
        aggregator = FactAggregator(data_service=mock_data_service)

        # 现价 150，计划买入价 165 (+10%)，52周低 120，高 180 (pos = (150-120)/(180-120) = 0.50)
        facts, missing = await aggregator.aggregate_facts(
            "AAPL",
            USE_CASE_BUY_DECISION,
            target_price=Decimal("165.00"),
            horizon="medium",
            risk_level="medium",
        )

        assert "computed" in facts
        assert facts["computed"]["target_vs_price_pct"] == Decimal("10.00")
        assert facts["computed"]["pos_in_52w_range"] == Decimal("0.50")
        assert facts["computed"]["current_price"] == Decimal("150.00")
        assert facts["computed"]["target_price"] == Decimal("165.00")
        assert facts["context"]["horizon"] == "medium"

    @pytest.mark.asyncio
    async def test_buy_decision_with_explicit_low_and_high_52w(
        self, base_facts: dict[str, Any]
    ) -> None:
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(facts=base_facts, missing_fields=[])
        )
        aggregator = FactAggregator(data_service=mock_data_service)

        facts, missing = await aggregator.aggregate_facts(
            "AAPL",
            USE_CASE_BUY_DECISION,
            target_price=Decimal("150.00"),
            low_52w=Decimal("100.00"),
            high_52w=Decimal("200.00"),
        )
        assert facts["computed"]["pos_in_52w_range"] == Decimal("0.50")

    @pytest.mark.asyncio
    async def test_buy_decision_without_bars_uses_fallback_52w(
        self, base_facts: dict[str, Any]
    ) -> None:
        base_facts["bars"] = []
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(facts=base_facts, missing_fields=[])
        )
        aggregator = FactAggregator(data_service=mock_data_service)

        facts, missing = await aggregator.aggregate_facts(
            "AAPL",
            USE_CASE_BUY_DECISION,
            target_price=Decimal("150.00"),
        )
        assert "low_52w" in missing
        assert "high_52w" in missing
        assert facts["computed"]["pos_in_52w_range"] == Decimal("0.50")

    @pytest.mark.asyncio
    async def test_buy_decision_missing_target_price_tracked(
        self, base_facts: dict[str, Any]
    ) -> None:
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(facts=base_facts, missing_fields=[])
        )
        aggregator = FactAggregator(data_service=mock_data_service)

        # 未提供 target_price
        facts, missing = await aggregator.aggregate_facts(
            "AAPL",
            USE_CASE_BUY_DECISION,
        )
        assert "target_price" in missing
        assert facts["computed"]["target_vs_price_pct"] == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_buy_decision_missing_quote_price_raises_insufficient_data(
        self, base_facts: dict[str, Any]
    ) -> None:
        base_facts["quote"]["price"] = None
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(facts=base_facts, missing_fields=[])
        )
        aggregator = FactAggregator(data_service=mock_data_service)

        with pytest.raises(InsufficientDataError) as exc_info:
            await aggregator.aggregate_facts("AAPL", USE_CASE_BUY_DECISION)
        assert "Missing current price" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_aggregate_technical_use_case_with_strategy_service(
        self, base_facts: dict[str, Any]
    ) -> None:
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(facts=base_facts, missing_fields=[])
        )
        mock_strategy_service = MagicMock()
        mock_strategy_service.compute_technical_snapshot = AsyncMock(
            return_value=DummyTechnicalSnapshot()
        )

        aggregator = FactAggregator(
            data_service=mock_data_service,
            strategy_service=mock_strategy_service,
        )

        facts, missing = await aggregator.aggregate_facts("AAPL", USE_CASE_TECHNICAL)

        # 验证技术指标映射
        assert "technical" in facts
        assert facts["technical"]["rsi_14"] == Decimal("62.50")
        assert facts["technical"]["support"] == Decimal("145.00")
        assert facts["technical"]["resistance"] == Decimal("160.00")

        # 验证交易计划确定性计算
        assert "computed" in facts
        assert "trade_plan" in facts["computed"]
        plan = facts["computed"]["trade_plan"]
        assert plan["entry"] == Decimal("150.00")
        assert plan["stop"] < plan["entry"]
        assert plan["target"] > plan["entry"]
        assert plan["risk_reward"] > Decimal("0")

    @pytest.mark.asyncio
    async def test_technical_use_case_with_synchronous_strategy_service(
        self, base_facts: dict[str, Any]
    ) -> None:
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(facts=base_facts, missing_fields=[])
        )
        mock_strategy_service = MagicMock()
        # 同步函数返回
        mock_strategy_service.compute_technical_snapshot = MagicMock(
            return_value=DummyTechnicalSnapshot()
        )

        aggregator = FactAggregator(
            data_service=mock_data_service,
            strategy_service=mock_strategy_service,
        )

        facts, missing = await aggregator.aggregate_facts("AAPL", USE_CASE_TECHNICAL)
        assert facts["technical"]["rsi_14"] == Decimal("62.50")
        assert "trade_plan" in facts["computed"]

    @pytest.mark.asyncio
    async def test_technical_use_case_without_strategy_service_falls_back(
        self, base_facts: dict[str, Any]
    ) -> None:
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(facts=base_facts, missing_fields=[])
        )

        # 无 strategy_service
        aggregator = FactAggregator(
            data_service=mock_data_service,
            strategy_service=None,
        )

        facts, missing = await aggregator.aggregate_facts("AAPL", USE_CASE_TECHNICAL)
        assert "technical_snapshot" in missing
        assert "computed" in facts
        assert "trade_plan" in facts["computed"]
        assert facts["computed"]["trade_plan"]["entry"] == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_technical_use_case_missing_price_raises_insufficient_data(
        self, base_facts: dict[str, Any]
    ) -> None:
        base_facts["quote"]["price"] = None
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(facts=base_facts, missing_fields=[])
        )
        aggregator = FactAggregator(data_service=mock_data_service)

        with pytest.raises(InsufficientDataError) as exc_info:
            await aggregator.aggregate_facts("AAPL", USE_CASE_TECHNICAL)
        assert "Missing current price for technical analysis" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_aggregate_earnings_use_case(self, base_facts: dict[str, Any]) -> None:
        mock_data_service = MagicMock()
        mock_data_service.build_facts = AsyncMock(
            return_value=DummySnapshot(facts=base_facts, missing_fields=[])
        )
        aggregator = FactAggregator(data_service=mock_data_service)

        # 财报缺少详细指引与管理层发言，但从基本面获取了利润率 net_margin
        facts, missing = await aggregator.aggregate_facts(
            "AAPL",
            USE_CASE_EARNINGS,
            earnings={
                "revenue": "94.9B",
                "eps": "1.64",
            },
        )

        assert "earnings" in facts
        assert facts["earnings"]["revenue"] == "94.9B"
        assert facts["earnings"]["eps"] == "1.64"
        assert facts["earnings"]["margins"] == "0.25"
        # 验证自动追踪缺失字段
        assert "earnings.guidance" in missing
        assert "earnings.management_commentary" in missing
