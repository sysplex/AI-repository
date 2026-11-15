"""M8 筛选器与自选清单持久化仓储实现，`CONTRACTS.md §3`。

实现筛选任务 (ScreenerRun) 与用户自选清单 (Watchlist / WatchlistItem) 的数据库持久化，
严格执行多租户隔离约束：所有 SQL 查询与更新操作强制以 ``user_id`` 为第一过滤维度，
彻底防御越权访问与水平权限穿透。
"""

from __future__ import annotations

import uuid
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import get_clock
from app.core.logging import get_logger
from app.modules.screener.exceptions import (
    DuplicateWatchlistItemError,
    ScreenerError,
    WatchlistItemNotFoundError,
    WatchlistNotFoundError,
)
from app.modules.screener.models import ScreenerRun, Watchlist, WatchlistItem
from app.modules.screener.schemas import (
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemUpdate,
    WatchlistUpdate,
)

__all__ = [
    "ScreenerRepository",
    "WatchlistRepository",
]

logger = get_logger("screener.repo")


class ScreenerRepository:
    """筛选任务持久化仓储（强制多租户隔离）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(self, run: ScreenerRun) -> ScreenerRun:
        """持久化创建新的筛选任务记录。"""
        if getattr(run, "id", None) is None:
            run.id = uuid.uuid4()
        if getattr(run, "created_at", None) is None:
            run.created_at = get_clock().now()
        self._session.add(run)
        await self._session.flush()
        return run

    async def update_run(self, run: ScreenerRun) -> ScreenerRun:
        """更新已有筛选任务状态与结果。"""
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_run(self, run_id: UUID, user_id: UUID) -> ScreenerRun | None:
        """按 ID 与 user_id 查询任务详情（急切加载结果列表）。"""
        stmt = (
            select(ScreenerRun)
            .options(selectinload(ScreenerRun.results))
            .where(ScreenerRun.id == run_id, ScreenerRun.user_id == user_id)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_runs(self, user_id: UUID, limit: int = 20, offset: int = 0) -> list[ScreenerRun]:
        """按用户分页查询历史筛选任务。"""
        stmt = (
            select(ScreenerRun)
            .options(selectinload(ScreenerRun.results))
            .where(ScreenerRun.user_id == user_id)
            .order_by(ScreenerRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())


class WatchlistRepository:
    """用户自选清单持久化仓储（强制多租户隔离）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_watchlists(self, user_id: UUID) -> list[Watchlist]:
        """查询用户全部自选清单（按创建时间正序，急切加载包含标的）。"""
        stmt = (
            select(Watchlist)
            .options(selectinload(Watchlist.items))
            .where(Watchlist.user_id == user_id)
            .order_by(Watchlist.created_at.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def get_watchlist(self, watchlist_id: UUID, user_id: UUID) -> Watchlist | None:
        """按 ID 与 user_id 获取单个自选清单（急切加载标的）。"""
        stmt = (
            select(Watchlist)
            .options(selectinload(Watchlist.items))
            .where(Watchlist.id == watchlist_id, Watchlist.user_id == user_id)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def create_watchlist(self, user_id: UUID, data: WatchlistCreate) -> Watchlist:
        """创建自选清单；若指定为默认清单，原子取消用户其他清单的默认状态。"""
        now = get_clock().now()
        if data.is_default:
            await self._session.execute(
                update(Watchlist)
                .where(
                    Watchlist.user_id == user_id,
                    Watchlist.is_default.is_(True),
                )
                .values(is_default=False)
            )

        watchlist = Watchlist(
            id=uuid.uuid4(),
            user_id=user_id,
            name=data.name,
            description=data.description,
            is_default=data.is_default,
            created_at=now,
            updated_at=now,
        )
        watchlist.items = []
        self._session.add(watchlist)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ScreenerError(
                message=f"已存在同名的自选清单: {data.name}",
                details={"name": data.name, "user_id": str(user_id)},
            ) from exc
        return watchlist

    async def update_watchlist(
        self, watchlist_id: UUID, user_id: UUID, data: WatchlistUpdate
    ) -> Watchlist | None:
        """更新自选清单名称、描述或默认属性。"""
        watchlist = await self.get_watchlist(watchlist_id, user_id)
        if watchlist is None:
            return None

        if data.is_default is True:
            await self._session.execute(
                update(Watchlist)
                .where(
                    Watchlist.user_id == user_id,
                    Watchlist.id != watchlist_id,
                    Watchlist.is_default.is_(True),
                )
                .values(is_default=False)
            )

        if data.name is not None:
            watchlist.name = data.name
        if data.description is not None:
            watchlist.description = data.description
        if data.is_default is not None:
            watchlist.is_default = data.is_default
        watchlist.updated_at = get_clock().now()

        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ScreenerError(
                message=f"已存在同名的自选清单: {data.name}",
                details={"name": data.name, "user_id": str(user_id)},
            ) from exc
        return watchlist

    async def delete_watchlist(self, watchlist_id: UUID, user_id: UUID) -> bool:
        """删除指定自选清单（级联删除清单内所有标的）。"""
        watchlist = await self.get_watchlist(watchlist_id, user_id)
        if watchlist is None:
            return False

        await self._session.delete(watchlist)
        await self._session.flush()
        return True

    async def add_item(
        self, watchlist_id: UUID, user_id: UUID, data: WatchlistItemCreate
    ) -> WatchlistItem:
        """向自选清单添加关注标的，并实施重复标的防御校验。"""
        watchlist = await self.get_watchlist(watchlist_id, user_id)
        if watchlist is None:
            raise WatchlistNotFoundError(
                message=f"未找到指定的自选清单: {watchlist_id}",
                details={"watchlist_id": str(watchlist_id), "user_id": str(user_id)},
            )

        norm_symbol = data.symbol.strip().upper()

        stmt = select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.symbol == norm_symbol,
        )
        res = await self._session.execute(stmt)
        if res.scalar_one_or_none() is not None:
            raise DuplicateWatchlistItemError(
                message=f"标的 {norm_symbol} 已存在于该自选清单中",
                details={"watchlist_id": str(watchlist_id), "symbol": norm_symbol},
            )

        item = WatchlistItem(
            id=uuid.uuid4(),
            watchlist_id=watchlist_id,
            symbol=norm_symbol,
            notes=data.notes,
            target_price=data.target_price,
            theme_tags=list(data.theme_tags),
            created_at=get_clock().now(),
        )
        self._session.add(item)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateWatchlistItemError(
                message=f"标的 {norm_symbol} 已存在于该自选清单中",
                details={"watchlist_id": str(watchlist_id), "symbol": norm_symbol},
            ) from exc

        return item

    async def update_item(
        self,
        watchlist_id: UUID,
        item_id: UUID,
        user_id: UUID,
        data: WatchlistItemUpdate,
    ) -> WatchlistItem | None:
        """更新自选清单内指定标的的备注、目标价或主题标签。"""
        watchlist = await self.get_watchlist(watchlist_id, user_id)
        if watchlist is None:
            raise WatchlistNotFoundError(
                message=f"未找到指定的自选清单: {watchlist_id}",
                details={"watchlist_id": str(watchlist_id), "user_id": str(user_id)},
            )

        stmt = select(WatchlistItem).where(
            WatchlistItem.id == item_id,
            WatchlistItem.watchlist_id == watchlist_id,
        )
        res = await self._session.execute(stmt)
        item = res.scalar_one_or_none()
        if item is None:
            raise WatchlistItemNotFoundError(
                message=f"自选清单中未找到指定标的: {item_id}",
                details={"watchlist_id": str(watchlist_id), "item_id": str(item_id)},
            )

        if data.notes is not None:
            item.notes = data.notes
        if data.target_price is not None:
            item.target_price = data.target_price
        if data.theme_tags is not None:
            item.theme_tags = cast(list[str], list(data.theme_tags))

        await self._session.flush()
        return item

    async def remove_item(self, watchlist_id: UUID, item_id: UUID, user_id: UUID) -> bool:
        """从指定自选清单移除关注标的。"""
        watchlist = await self.get_watchlist(watchlist_id, user_id)
        if watchlist is None:
            raise WatchlistNotFoundError(
                message=f"未找到指定的自选清单: {watchlist_id}",
                details={"watchlist_id": str(watchlist_id), "user_id": str(user_id)},
            )

        stmt = select(WatchlistItem).where(
            WatchlistItem.id == item_id,
            WatchlistItem.watchlist_id == watchlist_id,
        )
        res = await self._session.execute(stmt)
        item = res.scalar_one_or_none()
        if item is None:
            raise WatchlistItemNotFoundError(
                message=f"自选清单中未找到指定标的: {item_id}",
                details={"watchlist_id": str(watchlist_id), "item_id": str(item_id)},
            )

        await self._session.delete(item)
        await self._session.flush()
        return True
