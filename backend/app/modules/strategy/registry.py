"""Strategy registry and registration mechanisms (M3 / T03).

Provides the concrete StrategyRegistry implementation, default global registry,
and `@register_strategy` decorator for automatic strategy discovery.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, overload

from app.modules.strategy.ports import Strategy, StrategyRegistry


class StrategyRegistryImpl(StrategyRegistry):
    """Thread-safe, in-memory implementation of the StrategyRegistry protocol."""

    def __init__(self) -> None:
        self._strategies: dict[str, Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        """Register a strategy implementation into the catalog."""
        if not hasattr(strategy, "id") or not strategy.id:
            msg = "Strategy must have a non-empty 'id' attribute."
            raise ValueError(msg)
        self._strategies[strategy.id] = strategy

    def get(self, strategy_id: str) -> Strategy | None:
        """Retrieve a strategy by its unique identifier."""
        return self._strategies.get(strategy_id)

    def list_all(self) -> Sequence[Strategy]:
        """List all currently registered strategies."""
        return list(self._strategies.values())

    def clear(self) -> None:
        """Clear all registered strategies (primarily for testing)."""
        self._strategies.clear()


# Default singleton catalog for the application
default_registry = StrategyRegistryImpl()


@overload
def register_strategy[T: Strategy](strategy_cls_or_instance: type[T]) -> type[T]: ...


@overload
def register_strategy[T: Strategy](strategy_cls_or_instance: T) -> T: ...


@overload
def register_strategy[T: Strategy](
    strategy_cls_or_instance: None = None,
    *,
    registry: StrategyRegistry | None = None,
) -> Callable[[type[T] | T], type[T] | T]: ...


def register_strategy[T: Strategy](
    strategy_cls_or_instance: type[T] | T | None = None,
    *,
    registry: StrategyRegistry | None = None,
) -> Any:
    """Decorator or function to register a strategy class or instance.

    Usage:
        @register_strategy
        class MyStrategy:
            ...

        @register_strategy(registry=custom_registry)
        class MyCustomStrategy:
            ...

        register_strategy(my_instance)
    """
    target_registry = registry or default_registry

    def _do_register(item: type[T] | T) -> type[T] | T:
        instance: Strategy = item() if isinstance(item, type) else item
        target_registry.register(instance)
        return item

    if strategy_cls_or_instance is not None:
        return _do_register(strategy_cls_or_instance)

    return _do_register


def get_strategy(strategy_id: str) -> Strategy | None:
    """Convenience helper to get strategy from the default registry."""
    return default_registry.get(strategy_id)


def list_strategies() -> Sequence[Strategy]:
    """Convenience helper to list all strategies from the default registry."""
    return default_registry.list_all()
