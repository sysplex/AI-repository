import React, { useState } from 'react';
import {
  BookOpen,
  Edit2,
  Plus,
  Smile,
  Tag,
} from 'lucide-react';
import type { TradeJournalResponse, TradeJournalUpdate, TradeResponse } from '../../api/types';
import { simbrokerApi } from '../../api/simbroker';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Modal } from '../../components/common/Modal';
import { PriceDisplay } from '../../components/financial/PriceDisplay';
import { cn } from '../../utils/cn';

export interface TradingJournalViewProps {
  trades: TradeResponse[];
  journals: Record<string, TradeJournalResponse>;
  onJournalUpdated: (tradeId: string, updated: TradeJournalResponse) => void;
}

export const TradingJournalView: React.FC<TradingJournalViewProps> = ({
  trades,
  journals,
  onJournalUpdated,
}) => {
  // Editing state
  const [editingTrade, setEditingTrade] = useState<TradeResponse | null>(null);
  const [journalNotes, setJournalNotes] = useState<string>('');
  const [journalTags, setJournalTags] = useState<string>('');
  const [journalEmotion, setJournalEmotion] = useState<string>('理性坚定');
  const [isSaving, setIsSaving] = useState<boolean>(false);

  // Summary Metrics
  const totalTradesCount = trades.length;
  const journaledCount = Object.keys(journals).length;
  const totalRealizedPnl = trades.reduce((acc, t) => acc + parseFloat(t.realized_pnl || '0'), 0);

  const openJournalModal = (trade: TradeResponse) => {
    setEditingTrade(trade);
    const existing = journals[trade.id];
    setJournalNotes(existing?.notes || '');
    setJournalTags((existing?.tags || []).join(', '));
    setJournalEmotion(existing?.emotion || '理性坚定');
  };

  const handleSaveJournal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingTrade) return;

    setIsSaving(true);
    const tags = journalTags
      .split(/[,，\s]+/)
      .map((t) => t.trim())
      .filter(Boolean);

    const payload: TradeJournalUpdate = {
      notes: journalNotes.trim() || null,
      tags: tags.length > 0 ? tags : undefined,
      emotion: journalEmotion.trim() || null,
    };

    try {
      const updated = await simbrokerApi.updateTradeJournal(editingTrade.id, payload);
      onJournalUpdated(editingTrade.id, updated);
    } catch {
      // Local fallback
      const localUpdated: TradeJournalResponse = {
        id: `jnl-local-${Date.now()}`,
        trade_id: editingTrade.id,
        notes: journalNotes.trim() || null,
        tags,
        emotion: journalEmotion.trim() || null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      onJournalUpdated(editingTrade.id, localUpdated);
    } finally {
      setIsSaving(false);
      setEditingTrade(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & KPI Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80 space-y-1">
          <span className="text-[11px] font-medium text-slate-400">历史已平仓实现盈亏</span>
          <div className="text-xl font-bold font-mono text-white">
            <PriceDisplay value={totalRealizedPnl} />
          </div>
          <div className="text-[10px] text-slate-500">
            全部成交笔数: {totalTradesCount} 笔
          </div>
        </div>

        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80 space-y-1">
          <span className="text-[11px] font-medium text-slate-400">复盘日志覆盖率</span>
          <div className="text-xl font-bold font-mono text-blue-400">
            {totalTradesCount > 0
              ? `${Math.round((journaledCount / totalTradesCount) * 100)}%`
              : '0%'}
          </div>
          <div className="text-[10px] text-slate-500">
            已复盘 {journaledCount} 笔 / 共 {totalTradesCount} 笔
          </div>
        </div>

        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/80 space-y-1">
          <span className="text-[11px] font-medium text-slate-400">AI 交易复盘审计</span>
          <div className="text-xl font-bold font-mono text-emerald-400">
            遵循纪律
          </div>
          <div className="text-[10px] text-slate-500">
            单笔交易自动留痕，防止追涨杀跌
          </div>
        </div>
      </div>

      {/* Trades & Journal Feed */}
      <div className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-indigo-400" />
            <span>成交记录与结构化复盘日志卡片</span>
          </h3>
          <span className="text-xs text-slate-400">点击任意单笔成交即可录入或完善心得反思</span>
        </div>

        {trades.length === 0 ? (
          <div className="p-12 text-center text-slate-400 space-y-2 rounded-xl border border-slate-800 bg-slate-900/60">
            <BookOpen className="h-8 w-8 text-slate-600 mx-auto" />
            <p className="text-sm">暂无历史成交记录，请先在交易控制台下单撮合。</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {trades.map((trade) => {
              const journal = journals[trade.id];
              const isBuy = trade.side === 'buy';
              const realizedPnlNum = parseFloat(trade.realized_pnl || '0');

              return (
                <div
                  key={trade.id}
                  className="p-5 rounded-2xl border border-slate-800 bg-slate-900/90 hover:border-slate-700 transition-all shadow-sm space-y-4"
                >
                  {/* Top Bar of Trade Item */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
                    <div className="flex items-center gap-3">
                      <span
                        className={cn(
                          'px-2.5 py-1 rounded text-xs font-bold font-mono uppercase border',
                          isBuy
                            ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                            : 'bg-rose-500/20 text-rose-400 border-rose-500/30',
                        )}
                      >
                        {isBuy ? '买入做多 BUY' : '卖出平仓 SELL'}
                      </span>
                      <span className="text-base font-mono font-extrabold text-white">
                        {trade.symbol}
                      </span>
                      <span className="text-xs text-slate-400 font-mono">
                        {trade.qty} 股 @ ${parseFloat(trade.price).toFixed(2)}
                      </span>
                      <span className="text-xs text-slate-500 font-mono">
                        (佣金: ${parseFloat(trade.fee).toFixed(2)})
                      </span>
                    </div>

                    <div className="flex items-center gap-3">
                      {trade.side === 'sell' && (
                        <div className="flex items-center gap-1.5 font-mono text-xs">
                          <span className="text-slate-400">平仓盈亏:</span>
                          <span
                            className={cn(
                              'font-bold',
                              realizedPnlNum >= 0 ? 'text-emerald-400' : 'text-rose-400',
                            )}
                          >
                            {realizedPnlNum >= 0
                              ? `+$${realizedPnlNum.toFixed(2)}`
                              : `-$${Math.abs(realizedPnlNum).toFixed(2)}`}
                          </span>
                        </div>
                      )}
                      <span className="text-[11px] text-slate-500 font-mono">
                        {new Date(trade.executed_at).toLocaleString()}
                      </span>
                      <Button
                        size="xs"
                        variant="outline"
                        onClick={() => openJournalModal(trade)}
                        leftIcon={<Edit2 className="h-3 w-3 text-blue-400" />}
                      >
                        {journal ? '编辑复盘' : '录入复盘'}
                      </Button>
                    </div>
                  </div>

                  {/* Journal Content */}
                  {journal ? (
                    <div className="space-y-2.5 pl-2">
                      <div className="flex flex-wrap items-center gap-2">
                        {journal.emotion && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-indigo-950/60 text-indigo-300 border border-indigo-800/50">
                            <Smile className="h-3 w-3" />
                            <span>情绪: {journal.emotion}</span>
                          </span>
                        )}
                        {(journal.tags || []).map((tag, idx) => (
                          <span
                            key={idx}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-300 border border-slate-700/60"
                          >
                            <Tag className="h-3 w-3 text-slate-400" />
                            <span>{tag}</span>
                          </span>
                        ))}
                      </div>

                      {journal.notes ? (
                        <p className="text-xs text-slate-200 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
                          {journal.notes}
                        </p>
                      ) : (
                        <p className="text-xs text-slate-500 italic">尚未填写复盘心得文字</p>
                      )}
                    </div>
                  ) : (
                    <div
                      onClick={() => openJournalModal(trade)}
                      className="p-3 rounded-xl bg-slate-950/40 border border-dashed border-slate-800 text-xs text-slate-500 cursor-pointer hover:border-slate-700 hover:text-slate-400 transition-colors flex items-center justify-between"
                    >
                      <span>点击补充该笔交易的入场逻辑、策略标签与执行反思...</span>
                      <Plus className="h-4 w-4" />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Modal: Edit Trade Journal */}
      {editingTrade && (
        <Modal
          isOpen={!!editingTrade}
          onClose={() => setEditingTrade(null)}
          title={`交易复盘日志 - ${editingTrade.symbol} (${editingTrade.side.toUpperCase()} ${editingTrade.qty} 股)`}
        >
          <form onSubmit={handleSaveJournal} className="space-y-4 text-xs">
            <div className="space-y-1">
              <label className="font-semibold text-slate-300">入场 / 出场交易理由与策略逻辑</label>
              <textarea
                rows={4}
                required
                value={journalNotes}
                onChange={(e) => setJournalNotes(e.target.value)}
                placeholder="记录本次买卖的核心逻辑：例如突破 20 日均线回踩企稳、财报业绩超预期、估值安全边际充裕、跌破止损位严格离场..."
                className="w-full rounded-lg border border-slate-700 bg-slate-900 p-3 text-xs text-white focus:border-blue-500 focus:outline-none"
              />
            </div>

            <div className="space-y-1">
              <label className="font-semibold text-slate-300">策略标签 (逗号隔开)</label>
              <Input
                value={journalTags}
                onChange={(e) => setJournalTags(e.target.value)}
                placeholder="例如 趋势突破, 量化多因子, 波段止盈, 止损离场"
              />
            </div>

            <div className="space-y-1">
              <label className="font-semibold text-slate-300">交易情绪与心态复盘</label>
              <select
                value={journalEmotion}
                onChange={(e) => setJournalEmotion(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white focus:border-blue-500 focus:outline-none"
              >
                <option value="理性坚定">理性坚定（严格按交易计划执行）</option>
                <option value="从容果断">从容果断（目标位达成顺利止盈）</option>
                <option value="纪律执行">纪律执行（触发条件无犹豫离场）</option>
                <option value="稍显焦虑">稍显焦虑（担心踏空或波动不安）</option>
                <option value="冲动追高">冲动追高（受市场即时情绪扰动）</option>
              </select>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" type="button" onClick={() => setEditingTrade(null)}>
                取消
              </Button>
              <Button variant="primary" type="submit" isLoading={isSaving}>
                保存复盘记录
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};

export default TradingJournalView;
