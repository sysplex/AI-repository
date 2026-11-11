"""Redis 客户端（M0 / T07），`CONTRACTS.md §8`。

懒创建进程内单例；连接与读写超时固定 2 秒。对外只暴露
`get_redis/check_redis/close_redis`，探活失败一律返回 False，不向调用方抛异常。
连接串只从 `Settings.redis_url` 读取，本文件不含任何硬编码凭据。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.core.config import Settings

_TIMEOUT_SECONDS = 2.0

_client: aioredis.Redis | None = None


def _settings() -> Settings:
    """间接层：让测试可通过替换本模块内的名字注入配置。"""
    return get_settings()


def get_redis() -> aioredis.Redis:
    """懒创建单例；`decode_responses=True`，连接/读写超时均为 2 秒。"""
    global _client
    if _client is None:
        _client = aioredis.from_url(  # type: ignore[no-untyped-call]
            _settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=_TIMEOUT_SECONDS,
            socket_timeout=_TIMEOUT_SECONDS,
        )
    return _client


async def ping_redis() -> bool:
    """单次 PING；异常由 `check_redis` 统一收敛。"""
    return bool(await get_redis().ping())


async def check_redis() -> bool:
    """PING 探活；连接失败、拒绝、超时均返回 False，不抛异常。"""
    try:
        return await asyncio.wait_for(ping_redis(), timeout=_TIMEOUT_SECONDS)
    except Exception:
        # TimeoutError / ConnectionError / RedisError 一律视为不可用；
        # CancelledError 继承 BaseException，仍向上传播以便 /readyz 超时取消。
        return False


async def close_redis() -> None:
    """关闭连接并清空单例；重复调用安全。"""
    global _client
    client, _client = _client, None
    if client is not None:
        await client.aclose()
