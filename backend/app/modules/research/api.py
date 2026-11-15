"""M6 & M7 AI 研究用例 REST API 路由与端点实现，`CONTRACTS.md §6`。

对外暴露 `/api/v1/ai/*` 核心研究用例端点：
- `POST /api/v1/ai/research`：执行股票深度综合研究报告 (F2)
- `POST /api/v1/ai/buy-decision`：执行买入决策评估与代码量化点位 (F3)
- `POST /api/v1/ai/compare`：执行多股票横向对比分析 (F4)
- `POST /api/v1/ai/long-term`：执行长期持有价值与破裂条件评估 (F5)
- `POST /api/v1/ai/technical`：执行技术面通俗分析与确定性交易计划 (F6)
- `POST /api/v1/ai/earnings`：执行财报深度解读与业绩指引分析 (F7)
- `POST /api/v1/ai/portfolio`：执行投资组合配置优化建议 (F8)

设计原则与质量契约：
- 严格遵循 HARD-01 认证与租户数据隔离；
- 符合架构分层隔离（Layer 2 组装层，通过依赖注入解耦）；
- 统一将业务异常映射至标准 HTTP 状态码与 AppError 结构。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import Unauthenticated
from app.core.logging import get_logger
from app.modules.research.ports import ResearchServiceProtocol
from app.modules.research.schemas import (
    BuyDecisionRequest,
    CompareRequest,
    EarningsAnalysisRequest,
    LongTermRequest,
    PortfolioRequest,
    ResearchEnvelope,
    ResearchRequest,
    TechnicalAnalysisRequest,
)

__all__ = [
    "compare_stocks",
    "generate_portfolio_allocation",
    "get_current_user",
    "get_earnings_analysis",
    "get_long_term_analysis",
    "get_research_service",
    "get_stock_research",
    "get_technical_analysis",
    "router",
    "set_research_service",
    "set_research_service_provider",
]

logger = get_logger("research.api")

router = APIRouter()

# 全局或自定义服务实例/工厂（用于依赖注入与测试 Mock 隔离）
_research_service: ResearchServiceProtocol | None = None
_research_service_provider: Callable[[AsyncSession], ResearchServiceProtocol] | None = None


def set_research_service(service: ResearchServiceProtocol | None) -> None:
    """设置全局 ResearchService 实例（主要用于单元与集成测试快速注入）。"""
    global _research_service
    _research_service = service


def set_research_service_provider(
    provider: Callable[[AsyncSession], ResearchServiceProtocol] | None,
) -> None:
    """设置 ResearchService 依赖工厂（用于 FastAPI 运行期会话注入）。"""
    global _research_service_provider
    _research_service_provider = provider


def get_research_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ResearchServiceProtocol:
    """FastAPI 依赖注入提供器。"""
    if _research_service is not None:
        return _research_service
    if _research_service_provider is not None:
        return _research_service_provider(session)
    raise RuntimeError("ResearchService has not been configured in app router")


def get_current_user(request: Request) -> Any:
    """从 ASGI 请求上下文中提取已验证的当前用户（HARD-01）。"""
    user = getattr(request.state, "user", None)
    if user is None:
        raise Unauthenticated("需要认证才能访问 AI 研究服务")
    return user


def _extract_user_id(user: Any) -> UUID:
    """安全解析用户唯一标识 UUID。"""
    raw_id = getattr(user, "id", None)
    if raw_id is None and isinstance(user, dict):
        raw_id = user.get("id")
    if raw_id is None:
        raise Unauthenticated("无法获取有效的用户会话标识")
    if isinstance(raw_id, UUID):
        return raw_id
    try:
        return UUID(str(raw_id))
    except (ValueError, TypeError) as exc:
        raise Unauthenticated(f"无效的用户 ID 格式: {raw_id}") from exc


# -----------------------------------------------------------------------------
# 1. F2: 股票综合研究 (research)
# -----------------------------------------------------------------------------


@router.post(
    "/research",
    response_model=ResearchEnvelope,
    status_code=status.HTTP_200_OK,
    summary="执行股票综合研究报告",
)
async def get_stock_research(
    req: ResearchRequest,
    service: Annotated[ResearchServiceProtocol, Depends(get_research_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> ResearchEnvelope:
    """执行个股商业模式、护城河、核心风险与情景分析。"""
    user_id = _extract_user_id(user)
    return await service.get_stock_research(request=req, user_id=user_id)


# -----------------------------------------------------------------------------
# 2. F3: 买入决策评估 (buy-decision)
# -----------------------------------------------------------------------------


@router.post(
    "/buy-decision",
    response_model=ResearchEnvelope,
    status_code=status.HTTP_200_OK,
    summary="执行买入决策评估",
)
async def get_buy_decision(
    req: BuyDecisionRequest,
    service: Annotated[ResearchServiceProtocol, Depends(get_research_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> ResearchEnvelope:
    """结合用户想买价与时间周期，执行买入/观望/避开综合决策评估。"""
    user_id = _extract_user_id(user)
    return await service.get_buy_decision(request=req, user_id=user_id)


# -----------------------------------------------------------------------------
# 3. F6: 技术面通俗分析 (technical)
# -----------------------------------------------------------------------------


@router.post(
    "/technical",
    response_model=ResearchEnvelope,
    status_code=status.HTTP_200_OK,
    summary="执行技术面通俗分析与计划",
)
async def get_technical_analysis(
    req: TechnicalAnalysisRequest,
    service: Annotated[ResearchServiceProtocol, Depends(get_research_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> ResearchEnvelope:
    """执行均线/趋势/动量分析，并由代码确定性计算入场/止损/目标交易计划。"""
    user_id = _extract_user_id(user)
    return await service.get_technical_analysis(request=req, user_id=user_id)


# -----------------------------------------------------------------------------
# 4. F7: 财报深度解读 (earnings)
# -----------------------------------------------------------------------------


@router.post(
    "/earnings",
    response_model=ResearchEnvelope,
    status_code=status.HTTP_200_OK,
    summary="执行财报深度解读",
)
async def get_earnings_analysis(
    req: EarningsAnalysisRequest,
    service: Annotated[ResearchServiceProtocol, Depends(get_research_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> ResearchEnvelope:
    """解读营收/利润/指引预期差，评估管理层评论与市场反应。"""
    user_id = _extract_user_id(user)
    return await service.get_earnings_analysis(request=req, user_id=user_id)


# -----------------------------------------------------------------------------
# 5. F4: 股票横向对比 (compare)
# -----------------------------------------------------------------------------


@router.post(
    "/compare",
    response_model=ResearchEnvelope,
    status_code=status.HTTP_200_OK,
    summary="执行多股票横向对比分析",
)
async def compare_stocks(
    req: CompareRequest,
    service: Annotated[ResearchServiceProtocol, Depends(get_research_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> ResearchEnvelope:
    """横向对比 2-8 只美股标的，输出 8 大维度定性分析、确定性排名与画像匹配。"""
    user_id = _extract_user_id(user)
    return await service.compare_stocks(request=req, user_id=user_id)


# -----------------------------------------------------------------------------
# 6. F5: 长期持有价值与破裂条件 (long-term)
# -----------------------------------------------------------------------------


@router.post(
    "/long-term",
    response_model=ResearchEnvelope,
    status_code=status.HTTP_200_OK,
    summary="执行长期持有价值与破裂条件评估",
)
async def get_long_term_analysis(
    req: LongTermRequest,
    service: Annotated[ResearchServiceProtocol, Depends(get_research_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> ResearchEnvelope:
    """评估 5/10/15 年长期投资价值、7 大核心支柱与结构化论文破裂监控条件。"""
    user_id = _extract_user_id(user)
    return await service.get_long_term_analysis(request=req, user_id=user_id)


# -----------------------------------------------------------------------------
# 7. F8: 投资组合配置优化 (portfolio)
# -----------------------------------------------------------------------------


@router.post(
    "/portfolio",
    response_model=ResearchEnvelope,
    status_code=status.HTTP_200_OK,
    summary="执行投资组合配置优化建议",
)
async def generate_portfolio_allocation(
    req: PortfolioRequest,
    service: Annotated[ResearchServiceProtocol, Depends(get_research_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> ResearchEnvelope:
    """基于约束优化算法与风险目标，输出满足绝对权重守恒的资产配置与现金建议。"""
    user_id = _extract_user_id(user)
    return await service.generate_portfolio_allocation(request=req, user_id=user_id)
