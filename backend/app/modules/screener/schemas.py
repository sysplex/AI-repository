"""M8 筛选器与主题自选 DTO Schemas，`CONTRACTS.md §1`。

包含股票池、主题、筛选任务、AI 主题卡片与自选清单的数据模型与校验。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ScreenerRunStatus = Literal["pending", "running", "succeeded", "failed"]


# ---------------------------------------------------------
# 股票池 (Universe) 与 主题 (Theme) 领域定义
# ---------------------------------------------------------
class UniverseInfo(BaseModel):
    """股票池基本信息。"""

    model_config = ConfigDict(frozen=True)

    id: str = Field(
        min_length=1,
        max_length=64,
        description="股票池标识符，如 sp500, nasdaq100, dow30, custom",
    )
    name: str = Field(min_length=1, max_length=64, description="股票池展示名称")
    description: str = Field(description="股票池说明")
    symbol_count: int = Field(ge=0, description="包含标的数量")


class ThemeStockItem(BaseModel):
    """主题预设成分股。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=16, description="股票代码")
    name: str = Field(min_length=1, max_length=128, description="公司简称")
    sector: str = Field(description="所属板块")
    sub_industry: str = Field(description="细分赛道/产业")
    market_cap_tier: str = Field(description="市值梯队：mega, large, mid, small")

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        s = v.strip().upper()
        if not s:
            raise ValueError("symbol 不能为空")
        return s


class ThemeInfo(BaseModel):
    """主题基本信息（F9 主题清单）。"""

    model_config = ConfigDict(frozen=True)

    id: str = Field(
        min_length=1,
        max_length=64,
        description="主题标识，如 ai_chips, glp1_weightloss",
    )
    name: str = Field(min_length=1, max_length=64, description="主题展示名称")
    category: str = Field(description="主题分类：tech, healthcare, dividend, energy, macro")
    tagline: str = Field(description="一句话导语")
    description: str = Field(description="新手向背景与逻辑说明")
    stocks: list[ThemeStockItem] = Field(default_factory=list, description="预设成分股列表")


# ---------------------------------------------------------
# 策略筛选任务 (Screener Runs & Results)
# ---------------------------------------------------------
class ScreenerRunCreate(BaseModel):
    """创建策略筛选任务请求。"""

    strategy_id: str = Field(min_length=1, max_length=64, description="预设策略标识符")
    universe: str = Field(min_length=1, max_length=64, description="目标股票池或自定义池标识")
    params: dict[str, Any] = Field(default_factory=dict, description="策略微调参数")
    custom_symbols: list[str] | None = Field(default=None, description="自定义股票池时的标的列表")

    @field_validator("custom_symbols")
    @classmethod
    def _validate_custom_symbols(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = [sym.strip().upper() for sym in v if sym.strip()]
        if not cleaned:
            raise ValueError("custom_symbols 列表不可为空")
        return cleaned


class ScreenerResultItem(BaseModel):
    """单个标的筛选结果与指标快照。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(description="标的代码")
    rank: int = Field(ge=1, description="综合排名")
    score: Decimal = Field(description="量化得分")
    signal: str = Field(description="策略信号，如 BUY, STRONG_BUY, NEUTRAL")
    metrics_snapshot: dict[str, Any] = Field(default_factory=dict, description="筛选时刻的核心指标")

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        return v.strip().upper()


class ScreenerRunRead(BaseModel):
    """筛选任务详情与结果返回。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    strategy_id: str
    universe: str
    params: dict[str, Any]
    status: ScreenerRunStatus
    total_symbols: int
    matched_count: int
    failed_count: int = 0
    error_message: str | None = None
    results: list[ScreenerResultItem] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None


# ---------------------------------------------------------
# F9 主题卡片（Theme Cards AI 响应模型）
# ---------------------------------------------------------
class ThemeCardItem(BaseModel):
    """AI 生成的单股主题卡片（严格受 facts 约束）。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(description="标的代码")
    name: str = Field(description="公司名称")
    one_line_intro: str = Field(description="一句话商业模式/行业地位")
    why_watch: str = Field(description="为什么值得关注/核心看点")
    financial_strengths: list[str] = Field(min_length=1, description="财务亮点（引用真实数据）")
    main_risks: list[str] = Field(min_length=1, description="主要潜在风险")
    suitable_for: list[str] = Field(min_length=1, description="适合的投资者类型画像")
    more_attractive_when: str = Field(description="何时或何种估值/市场情境下更具吸引力")

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        return v.strip().upper()


class ThemeCardsResponse(BaseModel):
    """主题卡片完整返回包。"""

    theme_id: str
    theme_name: str
    cards: list[ThemeCardItem]
    as_of: datetime
    prompt_version: str


# ---------------------------------------------------------
# 自选清单 (Watchlists & Items)
# ---------------------------------------------------------
class WatchlistItemCreate(BaseModel):
    """向自选清单添加标的请求。"""

    symbol: str = Field(min_length=1, max_length=16, description="标的代码")
    notes: str = Field(default="", max_length=500, description="自选备注说明")
    target_price: Decimal | None = Field(default=None, gt=0, description="目标监控价格")
    theme_tags: list[str] = Field(default_factory=list, description="用户关联的主题标签")

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        s = v.strip().upper()
        if not s:
            raise ValueError("symbol 不能为空")
        return s


class WatchlistItemUpdate(BaseModel):
    """更新自选清单标的请求。"""

    notes: str | None = Field(default=None, max_length=500, description="自选备注说明")
    target_price: Decimal | None = Field(default=None, gt=0, description="目标监控价格")
    theme_tags: list[str] | None = Field(default=None, description="用户关联的主题标签")


class WatchlistItemRead(BaseModel):
    """自选标的明细返回。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    watchlist_id: UUID
    symbol: str
    notes: str
    target_price: Decimal | None
    theme_tags: list[str]
    created_at: datetime


class WatchlistCreate(BaseModel):
    """创建自选清单请求。"""

    name: str = Field(min_length=1, max_length=64, description="清单名称")
    description: str = Field(default="", max_length=255, description="清单说明")
    is_default: bool = Field(default=False, description="是否设为默认自选")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("清单名称不能为空")
        return s


class WatchlistUpdate(BaseModel):
    """更新自选清单请求。"""

    name: str | None = Field(default=None, min_length=1, max_length=64, description="清单名称")
    description: str | None = Field(default=None, max_length=255, description="清单说明")
    is_default: bool | None = Field(default=None, description="是否设为默认自选")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("清单名称不能为空")
        return s


class WatchlistRead(BaseModel):
    """自选清单读取返回模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    description: str
    is_default: bool
    items: list[WatchlistItemRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ExportToResearchRequest(BaseModel):
    """一键将筛选或自选标的送入研报或对比。"""

    symbols: list[str] = Field(min_length=1, max_length=10, description="导出的股票代码列表")
    target_action: Literal["compare", "portfolio", "deep_research"] = Field(
        description="目标研报动作：对比/投资组合/深度研报"
    )

    @field_validator("symbols")
    @classmethod
    def _validate_symbols(cls, v: list[str]) -> list[str]:
        cleaned = [sym.strip().upper() for sym in v if sym.strip()]
        if not cleaned:
            raise ValueError("标的列表不可为空")
        return list(dict.fromkeys(cleaned))  # 保留顺序去重
