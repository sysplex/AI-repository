"""Integration tests for Market Data REST API endpoints (M2 / T06)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.core.errors import DataUnavailable
from app.modules.marketdata.api import get_data_service
from app.modules.marketdata.models import (
    Bar,
    CompanyProfile,
    FactsSnapshot,
    Fundamentals,
    NewsItem,
    Quote,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_service() -> AsyncMock:
    service = AsyncMock()

    sample_quote = Quote(
        symbol="AAPL",
        price=Decimal("182.50"),
        change=Decimal("1.25"),
        change_pct=Decimal("0.69"),
        volume=54321000,
        as_of=datetime(2024, 6, 12, 14, 0, 0, tzinfo=UTC),
        delayed_seconds=0,
        stale=False,
    )
    service.get_quotes.return_value = {"AAPL": sample_quote}
    service.get_quote.return_value = sample_quote

    sample_bars = [
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
    service.get_bars.return_value = sample_bars

    sample_profile = CompanyProfile(
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
    service.get_profile.return_value = sample_profile

    sample_fundamentals = Fundamentals(
        symbol="AAPL",
        as_of=date(2024, 6, 1),
        pe_trailing=Decimal("28.4"),
        pe_forward=Decimal("25.1"),
        market_cap=Decimal("2800000000000"),
        missing_fields=[],
    )
    service.get_fundamentals.return_value = sample_fundamentals

    sample_news = [
        NewsItem(
            id="news-1",
            symbol="AAPL",
            title="Apple announces new product",
            summary="WWDC updates.",
            source="Reuters",
            url="https://reuters.com/news-1",
            published_at=datetime(2024, 6, 12, 10, 0, 0, tzinfo=UTC),
        )
    ]
    service.get_news.return_value = sample_news

    service.get_universe.return_value = ["AAPL", "MSFT", "NVDA"]

    sample_facts = FactsSnapshot(
        content_hash="a" * 64,
        symbol="AAPL",
        as_of=datetime(2024, 6, 12, 14, 0, 0, tzinfo=UTC),
        scope=["quote", "profile", "fundamentals", "bars"],
        facts={"quote": {"price": "182.50"}},
        missing_fields=[],
    )
    service.build_facts.return_value = sample_facts

    return service


# =============================================================================
# REST Endpoints Happy Paths
# =============================================================================


async def test_get_quotes_endpoint(
    app: FastAPI, client: httpx.AsyncClient, mock_service: AsyncMock
) -> None:
    app.dependency_overrides[get_data_service] = lambda: mock_service

    response = await client.get("/api/v1/market/quotes?symbols=AAPL")
    assert response.status_code == 200
    data = response.json()
    assert "AAPL" in data
    assert data["AAPL"]["symbol"] == "AAPL"
    assert data["AAPL"]["price"] == "182.50"
    assert data["AAPL"]["stale"] is False
    mock_service.get_quotes.assert_awaited_once_with(["AAPL"])


async def test_get_quotes_validation_error_on_empty(
    app: FastAPI, client: httpx.AsyncClient, mock_service: AsyncMock
) -> None:
    app.dependency_overrides[get_data_service] = lambda: mock_service

    response = await client.get("/api/v1/market/quotes?symbols= , ")
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


async def test_get_bars_endpoint(
    app: FastAPI, client: httpx.AsyncClient, mock_service: AsyncMock
) -> None:
    app.dependency_overrides[get_data_service] = lambda: mock_service

    response = await client.get("/api/v1/market/bars/AAPL?start=2024-06-01&end=2024-06-10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["close"] == "182.00"
    mock_service.get_bars.assert_awaited_once_with(
        symbol="AAPL",
        start=date(2024, 6, 1),
        end=date(2024, 6, 10),
        interval="1d",
        adjusted=True,
    )


async def test_get_bars_date_range_validation(
    app: FastAPI, client: httpx.AsyncClient, mock_service: AsyncMock
) -> None:
    app.dependency_overrides[get_data_service] = lambda: mock_service

    # start > end
    response = await client.get("/api/v1/market/bars/AAPL?start=2024-06-10&end=2024-06-01")
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


async def test_get_profile_endpoint(
    app: FastAPI, client: httpx.AsyncClient, mock_service: AsyncMock
) -> None:
    app.dependency_overrides[get_data_service] = lambda: mock_service

    response = await client.get("/api/v1/market/profile/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "AAPL"
    assert data["name"] == "Apple Inc."
    mock_service.get_profile.assert_awaited_once_with("AAPL")


async def test_get_fundamentals_endpoint(
    app: FastAPI, client: httpx.AsyncClient, mock_service: AsyncMock
) -> None:
    app.dependency_overrides[get_data_service] = lambda: mock_service

    response = await client.get("/api/v1/market/fundamentals/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "AAPL"
    assert data["pe_trailing"] == "28.4"
    mock_service.get_fundamentals.assert_awaited_once_with("AAPL")


async def test_get_news_endpoint(
    app: FastAPI, client: httpx.AsyncClient, mock_service: AsyncMock
) -> None:
    app.dependency_overrides[get_data_service] = lambda: mock_service

    response = await client.get("/api/v1/market/news/AAPL?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["source"] == "Reuters"
    mock_service.get_news.assert_awaited_once_with("AAPL", limit=10)


async def test_get_universe_endpoint(
    app: FastAPI, client: httpx.AsyncClient, mock_service: AsyncMock
) -> None:
    app.dependency_overrides[get_data_service] = lambda: mock_service

    response = await client.get("/api/v1/market/universe/sp500")
    assert response.status_code == 200
    data = response.json()
    assert "AAPL" in data
    mock_service.get_universe.assert_awaited_once_with("sp500")


async def test_build_facts_endpoint(
    app: FastAPI, client: httpx.AsyncClient, mock_service: AsyncMock
) -> None:
    app.dependency_overrides[get_data_service] = lambda: mock_service

    # POST without body
    res1 = await client.post("/api/v1/market/facts/AAPL")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["symbol"] == "AAPL"
    assert len(data1["content_hash"]) == 64
    mock_service.build_facts.assert_awaited_with("AAPL", scope=None)

    # POST with custom scope
    res2 = await client.post("/api/v1/market/facts/AAPL", json={"scope": ["quote", "profile"]})
    assert res2.status_code == 200
    mock_service.build_facts.assert_awaited_with("AAPL", scope=["quote", "profile"])


# =============================================================================
# Error Handling & OpenAPI Schema
# =============================================================================


async def test_data_unavailable_returns_http_424(
    app: FastAPI, client: httpx.AsyncClient, mock_service: AsyncMock
) -> None:
    mock_service.get_quotes.side_effect = DataUnavailable("外部数据源不可用且无可用缓存: UNKNOWN")
    app.dependency_overrides[get_data_service] = lambda: mock_service

    response = await client.get("/api/v1/market/quotes?symbols=UNKNOWN")
    assert response.status_code == 424
    data = response.json()
    assert data["error"]["code"] == "DATA_UNAVAILABLE"
    assert "外部数据源不可用且无可用缓存" in data["error"]["message"]
    assert "request_id" in data["error"]


async def test_openapi_schema_contains_market_routes(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema.get("paths", {})

    expected_routes = [
        "/api/v1/market/quotes",
        "/api/v1/market/bars/{symbol}",
        "/api/v1/market/profile/{symbol}",
        "/api/v1/market/fundamentals/{symbol}",
        "/api/v1/market/news/{symbol}",
        "/api/v1/market/universe/{name}",
        "/api/v1/market/facts/{symbol}",
    ]
    for route in expected_routes:
        assert route in paths, f"Route {route} missing from OpenAPI schema"
