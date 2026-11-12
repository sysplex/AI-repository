"""End-to-end integration acceptance tests for M2 Market Data module.

Verifies the complete market data lifecycle against docs/08-test-plan.md §5 M2:
1. Cold start retrieval -> Redis caching & DB persistence -> Cache hit with 0 external calls.
2. Corporate action stock split & historical price adjustment (NVDA 2024-06 10:1 split).
3. External provider outage & exponential backoff -> fallback to stale cache (`stale=True`).
4. Cold cache external failure -> HTTP 424 DATA_UNAVAILABLE.
5. AI Facts Snapshot (build_facts) deterministic SHA-256 content_hash and missing_fields tracking.
6. REST API full endpoint suite and validation error contracts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import DataUnavailable
from app.modules.marketdata.adapters.yfinance import YFinanceAdapter
from app.modules.marketdata.api import get_data_service
from app.modules.marketdata.cache import MarketDataCache
from app.modules.marketdata.models import (
    AnalystRatings,
    Bar,
    CompanyProfile,
    CorporateAction,
    EarningsHistory,
    FinancialStatements,
    Fundamentals,
    NewsItem,
    Quote,
)
from app.modules.marketdata.service import DataService
from app.modules.marketdata.tables import (
    BarDailyTable,
    DataSnapshotTable,
    FundamentalsSnapshotTable,
    NewsItemTable,
    SymbolTable,
)

pytestmark = pytest.mark.e2e

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "m2"


class SpyYFinanceAdapter:
    """Instrumented DataProvider wrapper tracking call invocations and simulating failures."""

    def __init__(self, fixture_dir: Path) -> None:
        self._real_adapter = YFinanceAdapter(fixture_dir=fixture_dir)
        self.name: str = self._real_adapter.name
        self.get_bars_calls: int = 0
        self.get_quote_calls: int = 0
        self.get_quotes_calls: int = 0
        self.get_fundamentals_calls: int = 0
        self.get_profile_calls: int = 0
        self.get_news_calls: int = 0
        self.get_universe_calls: int = 0
        self.get_corporate_actions_calls: int = 0
        self.simulate_failure: bool = False
        self.failure_exception: Exception = DataUnavailable("Upstream vendor connection timeout")

    async def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> Sequence[Bar]:
        if self.simulate_failure:
            raise self.failure_exception
        self.get_bars_calls += 1
        return await self._real_adapter.get_bars(symbol, start, end, interval, adjusted)

    async def get_quote(self, symbol: str) -> Quote:
        if self.simulate_failure:
            raise self.failure_exception
        self.get_quote_calls += 1
        return await self._real_adapter.get_quote(symbol)

    async def get_quotes(self, symbols: Sequence[str]) -> dict[str, Quote]:
        if self.simulate_failure:
            raise self.failure_exception
        self.get_quotes_calls += 1
        return await self._real_adapter.get_quotes(symbols)

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        if self.simulate_failure:
            raise self.failure_exception
        self.get_fundamentals_calls += 1
        return await self._real_adapter.get_fundamentals(symbol)

    async def get_profile(self, symbol: str) -> CompanyProfile:
        if self.simulate_failure:
            raise self.failure_exception
        self.get_profile_calls += 1
        return await self._real_adapter.get_profile(symbol)

    async def get_news(
        self,
        symbol: str,
        limit: int = 20,
        since: datetime | None = None,
    ) -> Sequence[NewsItem]:
        if self.simulate_failure:
            raise self.failure_exception
        self.get_news_calls += 1
        return await self._real_adapter.get_news(symbol, limit, since)

    async def get_universe(self, name: str) -> Sequence[str]:
        if self.simulate_failure:
            raise self.failure_exception
        self.get_universe_calls += 1
        return await self._real_adapter.get_universe(name)

    async def get_corporate_actions(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> Sequence[CorporateAction]:
        if self.simulate_failure:
            raise self.failure_exception
        self.get_corporate_actions_calls += 1
        return await self._real_adapter.get_corporate_actions(symbol, start, end)

    async def get_financial_statements(
        self,
        symbol: str,
        period: Literal["annual", "quarterly"] = "annual",
        limit: int = 10,
    ) -> FinancialStatements:
        return await self._real_adapter.get_financial_statements(symbol, period, limit)

    async def get_earnings(self, symbol: str, limit: int = 8) -> EarningsHistory:
        return await self._real_adapter.get_earnings(symbol, limit)

    async def get_analyst_ratings(self, symbol: str) -> AnalystRatings:
        return await self._real_adapter.get_analyst_ratings(symbol)


@pytest.fixture
def spy_provider() -> SpyYFinanceAdapter:
    """Fixture providing instrumented YFinanceAdapter with offline fixtures."""
    return SpyYFinanceAdapter(fixture_dir=FIXTURES_DIR)


@pytest.fixture
async def e2e_cache(redis: Any) -> AsyncIterator[MarketDataCache]:
    """Fixture providing isolated MarketDataCache with fast retries for e2e tests."""
    await redis.flushdb()
    cache = MarketDataCache(redis_client=redis, base_delay=0.01, max_retries=2)
    yield cache
    await redis.flushdb()


@pytest.fixture
def e2e_service(
    spy_provider: SpyYFinanceAdapter,
    e2e_cache: MarketDataCache,
) -> DataService:
    """DataService facade wiring spy provider and cache without persistence by default."""
    return DataService(
        provider=spy_provider,
        cache=e2e_cache,
    )


@pytest.fixture
async def e2e_client(
    app: FastAPI,
    e2e_service: DataService,
) -> AsyncIterator[httpx.AsyncClient]:
    """Configured test client pointing to FastAPI app with overridden DataService."""
    app.dependency_overrides[get_data_service] = lambda: e2e_service
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# =============================================================================
# 1. Cold Start & Cache Hit Verification
# =============================================================================


async def test_e2e_cold_start_and_cache_hit_lifecycle(
    e2e_client: httpx.AsyncClient,
    spy_provider: SpyYFinanceAdapter,
) -> None:
    """Verify cold start fetches from provider, caches in Redis, and second request hits cache."""
    # --- A. Historical Bars ---
    # First request: Cold start -> provider called
    resp1 = await e2e_client.get(
        "/api/v1/market/bars/AAPL",
        params={"start": "2026-11-08", "end": "2026-11-10"},
    )
    assert resp1.status_code == 200
    bars1 = resp1.json()
    assert len(bars1) == 3
    assert spy_provider.get_bars_calls == 1

    # Second request: Cache hit -> provider NOT called
    resp2 = await e2e_client.get(
        "/api/v1/market/bars/AAPL",
        params={"start": "2026-11-08", "end": "2026-11-10"},
    )
    assert resp2.status_code == 200
    bars2 = resp2.json()
    assert bars2 == bars1
    assert spy_provider.get_bars_calls == 1  # 0 additional external requests!

    # --- B. Realtime Quotes ---
    # First request: Cold start -> provider called
    resp_q1 = await e2e_client.get("/api/v1/market/quotes", params={"symbols": "AAPL,MSFT"})
    assert resp_q1.status_code == 200
    quotes1 = resp_q1.json()
    assert "AAPL" in quotes1
    assert "MSFT" in quotes1
    assert quotes1["AAPL"]["price"] == "224.23"
    assert quotes1["MSFT"]["price"] == "415.20"
    assert spy_provider.get_quotes_calls == 1

    # Second request: Cache hit -> provider NOT called
    resp_q2 = await e2e_client.get("/api/v1/market/quotes", params={"symbols": "AAPL,MSFT"})
    assert resp_q2.status_code == 200
    quotes2 = resp_q2.json()
    assert quotes2 == quotes1
    assert spy_provider.get_quotes_calls == 1  # 0 additional external requests!

    # --- C. Company Profile ---
    resp_p1 = await e2e_client.get("/api/v1/market/profile/AAPL")
    assert resp_p1.status_code == 200
    assert resp_p1.json()["name"] == "Apple Inc."
    assert spy_provider.get_profile_calls == 1

    resp_p2 = await e2e_client.get("/api/v1/market/profile/AAPL")
    assert resp_p2.status_code == 200
    assert resp_p2.json() == resp_p1.json()
    assert spy_provider.get_profile_calls == 1  # Cache hit!

    # --- D. Fundamentals ---
    resp_f1 = await e2e_client.get("/api/v1/market/fundamentals/AAPL")
    assert resp_f1.status_code == 200
    assert resp_f1.json()["pe_trailing"] == "34.2"
    assert spy_provider.get_fundamentals_calls == 1

    resp_f2 = await e2e_client.get("/api/v1/market/fundamentals/AAPL")
    assert resp_f2.status_code == 200
    assert resp_f2.json() == resp_f1.json()
    assert spy_provider.get_fundamentals_calls == 1  # Cache hit!


# =============================================================================
# 2. Corporate Actions & Stock Split Adjustment Verification (NVDA 10:1 Split)
# =============================================================================


async def test_e2e_nvda_split_and_adjustment_verification(
    e2e_client: httpx.AsyncClient,
    spy_provider: SpyYFinanceAdapter,
) -> None:
    """Verify NVDA 2024-06-10 10:1 stock split records and historical price adjustments."""
    # 1. Corporate Actions verification from provider
    actions = await spy_provider.get_corporate_actions(
        "NVDA",
        start=date(2024, 6, 1),
        end=date(2024, 6, 30),
    )
    assert len(actions) == 1
    split_action = actions[0]
    assert split_action.symbol == "NVDA"
    assert split_action.ex_date == date(2024, 6, 10)
    assert split_action.action_type == "split"
    assert split_action.ratio == Decimal("10.0")

    # 2. Historical bars with adjusted prices (adjusted=True)
    resp_adj = await e2e_client.get(
        "/api/v1/market/bars/NVDA",
        params={"start": "2024-06-07", "end": "2024-06-10", "adjusted": "true"},
    )
    assert resp_adj.status_code == 200
    bars = resp_adj.json()
    assert len(bars) == 2

    # Bar 0: 2024-06-07 (Friday, pre-split day)
    # Unadjusted close: 1208.88; Adjusted close: 120.888 -> exactly 10x
    pre_split_bar = bars[0]
    assert pre_split_bar["trade_date"] == "2024-06-07"
    assert pre_split_bar["close"] == "1208.88"
    assert pre_split_bar["adj_close"] == "120.888"
    close_val = Decimal(pre_split_bar["close"])
    adj_close_val = Decimal(pre_split_bar["adj_close"])
    assert (close_val / adj_close_val).quantize(Decimal("0.1")) == Decimal("10.0")

    # Bar 1: 2024-06-10 (Monday, split effective ex-date)
    # Both close and adj_close reflect the post-split quotation (121.79)
    post_split_bar = bars[1]
    assert post_split_bar["trade_date"] == "2024-06-10"
    assert post_split_bar["close"] == "121.79"
    assert post_split_bar["adj_close"] == "121.79"
    assert post_split_bar["volume"] == 423000000

    # 3. Historical bars unadjusted (adjusted=False)
    resp_unadj = await e2e_client.get(
        "/api/v1/market/bars/NVDA",
        params={"start": "2024-06-07", "end": "2024-06-10", "adjusted": "false"},
    )
    assert resp_unadj.status_code == 200
    unadj_bars = resp_unadj.json()
    assert len(unadj_bars) == 2
    assert unadj_bars[0]["trade_date"] == "2024-06-07"
    assert unadj_bars[0]["close"] == "1208.88"
    assert unadj_bars[0]["adj_close"] is None


# =============================================================================
# 3. External Failure, Exponential Backoff & Degraded Fallback (stale=True / 424)
# =============================================================================


async def test_e2e_external_failure_and_stale_fallback(
    e2e_client: httpx.AsyncClient,
    spy_provider: SpyYFinanceAdapter,
    e2e_cache: MarketDataCache,
) -> None:
    """Verify warm cache falls back to stale=True on failure, and cold cache yields 424."""
    # Step 1: Warm up cache for AAPL quote
    warm_resp = await e2e_client.get("/api/v1/market/quotes", params={"symbols": "AAPL"})
    assert warm_resp.status_code == 200
    initial_quote = warm_resp.json()["AAPL"]
    assert initial_quote["price"] == "224.23"
    assert initial_quote["stale"] is False

    # Step 2: Trigger external provider outage
    spy_provider.simulate_failure = True
    spy_provider.failure_exception = DataUnavailable("Upstream market vendor connection timeout")

    # Step 3: Expire active cache key (simulating TTL expiration) while backup key remains
    await e2e_cache.redis.delete(e2e_cache.quote_key("AAPL"))

    # Step 4: Query AAPL during outage -> Degraded fallback succeeds with stale=True
    degraded_resp = await e2e_client.get("/api/v1/market/quotes", params={"symbols": "AAPL"})
    assert degraded_resp.status_code == 200
    fallback_quote = degraded_resp.json()["AAPL"]
    assert fallback_quote["price"] == "224.23"
    assert fallback_quote["stale"] is True  # Stale indicator successfully attached!

    # Step 5: Query uncached symbol during outage -> Returns HTTP 424 DATA_UNAVAILABLE
    uncached_resp = await e2e_client.get(
        "/api/v1/market/quotes",
        params={"symbols": "UNKNOWN_TICKER"},
    )
    assert uncached_resp.status_code == 424
    err_body = uncached_resp.json()
    assert err_body["error"]["code"] == "DATA_UNAVAILABLE"
    msg = err_body["error"]["message"].lower()
    assert "不可用" in err_body["error"]["message"] or "unavailable" in msg


# =============================================================================
# 4. AI Facts Snapshot (build_facts) Determinism & Missing Fields Tracking
# =============================================================================


async def test_e2e_build_facts_snapshot_determinism(
    e2e_client: httpx.AsyncClient,
) -> None:
    """Verify build_facts produces deterministic SHA-256 content_hash and structured facts."""
    request_payload = {"scope": ["quote", "profile", "fundamentals", "bars"]}

    # First request
    resp1 = await e2e_client.post("/api/v1/market/facts/NVDA", json=request_payload)
    assert resp1.status_code == 200
    snap1 = resp1.json()

    assert snap1["symbol"] == "NVDA"
    assert len(snap1["content_hash"]) == 64  # SHA-256 hex string length
    assert "quote" in snap1["facts"]
    assert "profile" in snap1["facts"]
    assert "fundamentals" in snap1["facts"]
    assert "bars" in snap1["facts"]
    assert isinstance(snap1["missing_fields"], list)

    # Second request: exact same parameters produce identical content_hash
    resp2 = await e2e_client.post("/api/v1/market/facts/NVDA", json=request_payload)
    assert resp2.status_code == 200
    snap2 = resp2.json()

    assert snap1["content_hash"] == snap2["content_hash"]
    assert snap1["as_of"] == snap2["as_of"]
    assert snap1["facts"] == snap2["facts"]


async def test_e2e_build_facts_missing_fields_handling(
    spy_provider: SpyYFinanceAdapter,
    e2e_cache: MarketDataCache,
) -> None:
    """Verify build_facts sets missing scope values to null and tracks in missing_fields."""
    # Create service where fundamentals retrieval fails
    failing_provider = AsyncMock()
    failing_provider.name = "failing_mock"
    failing_provider.get_quote.return_value = Quote(
        symbol="SYM",
        price=Decimal("100.00"),
        change=Decimal("0.00"),
        change_pct=Decimal("0.00"),
        volume=1000,
        as_of=datetime(2026, 11, 10, 20, 0, 0, tzinfo=UTC),
        delayed_seconds=0,
        stale=False,
    )
    failing_provider.get_profile.return_value = CompanyProfile(
        symbol="SYM",
        name="Sym Corp",
        exchange="NYSE",
        sector="Industrials",
        industry="Machinery",
        description="Sample corp",
        website=None,  # Missing field
        employees=None,  # Missing field
        country="US",
    )
    failing_provider.get_fundamentals.side_effect = DataUnavailable("Fundamentals not filed")
    failing_provider.get_bars.return_value = []

    service = DataService(provider=failing_provider, cache=e2e_cache)
    snapshot = await service.build_facts("SYM", scope=["quote", "profile", "fundamentals", "bars"])

    # Fundamentals failed -> must be null in facts and present in missing_fields
    assert snapshot.facts["fundamentals"] is None
    assert "fundamentals" in snapshot.missing_fields

    # Missing profile fields -> tracked in missing_fields
    assert "profile.website" in snapshot.missing_fields
    assert "profile.employees" in snapshot.missing_fields

    # Succeeded scopes populated
    assert snapshot.facts["quote"] is not None
    assert snapshot.facts["quote"]["price"] == "100.00"
    assert len(snapshot.content_hash) == 64


# =============================================================================
# 5. REST API Full Endpoint Suite & Error Contracts
# =============================================================================


async def test_e2e_all_rest_api_endpoints_and_validation_errors(
    e2e_client: httpx.AsyncClient,
) -> None:
    """Verify all /api/v1/market/* endpoints respond correctly and handle invalid inputs."""
    # 1. Quotes
    q_resp = await e2e_client.get("/api/v1/market/quotes", params={"symbols": "AAPL,MSFT,NVDA"})
    assert q_resp.status_code == 200
    quotes = q_resp.json()
    assert set(quotes.keys()) == {"AAPL", "MSFT", "NVDA"}

    # 2. Profile
    p_resp = await e2e_client.get("/api/v1/market/profile/NVDA")
    assert p_resp.status_code == 200
    profile = p_resp.json()
    assert profile["name"] == "NVIDIA Corporation"
    assert profile["sector"] == "Technology"

    # 3. Fundamentals
    f_resp = await e2e_client.get("/api/v1/market/fundamentals/NVDA")
    assert f_resp.status_code == 200
    funds = f_resp.json()
    assert funds["pe_trailing"] == "58.4"
    assert funds["market_cap"] == "3500000000000"

    # 4. News
    n_resp = await e2e_client.get("/api/v1/market/news/NVDA", params={"limit": 5})
    assert n_resp.status_code == 200
    news = n_resp.json()
    assert len(news) >= 1
    assert "Blackwell" in news[0]["title"]
    assert news[0]["source"] == "TechCrunch"

    # 5. Universe
    u_resp = await e2e_client.get("/api/v1/market/universe/sp500")
    assert u_resp.status_code == 200
    universe = u_resp.json()
    assert "AAPL" in universe
    assert "NVDA" in universe
    assert "MSFT" in universe

    # 6. Validation Error: Empty symbols parameter -> HTTP 400
    bad_q_resp = await e2e_client.get("/api/v1/market/quotes", params={"symbols": ""})
    assert bad_q_resp.status_code == 400
    bad_q_err = bad_q_resp.json()
    assert bad_q_err["error"]["code"] == "VALIDATION_ERROR"

    # 7. Validation Error: Invalid bar date range (start > end) -> HTTP 400
    bad_bars_resp = await e2e_client.get(
        "/api/v1/market/bars/AAPL",
        params={"start": "2026-11-15", "end": "2026-11-01"},
    )
    assert bad_bars_resp.status_code == 400
    bad_bars_err = bad_bars_resp.json()
    assert bad_bars_err["error"]["code"] == "VALIDATION_ERROR"


# =============================================================================
# 6. Database Persistence End-to-End Verification
# =============================================================================


async def test_e2e_database_persistence_via_session_factory(
    spy_provider: SpyYFinanceAdapter,
    e2e_cache: MarketDataCache,
) -> None:
    """Verify DataService persists entities and snapshots when session_factory is provided."""
    persisted_records: list[Any] = []
    mock_session = AsyncMock()
    mock_session.get.return_value = None  # Simulates new records
    mock_session.add = MagicMock(side_effect=lambda record: persisted_records.append(record))

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = mock_session

    service = DataService(
        provider=spy_provider,
        cache=e2e_cache,
        session_factory=mock_factory,
    )

    # 1. Fetch bars -> persists BarDailyTable
    bars = await service.get_bars("AAPL", start=date(2026, 11, 8), end=date(2026, 11, 10))
    assert len(bars) == 3
    persisted_bars = [r for r in persisted_records if isinstance(r, BarDailyTable)]
    assert len(persisted_bars) == 3
    assert {b.trade_date for b in persisted_bars} == {
        date(2026, 11, 8),
        date(2026, 11, 9),
        date(2026, 11, 10),
    }

    # 2. Fetch profile -> persists SymbolTable
    profile = await service.get_profile("NVDA")
    assert profile.name == "NVIDIA Corporation"
    persisted_symbols = [r for r in persisted_records if isinstance(r, SymbolTable)]
    assert len(persisted_symbols) == 1
    assert persisted_symbols[0].symbol == "NVDA"

    # 3. Fetch fundamentals -> persists FundamentalsSnapshotTable
    funds = await service.get_fundamentals("NVDA")
    assert funds.pe_trailing == Decimal("58.4")
    persisted_funds = [r for r in persisted_records if isinstance(r, FundamentalsSnapshotTable)]
    assert len(persisted_funds) == 1
    assert persisted_funds[0].symbol == "NVDA"

    # 4. Fetch news -> persists NewsItemTable
    news = await service.get_news("NVDA", limit=5)
    assert len(news) >= 1
    persisted_news = [r for r in persisted_records if isinstance(r, NewsItemTable)]
    assert len(persisted_news) >= 1
    assert persisted_news[0].symbol == "NVDA"

    # 5. Build facts snapshot -> persists DataSnapshotTable
    snapshot = await service.build_facts("NVDA", scope=["quote", "profile"])
    persisted_snaps = [r for r in persisted_records if isinstance(r, DataSnapshotTable)]
    assert len(persisted_snaps) == 1
    assert persisted_snaps[0].content_hash == snapshot.content_hash
    assert persisted_snaps[0].symbol == "NVDA"

    # Verify session commit was called for every persistence transaction
    assert mock_session.commit.call_count >= 5


async def test_e2e_database_persistence_live_session(
    db_session: AsyncSession,
    spy_provider: SpyYFinanceAdapter,
    e2e_cache: MarketDataCache,
) -> None:
    """Verify live PostgreSQL persistence roundtrip when db_session fixture is available."""
    # Wire session_factory using the current transaction session
    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

    service = DataService(
        provider=spy_provider,
        cache=e2e_cache,
        session_factory=session_factory,
    )

    # 1. Fetch bars and verify in live database
    bars = await service.get_bars("AAPL", start=date(2026, 11, 8), end=date(2026, 11, 10))
    assert len(bars) == 3

    # Query directly from DB
    bar_stmt = (
        select(BarDailyTable)
        .where(BarDailyTable.symbol == "AAPL")
        .order_by(BarDailyTable.trade_date)
    )
    result = await db_session.execute(bar_stmt)
    db_bars = result.scalars().all()
    assert len(db_bars) == 3
    assert db_bars[0].close == Decimal("222.700000")

    # 2. Build facts and verify DataSnapshotTable record in live database
    snapshot = await service.build_facts("AAPL", scope=["quote", "profile"])
    snap_result = await db_session.execute(
        select(DataSnapshotTable).where(DataSnapshotTable.content_hash == snapshot.content_hash)
    )
    db_snap = snap_result.scalar_one_or_none()
    assert db_snap is not None
    assert db_snap.symbol == "AAPL"
    assert db_snap.facts["quote"]["price"] == "224.23"
