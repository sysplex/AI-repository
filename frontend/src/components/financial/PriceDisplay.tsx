import React, { useEffect, useRef, useState } from 'react';
import { formatPrice } from '../../utils/format';
import { useFinancialColor } from '../../hooks/useFinancialColor';
import { cn } from '../../utils/cn';

export interface PriceDisplayProps {
  value: number | string | null | undefined;
  decimals?: number;
  colored?: boolean;
  changeValue?: number | null; // 用于判定涨跌色彩的基准值，若未传入则根据价格本身是否为正判断或保持中性
  animateFlash?: boolean;
  className?: string;
  currency?: string;
  overrideScheme?: 'us' | 'cn';
}

export const PriceDisplay: React.FC<PriceDisplayProps> = ({
  value,
  decimals = 2,
  colored = false,
  changeValue = null,
  animateFlash = true,
  className,
  currency = '$',
  overrideScheme,
}) => {
  const numericVal = typeof value === 'number' ? value : value ? parseFloat(value) : null;
  const prevValRef = useRef<number | null>(numericVal);
  const [flashType, setFlashType] = useState<'up' | 'down' | null>(null);

  const colors = useFinancialColor(changeValue, overrideScheme);

  useEffect(() => {
    if (!animateFlash || numericVal === null) return;
    if (prevValRef.current !== null && prevValRef.current !== numericVal) {
      if (numericVal > prevValRef.current) {
        setFlashType('up');
      } else if (numericVal < prevValRef.current) {
        setFlashType('down');
      }
      const timer = setTimeout(() => setFlashType(null), 1200);
      return () => clearTimeout(timer);
    }
    prevValRef.current = numericVal;
  }, [numericVal, animateFlash]);

  const formattedText = formatPrice(value, decimals);
  // formatPrice returns "$182.50", if currency is not '$', replace it
  const displayText = currency === '$' ? formattedText : formattedText.replace('$', currency);

  return (
    <span
      className={cn(
        'font-mono tracking-tight font-semibold inline-flex items-center transition-all duration-300',
        colored && colors.text,
        flashType === 'up' && 'bg-emerald-500/20 text-emerald-300 px-1 rounded',
        flashType === 'down' && 'bg-rose-500/20 text-rose-300 px-1 rounded',
        className,
      )}
      title={numericVal !== null ? `${numericVal}` : undefined}
    >
      {displayText}
    </span>
  );
};
