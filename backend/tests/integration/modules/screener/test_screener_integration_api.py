"""M8-T06 筛选器与主题自选 REST API 集成测试。

全面验证：
1. HARD-01 鉴权守卫（未登录请求一律拦截并返回 401 UNAUTHENTICATED）；
2. 认证用户全量 REST 端点调用与正确响应（HTTP 200 / 201 / 204）：
   - GET /api/v1/universes
   - POST /api/v1/screener/runs
   - GET /api/v1/screener/runs/{id}
   - GET /api/v1/screener/runs
   - POST /api/v1/screener/export
   - GET /api/v1/themes
   - GET /api/v1/themes/{id}
   - POST /api/v1/themes/{id}/cards
   - GET /api/v1/watchlists
   - POST /api/v1/watchlists
   - GET /api/v1/watchlists/{id}
   - PUT /api/v1/watchlists/{id}
   - DELETE /api/v1/watchlists/{id}
   - POST /api/v1/watchlists/{id}/items
   - PUT /api/v1/watchlists/{id}/items/{item_id}
   - DELETE /api/v1/watchlists/{id}/items/{item_id}
   - POST /api/v1/watchlists/{id}/export
3. 异常映射与错误状态码验证：
   - 404 NOT_FOUND（UniverseNotFound, ThemeNotFound, ScreenerRunNotFound 等）
   - 409 STATE_CONFLICT（DuplicateWatchlistItemError）
   - 400 VALIDATION_ERROR（空自选导出 ValidationFailed）
   - 500 INTERNAL_ERROR（ScreenerExecutionError）
   - 422 VALIDATION_ERROR（无效参数 / UUID 校验失败）
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.deps import current_user
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.schemas import AuthenticatedUser, UserSettings
from app.modules.screener.api import get_current_user, get_screener_service
from app.modules.screener.exceptions import (
    DuplicateWatchlistItemError,
    ScreenerExecutionError,
    ScreenerRunNotFoundError,
    StrategyNotFoundError,
    ThemeNotFoundError,
    UniverseNotFoundError,
    WatchlistItemNotFoundError,
    WatchlistNotFoundError,
)
from app.modules.screener.ports import ScreenerServiceProtocol
from app.modules.screener.schemas import (
    ScreenerRunRead,
    ThemeCardItem,
    ThemeCardsResponse,
    ThemeInfo,
    ThemeStockItem,
    UniverseInfo,
    WatchlistItemRead,
    WatchlistRead,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def auth_user() -> AuthenticatedUser:
    """Mock 当前登录用户。"""
    return AuthenticatedUser(
        id=uuid.uuid4(),
        email="screener_trader@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(),
    )


@pytest.fixture
def mock_screener_service(auth_user: AuthenticatedUser) -> AsyncMock:
    """Mock ScreenerServiceProtocol 实例。"""
    service = AsyncMock(spec=ScreenerServiceProtocol)

    # 预设通用返回值
    service.list_universes.return_value = [
        UniverseInfo(
            id="sp500",
            name="标普500",
            description="标普500指数成分股",
            symbol_count=503,
        )
    ]
    service.list_themes.return_value = [
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
    service.get_theme.return_value = ThemeInfo(
        id="ai_chips",
        name="AI 芯片与算力",
        category="tech",
        tagline="算力底座",
        description="核心算力",
        stocks=[],
    )
    service.generate_theme_cards.return_value = ThemeCardsResponse(
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
    service.export_to_research.return_value = {
        "action": "compare",
        "symbols": ["AAPL", "MSFT"],
        "target_url": "/research/compare?symbols=AAPL,MSFT",
        "exported_count": 2,
    }

    run_read = ScreenerRunRead(
        id=uuid.uuid4(),
        user_id=auth_user.id,
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
    service.run_screener.return_value = run_read
    service.get_screener_run.return_value = run_read
    service.list_runs.return_value = [run_read]

    wl_id = uuid.uuid4()
    item_read = WatchlistItemRead(
        id=uuid.uuid4(),
        watchlist_id=wl_id,
        symbol="AAPL",
        target_price=Decimal("190.00"),
        notes="核心标的",
        theme_tags=["tech"],
        created_at=datetime.now(tz=UTC),
    )
    wl_read = WatchlistRead(
        id=wl_id,
        user_id=auth_user.id,
        name="科技龙头",
        description="跟踪美股龙头",
        is_default=True,
        items=[item_read],
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    service.list_watchlists.return_value = [wl_read]
    service.create_watchlist.return_value = wl_read
    service.get_watchlist.return_value = wl_read
    service.update_watchlist.return_value = wl_read
    service.delete_watchlist.return_value = None
    service.add_watchlist_item.return_value = item_read
    service.update_watchlist_item.return_value = item_read
    service.remove_watchlist_item.return_value = None

    return service


def _setup_auth(
    app: FastAPI,
    auth_user: AuthenticatedUser,
    mock_service: AsyncMock,
) -> None:
    """在 FastAPI 中注入模拟鉴权依赖和服务实例。"""

    async def _mock_current_user(request: Request) -> AuthenticatedUser:
        request.state.user = auth_user
        return auth_user

    app.dependency_overrides[current_user] = _mock_current_user
    app.dependency_overrides[get_current_user] = lambda: auth_user
    app.dependency_overrides[get_screener_service] = lambda: mock_service


# =============================================================================
# 1. HARD-01 鉴权守卫测试（未认证统一 401 UNAUTHENTICATED）
# =============================================================================


async def test_unauthenticated_requests(client: httpx.AsyncClient) -> None:
    random_id = uuid.uuid4()

    endpoints = [
        ("GET", "/api/v1/universes", None),
        ("POST", "/api/v1/screener/runs", {"universe": "sp500", "strategy_id": "momentum"}),
        ("GET", f"/api/v1/screener/runs/{random_id}", None),
        ("GET", "/api/v1/screener/runs", None),
        ("POST", "/api/v1/screener/export", {"symbols": ["AAPL"], "target_action": "compare"}),
        ("GET", "/api/v1/themes", None),
        ("GET", "/api/v1/themes/ai_chips", None),
        ("POST", "/api/v1/themes/ai_chips/cards", None),
        ("GET", "/api/v1/watchlists", None),
        ("POST", "/api/v1/watchlists", {"name": "自选"}),
        ("GET", f"/api/v1/watchlists/{random_id}", None),
        ("PUT", f"/api/v1/watchlists/{random_id}", {"name": "新名称"}),
        ("DELETE", f"/api/v1/watchlists/{random_id}", None),
        ("POST", f"/api/v1/watchlists/{random_id}/items", {"symbol": "AAPL"}),
        ("PUT", f"/api/v1/watchlists/{random_id}/items/{random_id}", {"notes": "更新"}),
        ("DELETE", f"/api/v1/watchlists/{random_id}/items/{random_id}", None),
        ("POST", f"/api/v1/watchlists/{random_id}/export", None),
    ]

    for method, path, json_data in endpoints:
        if method == "GET":
            resp = await client.get(path)
        elif method == "POST":
            resp = await client.post(path, json=json_data)
        elif method == "PUT":
            resp = await client.put(path, json=json_data)
        elif method == "DELETE":
            resp = await client.delete(path)
        else:
            raise ValueError(f"Unknown method {method}")

        assert resp.status_code == 401, f"{method} {path} 未返回 401，得到 {resp.status_code}"
        err = resp.json().get("error", {})
        assert err.get("code") == "UNAUTHENTICATED"


# =============================================================================
# 2. 认证用户全量 REST 端点调用（Happy Path 200 / 201 / 204）
# =============================================================================


async def test_universes_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_screener_service: AsyncMock,
) -> None:
    _setup_auth(app, auth_user, mock_screener_service)

    resp = await client.get("/api/v1/universes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "sp500"
    mock_screener_service.list_universes.assert_called_once()


async def test_screener_runs_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_screener_service: AsyncMock,
) -> None:
    _setup_auth(app, auth_user, mock_screener_service)
    run_id = mock_screener_service.run_screener.return_value.id

    # 1. POST /api/v1/screener/runs -> 201
    resp_create = await client.post(
        "/api/v1/screener/runs",
        json={"universe": "sp500", "strategy_id": "momentum", "params": {"period": 20}},
    )
    assert resp_create.status_code == 201
    assert resp_create.json()["id"] == str(run_id)

    # 2. GET /api/v1/screener/runs/{id} -> 200
    resp_get = await client.get(f"/api/v1/screener/runs/{run_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == str(run_id)

    # 3. GET /api/v1/screener/runs -> 200
    resp_list = await client.get("/api/v1/screener/runs?limit=10&offset=0")
    assert resp_list.status_code == 200
    assert len(resp_list.json()) == 1

    # 4. POST /api/v1/screener/export -> 200
    resp_export = await client.post(
        "/api/v1/screener/export",
        json={"symbols": ["AAPL", "MSFT"], "target_action": "compare"},
    )
    assert resp_export.status_code == 200
    assert resp_export.json()["action"] == "compare"


async def test_themes_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_screener_service: AsyncMock,
) -> None:
    _setup_auth(app, auth_user, mock_screener_service)

    # 1. GET /api/v1/themes -> 200
    resp_list = await client.get("/api/v1/themes")
    assert resp_list.status_code == 200
    assert len(resp_list.json()) == 1
    assert resp_list.json()[0]["id"] == "ai_chips"

    # 2. GET /api/v1/themes/{id} -> 200
    resp_get = await client.get("/api/v1/themes/ai_chips")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == "ai_chips"

    # 3. POST /api/v1/themes/{id}/cards -> 200
    resp_cards = await client.post("/api/v1/themes/ai_chips/cards")
    assert resp_cards.status_code == 200
    assert resp_cards.json()["theme_id"] == "ai_chips"
    assert len(resp_cards.json()["cards"]) == 1


async def test_watchlists_authenticated(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_screener_service: AsyncMock,
) -> None:
    _setup_auth(app, auth_user, mock_screener_service)
    wl_id = mock_screener_service.get_watchlist.return_value.id
    item_id = mock_screener_service.get_watchlist.return_value.items[0].id

    # 1. GET /api/v1/watchlists -> 200
    resp_list = await client.get("/api/v1/watchlists")
    assert resp_list.status_code == 200
    assert len(resp_list.json()) == 1

    # 2. POST /api/v1/watchlists -> 201
    resp_create = await client.post(
        "/api/v1/watchlists",
        json={"name": "科技龙头", "description": "跟踪龙头", "is_default": False},
    )
    assert resp_create.status_code == 201
    assert resp_create.json()["name"] == "科技龙头"

    # 3. GET /api/v1/watchlists/{id} -> 200
    resp_get = await client.get(f"/api/v1/watchlists/{wl_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == str(wl_id)

    # 4. PUT /api/v1/watchlists/{id} -> 200
    resp_update = await client.put(
        f"/api/v1/watchlists/{wl_id}",
        json={"name": "新名称"},
    )
    assert resp_update.status_code == 200

    # 5. POST /api/v1/watchlists/{id}/items -> 201
    resp_item_add = await client.post(
        f"/api/v1/watchlists/{wl_id}/items",
        json={"symbol": "AAPL", "target_price": "195.50", "notes": "突破买入"},
    )
    assert resp_item_add.status_code == 201

    # 6. PUT /api/v1/watchlists/{id}/items/{item_id} -> 200
    resp_item_up = await client.put(
        f"/api/v1/watchlists/{wl_id}/items/{item_id}",
        json={"notes": "更新备注"},
    )
    assert resp_item_up.status_code == 200

    # 7. POST /api/v1/watchlists/{id}/export -> 200
    resp_export = await client.post(f"/api/v1/watchlists/{wl_id}/export?target_action=compare")
    assert resp_export.status_code == 200
    assert resp_export.json()["action"] == "compare"

    # 8. DELETE /api/v1/watchlists/{id}/items/{item_id} -> 204
    resp_item_del = await client.delete(f"/api/v1/watchlists/{wl_id}/items/{item_id}")
    assert resp_item_del.status_code == 204

    # 9. DELETE /api/v1/watchlists/{id} -> 204
    resp_del = await client.delete(f"/api/v1/watchlists/{wl_id}")
    assert resp_del.status_code == 204


# =============================================================================
# 3. 错误状态码与异常映射验证
# =============================================================================


async def test_error_status_mapping(
    app: FastAPI,
    client: httpx.AsyncClient,
    auth_user: AuthenticatedUser,
    mock_screener_service: AsyncMock,
) -> None:
    _setup_auth(app, auth_user, mock_screener_service)
    random_id = uuid.uuid4()

    # Case 1: UniverseNotFoundError -> 404 NOT_FOUND
    mock_screener_service.run_screener.side_effect = UniverseNotFoundError("池不存在")
    resp_u = await client.post(
        "/api/v1/screener/runs",
        json={"universe": "invalid_u", "strategy_id": "momentum"},
    )
    assert resp_u.status_code == 404
    assert resp_u.json()["error"]["code"] == "NOT_FOUND"

    # Case 2: ThemeNotFoundError -> 404 NOT_FOUND
    mock_screener_service.get_theme.side_effect = ThemeNotFoundError("主题不存在")
    resp_t = await client.get("/api/v1/themes/non_exist")
    assert resp_t.status_code == 404
    assert resp_t.json()["error"]["code"] == "NOT_FOUND"

    # Case 3: ScreenerRunNotFoundError -> 404 NOT_FOUND
    mock_screener_service.get_screener_run.side_effect = ScreenerRunNotFoundError("任务不存在")
    resp_r = await client.get(f"/api/v1/screener/runs/{random_id}")
    assert resp_r.status_code == 404
    assert resp_r.json()["error"]["code"] == "NOT_FOUND"

    # Case 4: WatchlistNotFoundError -> 404 NOT_FOUND
    mock_screener_service.get_watchlist.side_effect = WatchlistNotFoundError("清单不存在")
    resp_w = await client.get(f"/api/v1/watchlists/{random_id}")
    assert resp_w.status_code == 404
    assert resp_w.json()["error"]["code"] == "NOT_FOUND"

    # Case 5: WatchlistItemNotFoundError -> 404 NOT_FOUND
    mock_screener_service.update_watchlist_item.side_effect = WatchlistItemNotFoundError(
        "标的不存在"
    )
    resp_wi = await client.put(
        f"/api/v1/watchlists/{random_id}/items/{random_id}",
        json={"notes": "更新"},
    )
    assert resp_wi.status_code == 404
    assert resp_wi.json()["error"]["code"] == "NOT_FOUND"

    # Case 6: StrategyNotFoundError -> 404 NOT_FOUND
    mock_screener_service.run_screener.side_effect = StrategyNotFoundError("策略不存在")
    resp_st = await client.post(
        "/api/v1/screener/runs",
        json={"universe": "sp500", "strategy_id": "non_exist"},
    )
    assert resp_st.status_code == 404
    assert resp_st.json()["error"]["code"] == "NOT_FOUND"

    # Case 7: DuplicateWatchlistItemError -> 409 STATE_CONFLICT
    mock_screener_service.add_watchlist_item.side_effect = DuplicateWatchlistItemError("标的已存在")
    resp_dup = await client.post(
        f"/api/v1/watchlists/{random_id}/items",
        json={"symbol": "AAPL"},
    )
    assert resp_dup.status_code == 409
    assert resp_dup.json()["error"]["code"] == "STATE_CONFLICT"

    # Case 8: ScreenerExecutionError -> 500 INTERNAL_ERROR
    mock_screener_service.run_screener.side_effect = ScreenerExecutionError("执行引擎崩溃")
    resp_err = await client.post(
        "/api/v1/screener/runs",
        json={"universe": "sp500", "strategy_id": "momentum"},
    )
    assert resp_err.status_code == 500
    assert resp_err.json()["error"]["code"] == "INTERNAL_ERROR"

    # Case 9: Empty Watchlist export -> 400 VALIDATION_ERROR
    empty_wl = WatchlistRead(
        id=random_id,
        user_id=auth_user.id,
        name="空清单",
        description="",
        is_default=False,
        items=[],
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    mock_screener_service.get_watchlist.side_effect = None
    mock_screener_service.get_watchlist.return_value = empty_wl
    resp_empty_exp = await client.post(f"/api/v1/watchlists/{random_id}/export")
    assert resp_empty_exp.status_code == 400
    assert resp_empty_exp.json()["error"]["code"] == "VALIDATION_ERROR"

    # Case 10: Invalid UUID parameter -> 400 VALIDATION_ERROR
    resp_uuid = await client.get("/api/v1/screener/runs/not-a-valid-uuid")
    assert resp_uuid.status_code == 400
    assert resp_uuid.json()["error"]["code"] == "VALIDATION_ERROR"
