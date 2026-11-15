import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ZapOff } from 'lucide-react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';

export interface QuotaExceededModalProps {
  isOpen: boolean;
  onClose: () => void;
  quotaUsed?: number;
  totalQuota?: number;
}

export const QuotaExceededModal: React.FC<QuotaExceededModalProps> = ({
  isOpen,
  onClose,
  quotaUsed = 20,
  totalQuota = 20,
}) => {
  const navigate = useNavigate();

  const handleGoUsage = () => {
    onClose();
    navigate('/settings/usage');
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="今日 AI 额度已达上限"
      maxWidth="md"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>
            我知道了
          </Button>
          <Button variant="primary" size="sm" onClick={handleGoUsage}>
            查看配额明细
          </Button>
        </>
      }
    >
      <div className="flex flex-col items-center text-center py-2 space-y-4">
        <div className="h-14 w-14 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
          <ZapOff className="h-7 w-7" />
        </div>
        <div className="space-y-1">
          <h4 className="text-base font-semibold text-slate-100">
            免费额度已耗尽（{quotaUsed} / {totalQuota}）
          </h4>
          <p className="text-xs text-slate-400 leading-relaxed max-w-sm">
            您今日的 AI 投研与决策分析调用次数已达到配额上限。配额将于次日 00:00 (UTC) 自动重置。
          </p>
        </div>
        <div className="w-full bg-slate-950/60 rounded-lg p-3 text-left border border-slate-800 text-xs text-slate-300 space-y-1.5">
          <div className="text-slate-400 font-medium">在配额重置前，您仍可无限制使用：</div>
          <ul className="list-disc list-inside text-slate-400 space-y-0.5 pl-1">
            <li>实时行情 K 线与技术指标图表</li>
            <li>因子策略筛选器与主题自选股</li>
            <li>SimBroker 模拟盘撮合与交易复盘</li>
          </ul>
        </div>
      </div>
    </Modal>
  );
};
