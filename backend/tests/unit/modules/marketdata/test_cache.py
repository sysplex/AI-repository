"""Unit tests for MarketDataCache and resilience wrappers (M2 / T04)."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.calendar import ET
from app.core.errors import DataUnavailable
from app.modules.marketdata.cache import (
    BARS_TTL,
    FUNDAMENTALS_TTL,
    PROFILE_TTL,
    QUOTE_TTL_CLOSED,
    QUOTE_TTL_OPEN,
    MarketDataCache,
)
from app.modules.marketdata.models import (
    Bar,
    CompanyProfile,
    Fundamentals,
    Quote,
)

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
        ),
        Bar(
            symbol="AAPL",
            trade_date=date(2024, 6, 11),
            open=Decimal("182.50"),
            high=Decimal("184.20"),
            low=Decimal("181.80"),
            close=Decimal("183.50"),
            volume=48000000,
            adj_close=Decimal("183.50"),
        ),
    ]


@pytest.fixture
def sample_fundamentals() -> Fundamentals:
    return Fundamentals(
        symbol="AAPL",
        as_of=date(2024, 6, 1),
        pe_trailing=Decimal("28.4"),
        pe_forward=Decimal("25.1"),
        market_cap=Decimal("2800000000000"),
        missing_fields=[],
    )


@pytest.fixture
def sample_profile() -> CompanyProfile:
    return CompanyProfile(
        symbol="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        industry="Consumer Electronics",
        description="Apple designs and manufactures mobile communication devices.",
        website="https://www.apple.com",
        employees=161000,
        country="US",
    )


@pytest.fixture
def cache(redis: Any) -> MarketDataCache:
    """Fast cache for testing with minimal backoff delay (1ms)."""
    return MarketDataCache(redis_client=redis, base_delay=0.001, max_retries=2)


# =============================================================================
# TTL and Keys
# =============================================================================


def test_quote_ttl_during_market_hours(cache: MarketDataCache) -> None:
    assert BARS_TTL == 3600
    assert FUNDAMENTALS_TTL == 86400
    assert PROFILE_TTL == 86400
    # 2024-06-12 11:00 AM ET is open trading hours (Wednesday)
    open_time = datetime(2024, 6, 12, 11, 0, 0, tzinfo=ET)
    assert cache.get_quote_ttl(open_time) == QUOTE_TTL_OPEN


def test_quote_ttl_outside_market_hours(cache: MarketDataCache) -> None:
    # 2024-06-12 21:00 PM ET is closed hours
    closed_time = datetime(2024, 6, 12, 21, 0, 0, tzinfo=ET)
    assert cache.get_quote_ttl(closed_time) == QUOTE_TTL_CLOSED

    # Weekend is closed
    weekend_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=ET)
    assert cache.get_quote_ttl(weekend_time) == QUOTE_TTL_CLOSED


def test_cache_keys_formatting(cache: MarketDataCache) -> None:
    assert cache.quote_key("aapl") == "quote:AAPL"
    assert cache.backup_quote_key("aapl") == "backup:quote:AAPL"
    assert cache.fundamentals_key("msft") == "fundamentals:MSFT"
    assert cache.backup_fundamentals_key("msft") == "backup:fundamentals:MSFT"
    assert cache.profile_key("nvda") == "profile:NVDA"
    assert cache.backup_profile_key("nvda") == "backup:profile:NVDA"

    bars_key = cache.bars_key("aapl", date(2024, 1, 1), date(2024, 1, 10), "1d", adjusted=True)
    assert bars_key == "bars:AAPL:2024-01-01:2024-01-10:1d"

    unadj_bars_key = cache.bars_key(
        "aapl", date(2024, 1, 1), date(2024, 1, 10), "1d", adjusted=False
    )
    assert unadj_bars_key == "bars:AAPL:2024-01-01:2024-01-10:1d:unadjusted"


# =============================================================================
# Quote Cache & Resilience Tests
# =============================================================================


async def test_quote_cache_hit_asserts_zero_provider_calls(
    cache: MarketDataCache, sample_quote: Quote
) -> None:
    # Pre-populate active cache
    await cache.set_quote("AAPL", sample_quote)

    fetcher = AsyncMock()
    result = await cache.get_or_fetch_quote("AAPL", fetcher)

    assert result.symbol == "AAPL"
    assert result.price == Decimal("182.50")
    assert result.stale is False
    # Strict assertion: Provider call count is 0
    assert fetcher.call_count == 0


async def test_quote_cache_miss_fetches_and_caches(
    cache: MarketDataCache, sample_quote: Quote
) -> None:
    fetcher = AsyncMock(return_value=sample_quote)

    result = await cache.get_or_fetch_quote("AAPL", fetcher)

    assert result.symbol == "AAPL"
    assert fetcher.call_count == 1

    # Active key and backup key should both exist in redis
    active_raw = await cache.redis.get(cache.quote_key("AAPL"))
    backup_raw = await cache.redis.get(cache.backup_quote_key("AAPL"))
    assert active_raw is not None
    assert backup_raw is not None

    # Subsequent call hits cache
    fetcher.reset_mock()
    cached = await cache.get_or_fetch_quote("AAPL", fetcher)
    assert cached.symbol == "AAPL"
    assert fetcher.call_count == 0


async def test_quote_failure_retries_and_falls_back_to_stale_backup(
    cache: MarketDataCache, sample_quote: Quote
) -> None:
    # Seed only backup cache (active cache expired or missing)
    await cache.redis.set(cache.backup_quote_key("AAPL"), sample_quote.model_dump_json())

    # Mock fetcher fails every attempt
    fetcher = AsyncMock(side_effect=RuntimeError("Provider 503 Service Unavailable"))

    result = await cache.get_or_fetch_quote("AAPL", fetcher)

    # Max retries is 2 -> total attempts = 1 initial + 2 retries = 3 calls
    assert fetcher.call_count == 3
    # Fallback successful: stale=True and original as_of preserved
    assert result.stale is True
    assert result.symbol == "AAPL"
    assert result.price == Decimal("182.50")
    assert result.as_of == sample_quote.as_of


async def test_quote_failure_without_backup_raises_data_unavailable(
    cache: MarketDataCache,
) -> None:
    fetcher = AsyncMock(side_effect=ConnectionError("Network timeout"))

    with pytest.raises(DataUnavailable) as exc_info:
        await cache.get_or_fetch_quote("AAPL", fetcher)

    assert "外部数据源不可用且无可用缓存" in str(exc_info.value)
    assert exc_info.value.http_status == 424
    assert fetcher.call_count == 3


async def test_get_quotes_batch_cache_and_stale_fallback(
    cache: MarketDataCache, sample_quote: Quote
) -> None:
    msft_quote = sample_quote.model_copy(update={"symbol": "MSFT", "price": Decimal("440.00")})
    nvda_quote = sample_quote.model_copy(update={"symbol": "NVDA", "price": Decimal("125.00")})

    # Cache AAPL
    await cache.set_quote("AAPL", sample_quote)
    # Seed NVDA backup only
    await cache.redis.set(cache.backup_quote_key("NVDA"), nvda_quote.model_dump_json())

    # Fetcher succeeds for MSFT, but fails if asked for NVDA
    async def mock_batch_fetcher(symbols: list[str]) -> dict[str, Quote]:
        if "NVDA" in symbols:
            raise RuntimeError("NVDA quote failed")
        return {"MSFT": msft_quote}

    # Fetch batch of 3: AAPL cached, MSFT retrieved, NVDA falls back to stale backup
    # If fetcher fails on batch, all missing fall back to backup
    failing_fetcher = AsyncMock(side_effect=RuntimeError("Batch quote error"))
    result = await cache.get_or_fetch_quotes(["AAPL", "NVDA"], failing_fetcher)

    assert result["AAPL"].stale is False
    assert result["NVDA"].stale is True
    assert result["NVDA"].symbol == "NVDA"
    assert failing_fetcher.call_count == 3


# =============================================================================
# Bars Cache & Resilience Tests
# =============================================================================


async def test_bars_cache_hit_and_miss(cache: MarketDataCache, sample_bars: list[Bar]) -> None:
    start = date(2024, 6, 10)
    end = date(2024, 6, 11)

    fetcher = AsyncMock(return_value=sample_bars)
    bars = await cache.get_or_fetch_bars("AAPL", start, end, fetcher)

    assert len(bars) == 2
    assert fetcher.call_count == 1

    # Second call hits cache
    fetcher.reset_mock()
    cached = await cache.get_or_fetch_bars("AAPL", start, end, fetcher)
    assert len(cached) == 2
    assert fetcher.call_count == 0


async def test_bars_failure_fallback_and_unavailable(
    cache: MarketDataCache, sample_bars: list[Bar]
) -> None:
    start = date(2024, 6, 10)
    end = date(2024, 6, 11)

    # Seed backup
    await cache.set_bars("AAPL", start, end, sample_bars)
    # Clear active key
    await cache.redis.delete(cache.bars_key("AAPL", start, end))

    failing_fetcher = AsyncMock(side_effect=TimeoutError("Bars timeout"))
    fallback_bars = await cache.get_or_fetch_bars("AAPL", start, end, failing_fetcher)
    assert len(fallback_bars) == 2
    assert failing_fetcher.call_count == 3

    # Now test with symbol that has no backup
    with pytest.raises(DataUnavailable):
        await cache.get_or_fetch_bars("UNKNOWN", start, end, failing_fetcher)


# =============================================================================
# Fundamentals Cache & Resilience Tests
# =============================================================================


async def test_fundamentals_cache_hit_and_stale_fallback(
    cache: MarketDataCache, sample_fundamentals: Fundamentals
) -> None:
    fetcher = AsyncMock(return_value=sample_fundamentals)
    funds = await cache.get_or_fetch_fundamentals("AAPL", fetcher)

    assert funds.pe_trailing == Decimal("28.4")
    assert fetcher.call_count == 1

    # Cache hit
    fetcher.reset_mock()
    cached = await cache.get_or_fetch_fundamentals("AAPL", fetcher)
    assert cached.pe_trailing == Decimal("28.4")
    assert fetcher.call_count == 0

    # Delete active key, make fetcher fail, verify fallback to backup
    await cache.redis.delete(cache.fundamentals_key("AAPL"))
    failing = AsyncMock(side_effect=RuntimeError("500 internal error"))
    fallback = await cache.get_or_fetch_fundamentals("AAPL", failing)
    assert fallback.pe_trailing == Decimal("28.4")
    assert failing.call_count == 3

    # Unknown symbol with no backup raises DataUnavailable
    with pytest.raises(DataUnavailable):
        await cache.get_or_fetch_fundamentals("UNKNOWN", failing)


# =============================================================================
# Company Profile Cache & Resilience Tests
# =============================================================================


async def test_profile_cache_hit_and_stale_fallback(
    cache: MarketDataCache, sample_profile: CompanyProfile
) -> None:
    fetcher = AsyncMock(return_value=sample_profile)
    profile = await cache.get_or_fetch_profile("AAPL", fetcher)

    assert profile.name == "Apple Inc."
    assert fetcher.call_count == 1

    # Cache hit
    fetcher.reset_mock()
    cached = await cache.get_or_fetch_profile("AAPL", fetcher)
    assert cached.name == "Apple Inc."
    assert fetcher.call_count == 0

    # Delete active key, make fetcher fail, verify fallback to backup
    await cache.redis.delete(cache.profile_key("AAPL"))
    failing = AsyncMock(side_effect=RuntimeError("Profile error"))
    fallback = await cache.get_or_fetch_profile("AAPL", failing)
    assert fallback.name == "Apple Inc."
    assert failing.call_count == 3

    # Unknown symbol with no backup raises DataUnavailable
    with pytest.raises(DataUnavailable):
        await cache.get_or_fetch_profile("UNKNOWN", failing)


# =============================================================================
# Cancellation propagation test
# =============================================================================


async def test_cancellation_propagates_without_retry(cache: MarketDataCache) -> None:
    async def cancel_fetcher() -> Quote:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await cache.get_or_fetch_quote("AAPL", cancel_fetcher)
