import React from 'react';
import { cn } from '../../utils/cn';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'success' | 'danger' | 'warning' | 'info' | 'purple' | 'neutral';
  size?: 'xs' | 'sm' | 'md';
}

export const Badge: React.FC<BadgeProps> = ({
  className,
  variant = 'default',
  size = 'sm',
  children,
  ...props
}) => {
  const variants = {
    default: 'bg-slate-800 text-slate-300 border-slate-700',
    neutral: 'bg-slate-800 text-slate-400 border-slate-700/80',
    success: 'bg-emerald-950/70 text-emerald-300 border-emerald-500/30',
    danger: 'bg-rose-950/70 text-rose-300 border-rose-500/30',
    warning: 'bg-amber-950/70 text-amber-300 border-amber-500/30',
    info: 'bg-blue-950/70 text-blue-300 border-blue-500/30',
    purple: 'bg-purple-950/70 text-purple-300 border-purple-500/30',
  };

  const sizes = {
    xs: 'px-1.5 py-0.5 text-[10px] font-medium leading-none',
    sm: 'px-2 py-0.5 text-xs font-medium',
    md: 'px-2.5 py-1 text-xs font-semibold',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border tracking-wide transition-colors',
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
};
