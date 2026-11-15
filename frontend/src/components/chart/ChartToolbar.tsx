import React from 'react';
import { Maximize2, Layers } from 'lucide-react';
import { Button } from '../common/Button';
import { cn } from '../../utils/cn';

export interface ChartToolbarProps {
  interval: '1d' | '1w';
  onIntervalChange: (interval: '1d' | '1w') => void;
  showSMA20: boolean;
  onToggleSMA20: () => void;
  showSMA50: boolean;
  onToggleSMA50: () => void;
  showSMA200: boolean;
  onToggleSMA200: () => void;
  showSupportResistance: boolean;
  onToggleSupportResistance: () => void;
  showSignals: boolean;
  onToggleSignals: () => void;
  onResetZoom: () => void;
  className?: string;
}

export const ChartToolbar: React.FC<ChartToolbarProps> = ({
  interval,
  onIntervalChange,
  showSMA20,
  onToggleSMA20,
  showSMA50,
  onToggleSMA50,
  showSMA200,
  onToggleSMA200,
  showSupportResistance,
  onToggleSupportResistance,
  showSignals,
  onToggleSignals,
  onResetZoom,
  className,
}) => {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center justify-between gap-2 p-2.5 bg-slate-900 border-b border-slate-800 text-xs select-none',
        className,
      )}
    >
      {/* K-line Interval Selector */}
      <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
        <button
          onClick={() => onIntervalChange('1d')}
          className={cn(
            'px-2.5 py-1 rounded text-xs font-semibold transition-colors',
            interval === '1d'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-white',
          )}
        >
          日 K (1D)
        </button>
        <button
          onClick={() => onIntervalChange('1w')}
          className={cn(
            'px-2.5 py-1 rounded text-xs font-semibold transition-colors',
            interval === '1w'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-white',
          )}
        >
          周 K (1W)
        </button>
      </div>

      {/* Technical Indicators & Overlays */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] text-slate-500 mr-1 flex items-center gap-1">
          <Layers className="h-3 w-3" />
          均线指标:
        </span>

        {/* SMA 20 */}
        <button
          onClick={onToggleSMA20}
          className={cn(
            'px-2 py-0.5 rounded text-[11px] font-mono border transition-all flex items-center gap-1.5',
            showSMA20
              ? 'bg-sky-950/80 text-sky-300 border-sky-500/50 shadow-sm'
              : 'bg-slate-950 text-slate-500 border-slate-800 hover:text-slate-300',
          )}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
          SMA 20
        </button>

        {/* SMA 50 */}
        <button
          onClick={onToggleSMA50}
          className={cn(
            'px-2 py-0.5 rounded text-[11px] font-mono border transition-all flex items-center gap-1.5',
            showSMA50
              ? 'bg-amber-950/80 text-amber-300 border-amber-500/50 shadow-sm'
              : 'bg-slate-950 text-slate-500 border-slate-800 hover:text-slate-300',
          )}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
          SMA 50
        </button>

        {/* SMA 200 */}
        <button
          onClick={onToggleSMA200}
          className={cn(
            'px-2 py-0.5 rounded text-[11px] font-mono border transition-all flex items-center gap-1.5',
            showSMA200
              ? 'bg-purple-950/80 text-purple-300 border-purple-500/50 shadow-sm'
              : 'bg-slate-950 text-slate-500 border-slate-800 hover:text-slate-300',
          )}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-purple-400" />
          SMA 200
        </button>

        <div className="h-3.5 w-px bg-slate-800 mx-1 hidden sm:block" />

        {/* Support & Resistance */}
        <button
          onClick={onToggleSupportResistance}
          className={cn(
            'px-2 py-0.5 rounded text-[11px] font-mono border transition-all',
            showSupportResistance
              ? 'bg-emerald-950/60 text-emerald-300 border-emerald-500/40'
              : 'bg-slate-950 text-slate-500 border-slate-800 hover:text-slate-300',
          )}
        >
          支撑/阻力线
        </button>

        {/* Strategy Signals */}
        <button
          onClick={onToggleSignals}
          className={cn(
            'px-2 py-0.5 rounded text-[11px] font-mono border transition-all',
            showSignals
              ? 'bg-indigo-950/80 text-indigo-300 border-indigo-500/50'
              : 'bg-slate-950 text-slate-500 border-slate-800 hover:text-slate-300',
          )}
        >
          策略买卖信号
        </button>
      </div>

      {/* Reset Zoom */}
      <div>
        <Button
          variant="ghost"
          size="xs"
          onClick={onResetZoom}
          title="适应图表全部可见范围"
          leftIcon={<Maximize2 className="h-3 w-3" />}
        >
          重置视口
        </Button>
      </div>
    </div>
  );
};
