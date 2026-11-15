"""M8-T02 股票池服务与主题股票库（UniverseManager）单元测试。

测试覆盖：
- 基准股票池列表获取（sp500, nasdaq100, dow30, custom）
- 股票池成分标的解析、大小写容错、去重与自定义股票池校验
- 主题前缀（theme:xxx）兼容解析
- 不存在股票池异常防御 (UniverseNotFoundError)
- F9 预设热门主题列表与详情查询完整性
- 不存在主题异常防御 (ThemeNotFoundError)
- 动态注册股票池与主题扩展性
- UniverseManagerProtocol 协议一致性与全局单例
"""

from __future__ import annotations

import pytest

from app.modules.screener.exceptions import ThemeNotFoundError, UniverseNotFoundError
from app.modules.screener.ports import UniverseManagerProtocol
from app.modules.screener.schemas import ThemeInfo, ThemeStockItem
from app.modules.screener.universe import (
    DOW30_SYMBOLS,
    NASDAQ100_SYMBOLS,
    PRESET_THEMES,
    SP500_SYMBOLS,
    UniverseManager,
    default_universe_manager,
)


@pytest.fixture
def manager() -> UniverseManager:
    return UniverseManager()


# ==============================================================================
# 1. 股票池基础列表测试
# ==============================================================================
def test_list_universes(manager: UniverseManager) -> None:
    universes = manager.list_universes()
    u_map = {u.id: u for u in universes}

    assert "sp500" in u_map
    assert "nasdaq100" in u_map
    assert "dow30" in u_map
    assert "custom" in u_map

    assert u_map["dow30"].symbol_count == 30
    assert u_map["nasdaq100"].symbol_count == 100
    assert u_map["sp500"].symbol_count >= 500
    assert u_map["custom"].symbol_count == 0


# ==============================================================================
# 2. 股票池成分股获取测试
# ==============================================================================
def test_get_universe_symbols_standard(manager: UniverseManager) -> None:
    # 标普 500
    sp500 = manager.get_universe_symbols("sp500")
    assert len(sp500) >= 500
    assert "AAPL" in sp500
    assert "MSFT" in sp500

    # 大小写与空格容错
    sp500_upper = manager.get_universe_symbols("  SP500  ")
    assert sp500_upper == sp500

    # 纳指 100
    nasdaq = manager.get_universe_symbols("nasdaq100")
    assert len(nasdaq) == 100
    assert "NVDA" in nasdaq

    # 道指 30
    dow = manager.get_universe_symbols("dow30")
    assert len(dow) == 30
    assert "KO" in dow

    # 返回的应当是独立副本，修改不影响内部状态
    dow.append("FAKE")
    assert "FAKE" not in manager.get_universe_symbols("dow30")


def test_get_universe_symbols_custom(manager: UniverseManager) -> None:
    # 正常自定义池
    symbols = manager.get_universe_symbols(
        "custom", custom_symbols=[" aapl ", "TSLA", "AAPL", "msft "]
    )
    assert symbols == ["AAPL", "TSLA", "MSFT"]

    # 空列表异常拦截
    with pytest.raises(UniverseNotFoundError) as exc_info:
        manager.get_universe_symbols("custom", custom_symbols=[])
    assert "未指定任何标的代码" in str(exc_info.value)

    # None 拦截
    with pytest.raises(UniverseNotFoundError):
        manager.get_universe_symbols("custom", custom_symbols=None)

    # 全空白字符拦截
    with pytest.raises(UniverseNotFoundError):
        manager.get_universe_symbols("custom", custom_symbols=["  ", ""])


def test_get_universe_symbols_theme_forwarding(manager: UniverseManager) -> None:
    # 支持 theme:xxx 语法读取主题成分股
    theme_symbols = manager.get_universe_symbols("theme:ai_chips")
    assert "NVDA" in theme_symbols
    assert "AMD" in theme_symbols

    # 支持直接以主题 id 读取
    theme_symbols_direct = manager.get_universe_symbols("ai_chips")
    assert theme_symbols_direct == theme_symbols


def test_get_universe_symbols_not_found(manager: UniverseManager) -> None:
    with pytest.raises(UniverseNotFoundError) as exc_info:
        manager.get_universe_symbols("unknown_pool")
    assert "未找到标识为 'unknown_pool' 的股票池" in str(exc_info.value)
    assert exc_info.value.details == {"universe": "unknown_pool"}


# ==============================================================================
# 3. F9 预设热门主题测试
# ==============================================================================
def test_list_themes(manager: UniverseManager) -> None:
    themes = manager.list_themes()
    assert len(themes) >= 5  # 至少 5 个预设主题

    theme_ids = {t.id for t in themes}
    assert "ai_chips" in theme_ids
    assert "glp1_weightloss" in theme_ids
    assert "high_dividend" in theme_ids
    assert "cyber_security" in theme_ids
    assert "cloud_saas" in theme_ids
    assert "clean_energy" in theme_ids

    # 验证每个主题的数据完整性
    for t in themes:
        assert len(t.name) > 0
        assert len(t.tagline) > 0
        assert len(t.description) > 0
        assert len(t.stocks) >= 3
        for stock in t.stocks:
            assert stock.symbol == stock.symbol.upper()
            assert len(stock.name) > 0
            assert len(stock.sector) > 0
            assert stock.market_cap_tier in ("mega", "large", "mid", "small")


def test_get_theme_success(manager: UniverseManager) -> None:
    ai_theme = manager.get_theme("ai_chips")
    assert ai_theme.id == "ai_chips"
    assert ai_theme.name == "AI 芯片与算力底座"
    assert ai_theme.category == "tech"
    symbols = [s.symbol for s in ai_theme.stocks]
    assert "NVDA" in symbols
    assert "TSM" in symbols

    # 容错测试：带 theme: 前缀与空格大小写
    ai_theme_prefix = manager.get_theme("  THEME:AI_CHIPS  ")
    assert ai_theme_prefix.id == "ai_chips"


def test_get_theme_not_found(manager: UniverseManager) -> None:
    with pytest.raises(ThemeNotFoundError) as exc_info:
        manager.get_theme("quantum_teleportation")
    assert "未找到标识为 'quantum_teleportation' 的主题" in str(exc_info.value)
    assert exc_info.value.details == {"theme_id": "quantum_teleportation"}


# ==============================================================================
# 4. 动态注册股票池与主题扩展测试
# ==============================================================================
def test_dynamic_registration(manager: UniverseManager) -> None:
    # 动态注册股票池
    manager.register_universe(
        universe_id="crypto_miners",
        name="加密矿业股票池",
        description="比特币与以太坊挖矿及算力托管企业",
        symbols=[" mara ", "RIOT", "CLSK", "MARA "],
    )

    u_list = manager.list_universes()
    u_map = {u.id: u for u in u_list}
    assert "crypto_miners" in u_map
    assert u_map["crypto_miners"].symbol_count == 3  # 去重后 3 只

    symbols = manager.get_universe_symbols("crypto_miners")
    assert symbols == ["MARA", "RIOT", "CLSK"]

    # 动态注册新主题
    new_theme = ThemeInfo(
        id="space_economy",
        name="商业航天与太空经济",
        category="macro",
        tagline="探索近地轨道与深空商业化新机遇",
        description="卫星互联网、火箭发射与太空载荷研发企业。",
        stocks=[
            ThemeStockItem(
                symbol="RKLB",
                name="Rocket Lab USA",
                sector="Industrials",
                sub_industry="Aerospace",
                market_cap_tier="mid",
            )
        ],
    )
    manager.register_theme(new_theme)
    assert manager.get_theme("space_economy").name == "商业航天与太空经济"
    assert manager.get_universe_symbols("theme:space_economy") == ["RKLB"]


# ==============================================================================
# 5. 协议一致性与全局单例测试
# ==============================================================================
def test_protocol_conformance_and_singleton() -> None:
    assert isinstance(default_universe_manager, UniverseManagerProtocol)
    assert isinstance(UniverseManager(), UniverseManagerProtocol)

    # 预设常量验证
    assert len(DOW30_SYMBOLS) == 30
    assert len(NASDAQ100_SYMBOLS) == 100
    assert len(SP500_SYMBOLS) >= 500
    assert len(PRESET_THEMES) >= 6
