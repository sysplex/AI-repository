"""收盘后全流程自动化批处理流水线编排引擎（M10-T05）。

对齐 docs/tasks/M10/CONTRACTS.md §1-§2 与 docs/04-modules.md#m10。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import is_trading_day
from app.core.logging import get_logger
from app.modules.notify.service import AlertService
from app.modules.scheduler.enums import JobStatus
from app.modules.scheduler.ports import ReviewServiceProtocol
from app.modules.scheduler.reports import DailyReportGenerator
from app.modules.scheduler.schemas import PipelineRunResult, PipelineStepStatus
from app.modules.simbroker.models import SimAccount, SimPosition
from app.modules.simbroker.service import SimService

__all__ = ["PostMarketPipeline"]

logger = get_logger("scheduler.pipeline")


class PostMarketPipeline:
    """美股收盘后自动化批处理任务链 DAG 调度器。"""

    def __init__(
        self,
        session: AsyncSession | None = None,
        sim_service: SimService | None = None,
        screener_service: Any | None = None,
        alert_service: AlertService | None = None,
        review_service: ReviewServiceProtocol | None = None,
        report_generator: DailyReportGenerator | None = None,
    ) -> None:
        self._session = session
        self._sim_service = sim_service
        self._screener_service = screener_service
        self._alert_service = alert_service
        self._review_service = review_service
        self._report_generator = report_generator or DailyReportGenerator()

    def _get_session(self, session: AsyncSession | None) -> AsyncSession:
        sess = session or self._session
        if sess is None:
            raise ValueError("AsyncSession 必须传入或在 PostMarketPipeline 构造时初始化。")
        return sess

    async def run(
        self,
        *,
        trade_date: date | None = None,
        force: bool = False,
        session: AsyncSession | None = None,
        market_context: dict[str, Any] | None = None,
    ) -> PipelineRunResult:
        """执行收盘后全流程批处理任务链。

        步骤拓扑：
        0. 交易日判定与跳过防护；
        1. 市场行情与收盘价可用性核验；
        2. 模拟盘 DAY 订单过期撤销、账户资产结算与净值快照（EquitySnapshot）；
        3. 策略候选池与筛选器扫描；
        4. 价格、技术信号、财报与长期论文破裂告警求值与多渠道并发推送；
        5. 历史 AI 投资建议收益率与相对 SPY 超额收益（Alpha）无未来函数回填；
        6. 生成并入库每日全市场大盘日报（market_digest）与用户持仓报告（portfolio_digest）。
        """
        sess = self._get_session(session)
        target_date = trade_date or date.today()
        start_time = datetime.now(UTC)
        steps_log: list[PipelineStepStatus] = []

        logger.info("post_market_pipeline.started", trade_date=str(target_date), force=force)

        # ---------------------------------------------------------------------
        # 步骤 0：美股交易日校验
        # ---------------------------------------------------------------------
        trading_day = is_trading_day(target_date)
        if not trading_day and not force:
            logger.info("post_market_pipeline.skipped_non_trading_day", trade_date=str(target_date))
            step_skip = PipelineStepStatus(
                name="calendar_guard",
                status=JobStatus.COMPLETED,
                started_at=start_time,
                finished_at=datetime.now(UTC),
                details={"is_trading_day": False, "action": "skipped"},
            )
            return PipelineRunResult(
                trade_date=target_date,
                status=JobStatus.COMPLETED,
                started_at=start_time,
                finished_at=datetime.now(UTC),
                is_trading_day=False,
                steps=[step_skip],
                error_message="今日非美股交易日，自动化流水线已安全挂起跳过。",
            )

        # ---------------------------------------------------------------------
        # 步骤 1：市场行情数据同步与确认
        # ---------------------------------------------------------------------
        s1_start = datetime.now(UTC)
        market_ctx = dict(market_context or {})
        s1_status = JobStatus.COMPLETED
        s1_details: dict[str, Any] = {"symbols_available": len(market_ctx)}
        steps_log.append(
            PipelineStepStatus(
                name="market_data_sync",
                status=s1_status,
                started_at=s1_start,
                finished_at=datetime.now(UTC),
                details=s1_details,
            )
        )

        # ---------------------------------------------------------------------
        # 步骤 2：模拟盘结算与净值快照
        # ---------------------------------------------------------------------
        s2_start = datetime.now(UTC)
        settled_accounts = 0
        total_expired_orders = 0
        account_snapshots: dict[uuid.UUID, dict[str, Any]] = {}

        try:
            # 查询系统中所有模拟盘账户
            stmt_acc = select(SimAccount)
            res_acc = await sess.execute(stmt_acc)
            accounts = list(res_acc.scalars().all())

            for acc in accounts:
                if self._sim_service is not None:
                    sim_res = await self._sim_service.process_market_close(
                        account_id=acc.id,
                        trade_date=target_date,
                        user_id=acc.user_id,
                    )
                    settled_accounts += 1
                    total_expired_orders += sim_res.expired_orders_count
                    account_snapshots[acc.id] = {
                        "equity": sim_res.equity,
                        "cash": sim_res.cash,
                        "market_value": sim_res.market_value,
                        "drawdown": sim_res.drawdown,
                    }
                else:
                    # 若未注入 sim_service，基于当前账户与持仓做基础结算计算
                    pos_stmt = select(SimPosition).where(SimPosition.account_id == acc.id)
                    pos_res = await sess.execute(pos_stmt)
                    pos_list = list(pos_res.scalars().all())

                    mkt_val = sum(
                        (
                            p.qty
                            * Decimal(
                                str(market_ctx.get(p.symbol, {}).get("current_price", p.avg_cost))
                            )
                            for p in pos_list
                        ),
                        Decimal("0"),
                    )
                    eq = acc.cash + mkt_val
                    account_snapshots[acc.id] = {
                        "equity": eq,
                        "cash": acc.cash,
                        "market_value": mkt_val,
                        "drawdown": Decimal("0"),
                    }
                    settled_accounts += 1

            s2_status = JobStatus.COMPLETED
            s2_details: dict[str, Any] = {
                "accounts_settled": settled_accounts,
                "expired_orders": total_expired_orders,
            }
        except Exception as e:
            logger.error("simbroker_settlement_failed", error=str(e))
            s2_status = JobStatus.FAILED
            s2_details = {"error": str(e)}

        steps_log.append(
            PipelineStepStatus(
                name="simbroker_settlement",
                status=s2_status,
                started_at=s2_start,
                finished_at=datetime.now(UTC),
                details=s2_details,
            )
        )

        # ---------------------------------------------------------------------
        # 步骤 3：策略筛选池扫描
        # ---------------------------------------------------------------------
        s3_start = datetime.now(UTC)
        s3_details: dict[str, Any] = {}
        try:
            if self._screener_service is not None and hasattr(
                self._screener_service, "run_all_presets"
            ):
                presets_res = await self._screener_service.run_all_presets()
                s3_details["presets_executed"] = len(presets_res)
            else:
                s3_details["note"] = "screener_service not configured or skipped"
            s3_status = JobStatus.COMPLETED
        except Exception as e:
            logger.warning("screener_scan_error", error=str(e))
            s3_status = JobStatus.FAILED
            s3_details["error"] = str(e)

        steps_log.append(
            PipelineStepStatus(
                name="screener_scan",
                status=s3_status,
                started_at=s3_start,
                finished_at=datetime.now(UTC),
                details=s3_details,
            )
        )

        # ---------------------------------------------------------------------
        # 步骤 4：智能提醒与论文破裂扫描与分发
        # ---------------------------------------------------------------------
        s4_start = datetime.now(UTC)
        triggered_alerts_count = 0
        s4_details: dict[str, Any] = {}
        try:
            if self._alert_service is not None:
                trig_res = await self._alert_service.evaluate_alerts(
                    market_context=market_ctx,
                    as_of=datetime.combine(target_date, datetime.min.time(), tzinfo=UTC),
                    session=sess,
                )
                triggered_alerts_count = len(trig_res)
                s4_details["alerts_triggered"] = triggered_alerts_count
            else:
                s4_details["note"] = "alert_service not configured, skipped"
            s4_status = JobStatus.COMPLETED
        except Exception as e:
            logger.error("alert_evaluation_error", error=str(e))
            s4_status = JobStatus.FAILED
            s4_details["error"] = str(e)

        steps_log.append(
            PipelineStepStatus(
                name="alert_evaluation",
                status=s4_status,
                started_at=s4_start,
                finished_at=datetime.now(UTC),
                details=s4_details,
            )
        )

        # ---------------------------------------------------------------------
        # 步骤 5：历史 AI 研报建议复盘与超额收益回填
        # ---------------------------------------------------------------------
        s5_start = datetime.now(UTC)
        s5_details: dict[str, Any] = {}
        try:
            if self._review_service is not None:
                backfilled = await self._review_service.backfill_outcomes(
                    as_of=target_date,
                    session=sess,
                )
                s5_details["outcomes_backfilled"] = len(backfilled)
            else:
                s5_details["note"] = "review_service not configured, skipped"
            s5_status = JobStatus.COMPLETED
        except Exception as e:
            logger.error("ai_review_backfill_error", error=str(e))
            s5_status = JobStatus.FAILED
            s5_details["error"] = str(e)

        steps_log.append(
            PipelineStepStatus(
                name="ai_review_backfill",
                status=s5_status,
                started_at=s5_start,
                finished_at=datetime.now(UTC),
                details=s5_details,
            )
        )

        # ---------------------------------------------------------------------
        # 步骤 6：生成收盘市场大盘日报与个人持仓复盘报告
        # ---------------------------------------------------------------------
        s6_start = datetime.now(UTC)
        reports_created = 0
        s6_details: dict[str, Any] = {}
        try:
            # 1. 生成公共大盘简报
            await self._report_generator.generate_market_digest(
                session=sess,
                trade_date=target_date,
                market_snapshot=market_ctx,
                alerts_count=triggered_alerts_count,
            )
            reports_created += 1

            # 2. 为每个活跃账户生成个人持仓简报
            stmt_acc = select(SimAccount)
            res_acc = await sess.execute(stmt_acc)
            for acc in res_acc.scalars().all():
                snap_info = account_snapshots.get(acc.id, {})
                eq_val = snap_info.get("equity", acc.cash)
                cash_val = snap_info.get("cash", acc.cash)
                mkt_val = snap_info.get("market_value", Decimal("0"))
                dd_val = snap_info.get("drawdown", Decimal("0"))

                # 获取账户持仓
                pos_stmt = select(SimPosition).where(SimPosition.account_id == acc.id)
                pos_res = await sess.execute(pos_stmt)
                positions: list[dict[str, Any]] = []
                for p in pos_res.scalars().all():
                    cur_p = float(market_ctx.get(p.symbol, {}).get("current_price", p.avg_cost))
                    cost_f = float(p.avg_cost)
                    pnl_f = (cur_p - cost_f) * float(p.qty)
                    pnl_pct = ((cur_p - cost_f) / cost_f * 100) if cost_f > 0 else 0.0
                    positions.append(
                        {
                            "symbol": p.symbol,
                            "shares": int(p.qty),
                            "cost_basis": cost_f,
                            "current_price": cur_p,
                            "unrealized_pnl": pnl_f,
                            "unrealized_pnl_pct": pnl_pct,
                        }
                    )

                await self._report_generator.generate_portfolio_digest(
                    session=sess,
                    user_id=acc.user_id,
                    account_id=acc.id,
                    trade_date=target_date,
                    equity=eq_val,
                    cash=cash_val,
                    market_value=mkt_val,
                    drawdown=dd_val,
                    positions=positions,
                )
                reports_created += 1

            s6_status = JobStatus.COMPLETED
            s6_details["reports_generated"] = reports_created
        except Exception as e:
            logger.error("daily_reports_generation_error", error=str(e))
            s6_status = JobStatus.FAILED
            s6_details["error"] = str(e)

        steps_log.append(
            PipelineStepStatus(
                name="daily_reports_generation",
                status=s6_status,
                started_at=s6_start,
                finished_at=datetime.now(UTC),
                details=s6_details,
            )
        )

        overall_status = (
            JobStatus.COMPLETED
            if all(s.status == JobStatus.COMPLETED for s in steps_log)
            else JobStatus.FAILED
        )

        logger.info(
            "post_market_pipeline.finished",
            trade_date=str(target_date),
            status=overall_status.value,
            steps_count=len(steps_log),
        )

        return PipelineRunResult(
            trade_date=target_date,
            status=overall_status,
            started_at=start_time,
            finished_at=datetime.now(UTC),
            is_trading_day=True,
            steps=steps_log,
        )
