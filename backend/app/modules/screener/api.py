"""M8 筛选器、主题自选与股票池 REST API 路由实现（T06），`CONTRACTS.md §5`。

暴露核心 REST API 端点：
- `/api/v1/universes`：查询股票池列表；
- `/api/v1/screener/*`：筛选任务创建、运行结果查询与历史列表；
- `/api/v1/themes/*`：热门主题清单、主题详情与 AI 主题卡片生成；
- `/api/v1/watchlists/*`：用户自选清单增删改查、标的管理与投研一键导出。

安全契约：
- 全面执行 HARD-01 鉴权（未登录统一返回 401 UNAUTHENTICATED）；
- 严格遵循多租户隔离约束，严禁越权操作。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import Unauthenticated, ValidationFailed
from app.core.logging import get_logger
from app.modules.screener.ports import ScreenerServiceProtocol
from app.modules.screener.schemas import (
    ExportToResearchRequest,
    ScreenerRunCreate,
    ScreenerRunRead,
    ThemeCardsResponse,
    ThemeInfo,
    UniverseInfo,
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemRead,
    WatchlistItemUpdate,
    WatchlistRead,
    WatchlistUpdate,
)

logger = get_logger("screener.api")

__all__ = [
    "add_watchlist_item",
    "create_screener_run",
    "create_watchlist",
    "delete_watchlist",
    "export_screener_results",
    "export_watchlist_to_research",
    "generate_theme_cards",
    "get_current_user",
    "get_screener_run",
    "get_screener_service",
    "get_theme",
    "get_watchlist",
    "list_screener_runs",
    "list_themes",
    "list_universes",
    "list_watchlists",
    "remove_watchlist_item",
    "router",
    "set_screener_service",
    "set_screener_service_provider",
    "update_watchlist",
    "update_watchlist_item",
]

router = APIRouter()

# 全局或自定义服务实例/工厂（用于依赖注入与测试 Mock 隔离）
_screener_service: ScreenerServiceProtocol | None = None
_screener_service_provider: Callable[[AsyncSession], ScreenerServiceProtocol] | None = None


def set_screener_service(service: ScreenerServiceProtocol | None) -> None:
    """设置全局 ScreenerService 实例（用于单元测试快速注入）。"""
    global _screener_service
    _screener_service = service


def set_screener_service_provider(
    provider: Callable[[AsyncSession], ScreenerServiceProtocol] | None,
) -> None:
    """设置 ScreenerService 依赖工厂（用于 FastAPI 运行期会话注入）。"""
    global _screener_service_provider
    _screener_service_provider = provider


def get_screener_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScreenerServiceProtocol:
    """FastAPI 依赖注入提供器。"""
    if _screener_service is not None:
        return _screener_service
    if _screener_service_provider is not None:
        return _screener_service_provider(session)
    raise RuntimeError("ScreenerService has not been configured in app router")


def get_current_user(request: Request) -> Any:
    """从 ASGI 请求上下文中提取已验证的当前用户（HARD-01）。"""
    user = getattr(request.state, "user", None)
    if user is None:
        raise Unauthenticated("需要认证才能访问筛选器服务")
    return user


def _extract_user_id(user: Any) -> UUID:
    """安全解析用户唯一标识 UUID。"""
    raw_id = getattr(user, "id", None)
    if raw_id is None and isinstance(user, dict):
        raw_id = user.get("id")
    if isinstance(raw_id, UUID):
        return raw_id
    if isinstance(raw_id, str):
        try:
            return UUID(raw_id)
        except (ValueError, TypeError) as exc:
            raise Unauthenticated(f"无效的用户 ID 格式: {raw_id}") from exc
    raise Unauthenticated("无效的用户认证凭据")


# ---------------------------------------------------------------------------
# 股票池 (Universes)
# ---------------------------------------------------------------------------


@router.get(
    "/universes",
    response_model=list[UniverseInfo],
    summary="获取可选股票池列表",
    tags=["screener"],
)
def list_universes(
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> list[UniverseInfo]:
    """返回系统支持的股票池（标普500、纳指100、道指30、自定义）。"""
    return service.list_universes()


# ---------------------------------------------------------------------------
# 策略筛选任务 (Screener Runs)
# ---------------------------------------------------------------------------


@router.post(
    "/screener/runs",
    response_model=ScreenerRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建并启动策略筛选任务",
    tags=["screener"],
)
async def create_screener_run(
    request: ScreenerRunCreate,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> ScreenerRunRead:
    """提交并执行全股票池策略量化筛选任务。"""
    user_id = _extract_user_id(current_user)
    return await service.run_screener(user_id=user_id, request=request)


@router.get(
    "/screener/runs/{id}",
    response_model=ScreenerRunRead,
    summary="获取指定筛选任务记录与排名结果",
    tags=["screener"],
)
async def get_screener_run(
    id: UUID,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> ScreenerRunRead:
    """查询筛选任务详情、执行进度、得分排名及指标快照。"""
    user_id = _extract_user_id(current_user)
    return await service.get_screener_run(run_id=id, user_id=user_id)


@router.get(
    "/screener/runs",
    response_model=list[ScreenerRunRead],
    summary="获取当前用户的历史筛选任务",
    tags=["screener"],
)
async def list_screener_runs(
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ScreenerRunRead]:
    """分页查询当前租户的历史策略筛选记录。"""
    user_id = _extract_user_id(current_user)
    return await service.list_runs(user_id=user_id, limit=limit, offset=offset)


@router.post(
    "/screener/export",
    response_model=dict[str, Any],
    summary="一键导出标的到研究/对比模块",
    tags=["screener"],
)
def export_screener_results(
    request: ExportToResearchRequest,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> dict[str, Any]:
    """将选定标的一键构造为跳转至研报或横向对比的数据载荷。"""
    return service.export_to_research(request)


# ---------------------------------------------------------------------------
# F9 热门主题与 AI 主题卡片 (Themes)
# ---------------------------------------------------------------------------


@router.get(
    "/themes",
    response_model=list[ThemeInfo],
    summary="获取系统预设热门主题清单",
    tags=["themes"],
)
def list_themes(
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> list[ThemeInfo]:
    """获取系统预设的热门主题投资库（F9）。"""
    return service.list_themes()


@router.get(
    "/themes/{id}",
    response_model=ThemeInfo,
    summary="获取指定主题详情与成分标的",
    tags=["themes"],
)
def get_theme(
    id: str,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> ThemeInfo:
    """获取指定主题的成分标的明细与逻辑导语。"""
    return service.get_theme(id)


@router.post(
    "/themes/{id}/cards",
    response_model=ThemeCardsResponse,
    summary="生成指定主题成分股投研卡片（带事实溯源）",
    tags=["themes"],
)
async def generate_theme_cards(
    id: str,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> ThemeCardsResponse:
    """AI 生成指定主题的新手说明卡片（严格执行代码 facts 事实溯源）。"""
    user_id = _extract_user_id(current_user)
    return await service.generate_theme_cards(theme_id=id, user_id=user_id)


# ---------------------------------------------------------------------------
# 自选清单与关注标的 (Watchlists)
# ---------------------------------------------------------------------------


@router.get(
    "/watchlists",
    response_model=list[WatchlistRead],
    summary="获取当前用户所有自选清单",
    tags=["watchlists"],
)
async def list_watchlists(
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> list[WatchlistRead]:
    """获取当前用户的所有自选清单（含所包含标的）。"""
    user_id = _extract_user_id(current_user)
    return await service.list_watchlists(user_id=user_id)


@router.post(
    "/watchlists",
    response_model=WatchlistRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建新的自选清单",
    tags=["watchlists"],
)
async def create_watchlist(
    body: WatchlistCreate,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> WatchlistRead:
    """创建自选清单。"""
    user_id = _extract_user_id(current_user)
    return await service.create_watchlist(user_id=user_id, data=body)


@router.get(
    "/watchlists/{id}",
    response_model=WatchlistRead,
    summary="获取指定自选清单详情及全部标的",
    tags=["watchlists"],
)
async def get_watchlist(
    id: UUID,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> WatchlistRead:
    """获取指定自选清单详情。"""
    user_id = _extract_user_id(current_user)
    return await service.get_watchlist(watchlist_id=id, user_id=user_id)


@router.put(
    "/watchlists/{id}",
    response_model=WatchlistRead,
    summary="更新自选清单名称、说明或默认状态",
    tags=["watchlists"],
)
async def update_watchlist(
    id: UUID,
    body: WatchlistUpdate,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> WatchlistRead:
    """更新自选清单元数据。"""
    user_id = _extract_user_id(current_user)
    return await service.update_watchlist(watchlist_id=id, user_id=user_id, data=body)


@router.delete(
    "/watchlists/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除指定的自选清单",
    tags=["watchlists"],
)
async def delete_watchlist(
    id: UUID,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> Response:
    """删除自选清单（级联删除清单内所有关注标的）。"""
    user_id = _extract_user_id(current_user)
    await service.delete_watchlist(watchlist_id=id, user_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/watchlists/{id}/items",
    response_model=WatchlistItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="向自选清单添加关注标的",
    tags=["watchlists"],
)
async def add_watchlist_item(
    id: UUID,
    body: WatchlistItemCreate,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> WatchlistItemRead:
    """向自选清单添加关注标的，重复添加抛出 409 STATE_CONFLICT。"""
    user_id = _extract_user_id(current_user)
    return await service.add_watchlist_item(watchlist_id=id, user_id=user_id, data=body)


@router.put(
    "/watchlists/{id}/items/{item_id}",
    response_model=WatchlistItemRead,
    summary="更新自选标的备注、目标价或主题标签",
    tags=["watchlists"],
)
async def update_watchlist_item(
    id: UUID,
    item_id: UUID,
    body: WatchlistItemUpdate,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> WatchlistItemRead:
    """更新自选标的个性化备注与标签。"""
    user_id = _extract_user_id(current_user)
    return await service.update_watchlist_item(
        watchlist_id=id, item_id=item_id, user_id=user_id, data=body
    )


@router.delete(
    "/watchlists/{id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="从自选清单中移除关注标的",
    tags=["watchlists"],
)
async def remove_watchlist_item(
    id: UUID,
    item_id: UUID,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
) -> Response:
    """从自选清单中移除标的。"""
    user_id = _extract_user_id(current_user)
    await service.remove_watchlist_item(watchlist_id=id, item_id=item_id, user_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/watchlists/{id}/export",
    response_model=dict[str, Any],
    summary="一键导出自选清单标的到研究/对比模块",
    tags=["watchlists"],
)
async def export_watchlist_to_research(
    id: UUID,
    current_user: Annotated[Any, Depends(get_current_user)],
    service: Annotated[ScreenerServiceProtocol, Depends(get_screener_service)],
    target_action: Literal["compare", "portfolio", "deep_research"] = "compare",
) -> dict[str, Any]:
    """将指定自选清单中的前 10 只标的一键导出至横向对比或组合分析。"""
    user_id = _extract_user_id(current_user)
    wl = await service.get_watchlist(watchlist_id=id, user_id=user_id)
    symbols = [item.symbol for item in wl.items[:10]]
    if not symbols:
        raise ValidationFailed("自选清单为空，无法导出到研究模块")
    return service.export_to_research(
        ExportToResearchRequest(symbols=symbols, target_action=target_action)
    )
