"""REST API endpoints for strategy module (M3 / T06).

Provides HTTP endpoints mounted under `/api/v1/strategy/*` according to
`docs/tasks/M3/CONTRACTS.md §6` and `docs/tasks/M3/T06-strategy-service-and-api.md`.
All endpoints enforce authentication (HARD-01).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modules.strategy.schemas import (
    BacktestRequest,
    BacktestResult,
    EvaluateRequest,
    ScanRequest,
    Signal,
    StrategyMetadata,
    TechnicalSnapshot,
)
from app.modules.strategy.service import StrategyService

router = APIRouter()

_strategy_service: StrategyService | None = None


def get_strategy_service() -> StrategyService:
    """Dependency provider for StrategyService."""
    global _strategy_service
    if _strategy_service is None:
        _strategy_service = StrategyService()
    return _strategy_service


def set_strategy_service(service: StrategyService) -> None:
    """Set the global StrategyService instance (used for DI wiring)."""
    global _strategy_service
    _strategy_service = service


async def require_user() -> None:
    """Authentication guard dependency (HARD-01).

    Overridden by app-level router wiring to enforce active user session.
    """
    return None


@router.get("/list", response_model=list[StrategyMetadata])
async def list_strategies_endpoint(
    service: Annotated[StrategyService, Depends(get_strategy_service)],
    _auth: Annotated[None, Depends(require_user)] = None,
) -> list[StrategyMetadata]:
    """Retrieve metadata of all registered technical and quantitative strategies."""
    return service.list_strategies()


@router.post("/evaluate", response_model=Signal)
async def evaluate_signal_endpoint(
    payload: EvaluateRequest,
    service: Annotated[StrategyService, Depends(get_strategy_service)],
    _auth: Annotated[None, Depends(require_user)] = None,
) -> Signal:
    """Evaluate trading signal for a specific stock symbol on a target date."""
    return await service.evaluate(
        strategy_id=payload.strategy_id,
        symbol=payload.symbol,
        as_of=payload.as_of,
        params=payload.params,
    )


@router.post("/scan", response_model=list[Signal])
async def scan_universe_endpoint(
    payload: ScanRequest,
    service: Annotated[StrategyService, Depends(get_strategy_service)],
    _auth: Annotated[None, Depends(require_user)] = None,
) -> list[Signal]:
    """Scan a stock universe with a strategy and filter generated signals."""
    return await service.scan(
        strategy_id=payload.strategy_id,
        universe=payload.symbols,
        as_of=payload.as_of,
        params=payload.params,
    )


@router.get("/technical/{symbol}", response_model=TechnicalSnapshot)
async def get_technical_snapshot_endpoint(
    symbol: str,
    service: Annotated[StrategyService, Depends(get_strategy_service)],
    as_of: Annotated[date | None, Query(description="Target date (YYYY-MM-DD)")] = None,
    _auth: Annotated[None, Depends(require_user)] = None,
) -> TechnicalSnapshot:
    """Retrieve comprehensive technical indicator snapshot for a symbol."""
    return await service.compute_technical_snapshot(symbol=symbol, as_of=as_of)


@router.post("/backtest", response_model=BacktestResult)
async def run_backtest_endpoint(
    payload: BacktestRequest,
    service: Annotated[StrategyService, Depends(get_strategy_service)],
    _auth: Annotated[None, Depends(require_user)] = None,
) -> BacktestResult:
    """Execute historical event-driven backtesting simulation for a strategy."""
    return await service.backtest(payload)
