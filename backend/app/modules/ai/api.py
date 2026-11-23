"""M5 AI 核心框架 REST API 端点（T07），`CONTRACTS.md §1 & §4` 与 `docs/05-api-spec.md §2.5`。

对外暴露完整的 `/api/v1/ai/*` 端点体系：
- `POST /api/v1/ai/analyze`：执行 AI 分析（去重快照、多维缓存、Schema 校验、数字溯源）
- `GET /api/v1/ai/reports/{report_id}`：获取单份 AI 报告（强制租户隔离）
- `GET /api/v1/ai/reports`：列出当前用户的历史报告列表
- `GET /api/v1/ai/reports/{report_id}/facts`：获取报告所引用的输入事实快照（审计可复盘）
- `GET /api/v1/ai/quota`：查询当前用户当日 AI 调用配额与使用状态
- `GET /api/v1/ai/prompts`：列出当前系统所有可用提示词模板
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import Unauthenticated
from app.core.logging import get_logger
from app.modules.ai.review_service import ReviewService
from app.modules.ai.schemas import (
    AIAnalyzeRequest,
    AIPromptInfo,
    AIReportResponse,
    AnalysisReport,
    DataSnapshotResponse,
    QuotaStatus,
    ReviewSummaryResponse,
    TestAPIKeyRequest,
    TestAPIKeyResponse,
)
from app.modules.ai.service import AIService

__all__ = [
    "get_ai_service",
    "get_current_user",
    "get_review_service",
    "reviews_router",
    "router",
    "set_ai_service_factory",
    "set_review_service_factory",
]

logger = get_logger(__name__)

router = APIRouter()

# 可覆盖的服务工厂（用于单元与集成测试注入 Mock）
_ai_service_factory: Callable[[AsyncSession], AIService] | None = None


def set_ai_service_factory(factory: Callable[[AsyncSession], AIService] | None) -> None:
    """设置 AIService 自定义构建工厂（测试辅助）。"""
    global _ai_service_factory
    _ai_service_factory = factory


def get_ai_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AIService:
    """AIService FastAPI 依赖注入提供器。"""
    if _ai_service_factory is not None:
        return _ai_service_factory(session)
    return AIService(session=session)


def get_current_user(request: Request) -> Any:
    """从 ASGI 请求上下文获取已通过鉴权的用户信息。"""
    user = getattr(request.state, "user", None)
    if user is None:
        raise Unauthenticated("需要认证才能访问 AI 服务")
    return user


# -----------------------------------------------------------------------------
# 1. AI 分析触发端点
# -----------------------------------------------------------------------------


@router.post(
    "/test-key",
    response_model=TestAPIKeyResponse,
    status_code=status.HTTP_200_OK,
    summary="测试第三方 AI API 密钥连通性",
)
async def test_api_key(
    req: TestAPIKeyRequest,
    user: Annotated[Any, Depends(get_current_user)],
) -> TestAPIKeyResponse:
    """即时在线测试用户提供的 API Key（连通性、模型可用性与额度）。"""
    del user  # 仅做鉴权拦截
    if req.provider == "mock":
        return TestAPIKeyResponse(valid=True, message="Mock 模拟服务可用", latency_ms=5)

    if req.provider == "google":
        model_name = req.model or "gemini-3.5-flash-lite"
        client = AIService.create_client(provider="google", api_key=req.api_key, model=model_name)
        try:
            res = await client.generate(
                system="You are a ping test.",
                user="Reply with 'PONG' and nothing else.",
                max_tokens=10,
                temperature=0.0,
            )
            msg = f"Google Gemini 连接成功！模型 [{model_name}] 响应正常，延迟 {res.latency_ms}ms"
            return TestAPIKeyResponse(
                valid=True,
                message=msg,
                latency_ms=res.latency_ms,
            )
        except Exception as exc:
            return TestAPIKeyResponse(
                valid=False,
                message=f"连接失败: {exc}",
                latency_ms=0,
            )

    return TestAPIKeyResponse(valid=False, message=f"暂不支持的提供商: {req.provider}")


@router.post(
    "/analyze",
    response_model=AnalysisReport,
    status_code=status.HTTP_200_OK,
    summary="执行 AI 分析",
)
async def analyze(
    req: AIAnalyzeRequest,
    service: Annotated[AIService, Depends(get_ai_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> AnalysisReport:
    """执行指定用例的 AI 分析。

    支持输入事实快照 SHA-256 去重持久化、全流程智能缓存、Schema 格式校验与数字溯源。
    """
    llm_client = None
    if req.ai_provider == "google" and req.google_api_key:
        llm_client = AIService.create_client(
            provider="google",
            api_key=req.google_api_key,
            model=req.google_model,
        )
    return await service.run(
        use_case=req.use_case,
        facts=req.facts,
        params=req.params,
        user_id=user.id,
        prompt_version=req.prompt_version,
        llm_client=llm_client,
    )


# -----------------------------------------------------------------------------
# 2. 报告管理与快照审计端点
# -----------------------------------------------------------------------------


@router.get(
    "/reports/{report_id}",
    response_model=AIReportResponse,
    status_code=status.HTTP_200_OK,
    summary="获取单份 AI 分析报告详情",
)
async def get_report(
    report_id: uuid.UUID,
    service: Annotated[AIService, Depends(get_ai_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> AIReportResponse:
    """获取指定 ID 的 AI 报告详情（强制租户数据隔离）。"""
    return await service.get_report(report_id, user_id=user.id)


@router.get(
    "/reports",
    response_model=list[AIReportResponse],
    status_code=status.HTTP_200_OK,
    summary="列出当前用户的 AI 报告历史",
)
async def list_reports(
    service: Annotated[AIService, Depends(get_ai_service)],
    user: Annotated[Any, Depends(get_current_user)],
    use_case: str | None = Query(None, description="按用例名称筛选"),
    limit: int = Query(50, ge=1, le=100, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
) -> list[AIReportResponse]:
    """分页列出当前登录用户的历史分析报告列表。"""
    return await service.list_reports(
        user_id=user.id,
        use_case=use_case,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/reports/{report_id}/facts",
    response_model=DataSnapshotResponse,
    status_code=status.HTTP_200_OK,
    summary="获取报告所引用的输入事实快照",
)
async def get_report_facts(
    report_id: uuid.UUID,
    service: Annotated[AIService, Depends(get_ai_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> DataSnapshotResponse:
    """获取指定报告所关联的数据事实快照（用于可信度验证与复盘审计）。"""
    report = await service.get_report(report_id, user_id=user.id)
    snapshot_data = await service.get_snapshot(report.data_snapshot_id)
    return DataSnapshotResponse.model_validate(snapshot_data)


# -----------------------------------------------------------------------------
# 3. 配额状态与提示词模板查询
# -----------------------------------------------------------------------------


@router.get(
    "/quota",
    response_model=QuotaStatus,
    status_code=status.HTTP_200_OK,
    summary="查询当前用户当日 AI 调用配额状态",
)
async def get_quota(
    service: Annotated[AIService, Depends(get_ai_service)],
    user: Annotated[Any, Depends(get_current_user)],
) -> QuotaStatus:
    """查询当前用户当日配额及已使用次数。"""
    return await service.get_quota_status(user.id)


@router.get(
    "/prompts",
    response_model=list[AIPromptInfo],
    status_code=status.HTTP_200_OK,
    summary="列出当前系统所有可用提示词模板",
)
async def list_prompts(
    service: Annotated[AIService, Depends(get_ai_service)],
    _user: Annotated[Any, Depends(get_current_user)],
) -> list[AIPromptInfo]:
    """获取当前系统活跃的提示词模板列表及输出 Schema。"""
    return service.list_prompts()


# -----------------------------------------------------------------------------
# 4. AI 建议事后表现复盘端点 (/api/v1/reviews/ai-outcomes)
# -----------------------------------------------------------------------------

reviews_router = APIRouter()

_review_service_factory: Callable[[AsyncSession], ReviewService] | None = None


def set_review_service_factory(factory: Callable[[AsyncSession], ReviewService] | None) -> None:
    """设置 ReviewService 自定义构建工厂（测试辅助）。"""
    global _review_service_factory
    _review_service_factory = factory


def get_review_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReviewService:
    """ReviewService 依赖注入提供器。"""
    if _review_service_factory is not None:
        return _review_service_factory(session)
    return ReviewService(session=session)


@reviews_router.get(
    "/ai-outcomes",
    response_model=ReviewSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="获取 AI 建议历史复盘统计与表现胜率聚合数据",
)
async def get_ai_outcomes(
    service: Annotated[ReviewService, Depends(get_review_service)],
    _user: Annotated[Any, Depends(get_current_user)],
    verdict: Annotated[
        str | None, Query(description="按结论过滤 (buy, holdable, avoid 等)")
    ] = None,
    symbol: Annotated[str | None, Query(description="按股票代码过滤")] = None,
    start_date: Annotated[date | None, Query(description="起始日期")] = None,
    end_date: Annotated[date | None, Query(description="结束日期")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewSummaryResponse:
    """获取 AI 建议历史复盘统计（5d/20d/60d 收益、相对 SPY 超额 Alpha、胜率及汇总）。"""
    return await service.get_outcomes_summary(
        verdict=verdict,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
