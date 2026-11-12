"""Contract tests for YFinanceAdapter verifying adherence to DataProvider protocol."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.marketdata.adapters.yfinance import YFinanceAdapter
from app.modules.marketdata.models import (
    AnalystRatings,
    Bar,
    CompanyProfile,
    EarningsHistory,
    FinancialStatements,
    Fundamentals,
    NewsItem,
    Quote,
)
from app.modules.marketdata.ports import DataProvider

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "m2"


@pytest.fixture
def adapter() -> YFinanceAdapter:
    """Fixture providing YFinanceAdapter configured with offline fixture replay."""
    return YFinanceAdapter(fixture_dir=FIXTURES_DIR)


def test_yfinance_implements_data_provider_protocol(adapter: YFinanceAdapter) -> None:
    """Verify YFinanceAdapter satisfies the runtime checkable DataProvider Protocol."""
    assert isinstance(adapter, DataProvider)
    assert adapter.name == "yfinance"


async def test_yfinance_get_quote_contract(adapter: YFinanceAdapter) -> None:
    """Verify get_quote returns Quote with correct types and Decimal amounts."""
    quote = await adapter.get_quote("AAPL")
    assert isinstance(quote, Quote)
    assert quote.symbol == "AAPL"
    assert quote.price == Decimal("224.23")
    assert quote.change == Decimal("1.50")
    assert quote.change_pct == Decimal("0.67")
    assert isinstance(quote.price, Decimal)
    assert quote.as_of.tzinfo is not None


async def test_yfinance_get_quotes_batch(adapter: YFinanceAdapter) -> None:
    """Verify get_quotes returns dict of Quotes keyed by uppercase symbols."""
    quotes = await adapter.get_quotes(["AAPL", "MSFT"])
    assert "AAPL" in quotes
    assert "MSFT" in quotes
    assert quotes["AAPL"].price == Decimal("224.23")
    assert quotes["MSFT"].price == Decimal("415.20")


async def test_yfinance_get_bars_contract(adapter: YFinanceAdapter) -> None:
    """Verify get_bars filters date range and formats bars."""
    bars = await adapter.get_bars("AAPL", start=date(2026, 11, 9), end=date(2026, 11, 10))
    assert len(bars) == 2
    for bar in bars:
        assert isinstance(bar, Bar)
        assert bar.symbol == "AAPL"
        assert isinstance(bar.open, Decimal)
        assert isinstance(bar.close, Decimal)
        assert bar.volume > 0


async def test_yfinance_nvda_split_contract(adapter: YFinanceAdapter) -> None:
    """Verify NVDA 2024-06 10-for-1 split case in corporate actions and adjusted bars."""
    actions = await adapter.get_corporate_actions(
        "NVDA",
        start=date(2024, 6, 1),
        end=date(2024, 6, 15),
    )
    assert len(actions) >= 1
    split_action = next(a for a in actions if a.action_type == "split")
    assert split_action.ex_date == date(2024, 6, 10)
    assert split_action.ratio == Decimal("10.0")

    bars = await adapter.get_bars(
        "NVDA",
        start=date(2024, 6, 7),
        end=date(2024, 6, 10),
        adjusted=True,
    )
    assert len(bars) == 2
    pre_split_bar = bars[0]
    assert pre_split_bar.trade_date == date(2024, 6, 7)
    assert pre_split_bar.close == Decimal("1208.88")
    assert pre_split_bar.adj_close == Decimal("120.888")


async def test_yfinance_get_fundamentals_contract(adapter: YFinanceAdapter) -> None:
    """Verify get_fundamentals outputs Fundamentals model."""
    fund = await adapter.get_fundamentals("AAPL")
    assert isinstance(fund, Fundamentals)
    assert fund.symbol == "AAPL"
    assert fund.pe_trailing == Decimal("34.2")
    assert fund.market_cap == Decimal("3400000000000")


async def test_yfinance_get_financial_statements_contract(adapter: YFinanceAdapter) -> None:
    """Verify get_financial_statements returns three statements."""
    stmts = await adapter.get_financial_statements("AAPL", period="annual")
    assert isinstance(stmts, FinancialStatements)
    assert stmts.symbol == "AAPL"
    assert "total_assets" in stmts.balance_sheet
    assert "total_revenue" in stmts.income_statement


async def test_yfinance_get_earnings_contract(adapter: YFinanceAdapter) -> None:
    """Verify get_earnings returns EarningsHistory."""
    eh = await adapter.get_earnings("AAPL", limit=5)
    assert isinstance(eh, EarningsHistory)
    assert eh.symbol == "AAPL"
    assert len(eh.events) == 1
    assert eh.events[0].eps_actual == Decimal("1.64")


async def test_yfinance_get_news_contract(adapter: YFinanceAdapter) -> None:
    """Verify get_news returns sequence of NewsItem."""
    news = await adapter.get_news("AAPL", limit=10)
    assert len(news) == 1
    item = news[0]
    assert isinstance(item, NewsItem)
    assert item.symbol == "AAPL"
    assert item.title == "Apple Reports Record Services Revenue"
    assert item.published_at.tzinfo is not None


async def test_yfinance_get_analyst_ratings_contract(adapter: YFinanceAdapter) -> None:
    """Verify get_analyst_ratings returns AnalystRatings."""
    ar = await adapter.get_analyst_ratings("AAPL")
    assert isinstance(ar, AnalystRatings)
    assert ar.symbol == "AAPL"
    assert ar.consensus_rating == "buy"
    assert ar.target_mean == Decimal("235.00")
    assert ar.analyst_count == 42


async def test_yfinance_get_profile_contract(adapter: YFinanceAdapter) -> None:
    """Verify get_profile returns CompanyProfile."""
    p = await adapter.get_profile("AAPL")
    assert isinstance(p, CompanyProfile)
    assert p.symbol == "AAPL"
    assert p.exchange == "NASDAQ"
    assert p.sector == "Technology"
    assert p.country == "US"


async def test_yfinance_get_universe_contract(adapter: YFinanceAdapter) -> None:
    """Verify get_universe returns list of tickers."""
    sp500 = await adapter.get_universe("sp500")
    assert "AAPL" in sp500
    assert "NVDA" in sp500
    assert len(sp500) == 10
