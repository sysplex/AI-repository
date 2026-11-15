import React from 'react';
import { AlertCircle, Clock } from 'lucide-react';
import { formatDateTime } from '../../utils/format';
import { Badge } from '../common/Badge';
import { cn } from '../../utils/cn';

export interface DataFreshnessTagProps {
  asOf: string | null | undefined;
  stale?: boolean;
  marketTimezone?: string;
  className?: string;
  showIcon?: boolean;
}

export const DataFreshnessTag: React.FC<DataFreshnessTagProps> = ({
  asOf,
  stale = false,
  marketTimezone = 'EST',
  className,
  showIcon = true,
}) => {
  const formattedTime = formatDateTime(asOf);

  if (stale) {
    return (
      <Badge
        variant="warning"
        size="sm"
        className={cn('inline-flex items-center gap-1.5 font-mono select-none', className)}
        title="当前标的市场数据为缓存快照，由于上游延迟或休市，可能存在时效差异"
      >
        {showIcon && <AlertCircle className="h-3 w-3 text-amber-400 shrink-0" />}
        <span>数据截至: {formattedTime} ({marketTimezone})</span>
        <span className="bg-amber-500/20 px-1 py-0.2 rounded text-[10px] text-amber-300 font-semibold">
          [数据可能延迟]
        </span>
      </Badge>
    );
  }

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 text-xs text-slate-400 font-mono select-none',
        className,
      )}
      title="数据更新正常"
    >
      {showIcon && <Clock className="h-3 w-3 text-emerald-400 shrink-0" />}
      <span>数据截至: {formattedTime} ({marketTimezone})</span>
    </div>
  );
};
