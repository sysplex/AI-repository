"""ARQ worker 后台任务与定时作业配置（M0-T08, M10-T05）。

启动方式：`arq app.worker.WorkerSettings`（见 `deploy/docker-compose.yml` 的 worker 服务）。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, ClassVar

from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import load_settings_or_exit, mask_redis_url
from app.core.db import dispose_engine, get_session_factory
from app.core.logging import get_logger, setup_logging
from app.modules.scheduler.pipeline import PostMarketPipeline

logger = get_logger(__name__)


async def ping(ctx: dict[str, Any]) -> str:
    """最小存活任务：入队后返回 "pong"，用于验证 worker 与队列连通。"""
    return "pong"


async def run_post_market_pipeline(
    ctx: dict[str, Any],
    trade_date: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """收盘后全流程批处理流水线任务（M10-T05）。

    可通过 ARQ 异步入队或由定时作业触发，支持传入 trade_date（YYYY-MM-DD）手动重跑历史交易日。
    """
    session_factory = ctx.get("session_factory") or get_session_factory()
    target_date = (
        datetime.strptime(trade_date.strip(), "%Y-%m-%d").date() if trade_date else date.today()
    )

    async with session_factory() as session:
        pipeline = PostMarketPipeline(session=session)
        res = await pipeline.run(trade_date=target_date, force=force)
        return res.model_dump(mode="json")


async def on_startup(ctx: dict[str, Any]) -> None:
    """worker 进程启动：配置结构化日志、数据库连接池并打印一次启动信息。"""
    settings = load_settings_or_exit()
    setup_logging(settings)
    ctx["session_factory"] = get_session_factory()
    logger.info(
        "worker.startup",
        app_env=settings.app_env,
        redis_url=mask_redis_url(settings.redis_url),
    )


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """worker 进程退出前的收尾工作：关闭数据库引擎与清理外部连接池。"""
    await dispose_engine()
    logger.info("worker.shutdown")


class WorkerSettings:
    """ARQ 入口。所有属性由 arq CLI 读取，故用 ClassVar 保持类级可见。"""

    functions: ClassVar[list[Any]] = [ping, run_post_market_pipeline]
    cron_jobs: ClassVar[list[Any]] = [
        # 美股正常交易日（周一至周五）收盘后定时触发
        # 对应美东 16:15 收盘结算窗口
        cron(
            run_post_market_pipeline,
            hour={20, 21},
            minute=15,
            weekday={0, 1, 2, 3, 4},
            name="cron:post_market_pipeline",
        )
    ]
    on_startup: ClassVar[Any] = on_startup
    on_shutdown: ClassVar[Any] = on_shutdown

    # 与 Settings.redis_url 单一来源，避免 worker 与 api 连到不同实例。
    redis_settings: ClassVar[RedisSettings] = RedisSettings.from_dsn(
        load_settings_or_exit().redis_url
    )

    max_jobs: ClassVar[int] = 10
    job_timeout: ClassVar[int] = 600
    keep_result: ClassVar[int] = 3600
