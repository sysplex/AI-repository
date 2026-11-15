"""M8-T04: WatchlistRepository 与 ScreenerRepository 单元测试。

验证多租户隔离约束、SQL 谓词绑定、自选清单与标的增删改查全生命周期、
以及标的重复添加防御 (DuplicateWatchlistItemError)。
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.screener.exceptions import (
    DuplicateWatchlistItemError,
    ScreenerError,
    WatchlistItemNotFoundError,
    WatchlistNotFoundError,
)
from app.modules.screener.models import ScreenerRun, Watchlist, WatchlistItem
from app.modules.screener.repo import ScreenerRepository, WatchlistRepository
from app.modules.screener.schemas import (
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemUpdate,
    WatchlistUpdate,
)

_NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def _result(
    *,
    scalar: Any = None,
    scalars: Sequence[Any] = (),
) -> MagicMock:
    res = MagicMock()
    res.scalar_one_or_none.return_value = scalar
    res.scalars.return_value.all.return_value = list(scalars)
    return res


def _session(*, result: MagicMock | None = None) -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result if result is not None else _result()
    return session


# ---------------------------------------------------------------------------
# ScreenerRepository 单元测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_repo_create_run_sets_created_at_and_adds() -> None:
    session = _session()
    repo = ScreenerRepository(session)
    user_id = uuid.uuid4()

    run = ScreenerRun(
        id=uuid.uuid4(),
        user_id=user_id,
        strategy_id="momentum_top",
        universe="sp500",
        params={},
        status="pending",
    )
    created = await repo.create_run(run)

    assert created is run
    assert created.created_at is not None
    session.add.assert_called_once_with(run)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_screener_repo_update_run_flushes() -> None:
    session = _session()
    repo = ScreenerRepository(session)
    run = ScreenerRun(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        strategy_id="momentum_top",
        universe="sp500",
        params={},
        status="running",
        created_at=_NOW,
    )
    run.status = "succeeded"
    updated = await repo.update_run(run)
    assert updated.status == "succeeded"
    session.add.assert_called_once_with(run)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_screener_repo_get_run_scopes_by_user_id() -> None:
    user_a = uuid.uuid4()
    run_id = uuid.uuid4()
    sentinel = MagicMock(spec=ScreenerRun)

    session = _session(result=_result(scalar=sentinel))
    repo = ScreenerRepository(session)

    res = await repo.get_run(run_id, user_a)
    assert res is sentinel

    call_stmt = session.execute.await_args_list[0].args[0]
    sql_text = str(call_stmt)
    assert "screener_runs.id" in sql_text
    assert "screener_runs.user_id" in sql_text
    params = call_stmt.compile().params
    assert run_id in params.values()
    assert user_a in params.values()


@pytest.mark.asyncio
async def test_screener_repo_get_run_returns_none_when_unmatched() -> None:
    session = _session(result=_result(scalar=None))
    repo = ScreenerRepository(session)
    res = await repo.get_run(uuid.uuid4(), uuid.uuid4())
    assert res is None


@pytest.mark.asyncio
async def test_screener_repo_list_runs_scopes_by_user_id_and_paginates() -> None:
    user_id = uuid.uuid4()
    run1 = MagicMock(spec=ScreenerRun)
    run2 = MagicMock(spec=ScreenerRun)

    session = _session(result=_result(scalars=[run1, run2]))
    repo = ScreenerRepository(session)

    runs = await repo.list_runs(user_id, limit=10, offset=5)
    assert runs == [run1, run2]

    call_stmt = session.execute.await_args_list[0].args[0]
    sql_text = str(call_stmt)
    assert "screener_runs.user_id" in sql_text
    assert "ORDER BY screener_runs.created_at DESC" in sql_text
    params = call_stmt.compile().params
    assert user_id in params.values()


# ---------------------------------------------------------------------------
# WatchlistRepository 单元测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchlist_repo_list_watchlists_scopes_by_user_id() -> None:
    user_id = uuid.uuid4()
    wl1 = MagicMock(spec=Watchlist)
    session = _session(result=_result(scalars=[wl1]))
    repo = WatchlistRepository(session)

    res = await repo.list_watchlists(user_id)
    assert res == [wl1]

    call_stmt = session.execute.await_args_list[0].args[0]
    sql_text = str(call_stmt)
    assert "watchlists.user_id" in sql_text
    assert "ORDER BY watchlists.created_at ASC" in sql_text
    params = call_stmt.compile().params
    assert user_id in params.values()


@pytest.mark.asyncio
async def test_watchlist_repo_get_watchlist_scopes_by_user_id() -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    sentinel = MagicMock(spec=Watchlist)

    session = _session(result=_result(scalar=sentinel))
    repo = WatchlistRepository(session)

    res = await repo.get_watchlist(wl_id, user_id)
    assert res is sentinel

    call_stmt = session.execute.await_args_list[0].args[0]
    sql_text = str(call_stmt)
    assert "watchlists.id" in sql_text
    assert "watchlists.user_id" in sql_text
    params = call_stmt.compile().params
    assert wl_id in params.values()
    assert user_id in params.values()


@pytest.mark.asyncio
async def test_watchlist_repo_create_watchlist_normal() -> None:
    session = _session()
    repo = WatchlistRepository(session)
    user_id = uuid.uuid4()

    data = WatchlistCreate(name="Tech Picks", description="AI and SaaS", is_default=False)
    created = await repo.create_watchlist(user_id, data)

    assert created.user_id == user_id
    assert created.name == "Tech Picks"
    assert created.description == "AI and SaaS"
    assert created.is_default is False
    assert created.items == []
    session.add.assert_called_once_with(created)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_watchlist_repo_create_watchlist_default_clears_previous_default() -> None:
    session = _session()
    repo = WatchlistRepository(session)
    user_id = uuid.uuid4()

    data = WatchlistCreate(name="Default Core", description="Primary list", is_default=True)
    created = await repo.create_watchlist(user_id, data)

    assert created.is_default is True
    # Verify update statement was executed to unset existing default
    assert session.execute.await_count == 1
    update_stmt = session.execute.await_args_list[0].args[0]
    assert "UPDATE watchlists SET is_default=" in str(update_stmt)
    assert user_id in update_stmt.compile().params.values()


@pytest.mark.asyncio
async def test_watchlist_repo_create_watchlist_name_conflict_raises_screener_error() -> None:
    session = _session()
    session.flush.side_effect = IntegrityError(
        "UNIQUE constraint failed", params={}, orig=Exception()
    )
    repo = WatchlistRepository(session)

    data = WatchlistCreate(name="Duplicate List")
    with pytest.raises(ScreenerError, match="已存在同名的自选清单"):
        await repo.create_watchlist(uuid.uuid4(), data)
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_watchlist_repo_update_watchlist_not_found() -> None:
    session = _session(result=_result(scalar=None))
    repo = WatchlistRepository(session)

    res = await repo.update_watchlist(uuid.uuid4(), uuid.uuid4(), WatchlistUpdate(name="New Name"))
    assert res is None


@pytest.mark.asyncio
async def test_watchlist_repo_update_watchlist_success() -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    watchlist = Watchlist(
        id=wl_id,
        user_id=user_id,
        name="Old Name",
        description="Old Desc",
        is_default=False,
        created_at=_NOW,
        updated_at=_NOW,
    )

    session = _session(result=_result(scalar=watchlist))
    repo = WatchlistRepository(session)

    data = WatchlistUpdate(name="New Name", description="Updated description", is_default=True)
    res = await repo.update_watchlist(wl_id, user_id, data)

    assert res is watchlist
    assert watchlist.name == "New Name"
    assert watchlist.description == "Updated description"
    assert watchlist.is_default is True
    # Verify execute called for unsetting other defaults
    assert session.execute.await_count >= 1
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_watchlist_repo_update_watchlist_conflict_rolls_back() -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    watchlist = Watchlist(
        id=wl_id,
        user_id=user_id,
        name="Name A",
        created_at=_NOW,
        updated_at=_NOW,
    )
    session = _session(result=_result(scalar=watchlist))
    session.flush.side_effect = IntegrityError("duplicate key value", params={}, orig=Exception())
    repo = WatchlistRepository(session)

    with pytest.raises(ScreenerError, match="已存在同名的自选清单"):
        await repo.update_watchlist(wl_id, user_id, WatchlistUpdate(name="Name B"))
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_watchlist_repo_delete_watchlist_not_found() -> None:
    session = _session(result=_result(scalar=None))
    repo = WatchlistRepository(session)
    res = await repo.delete_watchlist(uuid.uuid4(), uuid.uuid4())
    assert res is False


@pytest.mark.asyncio
async def test_watchlist_repo_delete_watchlist_success() -> None:
    wl = Watchlist(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="To Delete",
        created_at=_NOW,
        updated_at=_NOW,
    )
    session = _session(result=_result(scalar=wl))
    repo = WatchlistRepository(session)

    res = await repo.delete_watchlist(wl.id, wl.user_id)
    assert res is True
    session.delete.assert_called_once_with(wl)
    session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# WatchlistItem 单元测试与重复标的防御
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchlist_repo_add_item_watchlist_not_found() -> None:
    session = _session(result=_result(scalar=None))
    repo = WatchlistRepository(session)

    with pytest.raises(WatchlistNotFoundError, match="未找到指定的自选清单"):
        await repo.add_item(
            uuid.uuid4(),
            uuid.uuid4(),
            WatchlistItemCreate(symbol="NVDA"),
        )


@pytest.mark.asyncio
async def test_watchlist_repo_add_item_duplicate_symbol_precheck() -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    watchlist = Watchlist(
        id=wl_id,
        user_id=user_id,
        name="Main",
        created_at=_NOW,
        updated_at=_NOW,
    )
    existing_item = WatchlistItem(
        id=uuid.uuid4(),
        watchlist_id=wl_id,
        symbol="NVDA",
        created_at=_NOW,
    )

    # First execute: get_watchlist -> watchlist
    # Second execute: select WatchlistItem -> existing_item
    session = _session()
    res1 = _result(scalar=watchlist)
    res2 = _result(scalar=existing_item)
    session.execute.side_effect = [res1, res2]

    repo = WatchlistRepository(session)
    with pytest.raises(DuplicateWatchlistItemError, match="已存在于该自选清单中") as exc_info:
        await repo.add_item(wl_id, user_id, WatchlistItemCreate(symbol="nvda"))

    assert exc_info.value.http_status == 409


@pytest.mark.asyncio
async def test_watchlist_repo_add_item_duplicate_integrity_error_handled() -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    watchlist = Watchlist(
        id=wl_id,
        user_id=user_id,
        name="Main",
        created_at=_NOW,
        updated_at=_NOW,
    )

    session = _session()
    res1 = _result(scalar=watchlist)
    res2 = _result(scalar=None)  # not found in pre-check
    session.execute.side_effect = [res1, res2]
    session.flush.side_effect = IntegrityError(
        "UNIQUE constraint failed: watchlist_items.watchlist_id, watchlist_items.symbol",
        params={},
        orig=Exception(),
    )

    repo = WatchlistRepository(session)
    with pytest.raises(DuplicateWatchlistItemError, match="已存在于该自选清单中"):
        await repo.add_item(wl_id, user_id, WatchlistItemCreate(symbol="AAPL"))

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_watchlist_repo_add_item_success_normalizes_symbol() -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    watchlist = Watchlist(
        id=wl_id,
        user_id=user_id,
        name="Main",
        created_at=_NOW,
        updated_at=_NOW,
    )

    session = _session()
    res1 = _result(scalar=watchlist)
    res2 = _result(scalar=None)
    session.execute.side_effect = [res1, res2]

    repo = WatchlistRepository(session)
    data = WatchlistItemCreate(
        symbol=" msft ",
        notes="High conviction AI stock",
        target_price=Decimal("450.0000"),
        theme_tags=["ai_chips", "cloud_saas"],
    )
    item = await repo.add_item(wl_id, user_id, data)

    assert item.symbol == "MSFT"
    assert item.watchlist_id == wl_id
    assert item.notes == "High conviction AI stock"
    assert item.target_price == Decimal("450.0000")
    assert item.theme_tags == ["ai_chips", "cloud_saas"]
    session.add.assert_called_once_with(item)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_watchlist_repo_update_item_not_found_raises() -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    item_id = uuid.uuid4()
    watchlist = Watchlist(id=wl_id, user_id=user_id, name="Main")

    session = _session()
    session.execute.side_effect = [_result(scalar=watchlist), _result(scalar=None)]
    repo = WatchlistRepository(session)

    with pytest.raises(WatchlistItemNotFoundError, match="未找到指定标的"):
        await repo.update_item(
            wl_id,
            item_id,
            user_id,
            WatchlistItemUpdate(notes="Updated"),
        )


@pytest.mark.asyncio
async def test_watchlist_repo_update_item_success() -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    item_id = uuid.uuid4()
    watchlist = Watchlist(id=wl_id, user_id=user_id, name="Main")
    item = WatchlistItem(
        id=item_id,
        watchlist_id=wl_id,
        symbol="AAPL",
        notes="Initial",
        target_price=Decimal("200.00"),
        theme_tags=[],
        created_at=_NOW,
    )

    session = _session()
    session.execute.side_effect = [_result(scalar=watchlist), _result(scalar=item)]
    repo = WatchlistRepository(session)

    data = WatchlistItemUpdate(
        notes="Revised note",
        target_price=Decimal("240.00"),
        theme_tags=["hardware"],
    )
    updated = await repo.update_item(wl_id, item_id, user_id, data)

    assert updated is item
    assert item.notes == "Revised note"
    assert item.target_price == Decimal("240.00")
    assert item.theme_tags == ["hardware"]
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_watchlist_repo_remove_item_success() -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    item_id = uuid.uuid4()
    watchlist = Watchlist(id=wl_id, user_id=user_id, name="Main")
    item = WatchlistItem(id=item_id, watchlist_id=wl_id, symbol="GOOGL")

    session = _session()
    session.execute.side_effect = [_result(scalar=watchlist), _result(scalar=item)]
    repo = WatchlistRepository(session)

    res = await repo.remove_item(wl_id, item_id, user_id)
    assert res is True
    session.delete.assert_called_once_with(item)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_watchlist_repo_remove_item_watchlist_not_found() -> None:
    session = _session(result=_result(scalar=None))
    repo = WatchlistRepository(session)

    with pytest.raises(WatchlistNotFoundError, match="未找到指定的自选清单"):
        await repo.remove_item(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_watchlist_repo_remove_item_item_not_found() -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    watchlist = Watchlist(id=wl_id, user_id=user_id, name="Main")

    session = _session()
    session.execute.side_effect = [_result(scalar=watchlist), _result(scalar=None)]
    repo = WatchlistRepository(session)

    with pytest.raises(WatchlistItemNotFoundError, match="未找到指定标的"):
        await repo.remove_item(wl_id, uuid.uuid4(), user_id)
