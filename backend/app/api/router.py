"""根路由与 API 路由（M0 / T07 整体重写），`CONTRACTS.md §1/§8/§9`。

`root_router` 挂三个根路径探针（不带 /api/v1，且不在 OpenAPI 中）；
`api_router` 预留给 M1+ 的业务模块，由 `main.py` 以 `/api/v1` 前缀挂载。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.api.health import router as health_router
from app.api.identity import router as identity_router
from app.modules.ai.api import (
    reviews_router,
)
from app.modules.ai.api import (
    router as ai_router,
)
from app.modules.ai.service import AIService
from app.modules.marketdata.api import get_data_service
from app.modules.marketdata.api import router as market_router
from app.modules.notify.api import (
    alerts_router,
    channels_router,
)
from app.modules.research.aggregator import FactAggregator
from app.modules.research.api import (
    get_stock_research,
    set_research_service_provider,
)
from app.modules.research.api import (
    router as research_router,
)
from app.modules.research.schemas import ResearchEnvelope
from app.modules.research.service import ResearchService
from app.modules.scheduler.api import (
    reports_router,
    scheduler_router,
)
from app.modules.screener.api import (
    router as screener_router,
)
from app.modules.screener.api import (
    set_screener_service_provider,
)
from app.modules.screener.service import ScreenerService, create_screener_service
from app.modules.simbroker.api import (
    router as sim_router,
)
from app.modules.strategy.api import (
    get_strategy_service,
    set_strategy_service,
)
from app.modules.strategy.api import (
    router as strategy_router,
)
from app.modules.strategy.service import StrategyService

root_router = APIRouter()
root_router.include_router(health_router)

# Wire market data service into strategy service facade
data_service = get_data_service()
set_strategy_service(StrategyService(data_service=data_service))


def _create_research_service(session: AsyncSession) -> ResearchService:
    """Wire concrete dependencies into research service facade."""
    aggregator = FactAggregator(
        data_service=get_data_service(),
        strategy_service=get_strategy_service(),
    )
    ai_service = AIService(session=session)
    return ResearchService(
        ai_service=ai_service,
        fact_aggregator=aggregator,
    )


set_research_service_provider(_create_research_service)


def _create_screener_service(session: AsyncSession) -> ScreenerService:
    """Wire concrete dependencies into screener service facade."""
    return create_screener_service(
        session,
        strategy_service=get_strategy_service(),
        data_service=get_data_service(),
        ai_service=AIService(session=session),
    )


set_screener_service_provider(_create_screener_service)

api_router = APIRouter()
api_router.include_router(market_router, prefix="/market", tags=["marketdata"])
api_router.include_router(identity_router)
api_router.include_router(
    screener_router,
    dependencies=[Depends(current_user)],
)
api_router.include_router(
    strategy_router,
    prefix="/strategy",
    tags=["strategy"],
    dependencies=[Depends(current_user)],
)
api_router.include_router(
    sim_router,
    prefix="/sim",
    tags=["simbroker"],
    dependencies=[Depends(current_user)],
)
api_router.include_router(
    ai_router,
    prefix="/ai",
    tags=["ai"],
    dependencies=[Depends(current_user)],
)
api_router.include_router(
    research_router,
    prefix="/ai",
    tags=["research"],
    dependencies=[Depends(current_user)],
)

# Alias router for /research/* compatibility
alias_research_router = APIRouter()
alias_research_router.add_api_route(
    "",
    get_stock_research,
    methods=["POST"],
    response_model=ResearchEnvelope,
    summary="执行股票综合研究（兼容别名）",
    include_in_schema=False,
)
alias_research_router.include_router(research_router)
api_router.include_router(
    alias_research_router,
    prefix="/research",
    tags=["research"],
    dependencies=[Depends(current_user)],
    include_in_schema=False,
)

# M10: 提醒规则、通知渠道、每日研报、收盘调度与复盘看板
api_router.include_router(
    alerts_router,
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(current_user)],
)
api_router.include_router(
    channels_router,
    prefix="/notification-channels",
    tags=["notification-channels"],
    dependencies=[Depends(current_user)],
)
api_router.include_router(
    reports_router,
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(current_user)],
)
api_router.include_router(
    scheduler_router,
    prefix="/scheduler",
    tags=["scheduler"],
    dependencies=[Depends(current_user)],
)
api_router.include_router(
    reviews_router,
    prefix="/reviews",
    tags=["reviews"],
    dependencies=[Depends(current_user)],
)
