"""M8-T04: ScreenerService 统一门面服务单元测试。

验证策略筛选全生命周期流转 (pending -> running -> succeeded / failed)、
股票池/主题查询转发、自选清单业务管理、多租户安全拦截与投研导出。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.clock import FrozenClock
from app.modules.screener.exceptions import (
    ScreenerExecutionError,
    ScreenerRunNotFoundError,
    ThemeNotFoundError,
    UniverseNotFoundError,
    WatchlistItemNotFoundError,
    WatchlistNotFoundError,
)
from app.modules.screener.models import ScreenerResult, ScreenerRun, Watchlist, WatchlistItem
from app.modules.screener.ports import (
    ScreenerExecutorProtocol,
    ScreenerRepositoryProtocol,
    UniverseManagerProtocol,
    WatchlistRepositoryProtocol,
)
from app.modules.screener.schemas import (
    ExportToResearchRequest,
    ScreenerResultItem,
    ScreenerRunCreate,
    ThemeCardItem,
    ThemeCardsResponse,
    ThemeInfo,
    UniverseInfo,
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemUpdate,
    WatchlistUpdate,
)
from app.modules.screener.service import ScreenerService

_FIXED_TIME = datetime(2026, 11, 15, 14, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(_FIXED_TIME)


@pytest.fixture
def mock_screener_repo() -> AsyncMock:
    repo = AsyncMock(spec=ScreenerRepositoryProtocol)
    repo.create_run.side_effect = lambda run: run
    repo.update_run.side_effect = lambda run: run
    return repo


@pytest.fixture
def mock_watchlist_repo() -> AsyncMock:
    return AsyncMock(spec=WatchlistRepositoryProtocol)


@pytest.fixture
def mock_universe_mgr() -> MagicMock:
    mgr = MagicMock(spec=UniverseManagerProtocol)
    mgr.list_universes.return_value = [
        UniverseInfo(id="sp500", name="标普500", description="标普500指数成分股", symbol_count=503)
    ]
    mgr.get_universe_symbols.side_effect = lambda uid, custom_symbols=None: (
        custom_symbols if uid == "custom" and custom_symbols else ["AAPL", "MSFT", "NVDA"]
    )
    mgr.list_themes.return_value = [
        ThemeInfo(
            id="ai_chips",
            name="AI 芯片与算力核心",
            category="tech",
            tagline="算力为王",
            description="英伟达、博通等核心算力提供商",
            stocks=[],
        )
    ]
    mgr.get_theme.side_effect = lambda tid: (
        ThemeInfo(
            id=tid,
            name="AI 芯片",
            category="tech",
            tagline="算力",
            description="芯片",
            stocks=[],
        )
        if tid == "ai_chips"
        else (_ for _ in ()).throw(ThemeNotFoundError(f"主题未找到: {tid}"))
    )
    return mgr


@pytest.fixture
def mock_executor() -> AsyncMock:
    executor = AsyncMock(spec=ScreenerExecutorProtocol)
    return executor


# ---------------------------------------------------------------------------
# run_screener 筛选生命周期测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_screener_success_lifecycle(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
    mock_universe_mgr: MagicMock,
    mock_executor: AsyncMock,
    clock: FrozenClock,
) -> None:
    user_id = uuid.uuid4()
    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
        universe_manager=mock_universe_mgr,
        executor=mock_executor,
        clock=clock,
    )

    result_item1 = ScreenerResultItem(
        symbol="NVDA",
        rank=1,
        score=Decimal("94.5000"),
        signal="STRONG_BUY",
        metrics_snapshot={"pe": 35.2},
    )
    result_item2 = ScreenerResultItem(
        symbol="AAPL",
        rank=2,
        score=Decimal("82.0000"),
        signal="BUY",
        metrics_snapshot={"pe": 28.1},
    )
    mock_executor.execute_screening.return_value = ([result_item1, result_item2], [])

    req = ScreenerRunCreate(
        strategy_id="momentum_top",
        universe="sp500",
        params={"min_score": 80},
    )
    res = await service.run_screener(user_id, req)

    # 验证筛选任务流转与返回
    assert res.user_id == user_id
    assert res.strategy_id == "momentum_top"
    assert res.universe == "sp500"
    assert res.status == "succeeded"
    assert res.total_symbols == 3
    assert res.matched_count == 2
    assert res.failed_count == 0
    assert len(res.results) == 2
    assert res.results[0].symbol == "NVDA"
    assert res.results[0].rank == 1
    assert res.results[1].symbol == "AAPL"
    assert res.results[1].rank == 2

    # 验证持久化调用
    assert mock_screener_repo.create_run.await_count == 1
    assert mock_screener_repo.update_run.await_count == 1
    created_run = mock_screener_repo.create_run.await_args[0][0]
    assert created_run.user_id == user_id
    assert created_run.status == "succeeded"


@pytest.mark.asyncio
async def test_run_screener_custom_symbols(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
    mock_universe_mgr: MagicMock,
    mock_executor: AsyncMock,
    clock: FrozenClock,
) -> None:
    user_id = uuid.uuid4()
    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
        universe_manager=mock_universe_mgr,
        executor=mock_executor,
        clock=clock,
    )

    mock_executor.execute_screening.return_value = ([], [])
    req = ScreenerRunCreate(
        strategy_id="value_investing",
        universe="custom",
        custom_symbols=["TSLA", "AMD"],
    )
    res = await service.run_screener(user_id, req)

    mock_universe_mgr.get_universe_symbols.assert_called_once_with(
        "custom", custom_symbols=["TSLA", "AMD"]
    )
    assert res.total_symbols == 2
    assert res.status == "succeeded"


@pytest.mark.asyncio
async def test_run_screener_empty_universe_raises(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
    mock_universe_mgr: MagicMock,
    mock_executor: AsyncMock,
    clock: FrozenClock,
) -> None:
    mock_universe_mgr.get_universe_symbols.side_effect = None
    mock_universe_mgr.get_universe_symbols.return_value = []
    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
        universe_manager=mock_universe_mgr,
        executor=mock_executor,
        clock=clock,
    )

    req = ScreenerRunCreate(strategy_id="strat1", universe="empty_pool")
    with pytest.raises(UniverseNotFoundError, match="无可用标的"):
        await service.run_screener(uuid.uuid4(), req)


@pytest.mark.asyncio
async def test_run_screener_no_executor_fails(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
    mock_universe_mgr: MagicMock,
    clock: FrozenClock,
) -> None:
    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
        universe_manager=mock_universe_mgr,
        executor=None,
        clock=clock,
    )

    req = ScreenerRunCreate(strategy_id="strat1", universe="sp500")
    with pytest.raises(ScreenerExecutionError, match="未配置筛选执行器"):
        await service.run_screener(uuid.uuid4(), req)

    # 验证任务状态被更新为 failed
    assert mock_screener_repo.update_run.await_count == 1
    updated_run = mock_screener_repo.update_run.await_args[0][0]
    assert updated_run.status == "failed"
    assert "未配置筛选执行器" in (updated_run.error_message or "")


@pytest.mark.asyncio
async def test_run_screener_executor_exception_handled(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
    mock_universe_mgr: MagicMock,
    mock_executor: AsyncMock,
    clock: FrozenClock,
) -> None:
    mock_executor.execute_screening.side_effect = RuntimeError("Network timeout")
    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
        universe_manager=mock_universe_mgr,
        executor=mock_executor,
        clock=clock,
    )

    req = ScreenerRunCreate(strategy_id="strat1", universe="sp500")
    with pytest.raises(ScreenerExecutionError, match="Network timeout"):
        await service.run_screener(uuid.uuid4(), req)

    assert mock_screener_repo.update_run.await_count == 1
    updated_run = mock_screener_repo.update_run.await_args[0][0]
    assert updated_run.status == "failed"
    assert "Network timeout" in (updated_run.error_message or "")


# ---------------------------------------------------------------------------
# get_screener_run / list_runs 多租户与查询测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_screener_run_found(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
    clock: FrozenClock,
) -> None:
    user_id = uuid.uuid4()
    run_id = uuid.uuid4()

    run = ScreenerRun(
        id=run_id,
        user_id=user_id,
        strategy_id="momentum_top",
        universe="sp500",
        params={},
        status="succeeded",
        total_symbols=100,
        matched_count=1,
        failed_count=0,
        created_at=_FIXED_TIME,
        completed_at=_FIXED_TIME,
    )
    run.results = [
        ScreenerResult(
            id=uuid.uuid4(),
            run_id=run_id,
            symbol="NVDA",
            rank=1,
            score=Decimal("95.00"),
            signal="BUY",
            metrics_snapshot={},
            created_at=_FIXED_TIME,
        )
    ]
    mock_screener_repo.get_run.return_value = run

    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
        clock=clock,
    )
    res = await service.get_screener_run(run_id, user_id)

    assert res.id == run_id
    assert res.user_id == user_id
    assert len(res.results) == 1
    assert res.results[0].symbol == "NVDA"


@pytest.mark.asyncio
async def test_get_screener_run_not_found_or_wrong_tenant(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
    clock: FrozenClock,
) -> None:
    mock_screener_repo.get_run.return_value = None
    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
        clock=clock,
    )

    with pytest.raises(ScreenerRunNotFoundError, match="未找到指定的筛选任务记录"):
        await service.get_screener_run(uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_list_runs_returns_pydantic_reads(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
    clock: FrozenClock,
) -> None:
    user_id = uuid.uuid4()
    run1 = ScreenerRun(
        id=uuid.uuid4(),
        user_id=user_id,
        strategy_id="strat1",
        universe="sp500",
        params={},
        status="succeeded",
        total_symbols=500,
        matched_count=10,
        failed_count=0,
        created_at=_FIXED_TIME,
    )
    run1.results = []
    mock_screener_repo.list_runs.return_value = [run1]

    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
        clock=clock,
    )
    runs = await service.list_runs(user_id, limit=10, offset=0)
    assert len(runs) == 1
    assert runs[0].id == run1.id
    assert runs[0].strategy_id == "strat1"


# ---------------------------------------------------------------------------
# 股票池与主题 passthrough 测试
# ---------------------------------------------------------------------------


def test_universe_and_themes_passthrough(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
    mock_universe_mgr: MagicMock,
) -> None:
    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
        universe_manager=mock_universe_mgr,
    )

    universes = service.list_universes()
    assert len(universes) == 1
    assert universes[0].id == "sp500"

    themes = service.list_themes()
    assert len(themes) == 1
    assert themes[0].id == "ai_chips"

    theme = service.get_theme("ai_chips")
    assert theme.id == "ai_chips"

    with pytest.raises(ThemeNotFoundError):
        service.get_theme("non_existent")


@pytest.mark.asyncio
async def test_generate_theme_cards_with_generator(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
    mock_universe_mgr: MagicMock,
) -> None:
    mock_generator = AsyncMock()
    card_item = ThemeCardItem(
        symbol="NVDA",
        name="英伟达",
        one_line_intro="全球 AI 算力龙头",
        why_watch="数据中心需求暴增",
        financial_strengths=["毛利率高达75%"],
        main_risks=["客户集中度高"],
        suitable_for=["成长型投资者"],
        more_attractive_when="估值回调至30倍PE",
    )
    expected_resp = ThemeCardsResponse(
        theme_id="ai_chips",
        theme_name="AI 芯片",
        cards=[card_item],
        as_of=_FIXED_TIME,
        prompt_version="v1.0",
    )
    mock_generator.generate_theme_cards.return_value = expected_resp

    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
        universe_manager=mock_universe_mgr,
        theme_cards_generator=mock_generator,
    )

    resp = await service.generate_theme_cards("ai_chips", uuid.uuid4())
    assert resp.theme_id == "ai_chips"
    assert len(resp.cards) == 1
    assert resp.cards[0].symbol == "NVDA"


@pytest.mark.asyncio
async def test_generate_theme_cards_unimplemented(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
    mock_universe_mgr: MagicMock,
) -> None:
    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
        universe_manager=mock_universe_mgr,
        theme_cards_generator=None,
    )

    with pytest.raises(NotImplementedError, match="M8-T05"):
        await service.generate_theme_cards("ai_chips", uuid.uuid4())


# ---------------------------------------------------------------------------
# 自选清单门面 CRUD 测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchlist_facade_crud(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
    clock: FrozenClock,
) -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    item_id = uuid.uuid4()

    mock_wl = Watchlist(
        id=wl_id,
        user_id=user_id,
        name="Tech",
        description="Tech stocks",
        is_default=True,
        created_at=_FIXED_TIME,
        updated_at=_FIXED_TIME,
    )
    mock_item = WatchlistItem(
        id=item_id,
        watchlist_id=wl_id,
        symbol="NVDA",
        notes="Core hold",
        target_price=Decimal("150.00"),
        theme_tags=["ai_chips"],
        created_at=_FIXED_TIME,
    )
    mock_wl.items = [mock_item]

    mock_watchlist_repo.list_watchlists.return_value = [mock_wl]
    mock_watchlist_repo.get_watchlist.return_value = mock_wl
    mock_watchlist_repo.create_watchlist.return_value = mock_wl
    mock_watchlist_repo.update_watchlist.return_value = mock_wl
    mock_watchlist_repo.delete_watchlist.return_value = True
    mock_watchlist_repo.add_item.return_value = mock_item
    mock_watchlist_repo.update_item.return_value = mock_item
    mock_watchlist_repo.remove_item.return_value = True

    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
        clock=clock,
    )

    # 1. list
    lists = await service.list_watchlists(user_id)
    assert len(lists) == 1
    assert lists[0].id == wl_id
    assert len(lists[0].items) == 1

    # 2. get
    wl_read = await service.get_watchlist(wl_id, user_id)
    assert wl_read.name == "Tech"

    # 3. create
    c_read = await service.create_watchlist(user_id, WatchlistCreate(name="New", is_default=False))
    assert c_read.id == wl_id

    # 4. update
    u_read = await service.update_watchlist(wl_id, user_id, WatchlistUpdate(name="Renamed"))
    assert u_read.id == wl_id

    # 5. delete
    assert await service.delete_watchlist(wl_id, user_id) is True

    # 6. add item
    added_item = await service.add_watchlist_item(
        wl_id, user_id, WatchlistItemCreate(symbol="NVDA")
    )
    assert added_item.symbol == "NVDA"

    # 7. update item
    updated_item = await service.update_watchlist_item(
        wl_id, item_id, user_id, WatchlistItemUpdate(notes="Updated note")
    )
    assert updated_item.id == item_id

    # 8. remove item
    assert await service.remove_watchlist_item(wl_id, item_id, user_id) is True


@pytest.mark.asyncio
async def test_watchlist_facade_not_found_handling(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
) -> None:
    mock_watchlist_repo.get_watchlist.return_value = None
    mock_watchlist_repo.update_watchlist.return_value = None
    mock_watchlist_repo.delete_watchlist.return_value = False
    mock_watchlist_repo.update_item.return_value = None

    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
    )

    uid = uuid.uuid4()
    wlid = uuid.uuid4()
    with pytest.raises(WatchlistNotFoundError):
        await service.get_watchlist(wlid, uid)

    with pytest.raises(WatchlistNotFoundError):
        await service.update_watchlist(wlid, uid, WatchlistUpdate(name="Test"))

    with pytest.raises(WatchlistNotFoundError):
        await service.delete_watchlist(wlid, uid)

    with pytest.raises(WatchlistItemNotFoundError):
        await service.update_watchlist_item(
            wlid, uuid.uuid4(), uid, WatchlistItemUpdate(notes="Test")
        )


# ---------------------------------------------------------------------------
# export_to_research 测试
# ---------------------------------------------------------------------------


def test_export_to_research(
    mock_screener_repo: AsyncMock,
    mock_watchlist_repo: AsyncMock,
) -> None:
    service = ScreenerService(
        screener_repo=mock_screener_repo,
        watchlist_repo=mock_watchlist_repo,
    )

    req = ExportToResearchRequest(
        symbols=["nvda", "aapl", "msft"],
        target_action="compare",
    )
    payload = service.export_to_research(req)

    assert payload["target_action"] == "compare"
    assert payload["symbols"] == ["NVDA", "AAPL", "MSFT"]
    assert payload["status"] == "ready"
    assert payload["target_endpoint"] == "/api/v1/research/compare"
