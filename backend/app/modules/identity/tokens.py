"""M1 access 令牌颁发（T03），`CONTRACTS.md §8`。

只负责 access；refresh 明文令牌由 service 生成、哈希后落库，两者组装成
`TokenPair` 也是 service 的职责，避免本模块反向依赖仓储层。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.core.config import Settings
from app.modules.identity.enums import UserRole
from app.modules.identity.ports import TokenCodec

__all__ = ["issue_access"]


def issue_access(
    codec: TokenCodec,
    *,
    user_id: uuid.UUID,
    role: UserRole,
    settings: Settings,
    now: datetime,
) -> tuple[str, int]:
    """按 `Settings.access_token_ttl_seconds` 签发，返回 `(token, expires_in)`。"""
    ttl = settings.access_token_ttl_seconds
    token = codec.issue_access(user_id=user_id, role=role, now=now, ttl_seconds=ttl)
    return token, ttl
