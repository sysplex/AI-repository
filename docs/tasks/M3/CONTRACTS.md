# M3 接口契约（CONTRACTS）

> 策略引擎权威接线图。每个任务严格按本契约的**签名与行为**实现。
> 对应设计：`docs/02-architecture.md§5`、`docs/04-modules.md#m3`、`docs/05-api-spec.md§2.3`、`docs/08-test-plan.md§5`。

---

## 0. 全局与数据约定

| 项 | 约定 |
|---|---|
| 语言/版本 | Python 3.12；必须通过 `mypy --strict` |
| 金额与价格 | `Decimal`，严禁使用 `float` |
| 日期与时间 | 时间为带时区的 UTC `datetime`；交易日为 `date`（美东交易日） |
| 防未来函数 | 任何输入数据集合中，所有条目的时间必须 `ts <= as_of`；测试做篡改截断断言 |
| 模块边界 | 业务只通过 `app.modules.marketdata.service.DataService` 获取数据 |
| 异常规范 | 数据不足抛出 `app.core.errors.ValidationFailed("insufficient_data: ...")` |

---

## 1. 领域模型与 DTO（`app/modules/strategy/schemas.py`）

```python
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

SignalDirection = Literal["long", "flat", "short"]

class Signal(BaseModel):
    """策略信号输出"""
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    as_of: date
    direction: SignalDirection
    strength: int = Field(default=0, ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    levels: dict[str, Decimal] = Field(default_factory=dict)  # entry, stop, target
    metrics: dict[str, Any] = Field(default_factory=dict)     # 关键指标快照

class TechnicalSnapshot(BaseModel):
    """单只股票在特定日期的技术面指标快照"""
    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: date
    sma_20: Decimal | None = None
    sma_50: Decimal | None = None
    sma_200: Decimal | None = None
    ema_12: Decimal | None = None
    ema_26: Decimal | None = None
    rsi_14: Decimal | None = None
    macd: Decimal | None = None
    macd_signal: Decimal | None = None
    macd_hist: Decimal | None = None
    atr_14: Decimal | None = None
    bb_upper: Decimal | None = None
    bb_middle: Decimal | None = None
    bb_lower: Decimal | None = None
    obv: int | None = None
    support: Decimal | None = None
    resistance: Decimal | None = None

class StrategyContext(BaseModel):
    """传递给策略 evaluate 的上下文，严格防未来函数（数据全部 <= as_of）"""
    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: date
    bars: list[Any]  # list[Bar] from marketdata
    fundamentals: Any | None = None  # Fundamentals | None from marketdata
    params: dict[str, Any] = Field(default_factory=dict)

class StrategyMetadata(BaseModel):
    """策略元数据，供前端渲染与列表展示"""
    model_config = ConfigDict(frozen=True)

    id: str
    display_name: str
    category: Literal["trend", "pullback", "reversal", "value", "growth", "dividend"]
    description: str
    requires: list[str] = Field(default_factory=list)  # ["bars", "fundamentals"]
    default_params: dict[str, Any] = Field(default_factory=dict)

class TradeRecord(BaseModel):
    """回测成交记录"""
    model_config = ConfigDict(frozen=True)

    trade_date: date
    action: Literal["buy", "sell"]
    price: Decimal
    shares: int
    amount: Decimal
    pnl: Decimal | None = None
    pnl_pct: Decimal | None = None
    reason: str = ""

class EquityPoint(BaseModel):
    """回测单日权益曲线采样点"""
    model_config = ConfigDict(frozen=True)

    trade_date: date
    equity: Decimal
    cash: Decimal
    drawdown_pct: Decimal

class BacktestRequest(BaseModel):
    """回测请求"""
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    start: date
    end: date
    initial_capital: Decimal = Decimal("100000.00")
    params: dict[str, Any] = Field(default_factory=dict)

class BacktestResult(BaseModel):
    """回测汇总结果"""
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    start: date
    end: date
    initial_capital: Decimal
    final_equity: Decimal
    total_return_pct: Decimal
    annualized_return_pct: Decimal
    max_drawdown_pct: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    total_trades: int
    trades: list[TradeRecord]
    equity_curve: list[EquityPoint]
```

---

## 2. 策略协议（`app/modules/strategy/ports.py`）

```python
from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from app.modules.strategy.schemas import Signal, StrategyContext, StrategyMetadata

@runtime_checkable
class Strategy(Protocol):
    """策略必须实现的协议接口"""

    id: str
    display_name: str
    category: str
    description: str
    requires: set[str]
    default_params: dict[str, Any]

    def evaluate(self, ctx: StrategyContext) -> Signal:
        """评估策略并产出信号。严禁访问 ctx.as_of 之后的数据"""
        ...
```

---

## 3. 技术指标函数库（`app/modules/strategy/indicators.py`）

指标计算函数接收 `Sequence[Bar]`，一律采用纯函数与高精 `Decimal` 计算：

```python
from collections.abc import Sequence
from decimal import Decimal
from app.modules.marketdata.models import Bar

def calculate_sma(bars: Sequence[Bar], period: int) -> Decimal | None: ...
def calculate_ema(bars: Sequence[Bar], period: int) -> Decimal | None: ...
def calculate_rsi(bars: Sequence[Bar], period: int = 14) -> Decimal | None: ...
def calculate_macd(bars: Sequence[Bar], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[Decimal | None, Decimal | None, Decimal | None]: ...
def calculate_true_range(current: Bar, previous: Bar | None) -> Decimal: ...
def calculate_atr(bars: Sequence[Bar], period: int = 14) -> Decimal | None: ...
def calculate_bollinger_bands(bars: Sequence[Bar], period: int = 20, num_std: Decimal = Decimal("2.0")) -> tuple[Decimal | None, Decimal | None, Decimal | None]: ...
def calculate_obv(bars: Sequence[Bar]) -> int | None: ...
def calculate_swing_high_low(bars: Sequence[Bar], window: int = 5) -> tuple[list[Decimal], list[Decimal]]: ...
def calculate_support_resistance(bars: Sequence[Bar], window: int = 20) -> tuple[Decimal | None, Decimal | None]: ...
```

---

## 4. 止损/止盈点位计算（`app/modules/strategy/levels.py`）

```python
from decimal import Decimal
from app.modules.strategy.schemas import SignalDirection

def compute_atr_levels(
    entry_price: Decimal,
    atr: Decimal,
    direction: SignalDirection,
    stop_mult: Decimal = Decimal("2.0"),
    target_mult: Decimal = Decimal("3.0"),
) -> dict[str, Decimal]:
    """
    当 direction == 'long':
      stop = entry_price - (atr * stop_mult)
      target = entry_price + (atr * target_mult)
    当 direction == 'short':
      stop = entry_price + (atr * stop_mult)
      target = entry_price - (atr * target_mult)
    """
    ...
```

---

## 5. 门面服务（`app/modules/strategy/service.py`）

```python
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from app.modules.marketdata.service import DataService
from app.modules.strategy.schemas import (
    BacktestRequest,
    BacktestResult,
    Signal,
    StrategyMetadata,
    TechnicalSnapshot,
)

class StrategyService:
    def __init__(self, data_service: DataService) -> None:
        self._data_service = data_service

    def list_strategies(self) -> list[StrategyMetadata]: ...
    async def evaluate(self, strategy_id: str, symbol: str, as_of: date, params: dict[str, Any] | None = None) -> Signal: ...
    async def scan(self, strategy_id: str, universe: Sequence[str], as_of: date, params: dict[str, Any] | None = None) -> list[Signal]: ...
    async def compute_technical_snapshot(self, symbol: str, as_of: date) -> TechnicalSnapshot: ...
    async def backtest(self, req: BacktestRequest) -> BacktestResult: ...
```

---

## 6. HTTP API 接口清单（`app/modules/strategy/api.py`）

挂载路径前缀：`/api/v1/strategy`
所有端点必须通过 `require_user` 认证校验（依据 HARD-01 规范）：

| Method | Endpoint | 描述 | 请求 Payload / Query | 响应模型 |
|---|---|---|---|---|
| `GET` | `/api/v1/strategy/list` | 获取所有已注册策略元数据 | 无 | `list[StrategyMetadata]` |
| `POST` | `/api/v1/strategy/evaluate` | 评估单只股票信号 | `{"strategy_id": str, "symbol": str, "as_of": "YYYY-MM-DD", "params": {}}` | `Signal` |
| `POST` | `/api/v1/strategy/scan` | 股票池扫描筛选信号 | `{"strategy_id": str, "symbols": ["AAPL", ...], "as_of": "YYYY-MM-DD", "params": {}}` | `list[Signal]` |
| `GET` | `/api/v1/strategy/technical/{symbol}` | 获取技术指标快照 | `symbol` path, `as_of` query (可选) | `TechnicalSnapshot` |
| `POST` | `/api/v1/strategy/backtest` | 执行历史回测 | `BacktestRequest` | `BacktestResult` |
