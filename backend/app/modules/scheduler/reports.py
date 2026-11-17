"""每日投研大盘与个人持仓简报生成器（M10-T05）。

对齐 docs/tasks/M10/CONTRACTS.md §2.4 结构化报告规范。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.scheduler.enums import DailyReportType
from app.modules.scheduler.models import DailyReport

__all__ = ["DailyReportGenerator"]

logger = get_logger("scheduler.reports")


class DailyReportGenerator:
    """负责每日大盘行情与用户持仓简报的生成、渲染与持久化。"""

    @staticmethod
    def _format_markdown_market_digest(
        trade_date: date,
        indices: dict[str, dict[str, Any]],
        alerts_count: int,
        movers: dict[str, list[dict[str, Any]]],
    ) -> str:
        lines = [
            f"# 📊 美股收盘大盘日报（{trade_date.isoformat()}）",
            "",
            "> 市场总结由 StockPilot 收盘批处理引擎自动生成，基于官方日线快照与量化模型。",
            "",
            "## 1. 核心大盘指数表现",
            "",
            "| 指数 / ETF | 最新点位 | 当日涨跌额 | 当日涨跌幅 |",
            "|---|---|---|---|",
        ]
        for sym, d in indices.items():
            close_str = f"${d.get('close', 'N/A')}"
            chg_str = f"{d.get('change', 'N/A')}"
            pct_str = f"{d.get('change_pct', 'N/A')}%"
            lines.append(f"| **{sym}** | {close_str} | {chg_str} | {pct_str} |")

        lines.extend(
            [
                "",
                "## 2. 市场异动与量化监控",
                "",
                (
                    f"- **智能告警触发**：全市场今日累计触发智能提醒与论文破裂规则"
                    f" **{alerts_count}** 次；"
                ),
            ]
        )

        gainers = movers.get("gainers", [])
        if gainers:
            formatted_gainers = []
            for g in gainers[:5]:
                sym = g.get("symbol", "")
                pct = str(g.get("change_pct", "")).strip()
                pct_display = pct if pct.startswith(("+", "-")) else f"+{pct}"
                formatted_gainers.append(f"{sym} ({pct_display}%)")
            lines.append(f"- **领涨标的**：{', '.join(formatted_gainers)}；")

        losers = movers.get("losers", [])
        if losers:
            formatted_losers = []
            for loser in losers[:5]:
                sym = loser.get("symbol", "")
                pct = str(loser.get("change_pct", "")).strip()
                pct_display = pct if pct.startswith(("+", "-")) else f"-{pct}"
                formatted_losers.append(f"{sym} ({pct_display}%)")
            lines.append(f"- **领跌标的**：{', '.join(formatted_losers)}；")

        lines.extend(
            [
                "",
                "---",
                "*免责声明：本简报仅供量化研究与投资参考，不构成任何买卖建议。市场有风险，投资需谨慎。*",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _format_markdown_portfolio_digest(
        trade_date: date,
        equity: Decimal,
        cash: Decimal,
        market_value: Decimal,
        drawdown: Decimal,
        positions: list[dict[str, Any]],
        trades: list[dict[str, Any]],
    ) -> str:
        dd_pct = f"{float(drawdown) * 100:.2f}%"
        lines = [
            f"# 💼 模拟投资组合收盘复盘报告（{trade_date.isoformat()}）",
            "",
            (
                f"**总资产净值 (Equity)**：`${equity:,.2f}` ｜ "
                f"**现金储备**：`${cash:,.2f}` ｜ "
                f"**持仓市值**：`${market_value:,.2f}`"
            ),
            f"**当前距离历史最高回撤**：`{dd_pct}`",
            "",
            "## 1. 当前持仓明细",
            "",
        ]

        if not positions:
            lines.append("*当前账户未持有任何股票标的（100% 现金观望）。*")
        else:
            lines.extend(
                [
                    "| 标的代码 | 持仓股数 | 持仓均价 | 收盘现价 | 浮动盈亏额 | 浮动盈亏率 |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for p in positions:
                sym = p.get("symbol", "")
                shares = p.get("shares", 0)
                cost = f"${p.get('cost_basis', 0):,.2f}"
                curr = f"${p.get('current_price', 0):,.2f}"
                unrealized = f"${p.get('unrealized_pnl', 0):,.2f}"
                pnl_pct = f"{p.get('unrealized_pnl_pct', 0):+.2f}%"
                row = f"| **{sym}** | {shares} | {cost} | {curr} | {unrealized} | {pnl_pct} |"
                lines.append(row)

        lines.extend(
            [
                "",
                "## 2. 当日成交记录",
                "",
            ]
        )
        if not trades:
            lines.append("*今日无新增成交订单。*")
        else:
            lines.extend(
                [
                    "| 时间 | 标的 | 方向 | 成交股数 | 成交价格 | 成交金额 |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for t in trades:
                sym = t.get("symbol", "")
                side = t.get("side", "").upper()
                sh = t.get("shares", 0)
                px = f"${t.get('price', 0):,.2f}"
                tot = f"${t.get('amount', 0):,.2f}"
                time_str = t.get("time", "")
                lines.append(f"| {time_str} | **{sym}** | {side} | {sh} | {px} | {tot} |")

        lines.extend(
            [
                "",
                "---",
                "*StockPilot 模拟交易系统自动结算，非真实资金账户。*",
            ]
        )
        return "\n".join(lines)

    async def generate_market_digest(
        self,
        session: AsyncSession,
        trade_date: date,
        market_snapshot: dict[str, Any] | None = None,
        alerts_count: int = 0,
    ) -> DailyReport:
        """生成并落库全市场收盘大盘日报（公共简报，user_id 为空）。"""
        snapshot = market_snapshot or {}
        indices_data: dict[str, dict[str, Any]] = {}

        # 默认从 snapshot 提取主要大盘指数
        for idx_sym in ("SPY", "QQQ", "DIA"):
            if idx_sym in snapshot and isinstance(snapshot[idx_sym], dict):
                info = snapshot[idx_sym]
                indices_data[idx_sym] = {
                    "close": str(info.get("current_price") or info.get("close") or "N/A"),
                    "change": str(info.get("change") or "0.00"),
                    "change_pct": str(info.get("change_pct") or "0.00"),
                }
            else:
                indices_data[idx_sym] = {
                    "close": "N/A",
                    "change": "0.00",
                    "change_pct": "0.00",
                }

        movers = snapshot.get("movers") or {"gainers": [], "losers": []}
        summary_md = self._format_markdown_market_digest(
            trade_date=trade_date,
            indices=indices_data,
            alerts_count=alerts_count,
            movers=movers,
        )

        title = f"{trade_date.isoformat()} 美股收盘大盘日报"
        payload = {
            "indices": indices_data,
            "alerts_count": alerts_count,
            "movers": movers,
            "trade_date": trade_date.isoformat(),
        }

        # 幂等查找已有记录进行更新，避免重复插入
        stmt = select(DailyReport).where(
            DailyReport.user_id.is_(None),
            DailyReport.report_date == trade_date,
            DailyReport.report_type == DailyReportType.MARKET_DIGEST.value,
        )
        res = await session.execute(stmt)
        report = res.scalar_one_or_none()

        if report is None:
            report = DailyReport(
                user_id=None,
                report_date=trade_date,
                report_type=DailyReportType.MARKET_DIGEST.value,
                title=title,
                summary=summary_md,
                payload=payload,
            )
            session.add(report)
        else:
            report.title = title
            report.summary = summary_md
            report.payload = payload
            report.created_at = datetime.now(UTC)

        await session.commit()
        await session.refresh(report)
        logger.info("market_digest_generated", report_id=str(report.id), trade_date=str(trade_date))
        return report

    async def generate_portfolio_digest(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        trade_date: date,
        equity: Decimal = Decimal("0"),
        cash: Decimal = Decimal("0"),
        market_value: Decimal = Decimal("0"),
        drawdown: Decimal = Decimal("0"),
        positions: list[dict[str, Any]] | None = None,
        trades: list[dict[str, Any]] | None = None,
    ) -> DailyReport:
        """生成并落库指定用户的模拟持仓日结复盘报告。"""
        pos_list = positions or []
        trade_list = trades or []

        summary_md = self._format_markdown_portfolio_digest(
            trade_date=trade_date,
            equity=equity,
            cash=cash,
            market_value=market_value,
            drawdown=drawdown,
            positions=pos_list,
            trades=trade_list,
        )

        title = f"[{trade_date.isoformat()}] 模拟投资组合收盘复盘报告"
        payload = {
            "account_id": str(account_id),
            "equity": str(equity),
            "cash": str(cash),
            "market_value": str(market_value),
            "drawdown": str(drawdown),
            "positions_count": len(pos_list),
            "trades_count": len(trade_list),
            "positions": pos_list,
            "trades": trade_list,
            "trade_date": trade_date.isoformat(),
        }

        stmt = select(DailyReport).where(
            DailyReport.user_id == user_id,
            DailyReport.report_date == trade_date,
            DailyReport.report_type == DailyReportType.PORTFOLIO_DIGEST.value,
        )
        res = await session.execute(stmt)
        report = res.scalar_one_or_none()

        if report is None:
            report = DailyReport(
                user_id=user_id,
                report_date=trade_date,
                report_type=DailyReportType.PORTFOLIO_DIGEST.value,
                title=title,
                summary=summary_md,
                payload=payload,
            )
            session.add(report)
        else:
            report.title = title
            report.summary = summary_md
            report.payload = payload
            report.created_at = datetime.now(UTC)

        await session.commit()
        await session.refresh(report)
        logger.info(
            "portfolio_digest_generated",
            user_id=str(user_id),
            account_id=str(account_id),
            report_id=str(report.id),
        )
        return report
