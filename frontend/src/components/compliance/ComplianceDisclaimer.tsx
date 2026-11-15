import React from 'react';
import { ShieldAlert } from 'lucide-react';
import { cn } from '../../utils/cn';

export interface ComplianceDisclaimerProps {
  variant?: 'banner' | 'card' | 'inline';
  className?: string;
  customText?: string;
}

export const MANDATORY_LEGAL_DISCLAIMER =
  '本内容仅供研究与模拟学习，不构成任何投资建议。市场有风险，投资需谨慎。';

export const ComplianceDisclaimer: React.FC<ComplianceDisclaimerProps> = ({
  variant = 'card',
  className,
  customText,
}) => {
  const text = customText || MANDATORY_LEGAL_DISCLAIMER;

  if (variant === 'inline') {
    return (
      <div
        className={cn(
          'text-[11px] text-slate-500 flex items-center justify-center gap-1.5 py-2 select-none',
          className,
        )}
      >
        <ShieldAlert className="h-3.5 w-3.5 text-slate-400 shrink-0" />
        <span>{text}</span>
      </div>
    );
  }

  if (variant === 'banner') {
    return (
      <div
        className={cn(
          'w-full bg-slate-950/80 border-t border-slate-800/80 px-4 py-2 text-center text-xs text-slate-400 flex items-center justify-center gap-2 select-none',
          className,
        )}
      >
        <ShieldAlert className="h-3.5 w-3.5 text-amber-500/80 shrink-0" />
        <span>{text}</span>
      </div>
    );
  }

  // Card variant
  return (
    <div
      className={cn(
        'rounded-xl border border-slate-800 bg-slate-950/60 p-3.5 flex items-start gap-3 text-xs text-slate-400 select-none shadow-sm',
        className,
      )}
    >
      <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-400 shrink-0 mt-0.5">
        <ShieldAlert className="h-4 w-4" />
      </div>
      <div className="space-y-0.5">
        <div className="font-semibold text-slate-300">合规免责声明（Legal Disclaimer）</div>
        <p className="text-slate-400 leading-relaxed">{text}</p>
      </div>
    </div>
  );
};
