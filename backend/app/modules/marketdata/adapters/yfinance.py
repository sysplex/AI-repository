"""YFinance market data adapter implementing the DataProvider protocol.

All synchronous network and file operations are offloaded to a worker thread via
`asyncio.to_thread` to ensure the asynchronous event loop is never blocked.
Supports offline fixture replay for deterministic, zero-network tests.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yfinance as yf  # type: ignore[import-untyped]

from app.modules.marketdata.models import (
    AnalystRatings,
    Bar,
    CompanyProfile,
    CorporateAction,
    EarningsEvent,
    EarningsHistory,
    FinancialStatements,
    Fundamentals,
    NewsItem,
    Quote,
)


def _to_decimal(value: Any) -> Decimal | None:
    """Safely convert a number, float, or string to Decimal."""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return Decimal(str(value))
    if isinstance(value, (int, str)):
        try:
            return Decimal(str(value))
        except Exception:
            return None
    return None


def _to_utc_datetime(value: Any) -> datetime:
    """Ensure datetime has timezone and is converted to UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        with contextlib.suppress(Exception):
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
    return datetime.now(UTC)


class YFinanceAdapter:
    """DataProvider implementation backed by yfinance with fixture playback support."""

    name: str = "yfinance"

    def __init__(self, fixture_dir: Path | str | None = None) -> None:
        self._fixture_dir = Path(fixture_dir) if fixture_dir else None

    def _read_fixture(self, symbol: str) -> dict[str, Any] | None:
        if not self._fixture_dir:
            return None
        fixture_file = self._fixture_dir / f"{symbol.upper()}.json"
        if fixture_file.is_file():
            return json.loads(fixture_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        return None

    # 1. get_bars
    async def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> Sequence[Bar]:
        return await asyncio.to_thread(self._sync_get_bars, symbol, start, end, interval, adjusted)

    def _sync_get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str,
        adjusted: bool,
    ) -> list[Bar]:
        fixture = self._read_fixture(symbol)
        if fixture and "bars" in fixture:
            bars: list[Bar] = []
            for b in fixture["bars"]:
                trade_date = date.fromisoformat(b["trade_date"])
                if start <= trade_date <= end:
                    adj_close_val = (
                        Decimal(str(b.get("adj_close", b["close"]))) if adjusted else None
                    )
                    bars.append(
                        Bar(
                            symbol=symbol.upper(),
                            trade_date=trade_date,
                            open=Decimal(str(b["open"])),
                            high=Decimal(str(b["high"])),
                            low=Decimal(str(b["low"])),
                            close=Decimal(str(b["close"])),
                            volume=int(b["volume"]),
                            adj_close=adj_close_val,
                        )
                    )
            return bars

        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start.isoformat(),
            end=end.isoformat(),
            interval=interval,
            auto_adjust=adjusted,
        )
        result: list[Bar] = []
        for idx, row in df.iterrows():
            trade_date = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
            open_dec = _to_decimal(row.get("Open")) or Decimal("0")
            high_dec = _to_decimal(row.get("High")) or Decimal("0")
            low_dec = _to_decimal(row.get("Low")) or Decimal("0")
            close_dec = _to_decimal(row.get("Close")) or Decimal("0")
            volume_int = int(row.get("Volume", 0))
            adj_close_dec = _to_decimal(row.get("Adj Close")) or close_dec
            result.append(
                Bar(
                    symbol=symbol.upper(),
                    trade_date=trade_date,
                    open=open_dec,
                    high=high_dec,
                    low=low_dec,
                    close=close_dec,
                    volume=volume_int,
                    adj_close=adj_close_dec if adjusted else None,
                )
            )
        return result

    # 2. get_quote
    async def get_quote(self, symbol: str) -> Quote:
        return await asyncio.to_thread(self._sync_get_quote, symbol)

    def _sync_get_quote(self, symbol: str) -> Quote:
        fixture = self._read_fixture(symbol)
        if fixture and "quote" in fixture:
            q = fixture["quote"]
            return Quote(
                symbol=symbol.upper(),
                price=Decimal(str(q["price"])),
                change=Decimal(str(q["change"])),
                change_pct=Decimal(str(q["change_pct"])),
                volume=int(q["volume"]),
                as_of=_to_utc_datetime(q.get("as_of")),
                delayed_seconds=int(q.get("delayed_seconds", 0)),
                stale=bool(q.get("stale", False)),
            )

        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        price = _to_decimal(getattr(info, "last_price", None)) or Decimal("0")
        prev_close = _to_decimal(getattr(info, "previous_close", None)) or price
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else Decimal("0")
        vol = int(getattr(info, "last_volume", 0) or 0)
        return Quote(
            symbol=symbol.upper(),
            price=price,
            change=change,
            change_pct=change_pct,
            volume=vol,
            as_of=datetime.now(UTC),
        )

    # 3. get_quotes
    async def get_quotes(self, symbols: Sequence[str]) -> dict[str, Quote]:
        results: dict[str, Quote] = {}
        for s in symbols:
            results[s.upper()] = await self.get_quote(s)
        return results

    # 4. get_fundamentals
    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        return await asyncio.to_thread(self._sync_get_fundamentals, symbol)

    def _sync_get_fundamentals(self, symbol: str) -> Fundamentals:
        fixture = self._read_fixture(symbol)
        if fixture and "fundamentals" in fixture:
            f = fixture["fundamentals"]
            return Fundamentals(
                symbol=symbol.upper(),
                as_of=date.fromisoformat(f["as_of"]),
                pe_trailing=_to_decimal(f.get("pe_trailing")),
                pe_forward=_to_decimal(f.get("pe_forward")),
                pb=_to_decimal(f.get("pb")),
                ps=_to_decimal(f.get("ps")),
                roe=_to_decimal(f.get("roe")),
                net_margin=_to_decimal(f.get("net_margin")),
                debt_to_equity=_to_decimal(f.get("debt_to_equity")),
                market_cap=_to_decimal(f.get("market_cap")),
                dividend_yield=_to_decimal(f.get("dividend_yield")),
                beta=_to_decimal(f.get("beta")),
                missing_fields=list(f.get("missing_fields", [])),
            )

        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        missing: list[str] = []

        def _get_metric(key: str) -> Decimal | None:
            val = _to_decimal(info.get(key))
            if val is None:
                missing.append(key)
            return val

        pe_trailing = _get_metric("trailingPE")
        pe_forward = _get_metric("forwardPE")
        pb = _get_metric("priceToBook")
        ps = _get_metric("priceToSalesTrailing12Months")
        roe = _get_metric("returnOnEquity")
        net_margin = _get_metric("profitMargins")
        debt_to_equity = _get_metric("debtToEquity")
        market_cap = _get_metric("marketCap")
        div_yield = _get_metric("dividendYield")
        beta = _get_metric("beta")

        return Fundamentals(
            symbol=symbol.upper(),
            as_of=date.today(),
            pe_trailing=pe_trailing,
            pe_forward=pe_forward,
            pb=pb,
            ps=ps,
            roe=roe,
            net_margin=net_margin,
            debt_to_equity=debt_to_equity,
            market_cap=market_cap,
            dividend_yield=div_yield,
            beta=beta,
            missing_fields=missing,
        )

    # 5. get_financial_statements
    async def get_financial_statements(
        self,
        symbol: str,
        period: Literal["annual", "quarterly"] = "annual",
        limit: int = 10,
    ) -> FinancialStatements:
        return await asyncio.to_thread(self._sync_get_financial_statements, symbol, period, limit)

    def _sync_get_financial_statements(
        self,
        symbol: str,
        period: Literal["annual", "quarterly"],
        limit: int,
    ) -> FinancialStatements:
        fixture = self._read_fixture(symbol)
        if fixture and "financial_statements" in fixture:
            fs = fixture["financial_statements"]
            return FinancialStatements(
                symbol=symbol.upper(),
                period=period,
                period_end=date.fromisoformat(fs.get("period_end", "2025-12-31")),
                balance_sheet=dict(fs.get("balance_sheet", {})),
                income_statement=dict(fs.get("income_statement", {})),
                cash_flow=dict(fs.get("cash_flow", {})),
            )

        ticker = yf.Ticker(symbol)
        income_df = ticker.financials if period == "annual" else ticker.quarterly_financials
        bs_df = ticker.balance_sheet if period == "annual" else ticker.quarterly_balance_sheet
        cf_df = ticker.cashflow if period == "annual" else ticker.quarterly_cashflow

        latest_date = date.today()
        if hasattr(income_df, "columns") and len(income_df.columns) > 0:
            col0 = income_df.columns[0]
            if hasattr(col0, "date"):
                latest_date = col0.date()

        bs_dict = bs_df.to_dict() if bs_df is not None and hasattr(bs_df, "to_dict") else {}
        inc_dict = (
            income_df.to_dict() if income_df is not None and hasattr(income_df, "to_dict") else {}
        )
        cf_dict = cf_df.to_dict() if cf_df is not None and hasattr(cf_df, "to_dict") else {}

        return FinancialStatements(
            symbol=symbol.upper(),
            period=period,
            period_end=latest_date,
            balance_sheet=bs_dict,
            income_statement=inc_dict,
            cash_flow=cf_dict,
        )

    # 6. get_earnings
    async def get_earnings(self, symbol: str, limit: int = 8) -> EarningsHistory:
        return await asyncio.to_thread(self._sync_get_earnings, symbol, limit)

    def _sync_get_earnings(self, symbol: str, limit: int) -> EarningsHistory:
        fixture = self._read_fixture(symbol)
        if fixture and "earnings" in fixture:
            events: list[EarningsEvent] = []
            for ev in fixture["earnings"][:limit]:
                events.append(
                    EarningsEvent(
                        symbol=symbol.upper(),
                        report_date=date.fromisoformat(ev["report_date"]),
                        eps_estimated=_to_decimal(ev.get("eps_estimated")),
                        eps_actual=_to_decimal(ev.get("eps_actual")),
                        revenue_estimated=_to_decimal(ev.get("revenue_estimated")),
                        revenue_actual=_to_decimal(ev.get("revenue_actual")),
                        guidance=ev.get("guidance"),
                        reaction_1d_pct=_to_decimal(ev.get("reaction_1d_pct")),
                    )
                )
            return EarningsHistory(symbol=symbol.upper(), events=events)

        ticker = yf.Ticker(symbol)
        ed = ticker.earnings_dates
        events = []
        if ed is not None and hasattr(ed, "iterrows"):
            for count, (idx, row) in enumerate(ed.iterrows()):
                if count >= limit:
                    break
                report_date = idx.date() if hasattr(idx, "date") else date.today()
                events.append(
                    EarningsEvent(
                        symbol=symbol.upper(),
                        report_date=report_date,
                        eps_estimated=_to_decimal(row.get("EPS Estimate")),
                        eps_actual=_to_decimal(row.get("Reported EPS")),
                    )
                )
        return EarningsHistory(symbol=symbol.upper(), events=events)

    # 7. get_news
    async def get_news(
        self,
        symbol: str,
        limit: int = 20,
        since: datetime | None = None,
    ) -> Sequence[NewsItem]:
        return await asyncio.to_thread(self._sync_get_news, symbol, limit, since)

    def _sync_get_news(self, symbol: str, limit: int, since: datetime | None) -> list[NewsItem]:
        fixture = self._read_fixture(symbol)
        if fixture and "news" in fixture:
            news_items: list[NewsItem] = []
            for item in fixture["news"]:
                pub_at = _to_utc_datetime(item["published_at"])
                if since and pub_at < since:
                    continue
                news_items.append(
                    NewsItem(
                        id=str(item["id"]),
                        symbol=symbol.upper(),
                        title=str(item["title"]),
                        summary=str(item.get("summary", "")),
                        source=str(item.get("source", "Yahoo")),
                        url=str(item.get("url", "")),
                        published_at=pub_at,
                    )
                )
                if len(news_items) >= limit:
                    break
            return news_items

        ticker = yf.Ticker(symbol)
        raw_news = ticker.news or []
        items = []
        for n in raw_news:
            pub_at = _to_utc_datetime(n.get("providerPublishTime", datetime.now(UTC)))
            if since and pub_at < since:
                continue
            items.append(
                NewsItem(
                    id=str(n.get("uuid", n.get("id", ""))),
                    symbol=symbol.upper(),
                    title=str(n.get("title", "")),
                    summary=str(n.get("summary", "")),
                    source=str(n.get("publisher", "Yahoo")),
                    url=str(n.get("link", "")),
                    published_at=pub_at,
                )
            )
            if len(items) >= limit:
                break
        return items

    # 8. get_analyst_ratings
    async def get_analyst_ratings(self, symbol: str) -> AnalystRatings:
        return await asyncio.to_thread(self._sync_get_analyst_ratings, symbol)

    def _sync_get_analyst_ratings(self, symbol: str) -> AnalystRatings:
        fixture = self._read_fixture(symbol)
        if fixture and "analyst_ratings" in fixture:
            ar = fixture["analyst_ratings"]
            return AnalystRatings(
                symbol=symbol.upper(),
                as_of=date.fromisoformat(ar.get("as_of", date.today().isoformat())),
                consensus_rating=str(ar.get("consensus_rating", "hold")),
                target_high=_to_decimal(ar.get("target_high")),
                target_low=_to_decimal(ar.get("target_low")),
                target_mean=_to_decimal(ar.get("target_mean")),
                target_median=_to_decimal(ar.get("target_median")),
                analyst_count=int(ar.get("analyst_count", 0)),
            )

        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        return AnalystRatings(
            symbol=symbol.upper(),
            as_of=date.today(),
            consensus_rating=str(info.get("recommendationKey", "hold")),
            target_high=_to_decimal(info.get("targetHighPrice")),
            target_low=_to_decimal(info.get("targetLowPrice")),
            target_mean=_to_decimal(info.get("targetMeanPrice")),
            target_median=_to_decimal(info.get("targetMedianPrice")),
            analyst_count=int(info.get("numberOfAnalystOpinions", 0)),
        )

    # 9. get_corporate_actions
    async def get_corporate_actions(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> Sequence[CorporateAction]:
        return await asyncio.to_thread(self._sync_get_corporate_actions, symbol, start, end)

    def _sync_get_corporate_actions(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> list[CorporateAction]:
        fixture = self._read_fixture(symbol)
        if fixture and "corporate_actions" in fixture:
            actions: list[CorporateAction] = []
            for ca in fixture["corporate_actions"]:
                ex_date = date.fromisoformat(ca["ex_date"])
                if start <= ex_date <= end:
                    actions.append(
                        CorporateAction(
                            symbol=symbol.upper(),
                            ex_date=ex_date,
                            action_type=ca["action_type"],
                            ratio=_to_decimal(ca.get("ratio")),
                            amount=_to_decimal(ca.get("amount")),
                        )
                    )
            return actions

        ticker = yf.Ticker(symbol)
        actions_df = ticker.actions
        result = []
        if actions_df is not None and hasattr(actions_df, "iterrows"):
            for idx, row in actions_df.iterrows():
                ex_date = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
                if not (start <= ex_date <= end):
                    continue
                div = _to_decimal(row.get("Dividends"))
                split = _to_decimal(row.get("Stock Splits"))
                if div and div > Decimal("0"):
                    result.append(
                        CorporateAction(
                            symbol=symbol.upper(),
                            ex_date=ex_date,
                            action_type="dividend",
                            amount=div,
                        )
                    )
                if split and split > Decimal("0"):
                    result.append(
                        CorporateAction(
                            symbol=symbol.upper(),
                            ex_date=ex_date,
                            action_type="split",
                            ratio=split,
                        )
                    )
        return result

    # 10. get_profile
    async def get_profile(self, symbol: str) -> CompanyProfile:
        return await asyncio.to_thread(self._sync_get_profile, symbol)

    def _sync_get_profile(self, symbol: str) -> CompanyProfile:
        fixture = self._read_fixture(symbol)
        if fixture and "profile" in fixture:
            p = fixture["profile"]
            return CompanyProfile(
                symbol=symbol.upper(),
                name=str(p["name"]),
                exchange=str(p["exchange"]),
                sector=str(p["sector"]),
                industry=str(p["industry"]),
                description=str(p.get("description", "")),
                website=p.get("website"),
                employees=int(p["employees"]) if p.get("employees") else None,
                country=str(p.get("country", "US")),
            )

        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        return CompanyProfile(
            symbol=symbol.upper(),
            name=str(info.get("shortName") or info.get("longName") or symbol.upper()),
            exchange=str(info.get("exchange", "NASDAQ")),
            sector=str(info.get("sector", "Unknown")),
            industry=str(info.get("industry", "Unknown")),
            description=str(info.get("longBusinessSummary", "")),
            website=info.get("website"),
            employees=int(info["fullTimeEmployees"]) if info.get("fullTimeEmployees") else None,
            country=str(info.get("country", "US")),
        )

    # 11. get_universe
    async def get_universe(self, name: str) -> Sequence[str]:
        return await asyncio.to_thread(self._sync_get_universe, name)

    def _sync_get_universe(self, name: str) -> list[str]:
        if self._fixture_dir:
            univ_file = self._fixture_dir / "universes.json"
            if univ_file.is_file():
                data = json.loads(univ_file.read_text(encoding="utf-8"))
                if name.lower() in data:
                    return list(data[name.lower()])

        # Standard baseline components
        universes: dict[str, list[str]] = {
            "sp500": [
                "AAPL",
                "MSFT",
                "NVDA",
                "AMZN",
                "GOOGL",
                "META",
                "TSLA",
                "BRK-B",
                "JPM",
                "V",
            ],
            "nasdaq100": [
                "AAPL",
                "MSFT",
                "NVDA",
                "AMZN",
                "GOOGL",
                "META",
                "TSLA",
                "COST",
                "AVGO",
                "ADBE",
            ],
        }
        return universes.get(name.lower(), ["AAPL", "MSFT", "NVDA"])
