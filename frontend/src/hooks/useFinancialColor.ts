import { useAuth } from './useAuth';

export type FinancialDirection = 'up' | 'down' | 'neutral';

export interface FinancialColorClasses {
  direction: FinancialDirection;
  text: string;
  bg: string;
  border: string;
  badge: string;
  fill: string;
}

export function getFinancialDirection(val: number | null | undefined): FinancialDirection {
  if (val === null || val === undefined || isNaN(val) || Math.abs(val) < 0.000001) {
    return 'neutral';
  }
  return val > 0 ? 'up' : 'down';
}

export function getFinancialColor(
  val: number | null | undefined,
  scheme: 'us' | 'cn' = 'us',
): FinancialColorClasses {
  const direction = getFinancialDirection(val);

  if (direction === 'neutral') {
    return {
      direction: 'neutral',
      text: 'text-slate-400 dark:text-slate-400',
      bg: 'bg-slate-500/10',
      border: 'border-slate-500/20',
      badge: 'bg-slate-800 text-slate-300 border border-slate-700',
      fill: '#94a3b8',
    };
  }

  // 美股默认: up = green, down = red
  // 国内习惯: up = red, down = green
  const isBullishGreen = scheme === 'us';
  const isUp = direction === 'up';

  const isGreen = (isUp && isBullishGreen) || (!isUp && !isBullishGreen);

  if (isGreen) {
    return {
      direction,
      text: 'text-emerald-400 dark:text-emerald-400',
      bg: 'bg-emerald-500/10',
      border: 'border-emerald-500/30',
      badge: 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/30',
      fill: '#10b981',
    };
  }

  return {
    direction,
    text: 'text-rose-400 dark:text-rose-400',
    bg: 'bg-rose-500/10',
    border: 'border-rose-500/30',
    badge: 'bg-rose-950/60 text-rose-300 border border-rose-500/30',
    fill: '#f43f5e',
  };
}

export function useFinancialColor(
  val?: number | null,
  overrideScheme?: 'us' | 'cn',
): FinancialColorClasses {
  let scheme: 'us' | 'cn' = 'us';
  try {
    const auth = useAuth();
    scheme = overrideScheme || auth.colorScheme || 'us';
  } catch {
    scheme = overrideScheme || 'us';
  }

  return getFinancialColor(val, scheme);
}
