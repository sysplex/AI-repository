"""Unit tests for M2 marketdata models and ports."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.marketdata.models import (
    AnalystRatings,
    Bar,
    CompanyProfile,
    CorporateAction,
    EarningsEvent,
    EarningsHistory,
    FactsSnapshot,
    FinancialStatements,
    Fundamentals,
    NewsItem,
    Quote,
)
from app.modules.marketdata.ports import DataProvider


def test_bar_model_immutability_and_types() -> None:
    bar = Bar(
        symbol="AAPL",
        trade_date=date(2026, 11, 10),
        open=Decimal("220.50"),
        high=Decimal("225.00"),
        low=Decimal("219.80"),
        close=Decimal("224.23"),
        volume=54321000,
        adj_close=Decimal("224.23"),
    )

    assert bar.symbol == "AAPL"
    assert bar.open == Decimal("220.50")
    assert isinstance(bar.open, Decimal)
    assert bar.volume == 54321000

    with pytest.raises(ValidationError):
        # frozen=True prevents mutation
        bar.close = Decimal("230.00")  # type: ignore[misc]


def test_quote_model_immutability_and_defaults() -> None:
    now_utc = datetime.now(UTC)
    quote = Quote(
        symbol="MSFT",
        price=Decimal("415.20"),
        change=Decimal("3.50"),
        change_pct=Decimal("0.85"),
        volume=18500000,
        as_of=now_utc,
    )

    assert quote.symbol == "MSFT"
    assert quote.price == Decimal("415.20")
    assert quote.delayed_seconds == 0
    assert quote.stale is False

    with pytest.raises(ValidationError):
        quote.price = Decimal("420.00")  # type: ignore[misc]


def test_company_profile_model() -> None:
    profile = CompanyProfile(
        symbol="NVDA",
        name="NVIDIA Corporation",
        exchange="NASDAQ",
        sector="Technology",
        industry="Semiconductors",
        description="Designs GPUs and AI accelerators.",
        website="https://www.nvidia.com",
        employees=29600,
        country="US",
    )

    assert profile.symbol == "NVDA"
    assert profile.employees == 29600
    assert profile.country == "US"


def test_fundamentals_missing_fields_collection() -> None:
    fund = Fundamentals(
        symbol="GOOGL",
        as_of=date(2026, 11, 1),
        pe_trailing=Decimal("25.4"),
        pe_forward=Decimal("21.2"),
        market_cap=Decimal("2150000000000"),
        missing_fields=["dividend_yield", "debt_to_equity"],
    )

    assert fund.symbol == "GOOGL"
    assert fund.pe_trailing == Decimal("25.4")
    assert fund.pb is None
    assert "dividend_yield" in fund.missing_fields
    assert "debt_to_equity" in fund.missing_fields


def test_financial_statements_and_earnings() -> None:
    stmt = FinancialStatements(
        symbol="AAPL",
        period="annual",
        period_end=date(2025, 9, 30),
        balance_sheet={"total_assets": 352583000000},
        income_statement={"total_revenue": 391035000000},
        cash_flow={"operating_cash_flow": 118254000000},
    )
    assert stmt.period == "annual"
    assert stmt.income_statement["total_revenue"] == 391035000000

    event = EarningsEvent(
        symbol="AAPL",
        report_date=date(2026, 10, 31),
        eps_estimated=Decimal("1.60"),
        eps_actual=Decimal("1.64"),
        reaction_1d_pct=Decimal("2.15"),
    )
    history = EarningsHistory(symbol="AAPL", events=[event])
    assert len(history.events) == 1
    assert history.events[0].eps_actual == Decimal("1.64")


def test_corporate_action_split_and_dividend() -> None:
    split = CorporateAction(
        symbol="NVDA",
        ex_date=date(2024, 6, 10),
        action_type="split",
        ratio=Decimal("10.0"),
    )
    assert split.action_type == "split"
    assert split.ratio == Decimal("10.0")
    assert split.amount is None

    dividend = CorporateAction(
        symbol="AAPL",
        ex_date=date(2026, 11, 8),
        action_type="dividend",
        amount=Decimal("0.25"),
    )
    assert dividend.action_type == "dividend"
    assert dividend.amount == Decimal("0.25")
    assert dividend.ratio is None


def test_news_and_analyst_ratings() -> None:
    now_utc = datetime.now(UTC)
    news = NewsItem(
        id="news-101",
        symbol="TSLA",
        title="Tesla Unveils Next-Gen AI Fleet",
        summary="Tesla announces massive AI fleet milestone.",
        source="Reuters",
        url="https://example.com/news/101",
        published_at=now_utc,
    )
    assert news.id == "news-101"
    assert news.source == "Reuters"

    rating = AnalystRatings(
        symbol="TSLA",
        as_of=date(2026, 11, 1),
        consensus_rating="buy",
        target_high=Decimal("350.00"),
        target_low=Decimal("180.00"),
        target_mean=Decimal("260.00"),
        analyst_count=35,
    )
    assert rating.consensus_rating == "buy"
    assert rating.target_mean == Decimal("260.00")


def test_facts_snapshot_integrity() -> None:
    now_utc = datetime.now(UTC)
    snapshot = FactsSnapshot(
        content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        symbol="AMZN",
        as_of=now_utc,
        scope=["quote", "profile"],
        facts={"price": "205.50", "market_cap": "2100000000000"},
        missing_fields=[],
    )
    assert snapshot.symbol == "AMZN"
    assert snapshot.content_hash.startswith("e3b0c44")
    assert len(snapshot.scope) == 2


class DummyProvider:
    name: str = "dummy"

    async def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> list[Bar]:
        return []

    async def get_quote(self, symbol: str) -> Quote:
        raise NotImplementedError

    async def get_quotes(self, symbols: Any) -> dict[str, Quote]:
        return {}

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        raise NotImplementedError

    async def get_financial_statements(
        self,
        symbol: str,
        period: Any = "annual",
        limit: int = 10,
    ) -> FinancialStatements:
        raise NotImplementedError

    async def get_earnings(self, symbol: str, limit: int = 8) -> EarningsHistory:
        raise NotImplementedError

    async def get_news(
        self,
        symbol: str,
        limit: int = 20,
        since: datetime | None = None,
    ) -> list[NewsItem]:
        return []

    async def get_analyst_ratings(self, symbol: str) -> AnalystRatings:
        raise NotImplementedError

    async def get_corporate_actions(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> list[CorporateAction]:
        return []

    async def get_profile(self, symbol: str) -> CompanyProfile:
        raise NotImplementedError

    async def get_universe(self, name: str) -> list[str]:
        return ["AAPL", "MSFT"]


def test_data_provider_protocol_runtime_check() -> None:
    provider = DummyProvider()
    assert isinstance(provider, DataProvider)
    assert provider.name == "dummy"
