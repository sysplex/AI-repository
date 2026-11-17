"""Notify 统一抽象端口与消息实体（M10-T02），`CONTRACTS.md §1`。"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.modules.notify.enums import ChannelType

__all__ = [
    "BaseNotifier",
    "NotificationMessage",
    "NotificationResult",
]


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    """结构化通知消息实体。"""

    title: str
    body: str
    html_body: str | None = None
    alert_id: uuid.UUID | None = None
    alert_type: str = "general"
    symbol: str | None = None
    triggered_value: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NotificationResult:
    """单渠道投递结果实体。"""

    channel_type: ChannelType
    success: bool
    channel_id: uuid.UUID | None = None
    error_message: str | None = None
    delivered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """序列化为审计日志 JSON 字典。"""
        return {
            "channel_id": str(self.channel_id) if self.channel_id else None,
            "channel_type": self.channel_type.value,
            "success": self.success,
            "error_message": self.error_message,
            "delivered_at": self.delivered_at.isoformat(),
        }


class BaseNotifier(ABC):
    """所有通知通道适配器的公共抽象基类。"""

    @abstractmethod
    async def send(
        self,
        *,
        recipient: str,
        message: NotificationMessage,
        config: dict[str, Any],
        channel_id: uuid.UUID | None = None,
    ) -> NotificationResult:
        """异步投递消息。

        参数：
            recipient: 接收端标识（邮箱地址、Webhook 完整 URL、或用户名）
            message: 结构化通知消息
            config: 渠道附加配置（密钥、自定义请求头等）
            channel_id: 所属通知渠道持久化 UUID

        返回：
            NotificationResult 投递结果（成功与否及错误详情）
        """
        raise NotImplementedError
