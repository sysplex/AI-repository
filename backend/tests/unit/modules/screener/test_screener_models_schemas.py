"""M8-T01 筛选器与自选清单领域模型、ORM 与协议单元测试。

测试覆盖：
- DTO Schemas 序列化、反序列化、严格字段校验与非法输入拦截
- SQLAlchemy ORM 实体结构、主外键、级联删除与约束
- 协议接口定义与运行时可检查性
- 业务异常体系与 HTTP 状态码映射
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy import Table

from app.core.errors import AppError, ErrorCode
from app.modules.screener.exceptions import (
    DuplicateWatchlistItemError,
    ScreenerError,
    ScreenerExecutionError,
    ScreenerRunNotFoundError,
    StrategyNotFoundError,
    ThemeNotFoundError,
    UniverseNotFoundError,
    WatchlistItemNotFoundError,
    WatchlistNotFoundError,
)
from app.modules.screener.models import (
    ScreenerResult,
    ScreenerRun,
    Watchlist,
    WatchlistItem,
)
from app.modules.screener.ports import (
    AIServiceProtocol,
    MarketDataServiceProtocol,
    ScreenerExecutorProtocol,
    ScreenerRepositoryProtocol,
    ScreenerServiceProtocol,
    StrategyServiceProtocol,
    UniverseManagerProtocol,
    WatchlistRepositoryProtocol,
)
from app.modules.screener.schemas import (
    ExportToResearchRequest,
    ScreenerResultItem,
    ScreenerRunCreate,
    ScreenerRunRead,
    ThemeCardItem,
    ThemeCardsResponse,
    ThemeInfo,
    ThemeStockItem,
    UniverseInfo,
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemRead,
    WatchlistItemUpdate,
    WatchlistRead,
    WatchlistUpdate,
)


# ==============================================================================
# 1. 股票池与主题 Schemas 测试
# ==============================================================================
def test_universe_info_valid() -> None:
    u = UniverseInfo(
        id="sp500",
        name="标普 500",
        description="标准普尔 500 成分股",
        symbol_count=503,
    )
    assert u.id == "sp500"
    assert u.symbol_count == 503

    # 不可变性测试
    with pytest.raises(ValidationError):
        u.symbol_count = 500  # type: ignore[misc]


def test_theme_stock_item_validation() -> None:
    item = ThemeStockItem(
        symbol=" nvda ",
        name="英伟达",
        sector="Technology",
        sub_industry="Semiconductors",
        market_cap_tier="mega",
    )
    assert item.symbol == "NVDA"

    # 空 symbol 校验
    with pytest.raises(ValidationError):
        ThemeStockItem(
            symbol="  ",
            name="空",
            sector="Tech",
            sub_industry="Semi",
            market_cap_tier="large",
        )


def test_theme_info_valid() -> None:
    theme = ThemeInfo(
        id="ai_chips",
        name="AI 芯片算力",
        category="tech",
        tagline="人工智能大模型的核心硬件底座",
        description="覆盖 GPU、ASIC、存储与晶圆代工龙头企业。",
        stocks=[
            ThemeStockItem(
                symbol="NVDA",
                name="英伟达",
                sector="Technology",
                sub_industry="Semiconductors",
                market_cap_tier="mega",
            )
        ],
    )
    assert theme.id == "ai_chips"
    assert len(theme.stocks) == 1
    assert theme.stocks[0].symbol == "NVDA"


# ==============================================================================
# 2. 筛选任务 Schemas 测试
# ==============================================================================
def test_screener_run_create_validation() -> None:
    req = ScreenerRunCreate(
        strategy_id="momentum_breakout",
        universe="sp500",
        params={"lookback": 20},
    )
    assert req.strategy_id == "momentum_breakout"
    assert req.universe == "sp500"
    assert req.custom_symbols is None

    # 自定义池规整
    req2 = ScreenerRunCreate(
        strategy_id="fundamental_value",
        universe="custom",
        custom_symbols=[" aapl ", "tsla", "msft "],
    )
    assert req2.custom_symbols == ["AAPL", "TSLA", "MSFT"]

    # 非法空自定义标的
    with pytest.raises(ValidationError):
        ScreenerRunCreate(
            strategy_id="test",
            universe="custom",
            custom_symbols=["  ", ""],
        )


def test_screener_result_item_valid() -> None:
    res = ScreenerResultItem(
        symbol=" aapl ",
        rank=1,
        score=Decimal("94.5000"),
        signal="STRONG_BUY",
        metrics_snapshot={"pe": 28.5, "rsi": 62.0},
    )
    assert res.symbol == "AAPL"
    assert res.rank == 1
    assert res.score == Decimal("94.5000")
    assert isinstance(res.score, Decimal)

    with pytest.raises(ValidationError):
        ScreenerResultItem(
            symbol="AAPL",
            rank=0,  # ge=1 约束
            score=Decimal("90"),
            signal="BUY",
        )


def test_screener_run_read_serialization() -> None:
    run_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    read = ScreenerRunRead(
        id=run_id,
        user_id=user_id,
        strategy_id="momentum",
        universe="nasdaq100",
        params={"rsi_threshold": 30},
        status="succeeded",
        total_symbols=100,
        matched_count=12,
        failed_count=2,
        error_message=None,
        results=[
            ScreenerResultItem(
                symbol="MSFT",
                rank=1,
                score=Decimal("88.0000"),
                signal="BUY",
                metrics_snapshot={"rsi": 28.5},
            )
        ],
        created_at=now,
        completed_at=now,
    )
    assert read.id == run_id
    assert read.matched_count == 12
    assert read.failed_count == 2
    assert len(read.results) == 1
    assert read.results[0].symbol == "MSFT"


# ==============================================================================
# 3. AI 主题卡片 Schemas 测试
# ==============================================================================
def test_theme_card_item_validation() -> None:
    card = ThemeCardItem(
        symbol=" nvda ",
        name="NVIDIA Corporation",
        one_line_intro="全球 AI 算力与 GPU 加速计算独占龙头",
        why_watch="数据中心生成式 AI 资本开支持续扩张的直接受益者",
        financial_strengths=["毛利率超过 75%", "数据中心业务连续 4 个季度同比翻倍"],
        main_risks=["地缘政治出口管制限制", "下游云巨头自研 ASIC 芯片竞争"],
        suitable_for=["追求高成长的进取型投资者", "AI 核心基础设施长期看好者"],
        more_attractive_when="估值回落至动态市盈率 35 倍以下或市场出现恐慌回调时",
    )
    assert card.symbol == "NVDA"
    assert len(card.financial_strengths) == 2

    # 空列表约束
    with pytest.raises(ValidationError):
        ThemeCardItem(
            symbol="NVDA",
            name="NVIDIA",
            one_line_intro="Intro",
            why_watch="Watch",
            financial_strengths=[],  # min_length=1 约束
            main_risks=["Risk"],
            suitable_for=["Investor"],
            more_attractive_when="When",
        )


def test_theme_cards_response() -> None:
    resp = ThemeCardsResponse(
        theme_id="ai_chips",
        theme_name="AI 芯片算力",
        cards=[
            ThemeCardItem(
                symbol="NVDA",
                name="NVIDIA",
                one_line_intro="GPU 龙头",
                why_watch="AI 军备竞赛",
                financial_strengths=["高毛利"],
                main_risks=["周期性"],
                suitable_for=["成长型"],
                more_attractive_when="回调时",
            )
        ],
        as_of=datetime.now(UTC),
        prompt_version="theme_card_v1",
    )
    assert resp.theme_id == "ai_chips"
    assert len(resp.cards) == 1


# ==============================================================================
# 4. 自选清单 Schemas 测试
# ==============================================================================
def test_watchlist_create_validation() -> None:
    wl = WatchlistCreate(
        name=" 重点观察白马 ",
        description="核心资产清单",
        is_default=True,
    )
    assert wl.name == "重点观察白马"
    assert wl.is_default is True

    # 空名称校验
    with pytest.raises(ValidationError):
        WatchlistCreate(name="   ")


def test_watchlist_update_validation() -> None:
    up = WatchlistUpdate(name=" 新名称 ")
    assert up.name == "新名称"

    with pytest.raises(ValidationError):
        WatchlistUpdate(name="")


def test_watchlist_item_create_validation() -> None:
    item = WatchlistItemCreate(
        symbol=" aapl ",
        notes="关注 WWDC 发布会表现",
        target_price=Decimal("210.5000"),
        theme_tags=["消费电子", "AI手机"],
    )
    assert item.symbol == "AAPL"
    assert item.target_price == Decimal("210.5000")

    # 目标价格必须大于 0
    with pytest.raises(ValidationError):
        WatchlistItemCreate(symbol="AAPL", target_price=Decimal("0"))

    with pytest.raises(ValidationError):
        WatchlistItemCreate(symbol="AAPL", target_price=Decimal("-10.5"))


def test_watchlist_item_update_validation() -> None:
    up = WatchlistItemUpdate(notes="修改备注", target_price=Decimal("220.0000"))
    assert up.notes == "修改备注"
    assert up.target_price == Decimal("220.0000")

    with pytest.raises(ValidationError):
        WatchlistItemUpdate(target_price=Decimal("-5"))


def test_watchlist_read_with_items() -> None:
    wl_id = uuid.uuid4()
    item_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    read = WatchlistRead(
        id=wl_id,
        user_id=user_id,
        name="默认自选",
        description="主观察池",
        is_default=True,
        items=[
            WatchlistItemRead(
                id=item_id,
                watchlist_id=wl_id,
                symbol="TSLA",
                notes="自动驾驶进展",
                target_price=Decimal("250.0000"),
                theme_tags=["新能源车", "AI机器人"],
                created_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )
    assert read.id == wl_id
    assert len(read.items) == 1
    assert read.items[0].symbol == "TSLA"


def test_export_to_research_request() -> None:
    req = ExportToResearchRequest(
        symbols=[" aapl ", "TSLA", "AAPL ", "msft"],
        target_action="compare",
    )
    # 保留顺序去重且规范为大写
    assert req.symbols == ["AAPL", "TSLA", "MSFT"]
    assert req.target_action == "compare"

    # 空列表拦截
    with pytest.raises(ValidationError):
        ExportToResearchRequest(symbols=[], target_action="compare")


# ==============================================================================
# 5. ORM 实体结构与表元数据测试
# ==============================================================================
def test_orm_screener_run_table_metadata() -> None:
    assert ScreenerRun.__tablename__ == "screener_runs"
    columns = ScreenerRun.__table__.columns

    assert "id" in columns
    assert "user_id" in columns
    assert "strategy_id" in columns
    assert "universe" in columns
    assert "params" in columns
    assert "status" in columns
    assert "total_symbols" in columns
    assert "matched_count" in columns
    assert "failed_count" in columns
    assert "error_message" in columns
    assert "created_at" in columns
    assert "completed_at" in columns

    # 外键约束检查
    fk = list(columns["user_id"].foreign_keys)[0]
    assert fk.target_fullname == "users.id"
    assert fk.ondelete == "CASCADE"


def test_orm_screener_result_table_metadata() -> None:
    assert ScreenerResult.__tablename__ == "screener_results"
    columns = ScreenerResult.__table__.columns

    assert "id" in columns
    assert "run_id" in columns
    assert "symbol" in columns
    assert "rank" in columns
    assert "score" in columns
    assert "signal" in columns
    assert "metrics_snapshot" in columns
    assert "created_at" in columns

    fk = list(columns["run_id"].foreign_keys)[0]
    assert fk.target_fullname == "screener_runs.id"
    assert fk.ondelete == "CASCADE"


def test_orm_watchlist_table_metadata() -> None:
    assert Watchlist.__tablename__ == "watchlists"
    columns = Watchlist.__table__.columns

    assert "id" in columns
    assert "user_id" in columns
    assert "name" in columns
    assert "description" in columns
    assert "is_default" in columns
    assert "created_at" in columns
    assert "updated_at" in columns

    fk = list(columns["user_id"].foreign_keys)[0]
    assert fk.target_fullname == "users.id"
    assert fk.ondelete == "CASCADE"

    # 复合唯一索引约束
    table = cast(Table, Watchlist.__table__)
    uq_names = {u.name for u in table.constraints if hasattr(u, "name")}
    assert "uq_watchlists_user_id_name" in uq_names


def test_orm_watchlist_item_table_metadata() -> None:
    assert WatchlistItem.__tablename__ == "watchlist_items"
    columns = WatchlistItem.__table__.columns

    assert "id" in columns
    assert "watchlist_id" in columns
    assert "symbol" in columns
    assert "notes" in columns
    assert "target_price" in columns
    assert "theme_tags" in columns
    assert "created_at" in columns

    fk = list(columns["watchlist_id"].foreign_keys)[0]
    assert fk.target_fullname == "watchlists.id"
    assert fk.ondelete == "CASCADE"

    item_table = cast(Table, WatchlistItem.__table__)
    uq_names = {u.name for u in item_table.constraints if hasattr(u, "name")}
    assert "uq_watchlist_items_watchlist_id_symbol" in uq_names


# ==============================================================================
# 6. 端口协议与运行时检查测试
# ==============================================================================
def test_protocols_runtime_checkable() -> None:
    class DummyUniverseManager:
        def list_universes(self) -> list[UniverseInfo]:
            return []

        def get_universe_symbols(
            self, universe_id: str, custom_symbols: list[str] | None = None
        ) -> list[str]:
            return []

        def list_themes(self) -> list[ThemeInfo]:
            return []

        def get_theme(self, theme_id: str) -> ThemeInfo:
            raise NotImplementedError

    mgr = DummyUniverseManager()
    assert isinstance(mgr, UniverseManagerProtocol)


def test_protocols_exported() -> None:
    for proto in (
        AIServiceProtocol,
        MarketDataServiceProtocol,
        StrategyServiceProtocol,
        UniverseManagerProtocol,
        ScreenerExecutorProtocol,
        ScreenerRepositoryProtocol,
        WatchlistRepositoryProtocol,
        ScreenerServiceProtocol,
    ):
        assert getattr(proto, "_is_runtime_protocol", False) is True


# ==============================================================================
# 7. 业务异常体系与错误码映射测试
# ==============================================================================
def test_screener_exceptions_hierarchy() -> None:
    err = UniverseNotFoundError("股票池未找到", details={"universe": "unknown"})
    assert isinstance(err, ScreenerError)
    assert isinstance(err, AppError)
    assert err.http_status == 404
    assert err.code == ErrorCode.NOT_FOUND
    assert err.details == {"universe": "unknown"}

    dup = DuplicateWatchlistItemError("已存在标的")
    assert dup.http_status == 409
    assert dup.code == ErrorCode.STATE_CONFLICT

    strat_err = StrategyNotFoundError("未定义策略")
    assert strat_err.http_status == 404
    assert strat_err.code == ErrorCode.NOT_FOUND

    theme_err = ThemeNotFoundError("主题不存在")
    assert theme_err.http_status == 404
    assert theme_err.code == ErrorCode.NOT_FOUND

    run_err = ScreenerRunNotFoundError("任务不存在")
    assert run_err.http_status == 404
    assert run_err.code == ErrorCode.NOT_FOUND

    wl_err = WatchlistNotFoundError("自选清单不存在")
    assert wl_err.http_status == 404
    assert wl_err.code == ErrorCode.NOT_FOUND

    wli_err = WatchlistItemNotFoundError("标的不存在")
    assert wli_err.http_status == 404
    assert wli_err.code == ErrorCode.NOT_FOUND

    exec_err = ScreenerExecutionError("执行失败")
    assert exec_err.http_status == 500
    assert exec_err.code == ErrorCode.INTERNAL_ERROR
