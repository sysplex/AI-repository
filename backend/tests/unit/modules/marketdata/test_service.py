"""Unit tests for DataService and build_facts (M2 / T05)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import DataUnavailable
from app.modules.marketdata.cache import MarketDataCache
from app.modules.marketdata.models import (
    Bar,
    CompanyProfile,
    Fundamentals,
    NewsItem,
    Quote,
)
from app.modules.marketdata.service import DataService

pytestmark = pytest.mark.unit


@pytest.fixture
def sample_quote() -> Quote:
    return Quote(
        symbol="AAPL",
        price=Decimal("182.50"),
        change=Decimal("1.25"),
        change_pct=Decimal("0.69"),
        volume=54321000,
        as_of=datetime(2024, 6, 12, 14, 0, 0, tzinfo=UTC),
        delayed_seconds=0,
        stale=False,
    )


@pytest.fixture
def sample_profile() -> CompanyProfile:
    return CompanyProfile(
        symbol="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        industry="Consumer Electronics",
        description="Consumer electronics.",
        website="https://www.apple.com",
        employees=161000,
        country="US",
    )


@pytest.fixture
def sample_fundamentals() -> Fundamentals:
    return Fundamentals(
        symbol="AAPL",
        as_of=date(2024, 6, 1),
        pe_trailing=Decimal("28.4"),
        pe_forward=Decimal("25.1"),
        pb=Decimal("45.2"),
        ps=Decimal("7.8"),
        roe=Decimal("1.45"),
        net_margin=Decimal("0.25"),
        debt_to_equity=Decimal("1.8"),
        market_cap=Decimal("2800000000000"),
        dividend_yield=Decimal("0.005"),
        beta=Decimal("1.1"),
        missing_fields=[],
    )


@pytest.fixture
def sample_bars() -> list[Bar]:
    return [
        Bar(
            symbol="AAPL",
            trade_date=date(2024, 6, 10),
            open=Decimal("180.00"),
            high=Decimal("183.00"),
            low=Decimal("179.50"),
            close=Decimal("182.00"),
            volume=45000000,
            adj_close=Decimal("182.00"),
        )
    ]


@pytest.fixture
def sample_news() -> list[NewsItem]:
    return [
        NewsItem(
            id="news-1",
            symbol="AAPL",
            title="Apple announces new product",
            summary="Exciting announcements at WWDC.",
            source="Reuters",
            url="https://reuters.com/news-1",
            published_at=datetime(2024, 6, 12, 10, 0, 0, tzinfo=UTC),
        )
    ]


@pytest.fixture
async def cache(redis: Any) -> AsyncIterator[MarketDataCache]:
    await redis.flushdb()
    cache_inst = MarketDataCache(redis_client=redis, base_delay=0.001, max_retries=1)
    yield cache_inst
    await redis.flushdb()


@pytest.fixture
def mock_provider(
    sample_quote: Quote,
    sample_profile: CompanyProfile,
    sample_fundamentals: Fundamentals,
    sample_bars: list[Bar],
    sample_news: list[NewsItem],
) -> AsyncMock:
    provider = AsyncMock()
    provider.name = "mock_provider"
    provider.get_quote.return_value = sample_quote
    provider.get_quotes.return_value = {"AAPL": sample_quote}
    provider.get_profile.return_value = sample_profile
    provider.get_fundamentals.return_value = sample_fundamentals
    provider.get_bars.return_value = sample_bars
    provider.get_news.return_value = sample_news
    provider.get_universe.return_value = ["AAPL", "MSFT", "NVDA"]
    return provider


# =============================================================================
# Core Service Delegation & Caching
# =============================================================================


async def test_get_quote_uses_cache(mock_provider: AsyncMock, cache: MarketDataCache) -> None:
    service = DataService(provider=mock_provider, cache=cache)

    # First call: hits provider and caches
    q1 = await service.get_quote("AAPL")
    assert q1.symbol == "AAPL"
    assert mock_provider.get_quote.call_count == 1

    # Second call: hits cache, provider call count remains 1
    q2 = await service.get_quote("AAPL")
    assert q2.symbol == "AAPL"
    assert mock_provider.get_quote.call_count == 1


async def test_get_quotes_batch(mock_provider: AsyncMock, cache: MarketDataCache) -> None:
    service = DataService(provider=mock_provider, cache=cache)
    quotes = await service.get_quotes(["AAPL"])
    assert "AAPL" in quotes
    assert quotes["AAPL"].price == Decimal("182.50")


async def test_get_bars_uses_cache(mock_provider: AsyncMock, cache: MarketDataCache) -> None:
    service = DataService(provider=mock_provider, cache=cache)
    start = date(2024, 6, 1)
    end = date(2024, 6, 10)

    b1 = await service.get_bars("AAPL", start, end)
    assert len(b1) == 1
    assert mock_provider.get_bars.call_count == 1

    b2 = await service.get_bars("AAPL", start, end)
    assert len(b2) == 1
    assert mock_provider.get_bars.call_count == 1


async def test_get_fundamentals_and_profile_delegation(
    mock_provider: AsyncMock, cache: MarketDataCache
) -> None:
    service = DataService(provider=mock_provider, cache=cache)

    funds = await service.get_fundamentals("AAPL")
    assert funds.pe_trailing == Decimal("28.4")

    profile = await service.get_profile("AAPL")
    assert profile.name == "Apple Inc."

    universe = await service.get_universe("sp500")
    assert "AAPL" in universe

    news = await service.get_news("AAPL")
    assert len(news) == 1


async def test_service_without_cache(mock_provider: AsyncMock) -> None:
    # Service configured with no cache operates directly through provider
    service = DataService(provider=mock_provider, cache=None)
    q = await service.get_quote("AAPL")
    assert q.symbol == "AAPL"

    b = await service.get_bars("AAPL", date(2024, 6, 1), date(2024, 6, 10))
    assert len(b) == 1

    f = await service.get_fundamentals("AAPL")
    assert f.symbol == "AAPL"

    p = await service.get_profile("AAPL")
    assert p.symbol == "AAPL"


# =============================================================================
# build_facts Snapshot Tests
# =============================================================================


async def test_build_facts_deterministic_hash(
    mock_provider: AsyncMock, cache: MarketDataCache
) -> None:
    service = DataService(provider=mock_provider, cache=cache)

    # Run build_facts twice with the exact same data
    snap1 = await service.build_facts("AAPL")
    snap2 = await service.build_facts("AAPL")

    # Content hash must be 64 characters hex (SHA-256)
    assert len(snap1.content_hash) == 64
    # Must be deterministic across calls with identical data
    assert snap1.content_hash == snap2.content_hash
    assert snap1.symbol == "AAPL"
    assert snap1.as_of == snap2.as_of
    assert set(snap1.scope) == {"quote", "profile", "fundamentals", "bars"}


async def test_build_facts_tracks_missing_fields_and_none(
    mock_provider: AsyncMock, cache: MarketDataCache
) -> None:
    # Partial fundamentals with missing metrics
    incomplete_fundamentals = Fundamentals(
        symbol="AAPL",
        as_of=date(2024, 6, 1),
        pe_trailing=Decimal("28.4"),
        market_cap=Decimal("2800000000000"),
        pe_forward=None,
        dividend_yield=None,
        beta=None,
        missing_fields=["pe_forward", "dividend_yield", "beta"],
    )
    # Profile with missing employee count
    incomplete_profile = CompanyProfile(
        symbol="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        industry="Consumer Electronics",
        website=None,
        employees=None,
    )

    mock_provider.get_fundamentals.return_value = incomplete_fundamentals
    mock_provider.get_profile.return_value = incomplete_profile

    service = DataService(provider=mock_provider, cache=cache)
    snapshot = await service.build_facts("AAPL")

    assert snapshot.facts["fundamentals"]["pe_forward"] is None
    assert snapshot.facts["profile"]["website"] is None

    # Missing fields must explicitly list the absent attributes
    assert "fundamentals.pe_forward" in snapshot.missing_fields
    assert "fundamentals.dividend_yield" in snapshot.missing_fields
    assert "profile.website" in snapshot.missing_fields
    assert "profile.employees" in snapshot.missing_fields


async def test_build_facts_fault_tolerant_on_scope_failure(
    mock_provider: AsyncMock, cache: MarketDataCache
) -> None:
    # Quote and bars succeed, but fundamentals fails completely
    mock_provider.get_fundamentals.side_effect = DataUnavailable("No fundamentals available")

    service = DataService(provider=mock_provider, cache=cache)
    snapshot = await service.build_facts("AAPL")

    # Facts dictionary must set the failed scope to None
    assert snapshot.facts["fundamentals"] is None
    # Failed scope must be recorded in missing_fields
    assert "fundamentals" in snapshot.missing_fields
    # Other scopes succeeded
    assert snapshot.facts["quote"] is not None
    assert snapshot.facts["profile"] is not None
    assert len(snapshot.content_hash) == 64


async def test_build_facts_custom_scope(mock_provider: AsyncMock, cache: MarketDataCache) -> None:
    service = DataService(provider=mock_provider, cache=cache)
    snapshot = await service.build_facts("AAPL", scope=["quote", "news"])

    assert "quote" in snapshot.facts
    assert "news" in snapshot.facts
    assert "fundamentals" not in snapshot.facts
    assert "bars" not in snapshot.facts
    assert snapshot.scope == ["quote", "news"]


# =============================================================================
# Persistence via Session Factory
# =============================================================================


async def test_build_facts_persists_to_database(
    mock_provider: AsyncMock, cache: MarketDataCache
) -> None:
    mock_session = AsyncMock()
    mock_session.get.return_value = None  # No existing record
    mock_session.add = MagicMock()

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    service = DataService(
        provider=mock_provider,
        cache=cache,
        session_factory=mock_session_factory,
    )

    snapshot = await service.build_facts("AAPL")

    # Verify session.add was called for DataSnapshotTable
    assert mock_session.add.call_count >= 1
    added_records = [call.args[0] for call in mock_session.add.call_args_list]
    snapshot_records = [r for r in added_records if getattr(r, "content_hash", None) is not None]
    assert len(snapshot_records) == 1
    assert snapshot_records[0].content_hash == snapshot.content_hash
    assert snapshot_records[0].symbol == "AAPL"
    # Commit must have been called
    assert mock_session.commit.called


async def test_persistence_failures_do_not_fail_caller(
    mock_provider: AsyncMock, cache: MarketDataCache
) -> None:
    failing_session = AsyncMock()
    failing_session.get.side_effect = RuntimeError("Database connection lost")

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = failing_session

    service = DataService(
        provider=mock_provider,
        cache=cache,
        session_factory=mock_session_factory,
    )

    # Should gracefully catch database error and still return facts snapshot
    snapshot = await service.build_facts("AAPL")
    assert snapshot.symbol == "AAPL"
    assert len(snapshot.content_hash) == 64
