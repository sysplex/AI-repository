"""站内信通知适配器（M10-T02）。"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.logging import get_logger
from app.modules.notify.enums import ChannelType
from app.modules.notify.ports import BaseNotifier, NotificationMessage, NotificationResult

__all__ = ["InAppNotifier"]

_LOGGER = get_logger(__name__)


class InAppNotifier(BaseNotifier):
    """系统站内信通知适配器。"""

    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []

    async def send(
        self,
        *,
        recipient: str,
        message: NotificationMessage,
        config: dict[str, Any],
        channel_id: uuid.UUID | None = None,
    ) -> NotificationResult:
        """投递站内信。"""
        record = {
            "recipient": recipient,
            "title": message.title,
            "body": message.body,
            "symbol": message.symbol,
            "alert_type": message.alert_type,
            "channel_id": str(channel_id) if channel_id else None,
        }
        self.sent_messages.append(record)
        _LOGGER.info("in_app.sent", recipient=recipient, title=message.title)

        return NotificationResult(
            channel_type=ChannelType.IN_APP,
            channel_id=channel_id,
            success=True,
        )
