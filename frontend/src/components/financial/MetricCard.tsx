import React from 'react';
import { HelpCircle } from 'lucide-react';
import { ChangePercent } from './ChangePercent';
import { Skeleton } from '../common/Skeleton';
import { cn } from '../../utils/cn';

export interface MetricCardProps {
  title: string;
  value: React.ReactNode;
  change?: number | null;
  changeAmount?: number | null;
  subtext?: string;
  tooltip?: string;
  icon?: React.ReactNode;
  isLoading?: boolean;
  className?: string;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  change,
  changeAmount,
  subtext,
  tooltip,
  icon,
  isLoading = false,
  className,
}) => {
  if (isLoading) {
    return (
      <div className={cn('rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-3', className)}>
        <div className="flex items-center justify-between">
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="h-4 w-4 rounded-full" />
        </div>
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-3 w-20" />
      </div>
    );
  }

  return (
    <div
      className={cn(
        'rounded-xl border border-slate-800 bg-slate-900/80 p-4 shadow-sm hover:border-slate-700/80 transition-all flex flex-col justify-between',
        className,
      )}
    >
      <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
        <div className="flex items-center gap-1.5 font-medium">
          <span>{title}</span>
          {tooltip && (
            <span title={tooltip} className="cursor-help text-slate-500 hover:text-slate-300">
              <HelpCircle className="h-3.5 w-3.5" />
            </span>
          )}
        </div>
        {icon && <div className="text-slate-400 p-1 rounded-lg bg-slate-800/60">{icon}</div>}
      </div>

      <div className="flex items-baseline justify-between gap-2 mt-1">
        <div className="text-xl sm:text-2xl font-bold font-mono tracking-tight text-white">
          {value}
        </div>
        {change !== undefined && change !== null && (
          <ChangePercent value={change} changeAmount={changeAmount} mode="badge" />
        )}
      </div>

      {subtext && <p className="text-[11px] text-slate-500 mt-2 truncate">{subtext}</p>}
    </div>
  );
};
