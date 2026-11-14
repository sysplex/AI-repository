"""M5 AI 核心框架服务门面 (AIService)（T07），`CONTRACTS.md §4`。

提供端到端 AI 分析编排服务：
1. 规范化事实快照并基于 SHA-256 哈希去重持久化；
2. 计算全局确定性缓存键 `cache_key`；
3. 智能多维快照缓存查询（命中缓存零费用、零配额消耗、允许穿透熔断器）；
4. 缓存未命中时依次执行：预算熔断检查 -> 用户配额检查 -> 提示词渲染 ->
   LLM 调用 -> Schema 校验与单次反馈重试 -> 数字溯源反编造校验 ->
   配额与用量原子记账 -> 持久化 AI 报告记录；
5. 错误处理与失败报告状态归档。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    String,
    column,
    insert,
    select,
    table,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import get_clock
from app.core.errors import NotFound
from app.core.logging import get_logger
from app.modules.ai.adapters.mock import MockLLMClient
from app.modules.ai.circuit_breaker import BudgetCircuitBreaker
from app.modules.ai.models import AIReport
from app.modules.ai.ports import (
    LLMClient,
    PromptRegistryProtocol,
    QuotaServiceProtocol,
)
from app.modules.ai.prompts import (
    PromptTemplate,
    default_prompt_registry,
)
from app.modules.ai.quota import QuotaService
from app.modules.ai.retry import RetryableLLMCaller
from app.modules.ai.schemas import (
    AIPromptInfo,
    AIReportResponse,
    AnalysisReport,
    QuotaStatus,
)
from app.modules.ai.tracing import FactTracingEngine

__all__ = [
    "AIService",
    "data_snapshots_table",
    "get_budget_circuit_breaker",
    "set_budget_circuit_breaker",
]

logger = get_logger(__name__)

# 全局共享预算熔断器单例
_global_circuit_breaker = BudgetCircuitBreaker()


def get_budget_circuit_breaker() -> BudgetCircuitBreaker:
    """获取系统全局预算熔断器实例。"""
    return _global_circuit_breaker


def set_budget_circuit_breaker(breaker: BudgetCircuitBreaker) -> None:
    """设置系统全局预算熔断器实例（测试与配置注入）。"""
    global _global_circuit_breaker
    _global_circuit_breaker = breaker


# SQLAlchemy Core 表定义：data_snapshots（共享市场数据事实快照表）
data_snapshots_table = table(
    "data_snapshots",
    column("content_hash", String),
    column("symbol", String),
    column("as_of", DateTime),
    column("scope", JSON),
    column("facts", JSON),
    column("missing_fields", JSON),
    column("created_at", DateTime),
)


class AIService:
    """AI 核心框架编排门面服务。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        llm_client: LLMClient | None = None,
        prompt_registry: PromptRegistryProtocol | None = None,
        quota_service: QuotaServiceProtocol | None = None,
        circuit_breaker: BudgetCircuitBreaker | None = None,
        fact_tracing_engine: FactTracingEngine | None = None,
    ) -> None:
        self._session = session
        self._llm_client: LLMClient = llm_client if llm_client is not None else MockLLMClient()
        self._prompt_registry: PromptRegistryProtocol = (
            prompt_registry if prompt_registry is not None else default_prompt_registry
        )
        self._quota_service: QuotaServiceProtocol = (
            quota_service if quota_service is not None else QuotaService(session=session)
        )
        self._circuit_breaker: BudgetCircuitBreaker = (
            circuit_breaker if circuit_breaker is not None else get_budget_circuit_breaker()
        )
        self._fact_tracing_engine: FactTracingEngine = (
            fact_tracing_engine if fact_tracing_engine is not None else FactTracingEngine()
        )

    # -------------------------------------------------------------------------
    # 哈希与缓存键计算工具
    # -------------------------------------------------------------------------

    @staticmethod
    def compute_content_hash(facts: dict[str, Any]) -> str:
        """基于标准排序 JSON 字符串计算输入事实快照的 SHA-256 哈希值。"""
        serialized = json.dumps(facts, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_cache_key(
        use_case: str,
        prompt_version: str,
        content_hash: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """计算 AI 分析结果确定性缓存键。

        格式：sha256(use_case:prompt_version:content_hash:sorted_params)
        """
        sorted_params = json.dumps(params or {}, sort_keys=True, ensure_ascii=False, default=str)
        raw_key = f"{use_case.strip()}:{prompt_version.strip()}:{content_hash}:{sorted_params}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    # -------------------------------------------------------------------------
    # 核心分析生成管线 (run)
    # -------------------------------------------------------------------------

    async def run(
        self,
        use_case: str,
        facts: dict[str, Any],
        params: dict[str, Any] | None = None,
        user_id: UUID | None = None,
        as_of: datetime | None = None,
        prompt_version: str | None = None,
    ) -> AnalysisReport:
        """执行端到端 AI 分析。

        1. 规范化 facts 字典并生成 SHA-256 哈希，持久化/复用 data_snapshots 表；
        2. 计算 cache_key，若命中缓存则直接返回（无成本、不扣配额、穿透熔断器）；
        3. 检查预算熔断与用户当日调用配额；
        4. 加载提示词模板并渲染（含防提示注入隔离）；
        5. 调用 LLMClient 生成；
        6. Schema 校验（失败自动重试 1 次）；
        7. 数字溯源校验（杜绝编造幻觉）；
        8. 扣减配额并记账更新 ai_usage；
        9. 保存报告记录至 ai_reports，返回 AnalysisReport。
        """
        use_case = use_case.strip()
        params = params or {}
        now = get_clock().now()

        # 1. 持久化/复用数据快照
        content_hash = await self._ensure_data_snapshot(facts, as_of=as_of)

        # 2. 解析提示词模板与生效版本
        prompt_tmpl: PromptTemplate = self._prompt_registry.get(use_case, version=prompt_version)
        resolved_version = prompt_tmpl.version

        # 3. 计算缓存键并查询历史报告
        cache_key = self.compute_cache_key(
            use_case=use_case,
            prompt_version=resolved_version,
            content_hash=content_hash,
            params=params,
        )
        cached_report = await self._lookup_cache(cache_key)
        if cached_report is not None:
            logger.info(
                "AI analysis cache HIT for use_case={use_case}, cache_key={key}",
                use_case=use_case,
                key=cache_key,
            )
            # 缓存命中：穿透放行熔断检查，不扣配额，零成本
            self._circuit_breaker.check_budget(cached=True)
            return AnalysisReport(
                id=cached_report.id,
                use_case=cached_report.use_case,
                payload=cached_report.payload,
                cached=True,
                data_snapshot_id=cached_report.data_snapshot_id,
                prompt_version=cached_report.prompt_version,
                model=cached_report.model,
                cost_usd=Decimal("0.000000"),
                created_at=cached_report.created_at,
            )

        # 4. 缓存未命中：前置风控拦截检查
        # 4.1 检查预算熔断器
        self._circuit_breaker.check_budget(cached=False)

        # 4.2 检查用户当日配额
        if user_id is not None:
            await self._quota_service.check(user_id, raise_on_exceeded=True)

        # 5. 渲染提示词（PromptTemplate.render 内部自动执行 XML 沙箱防注入封装）
        rendered_system, rendered_user = prompt_tmpl.render(
            facts=facts,
            params=params,
        )

        # 6. LLM 生成与 Schema 校验（含 1 次重试）
        try:
            caller = RetryableLLMCaller(client=self._llm_client)
            validated_res = await caller.call(
                system=rendered_system,
                user=rendered_user,
                output_schema=prompt_tmpl.output_schema or None,
            )

            # 7. 数字溯源校验（docs/08 §4.3 防编造防御）
            parsed_payload = validated_res.parsed_json or {}
            self._fact_tracing_engine.verify_or_raise(
                payload=parsed_payload,
                facts=facts,
            )

            # 8. 扣减配额与记账更新
            if user_id is not None:
                await self._quota_service.consume(
                    user_id=user_id,
                    tokens_in=validated_res.input_tokens,
                    tokens_out=validated_res.output_tokens,
                    cost_usd=validated_res.cost_usd,
                )
            self._circuit_breaker.record_cost(validated_res.cost_usd)

            # 9. 落库持久化成功报告
            report_id = uuid.uuid4()
            report = AIReport(
                id=report_id,
                user_id=user_id if user_id is not None else uuid.uuid4(),
                use_case=use_case,
                params=params,
                cache_key=cache_key,
                data_snapshot_id=content_hash,
                prompt_version=resolved_version,
                model=validated_res.model,
                payload=parsed_payload,
                cost_usd=validated_res.cost_usd,
                status="success",
                error_message=None,
                created_at=now,
            )
            self._session.add(report)
            await self._session.flush()

            logger.info(
                "AI analysis succeeded: report_id={id}, use_case={uc}, cost=${cost}",
                id=report_id,
                uc=use_case,
                cost=validated_res.cost_usd,
            )
            return AnalysisReport(
                id=report.id,
                use_case=report.use_case,
                payload=report.payload,
                cached=False,
                data_snapshot_id=content_hash,
                prompt_version=report.prompt_version,
                model=report.model,
                cost_usd=report.cost_usd,
                created_at=report.created_at,
            )

        except Exception as exc:
            # 记录失败状态报告并重抛业务异常
            logger.error(
                "AI analysis pipeline failed for use_case={uc}: {err}",
                uc=use_case,
                err=str(exc),
            )
            if user_id is not None:
                failed_report = AIReport(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    use_case=use_case,
                    params=params,
                    cache_key=cache_key,
                    data_snapshot_id=content_hash,
                    prompt_version=resolved_version,
                    model=getattr(self._llm_client, "name", "unknown"),
                    payload={},
                    cost_usd=Decimal("0.000000"),
                    status="failed",
                    error_message=str(exc),
                    created_at=now,
                )
                self._session.add(failed_report)
                try:
                    await self._session.flush()
                except Exception as flush_err:
                    logger.debug("Failed to flush failed report record: {err}", err=flush_err)
            raise exc

    # -------------------------------------------------------------------------
    # 报告与快照查询
    # -------------------------------------------------------------------------

    async def get_report(
        self,
        report_id: UUID,
        *,
        user_id: UUID | None = None,
    ) -> AIReportResponse:
        """获取指定 ID 的 AI 分析报告，支持多租户隔离。"""
        stmt = select(AIReport).where(AIReport.id == report_id)
        if user_id is not None:
            stmt = stmt.where(AIReport.user_id == user_id)
        res = await self._session.execute(stmt)
        report = res.scalar_one_or_none()
        if report is None:
            raise NotFound("AI 报告不存在或无权访问")
        return AIReportResponse.model_validate(report)

    async def list_reports(
        self,
        user_id: UUID,
        *,
        use_case: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AIReportResponse]:
        """按用户列出历史报告列表。"""
        stmt = (
            select(AIReport)
            .where(AIReport.user_id == user_id)
            .order_by(AIReport.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if use_case is not None:
            stmt = stmt.where(AIReport.use_case == use_case.strip())
        res = await self._session.execute(stmt)
        reports = res.scalars().all()
        return [AIReportResponse.model_validate(r) for r in reports]

    async def get_snapshot(self, content_hash: str) -> dict[str, Any]:
        """获取指定 SHA-256 哈希的事实快照数据。"""
        stmt = select(
            data_snapshots_table.c.content_hash,
            data_snapshots_table.c.symbol,
            data_snapshots_table.c.as_of,
            data_snapshots_table.c.scope,
            data_snapshots_table.c.facts,
            data_snapshots_table.c.missing_fields,
            data_snapshots_table.c.created_at,
        ).where(data_snapshots_table.c.content_hash == content_hash)
        res = await self._session.execute(stmt)
        row = res.one_or_none()
        if row is None:
            raise NotFound(f"未找到哈希为 '{content_hash}' 的事实快照")
        return {
            "content_hash": row[0],
            "symbol": row[1],
            "as_of": row[2],
            "scope": row[3],
            "facts": row[4],
            "missing_fields": row[5],
            "created_at": row[6],
        }

    async def get_quota_status(self, user_id: UUID) -> QuotaStatus:
        """查询用户当日配额状态。"""
        return await self._quota_service.check(user_id, raise_on_exceeded=False)

    def list_prompts(self) -> list[AIPromptInfo]:
        """列出当前系统所有可用提示词模板。"""
        list_fn = getattr(self._prompt_registry, "list_templates", None)
        if callable(list_fn):
            templates: list[Any] = list_fn()
            return [t.to_info() for t in templates]
        return []

    # -------------------------------------------------------------------------
    # 内部辅助方法
    # -------------------------------------------------------------------------

    async def _ensure_data_snapshot(
        self,
        facts: dict[str, Any],
        *,
        as_of: datetime | None = None,
    ) -> str:
        """确保事实快照存在于 data_snapshots 表中，返回 content_hash。"""
        content_hash = self.compute_content_hash(facts)
        now = get_clock().now()
        snapshot_as_of = as_of or now
        symbol = str(facts.get("symbol", "MARKET"))
        scope = list(facts.keys())
        missing_fields = list(facts.get("missing_fields", []))

        stmt = select(data_snapshots_table.c.content_hash).where(
            data_snapshots_table.c.content_hash == content_hash
        )
        res = await self._session.execute(stmt)
        if res.scalar_one_or_none() is None:
            ins_stmt = insert(data_snapshots_table).values(
                content_hash=content_hash,
                symbol=symbol,
                as_of=snapshot_as_of,
                scope=scope,
                facts=facts,
                missing_fields=missing_fields,
                created_at=now,
            )
            try:
                await self._session.execute(ins_stmt)
                await self._session.flush()
            except Exception as ins_err:
                # 并发插入冲突时忽略
                logger.debug("Concurrent snapshot insert caught and ignored: {err}", err=ins_err)
        return content_hash

    async def _lookup_cache(self, cache_key: str) -> AIReport | None:
        """查询是否存在对应 cache_key 的成功历史报告。"""
        stmt = (
            select(AIReport)
            .where(
                AIReport.cache_key == cache_key,
                AIReport.status == "success",
            )
            .order_by(AIReport.created_at.desc())
            .limit(1)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()
