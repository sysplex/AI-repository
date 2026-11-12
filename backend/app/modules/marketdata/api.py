"""REST API endpoints for marketdata module (M2 / T06).

Provides HTTP endpoints mounted under `/api/v1/market/*` according to
`docs/05-api-spec.md §2.2` and `docs/tasks/M2/CONTRACTS.md §7`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.core.errors import ValidationFailed
from app.modules.marketdata.models import (
    Bar,
    CompanyProfile,
    FactsSnapshot,
    Fundamentals,
    NewsItem,
    Quote,
)
from app.modules.marketdata.service import DataService

router = APIRouter()

_data_service: DataService | None = None


def get_data_service() -> DataService:
    """Dependency provider for DataService."""
    global _data_service
    if _data_service is None:
        from app.core.db import get_session_factory
        from app.core.redis import get_redis
        from app.modules.marketdata.adapters.yfinance import YFinanceAdapter
        from app.modules.marketdata.cache import MarketDataCache

        provider = YFinanceAdapter()
        cache = MarketDataCache(redis_client=get_redis())
        session_factory = get_session_factory()
        _data_service = DataService(
            provider=provider,
            cache=cache,
            session_factory=session_factory,
        )
    return _data_service


class BuildFactsRequest(BaseModel):
    """Optional request body payload specifying scopes for facts snapshot."""

    model_config = ConfigDict(frozen=True)

    scope: list[str] | None = None


@router.get("/quotes", response_model=dict[str, Quote])
async def get_quotes(
    symbols: Annotated[str, Query(description="Comma-separated stock symbols, e.g. AAPL,MSFT")],
    service: Annotated[DataService, Depends(get_data_service)],
) -> dict[str, Quote]:
    """Retrieve realtime quotes for one or more stock symbols."""
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise ValidationFailed("At least one symbol must be provided")
    return await service.get_quotes(symbol_list)


@router.get("/bars/{symbol}", response_model=list[Bar])
async def get_bars(
    symbol: str,
    start: Annotated[date, Query(description="Start date (YYYY-MM-DD)")],
    end: Annotated[date, Query(description="End date (YYYY-MM-DD)")],
    service: Annotated[DataService, Depends(get_data_service)],
    interval: Annotated[str, Query(description="Candlestick bar interval")] = "1d",
    adjusted: Annotated[bool, Query(description="Whether prices are adjusted")] = True,
) -> Sequence[Bar]:
    """Retrieve historical candlestick bars."""
    if start > end:
        raise ValidationFailed("start date cannot be after end date")
    return await service.get_bars(
        symbol=symbol,
        start=start,
        end=end,
        interval=interval,
        adjusted=adjusted,
    )


@router.get("/profile/{symbol}", response_model=CompanyProfile)
async def get_profile(
    symbol: str,
    service: Annotated[DataService, Depends(get_data_service)],
) -> CompanyProfile:
    """Retrieve company background, sector, and industry classification."""
    return await service.get_profile(symbol)


@router.get("/fundamentals/{symbol}", response_model=Fundamentals)
async def get_fundamentals(
    symbol: str,
    service: Annotated[DataService, Depends(get_data_service)],
) -> Fundamentals:
    """Retrieve company valuation and financial profitability metrics."""
    return await service.get_fundamentals(symbol)


@router.get("/news/{symbol}", response_model=list[NewsItem])
async def get_news(
    symbol: str,
    service: Annotated[DataService, Depends(get_data_service)],
    limit: Annotated[int, Query(ge=1, le=100, description="Max news items")] = 20,
) -> Sequence[NewsItem]:
    """Retrieve latest financial news articles for a symbol."""
    return await service.get_news(symbol, limit=limit)


@router.get("/universe/{name}", response_model=list[str])
async def get_universe(
    name: str,
    service: Annotated[DataService, Depends(get_data_service)],
) -> Sequence[str]:
    """Retrieve constituents of an equity universe (e.g. sp500, nasdaq100)."""
    return await service.get_universe(name)


@router.post("/facts/{symbol}", response_model=FactsSnapshot)
async def build_facts(
    symbol: str,
    service: Annotated[DataService, Depends(get_data_service)],
    payload: BuildFactsRequest | None = None,
) -> FactsSnapshot:
    """Build and persist deterministic AI market fact snapshot with SHA-256 hash."""
    scope = payload.scope if payload is not None else None
    return await service.build_facts(symbol, scope=scope)
