"""Market data module (M2).

Provides domain models, provider ports, caching, and persistence for financial market data.
"""

from app.modules.marketdata.cache import MarketDataCache
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
from app.modules.marketdata.service import DataService

__all__ = [
    "AnalystRatings",
    "Bar",
    "CompanyProfile",
    "CorporateAction",
    "DataProvider",
    "DataService",
    "EarningsEvent",
    "EarningsHistory",
    "FactsSnapshot",
    "FinancialStatements",
    "Fundamentals",
    "MarketDataCache",
    "NewsItem",
    "Quote",
]
