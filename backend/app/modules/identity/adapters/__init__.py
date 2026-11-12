"""M1 identity 外部系统适配器（T03），`CONTRACTS.md §6`。

业务层只依赖 `ports.py` 的 Protocol；第三方 SDK（`argon2` / `jwt`）只在本包内出现。
"""

from __future__ import annotations

from app.modules.identity.adapters.mail import (
    InMemoryMailSender,
    LoggingMailSender,
    MailMessage,
)
from app.modules.identity.adapters.password_hasher import Argon2PasswordHasher
from app.modules.identity.adapters.token_codec import JWTTokenCodec

__all__ = [
    "Argon2PasswordHasher",
    "InMemoryMailSender",
    "JWTTokenCodec",
    "LoggingMailSender",
    "MailMessage",
]
