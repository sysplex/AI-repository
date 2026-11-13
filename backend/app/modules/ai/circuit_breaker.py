"""M5 AI 成本预算熔断器（T06），`CONTRACTS.md §0 / §4`。

监控日度与月度全局/租户 LLM 调用总成本，防止异常失控与账单击穿。
当累计消耗达到预设阈值时自动触发熔断状态 (OPEN)，拒绝外部模型请求 (HTTP 503)，
同时允许缓存命中 (cached=True) 的只读请求正常响应。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from app.core.clock import get_clock
from app.core.logging import get_logger
from app.modules.ai.exceptions import BudgetCircuitOpenError
from app.modules.ai.schemas import BudgetCircuitStatus

__all__ = [
    "DEFAULT_DAILY_BUDGET_USD",
    "DEFAULT_MONTHLY_BUDGET_USD",
    "BudgetCircuitBreaker",
    "CircuitState",
]

logger = get_logger(__name__)

CircuitState = Literal["CLOSED", "OPEN", "HALF_OPEN"]

DEFAULT_DAILY_BUDGET_USD = Decimal("50.000000")
DEFAULT_MONTHLY_BUDGET_USD = Decimal("1000.000000")


class BudgetCircuitBreaker:
    """成本与调用预算熔断器。

    跟踪每日与每月累计产生的 LLM 支出费用；
    当累计成本达到阈值时自动进入 OPEN 熔断态，阻断所有计费调用。
    """

    def __init__(
        self,
        *,
        daily_budget_usd: Decimal = DEFAULT_DAILY_BUDGET_USD,
        monthly_budget_usd: Decimal = DEFAULT_MONTHLY_BUDGET_USD,
    ) -> None:
        self._daily_budget_usd: Decimal = Decimal(str(daily_budget_usd))
        self._monthly_budget_usd: Decimal = Decimal(str(monthly_budget_usd))

        self._state: CircuitState = "CLOSED"
        self._daily_cost_usd: Decimal = Decimal("0.000000")
        self._monthly_cost_usd: Decimal = Decimal("0.000000")

        self._current_day: date | None = None
        self._current_month: tuple[int, int] | None = None

        self._tripped_at: datetime | None = None
        self._tripped_reason: str | None = None

    @property
    def state(self) -> CircuitState:
        """熔断器当前状态 (CLOSED, OPEN, HALF_OPEN)。"""
        return self._state

    @property
    def is_open(self) -> bool:
        """是否处于熔断开启状态（拒绝外部模型请求）。"""
        return self._state == "OPEN"

    @property
    def daily_budget_usd(self) -> Decimal:
        """日度预算限额 (USD)。"""
        return self._daily_budget_usd

    @property
    def monthly_budget_usd(self) -> Decimal:
        """月度预算限额 (USD)。"""
        return self._monthly_budget_usd

    @property
    def daily_cost_usd(self) -> Decimal:
        """当日累计成本 (USD)。"""
        self._rollover_if_needed(get_clock().now())
        return self._daily_cost_usd

    @property
    def monthly_cost_usd(self) -> Decimal:
        """当月累计成本 (USD)。"""
        self._rollover_if_needed(get_clock().now())
        return self._monthly_cost_usd

    def check_budget(self, *, cached: bool = False) -> None:
        """检查当前预算熔断状态。

        Args:
            cached: 是否命中快照缓存。缓存命中无需调用外部 LLM 且费用为 0，
                    即使熔断器处于 OPEN 状态也允许通行。

        Raises:
            BudgetCircuitOpenError: 熔断器处于 OPEN 或当前成本已超过预算限额。
        """
        if cached:
            # 缓存命中：零成本，直接放行
            return

        now = get_clock().now()
        self._rollover_if_needed(now)

        if self.is_open:
            logger.warning(
                "BudgetCircuitBreaker blocked request: state={state}, reason={reason}",
                state=self._state,
                reason=self._tripped_reason,
            )
            reason_str = self._tripped_reason or "circuit_open"
            raise BudgetCircuitOpenError(
                f"AI 预算熔断器已开启（{reason_str}），暂停外部模型调用",
                details=self.get_status().model_dump(mode="json"),
            )

        if self._daily_cost_usd >= self._daily_budget_usd:
            self.trip("daily_budget_exceeded")
            msg = (
                f"当日 AI 总成本已达到熔断上限"
                f"（${self._daily_cost_usd:.2f} >= ${self._daily_budget_usd:.2f}）"
            )
            raise BudgetCircuitOpenError(
                msg,
                details=self.get_status().model_dump(mode="json"),
            )

        if self._monthly_cost_usd >= self._monthly_budget_usd:
            self.trip("monthly_budget_exceeded")
            msg = (
                f"当月 AI 总成本已达到熔断上限"
                f"（${self._monthly_cost_usd:.2f} >= ${self._monthly_budget_usd:.2f}）"
            )
            raise BudgetCircuitOpenError(
                msg,
                details=self.get_status().model_dump(mode="json"),
            )

    def record_cost(self, cost_usd: Decimal) -> None:
        """记账新产生的调用成本，并在触碰阈值时触发熔断。

        Args:
            cost_usd: 本次调用成本 (USD)
        """
        now = get_clock().now()
        self._rollover_if_needed(now)
        cost = Decimal(str(cost_usd))

        self._daily_cost_usd += cost
        self._monthly_cost_usd += cost

        if self._daily_cost_usd >= self._daily_budget_usd:
            self.trip("daily_budget_exceeded")
        elif self._monthly_cost_usd >= self._monthly_budget_usd:
            self.trip("monthly_budget_exceeded")

    def trip(self, reason: str = "manual_intervention") -> None:
        """将熔断器强行触发为 OPEN 状态。"""
        now = get_clock().now()
        self._state = "OPEN"
        self._tripped_at = now
        self._tripped_reason = reason
        logger.error(
            "BudgetCircuitBreaker TRIPPED to OPEN: reason={reason}",
            reason=reason,
            daily=str(self._daily_cost_usd),
            monthly=str(self._monthly_cost_usd),
        )

    def reset(self) -> None:
        """重置熔断器恢复为 CLOSED 正常工作状态。"""
        self._state = "CLOSED"
        self._tripped_at = None
        self._tripped_reason = None
        logger.info("BudgetCircuitBreaker reset to CLOSED")

    def configure_limits(
        self,
        *,
        daily_budget_usd: Decimal | None = None,
        monthly_budget_usd: Decimal | None = None,
    ) -> None:
        """动态配置预算阈值（管理员操作）。"""
        if daily_budget_usd is not None:
            if daily_budget_usd <= Decimal("0"):
                raise ValueError("daily_budget_usd must be positive")
            self._daily_budget_usd = Decimal(str(daily_budget_usd))

        if monthly_budget_usd is not None:
            if monthly_budget_usd <= Decimal("0"):
                raise ValueError("monthly_budget_usd must be positive")
            self._monthly_budget_usd = Decimal(str(monthly_budget_usd))

        # 若原因为阈值超额，且新阈值高于当前支出，自动解除熔断
        if self._state == "OPEN" and (
            (
                self._tripped_reason == "daily_budget_exceeded"
                and self._daily_cost_usd < self._daily_budget_usd
            )
            or (
                self._tripped_reason == "monthly_budget_exceeded"
                and self._monthly_cost_usd < self._monthly_budget_usd
            )
        ):
            self.reset()

    def sync_costs(
        self,
        *,
        daily_cost_usd: Decimal | None = None,
        monthly_cost_usd: Decimal | None = None,
    ) -> None:
        """同步外部或数据库历史累计成本。"""
        now = get_clock().now()
        self._rollover_if_needed(now)

        if daily_cost_usd is not None:
            self._daily_cost_usd = Decimal(str(daily_cost_usd))
        if monthly_cost_usd is not None:
            self._monthly_cost_usd = Decimal(str(monthly_cost_usd))

        # 检查是否触碰熔断阈值
        if self._daily_cost_usd >= self._daily_budget_usd:
            self.trip("daily_budget_exceeded")
        elif self._monthly_cost_usd >= self._monthly_budget_usd:
            self.trip("monthly_budget_exceeded")

    def get_status(self) -> BudgetCircuitStatus:
        """获取熔断器详细状态视图。"""
        now = get_clock().now()
        self._rollover_if_needed(now)
        return BudgetCircuitStatus(
            state=self._state,
            daily_cost_usd=self._daily_cost_usd,
            daily_budget_usd=self._daily_budget_usd,
            monthly_cost_usd=self._monthly_cost_usd,
            monthly_budget_usd=self._monthly_budget_usd,
            is_open=self.is_open,
            tripped_at=self._tripped_at,
            tripped_reason=self._tripped_reason,
        )

    def _rollover_if_needed(self, now: datetime) -> None:
        """检查并执行跨日与跨月成本自动清零滚转。"""
        current_date = now.date()
        current_year_month = (now.year, now.month)

        if self._current_day is None:
            self._current_day = current_date

        if self._current_month is None:
            self._current_month = current_year_month

        # 跨日滚转
        if self._current_day != current_date:
            logger.info(
                "Rolling over daily budget from {old} to {new}",
                old=self._current_day,
                new=current_date,
            )
            self._daily_cost_usd = Decimal("0.000000")
            self._current_day = current_date
            if self._state == "OPEN" and self._tripped_reason == "daily_budget_exceeded":
                self.reset()

        # 跨月滚转
        if self._current_month != current_year_month:
            logger.info(
                "Rolling over monthly budget from {old} to {new}",
                old=self._current_month,
                new=current_year_month,
            )
            self._monthly_cost_usd = Decimal("0.000000")
            self._current_month = current_year_month
            if self._state == "OPEN" and self._tripped_reason == "monthly_budget_exceeded":
                self.reset()
