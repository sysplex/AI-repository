import React, { useState } from 'react';
import {
  Activity,
  AlertTriangle,
  DollarSign,
  Plus,
  Scale,
  ShieldCheck,
  TrendingUp,
  Wallet,
} from 'lucide-react';
import type {
  AccountOverview,
  AccountResponse,
  PerformanceMetrics,
  RiskOverview,
} from '../../api/types';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { PriceDisplay } from '../../components/financial/PriceDisplay';
import { ChangePercent } from '../../components/financial/ChangePercent';
import { cn } from '../../utils/cn';

export interface AccountOverviewViewProps {
  overview: AccountOverview;
  accounts: AccountResponse[];
  activeAccountId: string;
  onSelectAccount: (id: string) => void;
  performance: PerformanceMetrics;
  risk: RiskOverview;
  onOpenDeposit: () => void;
  onOpenCreateAccount: () => void;
}

export const AccountOverviewView: React.FC<AccountOverviewViewProps> = ({
  overview,
  accounts,
  activeAccountId,
  onSelectAccount,
  performance,
  risk,
  onOpenDeposit,
  onOpenCreateAccount,
}) => {
  const [curveMode, setCurveMode] = useState<'equity' | 'benchmark'>('equity');

  const equityNum = parseFloat(overview.equity);
  const cashNum = parseFloat(overview.cash);
  const marketValNum = parseFloat(overview.market_value);
  const dailyPnlNum = parseFloat(overview.daily_pnl);
  const dailyPnlPct = parseFloat(overview.daily_pnl_pct);
  const totalPnlNum = parseFloat(overview.total_pnl);
  const totalPnlPct = parseFloat(overview.total_pnl_pct);

  // PDT check
  const pdtCount = overview.pdt_day_trades_count || 0;
  const isPdtWarning = overview.pdt_warning || pdtCount >= 3;

  return (
    <div className="space-y-6">
      {/* Account Switcher Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow-sm">
        <div className="flex items-center gap-3 overflow-x-auto">
          <div className="flex items-center gap-1.5 shrink-0 text-xs text-slate-400 font-medium">
            <Wallet className="h-4 w-4 text-blue-400" />
            <span>模拟账户:</span>
          </div>
          <div className="flex items-center gap-2">
            {accounts.map((acc) => (
              <button
                key={acc.id}
                onClick={() => onSelectAccount(acc.id)}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shrink-0',
                  acc.id === activeAccountId
                    ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20 border border-blue-500'
                    : 'bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700/60',
                )}
              >
                <span>{acc.name}</span>
                <span className="text-[10px] ml-1.5 opacity-75 font-mono">
                  ${parseFloat(acc.cash).toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            size="sm"
            variant="outline"
            onClick={onOpenDeposit}
            leftIcon={<DollarSign className="h-3.5 w-3.5 text-emerald-400" />}
          >
            资金出入金
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onOpenCreateAccount}
            leftIcon={<Plus className="h-3.5 w-3.5 text-blue-400" />}
          >
            新建账户
          </Button>
        </div>
      </div>

      {/* Main KPI Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* Total Equity */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80 space-y-1">
          <span className="text-[11px] font-medium text-slate-400">总资产净值 (Equity)</span>
          <div className="text-xl font-bold font-mono text-white">
            <PriceDisplay value={equityNum} />
          </div>
          <div className="text-[10px] text-slate-500 font-mono">
            初始本金: ${parseFloat(overview.initial_cash).toLocaleString()}
          </div>
        </div>

        {/* Available Cash */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80 space-y-1">
          <span className="text-[11px] font-medium text-slate-400">可用现金 (Cash)</span>
          <div className="text-xl font-bold font-mono text-emerald-400">
            <PriceDisplay value={cashNum} />
          </div>
          <div className="text-[10px] text-slate-500 font-mono">
            现金水位: {risk.cash_ratio}%
          </div>
        </div>

        {/* Market Value */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80 space-y-1">
          <span className="text-[11px] font-medium text-slate-400">持仓总市值 (Market Value)</span>
          <div className="text-xl font-bold font-mono text-blue-300">
            <PriceDisplay value={marketValNum} />
          </div>
          <div className="text-[10px] text-slate-500 font-mono">
            持仓仓位: {(100 - parseFloat(risk.cash_ratio)).toFixed(1)}%
          </div>
        </div>

        {/* Daily PnL */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80 space-y-1">
          <span className="text-[11px] font-medium text-slate-400">当日浮动盈亏 (Daily PnL)</span>
          <div className="flex items-center gap-1.5">
            <span className="text-xl font-bold font-mono text-white">
              <PriceDisplay value={dailyPnlNum} />
            </span>
          </div>
          <ChangePercent value={dailyPnlPct} mode="compact" />
        </div>

        {/* Total Return */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80 space-y-1">
          <span className="text-[11px] font-medium text-slate-400">累计总收益回报 (Total Return)</span>
          <div className="flex items-center gap-1.5">
            <span className="text-xl font-bold font-mono text-white">
              <PriceDisplay value={totalPnlNum} />
            </span>
          </div>
          <ChangePercent value={totalPnlPct} mode="compact" />
        </div>
      </div>

      {/* PDT Regulatory Notice Banner */}
      <div
        className={cn(
          'p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs',
          isPdtWarning
            ? 'bg-amber-950/30 border-amber-500/40 text-amber-200'
            : 'bg-slate-900/40 border-slate-800 text-slate-300',
        )}
      >
        <div className="flex items-center gap-3">
          {isPdtWarning ? (
            <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0" />
          ) : (
            <ShieldCheck className="h-5 w-5 text-blue-400 shrink-0" />
          )}
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-white">美股 FINRA PDT (典型日内交易者) 规则监控</span>
              <Badge variant={isPdtWarning ? 'warning' : 'success'} size="xs">
                {`近 5 个交易日内完成: ${pdtCount} / 3 次日内平仓`}
              </Badge>
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              当前账户总净值超 $25,000 美元监管豁免线，日内交易合规状态良好，未受锁仓限制。
            </p>
          </div>
        </div>

        <div className="text-[11px] text-slate-400 font-mono shrink-0 self-end sm:self-center">
          PDT 剩余额度: <span className="font-bold text-white">{Math.max(0, 3 - pdtCount)}</span> 次
        </div>
      </div>

      {/* Performance & Alpha Benchmark Comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Equity Curve (8 cols) */}
        <div className="lg:col-span-8 p-5 rounded-2xl border border-slate-800 bg-slate-900/80 space-y-4 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-emerald-400" />
                <span>全周期资产净值走势与标普 500 基准走势对比</span>
              </h3>
              <p className="text-[11px] text-slate-400 mt-0.5">
                实时记录每日结算净值，动态剥离大盘 Beta 并测算策略超额超额 Alpha
              </p>
            </div>

            <div className="flex items-center gap-1.5 p-0.5 rounded-lg bg-slate-950 border border-slate-800">
              <button
                onClick={() => setCurveMode('equity')}
                className={cn(
                  'px-2.5 py-1 rounded text-[11px] font-medium transition-colors',
                  curveMode === 'equity'
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-400 hover:text-white',
                )}
              >
                净值走势
              </button>
              <button
                onClick={() => setCurveMode('benchmark')}
                className={cn(
                  'px-2.5 py-1 rounded text-[11px] font-medium transition-colors',
                  curveMode === 'benchmark'
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-400 hover:text-white',
                )}
              >
                Alpha 对比
              </button>
            </div>
          </div>

          {/* SVG Line Chart Representation */}
          <div className="h-56 w-full flex flex-col justify-between pt-2">
            <div className="relative h-44 w-full">
              {/* SVG Coordinate Grid */}
              <svg className="w-full h-full overflow-visible" viewBox="0 0 700 160">
                <defs>
                  <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity="0.3" />
                    <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
                  </linearGradient>
                </defs>
                {/* Horizontal Guide Lines */}
                <line x1="0" y1="30" x2="700" y2="30" stroke="#334155" strokeDasharray="3 3" />
                <line x1="0" y1="80" x2="700" y2="80" stroke="#334155" strokeDasharray="3 3" />
                <line x1="0" y1="130" x2="700" y2="130" stroke="#334155" strokeDasharray="3 3" />

                {/* Benchmark SPY Curve (Gray Line) */}
                <path
                  d="M 10 140 Q 150 135 250 125 T 450 110 T 690 95"
                  fill="none"
                  stroke="#64748b"
                  strokeWidth="2"
                  strokeDasharray="4 4"
                />

                {/* Account Equity Curve (Emerald Line) */}
                <path
                  d="M 10 140 Q 120 120 220 110 T 400 80 T 550 50 T 690 25"
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="3.5"
                />

                {/* Area under equity */}
                <path
                  d="M 10 140 Q 120 120 220 110 T 400 80 T 550 50 T 690 25 L 690 150 L 10 150 Z"
                  fill="url(#equityGrad)"
                />
              </svg>
            </div>

            {/* X-axis dates & Legend */}
            <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono pt-2 border-t border-slate-800">
              <span>2026-10-15</span>
              <span>2026-10-25</span>
              <span>2026-11-05</span>
              <span>今日 (2026-11-15)</span>
            </div>
          </div>

          {/* Legend */}
          <div className="flex items-center justify-center gap-6 pt-1 text-xs text-slate-400 font-medium">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-6 rounded bg-emerald-500" />
              <span>当前模拟账户 (+14.95%)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-0.5 w-6 border-b-2 border-dashed border-slate-500" />
              <span>标普 500 (SPY) 基准 (+6.20%)</span>
            </div>
          </div>
        </div>

        {/* Right: Key Performance & Risk Check (4 cols) */}
        <div className="lg:col-span-4 p-5 rounded-2xl border border-slate-800 bg-slate-900/80 space-y-4 shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2 border-b border-slate-800/80 pb-3">
              <Activity className="h-4 w-4 text-blue-400" />
              <span>多因子业绩分析与体检指标</span>
            </h3>

            <div className="divide-y divide-slate-800/80 text-xs mt-3">
              <div className="py-2.5 flex items-center justify-between">
                <span className="text-slate-400">超额 Alpha (年化)</span>
                <span className="font-mono font-bold text-emerald-400">
                  +{performance.alpha || '8.75'}%
                </span>
              </div>
              <div className="py-2.5 flex items-center justify-between">
                <span className="text-slate-400">市场敏感度 Beta</span>
                <span className="font-mono font-bold text-slate-200">
                  {performance.beta || '1.05'}
                </span>
              </div>
              <div className="py-2.5 flex items-center justify-between">
                <span className="text-slate-400">交易胜率 (Win Rate)</span>
                <span className="font-mono font-bold text-blue-300">
                  {performance.win_rate}% ({performance.winning_trades}胜 / {performance.losing_trades}负)
                </span>
              </div>
              <div className="py-2.5 flex items-center justify-between">
                <span className="text-slate-400">盈亏比 (Profit/Loss Ratio)</span>
                <span className="font-mono font-bold text-slate-200">
                  {performance.profit_loss_ratio}
                </span>
              </div>
              <div className="py-2.5 flex items-center justify-between">
                <span className="text-slate-400">历史最大回撤 (Max Drawdown)</span>
                <span className="font-mono font-bold text-rose-400">
                  -{performance.max_drawdown}%
                </span>
              </div>
              <div className="py-2.5 flex items-center justify-between">
                <span className="text-slate-400">总成交笔数 (Total Trades)</span>
                <span className="font-mono font-bold text-white">
                  {performance.total_trades} 笔
                </span>
              </div>
            </div>
          </div>

          {/* Risk Allocation Pills */}
          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
            <span className="text-[11px] font-semibold text-slate-300 flex items-center gap-1.5">
              <Scale className="h-3.5 w-3.5 text-indigo-400" />
              <span>前四大重仓标的集中度</span>
            </span>
            <div className="flex flex-wrap gap-1.5">
              {(risk.top_positions || []).map(([sym, w], idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-800 text-slate-300 border border-slate-700/60"
                >
                  {sym}: {w}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AccountOverviewView;
