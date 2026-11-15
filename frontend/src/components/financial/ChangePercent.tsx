import React from 'react';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import { formatPercent, formatPrice } from '../../utils/format';
import { useFinancialColor } from '../../hooks/useFinancialColor';
import { cn } from '../../utils/cn';

export interface ChangePercentProps {
  value: number | string | null | undefined;
  changeAmount?: number | string | null | undefined;
  mode?: 'badge' | 'text' | 'compact';
  showIcon?: boolean;
  withSign?: boolean;
  className?: string;
  overrideScheme?: 'us' | 'cn';
}

export const ChangePercent: React.FC<ChangePercentProps> = ({
  value,
  changeAmount,
  mode = 'badge',
  showIcon = true,
  withSign = true,
  className,
  overrideScheme,
}) => {
  const numericVal = typeof value === 'number' ? value : value ? parseFloat(value) : null;
  const numChangeAmount =
    typeof changeAmount === 'number'
      ? changeAmount
      : changeAmount
        ? parseFloat(changeAmount)
        : null;

  const colors = useFinancialColor(numericVal, overrideScheme);
  const formattedPercent = formatPercent(numericVal, withSign);

  const renderIcon = () => {
    if (!showIcon) return null;
    if (colors.direction === 'up') {
      return <ArrowUpRight className="h-3.5 w-3.5 shrink-0" />;
    }
    if (colors.direction === 'down') {
      return <ArrowDownRight className="h-3.5 w-3.5 shrink-0" />;
    }
    return <Minus className="h-3 w-3 shrink-0" />;
  };

  if (mode === 'text') {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1 font-mono font-medium text-xs sm:text-sm',
          colors.text,
          className,
        )}
      >
        {renderIcon()}
        {numChangeAmount !== null && (
          <span>{numChangeAmount > 0 ? `+${formatPrice(numChangeAmount)}` : formatPrice(numChangeAmount)}</span>
        )}
        <span>{formattedPercent}</span>
      </span>
    );
  }

  // badge / compact
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 font-mono font-medium rounded-md px-2 py-0.5 text-xs border transition-colors',
        colors.badge,
        mode === 'compact' && 'px-1.5 py-0 text-[11px]',
        className,
      )}
    >
      {renderIcon()}
      {numChangeAmount !== null && mode !== 'compact' && (
        <span className="opacity-90">
          {numChangeAmount > 0 ? `+${formatPrice(numChangeAmount)}` : formatPrice(numChangeAmount)}
        </span>
      )}
      <span>{formattedPercent}</span>
    </span>
  );
};
