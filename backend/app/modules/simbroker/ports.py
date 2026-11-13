"""M4 模拟盘端口与协议契约（T01），`CONTRACTS.md §2`。

提供外部交互 Broker 统一接口定义与行情/公司行动注入依赖协议，实现整洁六边形架构。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from app.modules.simbroker.schemas import (
    AccountOverview,
    OrderCreate,
    OrderResponse,
    PositionResponse,
    TradeResponse,
)

__all__ = [
    "BarProtocol",
    "Broker",
    "CorporateActionFeedProtocol",
    "MarketDataFeedProtocol",
]


class BarProtocol(Protocol):
    """行情 K 线结构化鸭子类型协议"""

    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class Broker(Protocol):
    """系统统一定义的 Broker 端口协议（docs/02-architecture.md）"""

    name: str

    def submit_order(
        self, account_id: str, req: OrderCreate, idempotency_key: str
    ) -> OrderResponse: ...

    def cancel_order(self, account_id: str, order_id: str) -> OrderResponse: ...

    def get_account(self, account_id: str) -> AccountOverview: ...

    def get_positions(self, account_id: str) -> Sequence[PositionResponse]: ...

    def process_bar(self, account_id: str, bar_time: datetime) -> Sequence[TradeResponse]: ...


class MarketDataFeedProtocol(Protocol):
    """行情数据注入协议（解耦 marketdata 模块实体）"""

    def get_latest_price(self, symbol: str) -> Decimal | None: ...

    def get_daily_bar(self, symbol: str, trade_date: date) -> BarProtocol | None: ...

    def get_sp500_return(self, start_date: date, end_date: date) -> Decimal | None: ...

    def get_symbol_sector(self, symbol: str) -> str | None: ...


class CorporateActionFeedProtocol(Protocol):
    """公司行动数据源协议（拆股与分红）"""

    def get_split_ratio(self, symbol: str, trade_date: date) -> Decimal | None: ...

    def get_dividend_per_share(self, symbol: str, trade_date: date) -> Decimal | None: ...
