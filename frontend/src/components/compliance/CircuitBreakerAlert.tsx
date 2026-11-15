import React from 'react';
import { ShieldX } from 'lucide-react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';

export interface CircuitBreakerAlertProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CircuitBreakerAlert: React.FC<CircuitBreakerAlertProps> = ({ isOpen, onClose }) => {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="系统预算保护熔断生效中"
      maxWidth="md"
      footer={
        <Button variant="secondary" size="sm" onClick={onClose}>
          关闭提示
        </Button>
      }
    >
      <div className="flex flex-col items-center text-center py-2 space-y-4">
        <div className="h-14 w-14 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
          <ShieldX className="h-7 w-7" />
        </div>
        <div className="space-y-1">
          <h4 className="text-base font-semibold text-slate-100">AI 预算熔断器已开启 (HTTP 503)</h4>
          <p className="text-xs text-slate-400 leading-relaxed max-w-sm">
            当前平台系统总体 AI 调用预算已达预警阈值。为防止资源超支，AI 决策与生成服务暂时熔断。
          </p>
        </div>
        <div className="w-full bg-slate-950/60 rounded-lg p-3 text-left border border-slate-800 text-xs text-slate-400">
          熔断窗口期结束后系统将自动恢复推理，行情与基础功能不受影响。如需紧急保障，请联系管理员调整预算限额。
        </div>
      </div>
    </Modal>
  );
};
