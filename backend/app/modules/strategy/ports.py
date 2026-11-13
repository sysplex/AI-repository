"""Protocol interfaces for the strategy module (M3 / T01).

Defines the abstract contracts for Strategy implementations and StrategyRegistry.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from app.modules.strategy.schemas import Signal, StrategyContext


@runtime_checkable
class Strategy(Protocol):
    """Abstract protocol that every trading strategy must satisfy."""

    id: str
    display_name: str
    category: str
    description: str
    requires: set[str]
    default_params: dict[str, Any]

    def evaluate(self, ctx: StrategyContext) -> Signal:
        """Evaluate market data and produce a trading signal.

        Must adhere strictly to lookahead protection: never access data beyond ctx.as_of.
        """
        ...


@runtime_checkable
class StrategyRegistry(Protocol):
    """Abstract protocol for strategy catalog registry."""

    def register(self, strategy: Strategy) -> None:
        """Register a strategy implementation."""
        ...

    def get(self, strategy_id: str) -> Strategy | None:
        """Retrieve a strategy by unique identifier."""
        ...

    def list_all(self) -> Sequence[Strategy]:
        """List all registered strategy implementations."""
        ...
