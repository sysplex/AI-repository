import React, { useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  DollarSign,
  Info,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import type {
  AccountOverview,
  OrderCreate,
  PositionResponse,
} from '../../api/types';
import { simbrokerApi } from '../../api/simbroker';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Modal } from '../../components/common/Modal';
import { PriceDisplay } from '../../components/financial/PriceDisplay';
import { ChangePercent } from '../../components/financial/ChangePercent';
import { cn } from '../../utils/cn';

export interface OrderTradePanelViewProps {
  overview: AccountOverview;
  positions: PositionResponse[];
  onOrderSubmitted: () => void;
  prefillOrder?: { symbol: string; side: 'buy' | 'sell'; quantity?: number } | null;
  onClearPrefill?: () => void;
}

export const OrderTradePanelView: React.FC<OrderTradePanelViewProps> = ({
  overview,
  positions,
  onOrderSubmitted,
  prefillOrder,
  onClearPrefill,
}) => {
  // Trade Form States
  const [symbol, setSymbol] = useState<string>('NVDA');
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [orderType, setOrderType] = useState<'market' | 'limit' | 'stop'>('market');
  const [tif, setTif] = useState<'day' | 'gtc'>('day');
  const [qty, setQty] = useState<string>('10');
  const [limitPrice, setLimitPrice] = useState<string>('148.50');
  const [stopPrice, setStopPrice] = useState<string>('140.00');
  const [note, setNote] = useState<string>('突破均线顺势建仓');

  // Consume prefilled order parameters (e.g. from quick close / sell)
  React.useEffect(() => {
    if (prefillOrder) {
      if (prefillOrder.symbol) {
        setSymbol(prefillOrder.symbol.toUpperCase());
      }
      if (prefillOrder.side) {
        setSide(prefillOrder.side);
      }
      if (prefillOrder.quantity !== undefined && prefillOrder.quantity > 0) {
        setQty(String(prefillOrder.quantity));
      }
      onClearPrefill?.();
    }
  }, [prefillOrder, onClearPrefill]);

  // Interactive Reference Price Map (Live / Simulated)
  const [quoteMap] = useState<Record<string, { price: number; changePct: number; name: string }>>({
    NVDA: { price: 148.88, changePct: 3.42, name: 'NVIDIA Corporation' },
    MSFT: { price: 432.1, changePct: 0.95, name: 'Microsoft Corporation' },
    AAPL: { price: 224.2, changePct: 1.15, name: 'Apple Inc.' },
    LLY: { price: 845.2, changePct: 1.84, name: 'Eli Lilly and Company' },
    TSLA: { price: 260.5, changePct: -1.25, name: 'Tesla Inc.' },
    CRWD: { price: 325.6, changePct: 1.12, name: 'CrowdStrike Holdings' },
    TSM: { price: 188.4, changePct: 2.30, name: 'Taiwan Semiconductor' },
  });

  const upperSymbol = symbol.trim().toUpperCase();
  const currentQuote = quoteMap[upperSymbol] || { price: 150.0, changePct: 1.0, name: `${upperSymbol} Inc.` };
  const currentPrice = currentQuote.price;

  // Existing Position for this symbol
  const existingPosition = positions.find((p) => p.symbol.toUpperCase() === upperSymbol);
  const positionQty = existingPosition ? parseFloat(existingPosition.qty) : 0;

  // Cash & Buying Power Calculations
  const cashAvailable = parseFloat(overview.cash);
  const executionPrice =
    orderType === 'limit' && limitPrice ? parseFloat(limitPrice) : currentPrice;
  const numQty = parseFloat(qty) || 0;
  const estimatedAmount = numQty * executionPrice;
  const estimatedFee = Math.max(1.0, estimatedAmount * 0.0002);
  const totalCost = estimatedAmount + estimatedFee;

  const maxBuyQty = executionPrice > 0 ? Math.floor((cashAvailable - 5.0) / executionPrice) : 0;
  const maxSellQty = positionQty;

  // Validation Checks
  const isInsufficientCash = side === 'buy' && totalCost > cashAvailable;
  const isInsufficientPosition = side === 'sell' && numQty > positionQty;
  const isPdtRisk = side === 'sell' && positionQty > 0;

  // Confirm Modal State
  const [isConfirmModalOpen, setIsConfirmModalOpen] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitFeedback, setSubmitFeedback] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  // Quick Quantity Selector
  const handleSetRatio = (ratio: number) => {
    if (side === 'buy') {
      const calculated = Math.floor(maxBuyQty * ratio);
      setQty(String(Math.max(1, calculated)));
    } else {
      const calculated = Math.floor(maxSellQty * ratio);
      setQty(String(Math.max(1, calculated)));
    }
  };

  const handleSubmitOrder = async () => {
    setIsSubmitting(true);
    const payload: OrderCreate = {
      symbol: upperSymbol,
      side,
      type: orderType,
      qty: numQty,
      limit_price: orderType === 'limit' ? parseFloat(limitPrice) : null,
      stop_price: orderType === 'stop' ? parseFloat(stopPrice) : null,
      tif,
      note: note.trim() || undefined,
      source: 'manual',
    };

    try {
      await simbrokerApi.submitOrder(overview.id, payload);
      setSubmitFeedback({
        type: 'success',
        message: `订单提交成功！${side === 'buy' ? '买入' : '卖出'} ${numQty} 股 ${upperSymbol}`,
      });
      onOrderSubmitted();
    } catch (err: unknown) {
      setSubmitFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : '下单失败，请检查可用资金或持仓',
      });
    } finally {
      setIsSubmitting(false);
      setIsConfirmModalOpen(false);
      setTimeout(() => setSubmitFeedback(null), 4500);
    }
  };

  return (
    <div className="space-y-6">
      {/* Success / Error Feedback Toast */}
      {submitFeedback && (
        <div
          className={cn(
            'flex items-center gap-2 p-4 rounded-xl font-medium text-xs shadow-lg animate-in fade-in',
            submitFeedback.type === 'success'
              ? 'bg-emerald-500/90 text-white shadow-emerald-500/20'
              : 'bg-rose-500/90 text-white shadow-rose-500/20',
          )}
        >
          {submitFeedback.type === 'success' ? (
            <CheckCircle2 className="h-5 w-5 shrink-0" />
          ) : (
            <AlertCircle className="h-5 w-5 shrink-0" />
          )}
          <span>{submitFeedback.message}</span>
        </div>
      )}

      {/* Main Trade Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Interactive Trade Form (7 cols) */}
        <div className="lg:col-span-7 rounded-2xl border border-slate-800 bg-slate-900/80 p-6 space-y-6 shadow-md">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <DollarSign className="h-5 w-5 text-blue-400" />
              <span>模拟交易委托操作台</span>
            </h3>
            <span className="text-xs text-slate-400 font-mono">
              账户: <span className="text-white font-semibold">{overview.name}</span>
            </span>
          </div>

          {/* Quick Symbol Switcher & Live Quote Header */}
          <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <span className="text-[11px] font-semibold text-slate-400">选择交易标的</span>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                  className="w-28 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm font-mono font-bold text-white uppercase focus:border-blue-500 focus:outline-none"
                  placeholder="NVDA"
                />
                <div className="flex items-center gap-1 overflow-x-auto">
                  {['NVDA', 'MSFT', 'AAPL', 'LLY', 'TSLA'].map((s) => (
                    <button
                      key={s}
                      onClick={() => setSymbol(s)}
                      className={cn(
                        'px-2 py-1 rounded text-xs font-mono font-medium transition-colors',
                        upperSymbol === s
                          ? 'bg-blue-600 text-white'
                          : 'bg-slate-800 text-slate-400 hover:text-white',
                      )}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="text-right space-y-0.5">
              <div className="text-lg font-bold font-mono text-white">
                <PriceDisplay value={currentPrice} />
              </div>
              <ChangePercent value={currentQuote.changePct} mode="compact" />
            </div>
          </div>

          {/* Side Switcher (BUY vs SELL) */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => setSide('buy')}
              className={cn(
                'py-2.5 rounded-xl font-bold text-sm transition-all flex items-center justify-center gap-2 border select-none',
                side === 'buy'
                  ? 'bg-emerald-600 border-emerald-500 text-white shadow-lg shadow-emerald-600/20'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white hover:bg-slate-900',
              )}
            >
              <TrendingUp className="h-4 w-4" />
              <span>买入 (BUY)</span>
            </button>

            <button
              onClick={() => setSide('sell')}
              className={cn(
                'py-2.5 rounded-xl font-bold text-sm transition-all flex items-center justify-center gap-2 border select-none',
                side === 'sell'
                  ? 'bg-rose-600 border-rose-500 text-white shadow-lg shadow-rose-600/20'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white hover:bg-slate-900',
              )}
            >
              <TrendingDown className="h-4 w-4" />
              <span>卖出 (SELL)</span>
            </button>
          </div>

          {/* Order Type & TIF */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300">委托类型 (Order Type)</label>
              <div className="grid grid-cols-3 gap-1.5">
                {[
                  { id: 'market', label: '市价单' },
                  { id: 'limit', label: '限价单' },
                  { id: 'stop', label: '止损单' },
                ].map((type) => (
                  <button
                    key={type.id}
                    onClick={() => setOrderType(type.id as any)}
                    className={cn(
                      'py-1.5 rounded-lg text-xs font-medium border transition-colors',
                      orderType === type.id
                        ? 'bg-blue-600 border-blue-500 text-white'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white',
                    )}
                  >
                    {type.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300">有效期 (TIF)</label>
              <div className="grid grid-cols-2 gap-1.5">
                {[
                  { id: 'day', label: '当日有效 (DAY)' },
                  { id: 'gtc', label: '长期有效 (GTC)' },
                ].map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setTif(t.id as any)}
                    className={cn(
                      'py-1.5 rounded-lg text-xs font-medium border transition-colors',
                      tif === t.id
                        ? 'bg-blue-600 border-blue-500 text-white'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white',
                    )}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Conditional Limit / Stop Price inputs */}
          {orderType === 'limit' && (
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300">限价 ($)</label>
              <Input
                type="number"
                step="0.01"
                value={limitPrice}
                onChange={(e) => setLimitPrice(e.target.value)}
                className="font-mono text-sm"
                placeholder="输入期望成交的限价"
              />
            </div>
          )}

          {orderType === 'stop' && (
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300">止损触发价 ($)</label>
              <Input
                type="number"
                step="0.01"
                value={stopPrice}
                onChange={(e) => setStopPrice(e.target.value)}
                className="font-mono text-sm"
                placeholder="触发止损平仓的保护价"
              />
            </div>
          )}

          {/* Quantity & Ratio Shortcuts */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <label className="font-semibold text-slate-300">委托数量 (股)</label>
              <span className="text-slate-400 font-mono">
                {side === 'buy'
                  ? `最大可买: ${maxBuyQty} 股`
                  : `当前持仓: ${positionQty} 股`}
              </span>
            </div>

            <Input
              type="number"
              min="1"
              step="1"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              className="font-mono text-sm"
              placeholder="股数"
            />

            {/* Quick ratio percentage buttons */}
            <div className="grid grid-cols-4 gap-2 pt-1">
              {[0.25, 0.5, 0.75, 1.0].map((ratio) => (
                <button
                  key={ratio}
                  onClick={() => handleSetRatio(ratio)}
                  className="py-1 rounded bg-slate-800 text-[11px] font-mono font-medium text-slate-300 hover:bg-slate-700 transition-colors"
                >
                  {ratio * 100}%
                </button>
              ))}
            </div>
          </div>

          {/* Trading Note / Reason */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300">
              入场/出场理由与日志备注 (自动归档复盘)
            </label>
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="记录本次操作策略逻辑，如均线突破、财报发布前减仓..."
            />
          </div>

          {/* Pre-flight Warnings */}
          {isInsufficientCash && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
              <span>购买力不足：预计总费用超过当前账户可用现金。</span>
            </div>
          )}

          {isInsufficientPosition && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
              <span>持仓不足：卖出数量不能大于您当前账户持有的可用股数。</span>
            </div>
          )}

          {/* Submit Trigger Button */}
          <Button
            size="lg"
            variant={side === 'buy' ? 'primary' : 'danger'}
            disabled={isInsufficientCash || isInsufficientPosition || numQty <= 0}
            onClick={() => setIsConfirmModalOpen(true)}
            leftIcon={<ArrowRight className="h-4 w-4" />}
            className="w-full font-bold shadow-lg"
          >
            {`确认${side === 'buy' ? '买入' : '卖出'} ${upperSymbol} (${numQty} 股)`}
          </Button>
        </div>

        {/* Right: Estimated Cost & Account Impact (5 cols) */}
        <div className="lg:col-span-5 rounded-2xl border border-slate-800 bg-slate-900/80 p-6 space-y-5 shadow-md flex flex-col justify-between">
          <div className="space-y-4">
            <h3 className="text-sm font-bold text-white border-b border-slate-800/80 pb-3 flex items-center gap-2">
              <Info className="h-4 w-4 text-blue-400" />
              <span>交易要素测算与资金影响</span>
            </h3>

            <div className="divide-y divide-slate-800/80 text-xs">
              <div className="py-2.5 flex items-center justify-between">
                <span className="text-slate-400">参考成交价格</span>
                <span className="font-mono font-bold text-white">
                  ${executionPrice.toFixed(2)}
                </span>
              </div>
              <div className="py-2.5 flex items-center justify-between">
                <span className="text-slate-400">预估成交总金额</span>
                <span className="font-mono font-bold text-slate-200">
                  ${estimatedAmount.toFixed(2)}
                </span>
              </div>
              <div className="py-2.5 flex items-center justify-between">
                <span className="text-slate-400">预估佣金与规费 (SEC/TAF)</span>
                <span className="font-mono text-slate-300">
                  ${estimatedFee.toFixed(2)}
                </span>
              </div>
              <div className="py-2.5 flex items-center justify-between">
                <span className="font-semibold text-slate-300">
                  {side === 'buy' ? '合计需扣除可用现金' : '预计回笼资金'}
                </span>
                <span
                  className={cn(
                    'font-mono font-bold text-sm',
                    side === 'buy' ? 'text-amber-400' : 'text-emerald-400',
                  )}
                >
                  ${(side === 'buy' ? totalCost : estimatedAmount - estimatedFee).toFixed(2)}
                </span>
              </div>
              <div className="py-2.5 flex items-center justify-between">
                <span className="text-slate-400">交易后可用现金余额</span>
                <span className="font-mono font-semibold text-white">
                  ${Math.max(0, side === 'buy' ? cashAvailable - totalCost : cashAvailable + estimatedAmount - estimatedFee).toFixed(2)}
                </span>
              </div>
            </div>

            {/* PDT Alert Notice */}
            {isPdtRisk && (
              <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-800/50 text-amber-200 text-xs space-y-1">
                <div className="font-bold flex items-center gap-1.5">
                  <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
                  <span>潜在日内交易 (Day Trade) 提示</span>
                </div>
                <p className="text-[11px] text-amber-300/80 leading-relaxed">
                  若该标的的部分持仓为今日买入，本次卖出操作将在结算时计入 1 笔日内交易（当前已用 {overview.pdt_day_trades_count}/3 次）。
                </p>
              </div>
            )}
          </div>

          {/* Quick Portfolio Footprint */}
          <div className="p-3.5 rounded-xl bg-slate-950/60 border border-slate-800 text-xs space-y-2">
            <span className="text-[11px] font-semibold text-slate-400">标的持仓底色</span>
            <div className="flex items-center justify-between">
              <span className="text-slate-300">{upperSymbol} 持仓股数</span>
              <span className="font-mono font-bold text-white">{positionQty} 股</span>
            </div>
            {existingPosition && (
              <div className="flex items-center justify-between">
                <span className="text-slate-300">加权成本均价</span>
                <span className="font-mono text-slate-300">${parseFloat(existingPosition.avg_cost).toFixed(2)}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Second-Chance Order Confirmation Modal */}
      <Modal
        isOpen={isConfirmModalOpen}
        onClose={() => setIsConfirmModalOpen(false)}
        title="确认提交模拟交易委托"
      >
        <div className="space-y-4 text-xs">
          <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2 font-mono">
            <div className="flex justify-between">
              <span className="text-slate-400">交易标的:</span>
              <span className="font-bold text-white">{upperSymbol}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">委托方向:</span>
              <span className={cn('font-bold', side === 'buy' ? 'text-emerald-400' : 'text-rose-400')}>
                {side === 'buy' ? '买入做多 (BUY)' : '卖出平仓 (SELL)'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">委托类型:</span>
              <span className="text-white uppercase">{orderType}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">委托数量:</span>
              <span className="font-bold text-white">{numQty} 股</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">执行价格:</span>
              <span className="text-white">${executionPrice.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">预估发生金额:</span>
              <span className="text-white">${estimatedAmount.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">有效期限:</span>
              <span className="text-white uppercase">{tif}</span>
            </div>
          </div>

          {note && (
            <p className="text-slate-400 italic">
              备注: {note}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={() => setIsConfirmModalOpen(false)}>
              返回修改
            </Button>
            <Button
              variant={side === 'buy' ? 'primary' : 'danger'}
              isLoading={isSubmitting}
              onClick={handleSubmitOrder}
            >
              确认下单
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default OrderTradePanelView;
