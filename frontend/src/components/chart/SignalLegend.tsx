import React from 'react';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { cn } from '../../utils/cn';

export interface SignalLegendProps {
  className?: string;
  supportLevel?: number;
  resistanceLevel?: number;
}

export const SignalLegend: React.FC<SignalLegendProps> = ({
  className,
  supportLevel,
  resistanceLevel,
}) => {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-x-4 gap-y-1.5 px-3 py-1.5 bg-slate-950/80 border-t border-slate-800 text-[11px] text-slate-400 select-none font-mono',
        className,
      )}
    >
      <div className="flex items-center gap-1 text-emerald-400">
        <ArrowUpRight className="h-3 w-3" />
        <span>BUY (多头买入点)</span>
      </div>

      <div className="flex items-center gap-1 text-rose-400">
        <ArrowDownRight className="h-3 w-3" />
        <span>SELL (空头平仓点)</span>
      </div>

      <div className="flex items-center gap-1.5 text-sky-400">
        <span className="w-2.5 h-0.5 bg-sky-400" />
        <span>SMA20</span>
      </div>

      <div className="flex items-center gap-1.5 text-amber-400">
        <span className="w-2.5 h-0.5 bg-amber-400" />
        <span>SMA50</span>
      </div>

      <div className="flex items-center gap-1.5 text-purple-400">
        <span className="w-2.5 h-0.5 bg-purple-400" />
        <span>SMA200</span>
      </div>

      {supportLevel !== undefined && supportLevel > 0 && (
        <div className="flex items-center gap-1.5 text-emerald-300">
          <span className="w-2.5 h-0.5 border-b border-dashed border-emerald-400" />
          <span>{`支撑位: $${supportLevel.toFixed(2)}`}</span>
        </div>
      )}

      {resistanceLevel !== undefined && resistanceLevel > 0 && (
        <div className="flex items-center gap-1.5 text-rose-300">
          <span className="w-2.5 h-0.5 border-b border-dashed border-rose-400" />
          <span>{`阻力位: $${resistanceLevel.toFixed(2)}`}</span>
        </div>
      )}
    </div>
  );
};
