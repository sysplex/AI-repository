"""HS256 JWT access 令牌适配器（T03）——仓库内唯一 `import jwt` 的位置。

解码不依赖 PyJWT 的「当前系统时间」，而是显式按调用方传入的 `now` 判断过期，
使 `FrozenClock` 下的测试可确定性复现；所有失败统一转成 M0 的
`Unauthenticated` / `TokenExpired`，`from None` 掐断底层异常链，不泄露库文本。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Final

import jwt

from app.core.errors import TokenExpired, Unauthenticated
from app.modules.identity.enums import UserRole
from app.modules.identity.ports import AccessClaims

__all__ = ["JWTTokenCodec"]

_MIN_SECRET_LENGTH: Final[int] = 32
_SUPPORTED_ALGORITHM: Final[str] = "HS256"


def _epoch_seconds(value: object) -> int:
    """把 JWT 的 `iat` / `exp` 收敛成整数 epoch 秒；`bool` 与浮点一律拒绝。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("epoch seconds must be int")
    return value


class JWTTokenCodec:
    """`TokenCodec` 端口的 PyJWT 实现。"""

    def __init__(self, secret: str, algorithm: str) -> None:
        if len(secret) < _MIN_SECRET_LENGTH:
            raise ValueError("JWT 签名密钥长度至少 32 字符")
        if algorithm != _SUPPORTED_ALGORITHM:
            raise ValueError("M1 仅支持 HS256")
        self._secret = secret
        self._algorithm = algorithm

    def issue_access(
        self,
        *,
        user_id: uuid.UUID,
        role: UserRole,
        now: datetime,
        ttl_seconds: int,
    ) -> str:
        """签发只含 `sub/role/iat/exp` 的 access 令牌（epoch 秒精度）。"""
        issued_at = int(now.timestamp())
        expires_at = issued_at + ttl_seconds
        payload = {
            "sub": str(user_id),
            "role": role.value,
            "iat": issued_at,
            "exp": expires_at,
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode_access(self, token: str, *, now: datetime) -> AccessClaims:
        """严格校验签名与必要字段，按传入的 `now` 判断过期。

        `verify_exp` / `verify_iat` 均关闭：PyJWT 2.15 的 `iat` 校验会把「签发时间
        晚于进程系统时间」判为 `ImmatureSignatureError`，而本端口的时间基准是调用方
        显式传入的 `now`（`FrozenClock` / 请求时钟），不能用进程时钟代替。时间语义
        全部由下面的显式比较实现，因此关闭第三方时间校验不降低严格性。
        """
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={
                    "require": ["sub", "role", "iat", "exp"],
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
        except (jwt.InvalidTokenError, TypeError, ValueError):
            raise Unauthenticated() from None

        try:
            user_id = uuid.UUID(str(payload["sub"]))
            role = UserRole(str(payload["role"]))
            issued_at = datetime.fromtimestamp(_epoch_seconds(payload["iat"]), UTC)
            expires_at = datetime.fromtimestamp(_epoch_seconds(payload["exp"]), UTC)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            raise Unauthenticated() from None

        if expires_at <= now:
            raise TokenExpired() from None
        if expires_at <= issued_at:
            raise Unauthenticated() from None
        return AccessClaims(user_id=user_id, role=role, issued_at=issued_at, expires_at=expires_at)
