"""Core market data facade service and facts aggregator (M2 / T05).

Provides high-level data orchestration integrating provider adapters,
Redis caching, database persistence, and deterministic AI facts snapshots.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.core.clock import get_clock
from app.core.logging import get_logger
from app.modules.marketdata.cache import MarketDataCache
from app.modules.marketdata.models import (
    Bar,
    CompanyProfile,
    FactsSnapshot,
    Fundamentals,
    NewsItem,
    Quote,
)
from app.modules.marketdata.ports import DataProvider
from app.modules.marketdata.tables import (
    BarDailyTable,
    DataSnapshotTable,
    FundamentalsSnapshotTable,
    NewsItemTable,
    SymbolTable,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

DEFAULT_FACTS_SCOPE: list[str] = ["quote", "profile", "fundamentals", "bars"]


class DataService:
    """Core market data service orchestrating providers, caching, and persistence."""

    def __init__(
        self,
        provider: DataProvider,
        cache: MarketDataCache | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._session_factory = session_factory

    # -------------------------------------------------------------------------
    # Core Market Data Retrieval
    # -------------------------------------------------------------------------

    async def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> Sequence[Bar]:
        """Fetch historical candlestick bars with caching and persistence."""
        sym = symbol.upper()
        if self._cache is not None:
            bars = await self._cache.get_or_fetch_bars(
                sym,
                start,
                end,
                lambda: self._provider.get_bars(sym, start, end, interval, adjusted),
                interval=interval,
                adjusted=adjusted,
            )
        else:
            bars = await self._provider.get_bars(sym, start, end, interval, adjusted)

        if self._session_factory is not None and bars:
            await self._persist_bars(bars)
        return bars

    async def get_quote(self, symbol: str) -> Quote:
        """Fetch quote with caching and stale fallback."""
        sym = symbol.upper()
        if self._cache is not None:
            return await self._cache.get_or_fetch_quote(
                sym,
                lambda: self._provider.get_quote(sym),
            )
        return await self._provider.get_quote(sym)

    async def get_quotes(self, symbols: Sequence[str]) -> dict[str, Quote]:
        """Batch fetch quotes with cache optimization."""
        upper_symbols = [s.upper() for s in symbols]
        if self._cache is not None:
            return await self._cache.get_or_fetch_quotes(
                upper_symbols,
                lambda syms: self._provider.get_quotes(syms),
            )
        return await self._provider.get_quotes(upper_symbols)

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        """Fetch fundamental valuation and profitability metrics."""
        sym = symbol.upper()
        if self._cache is not None:
            funds = await self._cache.get_or_fetch_fundamentals(
                sym,
                lambda: self._provider.get_fundamentals(sym),
            )
        else:
            funds = await self._provider.get_fundamentals(sym)

        if self._session_factory is not None:
            await self._persist_fundamentals(funds)
        return funds

    async def get_profile(self, symbol: str) -> CompanyProfile:
        """Fetch company background and sector classification."""
        sym = symbol.upper()
        if self._cache is not None:
            profile = await self._cache.get_or_fetch_profile(
                sym,
                lambda: self._provider.get_profile(sym),
            )
        else:
            profile = await self._provider.get_profile(sym)

        if self._session_factory is not None:
            await self._persist_profile(profile)
        return profile

    async def get_news(
        self,
        symbol: str,
        limit: int = 20,
        since: datetime | None = None,
    ) -> Sequence[NewsItem]:
        """Fetch latest news items for a symbol."""
        sym = symbol.upper()
        news = await self._provider.get_news(sym, limit=limit, since=since)
        if self._session_factory is not None and news:
            await self._persist_news(news)
        return news

    async def get_universe(self, name: str) -> Sequence[str]:
        """Fetch index universe constituents."""
        return await self._provider.get_universe(name)

    # -------------------------------------------------------------------------
    # AI Facts Snapshot Aggregation
    # -------------------------------------------------------------------------

    async def build_facts(
        self,
        symbol: str,
        scope: Sequence[str] | None = None,
    ) -> FactsSnapshot:
        """Aggregate structured market facts, track missing fields, and compute SHA-256."""
        sym = symbol.upper()
        scope_list = list(scope) if scope is not None else list(DEFAULT_FACTS_SCOPE)
        facts: dict[str, Any] = {}
        missing_fields: list[str] = []
        quote_as_of: datetime | None = None

        if "quote" in scope_list:
            try:
                quote = await self.get_quote(sym)
                facts["quote"] = quote.model_dump(mode="json")
                quote_as_of = quote.as_of
            except Exception as exc:
                logger.warning("build_facts_quote_unavailable", symbol=sym, error=str(exc))
                facts["quote"] = None
                missing_fields.append("quote")

        if "profile" in scope_list:
            try:
                profile = await self.get_profile(sym)
                facts["profile"] = profile.model_dump(mode="json")
                for field_name in ["website", "employees"]:
                    if getattr(profile, field_name) is None:
                        missing_fields.append(f"profile.{field_name}")
            except Exception as exc:
                logger.warning("build_facts_profile_unavailable", symbol=sym, error=str(exc))
                facts["profile"] = None
                missing_fields.append("profile")

        if "fundamentals" in scope_list:
            try:
                funds = await self.get_fundamentals(sym)
                facts["fundamentals"] = funds.model_dump(mode="json")
                for field_name in [
                    "pe_trailing",
                    "pe_forward",
                    "pb",
                    "ps",
                    "roe",
                    "net_margin",
                    "debt_to_equity",
                    "market_cap",
                    "dividend_yield",
                    "beta",
                ]:
                    if getattr(funds, field_name) is None:
                        missing_fields.append(f"fundamentals.{field_name}")
            except Exception as exc:
                logger.warning("build_facts_fundamentals_unavailable", symbol=sym, error=str(exc))
                facts["fundamentals"] = None
                missing_fields.append("fundamentals")

        if "bars" in scope_list:
            try:
                end_date = get_clock().now().date()
                start_date = end_date - timedelta(days=30)
                bars = await self.get_bars(sym, start=start_date, end=end_date)
                if bars:
                    facts["bars"] = [b.model_dump(mode="json") for b in bars]
                else:
                    facts["bars"] = []
                    missing_fields.append("bars")
            except Exception as exc:
                logger.warning("build_facts_bars_unavailable", symbol=sym, error=str(exc))
                facts["bars"] = None
                missing_fields.append("bars")

        if "news" in scope_list:
            try:
                news = await self.get_news(sym, limit=10)
                facts["news"] = [n.model_dump(mode="json") for n in news]
            except Exception as exc:
                logger.warning("build_facts_news_unavailable", symbol=sym, error=str(exc))
                facts["news"] = None
                missing_fields.append("news")

        as_of = quote_as_of if quote_as_of is not None else get_clock().now().astimezone(UTC)

        # Deterministic canonical JSON and SHA-256 hash
        canonical = {
            "as_of": as_of.isoformat(),
            "facts": facts,
            "missing_fields": sorted(missing_fields),
            "scope": sorted(scope_list),
            "symbol": sym,
        }
        canonical_str = json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        content_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

        snapshot = FactsSnapshot(
            content_hash=content_hash,
            symbol=sym,
            as_of=as_of,
            scope=scope_list,
            facts=facts,
            missing_fields=sorted(missing_fields),
        )

        if self._session_factory is not None:
            await self._persist_snapshot(snapshot)

        return snapshot

    # -------------------------------------------------------------------------
    # Database Persistence Helpers (Fault-Tolerant)
    # -------------------------------------------------------------------------

    async def _persist_snapshot(self, snapshot: FactsSnapshot) -> None:
        if self._session_factory is None:
            return
        try:
            async with self._session_factory() as session:
                existing = await session.get(DataSnapshotTable, snapshot.content_hash)
                if existing is None:
                    record = DataSnapshotTable(
                        content_hash=snapshot.content_hash,
                        symbol=snapshot.symbol,
                        as_of=snapshot.as_of,
                        scope=snapshot.scope,
                        facts=snapshot.facts,
                        missing_fields=snapshot.missing_fields,
                    )
                    session.add(record)
                    await session.commit()
        except Exception as exc:
            logger.warning(
                "marketdata_snapshot_persist_failed",
                content_hash=snapshot.content_hash,
                symbol=snapshot.symbol,
                error=str(exc),
            )

    async def _persist_bars(self, bars: Sequence[Bar]) -> None:
        if self._session_factory is None:
            return
        try:
            async with self._session_factory() as session:
                for bar in bars:
                    existing = await session.get(BarDailyTable, (bar.symbol, bar.trade_date))
                    if existing is None:
                        session.add(
                            BarDailyTable(
                                symbol=bar.symbol,
                                trade_date=bar.trade_date,
                                open=bar.open,
                                high=bar.high,
                                low=bar.low,
                                close=bar.close,
                                volume=bar.volume,
                                adj_close=bar.adj_close,
                            )
                        )
                    else:
                        existing.open = bar.open
                        existing.high = bar.high
                        existing.low = bar.low
                        existing.close = bar.close
                        existing.volume = bar.volume
                        existing.adj_close = bar.adj_close
                await session.commit()
        except Exception as exc:
            logger.warning("marketdata_bars_persist_failed", error=str(exc))

    async def _persist_profile(self, profile: CompanyProfile) -> None:
        if self._session_factory is None:
            return
        try:
            async with self._session_factory() as session:
                existing = await session.get(SymbolTable, profile.symbol)
                if existing is None:
                    session.add(
                        SymbolTable(
                            symbol=profile.symbol,
                            name=profile.name,
                            exchange=profile.exchange,
                            sector=profile.sector,
                            industry=profile.industry,
                            status="active",
                        )
                    )
                else:
                    existing.name = profile.name
                    existing.exchange = profile.exchange
                    existing.sector = profile.sector
                    existing.industry = profile.industry
                await session.commit()
        except Exception as exc:
            logger.warning("marketdata_profile_persist_failed", error=str(exc))

    async def _persist_fundamentals(self, fundamentals: Fundamentals) -> None:
        if self._session_factory is None:
            return
        try:
            async with self._session_factory() as session:
                existing = await session.get(
                    FundamentalsSnapshotTable, (fundamentals.symbol, fundamentals.as_of)
                )
                if existing is None:
                    session.add(
                        FundamentalsSnapshotTable(
                            symbol=fundamentals.symbol,
                            as_of=fundamentals.as_of,
                            pe_trailing=fundamentals.pe_trailing,
                            pb=fundamentals.pb,
                            ps=fundamentals.ps,
                            market_cap=fundamentals.market_cap,
                            metrics=fundamentals.model_dump(mode="json"),
                        )
                    )
                await session.commit()
        except Exception as exc:
            logger.warning("marketdata_fundamentals_persist_failed", error=str(exc))

    async def _persist_news(self, news: Sequence[NewsItem]) -> None:
        if self._session_factory is None:
            return
        try:
            async with self._session_factory() as session:
                for item in news:
                    existing = await session.get(NewsItemTable, item.id)
                    if existing is None:
                        session.add(
                            NewsItemTable(
                                id=item.id,
                                symbol=item.symbol,
                                title=item.title,
                                summary=item.summary,
                                source=item.source,
                                url=item.url,
                                published_at=item.published_at,
                            )
                        )
                await session.commit()
        except Exception as exc:
            logger.warning("marketdata_news_persist_failed", error=str(exc))
