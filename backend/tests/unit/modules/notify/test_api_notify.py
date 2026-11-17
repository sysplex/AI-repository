"""单元测试：Notify 模块 REST API 端点（M10-T06）。

测试覆盖：
- 认证上下文提取与服务依赖装配
- 提醒规则 CRUD、历史流水查询与论文破裂批量创建
- 通知渠道 CRUD 与连通性测试
- 异常分支与 404/401 守卫
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import NotFound, Unauthenticated
from app.modules.notify.api import (
    batch_create_thesis_breakers,
    check_channel_connectivity,
    create_alert,
    create_channel,
    delete_alert,
    delete_channel,
    get_alert,
    get_alert_service,
    get_channel,
    get_current_user,
    list_alert_history,
    list_alerts,
    list_channels,
    set_alert_service_factory,
    update_alert,
    update_channel,
)
from app.modules.notify.enums import (
    AlertStatus,
    AlertType,
    ChannelType,
    DeliveryStatus,
    PriceDirection,
)
from app.modules.notify.schemas import (
    AlertCreate,
    AlertHistoryRead,
    AlertRead,
    AlertUpdate,
    BatchThesisBreakersRequest,
    ChannelTestResult,
    NotificationChannelCreate,
    NotificationChannelRead,
    NotificationChannelUpdate,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


@pytest.fixture
def sample_alert(mock_user: MagicMock) -> AlertRead:
    return AlertRead(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        symbol="AAPL",
        alert_type=AlertType.PRICE,
        title="AAPL 突破 $230",
        conditions={"direction": PriceDirection.CROSS_ABOVE.value, "target_price": "230.00"},
        channel_ids=[],
        status=AlertStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_channel(mock_user: MagicMock) -> NotificationChannelRead:
    return NotificationChannelRead(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        channel_type=ChannelType.WEBHOOK,
        name="飞书运维群",
        config={"webhook_url": "https://open.feishu.cn/hook/xxx"},
        is_enabled=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# =============================================================================
# 1. 鉴权与服务提供器测试
# =============================================================================


def test_get_current_user_present(mock_user: MagicMock) -> None:
    req = MagicMock()
    req.state.user = mock_user
    assert get_current_user(req) is mock_user


def test_get_current_user_absent_raises() -> None:
    req = MagicMock()
    req.state.user = None
    with pytest.raises(Unauthenticated, match="需要登录"):
        get_current_user(req)


def test_get_alert_service_default() -> None:
    session = AsyncMock()
    set_alert_service_factory(None)
    svc = get_alert_service(session)
    assert svc is not None


def test_set_alert_service_factory_override() -> None:
    custom_mock = MagicMock()
    set_alert_service_factory(lambda sess: custom_mock)
    assert get_alert_service(AsyncMock()) is custom_mock
    set_alert_service_factory(None)


# =============================================================================
# 2. 提醒规则端点测试
# =============================================================================


@pytest.mark.asyncio
async def test_create_alert_api(mock_user: MagicMock, sample_alert: AlertRead) -> None:
    service = AsyncMock()
    service.create_alert.return_value = sample_alert

    data = AlertCreate(
        symbol="AAPL",
        alert_type=AlertType.PRICE,
        title="AAPL 突破 $230",
        conditions={"direction": PriceDirection.CROSS_ABOVE, "target_price": Decimal("230.00")},
    )

    res = await create_alert(data=data, service=service, user=mock_user)
    assert res.id == sample_alert.id
    service.create_alert.assert_awaited_once_with(user_id=mock_user.id, data=data)


@pytest.mark.asyncio
async def test_list_alerts_api(mock_user: MagicMock, sample_alert: AlertRead) -> None:
    service = AsyncMock()
    service.list_alerts.return_value = [sample_alert]

    res = await list_alerts(
        service=service,
        user=mock_user,
        symbol="AAPL",
        alert_type=AlertType.PRICE,
        status=AlertStatus.ACTIVE,
        limit=20,
        offset=0,
    )
    assert len(res) == 1
    assert res[0].symbol == "AAPL"
    service.list_alerts.assert_awaited_once_with(
        user_id=mock_user.id,
        symbol="AAPL",
        alert_type=AlertType.PRICE,
        status=AlertStatus.ACTIVE,
        limit=20,
        offset=0,
    )


@pytest.mark.asyncio
async def test_get_alert_api_success(mock_user: MagicMock, sample_alert: AlertRead) -> None:
    service = AsyncMock()
    service.get_alert.return_value = sample_alert

    res = await get_alert(alert_id=sample_alert.id, service=service, user=mock_user)
    assert res.id == sample_alert.id


@pytest.mark.asyncio
async def test_get_alert_api_not_found(mock_user: MagicMock) -> None:
    service = AsyncMock()
    service.get_alert.return_value = None

    with pytest.raises(NotFound, match="提醒规则不存在"):
        await get_alert(alert_id=uuid.uuid4(), service=service, user=mock_user)


@pytest.mark.asyncio
async def test_update_alert_api_success(mock_user: MagicMock, sample_alert: AlertRead) -> None:
    service = AsyncMock()
    service.update_alert.return_value = sample_alert

    data = AlertUpdate(title="新标题", status=AlertStatus.DISABLED)
    res = await update_alert(alert_id=sample_alert.id, data=data, service=service, user=mock_user)
    assert res.id == sample_alert.id
    service.update_alert.assert_awaited_once_with(
        user_id=mock_user.id, alert_id=sample_alert.id, data=data
    )


@pytest.mark.asyncio
async def test_update_alert_api_not_found(mock_user: MagicMock) -> None:
    service = AsyncMock()
    service.update_alert.return_value = None

    data = AlertUpdate(title="新标题")
    with pytest.raises(NotFound, match="提醒规则不存在"):
        await update_alert(alert_id=uuid.uuid4(), data=data, service=service, user=mock_user)


@pytest.mark.asyncio
async def test_delete_alert_api_success(mock_user: MagicMock) -> None:
    service = AsyncMock()
    service.delete_alert.return_value = True

    alert_id = uuid.uuid4()
    await delete_alert(alert_id=alert_id, service=service, user=mock_user)
    service.delete_alert.assert_awaited_once_with(user_id=mock_user.id, alert_id=alert_id)


@pytest.mark.asyncio
async def test_delete_alert_api_not_found(mock_user: MagicMock) -> None:
    service = AsyncMock()
    service.delete_alert.return_value = False

    with pytest.raises(NotFound, match="提醒规则不存在"):
        await delete_alert(alert_id=uuid.uuid4(), service=service, user=mock_user)


@pytest.mark.asyncio
async def test_list_alert_history_api(mock_user: MagicMock) -> None:
    service = AsyncMock()
    sample_hist = AlertHistoryRead(
        id=uuid.uuid4(),
        alert_id=uuid.uuid4(),
        user_id=mock_user.id,
        symbol="AAPL",
        alert_type=AlertType.PRICE,
        triggered_value={"current_price": 235.5},
        message="AAPL 触发提醒",
        delivery_status=DeliveryStatus.SENT,
        delivered_channels=[],
        created_at=datetime.now(UTC),
    )
    service.list_history.return_value = [sample_hist]

    res = await list_alert_history(
        service=service, user=mock_user, symbol="AAPL", limit=10, offset=0
    )
    assert len(res) == 1
    assert res[0].symbol == "AAPL"


@pytest.mark.asyncio
async def test_batch_create_thesis_breakers_api(
    mock_user: MagicMock, sample_alert: AlertRead
) -> None:
    service = AsyncMock()
    service.batch_create_thesis_breakers.return_value = [sample_alert]

    req = BatchThesisBreakersRequest(
        symbol="AAPL",
        breakers=[{"metric": "gross_margin", "operator": "lt", "threshold": 0.4}],
    )
    res = await batch_create_thesis_breakers(data=req, service=service, user=mock_user)
    assert len(res) == 1
    service.batch_create_thesis_breakers.assert_awaited_once()


# =============================================================================
# 3. 通知渠道端点测试
# =============================================================================


@pytest.mark.asyncio
async def test_create_channel_api(
    mock_user: MagicMock, sample_channel: NotificationChannelRead
) -> None:
    service = AsyncMock()
    service.create_channel.return_value = sample_channel

    data = NotificationChannelCreate(
        channel_type=ChannelType.WEBHOOK,
        name="飞书群",
        config={"webhook_url": "https://hook.url"},
    )
    res = await create_channel(data=data, service=service, user=mock_user)
    assert res.id == sample_channel.id
    service.create_channel.assert_awaited_once_with(user_id=mock_user.id, data=data)


@pytest.mark.asyncio
async def test_list_channels_api(
    mock_user: MagicMock, sample_channel: NotificationChannelRead
) -> None:
    service = AsyncMock()
    service.list_channels.return_value = [sample_channel]

    res = await list_channels(service=service, user=mock_user)
    assert len(res) == 1
    assert res[0].name == sample_channel.name


@pytest.mark.asyncio
async def test_get_channel_api_success(
    mock_user: MagicMock, sample_channel: NotificationChannelRead
) -> None:
    service = AsyncMock()
    service.get_channel.return_value = sample_channel

    res = await get_channel(channel_id=sample_channel.id, service=service, user=mock_user)
    assert res.id == sample_channel.id


@pytest.mark.asyncio
async def test_get_channel_api_not_found(mock_user: MagicMock) -> None:
    service = AsyncMock()
    service.get_channel.return_value = None

    with pytest.raises(NotFound, match="通知渠道不存在"):
        await get_channel(channel_id=uuid.uuid4(), service=service, user=mock_user)


@pytest.mark.asyncio
async def test_update_channel_api_success(
    mock_user: MagicMock, sample_channel: NotificationChannelRead
) -> None:
    service = AsyncMock()
    service.update_channel.return_value = sample_channel

    data = NotificationChannelUpdate(name="更新后的名称")
    res = await update_channel(
        channel_id=sample_channel.id, data=data, service=service, user=mock_user
    )
    assert res.id == sample_channel.id


@pytest.mark.asyncio
async def test_update_channel_api_not_found(mock_user: MagicMock) -> None:
    service = AsyncMock()
    service.update_channel.return_value = None

    data = NotificationChannelUpdate(name="更新后的名称")
    with pytest.raises(NotFound, match="通知渠道不存在"):
        await update_channel(channel_id=uuid.uuid4(), data=data, service=service, user=mock_user)


@pytest.mark.asyncio
async def test_delete_channel_api_success(mock_user: MagicMock) -> None:
    service = AsyncMock()
    service.delete_channel.return_value = True

    cid = uuid.uuid4()
    await delete_channel(channel_id=cid, service=service, user=mock_user)
    service.delete_channel.assert_awaited_once_with(user_id=mock_user.id, channel_id=cid)


@pytest.mark.asyncio
async def test_delete_channel_api_not_found(mock_user: MagicMock) -> None:
    service = AsyncMock()
    service.delete_channel.return_value = False

    with pytest.raises(NotFound, match="通知渠道不存在"):
        await delete_channel(channel_id=uuid.uuid4(), service=service, user=mock_user)


@pytest.mark.asyncio
async def test_test_channel_api_success(mock_user: MagicMock) -> None:
    service = AsyncMock()
    cid = uuid.uuid4()
    service.test_channel.return_value = {
        "channel_id": str(cid),
        "channel_name": "测试渠道",
        "success": True,
        "results": [{"channel_type": "webhook", "success": True}],
    }

    res = await check_channel_connectivity(channel_id=cid, service=service, user=mock_user)
    assert isinstance(res, ChannelTestResult)
    assert res.success is True
    assert res.channel_name == "测试渠道"


@pytest.mark.asyncio
async def test_test_channel_api_not_found(mock_user: MagicMock) -> None:
    service = AsyncMock()
    service.test_channel.return_value = None

    with pytest.raises(NotFound, match="通知渠道不存在"):
        await check_channel_connectivity(channel_id=uuid.uuid4(), service=service, user=mock_user)
