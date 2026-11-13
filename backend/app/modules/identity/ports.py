"""M1 identity 端口定义（T01），`CONTRACTS.md §5`。

外部系统（密码学库 / JWT 库 / 邮件投递）一律经本文件的 Protocol 接入；
实现放在 `adapters/`（T03），业务代码不直接 import 第三方 SDK（`docs/02 §4`）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.modules.identity.enums import UserRole

__all__ = ["AccessClaims", "MailSender", "PasswordHasher", "TokenCodec"]


class PasswordHasher(Protocol):
    """密码哈希端口：`verify` 对畸形哈希返回 False，不抛底层异常。"""

    def hash(self, password: str) -> str:
        """返回包含算法与参数的完整哈希串。"""
        ...

    def verify(self, password: str, password_hash: str) -> bool:
        """校验明文密码；任何异常都收敛为 False。"""
        ...


@dataclass(frozen=True, slots=True)
class AccessClaims:
    """access 令牌解析结果；所有时间为 UTC。"""

    user_id: uuid.UUID
    role: UserRole
    issued_at: datetime
    expires_at: datetime


class TokenCodec(Protocol):
    """access 令牌编解码端口；失败统一抛 M0 的 Unauthenticated / TokenExpired。"""

    def issue_access(
        self,
        *,
        user_id: uuid.UUID,
        role: UserRole,
        now: datetime,
        ttl_seconds: int,
    ) -> str:
        """签发 HS256 access 令牌；claims 只含 sub/role/iat/exp。"""
        ...

    def decode_access(self, token: str, *, now: datetime) -> AccessClaims:
        """严格校验签名、过期与必要字段，返回不可变 claims。"""
        ...


class MailSender(Protocol):
    """邮件投递端口（Q3 裁决：内存 / 日志 / Gmail·Outlook SMTP 三种实现）。"""

    async def send(self, *, to: str, subject: str, body: str) -> None:
        """发送一封纯文本邮件；实现不得记录完整令牌到生产日志。"""
        ...
