"""M5 AI 配额管理与用量审计服务（T06），`CONTRACTS.md §2`。

实现用户级 AI 调用日配额检查、超额拦截与原子用量持久化扣减。
遵循六边形架构与独立契约：不直接依赖 identity 模块，通过 SQLAlchemy Core 访问 ai_usage 表。
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    Integer,
    Numeric,
    Uuid,
    column,
    delete,
    insert,
    select,
    table,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import get_clock
from app.core.config import get_settings
from app.core.logging import get_logger
from app.modules.ai.exceptions import QuotaExceededError
from app.modules.ai.ports import QuotaServiceProtocol
from app.modules.ai.schemas import QuotaStatus

__all__ = [
    "QuotaService",
    "ai_usage_table",
]

logger = get_logger(__name__)

# SQLAlchemy Core 表定义（与 0003_identity 迁移结构完全一致）
ai_usage_table = table(
    "ai_usage",
    column("id", Uuid),
    column("user_id", Uuid),
    column("usage_date", Date),
    column("calls", Integer),
    column("tokens_in", Integer),
    column("tokens_out", Integer),
    column("cost_usd", Numeric),
    column("created_at", DateTime),
    column("updated_at", DateTime),
)


class QuotaService(QuotaServiceProtocol):
    """用户 AI 调用配额检查与审计服务。

    支持异步数据库 Session 持久化；当 session 为 None 时自动降级为高并发内存字典，
    保障纯单元测试与低开销运行。
    """

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        daily_quota: int | None = None,
    ) -> None:
        self._session = session
        self._daily_quota: int = (
            daily_quota if daily_quota is not None else get_settings().ai_daily_quota
        )
        # 内存缓存/降级用量字典：键为 (user_id, usage_date)
        self._in_memory_usage: dict[tuple[UUID, date], dict[str, Any]] = {}

    @property
    def daily_quota(self) -> int:
        """当日默认配额上限。"""
        return self._daily_quota

    def set_daily_quota(self, quota: int) -> None:
        """动态配置每日配额上限。"""
        if quota < 0:
            raise ValueError("daily_quota must be non-negative")
        self._daily_quota = quota

    async def check(
        self,
        user_id: UUID,
        *,
        usage_date: date | None = None,
        raise_on_exceeded: bool = True,
    ) -> QuotaStatus:
        """检查用户当日 AI 调用配额。

        Args:
            user_id: 租户用户 UUID
            usage_date: 目标日期（默认为 clock 当前 UTC 日期）
            raise_on_exceeded: 超额时是否抛出 QuotaExceededError (429)

        Returns:
            QuotaStatus 配额状态对象

        Raises:
            QuotaExceededError: 当 calls_today >= daily_quota 且 raise_on_exceeded 为 True 时
        """
        today = usage_date if usage_date is not None else get_clock().now().date()
        calls_today = await self._get_calls_today(user_id, today)

        remaining = max(0, self._daily_quota - calls_today)
        is_exceeded = calls_today >= self._daily_quota

        status = QuotaStatus(
            user_id=user_id,
            usage_date=today,
            calls_today=calls_today,
            daily_quota=self._daily_quota,
            remaining_calls=remaining,
            is_exceeded=is_exceeded,
        )

        if is_exceeded and raise_on_exceeded:
            logger.warning(
                "AI daily quota exceeded for user {user_id}: {calls}/{quota} on {date}",
                user_id=user_id,
                calls=calls_today,
                quota=self._daily_quota,
                date=today,
            )
            msg = (
                f"User {user_id} has exceeded daily AI quota of {self._daily_quota} calls "
                f"today ({calls_today}/{self._daily_quota})"
            )
            raise QuotaExceededError(
                msg,
                details={
                    "user_id": str(user_id),
                    "usage_date": str(today),
                    "calls_today": calls_today,
                    "daily_quota": self._daily_quota,
                    "remaining_calls": 0,
                    "is_exceeded": True,
                },
            )

        return status

    async def consume(
        self,
        user_id: UUID,
        tokens_in: int,
        tokens_out: int,
        cost_usd: Decimal,
        *,
        usage_date: date | None = None,
    ) -> None:
        """扣减配额并原子记账持久化到 ai_usage。

        Args:
            user_id: 用户 UUID
            tokens_in: 输入 Token 数量
            tokens_out: 输出 Token 数量
            cost_usd: 调用成本 (Decimal)
            usage_date: 计费日期（默认为 clock 当前 UTC 日期）
        """
        today = usage_date if usage_date is not None else get_clock().now().date()
        now = get_clock().now()
        cost = Decimal(str(cost_usd))

        if self._session is not None:
            # 1. 尝试原子更新已有记录
            update_stmt = (
                update(ai_usage_table)
                .where(
                    ai_usage_table.c.user_id == user_id,
                    ai_usage_table.c.usage_date == today,
                )
                .values(
                    calls=ai_usage_table.c.calls + 1,
                    tokens_in=ai_usage_table.c.tokens_in + int(tokens_in),
                    tokens_out=ai_usage_table.c.tokens_out + int(tokens_out),
                    cost_usd=ai_usage_table.c.cost_usd + cost,
                    updated_at=now,
                )
            )
            res = await self._session.execute(update_stmt)
            rowcount = getattr(res, "rowcount", 0)
            if rowcount == 0:
                # 2. 不存在时执行首次插入
                insert_stmt = insert(ai_usage_table).values(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    usage_date=today,
                    calls=1,
                    tokens_in=int(tokens_in),
                    tokens_out=int(tokens_out),
                    cost_usd=cost,
                    created_at=now,
                    updated_at=now,
                )
                try:
                    await self._session.execute(insert_stmt)
                except Exception:
                    # 并发竞态冲突，重试更新
                    await self._session.execute(update_stmt)
            await self._session.flush()
        else:
            # 内存存储
            key = (user_id, today)
            if key not in self._in_memory_usage:
                self._in_memory_usage[key] = {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "usage_date": today,
                    "calls": 1,
                    "tokens_in": int(tokens_in),
                    "tokens_out": int(tokens_out),
                    "cost_usd": cost,
                    "created_at": now,
                    "updated_at": now,
                }
            else:
                rec = self._in_memory_usage[key]
                rec["calls"] += 1
                rec["tokens_in"] += int(tokens_in)
                rec["tokens_out"] += int(tokens_out)
                rec["cost_usd"] += cost
                rec["updated_at"] = now

    async def get_usage_record(
        self,
        user_id: UUID,
        *,
        usage_date: date | None = None,
    ) -> dict[str, Any] | None:
        """获取用户指定日期的完整用量记录。"""
        today = usage_date if usage_date is not None else get_clock().now().date()

        if self._session is not None:
            stmt = select(
                ai_usage_table.c.calls,
                ai_usage_table.c.tokens_in,
                ai_usage_table.c.tokens_out,
                ai_usage_table.c.cost_usd,
            ).where(
                ai_usage_table.c.user_id == user_id,
                ai_usage_table.c.usage_date == today,
            )
            res = await self._session.execute(stmt)
            row = res.one_or_none()
            if row is None:
                return None
            return {
                "calls": int(row[0]),
                "tokens_in": int(row[1]),
                "tokens_out": int(row[2]),
                "cost_usd": Decimal(str(row[3])),
            }

        key = (user_id, today)
        if key in self._in_memory_usage:
            rec = self._in_memory_usage[key]
            return {
                "calls": rec["calls"],
                "tokens_in": rec["tokens_in"],
                "tokens_out": rec["tokens_out"],
                "cost_usd": rec["cost_usd"],
            }
        return None

    async def reset_usage(
        self,
        user_id: UUID,
        *,
        usage_date: date | None = None,
    ) -> None:
        """重置用户指定日期的用量（管理员与测试辅助）。"""
        today = usage_date if usage_date is not None else get_clock().now().date()
        if self._session is not None:
            stmt = delete(ai_usage_table).where(
                ai_usage_table.c.user_id == user_id,
                ai_usage_table.c.usage_date == today,
            )
            await self._session.execute(stmt)
            await self._session.flush()
        key = (user_id, today)
        self._in_memory_usage.pop(key, None)

    async def _get_calls_today(self, user_id: UUID, today: date) -> int:
        """读取当日调用次数。"""
        if self._session is not None:
            stmt = select(ai_usage_table.c.calls).where(
                ai_usage_table.c.user_id == user_id,
                ai_usage_table.c.usage_date == today,
            )
            res = await self._session.execute(stmt)
            row = res.one_or_none()
            if row is not None and row[0] is not None:
                return int(row[0])
            return 0

        key = (user_id, today)
        if key in self._in_memory_usage:
            return int(self._in_memory_usage[key]["calls"])
        return 0
