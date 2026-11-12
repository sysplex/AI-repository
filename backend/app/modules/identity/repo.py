"""M1 identity 仓储层（T02），`CONTRACTS.md §7`。

`TenantRepository` 是所有用户私有表查询的唯一入口：构造时必须带 `user_id`，
`_scoped()` 无条件注入 `user_id` 谓词，让「忘了带租户条件」在代码层面不可能发生。

例外：`refresh_tokens` / `password_reset_tokens` 按 SHA-256 摘要查询属于认证凭据
路径（摘要本身即秘密），不走租户过滤；但「按用户」的吊销/列举一律显式带 `user_id`。

类型说明：SQLAlchemy 2.0 的 stub 把 `select(Model)` 推断为 `Select[Model]`（而非
`Select[tuple[Model]]`）；`CONTRACTS §7` 的 `Select[tuple[ModelT]]` 是文档级写法，
本模块按实际 stub 使用 `Select[ModelT]`，运行时语义一致（已在 PR 登记偏差）。
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any, Generic, TypeVar, cast

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.db import Base
from app.modules.identity.models import AiUsage, PasswordResetToken, RefreshToken, User

__all__ = [
    "AiUsageRepository",
    "ModelT",
    "PasswordResetTokenRepository",
    "RefreshTokenRepository",
    "TenantRepository",
    "UserRepository",
]

ModelT = TypeVar("ModelT", bound=Base)


class TenantRepository(Generic[ModelT]):  # noqa: UP046 - 契约 §7 要求 TypeVar 公开符号
    """用户私有表查询基类；所有查询必须经 `_scoped()` 注入租户条件。"""

    model: type[ModelT]

    def __init__(self, session: AsyncSession, *, user_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_user_id: uuid.UUID | None = user_id

    def _user_id(self) -> uuid.UUID:
        """缺失租户标识时立即报错，绝不退化成「查全表」。"""
        if self._tenant_user_id is None:
            raise ValueError("TenantRepository 必须显式传入 user_id")
        return self._tenant_user_id

    def _scoped(self, stmt: Select[ModelT]) -> Select[ModelT]:
        """无条件追加 `user_id = :tenant`；不得被子类绕过。"""
        column = cast(Any, self.model).user_id
        return stmt.where(column == self._user_id())

    async def get_by_id(self, entity_id: uuid.UUID) -> ModelT | None:
        stmt = self._scoped(select(self.model).where(cast(Any, self.model).id == entity_id))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, *, limit: int = 20, offset: int = 0) -> Sequence[ModelT]:
        stmt = self._scoped(select(self.model)).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class UserRepository:
    """用户主表；按 email / id 检索不需要租户过滤（用户自身即租户根）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, email: str, password_hash: str, settings: dict[str, Any]) -> User:
        user = User(email=email, password_hash=password_hash, settings=settings)
        self._session.add(user)
        await self._session.flush()
        # 取回 role/status/created_at 等数据库端默认值，供 UserPublic 直接序列化。
        await self._session.refresh(user)
        return user

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return cast(User | None, await self._session.get(User, user_id))

    async def save(self, user: User) -> None:
        """把已被修改的持久化对象刷回当前事务（不 commit，由 get_session 统一提交）。"""
        self._session.add(user)
        await self._session.flush()

    async def list_paginated(self, *, page: int, page_size: int) -> tuple[Sequence[User], int]:
        total_result = await self._session.execute(select(func.count()).select_from(User))
        total = int(total_result.scalar_one() or 0)
        items_result = await self._session.execute(
            select(User).order_by(User.created_at).offset((page - 1) * page_size).limit(page_size)
        )
        return list(items_result.scalars().all()), total


class RefreshTokenRepository:
    """刷新令牌；按摘要查询，但按用户吊销必须带 `user_id`。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_active_by_hash(self, token_hash: str, *, now: datetime) -> RefreshToken | None:
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken, *, now: datetime) -> None:
        token.revoked_at = now
        self._session.add(token)
        await self._session.flush()

    async def revoke_all_for_user(self, *, user_id: uuid.UUID, now: datetime) -> int:
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        result = await self._session.execute(stmt)
        return int(cast(Any, result).rowcount or 0)


class PasswordResetTokenRepository:
    """密码重置令牌；一次性（`used_at`），按摘要查询。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> PasswordResetToken:
        token = PasswordResetToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_active_by_hash(
        self, token_hash: str, *, now: datetime
    ) -> PasswordResetToken | None:
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_used(self, token: PasswordResetToken, *, now: datetime) -> None:
        token.used_at = now
        self._session.add(token)
        await self._session.flush()


class AiUsageRepository(TenantRepository[AiUsage]):
    """AI 用量只读视图；查询一律经 `_scoped()` 带租户条件。"""

    model = AiUsage

    async def get_for_date(self, *, usage_date: date) -> AiUsage | None:
        stmt = self._scoped(select(AiUsage).where(AiUsage.usage_date == usage_date))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
