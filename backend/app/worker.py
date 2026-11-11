"""ARQ worker 空壳（M0-T08）。

只提供存活任务 `ping`，不含任何业务逻辑；M1 起在此注册真实任务。
启动方式：`arq app.worker.WorkerSettings`（见 `deploy/docker-compose.yml` 的 worker 服务）。
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.core.config import get_settings, mask_redis_url
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


async def ping(ctx: dict[str, Any]) -> str:
    """最小存活任务：入队后返回 "pong"，用于验证 worker 与队列连通。"""
    return "pong"


async def on_startup(ctx: dict[str, Any]) -> None:
    """worker 进程启动：配置结构化日志并打印一次启动信息。"""
    settings = get_settings()
    setup_logging(settings)
    logger.info(
        "worker.startup",
        app_env=settings.app_env,
        redis_url=mask_redis_url(settings.redis_url),
    )


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """worker 进程退出前的收尾日志；M1 起在此关闭外部连接池。"""
    logger.info("worker.shutdown")


class WorkerSettings:
    """ARQ 入口。所有属性由 arq CLI 读取，故用 ClassVar 保持类级可见。"""

    functions: ClassVar[list[Any]] = [ping]
    on_startup: ClassVar[Any] = on_startup
    on_shutdown: ClassVar[Any] = on_shutdown

    # 与 Settings.redis_url 单一来源，避免 worker 与 api 连到不同实例。
    redis_settings: ClassVar[RedisSettings] = RedisSettings.from_dsn(get_settings().redis_url)

    max_jobs: ClassVar[int] = 10
    job_timeout: ClassVar[int] = 300
    keep_result: ClassVar[int] = 3600
