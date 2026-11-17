"""Notify 领域 Pydantic 校验 Schema（M10-T01），`CONTRACTS.md §2-§4`。"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.notify.enums import (
    AlertStatus,
    AlertType,
    ChannelType,
    ComparisonOperator,
    DeliveryStatus,
    PriceDirection,
)

__all__ = [
    "AlertCreate",
    "AlertHistoryRead",
    "AlertRead",
    "AlertUpdate",
    "BatchThesisBreakersRequest",
    "ChannelTestResult",
    "EarningsDateCondition",
    "NotificationChannelCreate",
    "NotificationChannelRead",
    "NotificationChannelUpdate",
    "PriceCondition",
    "TechnicalSignalCondition",
    "ThesisBreakerCondition",
]


# ==========================================
# 1. 提醒条件 Schema
# ==========================================


class PriceCondition(BaseModel):
    """价格提醒条件。"""

    model_config = ConfigDict(extra="ignore")

    direction: PriceDirection
    target_price: Decimal = Field(gt=0, description="目标触发价格，必须大于 0")


class TechnicalSignalCondition(BaseModel):
    """技术指标形态条件。"""

    model_config = ConfigDict(extra="ignore")

    indicator: str = Field(min_length=1, max_length=64, description="指标名称，如 RSI, SMA_CROSS")
    operator: ComparisonOperator
    threshold: Decimal | None = None
    parameters: dict[str, Any] = Field(default_factory=dict, description="指标参数如 period=14")


class EarningsDateCondition(BaseModel):
    """财报日倒计时条件。"""

    model_config = ConfigDict(extra="ignore")

    days_before: int = Field(default=1, ge=0, le=30, description="提前提醒的天数（0-30天）")


class ThesisBreakerCondition(BaseModel):
    """长期投资论文破裂条件（对齐 M7 ThesisEvaluation）。"""

    model_config = ConfigDict(extra="ignore")

    metric: str = Field(min_length=1, max_length=64, description="被监控的财务或运营指标代码")
    operator: ComparisonOperator
    threshold: Decimal = Field(description="破裂触发门槛值")
    description: str | None = Field(default=None, max_length=256, description="破裂条件业务描述")


# ==========================================
# 2. 渠道管理 Schema
# ==========================================


class NotificationChannelCreate(BaseModel):
    """创建通知渠道请求。"""

    channel_type: ChannelType
    name: str = Field(min_length=1, max_length=128, description="渠道友好名称")
    config: dict[str, Any] = Field(
        default_factory=dict, description="渠道参数配置（邮件或 Webhook）"
    )
    is_enabled: bool = Field(default=True, description="是否即时启用")


class NotificationChannelUpdate(BaseModel):
    """更新通知渠道请求。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    config: dict[str, Any] | None = None
    is_enabled: bool | None = None


class NotificationChannelRead(BaseModel):
    """通知渠道公开响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    channel_type: ChannelType
    name: str
    config: dict[str, Any]
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


# ==========================================
# 3. 提醒规则 Schema
# ==========================================


class AlertCreate(BaseModel):
    """创建提醒规则请求。"""

    symbol: str | None = Field(default=None, max_length=16, description="标的代码，如 AAPL")
    alert_type: AlertType
    title: str = Field(min_length=1, max_length=256, description="提醒规则标题")
    conditions: dict[str, Any] = Field(description="具体的触发条件字典")
    channel_ids: list[str] = Field(default_factory=list, description="接收提醒的渠道 ID 列表")
    cooldown_minutes: int = Field(default=1440, ge=1, description="冷却时间（分钟），默认 24 小时")

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip().upper()
            return v if v else None
        return None


class AlertUpdate(BaseModel):
    """更新提醒规则请求。"""

    title: str | None = Field(default=None, min_length=1, max_length=256)
    conditions: dict[str, Any] | None = None
    channel_ids: list[str] | None = None
    status: AlertStatus | None = None
    cooldown_minutes: int | None = Field(default=None, ge=1)


class AlertRead(BaseModel):
    """提醒规则详情响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    symbol: str | None
    alert_type: AlertType
    title: str
    conditions: dict[str, Any]
    channel_ids: list[str]
    status: AlertStatus
    last_triggered_at: datetime | None = None
    trigger_count: int = Field(default=0)
    cooldown_minutes: int = 1440
    created_at: datetime
    updated_at: datetime


# ==========================================
# 4. 触发历史与审计流水
# ==========================================


class AlertHistoryRead(BaseModel):
    """提醒触发历史记录响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_id: uuid.UUID
    user_id: uuid.UUID
    symbol: str | None
    alert_type: AlertType
    triggered_value: dict[str, Any]
    message: str
    delivery_status: DeliveryStatus
    delivered_channels: list[dict[str, Any]]
    created_at: datetime


class BatchThesisBreakersRequest(BaseModel):
    """批量从 M7 投资论文破裂项创建监控规则请求。"""

    symbol: str = Field(min_length=1, max_length=16, description="标的代码")
    breakers: list[dict[str, Any]] = Field(description="M7 破裂条件列表")
    channel_ids: list[str] = Field(default_factory=list, description="通知渠道列表")
    cooldown_minutes: int = Field(default=1440, ge=1, description="冷却时间（分钟）")


class ChannelTestResult(BaseModel):
    """渠道连通性测试响应。"""

    channel_id: str
    channel_name: str
    success: bool
    results: list[dict[str, Any]] = Field(default_factory=list)
