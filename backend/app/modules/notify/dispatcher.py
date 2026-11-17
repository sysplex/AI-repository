"""多通道通知分发网关与告警调度器（M10-T02），`CONTRACTS.md §1`。

包含：
- 渠道路由映射与动态多路并发分发
- 投递失败静默降级（绝不阻塞主流程）
- 审计流水记录至 `alert_history` 表
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.core.metrics import record_notification_dispatched
from app.modules.notify.adapters.email_notifier import EmailNotifier
from app.modules.notify.adapters.in_app_notifier import InAppNotifier
from app.modules.notify.adapters.webhook_notifier import WebhookNotifier
from app.modules.notify.enums import ChannelType, DeliveryStatus
from app.modules.notify.models import AlertHistory, NotificationChannel
from app.modules.notify.ports import BaseNotifier, NotificationMessage, NotificationResult

__all__ = ["NotificationDispatcher"]

_LOGGER = get_logger(__name__)


class NotificationDispatcher:
    """多通道通知调度分发服务。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        *,
        email_notifier: BaseNotifier | None = None,
        webhook_notifier: BaseNotifier | None = None,
        in_app_notifier: BaseNotifier | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._notifiers: dict[ChannelType, BaseNotifier] = {
            ChannelType.EMAIL: email_notifier or EmailNotifier(),
            ChannelType.WEBHOOK: webhook_notifier or WebhookNotifier(),
            ChannelType.IN_APP: in_app_notifier or InAppNotifier(),
        }

    def register_notifier(self, channel_type: ChannelType, notifier: BaseNotifier) -> None:
        """注册自定义渠道适配器（扩展点）。"""
        self._notifiers[channel_type] = notifier

    async def _resolve_channels(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        channel_ids: Sequence[str] | None,
    ) -> list[NotificationChannel]:
        """解析需要投递的渠道配置列表。"""
        stmt = select(NotificationChannel).where(
            NotificationChannel.user_id == user_id,
            NotificationChannel.is_enabled.is_(True),
        )

        if channel_ids:
            parsed_uuids: list[uuid.UUID] = []
            for cid in channel_ids:
                try:
                    parsed_uuids.append(uuid.UUID(cid))
                except (ValueError, TypeError):
                    continue
            if parsed_uuids:
                stmt = stmt.where(NotificationChannel.id.in_(parsed_uuids))

        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _record_history(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        message: NotificationMessage,
        results: list[NotificationResult],
    ) -> None:
        """记录警报触发与投递审计流水。"""
        if not message.alert_id:
            return

        success_count = sum(1 for r in results if r.success)
        if success_count == len(results) and len(results) > 0:
            status = DeliveryStatus.SENT
        elif success_count > 0:
            status = DeliveryStatus.PARTIAL
        else:
            status = DeliveryStatus.FAILED

        history = AlertHistory(
            alert_id=message.alert_id,
            user_id=user_id,
            symbol=message.symbol,
            alert_type=message.alert_type,
            triggered_value=message.triggered_value,
            message=f"{message.title}\n\n{message.body}",
            delivery_status=status.value,
            delivered_channels=[r.to_dict() for r in results],
        )
        session.add(history)
        await session.flush()

    async def dispatch(
        self,
        *,
        user_id: uuid.UUID,
        message: NotificationMessage,
        channel_ids: Sequence[str] | None = None,
        session: AsyncSession | None = None,
    ) -> list[NotificationResult]:
        """并发多渠道分发消息。

        铁律：内部任何网络或数据异常均在内部收敛捕获，绝不向调用方抛出异常中断主干流程。
        """

        async def _do_dispatch(sess: AsyncSession) -> list[NotificationResult]:
            channels = await self._resolve_channels(sess, user_id, channel_ids)
            tasks = []

            if not channels:
                # 若无配置任何外部渠道，默认走站内信投递
                in_app = self._notifiers.get(ChannelType.IN_APP)
                if in_app:
                    tasks.append(
                        in_app.send(
                            recipient=str(user_id),
                            message=message,
                            config={},
                            channel_id=None,
                        )
                    )
            else:
                for ch in channels:
                    try:
                        ch_type = ChannelType(ch.channel_type)
                    except ValueError:
                        continue
                    notifier = self._notifiers.get(ch_type)
                    if not notifier:
                        continue

                    recipient = (
                        ch.config.get("target_email") or ch.config.get("webhook_url") or ch.name
                    )
                    tasks.append(
                        notifier.send(
                            recipient=recipient,
                            message=message,
                            config=ch.config,
                            channel_id=ch.id,
                        )
                    )

            if not tasks:
                return [
                    NotificationResult(
                        channel_type=ChannelType.IN_APP,
                        success=False,
                        error_message="无可用通知渠道",
                    )
                ]

            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            results: list[NotificationResult] = []

            for r in raw_results:
                if isinstance(r, NotificationResult):
                    results.append(r)
                elif isinstance(r, Exception):
                    results.append(
                        NotificationResult(
                            channel_type=ChannelType.IN_APP,
                            success=False,
                            error_message=str(r),
                        )
                    )

            # 记录 Prometheus 投递指标
            for res in results:
                record_notification_dispatched(
                    channel_type=res.channel_type.value,
                    status="success" if res.success else "failure",
                )

            # 写入审计流水
            try:
                await self._record_history(sess, user_id, message, results)
            except Exception as exc:
                _LOGGER.error(
                    "dispatcher.record_history_failed",
                    user_id=str(user_id),
                    error=str(exc),
                )

            return results

        try:
            if session is not None:
                return await _do_dispatch(session)
            async with self._session_factory() as sess, sess.begin():
                return await _do_dispatch(sess)
        except Exception as exc:
            _LOGGER.error(
                "dispatcher.dispatch_critical_error",
                user_id=str(user_id),
                error=str(exc),
            )
            return [
                NotificationResult(
                    channel_type=ChannelType.IN_APP,
                    success=False,
                    error_message=f"分发关键异常: {exc}",
                )
            ]
