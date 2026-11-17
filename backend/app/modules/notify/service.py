"""智能提醒与论文破裂监控核心服务（M10-T03）。"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import record_alert_evaluated, record_alert_triggered
from app.modules.notify.dispatcher import NotificationDispatcher
from app.modules.notify.enums import (
    AlertStatus,
    AlertType,
    ComparisonOperator,
)
from app.modules.notify.evaluators import EvaluationResult, get_evaluator
from app.modules.notify.evaluators.thesis_breaker_evaluator import _normalize_operator
from app.modules.notify.models import Alert, AlertHistory, NotificationChannel
from app.modules.notify.ports import NotificationMessage
from app.modules.notify.schemas import (
    AlertCreate,
    AlertHistoryRead,
    AlertRead,
    AlertUpdate,
    EarningsDateCondition,
    NotificationChannelCreate,
    NotificationChannelRead,
    NotificationChannelUpdate,
    PriceCondition,
    TechnicalSignalCondition,
    ThesisBreakerCondition,
)

__all__ = ["AlertService"]

logger = get_logger("notify.service")


class AlertService:
    """智能提醒规则生命周期管理与触发评估引擎服务。"""

    def __init__(
        self,
        session: AsyncSession | None = None,
        dispatcher: NotificationDispatcher | None = None,
    ) -> None:
        self._session = session
        self._dispatcher = dispatcher or NotificationDispatcher()

    def _get_session(self, session: AsyncSession | None) -> AsyncSession:
        sess = session or self._session
        if sess is None:
            raise ValueError("AsyncSession 必须传入或在 AlertService 构造时初始化。")
        return sess

    # ==========================================
    # 1. 提醒规则 CRUD
    # ==========================================

    async def create_alert(
        self,
        user_id: uuid.UUID,
        data: AlertCreate,
        session: AsyncSession | None = None,
    ) -> AlertRead:
        """创建一条新的提醒规则，严格根据 alert_type 校验 conditions。"""
        sess = self._get_session(session)

        # 校验 conditions 格式规范
        conditions_data = data.conditions
        if data.alert_type == AlertType.PRICE:
            PriceCondition.model_validate(conditions_data)
        elif data.alert_type == AlertType.TECHNICAL_SIGNAL:
            TechnicalSignalCondition.model_validate(conditions_data)
        elif data.alert_type == AlertType.EARNINGS_DATE:
            EarningsDateCondition.model_validate(conditions_data)
        elif data.alert_type == AlertType.THESIS_BREAKER:
            ThesisBreakerCondition.model_validate(conditions_data)

        alert = Alert(
            user_id=user_id,
            symbol=data.symbol,
            alert_type=data.alert_type.value,
            title=data.title,
            conditions=conditions_data,
            channel_ids=list(data.channel_ids or []),
            status=AlertStatus.ACTIVE.value,
            trigger_count=0,
            cooldown_minutes=data.cooldown_minutes,
        )
        sess.add(alert)
        await sess.commit()
        await sess.refresh(alert)
        logger.info(
            "alert_created",
            alert_id=str(alert.id),
            user_id=str(user_id),
            alert_type=alert.alert_type,
            symbol=alert.symbol,
        )
        return AlertRead.model_validate(alert)

    async def get_alert(
        self,
        user_id: uuid.UUID,
        alert_id: uuid.UUID,
        session: AsyncSession | None = None,
    ) -> AlertRead | None:
        """根据 ID 加载提醒规则并验证租户隔离。"""
        sess = self._get_session(session)
        stmt = select(Alert).where(Alert.id == alert_id, Alert.user_id == user_id)
        res = await sess.execute(stmt)
        alert = res.scalar_one_or_none()
        if not alert:
            return None
        return AlertRead.model_validate(alert)

    async def list_alerts(
        self,
        user_id: uuid.UUID,
        status: AlertStatus | str | None = None,
        symbol: str | None = None,
        alert_type: AlertType | str | None = None,
        limit: int = 50,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> list[AlertRead]:
        """按条件过滤查询用户的提醒规则列表。"""
        sess = self._get_session(session)
        stmt = select(Alert).where(Alert.user_id == user_id)

        if status:
            val = status.value if isinstance(status, AlertStatus) else str(status)
            stmt = stmt.where(Alert.status == val)
        if symbol:
            stmt = stmt.where(Alert.symbol == symbol.strip().upper())
        if alert_type:
            val = alert_type.value if isinstance(alert_type, AlertType) else str(alert_type)
            stmt = stmt.where(Alert.alert_type == val)

        stmt = stmt.order_by(Alert.created_at.desc()).limit(limit).offset(offset)
        res = await sess.execute(stmt)
        return [AlertRead.model_validate(a) for a in res.scalars().all()]

    async def update_alert(
        self,
        user_id: uuid.UUID,
        alert_id: uuid.UUID,
        data: AlertUpdate,
        session: AsyncSession | None = None,
    ) -> AlertRead | None:
        """更新提醒规则属性。"""
        sess = self._get_session(session)
        stmt = select(Alert).where(Alert.id == alert_id, Alert.user_id == user_id)
        res = await sess.execute(stmt)
        alert = res.scalar_one_or_none()
        if not alert:
            return None

        if data.title is not None:
            alert.title = data.title
        if data.conditions is not None:
            alert.conditions = data.conditions
        if data.channel_ids is not None:
            alert.channel_ids = list(data.channel_ids)
        if data.status is not None:
            alert.status = (
                data.status.value if isinstance(data.status, AlertStatus) else str(data.status)
            )
        if data.cooldown_minutes is not None:
            alert.cooldown_minutes = data.cooldown_minutes

        alert.updated_at = datetime.now(UTC)
        await sess.commit()
        await sess.refresh(alert)
        return AlertRead.model_validate(alert)

    async def delete_alert(
        self,
        user_id: uuid.UUID,
        alert_id: uuid.UUID,
        session: AsyncSession | None = None,
    ) -> bool:
        """删除提醒规则。"""
        sess = self._get_session(session)
        stmt = select(Alert).where(Alert.id == alert_id, Alert.user_id == user_id)
        res = await sess.execute(stmt)
        alert = res.scalar_one_or_none()
        if not alert:
            return False

        await sess.delete(alert)
        await sess.commit()
        logger.info("alert_deleted", alert_id=str(alert_id), user_id=str(user_id))
        return True

    # ==========================================
    # 2. 批量将 M7 论文破裂项转为监控规则
    # ==========================================

    async def batch_create_thesis_breakers(
        self,
        user_id: uuid.UUID,
        symbol: str,
        breakers: Sequence[dict[str, Any] | Any],
        channel_ids: list[str] | None = None,
        cooldown_minutes: int = 1440,
        session: AsyncSession | None = None,
    ) -> list[AlertRead]:
        """将 M7 产出的投资论文破裂条件批量生成为 thesis_breaker 监控规则。"""
        sess = self._get_session(session)
        created_alerts: list[Alert] = []
        sym = symbol.strip().upper()

        for item in breakers:
            if isinstance(item, dict):
                metric = item.get("metric", "")
                threshold_raw = item.get("threshold", "")
                cond_desc = item.get("condition") or item.get("description") or ""
                data_field = item.get("data_field")
                op_raw = item.get("operator")
            else:
                metric = getattr(item, "metric", "")
                threshold_raw = getattr(item, "threshold", "")
                cond_desc = (
                    getattr(item, "condition", None) or getattr(item, "description", None) or ""
                )
                data_field = getattr(item, "data_field", None)
                op_raw = getattr(item, "operator", None)

            # 解析 operator 与 threshold
            op = _normalize_operator(op_raw)
            threshold_val = threshold_raw
            if op is None and isinstance(threshold_raw, str):
                match = re.match(
                    r"^([<>!=]=?|[a-zA-Z]+)?\s*([+-]?\d+(?:\.\d+)?%?)$", threshold_raw.strip()
                )
                if match:
                    op_part, val_part = match.groups()
                    op = _normalize_operator(op_part)
                    threshold_val = val_part

            op_val = op.value if op else ComparisonOperator.LT.value
            title = f"[{sym}] 论文破裂监控 - {cond_desc or metric}"
            cond_dict: dict[str, Any] = {
                "metric": metric,
                "operator": op_val,
                "threshold": threshold_val,
                "description": cond_desc,
            }
            if data_field:
                cond_dict["data_field"] = data_field

            alert = Alert(
                user_id=user_id,
                symbol=sym,
                alert_type=AlertType.THESIS_BREAKER.value,
                title=title,
                conditions=cond_dict,
                channel_ids=list(channel_ids or []),
                status=AlertStatus.ACTIVE.value,
                trigger_count=0,
                cooldown_minutes=cooldown_minutes,
            )
            sess.add(alert)
            created_alerts.append(alert)

        await sess.commit()
        for a in created_alerts:
            await sess.refresh(a)

        logger.info(
            "thesis_breakers_batch_created",
            user_id=str(user_id),
            symbol=sym,
            count=len(created_alerts),
        )
        return [AlertRead.model_validate(a) for a in created_alerts]

    # ==========================================
    # 3. 通知渠道管理 CRUD
    # ==========================================

    async def create_channel(
        self,
        user_id: uuid.UUID,
        data: NotificationChannelCreate,
        session: AsyncSession | None = None,
    ) -> NotificationChannelRead:
        """创建通知渠道。"""
        sess = self._get_session(session)
        channel = NotificationChannel(
            user_id=user_id,
            channel_type=data.channel_type.value,
            name=data.name,
            config=data.config,
            is_enabled=data.is_enabled,
        )
        sess.add(channel)
        await sess.commit()
        await sess.refresh(channel)
        return NotificationChannelRead.model_validate(channel)

    async def list_channels(
        self,
        user_id: uuid.UUID,
        session: AsyncSession | None = None,
    ) -> list[NotificationChannelRead]:
        """获取用户的所有通知渠道配置。"""
        sess = self._get_session(session)
        stmt = (
            select(NotificationChannel)
            .where(NotificationChannel.user_id == user_id)
            .order_by(NotificationChannel.created_at.asc())
        )
        res = await sess.execute(stmt)
        return [NotificationChannelRead.model_validate(c) for c in res.scalars().all()]

    async def get_channel(
        self,
        user_id: uuid.UUID,
        channel_id: uuid.UUID,
        session: AsyncSession | None = None,
    ) -> NotificationChannelRead | None:
        """获取单个渠道。"""
        sess = self._get_session(session)
        stmt = select(NotificationChannel).where(
            NotificationChannel.id == channel_id,
            NotificationChannel.user_id == user_id,
        )
        res = await sess.execute(stmt)
        c = res.scalar_one_or_none()
        if not c:
            return None
        return NotificationChannelRead.model_validate(c)

    async def update_channel(
        self,
        user_id: uuid.UUID,
        channel_id: uuid.UUID,
        data: NotificationChannelUpdate,
        session: AsyncSession | None = None,
    ) -> NotificationChannelRead | None:
        """更新通知渠道。"""
        sess = self._get_session(session)
        stmt = select(NotificationChannel).where(
            NotificationChannel.id == channel_id,
            NotificationChannel.user_id == user_id,
        )
        res = await sess.execute(stmt)
        c = res.scalar_one_or_none()
        if not c:
            return None

        if data.name is not None:
            c.name = data.name
        if data.config is not None:
            c.config = data.config
        if data.is_enabled is not None:
            c.is_enabled = data.is_enabled

        c.updated_at = datetime.now(UTC)
        await sess.commit()
        await sess.refresh(c)
        return NotificationChannelRead.model_validate(c)

    async def delete_channel(
        self,
        user_id: uuid.UUID,
        channel_id: uuid.UUID,
        session: AsyncSession | None = None,
    ) -> bool:
        """删除通知渠道。"""
        sess = self._get_session(session)
        stmt = select(NotificationChannel).where(
            NotificationChannel.id == channel_id,
            NotificationChannel.user_id == user_id,
        )
        res = await sess.execute(stmt)
        c = res.scalar_one_or_none()
        if not c:
            return False

        await sess.delete(c)
        await sess.commit()
        return True

    async def test_channel(
        self,
        user_id: uuid.UUID,
        channel_id: uuid.UUID,
        session: AsyncSession | None = None,
    ) -> dict[str, Any] | None:
        """测试指定渠道的连通性。"""
        sess = self._get_session(session)
        channel = await self.get_channel(user_id, channel_id, session=sess)
        if not channel:
            return None

        msg = NotificationMessage(
            title="StockPilot 渠道连通性测试",
            body=f"这是一条来自 StockPilot 系统的测试消息。渠道 [{channel.name}] 已成功连通！",
            alert_type="test",
            symbol=None,
            meta={"test": True, "channel_id": str(channel_id)},
        )
        results = await self._dispatcher.dispatch(
            user_id=user_id,
            message=msg,
            channel_ids=[str(channel_id)],
            session=sess,
        )
        result_dicts = [r.to_dict() for r in results]
        is_success = any(r.success for r in results) if results else False
        return {
            "channel_id": str(channel_id),
            "channel_name": channel.name,
            "success": is_success,
            "results": result_dicts,
        }

    # ==========================================
    # 4. 扫描评估与触发分发引擎
    # ==========================================

    async def evaluate_alerts(
        self,
        *,
        market_context: dict[str, Any],
        user_id: uuid.UUID | None = None,
        as_of: datetime | None = None,
        session: AsyncSession | None = None,
    ) -> list[tuple[Alert, EvaluationResult]]:
        """全量或针对单用户的提醒规则扫描求值引擎。

        Args:
            market_context: 包含行情、指标、基本面等快照字典。
                            支持形如 {"AAPL": {"current_price": 230, ...}} 的标的字典，
                            或针对单一标的的平铺上下文字典。
            user_id: 可选用户过滤；若为 None 则扫描全量有效规则。
            as_of: 评估时间戳，默认为 UTC 当前时间。
            session: 数据库会话。

        Returns:
            list[tuple[Alert, EvaluationResult]]: 触发警报的实体与判定结果列表。
        """
        sess = self._get_session(session)
        now_dt = as_of or datetime.now(UTC)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=UTC)

        stmt = select(Alert).where(
            Alert.status.in_([AlertStatus.ACTIVE.value, AlertStatus.COOLDOWN.value])
        )
        if user_id:
            stmt = stmt.where(Alert.user_id == user_id)

        res = await sess.execute(stmt)
        candidate_alerts = list(res.scalars().all())
        if candidate_alerts:
            record_alert_evaluated(len(candidate_alerts))

        triggered_results: list[tuple[Alert, EvaluationResult]] = []

        for alert in candidate_alerts:
            # 1. 冷却期判定与恢复
            if alert.status == AlertStatus.COOLDOWN.value:
                cooldown_delta = timedelta(minutes=alert.cooldown_minutes or 1440)
                last_trig = alert.last_triggered_at
                if last_trig:
                    if last_trig.tzinfo is None:
                        last_trig = last_trig.replace(tzinfo=UTC)
                    if now_dt >= last_trig + cooldown_delta:
                        # 冷却期已过，恢复为 ACTIVE
                        alert.status = AlertStatus.ACTIVE.value
                    else:
                        # 仍处在冷却保护中，抑制重复触发
                        continue
                else:
                    alert.status = AlertStatus.ACTIVE.value

            # 2. 匹配标的评估上下文
            sym = alert.symbol
            sym_ctx: dict[str, Any] = {}
            if sym and sym in market_context and isinstance(market_context[sym], dict):
                sym_ctx = dict(market_context[sym])
            elif (
                sym
                and sym.upper() in market_context
                and isinstance(market_context[sym.upper()], dict)
            ):
                sym_ctx = dict(market_context[sym.upper()])
            elif (
                sym
                and sym.lower() in market_context
                and isinstance(market_context[sym.lower()], dict)
            ):
                sym_ctx = dict(market_context[sym.lower()])
            else:
                # 尝试直接使用 market_context（当外层只传入了单一标的行情快照时）
                sym_ctx = dict(market_context)

            if "symbol" not in sym_ctx and sym:
                sym_ctx["symbol"] = sym
            if "as_of_date" not in sym_ctx:
                sym_ctx["as_of_date"] = now_dt.date()

            # 3. 获取对应的评估器
            evaluator = get_evaluator(alert.alert_type)
            if not evaluator:
                continue

            # 4. 执行评估
            eval_res = evaluator.evaluate(alert, sym_ctx)
            if not eval_res.triggered:
                continue

            record_alert_triggered(alert.alert_type)

            # 5. 触发后更新状态并派发
            alert.last_triggered_at = now_dt
            alert.trigger_count = (alert.trigger_count or 0) + 1
            alert.status = AlertStatus.COOLDOWN.value
            alert.updated_at = now_dt

            # 组装通知消息
            message = NotificationMessage(
                title=f"【StockPilot 告警】{alert.title}",
                body=eval_res.message,
                alert_id=alert.id,
                symbol=alert.symbol,
                alert_type=alert.alert_type,
                triggered_value=eval_res.triggered_value,
            )

            # 异步非阻塞派发
            try:
                await self._dispatcher.dispatch(
                    user_id=alert.user_id,
                    message=message,
                    channel_ids=alert.channel_ids,
                    session=sess,
                )
            except Exception as e:
                logger.error(
                    "dispatch_failed_silently",
                    alert_id=str(alert.id),
                    error=str(e),
                )

            triggered_results.append((alert, eval_res))

        await sess.commit()
        logger.info(
            "alerts_evaluated",
            candidates_count=len(candidate_alerts),
            triggered_count=len(triggered_results),
        )
        return triggered_results

    # ==========================================
    # 5. 触发历史审计流水查询
    # ==========================================

    async def list_history(
        self,
        user_id: uuid.UUID,
        alert_id: uuid.UUID | None = None,
        symbol: str | None = None,
        limit: int = 50,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> list[AlertHistoryRead]:
        """查询提醒触发历史记录。"""
        sess = self._get_session(session)
        stmt = select(AlertHistory).where(AlertHistory.user_id == user_id)

        if alert_id:
            stmt = stmt.where(AlertHistory.alert_id == alert_id)
        if symbol:
            stmt = stmt.where(AlertHistory.symbol == symbol.strip().upper())

        stmt = stmt.order_by(AlertHistory.created_at.desc()).limit(limit).offset(offset)
        res = await sess.execute(stmt)
        return [AlertHistoryRead.model_validate(h) for h in res.scalars().all()]
