import React from 'react';
import { Sparkles } from 'lucide-react';
import { Badge } from '../common/Badge';
import { cn } from '../../utils/cn';

export interface AIPromptVersionBadgeProps {
  model?: string;
  promptVersion?: string;
  size?: 'xs' | 'sm';
  className?: string;
  showIcon?: boolean;
}

export const AIPromptVersionBadge: React.FC<AIPromptVersionBadgeProps> = ({
  model = 'gpt-4o',
  promptVersion = 'v1.0.0',
  size = 'xs',
  className,
  showIcon = true,
}) => {
  return (
    <Badge
      variant="purple"
      size={size}
      className={cn('inline-flex items-center gap-1.5 font-mono select-none', className)}
      title={`AI 推理引擎: ${model}，提示词工程模板版本: ${promptVersion}，满足金融系统审计与复核要求`}
    >
      {showIcon && <Sparkles className="h-2.5 w-2.5 text-purple-300 shrink-0" />}
      <span className="font-semibold text-purple-200">{`AI 引擎: ${model}`}</span>
      <span className="opacity-50">|</span>
      <span>{`模板: ${promptVersion}`}</span>
    </Badge>
  );
};
