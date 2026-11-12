"""Integration tests for M2 marketdata tables and Alembic migration 0002."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Numeric, select
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.modules.marketdata.tables import (
    BarDailyTable,
    CorporateActionTable,
    DataSnapshotTable,
    EarningsEventTable,
    FinancialStatementTable,
    FundamentalsSnapshotTable,
    NewsItemTable,
    SymbolTable,
)

BACKEND = Path(__file__).resolve().parents[4]
ALEMBIC_DIR = BACKEND / "alembic"
INI_PATH = BACKEND / "alembic.ini"


def _config() -> Config:
    config = Config(str(INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config


def test_marketdata_offline_sql_contains_all_tables(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify offline DDL generation creates all 8 M2 tables and indexes."""
    from app.core.config import Settings

    offline_settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user@localhost:5432/offline",
        redis_url="redis://localhost:6379/0",
        secret_key="x" * 32,
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: offline_settings)
    command.upgrade(_config(), "head", sql=True)
    output = capsys.readouterr().out

    expected_tables = [
        "CREATE TABLE symbols",
        "CREATE TABLE bars_daily",
        "CREATE TABLE corporate_actions",
        "CREATE TABLE fundamentals_snapshots",
        "CREATE TABLE financial_statements",
        "CREATE TABLE earnings_events",
        "CREATE TABLE news_items",
        "CREATE TABLE data_snapshots",
    ]
    for table in expected_tables:
        assert table in output, f"Missing table DDL: {table}"

    expected_indexes = [
        "ix_bars_daily_trade_date",
        "ix_news_items_symbol_published_at",
        "ix_data_snapshots_symbol_as_of",
    ]
    for idx in expected_indexes:
        assert idx in output, f"Missing index DDL: {idx}"


def test_marketdata_orm_models_definitions() -> None:
    """Verify ORM model columns, primary keys, and constraints."""
    # 1. symbols
    symbol_cols = {c.name: c for c in SymbolTable.__table__.columns}
    assert symbol_cols["symbol"].primary_key is True
    assert symbol_cols["name"].nullable is False

    # 2. bars_daily
    bar_cols = {c.name: c for c in BarDailyTable.__table__.columns}
    assert bar_cols["symbol"].primary_key is True
    assert bar_cols["trade_date"].primary_key is True
    assert isinstance(bar_cols["open"].type, Numeric)
    assert bar_cols["open"].type.precision == 18
    assert bar_cols["open"].type.scale == 6

    # 3. corporate_actions
    ca_cols = {c.name: c for c in CorporateActionTable.__table__.columns}
    assert ca_cols["symbol"].primary_key is True
    assert ca_cols["ex_date"].primary_key is True
    assert ca_cols["action_type"].primary_key is True

    # 4. fundamentals_snapshots
    fs_cols = {c.name: c for c in FundamentalsSnapshotTable.__table__.columns}
    assert fs_cols["symbol"].primary_key is True
    assert fs_cols["as_of"].primary_key is True
    assert isinstance(fs_cols["market_cap"].type, Numeric)

    # 5. financial_statements
    stmt_cols = {c.name: c for c in FinancialStatementTable.__table__.columns}
    assert stmt_cols["symbol"].primary_key is True
    assert stmt_cols["period_end"].primary_key is True
    assert stmt_cols["period_type"].primary_key is True

    # 6. earnings_events
    ee_cols = {c.name: c for c in EarningsEventTable.__table__.columns}
    assert ee_cols["symbol"].primary_key is True
    assert ee_cols["report_date"].primary_key is True

    # 7. news_items
    news_cols = {c.name: c for c in NewsItemTable.__table__.columns}
    assert news_cols["id"].primary_key is True

    # 8. data_snapshots
    snap_cols = {c.name: c for c in DataSnapshotTable.__table__.columns}
    assert snap_cols["content_hash"].primary_key is True


async def test_marketdata_crud_roundtrip(db_session: AsyncSession) -> None:
    """Verify insert and query roundtrip on M2 tables in an isolated transaction."""
    # Insert Symbol
    symbol_record = SymbolTable(
        symbol="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        industry="Consumer Electronics",
        status="active",
    )
    db_session.add(symbol_record)

    # Insert Bar
    bar_record = BarDailyTable(
        symbol="AAPL",
        trade_date=date(2026, 11, 10),
        open=Decimal("220.500000"),
        high=Decimal("225.000000"),
        low=Decimal("219.800000"),
        close=Decimal("224.230000"),
        volume=54321000,
        adj_close=Decimal("224.230000"),
    )
    db_session.add(bar_record)

    # Insert CorporateAction
    ca_record = CorporateActionTable(
        symbol="AAPL",
        ex_date=date(2024, 6, 10),
        action_type="split",
        ratio=Decimal("10.000000"),
    )
    db_session.add(ca_record)

    # Insert DataSnapshot
    snap_record = DataSnapshotTable(
        content_hash="abc123hash",
        symbol="AAPL",
        as_of=datetime.now(UTC),
        scope=["quote", "profile"],
        facts={"price": "224.23"},
        missing_fields=[],
    )
    db_session.add(snap_record)

    await db_session.flush()

    # Query back and verify
    stmt = select(BarDailyTable).where(
        BarDailyTable.symbol == "AAPL",
        BarDailyTable.trade_date == date(2026, 11, 10),
    )
    queried_bar = (await db_session.execute(stmt)).scalar_one_or_none()
    assert queried_bar is not None
    assert queried_bar.close == Decimal("224.230000")
    assert queried_bar.volume == 54321000

    stmt_ca = select(CorporateActionTable).where(
        CorporateActionTable.symbol == "AAPL",
        CorporateActionTable.action_type == "split",
    )
    queried_ca = (await db_session.execute(stmt_ca)).scalar_one_or_none()
    assert queried_ca is not None
    assert queried_ca.ratio == Decimal("10.000000")
