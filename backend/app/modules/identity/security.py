"""M1 安全原语组合层（T03），`CONTRACTS.md §8`。

本模块**不 import 任何第三方 SDK**，只把 `ports.py` 的能力与标准库原语组合起来。
明文不透明令牌只经响应体或本地邮件适配器返回一次，绝不落库、绝不写日志。
"""

from __future__ import annotations

import hashlib
import secrets

from pydantic import SecretStr

from app.modules.identity.ports import PasswordHasher

__all__ = ["hash_opaque_token", "hash_password", "new_opaque_token", "verify_password"]

_TOKEN_BYTES = 32


def hash_password(hasher: PasswordHasher, password: SecretStr) -> str:
    """用端口实现哈希；`SecretStr` 只在这里解包一次。"""
    return hasher.hash(password.get_secret_value())


def verify_password(hasher: PasswordHasher, password: SecretStr, password_hash: str) -> bool:
    """校验密码；任何畸形哈希由适配器收敛为 False。"""
    return hasher.verify(password.get_secret_value(), password_hash)


def new_opaque_token() -> str:
    """生成 URL-safe 的 256 位随机明文令牌。"""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_opaque_token(token: str) -> str:
    """把明文令牌映射为固定 64 位十六进制 SHA-256 摘要，供数据库唯一列使用。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
