"""M4 模拟盘 REST API 路由端点（T07），`CONTRACTS.md §1 & §2` 与 `docs/05-api-spec.md §2.4`。

对外暴露完整的 `/api/v1/sim/*` 端点体系：
- 账户生命周期管理（创建、列表、实时概览）
- 出入金资金流（充值、提现）
- 订单交易生命周期（下单、挂单列表、撤单）
- 持仓、成交历史查询
- 投资组合业绩指标与持仓风险体检
- 交易复盘日志录入
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import Unauthenticated
from app.modules.simbroker.ports import MarketDataFeedProtocol
from app.modules.simbroker.schemas import (
    AccountCreate,
    AccountOverview,
    AccountResponse,
    DepositRequest,
    OrderCreate,
    OrderResponse,
    PerformanceMetrics,
    PositionResponse,
    RiskOverview,
    TradeJournalResponse,
    TradeJournalUpdate,
    TradeResponse,
)
from app.modules.simbroker.service import SimService

logger = structlog.get_logger(__name__)

router = APIRouter()

_market_feed: MarketDataFeedProtocol | None = None


def set_market_feed(feed: MarketDataFeedProtocol | None) -> None:
    """注入行情数据源供 SimService 进行估值与基准对比。"""
    global _market_feed
    _market_feed = feed


def get_sim_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SimService:
    """SimService 依赖注入提供器。"""
    return SimService(session=session, market_feed=_market_feed)


def get_current_user(request: Request) -> Any:
    """从 ASGI 请求上下文获取已通过 HARD-01 鉴权的用户信息。"""
    user = getattr(request.state, "user", None)
    if user is None:
        raise Unauthenticated()
    return user


# -----------------------------------------------------------------------------
# 1. 账户管理端点
# -----------------------------------------------------------------------------


@router.post(
    "/accounts",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建模拟盘账户",
)
async def create_account(
    req: AccountCreate,
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> AccountResponse:
    """为当前登录用户创建一个新的模拟盘账户。"""
    return await service.create_account(user_id=user.id, req=req)


@router.get(
    "/accounts",
    response_model=list[AccountResponse],
    summary="列出我的模拟账户",
)
async def list_accounts(
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> list[AccountResponse]:
    """查询当前登录用户名下的所有模拟账户。"""
    return await service.list_accounts(user_id=user.id)


@router.get(
    "/accounts/{account_id}",
    response_model=AccountOverview,
    summary="获取账户实时概览",
)
async def get_account_overview(
    account_id: uuid.UUID,
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> AccountOverview:
    """获取模拟账户的实时净值、持仓市值、当日盈亏、总盈亏及 PDT 监控状态。"""
    return await service.get_account_overview(account_id=account_id, user_id=user.id)


# -----------------------------------------------------------------------------
# 2. 资金出入金端点
# -----------------------------------------------------------------------------


@router.post(
    "/accounts/{account_id}/deposit",
    summary="充值入金",
)
async def deposit(
    account_id: uuid.UUID,
    req: DepositRequest,
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> dict[str, Any]:
    """向指定账户存入资金。"""
    new_cash = await service.deposit(account_id=account_id, amount=req.amount, user_id=user.id)
    return {"account_id": str(account_id), "cash": str(new_cash)}


@router.post(
    "/accounts/{account_id}/withdraw",
    summary="提现出金",
)
async def withdraw(
    account_id: uuid.UUID,
    req: DepositRequest,
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> dict[str, Any]:
    """从指定账户提取资金（受当前可用现金限制）。"""
    new_cash = await service.withdraw(account_id=account_id, amount=req.amount, user_id=user.id)
    return {"account_id": str(account_id), "cash": str(new_cash)}


# -----------------------------------------------------------------------------
# 3. 订单交易生命周期
# -----------------------------------------------------------------------------


@router.post(
    "/accounts/{account_id}/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提交订单",
)
async def submit_order(
    account_id: uuid.UUID,
    req: OrderCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> OrderResponse:
    """提交委托订单，强制要求传递 Idempotency-Key 请求头保障幂等性。"""
    return await service.submit_order(
        user_id=user.id,
        account_id=account_id,
        req=req,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/accounts/{account_id}/orders",
    response_model=list[OrderResponse],
    summary="查询订单列表",
)
async def list_orders(
    account_id: uuid.UUID,
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
    order_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[OrderResponse]:
    """查询指定账户的委托订单列表，支持按订单状态过滤。"""
    return await service.list_orders(
        account_id=account_id,
        status=order_status,
        user_id=user.id,
    )


@router.delete(
    "/accounts/{account_id}/orders/{order_id}",
    response_model=OrderResponse,
    summary="撤销挂单",
)
async def cancel_order(
    account_id: uuid.UUID,
    order_id: uuid.UUID,
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> OrderResponse:
    """撤销尚未完全成交的委托订单。"""
    return await service.cancel_order(
        account_id=account_id,
        order_id=order_id,
        user_id=user.id,
    )


# -----------------------------------------------------------------------------
# 4. 持仓与成交查询
# -----------------------------------------------------------------------------


@router.get(
    "/accounts/{account_id}/positions",
    response_model=list[PositionResponse],
    summary="查询持仓列表",
)
async def get_positions(
    account_id: uuid.UUID,
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> list[PositionResponse]:
    """查询指定账户的所有有效持仓明细（含加权成本、现价、浮动盈亏与持仓权重）。"""
    return await service.get_positions(account_id=account_id, user_id=user.id)


@router.get(
    "/accounts/{account_id}/trades",
    response_model=list[TradeResponse],
    summary="查询成交记录",
)
async def get_trades(
    account_id: uuid.UUID,
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> list[TradeResponse]:
    """查询指定账户的所有历史成交明细。"""
    return await service.get_trades(account_id=account_id, user_id=user.id)


# -----------------------------------------------------------------------------
# 5. 业绩分析与持仓风险体检
# -----------------------------------------------------------------------------


@router.get(
    "/accounts/{account_id}/performance",
    response_model=PerformanceMetrics,
    summary="查询账户业绩指标",
)
async def get_performance(
    account_id: uuid.UUID,
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> PerformanceMetrics:
    """获取账户全周期绩效指标（净值曲线、全局最大回撤、胜率、盈亏比与基准 SPY 对比）。"""
    return await service.get_performance(account_id=account_id, user_id=user.id)


@router.get(
    "/accounts/{account_id}/risk",
    response_model=RiskOverview,
    summary="持仓风险体检诊断",
)
async def get_risk(
    account_id: uuid.UUID,
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> RiskOverview:
    """获取当前投资组合健康度风险体检（现金水位、重仓股集中度、行业分布、PDT 监管状态）。"""
    return await service.get_risk(account_id=account_id, user_id=user.id)


# -----------------------------------------------------------------------------
# 6. 交易复盘日志录入
# -----------------------------------------------------------------------------


@router.put(
    "/trades/{trade_id}/journal",
    response_model=TradeJournalResponse,
    summary="录入/更新交易日志",
)
async def update_trade_journal(
    trade_id: uuid.UUID,
    req: TradeJournalUpdate,
    service: Annotated[SimService, Depends(get_sim_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> TradeJournalResponse:
    """对单笔成交录入复盘笔记、标签与交易情绪。"""
    return await service.update_trade_journal(
        trade_id=trade_id,
        req=req,
        user_id=user.id,
    )
