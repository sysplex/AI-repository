"""AI 投资建议持续复盘与超额收益评估服务（M10-T04）。

对齐 docs/tasks/M10/CONTRACTS.md §5 复盘收益率与相对 SPY 超额 Alpha 计算标准。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import (
    CalendarRangeError,
    next_trading_day,
    trading_days_between,
)
from app.core.logging import get_logger
from app.modules.ai.models import AIRecommendationOutcome, AIReport
from app.modules.ai.ports import PriceFeedProtocol
from app.modules.ai.schemas import (
    AIRecommendationOutcomeResponse,
    ReviewSummaryResponse,
    VerdictStatsResponse,
)

__all__ = ["ReviewService"]

logger = get_logger("ai.review_service")


class ReviewService:
    """AI 投资建议事后表现评估器与复盘聚合分析服务。"""

    def __init__(
        self,
        session: AsyncSession | None = None,
        price_feed: PriceFeedProtocol | None = None,
        benchmark_symbol: str = "SPY",
    ) -> None:
        self._session = session
        self._price_feed = price_feed
        self._benchmark_symbol = benchmark_symbol.strip().upper()

    def _get_session(self, session: AsyncSession | None) -> AsyncSession:
        sess = session or self._session
        if sess is None:
            raise ValueError("AsyncSession 必须传入或在 ReviewService 构造时初始化。")
        return sess

    # ==========================================
    # 1. 辅助方法：研报信息提取与交易日锚点
    # ==========================================

    @staticmethod
    def _extract_report_info(report: AIReport) -> tuple[str | None, str | None, Decimal | None]:
        """从 AIReport 实体中提取标的代码、推荐结论与基准价格 P0。"""
        params = report.params or {}
        payload = report.payload or {}

        # 1. 提取 symbol
        symbol = params.get("symbol") or payload.get("symbol")
        if symbol:
            symbol = str(symbol).strip().upper()

        # 2. 提取 verdict
        raw_verdict = (
            payload.get("verdict")
            or payload.get("recommendation")
            or payload.get("action")
            or params.get("verdict")
        )
        verdict = str(raw_verdict).strip().lower() if raw_verdict else "neutral"

        # 3. 提取出具时基准价格 P0
        price_val = None
        for k in ("price", "current_price", "price_at_report", "target_price"):
            if k in payload and payload[k] is not None:
                price_val = payload[k]
                break
            if k in params and params[k] is not None:
                price_val = params[k]
                break

        if price_val is None and isinstance(payload.get("quote"), dict):
            price_val = payload["quote"].get("price")

        p0: Decimal | None = None
        if price_val is not None:
            try:
                cleaned = str(price_val).replace("$", "").replace(",", "").strip()
                p0 = Decimal(cleaned)
            except Exception:
                p0 = None

        return symbol, verdict, p0

    @staticmethod
    def _calculate_horizon_dates(report_date: date) -> dict[int, date]:
        """计算出具日之后严格对应的 T+5, T+20, T+60 交易日。"""
        try:
            start_date = next_trading_day(report_date)
            # 60 交易日大约跨越 100~130 自然日，预留 150 天范围
            end_date = report_date + timedelta(days=150)
            t_days = trading_days_between(start_date, end_date)
        except (CalendarRangeError, ValueError):
            return {}

        res: dict[int, date] = {}
        if len(t_days) >= 5:
            res[5] = t_days[4]
        if len(t_days) >= 20:
            res[20] = t_days[19]
        if len(t_days) >= 60:
            res[60] = t_days[59]
        return res

    # ==========================================
    # 2. 核心扫描与回填评估引擎
    # ==========================================

    async def backfill_outcomes(
        self,
        *,
        as_of: date | None = None,
        batch_size: int = 100,
        session: AsyncSession | None = None,
    ) -> list[AIRecommendationOutcomeResponse]:
        """扫描历史 AI 研报，回填 5/20/60 日绝对表现与相对 SPY 超额 Alpha。

        满足幂等性与渐进式更新要求（已回填周期不重复计算，未到期周期到期自动补全）。
        """
        if self._price_feed is None:
            logger.warning("backfill_skipped_no_price_feed")
            return []

        sess = self._get_session(session)
        now_date = as_of or date.today()

        # 查询已完成的 AIReport
        stmt = (
            select(AIReport)
            .where(AIReport.status.in_(["success", "completed"]))
            .order_by(AIReport.created_at.asc())
            .limit(batch_size)
        )
        res = await sess.execute(stmt)
        reports = list(res.scalars().all())

        updated_outcomes: list[AIRecommendationOutcome] = []

        for report in reports:
            symbol, verdict, p0 = self._extract_report_info(report)
            if not symbol or not verdict:
                continue

            report_dt = report.created_at
            report_date = report_dt.date() if isinstance(report_dt, datetime) else report_dt

            # 若未在 payload 记录 P0，尝试从行情服务获取出具日当日价格
            if p0 is None or p0 <= 0:
                p0 = await self._price_feed.get_price(symbol, report_date)
            if p0 is None or p0 <= 0:
                # 依然无价格，跳过当前报告
                continue

            # 查询是否已存在 outcome 实体
            stmt_out = select(AIRecommendationOutcome).where(
                AIRecommendationOutcome.report_id == report.id
            )
            res_out = await sess.execute(stmt_out)
            outcome = res_out.scalar_one_or_none()

            if outcome is None:
                outcome = AIRecommendationOutcome(
                    report_id=report.id,
                    symbol=symbol,
                    verdict=verdict,
                    price_at_report=round(p0, 4),
                )
                sess.add(outcome)

            # 获取 T+5, T+20, T+60 对应交易日
            horizon_dates = self._calculate_horizon_dates(report_date)

            # 1. 回填 T+5
            if outcome.ret_5d is None and 5 in horizon_dates and horizon_dates[5] <= now_date:
                p5 = await self._price_feed.get_price(symbol, horizon_dates[5])
                if p5 is not None and p0 > 0:
                    outcome.ret_5d = round((p5 - p0) / p0, 4)

            # 2. 回填 T+20 与相对 SPY 超额 Alpha
            if outcome.ret_20d is None and 20 in horizon_dates and horizon_dates[20] <= now_date:
                p20 = await self._price_feed.get_price(symbol, horizon_dates[20])
                if p20 is not None and p0 > 0:
                    outcome.ret_20d = round((p20 - p0) / p0, 4)

            if (
                outcome.ret_20d is not None
                and outcome.ret_vs_spy_20d is None
                and 20 in horizon_dates
            ):
                # 计算 SPY 在出具日到 T+20 的基准收益
                spy_p0 = await self._price_feed.get_price(self._benchmark_symbol, report_date)
                spy_p20 = await self._price_feed.get_price(
                    self._benchmark_symbol, horizon_dates[20]
                )
                if spy_p0 and spy_p20 and spy_p0 > 0:
                    spy_ret = (spy_p20 - spy_p0) / spy_p0
                    outcome.ret_vs_spy_20d = round(outcome.ret_20d - spy_ret, 4)

            # 3. 回填 T+60
            if outcome.ret_60d is None and 60 in horizon_dates and horizon_dates[60] <= now_date:
                p60 = await self._price_feed.get_price(symbol, horizon_dates[60])
                if p60 is not None and p0 > 0:
                    outcome.ret_60d = round((p60 - p0) / p0, 4)

            updated_outcomes.append(outcome)

        await sess.commit()
        for o in updated_outcomes:
            await sess.refresh(o)

        logger.info(
            "ai_outcomes_backfilled",
            scanned_reports=len(reports),
            updated_outcomes=len(updated_outcomes),
        )
        return [AIRecommendationOutcomeResponse.model_validate(o) for o in updated_outcomes]

    # ==========================================
    # 3. 复盘看板聚合统计接口
    # ==========================================

    async def outcomes(
        self,
        *,
        verdict: str | None = None,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> ReviewSummaryResponse:
        """获取 AI 投资建议历史复盘统计与表现胜率聚合数据。"""
        sess = self._get_session(session)
        stmt = select(AIRecommendationOutcome)

        if verdict:
            stmt = stmt.where(AIRecommendationOutcome.verdict == verdict.strip().lower())
        if symbol:
            stmt = stmt.where(AIRecommendationOutcome.symbol == symbol.strip().upper())
        if start_date:
            stmt = stmt.where(AIRecommendationOutcome.created_at >= start_date)
        if end_date:
            stmt = stmt.where(AIRecommendationOutcome.created_at <= end_date)

        stmt = stmt.order_by(AIRecommendationOutcome.created_at.desc()).limit(limit).offset(offset)
        res = await sess.execute(stmt)
        outcomes_list = list(res.scalars().all())

        if not outcomes_list:
            return ReviewSummaryResponse(
                total_recommendations=0,
                evaluated_count=0,
            )

        # 聚合统计容器
        grouped: dict[str, list[AIRecommendationOutcome]] = defaultdict(list)
        all_5d: list[Decimal] = []
        all_20d: list[Decimal] = []
        all_60d: list[Decimal] = []
        all_alpha: list[Decimal] = []
        evaluated_count = 0

        for item in outcomes_list:
            grouped[item.verdict].append(item)
            has_eval = False
            if item.ret_5d is not None:
                all_5d.append(item.ret_5d)
                has_eval = True
            if item.ret_20d is not None:
                all_20d.append(item.ret_20d)
                has_eval = True
            if item.ret_60d is not None:
                all_60d.append(item.ret_60d)
                has_eval = True
            if item.ret_vs_spy_20d is not None:
                all_alpha.append(item.ret_vs_spy_20d)
            if has_eval:
                evaluated_count += 1

        def _avg(vals: Sequence[Decimal]) -> Decimal | None:
            if not vals:
                return None
            return round(sum(vals) / Decimal(len(vals)), 4)

        # 构建按 verdict 统计字典
        by_verdict: dict[str, VerdictStatsResponse] = {}
        bullish_verdicts = {"buy", "strong_buy", "holdable"}
        bearish_verdicts = {"avoid", "sell", "not_recommended"}

        global_wins = 0
        global_win_evals = 0

        for v_name, items in grouped.items():
            v_5d = [i.ret_5d for i in items if i.ret_5d is not None]
            v_20d = [i.ret_20d for i in items if i.ret_20d is not None]
            v_60d = [i.ret_60d for i in items if i.ret_60d is not None]
            v_alpha = [i.ret_vs_spy_20d for i in items if i.ret_vs_spy_20d is not None]

            # 胜率计算：看多者以 20 日收益 > 0 为胜；看空/避开者以 20 日收益 <= 0 为胜
            v_wins = 0
            for i in items:
                if i.ret_20d is not None and (
                    (v_name in bullish_verdicts and i.ret_20d > Decimal("0"))
                    or (v_name in bearish_verdicts and i.ret_20d <= Decimal("0"))
                    or (
                        v_name not in bullish_verdicts
                        and v_name not in bearish_verdicts
                        and abs(i.ret_20d) <= Decimal("0.05")
                    )
                ):
                    v_wins += 1

            win_rate = round(Decimal(v_wins) / Decimal(len(v_20d)), 4) if len(v_20d) > 0 else None

            global_wins += v_wins
            global_win_evals += len(v_20d)

            by_verdict[v_name] = VerdictStatsResponse(
                verdict=v_name,
                total_count=len(items),
                evaluated_5d_count=len(v_5d),
                evaluated_20d_count=len(v_20d),
                evaluated_60d_count=len(v_60d),
                avg_return_5d=_avg(v_5d),
                avg_return_20d=_avg(v_20d),
                avg_return_60d=_avg(v_60d),
                avg_alpha_20d=_avg(v_alpha),
                win_rate_20d=win_rate,
            )

        overall_win_rate = (
            round(Decimal(global_wins) / Decimal(global_win_evals), 4)
            if global_win_evals > 0
            else None
        )

        return ReviewSummaryResponse(
            total_recommendations=len(outcomes_list),
            evaluated_count=evaluated_count,
            avg_return_5d=_avg(all_5d),
            avg_return_20d=_avg(all_20d),
            avg_return_60d=_avg(all_60d),
            avg_alpha_20d=_avg(all_alpha),
            win_rate_20d=overall_win_rate,
            by_verdict=by_verdict,
            items=[AIRecommendationOutcomeResponse.model_validate(x) for x in outcomes_list],
        )
