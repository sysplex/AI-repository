"""Argon2 密码哈希适配器（T03）——仓库内唯一 `import argon2` 的位置。

参数按 OWASP 基线常量化；`verify` 对错误密码与畸形哈希一律返回 False，
绝不把底层异常抛给业务层或泄露到响应体。
"""

from __future__ import annotations

from typing import Final

from argon2 import PasswordHasher as _Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError

__all__ = ["Argon2PasswordHasher"]

_TIME_COST: Final[int] = 3
_MEMORY_COST_KIB: Final[int] = 64 * 1024  # 64 MiB
_PARALLELISM: Final[int] = 2
_HASH_LENGTH: Final[int] = 32
_SALT_LENGTH: Final[int] = 16


class Argon2PasswordHasher:
    """`PasswordHasher` 端口的 argon2id 实现。"""

    def __init__(self) -> None:
        self._hasher = _Argon2Hasher(
            time_cost=_TIME_COST,
            memory_cost=_MEMORY_COST_KIB,
            parallelism=_PARALLELISM,
            hash_len=_HASH_LENGTH,
            salt_len=_SALT_LENGTH,
        )

    def hash(self, password: str) -> str:
        """返回带算法、参数、盐的完整 `$argon2...` 串。"""
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        """校验密码；不匹配、类型非法或哈希串畸形均收敛为 False。

        argon2-cffi 对 `None` 之类的非字符串会在内部 `.encode()` 抛
        `AttributeError`（不是 `ValueError` 子类），因此先做类型与空值前置判断，
        保证端口「只返回布尔」的约定在任何输入下都成立。
        """
        if not isinstance(password, str) or not isinstance(password_hash, str):
            return False
        if not password or not password_hash:
            return False
        try:
            return bool(self._hasher.verify(password_hash, password))
        except (VerificationError, InvalidHashError, ValueError, TypeError):
            return False
