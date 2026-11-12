"""M2 DataProvider port contract.

Defines the abstract protocol for fetching market data, financial statements,
corporate actions, and universes across any data vendor adapter.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Literal, Protocol, runtime_checkable

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


@runtime_checkable
class DataProvider(Protocol):
    """Abstract protocol for financial and market data providers."""

    name: str

    async def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> Sequence[Bar]:
        """Fetch historical candlestick bars within the date range [start, end]."""
        ...

    async def get_quote(self, symbol: str) -> Quote:
        """Fetch current or latest market quote for a single symbol."""
        ...

    async def get_quotes(self, symbols: Sequence[str]) -> dict[str, Quote]:
        """Fetch market quotes for a sequence of symbols."""
        ...

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        """Fetch valuation and fundamental snapshot metrics."""
        ...

    async def get_financial_statements(
        self,
        symbol: str,
        period: Literal["annual", "quarterly"] = "annual",
        limit: int = 10,
    ) -> FinancialStatements:
        """Fetch financial balance sheet, income, and cash flow statements."""
        ...

    async def get_earnings(self, symbol: str, limit: int = 8) -> EarningsHistory:
        """Fetch historical earnings events and future estimates."""
        ...

    async def get_news(
        self,
        symbol: str,
        limit: int = 20,
        since: datetime | None = None,
    ) -> Sequence[NewsItem]:
        """Fetch market news items for a specific symbol."""
        ...

    async def get_analyst_ratings(self, symbol: str) -> AnalystRatings:
        """Fetch consensus analyst ratings and price targets."""
        ...

    async def get_corporate_actions(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> Sequence[CorporateAction]:
        """Fetch corporate actions (stock splits, cash dividends) in range."""
        ...

    async def get_profile(self, symbol: str) -> CompanyProfile:
        """Fetch company overview, sector, and industry details."""
        ...

    async def get_universe(self, name: str) -> Sequence[str]:
        """Fetch index or ETF constituent symbols (e.g., 'sp500', 'nasdaq100')."""
        ...
