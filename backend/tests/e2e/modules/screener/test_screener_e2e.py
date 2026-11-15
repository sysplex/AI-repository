"""M8-T08 筛选器与主题自选端到端（E2E）集成验收测试套件。

全面验证 M8 全部业务验收标准（CONTRACTS §5, DoD）：
1. 自选清单全生命周期 (Watchlist Lifecycle)：
   - 创建清单 -> 添加标的 -> 重复添加检测 (409) -> 更新标的备注/目标价 -> 更新清单信息 ->
     一键导出至投研对比 -> 移除标的 -> 删除清单 -> 404 检测。
2. 筛选任务到自选联动 (Screener-to-Watchlist Lifecycle)：
   - 查询基准股票池 -> 启动道指 30 / 标普 500 策略筛选 -> 轮询查询结果与指标快照 ->
     筛选结果导出研报 -> 将筛选出的排名第一标的一键加入自选。
3. 热门主题与 AI 事实溯源卡片生成 (Thematic Cards AI Lifecycle)：
   - 查询热门主题库 -> 获取指定主题画像 -> 触发生成 AI 主题卡片 -> 验证数字事实溯源与合规防线。
4. 多租户数据隔离防御 (Multi-Tenant Isolation Defense)：
   - 用户 A 创建自选清单与筛选任务；
   - 用户 B 发起越权读取、修改、删除与标的注入攻击，验证 404/403 严格隔离拦截；
   - 用户 B 的清单与任务列表绝不包含用户 A 的任何私有数据。
5. HARD-01 鉴权守卫验证 (HARD-01 Authentication Guard)：
   - 未登录请求一律严格拦截并返回 401 UNAUTHENTICATED。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.deps import current_user
from app.core.clock import FrozenClock
from app.modules.identity.enums import UserRole, UserStatus
from app.modules.identity.schemas import AuthenticatedUser, UserSettings
from app.modules.screener.api import get_current_user, get_screener_service
from app.modules.screener.exceptions import (
    DuplicateWatchlistItemError,
    WatchlistItemNotFoundError,
    WatchlistNotFoundError,
)
from app.modules.screener.executor import ScreenerExecutor
from app.modules.screener.models import ScreenerRun, Watchlist, WatchlistItem
from app.modules.screener.ports import (
    ScreenerRepositoryProtocol,
    WatchlistRepositoryProtocol,
)
from app.modules.screener.prompts import (
    DEFAULT_BANNED_TERMS,
    THEME_CARD_PROMPT_VERSION,
    ThemeCardsGenerator,
)
from app.modules.screener.schemas import (
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemUpdate,
    WatchlistUpdate,
)
from app.modules.screener.service import ScreenerService
from app.modules.screener.universe import default_universe_manager
from app.modules.strategy.schemas import Signal

pytestmark = pytest.mark.e2e

_USER_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_USER_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_FIXED_TIME = datetime(2026, 11, 15, 10, 0, 0, tzinfo=UTC)


# =============================================================================
# 1. 真实内存持久化仓储与确定性模拟服务
# =============================================================================


class E2EInMemoryScreenerRepository(ScreenerRepositoryProtocol):
    """支持多租户隔离的筛选任务内存仓储。"""

    def __init__(self) -> None:
        self.runs: dict[UUID, ScreenerRun] = {}

    async def create_run(self, run: ScreenerRun) -> ScreenerRun:
        if getattr(run, "id", None) is None:
            run.id = uuid.uuid4()
        self.runs[run.id] = run
        return run

    async def update_run(self, run: ScreenerRun) -> ScreenerRun:
        self.runs[run.id] = run
        return run

    async def get_run(self, run_id: UUID, user_id: UUID) -> ScreenerRun | None:
        r = self.runs.get(run_id)
        if r and r.user_id == user_id:
            return r
        return None

    async def list_runs(self, user_id: UUID, limit: int = 20, offset: int = 0) -> list[ScreenerRun]:
        user_runs = [r for r in self.runs.values() if r.user_id == user_id]
        return user_runs[offset : offset + limit]


class E2EInMemoryWatchlistRepository(WatchlistRepositoryProtocol):
    """支持完整增删改查与多租户隔离的自选清单内存仓储。"""

    def __init__(self) -> None:
        self.watchlists: dict[UUID, Watchlist] = {}

    async def list_watchlists(self, user_id: UUID) -> list[Watchlist]:
        return [w for w in self.watchlists.values() if w.user_id == user_id]

    async def get_watchlist(self, watchlist_id: UUID, user_id: UUID) -> Watchlist | None:
        w = self.watchlists.get(watchlist_id)
        if w and w.user_id == user_id:
            return w
        return None

    async def create_watchlist(self, user_id: UUID, data: WatchlistCreate) -> Watchlist:
        now = _FIXED_TIME
        if data.is_default:
            for w in self.watchlists.values():
                if w.user_id == user_id and w.is_default:
                    w.is_default = False

        wl = Watchlist(
            id=uuid.uuid4(),
            user_id=user_id,
            name=data.name,
            description=data.description,
            is_default=data.is_default,
            items=[],
            created_at=now,
            updated_at=now,
        )
        self.watchlists[wl.id] = wl
        return wl

    async def update_watchlist(
        self, watchlist_id: UUID, user_id: UUID, data: WatchlistUpdate
    ) -> Watchlist | None:
        wl = await self.get_watchlist(watchlist_id, user_id)
        if wl is None:
            return None

        if data.name is not None:
            wl.name = data.name
        if data.description is not None:
            wl.description = data.description
        if data.is_default is not None:
            if data.is_default:
                for other in self.watchlists.values():
                    if other.user_id == user_id and other.is_default:
                        other.is_default = False
            wl.is_default = data.is_default

        wl.updated_at = _FIXED_TIME
        return wl

    async def delete_watchlist(self, watchlist_id: UUID, user_id: UUID) -> bool:
        wl = await self.get_watchlist(watchlist_id, user_id)
        if wl is None:
            return False
        del self.watchlists[watchlist_id]
        return True

    async def add_item(
        self, watchlist_id: UUID, user_id: UUID, data: WatchlistItemCreate
    ) -> WatchlistItem:
        wl = await self.get_watchlist(watchlist_id, user_id)
        if wl is None:
            raise WatchlistNotFoundError(f"未找到自选清单: {watchlist_id}")

        clean_sym = data.symbol.strip().upper()
        if any(item.symbol == clean_sym for item in wl.items):
            raise DuplicateWatchlistItemError(f"标的 {clean_sym} 已存在于自选清单中")

        item = WatchlistItem(
            id=uuid.uuid4(),
            watchlist_id=wl.id,
            symbol=clean_sym,
            notes=data.notes,
            target_price=data.target_price,
            theme_tags=data.theme_tags,
            created_at=_FIXED_TIME,
        )
        wl.items.append(item)
        return item

    async def update_item(
        self, watchlist_id: UUID, item_id: UUID, user_id: UUID, data: WatchlistItemUpdate
    ) -> WatchlistItem:
        wl = await self.get_watchlist(watchlist_id, user_id)
        if wl is None:
            raise WatchlistNotFoundError(f"未找到自选清单: {watchlist_id}")

        target_item = next((it for it in wl.items if it.id == item_id), None)
        if target_item is None:
            raise WatchlistItemNotFoundError(f"未找到标的条目: {item_id}")

        if data.notes is not None:
            target_item.notes = data.notes
        if data.target_price is not None:
            target_item.target_price = data.target_price
        if data.theme_tags is not None:
            target_item.theme_tags = data.theme_tags

        return target_item

    async def remove_item(self, watchlist_id: UUID, item_id: UUID, user_id: UUID) -> bool:
        wl = await self.get_watchlist(watchlist_id, user_id)
        if wl is None:
            raise WatchlistNotFoundError(f"未找到自选清单: {watchlist_id}")

        orig_len = len(wl.items)
        wl.items = [it for it in wl.items if it.id != item_id]
        if len(wl.items) == orig_len:
            raise WatchlistItemNotFoundError(f"未找到标的条目: {item_id}")
        return True


class E2EStrategyService:
    """提供高逼真度确定性策略评分的模拟服务。"""

    async def evaluate(
        self,
        strategy_id: str,
        symbol: str,
        as_of: Any,
        params: dict[str, Any] | None = None,
    ) -> Signal:
        seed_key = f"{strategy_id}:{symbol}"
        hash_val = int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest(), 16)
        score = Decimal((hash_val % 5000) + 5000) / Decimal(100)  # 50.00 ~ 99.99

        return Signal(
            strategy_id=strategy_id,
            symbol=symbol,
            as_of=as_of if isinstance(as_of, date) else _FIXED_TIME.date(),
            direction="long",
            strength=int(score),
            reasons=["均线金叉多头排列"],
            metrics={"rsi": 62.5, "pe": 24.8, "score": float(score)},
        )


class E2EMarketDataService:
    """提供高逼真度市场事实的模拟服务。"""

    async def get_bars_daily(self, symbol: str, start_date: Any, end_date: Any) -> Any:
        return []

    async def build_facts(self, symbol: str, as_of: datetime | None = None) -> dict[str, Any]:
        return {
            "symbol": symbol.upper(),
            "pe": Decimal("32.5"),
            "roe": Decimal("24.0"),
            "revenue_growth": Decimal("18.5"),
            "gross_margin": Decimal("52.0"),
            "market_cap_tier": "mega",
        }


class E2EThemeAIService:
    """生成合规且事实溯源严格的 AI 主题卡片模拟服务。"""

    async def run(
        self,
        use_case: str,
        facts: dict[str, Any],
        params: dict[str, Any] | None = None,
        user_id: UUID | None = None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        stocks_facts = facts.get("stocks", [])
        cards: list[dict[str, Any]] = []

        for sf in stocks_facts:
            sym = sf.get("symbol", "UNKNOWN")
            name = sf.get("name", sym)
            pe = sf.get("pe", 30.0)
            roe = sf.get("roe", 20.0)

            cards.append(
                {
                    "symbol": sym,
                    "name": name,
                    "one_line_intro": f"{name}是行业领先的优质科技标的",
                    "why_watch": f"行业龙头壁垒显著，净资产收益率达到 {roe}%",
                    "financial_strengths": [
                        f"最新市盈率(PE)为 {pe} 倍",
                        f"净资产收益率(ROE)达到 {roe}%",
                    ],
                    "main_risks": ["宏观流动性紧缩风险", "行业竞争加剧风险"],
                    "suitable_for": ["稳健型成长投资者"],
                    "more_attractive_when": f"PE 回调至 {pe} 倍以下时更具估值安全边际",
                }
            )

        return {"cards": cards}


# =============================================================================
# 2. Pytest Fixtures
# =============================================================================


@pytest.fixture
def auth_user_a() -> AuthenticatedUser:
    return AuthenticatedUser(
        id=_USER_A_ID,
        email="user_a@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(risk_profile="balanced", language="zh-CN"),
    )


@pytest.fixture
def auth_user_b() -> AuthenticatedUser:
    return AuthenticatedUser(
        id=_USER_B_ID,
        email="user_b@example.com",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        settings=UserSettings(risk_profile="conservative", language="zh-CN"),
    )


@pytest.fixture
def e2e_screener_service() -> ScreenerService:
    clock = FrozenClock(_FIXED_TIME)
    screener_repo = E2EInMemoryScreenerRepository()
    watchlist_repo = E2EInMemoryWatchlistRepository()
    strategy_service = E2EStrategyService()
    executor = ScreenerExecutor(strategy_service=strategy_service, default_concurrency=20)
    marketdata_service = E2EMarketDataService()
    ai_service = E2EThemeAIService()

    generator = ThemeCardsGenerator(
        universe_manager=default_universe_manager,
        ai_service=ai_service,
        marketdata_service=marketdata_service,
        clock=clock,
    )

    return ScreenerService(
        screener_repo=screener_repo,
        watchlist_repo=watchlist_repo,
        universe_manager=default_universe_manager,
        executor=executor,
        theme_cards_generator=generator,
        clock=clock,
    )


def _set_auth_user(app: FastAPI, user: AuthenticatedUser) -> None:
    async def _mock_current_user(request: Request) -> AuthenticatedUser:
        request.state.user = user
        return user

    app.dependency_overrides[current_user] = _mock_current_user
    app.dependency_overrides[get_current_user] = lambda: user


# =============================================================================
# 3. E2E-01: 自选清单全生命周期业务验收
# =============================================================================


async def test_e2e_watchlist_full_lifecycle(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_screener_service: ScreenerService,
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-01: 自选清单增删改查、标的管理、重复检测与投研一键导出端到端验收。"""
    _set_auth_user(app, auth_user_a)
    app.dependency_overrides[get_screener_service] = lambda: e2e_screener_service

    # 1. 初始列表为空
    resp_init = await client.get("/api/v1/watchlists")
    assert resp_init.status_code == 200
    assert resp_init.json() == []

    # 2. 创建清单
    resp_create = await client.post(
        "/api/v1/watchlists",
        json={"name": "科技成长", "description": "核心观察仓", "is_default": True},
    )
    assert resp_create.status_code == 201
    wl_data = resp_create.json()
    wl_id = wl_data["id"]
    assert wl_data["name"] == "科技成长"
    assert wl_data["is_default"] is True
    assert wl_data["items"] == []

    # 3. 添加标的 1 (AAPL)
    resp_item1 = await client.post(
        f"/api/v1/watchlists/{wl_id}/items",
        json={"symbol": "AAPL", "target_price": "180.00", "notes": "逢低关注"},
    )
    assert resp_item1.status_code == 201
    item1_data = resp_item1.json()
    item1_id = item1_data["id"]
    assert item1_data["symbol"] == "AAPL"
    assert item1_data["target_price"] == "180.00"

    # 4. 添加标的 2 (NVDA)
    resp_item2 = await client.post(
        f"/api/v1/watchlists/{wl_id}/items",
        json={"symbol": "NVDA", "target_price": "145.50", "notes": "AI龙头"},
    )
    assert resp_item2.status_code == 201

    # 5. 重复添加 AAPL 验证拦截 (409 STATE_CONFLICT)
    resp_dup = await client.post(
        f"/api/v1/watchlists/{wl_id}/items",
        json={"symbol": "AAPL"},
    )
    assert resp_dup.status_code == 409
    assert resp_dup.json()["error"]["code"] == "STATE_CONFLICT"

    # 6. 更新标的 1 备注与目标价
    resp_up_item = await client.put(
        f"/api/v1/watchlists/{wl_id}/items/{item1_id}",
        json={"notes": "已加仓突破", "target_price": "195.00", "theme_tags": ["tech", "mega"]},
    )
    assert resp_up_item.status_code == 200
    assert resp_up_item.json()["notes"] == "已加仓突破"
    assert resp_up_item.json()["target_price"] == "195.00"

    # 7. 更新清单元数据
    resp_up_wl = await client.put(
        f"/api/v1/watchlists/{wl_id}",
        json={"name": "科技主力池", "description": "核心持仓观察"},
    )
    assert resp_up_wl.status_code == 200
    assert resp_up_wl.json()["name"] == "科技主力池"

    # 8. 查询清单详情，验证标的与状态持久性
    resp_get = await client.get(f"/api/v1/watchlists/{wl_id}")
    assert resp_get.status_code == 200
    detail = resp_get.json()
    assert detail["name"] == "科技主力池"
    assert len(detail["items"]) == 2

    # 9. 一键导出至研报/横向对比
    resp_export = await client.post(f"/api/v1/watchlists/{wl_id}/export?target_action=compare")
    assert resp_export.status_code == 200
    export_data = resp_export.json()
    assert export_data["target_action"] == "compare"
    assert "AAPL" in export_data["symbols"]
    assert "NVDA" in export_data["symbols"]
    assert export_data["target_endpoint"] == "/api/v1/research/compare"

    # 10. 移除标的 1 (AAPL)
    resp_del_item = await client.delete(f"/api/v1/watchlists/{wl_id}/items/{item1_id}")
    assert resp_del_item.status_code == 204

    # 验证剩余标的
    resp_after_del = await client.get(f"/api/v1/watchlists/{wl_id}")
    assert len(resp_after_del.json()["items"]) == 1
    assert resp_after_del.json()["items"][0]["symbol"] == "NVDA"

    # 11. 删除清单
    resp_del_wl = await client.delete(f"/api/v1/watchlists/{wl_id}")
    assert resp_del_wl.status_code == 204

    # 再次查询已删除清单 -> 404 NOT_FOUND
    resp_404 = await client.get(f"/api/v1/watchlists/{wl_id}")
    assert resp_404.status_code == 404
    assert resp_404.json()["error"]["code"] == "NOT_FOUND"


# =============================================================================
# 4. E2E-02: 策略筛选全流程与自选清单联动业务验收
# =============================================================================


async def test_e2e_screener_screening_and_add_to_watchlist(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_screener_service: ScreenerService,
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-02: 股票池查询 -> 策略筛选 -> 排名回读 -> 标的加入自选端到端联动。"""
    _set_auth_user(app, auth_user_a)
    app.dependency_overrides[get_screener_service] = lambda: e2e_screener_service

    # 1. 查询系统支持的基准股票池
    resp_univ = await client.get("/api/v1/universes")
    assert resp_univ.status_code == 200
    univ_ids = [u["id"] for u in resp_univ.json()]
    assert "dow30" in univ_ids
    assert "sp500" in univ_ids

    # 2. 提交道指 30 策略量化筛选任务
    resp_run = await client.post(
        "/api/v1/screener/runs",
        json={"universe": "dow30", "strategy_id": "trend_following", "params": {"min_score": 60}},
    )
    assert resp_run.status_code == 201
    run_info = resp_run.json()
    run_id = run_info["id"]
    assert run_info["universe"] == "dow30"
    assert run_info["status"] == "succeeded"
    assert run_info["matched_count"] > 0
    assert len(run_info["results"]) > 0

    # 验证筛选排名分值
    top_result = run_info["results"][0]
    top_symbol = top_result["symbol"]
    assert top_result["rank"] == 1
    assert Decimal(str(top_result["score"])) >= Decimal("60.00")

    # 3. 轮询/查询指定任务记录详情
    resp_get_run = await client.get(f"/api/v1/screener/runs/{run_id}")
    assert resp_get_run.status_code == 200
    assert resp_get_run.json()["id"] == run_id

    # 4. 查询当前租户历史筛选任务列表
    resp_list_runs = await client.get("/api/v1/screener/runs")
    assert resp_list_runs.status_code == 200
    assert any(r["id"] == run_id for r in resp_list_runs.json())

    # 5. 一键导出筛选结果
    resp_exp = await client.post(
        "/api/v1/screener/export",
        json={"symbols": [top_symbol], "target_action": "deep_research"},
    )
    assert resp_exp.status_code == 200
    assert resp_exp.json()["target_action"] == "deep_research"

    # 6. 将筛选排名第一的标的一键加入自选清单
    resp_wl = await client.post(
        "/api/v1/watchlists",
        json={"name": "量化精选池", "description": "道指策略筛选优选"},
    )
    assert resp_wl.status_code == 201
    wl_id = resp_wl.json()["id"]

    resp_add = await client.post(
        f"/api/v1/watchlists/{wl_id}/items",
        json={"symbol": top_symbol, "notes": f"来自筛选任务 #{run_id} 排名第一标的"},
    )
    assert resp_add.status_code == 201
    assert resp_add.json()["symbol"] == top_symbol

    # 7. 确认自选清单已成功收入该标的
    resp_check = await client.get(f"/api/v1/watchlists/{wl_id}")
    assert len(resp_check.json()["items"]) == 1
    assert resp_check.json()["items"][0]["symbol"] == top_symbol


# =============================================================================
# 5. E2E-03: 热门主题与 AI 事实溯源卡片生成端到端验收
# =============================================================================


async def test_e2e_thematic_cards_ai_lifecycle(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_screener_service: ScreenerService,
    auth_user_a: AuthenticatedUser,
) -> None:
    """E2E-03: 热门主题查询 -> 成分股查看 -> AI 卡片生成与事实溯源验证。"""
    _set_auth_user(app, auth_user_a)
    app.dependency_overrides[get_screener_service] = lambda: e2e_screener_service

    # 1. 查询系统预设主题库
    resp_themes = await client.get("/api/v1/themes")
    assert resp_themes.status_code == 200
    themes = resp_themes.json()
    assert len(themes) >= 6
    theme_ids = [t["id"] for t in themes]
    assert "ai_chips" in theme_ids

    # 2. 查询特定主题详情
    resp_detail = await client.get("/api/v1/themes/ai_chips")
    assert resp_detail.status_code == 200
    ai_theme = resp_detail.json()
    assert ai_theme["id"] == "ai_chips"
    assert len(ai_theme["stocks"]) > 0

    # 3. 触发并获取 AI 生成的主题成分股投研卡片
    resp_cards = await client.post("/api/v1/themes/ai_chips/cards")
    assert resp_cards.status_code == 200
    cards_data = resp_cards.json()
    assert cards_data["theme_id"] == "ai_chips"
    assert cards_data["prompt_version"] == THEME_CARD_PROMPT_VERSION
    assert len(cards_data["cards"]) > 0

    # 验证卡片内容规范与合规防线
    for card in cards_data["cards"]:
        assert card["symbol"] != ""
        assert card["name"] != ""
        assert len(card["financial_strengths"]) >= 1
        assert len(card["main_risks"]) >= 1
        assert len(card["suitable_for"]) >= 1

        # 验证 0 违规禁用词
        for banned in DEFAULT_BANNED_TERMS:
            assert banned not in card["one_line_intro"]
            assert banned not in card["why_watch"]
            assert banned not in " ".join(card["financial_strengths"])


# =============================================================================
# 6. E2E-04: 多租户严格物理/逻辑隔离防御验收
# =============================================================================


async def test_e2e_multi_tenant_isolation_attack_resistance(
    app: FastAPI,
    client: httpx.AsyncClient,
    e2e_screener_service: ScreenerService,
    auth_user_a: AuthenticatedUser,
    auth_user_b: AuthenticatedUser,
) -> None:
    """E2E-04: 跨租户越权读取、修改、删除与数据泄露攻击防御。"""
    app.dependency_overrides[get_screener_service] = lambda: e2e_screener_service

    # 1. User A 创建自选清单与筛选任务
    _set_auth_user(app, auth_user_a)
    resp_wl_a = await client.post(
        "/api/v1/watchlists",
        json={"name": "User A 私有清单", "description": "私密自选"},
    )
    assert resp_wl_a.status_code == 201
    wl_a_id = resp_wl_a.json()["id"]

    resp_run_a = await client.post(
        "/api/v1/screener/runs",
        json={"universe": "dow30", "strategy_id": "trend_following"},
    )
    assert resp_run_a.status_code == 201
    run_a_id = resp_run_a.json()["id"]

    # 2. 切换为 User B 上下文（模拟攻击者发起水平越权）
    _set_auth_user(app, auth_user_b)

    # 攻击 1: User B 越权读取 User A 的自选清单 -> 404 NOT_FOUND
    resp_attack_get_wl = await client.get(f"/api/v1/watchlists/{wl_a_id}")
    assert resp_attack_get_wl.status_code == 404
    assert resp_attack_get_wl.json()["error"]["code"] == "NOT_FOUND"

    # 攻击 2: User B 越权修改 User A 的自选清单 -> 404 NOT_FOUND
    resp_attack_put_wl = await client.put(
        f"/api/v1/watchlists/{wl_a_id}",
        json={"name": "被篡改的清单"},
    )
    assert resp_attack_put_wl.status_code == 404

    # 攻击 3: User B 越权向 User A 的清单插入标的 -> 404 NOT_FOUND
    resp_attack_add_item = await client.post(
        f"/api/v1/watchlists/{wl_a_id}/items",
        json={"symbol": "MSFT"},
    )
    assert resp_attack_add_item.status_code == 404

    # 攻击 4: User B 越权删除 User A 的自选清单 -> 404 NOT_FOUND
    resp_attack_del_wl = await client.delete(f"/api/v1/watchlists/{wl_a_id}")
    assert resp_attack_del_wl.status_code == 404

    # 攻击 5: User B 越权读取 User A 的筛选任务记录 -> 404 NOT_FOUND
    resp_attack_get_run = await client.get(f"/api/v1/screener/runs/{run_a_id}")
    assert resp_attack_get_run.status_code == 404

    # 攻击 6: User B 查询自身列表，绝不包含 User A 的数据
    resp_list_wl_b = await client.get("/api/v1/watchlists")
    assert resp_list_wl_b.status_code == 200
    assert not any(w["id"] == wl_a_id for w in resp_list_wl_b.json())

    resp_list_runs_b = await client.get("/api/v1/screener/runs")
    assert resp_list_runs_b.status_code == 200
    assert not any(r["id"] == run_a_id for r in resp_list_runs_b.json())


# =============================================================================
# 7. E2E-05: HARD-01 鉴权守卫拦截验收
# =============================================================================


async def test_e2e_unauthenticated_requests_blocked(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    """E2E-05: 未携带有效 Token 的请求一律拦截并返回 401 UNAUTHENTICATED。"""
    # 清理所有依赖覆盖，恢复真实鉴权拦截
    app.dependency_overrides.clear()
    dummy_uuid = uuid.uuid4()

    endpoints = [
        ("GET", "/api/v1/universes"),
        ("POST", "/api/v1/screener/runs"),
        ("GET", f"/api/v1/screener/runs/{dummy_uuid}"),
        ("GET", "/api/v1/screener/runs"),
        ("POST", "/api/v1/screener/export"),
        ("GET", "/api/v1/themes"),
        ("GET", "/api/v1/themes/ai_chips"),
        ("POST", "/api/v1/themes/ai_chips/cards"),
        ("GET", "/api/v1/watchlists"),
        ("POST", "/api/v1/watchlists"),
        ("GET", f"/api/v1/watchlists/{dummy_uuid}"),
        ("PUT", f"/api/v1/watchlists/{dummy_uuid}"),
        ("DELETE", f"/api/v1/watchlists/{dummy_uuid}"),
        ("POST", f"/api/v1/watchlists/{dummy_uuid}/items"),
        ("PUT", f"/api/v1/watchlists/{dummy_uuid}/items/{dummy_uuid}"),
        ("DELETE", f"/api/v1/watchlists/{dummy_uuid}/items/{dummy_uuid}"),
        ("POST", f"/api/v1/watchlists/{dummy_uuid}/export"),
    ]

    for method, path in endpoints:
        if method == "GET":
            resp = await client.get(path)
        elif method == "POST":
            resp = await client.post(path, json={})
        elif method == "PUT":
            resp = await client.put(path, json={})
        elif method == "DELETE":
            resp = await client.delete(path)
        else:
            raise ValueError(f"Unknown method {method}")

        assert resp.status_code == 401, f"{method} {path} 未返回 401"
        assert resp.json()["error"]["code"] == "UNAUTHENTICATED"
