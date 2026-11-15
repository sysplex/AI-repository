"""M8 筛选器统一门面服务实现，`CONTRACTS.md §3`。

实现 ``ScreenerServiceProtocol``，编排全市场策略筛选流程、股票池/主题解析与多租户自选清单管理。
"""

from __future__ import annotations

import uuid
from typing import Any, Literal, cast
from uuid import UUID

from app.core.clock import get_clock
from app.core.logging import get_logger
from app.modules.screener.exceptions import (
    ScreenerError,
    ScreenerExecutionError,
    ScreenerRunNotFoundError,
    UniverseNotFoundError,
    WatchlistItemNotFoundError,
    WatchlistNotFoundError,
)
from app.modules.screener.models import ScreenerResult, ScreenerRun, Watchlist, WatchlistItem
from app.modules.screener.ports import (
    ScreenerExecutorProtocol,
    ScreenerRepositoryProtocol,
    ScreenerServiceProtocol,
    UniverseManagerProtocol,
    WatchlistRepositoryProtocol,
)
from app.modules.screener.prompts import ThemeCardsGenerator
from app.modules.screener.schemas import (
    ExportToResearchRequest,
    ScreenerResultItem,
    ScreenerRunCreate,
    ScreenerRunRead,
    ThemeCardsResponse,
    ThemeInfo,
    UniverseInfo,
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemRead,
    WatchlistItemUpdate,
    WatchlistRead,
    WatchlistUpdate,
)
from app.modules.screener.universe import UniverseManager

__all__ = ["ScreenerService"]

logger = get_logger("screener.service")


class ScreenerService(ScreenerServiceProtocol):
    """筛选器与自选核心门面服务（满足 ScreenerServiceProtocol 协议）。"""

    def __init__(
        self,
        *,
        screener_repo: ScreenerRepositoryProtocol,
        watchlist_repo: WatchlistRepositoryProtocol,
        universe_manager: UniverseManagerProtocol | None = None,
        executor: ScreenerExecutorProtocol | None = None,
        theme_cards_generator: Any | None = None,
        clock: Any | None = None,
    ) -> None:
        self._screener_repo = screener_repo
        self._watchlist_repo = watchlist_repo
        self._universe_manager: UniverseManagerProtocol = (
            universe_manager if universe_manager is not None else UniverseManager()
        )
        self._executor = executor
        self._clock = clock if clock is not None else get_clock()
        self._theme_cards_generator = (
            theme_cards_generator
            if theme_cards_generator is not None
            else ThemeCardsGenerator(
                universe_manager=self._universe_manager,
                clock=self._clock,
            )
        )

    # ---------------------------------------------------------
    # 策略筛选任务执行与状态查询
    # ---------------------------------------------------------
    async def run_screener(self, user_id: UUID, request: ScreenerRunCreate) -> ScreenerRunRead:
        """创建并执行策略筛选任务，原子更新运行状态与标的结果快照。"""
        # 1. 解析目标股票池标的列表
        if request.universe == "custom":
            symbols = self._universe_manager.get_universe_symbols(
                "custom", custom_symbols=request.custom_symbols
            )
        else:
            symbols = self._universe_manager.get_universe_symbols(request.universe)

        if not symbols:
            raise UniverseNotFoundError(
                message=f"股票池 {request.universe} 无可用标的",
                details={"universe": request.universe},
            )

        # 2. 创建初始筛选任务记录 (running 状态)
        run = ScreenerRun(
            id=uuid.uuid4(),
            user_id=user_id,
            strategy_id=request.strategy_id,
            universe=request.universe,
            params=request.params,
            status="running",
            total_symbols=len(symbols),
            matched_count=0,
            failed_count=0,
            created_at=self._clock.now(),
        )
        run = await self._screener_repo.create_run(run)

        # 3. 调用筛选引擎并发执行，捕获异常避免任务状态悬空
        if self._executor is None:
            run.status = "failed"
            run.error_message = "未配置筛选执行器 (executor)"
            run.completed_at = self._clock.now()
            await self._screener_repo.update_run(run)
            raise ScreenerExecutionError(message="未配置筛选执行器 (executor)")

        try:
            results, failed_items = await self._executor.execute_screening(
                strategy_id=request.strategy_id,
                symbols=symbols,
                params=request.params,
                as_of=self._clock.now(),
            )

            orm_results = [
                ScreenerResult(
                    id=uuid.uuid4(),
                    run_id=run.id,
                    symbol=item.symbol,
                    rank=item.rank,
                    score=item.score,
                    signal=item.signal,
                    metrics_snapshot=item.metrics_snapshot,
                    created_at=self._clock.now(),
                )
                for item in results
            ]

            run.results = orm_results
            run.matched_count = len(results)
            run.failed_count = len(failed_items)
            run.status = "succeeded"
            run.completed_at = self._clock.now()
            await self._screener_repo.update_run(run)

        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = self._clock.now()
            await self._screener_repo.update_run(run)
            if isinstance(exc, ScreenerError):
                raise exc
            raise ScreenerExecutionError(
                message=f"筛选执行失败: {exc}",
                details={"strategy_id": request.strategy_id, "error": str(exc)},
            ) from exc

        return self._to_run_read(run)

    async def get_screener_run(self, run_id: UUID, user_id: UUID) -> ScreenerRunRead:
        """获取指定筛选任务记录（严格验证租户所有权，无权或不存在均统一 404）。"""
        run = await self._screener_repo.get_run(run_id, user_id)
        if run is None:
            raise ScreenerRunNotFoundError(
                message=f"未找到指定的筛选任务记录: {run_id}",
                details={"run_id": str(run_id), "user_id": str(user_id)},
            )
        return self._to_run_read(run)

    async def list_runs(
        self, user_id: UUID, limit: int = 20, offset: int = 0
    ) -> list[ScreenerRunRead]:
        """按用户分页查询历史筛选记录。"""
        runs = await self._screener_repo.list_runs(user_id, limit=limit, offset=offset)
        return [self._to_run_read(r) for r in runs]

    # ---------------------------------------------------------
    # 股票池与 F9 预设主题信息查询
    # ---------------------------------------------------------
    def list_universes(self) -> list[UniverseInfo]:
        """获取系统支持的全部股票池清单。"""
        return self._universe_manager.list_universes()

    def list_themes(self) -> list[ThemeInfo]:
        """获取系统预设的全部热门主题清单。"""
        return self._universe_manager.list_themes()

    def get_theme(self, theme_id: str) -> ThemeInfo:
        """获取指定主题的成分标的与分类信息。"""
        return self._universe_manager.get_theme(theme_id)

    async def generate_theme_cards(
        self, theme_id: str, user_id: UUID | None = None
    ) -> ThemeCardsResponse:
        """生成主题卡片（委托给 ThemeCardsGenerator 并执行事实溯源）。"""
        result = await self._theme_cards_generator.generate_theme_cards(
            theme_id=theme_id, user_id=user_id
        )
        return cast(ThemeCardsResponse, result)

    # ---------------------------------------------------------
    # 自选清单 (Watchlists) 管理
    # ---------------------------------------------------------
    async def list_watchlists(self, user_id: UUID) -> list[WatchlistRead]:
        """获取当前用户的所有自选清单。"""
        watchlists = await self._watchlist_repo.list_watchlists(user_id)
        return [self._to_watchlist_read(w) for w in watchlists]

    async def get_watchlist(self, watchlist_id: UUID, user_id: UUID) -> WatchlistRead:
        """获取指定自选清单详情及全部关注标的。"""
        watchlist = await self._watchlist_repo.get_watchlist(watchlist_id, user_id)
        if watchlist is None:
            raise WatchlistNotFoundError(
                message=f"未找到指定的自选清单: {watchlist_id}",
                details={"watchlist_id": str(watchlist_id), "user_id": str(user_id)},
            )
        return self._to_watchlist_read(watchlist)

    async def create_watchlist(self, user_id: UUID, data: WatchlistCreate) -> WatchlistRead:
        """创建新的自选清单。"""
        watchlist = await self._watchlist_repo.create_watchlist(user_id, data)
        return self._to_watchlist_read(watchlist)

    async def update_watchlist(
        self, watchlist_id: UUID, user_id: UUID, data: WatchlistUpdate
    ) -> WatchlistRead:
        """更新自选清单名称、说明或默认状态。"""
        watchlist = await self._watchlist_repo.update_watchlist(watchlist_id, user_id, data)
        if watchlist is None:
            raise WatchlistNotFoundError(
                message=f"未找到指定的自选清单: {watchlist_id}",
                details={"watchlist_id": str(watchlist_id), "user_id": str(user_id)},
            )
        return self._to_watchlist_read(watchlist)

    async def delete_watchlist(self, watchlist_id: UUID, user_id: UUID) -> bool:
        """删除指定的自选清单。"""
        deleted = await self._watchlist_repo.delete_watchlist(watchlist_id, user_id)
        if not deleted:
            raise WatchlistNotFoundError(
                message=f"未找到指定的自选清单: {watchlist_id}",
                details={"watchlist_id": str(watchlist_id), "user_id": str(user_id)},
            )
        return True

    async def add_watchlist_item(
        self, watchlist_id: UUID, user_id: UUID, data: WatchlistItemCreate
    ) -> WatchlistItemRead:
        """向指定自选清单添加关注标的。"""
        item = await self._watchlist_repo.add_item(watchlist_id, user_id, data)
        return self._to_item_read(item)

    async def update_watchlist_item(
        self,
        watchlist_id: UUID,
        item_id: UUID,
        user_id: UUID,
        data: WatchlistItemUpdate,
    ) -> WatchlistItemRead:
        """更新指定自选标的的备注、目标价或主题标签。"""
        item = await self._watchlist_repo.update_item(watchlist_id, item_id, user_id, data)
        if item is None:
            raise WatchlistItemNotFoundError(
                message=f"自选清单中未找到指定标的: {item_id}",
                details={"watchlist_id": str(watchlist_id), "item_id": str(item_id)},
            )
        return self._to_item_read(item)

    async def remove_watchlist_item(self, watchlist_id: UUID, item_id: UUID, user_id: UUID) -> bool:
        """从指定自选清单中移除标的。"""
        return await self._watchlist_repo.remove_item(watchlist_id, item_id, user_id)

    # ---------------------------------------------------------
    # 一键导出至研报/横向对比
    # ---------------------------------------------------------
    def export_to_research(self, request: ExportToResearchRequest) -> dict[str, Any]:
        """将选定标的一键构造为跳转或调用 Research 模块的数据载荷。"""
        symbols = [s.strip().upper() for s in request.symbols]
        return {
            "target_action": request.target_action,
            "symbols": symbols,
            "status": "ready",
            "target_endpoint": f"/api/v1/research/{request.target_action}",
        }

    # ---------------------------------------------------------
    # 私有 DTO 转换工具方法
    # ---------------------------------------------------------
    @staticmethod
    def _to_item_read(item: WatchlistItem) -> WatchlistItemRead:
        return WatchlistItemRead(
            id=item.id,
            watchlist_id=item.watchlist_id,
            symbol=item.symbol,
            notes=item.notes,
            target_price=item.target_price,
            theme_tags=list(item.theme_tags or []),
            created_at=item.created_at,
        )

    @classmethod
    def _to_watchlist_read(cls, watchlist: Watchlist) -> WatchlistRead:
        items = [cls._to_item_read(it) for it in (watchlist.items or [])]
        return WatchlistRead(
            id=watchlist.id,
            user_id=watchlist.user_id,
            name=watchlist.name,
            description=watchlist.description,
            is_default=watchlist.is_default,
            items=items,
            created_at=watchlist.created_at,
            updated_at=watchlist.updated_at,
        )

    @staticmethod
    def _to_run_read(run: ScreenerRun) -> ScreenerRunRead:
        raw_results = sorted(run.results or [], key=lambda r: r.rank)
        results = [
            ScreenerResultItem(
                symbol=r.symbol,
                rank=r.rank,
                score=r.score,
                signal=r.signal,
                metrics_snapshot=r.metrics_snapshot,
            )
            for r in raw_results
        ]
        return ScreenerRunRead(
            id=run.id,
            user_id=run.user_id,
            strategy_id=run.strategy_id,
            universe=run.universe,
            params=run.params,
            status=cast(Literal["pending", "running", "succeeded", "failed"], run.status),
            total_symbols=run.total_symbols,
            matched_count=run.matched_count,
            failed_count=run.failed_count,
            error_message=run.error_message,
            results=results,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )
