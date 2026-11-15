"""M8-T06 筛选器与主题自选 REST API 单元测试。

验证范围：
1. 依赖提取与 HARD-01 鉴权辅助方法（_extract_user_id, get_current_user）；
2. 服务依赖提供器（get_screener_service, set_screener_service, set_screener_service_provider）；
3. 服务装配工厂（create_screener_service）；
4. REST API 路由处理函数直接调用行为（股票池、筛选运行、主题、AI卡片、
   自选清单CRUD、标的管理、投研导出）；
5. 边界与异常分支覆盖（空自选导出抛出 ValidationFailed 等）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import Unauthenticated, ValidationFailed
from app.modules.screener.api import (
    _extract_user_id,
    add_watchlist_item,
    create_screener_run,
    create_watchlist,
    delete_watchlist,
    export_screener_results,
    export_watchlist_to_research,
    generate_theme_cards,
    get_current_user,
    get_screener_run,
    get_screener_service,
    get_theme,
    get_watchlist,
    list_screener_runs,
    list_themes,
    list_universes,
    list_watchlists,
    remove_watchlist_item,
    set_screener_service,
    set_screener_service_provider,
    update_watchlist,
    update_watchlist_item,
)
from app.modules.screener.ports import ScreenerServiceProtocol
from app.modules.screener.schemas import (
    ExportToResearchRequest,
    ScreenerRunCreate,
    ScreenerRunRead,
    ThemeCardItem,
    ThemeCardsResponse,
    ThemeInfo,
    ThemeStockItem,
    UniverseInfo,
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemRead,
    WatchlistItemUpdate,
    WatchlistRead,
    WatchlistUpdate,
)
from app.modules.screener.service import create_screener_service

pytestmark = pytest.mark.unit


# =============================================================================
# 1. 鉴权与辅助方法测试
# =============================================================================


def test_extract_user_id_from_uuid() -> None:
    uid = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.id = uid
    assert _extract_user_id(mock_user) == uid


def test_extract_user_id_from_valid_str() -> None:
    uid = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.id = str(uid)
    assert _extract_user_id(mock_user) == uid


def test_extract_user_id_from_dict() -> None:
    uid = uuid.uuid4()
    assert _extract_user_id({"id": uid}) == uid
    assert _extract_user_id({"id": str(uid)}) == uid


def test_extract_user_id_invalid_str_raises() -> None:
    mock_user = MagicMock()
    mock_user.id = "not-a-valid-uuid"
    with pytest.raises(Unauthenticated, match="无效的用户 ID 格式"):
        _extract_user_id(mock_user)


def test_extract_user_id_missing_raises() -> None:
    mock_user = object()
    with pytest.raises(Unauthenticated, match="无效的用户认证凭据"):
        _extract_user_id(mock_user)


def test_extract_user_id_invalid_type_raises() -> None:
    mock_user = MagicMock()
    mock_user.id = 123456
    with pytest.raises(Unauthenticated, match="无效的用户认证凭据"):
        _extract_user_id(mock_user)


def test_get_current_user_present() -> None:
    request = MagicMock()
    mock_user = MagicMock()
    request.state.user = mock_user
    assert get_current_user(request) is mock_user


def test_get_current_user_absent_raises() -> None:
    request = MagicMock()
    request.state.user = None
    with pytest.raises(Unauthenticated, match="需要认证才能访问筛选器服务"):
        get_current_user(request)


# =============================================================================
# 2. ScreenerService 依赖注入提供器测试
# =============================================================================


def test_screener_service_provider_flow() -> None:
    # 恢复环境
    set_screener_service(None)
    set_screener_service_provider(None)

    # 未配置前抛出 RuntimeError
    mock_session = AsyncMock()
    with pytest.raises(RuntimeError, match="ScreenerService has not been configured"):
        get_screener_service(mock_session)

    # 静态服务配置
    mock_svc = MagicMock(spec=ScreenerServiceProtocol)
    set_screener_service(mock_svc)
    assert get_screener_service(mock_session) is mock_svc

    # 动态工厂配置
    set_screener_service(None)
    mock_factory = MagicMock(return_value=mock_svc)
    set_screener_service_provider(mock_factory)
    assert get_screener_service(mock_session) is mock_svc
    mock_factory.assert_called_once_with(mock_session)

    # 清理
    set_screener_service(None)
    set_screener_service_provider(None)


# =============================================================================
# 3. 组合根工厂 create_screener_service 测试
# =============================================================================


def test_create_screener_service_wiring() -> None:
    mock_session = AsyncMock()
    mock_strategy = MagicMock()
    mock_data = MagicMock()
    mock_ai = MagicMock()

    service = create_screener_service(
        session=mock_session,
        strategy_service=mock_strategy,
        data_service=mock_data,
        ai_service=mock_ai,
    )
    assert service is not None
    assert service._screener_repo is not None
    assert service._watchlist_repo is not None
    assert service._executor is not None
    assert service._theme_cards_generator is not None


def test_create_screener_service_without_strategy() -> None:
    mock_session = AsyncMock()
    service = create_screener_service(
        session=mock_session,
        strategy_service=None,
    )
    assert service is not None
    assert service._executor is None


# =============================================================================
# 4. REST API 路由处理函数单元测试
# =============================================================================


def test_list_universes_handler() -> None:
    mock_svc = MagicMock(spec=ScreenerServiceProtocol)
    mock_svc.list_universes.return_value = [
        UniverseInfo(
            id="sp500",
            name="标普500",
            description="标普500指数成分股",
            symbol_count=503,
        )
    ]
    mock_user = MagicMock()
    res = list_universes(current_user=mock_user, service=mock_svc)
    assert len(res) == 1
    assert res[0].id == "sp500"
    mock_svc.list_universes.assert_called_once()


@pytest.mark.asyncio
async def test_create_screener_run_handler() -> None:
    user_id = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_svc = AsyncMock(spec=ScreenerServiceProtocol)
    expected_read = ScreenerRunRead(
        id=uuid.uuid4(),
        user_id=user_id,
        universe="sp500",
        strategy_id="momentum",
        params={},
        status="succeeded",
        total_symbols=10,
        matched_count=2,
        failed_count=0,
        results=[],
        created_at=datetime.now(tz=UTC),
        completed_at=datetime.now(tz=UTC),
    )
    mock_svc.run_screener.return_value = expected_read

    req = ScreenerRunCreate(universe="sp500", strategy_id="momentum")
    res = await create_screener_run(request=req, current_user=mock_user, service=mock_svc)
    assert res == expected_read
    mock_svc.run_screener.assert_awaited_once_with(user_id=user_id, request=req)


@pytest.mark.asyncio
async def test_get_screener_run_handler() -> None:
    user_id = uuid.uuid4()
    run_id = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_svc = AsyncMock(spec=ScreenerServiceProtocol)
    expected_read = ScreenerRunRead(
        id=run_id,
        user_id=user_id,
        universe="sp500",
        strategy_id="momentum",
        params={},
        status="succeeded",
        total_symbols=10,
        matched_count=1,
        failed_count=0,
        results=[],
        created_at=datetime.now(tz=UTC),
    )
    mock_svc.get_screener_run.return_value = expected_read

    res = await get_screener_run(id=run_id, current_user=mock_user, service=mock_svc)
    assert res == expected_read
    mock_svc.get_screener_run.assert_awaited_once_with(run_id=run_id, user_id=user_id)


@pytest.mark.asyncio
async def test_list_screener_runs_handler() -> None:
    user_id = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_svc = AsyncMock(spec=ScreenerServiceProtocol)
    mock_svc.list_runs.return_value = []

    res = await list_screener_runs(current_user=mock_user, service=mock_svc, limit=10, offset=5)
    assert res == []
    mock_svc.list_runs.assert_awaited_once_with(user_id=user_id, limit=10, offset=5)


def test_export_screener_results_handler() -> None:
    mock_user = MagicMock()
    mock_svc = MagicMock(spec=ScreenerServiceProtocol)
    mock_svc.export_to_research.return_value = {
        "action": "compare",
        "symbols": ["AAPL", "MSFT"],
        "target_url": "/research/compare?symbols=AAPL,MSFT",
        "exported_count": 2,
    }

    req = ExportToResearchRequest(symbols=["AAPL", "MSFT"], target_action="compare")
    res = export_screener_results(request=req, current_user=mock_user, service=mock_svc)
    assert res["action"] == "compare"
    mock_svc.export_to_research.assert_called_once_with(req)


def test_list_themes_handler() -> None:
    mock_user = MagicMock()
    mock_svc = MagicMock(spec=ScreenerServiceProtocol)
    mock_svc.list_themes.return_value = [
        ThemeInfo(
            id="ai_chips",
            name="AI 芯片与算力",
            category="tech",
            tagline="算力底座",
            description="核心算力",
            stocks=[
                ThemeStockItem(
                    symbol="NVDA",
                    name="NVIDIA",
                    sector="Semiconductors",
                    sub_industry="GPUs",
                    market_cap_tier="mega",
                )
            ],
        )
    ]
    res = list_themes(current_user=mock_user, service=mock_svc)
    assert len(res) == 1
    assert res[0].id == "ai_chips"
    mock_svc.list_themes.assert_called_once()


def test_get_theme_handler() -> None:
    mock_user = MagicMock()
    mock_svc = MagicMock(spec=ScreenerServiceProtocol)
    expected_theme = ThemeInfo(
        id="ai_chips",
        name="AI 芯片与算力",
        category="tech",
        tagline="算力底座",
        description="核心算力",
        stocks=[],
    )
    mock_svc.get_theme.return_value = expected_theme
    res = get_theme(id="ai_chips", current_user=mock_user, service=mock_svc)
    assert res == expected_theme
    mock_svc.get_theme.assert_called_once_with("ai_chips")


@pytest.mark.asyncio
async def test_generate_theme_cards_handler() -> None:
    user_id = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_svc = AsyncMock(spec=ScreenerServiceProtocol)
    expected_resp = ThemeCardsResponse(
        theme_id="ai_chips",
        theme_name="AI 芯片",
        cards=[
            ThemeCardItem(
                symbol="NVDA",
                name="英伟达",
                one_line_intro="全球 GPU 绝对龙头",
                why_watch="AI 训练算力底座",
                financial_strengths=["毛利率 75%"],
                main_risks=["供应链依赖"],
                suitable_for=["成长型投资者"],
                more_attractive_when="估值回调时",
            )
        ],
        as_of=datetime.now(tz=UTC),
        prompt_version="1.0",
    )
    mock_svc.generate_theme_cards.return_value = expected_resp

    res = await generate_theme_cards(id="ai_chips", current_user=mock_user, service=mock_svc)
    assert res == expected_resp
    mock_svc.generate_theme_cards.assert_awaited_once_with(theme_id="ai_chips", user_id=user_id)


@pytest.mark.asyncio
async def test_watchlist_crud_handlers() -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    item_id = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_svc = AsyncMock(spec=ScreenerServiceProtocol)

    # 1. list_watchlists
    mock_svc.list_watchlists.return_value = []
    res_list = await list_watchlists(current_user=mock_user, service=mock_svc)
    assert res_list == []
    mock_svc.list_watchlists.assert_awaited_once_with(user_id=user_id)

    # 2. create_watchlist
    create_body = WatchlistCreate(name="我的自选", description="科技股跟踪")
    expected_read = WatchlistRead(
        id=wl_id,
        user_id=user_id,
        name="我的自选",
        description="科技股跟踪",
        is_default=False,
        items=[],
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    mock_svc.create_watchlist.return_value = expected_read
    res_create = await create_watchlist(body=create_body, current_user=mock_user, service=mock_svc)
    assert res_create == expected_read
    mock_svc.create_watchlist.assert_awaited_once_with(user_id=user_id, data=create_body)

    # 3. get_watchlist
    mock_svc.get_watchlist.return_value = expected_read
    res_get = await get_watchlist(id=wl_id, current_user=mock_user, service=mock_svc)
    assert res_get == expected_read
    mock_svc.get_watchlist.assert_awaited_once_with(watchlist_id=wl_id, user_id=user_id)

    # 4. update_watchlist
    update_body = WatchlistUpdate(name="更新后的名称")
    mock_svc.update_watchlist.return_value = expected_read
    res_update = await update_watchlist(
        id=wl_id, body=update_body, current_user=mock_user, service=mock_svc
    )
    assert res_update == expected_read
    mock_svc.update_watchlist.assert_awaited_once_with(
        watchlist_id=wl_id, user_id=user_id, data=update_body
    )

    # 5. delete_watchlist
    del_resp = await delete_watchlist(id=wl_id, current_user=mock_user, service=mock_svc)
    assert del_resp.status_code == 204
    mock_svc.delete_watchlist.assert_awaited_once_with(watchlist_id=wl_id, user_id=user_id)

    # 6. add_watchlist_item
    item_create = WatchlistItemCreate(symbol="AAPL", target_price=Decimal("190.00"))
    item_read = WatchlistItemRead(
        id=item_id,
        watchlist_id=wl_id,
        symbol="AAPL",
        target_price=Decimal("190.00"),
        notes="",
        theme_tags=[],
        created_at=datetime.now(tz=UTC),
    )
    mock_svc.add_watchlist_item.return_value = item_read
    res_add_item = await add_watchlist_item(
        id=wl_id, body=item_create, current_user=mock_user, service=mock_svc
    )
    assert res_add_item == item_read
    mock_svc.add_watchlist_item.assert_awaited_once_with(
        watchlist_id=wl_id, user_id=user_id, data=item_create
    )

    # 7. update_watchlist_item
    item_update = WatchlistItemUpdate(notes="逢低关注")
    mock_svc.update_watchlist_item.return_value = item_read
    res_up_item = await update_watchlist_item(
        id=wl_id,
        item_id=item_id,
        body=item_update,
        current_user=mock_user,
        service=mock_svc,
    )
    assert res_up_item == item_read
    mock_svc.update_watchlist_item.assert_awaited_once_with(
        watchlist_id=wl_id, item_id=item_id, user_id=user_id, data=item_update
    )

    # 8. remove_watchlist_item
    rem_resp = await remove_watchlist_item(
        id=wl_id, item_id=item_id, current_user=mock_user, service=mock_svc
    )
    assert rem_resp.status_code == 204
    mock_svc.remove_watchlist_item.assert_awaited_once_with(
        watchlist_id=wl_id, item_id=item_id, user_id=user_id
    )


@pytest.mark.asyncio
async def test_export_watchlist_to_research_handlers() -> None:
    user_id = uuid.uuid4()
    wl_id = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_svc = AsyncMock(spec=ScreenerServiceProtocol)

    # Case 1: Watchlist has items -> success export
    item1 = WatchlistItemRead(
        id=uuid.uuid4(),
        watchlist_id=wl_id,
        symbol="AAPL",
        target_price=None,
        notes="",
        theme_tags=[],
        created_at=datetime.now(tz=UTC),
    )
    item2 = WatchlistItemRead(
        id=uuid.uuid4(),
        watchlist_id=wl_id,
        symbol="NVDA",
        target_price=None,
        notes="",
        theme_tags=[],
        created_at=datetime.now(tz=UTC),
    )
    wl_read = WatchlistRead(
        id=wl_id,
        user_id=user_id,
        name="自选",
        description="",
        is_default=False,
        items=[item1, item2],
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    mock_svc.get_watchlist.return_value = wl_read
    mock_svc.export_to_research.return_value = {
        "action": "compare",
        "symbols": ["AAPL", "NVDA"],
        "target_url": "/research/compare?symbols=AAPL,NVDA",
        "exported_count": 2,
    }

    res = await export_watchlist_to_research(
        id=wl_id,
        current_user=mock_user,
        service=mock_svc,
        target_action="compare",
    )
    assert res["action"] == "compare"
    assert res["symbols"] == ["AAPL", "NVDA"]

    # Case 2: Watchlist is empty -> raises ValidationFailed
    empty_wl = WatchlistRead(
        id=wl_id,
        user_id=user_id,
        name="空自选",
        description="",
        is_default=False,
        items=[],
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    mock_svc.get_watchlist.return_value = empty_wl
    with pytest.raises(ValidationFailed, match="自选清单为空"):
        await export_watchlist_to_research(
            id=wl_id,
            current_user=mock_user,
            service=mock_svc,
            target_action="compare",
        )
