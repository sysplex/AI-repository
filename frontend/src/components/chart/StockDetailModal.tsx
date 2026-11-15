import React, { useState } from 'react';
import { Sparkles, Brain, AlertTriangle } from 'lucide-react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { StockCandleChart } from './StockCandleChart';
import { DataFreshnessTag } from '../compliance/DataFreshnessTag';
import { AIPromptVersionBadge } from '../compliance/AIPromptVersionBadge';
import { ComplianceDisclaimer } from '../compliance/ComplianceDisclaimer';
import { useMarketData } from '../../hooks/useMarketData';
import type { Signal } from '../../api/types';

export interface StockDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string;
  name?: string;
  signals?: Signal[];
  onOpenResearch?: (symbol: string) => void;
}

export const StockDetailModal: React.FC<StockDetailModalProps> = ({
  isOpen,
  onClose,
  symbol,
  name,
  signals = [],
  onOpenResearch,
}) => {
  const [interval, setInterval] = useState<'1d' | '1w'>('1d');

  const {
    candles,
    volumeBars,
    sma20,
    sma50,
    sma200,
    keyLevels,
    isLoading,
    isError,
  } = useMarketData({
    symbol,
    interval,
    lookbackDays: interval === '1d' ? 180 : 720,
    enabled: isOpen && !!symbol,
  });

  const latestSignal = signals.length > 0 ? signals[signals.length - 1] : null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      maxWidth="2xl"
      title={
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold font-mono tracking-tight text-white">{symbol}</span>
          {name && <span className="text-xs text-slate-400 font-normal">{name}</span>}
          <AIPromptVersionBadge model="deepseek-chat" promptVersion="v1.2.0" />
        </div>
      }
      description={
        <div className="flex items-center gap-2 mt-1">
          <DataFreshnessTag asOf={new Date().toISOString()} />
        </div>
      }
      footer={
        <div className="flex items-center justify-between w-full">
          <span className="text-[11px] text-slate-500 hidden sm:inline">
            拖动缩放或平移时间轴查看历史 K 线与均线交叉
          </span>
          <div className="flex items-center gap-2 ml-auto">
            <Button variant="secondary" size="sm" onClick={onClose}>
              关闭
            </Button>
            {onOpenResearch && (
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  onClose();
                  onOpenResearch(symbol);
                }}
                leftIcon={<Brain className="h-4 w-4" />}
              >
                前往 AI 研报
              </Button>
            )}
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        {/* Loading / Error / Chart View */}
        {isLoading && candles.length === 0 ? (
          <div className="h-96 rounded-xl border border-slate-800 bg-slate-950 flex flex-col items-center justify-center gap-3">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
            <p className="text-xs text-slate-400">正在拉取 {symbol} 历史 K 线与技术指标...</p>
          </div>
        ) : isError && candles.length === 0 ? (
          <div className="h-96 rounded-xl border border-slate-800 bg-slate-950 flex flex-col items-center justify-center gap-3 text-slate-400">
            <AlertTriangle className="h-8 w-8 text-amber-500" />
            <p className="text-sm">暂未拉取到标的 K 线数据，请稍后重试</p>
          </div>
        ) : (
          <StockCandleChart
            symbol={symbol}
            candles={candles}
            volumeBars={volumeBars}
            sma20={sma20}
            sma50={sma50}
            sma200={sma200}
            signals={signals}
            supportLevel={keyLevels.support}
            resistanceLevel={keyLevels.resistance}
            interval={interval}
            onIntervalChange={setInterval}
            height={460}
          />
        )}

        {/* 策略信号卡片（若有） */}
        {latestSignal && (
          <div className="rounded-xl border border-indigo-900/40 bg-indigo-950/20 p-3.5 flex flex-col gap-2 text-xs">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 font-semibold text-indigo-300">
                <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                <span>策略研判信号: {latestSignal.strategy_id}</span>
                <span
                  className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                    latestSignal.direction === 'long'
                      ? 'bg-emerald-500/20 text-emerald-300'
                      : 'bg-rose-500/20 text-rose-300'
                  }`}
                >
                  {latestSignal.direction.toUpperCase()} ({latestSignal.strength} 分)
                </span>
              </div>
              <span className="text-[11px] text-slate-400 font-mono">
                触发日: {latestSignal.as_of}
              </span>
            </div>

            {latestSignal.reasons && latestSignal.reasons.length > 0 && (
              <p className="text-slate-300 text-[11px] leading-relaxed">
                理由: {latestSignal.reasons.join('；')}
              </p>
            )}

            {latestSignal.levels && (
              <div className="flex flex-wrap items-center gap-3 font-mono text-[11px] pt-1 border-t border-indigo-900/30">
                {latestSignal.levels.entry && (
                  <span className="text-sky-300">入场位: ${latestSignal.levels.entry}</span>
                )}
                {latestSignal.levels.stop_loss && (
                  <span className="text-rose-300">
                    ATR 止损: ${latestSignal.levels.stop_loss}
                  </span>
                )}
                {latestSignal.levels.target && (
                  <span className="text-emerald-300">
                    止盈目标: ${latestSignal.levels.target}
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* 法定免责 */}
        <ComplianceDisclaimer variant="inline" />
      </div>
    </Modal>
  );
};

export default StockDetailModal;
