"""M8 筛选器与主题自选端口协议抽象，`CONTRACTS.md §3`。

定义 screener 模块依赖倒置契约：
- ``UniverseManagerProtocol``：股票池与主题股票库管理协议
- ``ScreenerExecutorProtocol``：多标的并发策略筛选执行器协议
- ``ScreenerRepositoryProtocol``：筛选任务持久化仓储协议
- ``WatchlistRepositoryProtocol``：自选列表持久化仓储协议
- ``ScreenerServiceProtocol``：统一门面服务协议
- 外部依赖协议：``StrategyServiceProtocol``, ``MarketDataServiceProtocol``, ``AIServiceProtocol``
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from app.modules.screener.models import ScreenerRun, Watchlist, WatchlistItem
from app.modules.screener.schemas import (
    ScreenerResultItem,
    ScreenerRunCreate,
    ScreenerRunRead,
    ThemeCardsResponse,
    ThemeInfo,
    UniverseInfo,
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemUpdate,
    WatchlistUpdate,
)

__all__ = [
    "AIServiceProtocol",
    "MarketDataServiceProtocol",
    "ScreenerExecutorProtocol",
    "ScreenerRepositoryProtocol",
    "ScreenerServiceProtocol",
    "StrategyServiceProtocol",
    "UniverseManagerProtocol",
    "WatchlistRepositoryProtocol",
]


# ---------------------------------------------------------
# 外部依赖契约（Layer 2 / 3 依赖倒置）
# ---------------------------------------------------------
@runtime_checkable
class AIServiceProtocol(Protocol):
    """AI 核心门面协议。"""

    async def run(
        self,
        use_case: str,
        facts: dict[str, Any],
        params: dict[str, Any] | None = None,
        user_id: UUID | None = None,
        as_of: datetime | None = None,
    ) -> Any: ...


@runtime_checkable
class StrategyServiceProtocol(Protocol):
    """策略分析服务协议。"""

    def list_strategies(self) -> list[Any]: ...

    async def run_strategy(
        self,
        strategy_id: str,
        symbol: str,
        params: dict[str, Any] | None = None,
        as_of: datetime | None = None,
    ) -> Any: ...


@runtime_checkable
class MarketDataServiceProtocol(Protocol):
    """市场数据源协议。"""

    async def get_bars_daily(
        self,
        symbol: str,
        start_date: Any,
        end_date: Any,
    ) -> Any: ...

    async def build_facts(
        self,
        symbol: str,
        as_of: datetime | None = None,
    ) -> dict[str, Any]: ...


# ---------------------------------------------------------
# Screener 内部领域协议
# ---------------------------------------------------------
@runtime_checkable
class UniverseManagerProtocol(Protocol):
    """股票池与主题股票库管理协议。"""

    def list_universes(self) -> list[UniverseInfo]: ...

    def get_universe_symbols(
        self, universe_id: str, custom_symbols: list[str] | None = None
    ) -> list[str]: ...

    def list_themes(self) -> list[ThemeInfo]: ...

    def get_theme(self, theme_id: str) -> ThemeInfo: ...


@runtime_checkable
class ScreenerExecutorProtocol(Protocol):
    """多标的并发策略筛选引擎协议（带隔离容错与确定性排序）。"""

    async def execute_screening(
        self,
        strategy_id: str,
        symbols: list[str],
        params: dict[str, Any],
        as_of: datetime | None = None,
    ) -> tuple[list[ScreenerResultItem], list[dict[str, Any]]]: ...


@runtime_checkable
class ScreenerRepositoryProtocol(Protocol):
    """筛选任务持久化仓储协议（用户多租户隔离）。"""

    async def create_run(self, run: ScreenerRun) -> ScreenerRun: ...

    async def update_run(self, run: ScreenerRun) -> ScreenerRun: ...

    async def get_run(self, run_id: UUID, user_id: UUID) -> ScreenerRun | None: ...

    async def list_runs(
        self, user_id: UUID, limit: int = 20, offset: int = 0
    ) -> list[ScreenerRun]: ...


@runtime_checkable
class WatchlistRepositoryProtocol(Protocol):
    """自选列表持久化仓储协议（用户多租户隔离）。"""

    async def list_watchlists(self, user_id: UUID) -> list[Watchlist]: ...

    async def get_watchlist(self, watchlist_id: UUID, user_id: UUID) -> Watchlist | None: ...

    async def create_watchlist(self, user_id: UUID, data: WatchlistCreate) -> Watchlist: ...

    async def update_watchlist(
        self, watchlist_id: UUID, user_id: UUID, data: WatchlistUpdate
    ) -> Watchlist | None: ...

    async def delete_watchlist(self, watchlist_id: UUID, user_id: UUID) -> bool: ...

    async def add_item(
        self, watchlist_id: UUID, user_id: UUID, data: WatchlistItemCreate
    ) -> WatchlistItem: ...

    async def update_item(
        self,
        watchlist_id: UUID,
        item_id: UUID,
        user_id: UUID,
        data: WatchlistItemUpdate,
    ) -> WatchlistItem | None: ...

    async def remove_item(self, watchlist_id: UUID, item_id: UUID, user_id: UUID) -> bool: ...


@runtime_checkable
class ScreenerServiceProtocol(Protocol):
    """统一筛选器服务对外门面协议。"""

    async def run_screener(self, user_id: UUID, request: ScreenerRunCreate) -> ScreenerRunRead: ...

    async def get_screener_run(self, run_id: UUID, user_id: UUID) -> ScreenerRunRead: ...

    def list_universes(self) -> list[UniverseInfo]: ...

    def list_themes(self) -> list[ThemeInfo]: ...

    def get_theme(self, theme_id: str) -> ThemeInfo: ...

    async def generate_theme_cards(self, theme_id: str, user_id: UUID) -> ThemeCardsResponse: ...
