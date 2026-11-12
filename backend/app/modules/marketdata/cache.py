"""Market data cache proxy and resilience fallbacks (M2 / T04).

Implements Redis caching for quotes, bars, fundamentals, and company profiles,
along with exponential backoff retries and stale data fallback.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING, TypeVar

from pydantic import TypeAdapter

from app.core.calendar import is_market_open
from app.core.clock import get_clock
from app.core.errors import DataUnavailable
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.modules.marketdata.models import (
    Bar,
    CompanyProfile,
    Fundamentals,
    Quote,
)

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = get_logger(__name__)

T = TypeVar("T")

QUOTE_TTL_OPEN: int = 60
QUOTE_TTL_CLOSED: int = 300
FUNDAMENTALS_TTL: int = 86400
PROFILE_TTL: int = 86400
BARS_TTL: int = 3600
BACKUP_TTL: int = 86400 * 30

_BARS_ADAPTER: TypeAdapter[list[Bar]] = TypeAdapter(list[Bar])


class MarketDataCache:
    """Redis cache proxy with exponential backoff and stale fallback for market data."""

    def __init__(
        self,
        redis_client: aioredis.Redis | None = None,
        base_delay: float = 0.2,
        max_retries: int = 2,
        backup_ttl: int | None = BACKUP_TTL,
    ) -> None:
        self._redis = redis_client
        self._base_delay = base_delay
        self._max_retries = max_retries
        self._backup_ttl = backup_ttl

    @property
    def redis(self) -> aioredis.Redis:
        """Lazily initialize Redis client if not injected."""
        if self._redis is None:
            self._redis = get_redis()
        return self._redis

    def get_quote_ttl(self, at: datetime | None = None) -> int:
        """Return TTL in seconds based on whether the market is open."""
        if at is None:
            at = get_clock().now()
        try:
            if is_market_open(at):
                return QUOTE_TTL_OPEN
        except Exception as exc:
            logger.debug("market_open_check_failed", error=str(exc))
        return QUOTE_TTL_CLOSED

    @staticmethod
    def quote_key(symbol: str) -> str:
        return f"quote:{symbol.upper()}"

    @staticmethod
    def backup_quote_key(symbol: str) -> str:
        return f"backup:quote:{symbol.upper()}"

    @staticmethod
    def fundamentals_key(symbol: str) -> str:
        return f"fundamentals:{symbol.upper()}"

    @staticmethod
    def backup_fundamentals_key(symbol: str) -> str:
        return f"backup:fundamentals:{symbol.upper()}"

    @staticmethod
    def profile_key(symbol: str) -> str:
        return f"profile:{symbol.upper()}"

    @staticmethod
    def backup_profile_key(symbol: str) -> str:
        return f"backup:profile:{symbol.upper()}"

    @staticmethod
    def bars_key(
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> str:
        suffix = "" if adjusted else ":unadjusted"
        return f"bars:{symbol.upper()}:{start.isoformat()}:{end.isoformat()}:{interval}{suffix}"

    @staticmethod
    def backup_bars_key(
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> str:
        suffix = "" if adjusted else ":unadjusted"
        return (
            f"backup:bars:{symbol.upper()}:{start.isoformat()}:{end.isoformat()}:{interval}{suffix}"
        )

    # -------------------------------------------------------------------------
    # Retry Execution
    # -------------------------------------------------------------------------

    async def fetch_with_retry(
        self,
        fetcher: Callable[[], Awaitable[T]],
        context_name: str = "data",
    ) -> T:
        """Execute fetcher with exponential backoff retries on failure."""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await fetcher()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    delay = self._base_delay * (2**attempt)
                    logger.warning(
                        "marketdata_fetch_retry",
                        context=context_name,
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "marketdata_fetch_exhausted",
                        context=context_name,
                        attempts=self._max_retries + 1,
                        error=str(exc),
                    )
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Unexpected state: retries loop exited without last_exc")

    # -------------------------------------------------------------------------
    # Quote Cache
    # -------------------------------------------------------------------------

    async def get_quote(self, symbol: str) -> Quote | None:
        """Retrieve active cached quote if present."""
        raw = await self.redis.get(self.quote_key(symbol))
        if raw is None:
            return None
        return Quote.model_validate_json(raw)

    async def get_backup_quote(self, symbol: str) -> Quote | None:
        """Retrieve fallback cached quote marked as stale."""
        raw = await self.redis.get(self.backup_quote_key(symbol))
        if raw is None:
            return None
        quote = Quote.model_validate_json(raw)
        return quote.model_copy(update={"stale": True})

    async def set_quote(self, symbol: str, quote: Quote, at: datetime | None = None) -> None:
        """Save quote to active cache (with market-aware TTL) and backup cache."""
        ttl = self.get_quote_ttl(at)
        data = quote.model_dump_json()
        active_key = self.quote_key(symbol)
        backup_key = self.backup_quote_key(symbol)

        await self.redis.set(active_key, data, ex=ttl)
        if self._backup_ttl is not None:
            await self.redis.set(backup_key, data, ex=self._backup_ttl)
        else:
            await self.redis.set(backup_key, data)

    async def get_or_fetch_quote(
        self,
        symbol: str,
        fetcher: Callable[[], Awaitable[Quote]],
        at: datetime | None = None,
    ) -> Quote:
        """Check cache first; on miss, retry fetcher; on failure, fallback to stale backup."""
        cached = await self.get_quote(symbol)
        if cached is not None:
            return cached

        try:
            quote = await self.fetch_with_retry(fetcher, context_name=f"quote:{symbol}")
            await self.set_quote(symbol, quote, at=at)
            return quote
        except Exception as exc:
            backup = await self.get_backup_quote(symbol)
            if backup is not None:
                logger.warning("marketdata_stale_fallback", symbol=symbol, type="quote")
                return backup
            raise DataUnavailable(f"外部数据源不可用且无可用缓存: {symbol}") from exc

    async def get_or_fetch_quotes(
        self,
        symbols: Sequence[str],
        fetcher: Callable[[Sequence[str]], Awaitable[dict[str, Quote]]],
        at: datetime | None = None,
    ) -> dict[str, Quote]:
        """Batch retrieve quotes with cache hit reuse and fallback for missing symbols."""
        result: dict[str, Quote] = {}
        missing: list[str] = []

        for sym in symbols:
            cached = await self.get_quote(sym)
            if cached is not None:
                result[sym] = cached
            else:
                missing.append(sym)

        if not missing:
            return result

        try:
            fetched = await self.fetch_with_retry(
                lambda: fetcher(missing),
                context_name=f"quotes:{','.join(missing)}",
            )
            for sym, q in fetched.items():
                await self.set_quote(sym, q, at=at)
                result[sym] = q
        except Exception as exc:
            for sym in missing:
                backup = await self.get_backup_quote(sym)
                if backup is not None:
                    logger.warning("marketdata_stale_fallback", symbol=sym, type="quote")
                    result[sym] = backup
                else:
                    raise DataUnavailable(f"外部数据源不可用且无可用缓存: {sym}") from exc

        return result

    # -------------------------------------------------------------------------
    # Bars Cache
    # -------------------------------------------------------------------------

    async def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> list[Bar] | None:
        """Retrieve active cached bars if present."""
        raw = await self.redis.get(self.bars_key(symbol, start, end, interval, adjusted))
        if raw is None:
            return None
        return _BARS_ADAPTER.validate_json(raw)

    async def get_backup_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> list[Bar] | None:
        """Retrieve backup cached bars."""
        raw = await self.redis.get(self.backup_bars_key(symbol, start, end, interval, adjusted))
        if raw is None:
            return None
        return _BARS_ADAPTER.validate_json(raw)

    async def set_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        bars: Sequence[Bar],
        interval: str = "1d",
        adjusted: bool = True,
    ) -> None:
        """Save bars to active cache and backup cache."""
        data = _BARS_ADAPTER.dump_json(list(bars)).decode("utf-8")
        active_key = self.bars_key(symbol, start, end, interval, adjusted)
        backup_key = self.backup_bars_key(symbol, start, end, interval, adjusted)

        await self.redis.set(active_key, data, ex=BARS_TTL)
        if self._backup_ttl is not None:
            await self.redis.set(backup_key, data, ex=self._backup_ttl)
        else:
            await self.redis.set(backup_key, data)

    async def get_or_fetch_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        fetcher: Callable[[], Awaitable[Sequence[Bar]]],
        interval: str = "1d",
        adjusted: bool = True,
    ) -> Sequence[Bar]:
        """Check cache first; on miss, retry fetcher; on failure, fallback to backup."""
        cached = await self.get_bars(symbol, start, end, interval, adjusted)
        if cached is not None:
            return cached

        try:
            bars = await self.fetch_with_retry(
                fetcher,
                context_name=f"bars:{symbol}:{start}:{end}:{interval}",
            )
            await self.set_bars(symbol, start, end, bars, interval, adjusted)
            return bars
        except Exception as exc:
            backup = await self.get_backup_bars(symbol, start, end, interval, adjusted)
            if backup is not None:
                logger.warning("marketdata_stale_fallback", symbol=symbol, type="bars")
                return backup
            raise DataUnavailable(f"外部数据源不可用且无可用缓存: {symbol}") from exc

    # -------------------------------------------------------------------------
    # Fundamentals Cache
    # -------------------------------------------------------------------------

    async def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        """Retrieve active cached fundamentals."""
        raw = await self.redis.get(self.fundamentals_key(symbol))
        if raw is None:
            return None
        return Fundamentals.model_validate_json(raw)

    async def get_backup_fundamentals(self, symbol: str) -> Fundamentals | None:
        """Retrieve backup cached fundamentals."""
        raw = await self.redis.get(self.backup_fundamentals_key(symbol))
        if raw is None:
            return None
        return Fundamentals.model_validate_json(raw)

    async def set_fundamentals(self, symbol: str, fundamentals: Fundamentals) -> None:
        """Save fundamentals to active and backup cache."""
        data = fundamentals.model_dump_json()
        active_key = self.fundamentals_key(symbol)
        backup_key = self.backup_fundamentals_key(symbol)

        await self.redis.set(active_key, data, ex=FUNDAMENTALS_TTL)
        if self._backup_ttl is not None:
            await self.redis.set(backup_key, data, ex=self._backup_ttl)
        else:
            await self.redis.set(backup_key, data)

    async def get_or_fetch_fundamentals(
        self,
        symbol: str,
        fetcher: Callable[[], Awaitable[Fundamentals]],
    ) -> Fundamentals:
        """Check cache first; on miss, retry fetcher; on failure, fallback to backup."""
        cached = await self.get_fundamentals(symbol)
        if cached is not None:
            return cached

        try:
            funds = await self.fetch_with_retry(fetcher, context_name=f"fundamentals:{symbol}")
            await self.set_fundamentals(symbol, funds)
            return funds
        except Exception as exc:
            backup = await self.get_backup_fundamentals(symbol)
            if backup is not None:
                logger.warning("marketdata_stale_fallback", symbol=symbol, type="fundamentals")
                return backup
            raise DataUnavailable(f"外部数据源不可用且无可用缓存: {symbol}") from exc

    # -------------------------------------------------------------------------
    # Profile Cache
    # -------------------------------------------------------------------------

    async def get_profile(self, symbol: str) -> CompanyProfile | None:
        """Retrieve active cached company profile."""
        raw = await self.redis.get(self.profile_key(symbol))
        if raw is None:
            return None
        return CompanyProfile.model_validate_json(raw)

    async def get_backup_profile(self, symbol: str) -> CompanyProfile | None:
        """Retrieve backup cached company profile."""
        raw = await self.redis.get(self.backup_profile_key(symbol))
        if raw is None:
            return None
        return CompanyProfile.model_validate_json(raw)

    async def set_profile(self, symbol: str, profile: CompanyProfile) -> None:
        """Save company profile to active and backup cache."""
        data = profile.model_dump_json()
        active_key = self.profile_key(symbol)
        backup_key = self.backup_profile_key(symbol)

        await self.redis.set(active_key, data, ex=PROFILE_TTL)
        if self._backup_ttl is not None:
            await self.redis.set(backup_key, data, ex=self._backup_ttl)
        else:
            await self.redis.set(backup_key, data)

    async def get_or_fetch_profile(
        self,
        symbol: str,
        fetcher: Callable[[], Awaitable[CompanyProfile]],
    ) -> CompanyProfile:
        """Check cache first; on miss, retry fetcher; on failure, fallback to backup."""
        cached = await self.get_profile(symbol)
        if cached is not None:
            return cached

        try:
            profile = await self.fetch_with_retry(fetcher, context_name=f"profile:{symbol}")
            await self.set_profile(symbol, profile)
            return profile
        except Exception as exc:
            backup = await self.get_backup_profile(symbol)
            if backup is not None:
                logger.warning("marketdata_stale_fallback", symbol=symbol, type="profile")
                return backup
            raise DataUnavailable(f"外部数据源不可用且无可用缓存: {symbol}") from exc
