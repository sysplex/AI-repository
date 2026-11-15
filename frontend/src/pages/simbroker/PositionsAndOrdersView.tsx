import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  ExternalLink,
  ListFilter,
  PieChart,
  RefreshCw,
} from 'lucide-react';
import type { OrderResponse, PositionResponse } from '../../api/types';
import { simbrokerApi } from '../../api/simbroker';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { ChangePercent } from '../../components/financial/ChangePercent';
import { cn } from '../../utils/cn';

export interface PositionsAndOrdersViewProps {
  accountId: string;
  positions: PositionResponse[];
  orders: OrderResponse[];
  onRefresh: () => void;
  onQuickTrade?: (symbol: string, side: 'buy' | 'sell') => void;
}

export const PositionsAndOrdersView: React.FC<PositionsAndOrdersViewProps> = ({
  accountId,
  positions,
  orders,
  onRefresh,
  onQuickTrade,
}) => {
  const navigate = useNavigate();

  // Active section tab: 'positions' vs 'orders'
  const [subTab, setSubTab] = useState<'positions' | 'orders'>('positions');
  const [orderStatusFilter, setOrderStatusFilter] = useState<string>('all');
  const [cancellingOrderId, setCancellingOrderId] = useState<string | null>(null);

  const handleCancelOrder = async (orderId: string) => {
    if (!window.confirm('确认撤销该笔未完全成交的委托订单吗？')) return;
    setCancellingOrderId(orderId);
    try {
      await simbrokerApi.cancelOrder(accountId, orderId);
      onRefresh();
    } catch {
      // Local fallback
      onRefresh();
    } finally {
      setCancellingOrderId(null);
    }
  };

  const filteredOrders = orders.filter((o) => {
    if (orderStatusFilter === 'all') return true;
    if (orderStatusFilter === 'open') {
      return o.status === 'accepted' || o.status === 'pending';
    }
    return o.status.toLowerCase() === orderStatusFilter.toLowerCase();
  });

  const getOrderStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case 'filled':
        return <Badge variant="success" size="xs">已完全成交</Badge>;
      case 'accepted':
      case 'pending':
        return <Badge variant="info" size="xs">挂单撮合中</Badge>;
      case 'cancelled':
        return <Badge variant="neutral" size="xs">已撤单</Badge>;
      case 'rejected':
        return <Badge variant="danger" size="xs">已拒绝</Badge>;
      default:
        return <Badge variant="neutral" size="xs">{status}</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Sub Tabs Toggle Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow-sm">
        <div className="flex items-center gap-2 p-1 rounded-xl bg-slate-950 border border-slate-800 self-start">
          <button
            onClick={() => setSubTab('positions')}
            className={cn(
              'flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-semibold transition-colors',
              subTab === 'positions'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white',
            )}
          >
            <PieChart className="h-4 w-4" />
            <span>持仓明细 ({positions.length})</span>
          </button>

          <button
            onClick={() => setSubTab('orders')}
            className={cn(
              'flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-semibold transition-colors',
              subTab === 'orders'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white',
            )}
          >
            <ListFilter className="h-4 w-4" />
            <span>委托订单管理 ({orders.length})</span>
          </button>
        </div>

        <div className="flex items-center gap-2">
          {subTab === 'orders' && (
            <div className="flex items-center gap-1 overflow-x-auto text-xs">
              {[
                { id: 'all', label: '全部' },
                { id: 'open', label: '挂单中' },
                { id: 'filled', label: '已成交' },
                { id: 'cancelled', label: '已撤单' },
              ].map((f) => (
                <button
                  key={f.id}
                  onClick={() => setOrderStatusFilter(f.id)}
                  className={cn(
                    'px-2.5 py-1 rounded text-[11px] font-medium transition-colors',
                    orderStatusFilter === f.id
                      ? 'bg-slate-800 text-white border border-slate-700'
                      : 'text-slate-400 hover:text-white',
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
          )}

          <Button
            size="sm"
            variant="ghost"
            onClick={onRefresh}
            leftIcon={<RefreshCw className="h-3.5 w-3.5 text-slate-400" />}
            title="刷新数据"
            aria-label="刷新数据"
          />
        </div>
      </div>

      {/* View 1: Positions Table */}
      {subTab === 'positions' && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 overflow-hidden shadow-sm">
          {positions.length === 0 ? (
            <div className="p-12 text-center text-slate-400 space-y-2">
              <PieChart className="h-8 w-8 text-slate-600 mx-auto" />
              <p className="text-sm">当前模拟账户暂无持仓资产</p>
              <p className="text-xs text-slate-500">前往「模拟交易下单」挑选标的提交买入委托。</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                  <tr>
                    <th className="py-3 px-4">标的代码</th>
                    <th className="py-3 px-4">持仓数量</th>
                    <th className="py-3 px-4">持仓均价</th>
                    <th className="py-3 px-4">最新市价</th>
                    <th className="py-3 px-4">持仓总市值</th>
                    <th className="py-3 px-4">浮动盈亏</th>
                    <th className="py-3 px-4">仓位占比</th>
                    <th className="py-3 px-4 text-right">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-sans">
                  {positions.map((pos) => {
                    const unrealized = parseFloat(pos.unrealized_pnl);
                    const unrealizedPct = parseFloat(pos.unrealized_pnl_pct);
                    const weight = parseFloat(pos.weight_pct);

                    return (
                      <tr key={pos.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-4 font-mono font-extrabold text-white">
                          <button
                            onClick={() => navigate(`/research?symbol=${pos.symbol}`)}
                            className="hover:text-blue-400 transition-colors flex items-center gap-1 group"
                          >
                            <span>{pos.symbol}</span>
                            <ExternalLink className="h-3 w-3 opacity-0 group-hover:opacity-100" />
                          </button>
                        </td>
                        <td className="py-3 px-4 font-mono font-bold text-slate-200">
                          {pos.qty} 股
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-300">
                          ${parseFloat(pos.avg_cost).toFixed(2)}
                        </td>
                        <td className="py-3 px-4 font-mono font-medium text-white">
                          ${parseFloat(pos.current_price).toFixed(2)}
                        </td>
                        <td className="py-3 px-4 font-mono font-semibold text-slate-200">
                          ${parseFloat(pos.market_value).toLocaleString()}
                        </td>
                        <td className="py-3 px-4 font-mono">
                          <div className="flex flex-col">
                            <span
                              className={cn(
                                'font-bold',
                                unrealized >= 0 ? 'text-emerald-400' : 'text-rose-400',
                              )}
                            >
                              {unrealized >= 0 ? `+$${unrealized.toFixed(2)}` : `-$${Math.abs(unrealized).toFixed(2)}`}
                            </span>
                            <ChangePercent value={unrealizedPct} mode="compact" />
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono">
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-blue-500 rounded-full"
                                style={{ width: `${Math.min(100, weight)}%` }}
                              />
                            </div>
                            <span className="text-slate-300">{weight.toFixed(1)}%</span>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            {onQuickTrade && (
                              <Button
                                size="sm"
                                variant="danger"
                                onClick={() => onQuickTrade(pos.symbol, 'sell')}
                                title="快速卖出平仓"
                              >
                                快速平仓
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => navigate(`/research?symbol=${pos.symbol}`)}
                              title="查看研报"
                              aria-label="查看研报"
                              leftIcon={<ArrowRight className="h-3.5 w-3.5 text-slate-400" />}
                            />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* View 2: Orders Table */}
      {subTab === 'orders' && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 overflow-hidden shadow-sm">
          {filteredOrders.length === 0 ? (
            <div className="p-12 text-center text-slate-400 space-y-2">
              <ListFilter className="h-8 w-8 text-slate-600 mx-auto" />
              <p className="text-sm">暂无符合当前状态过滤条件的委托订单</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                  <tr>
                    <th className="py-3 px-4">委托时间</th>
                    <th className="py-3 px-4">标的代码</th>
                    <th className="py-3 px-4">买卖方向</th>
                    <th className="py-3 px-4">订单类型</th>
                    <th className="py-3 px-4">委托数量</th>
                    <th className="py-3 px-4">委托价格</th>
                    <th className="py-3 px-4">TIF 有效期</th>
                    <th className="py-3 px-4">订单状态</th>
                    <th className="py-3 px-4">入场理由/备注</th>
                    <th className="py-3 px-4 text-right">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-sans">
                  {filteredOrders.map((ord) => {
                    const isOpen = ord.status === 'accepted' || ord.status === 'pending';
                    const isCancelling = cancellingOrderId === ord.id;

                    return (
                      <tr key={ord.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-4 font-mono text-slate-400">
                          {new Date(ord.created_at).toLocaleTimeString()}
                        </td>
                        <td className="py-3 px-4 font-mono font-bold text-white">
                          {ord.symbol}
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={cn(
                              'px-2 py-0.5 rounded text-[10px] font-bold',
                              ord.side === 'buy'
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : 'bg-rose-500/20 text-rose-400 border border-rose-500/30',
                            )}
                          >
                            {ord.side === 'buy' ? 'BUY 买入' : 'SELL 卖出'}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono uppercase text-slate-300">
                          {ord.type}
                        </td>
                        <td className="py-3 px-4 font-mono font-bold text-white">
                          {ord.qty} 股
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-200">
                          {ord.type === 'market'
                            ? '市价成交'
                            : ord.limit_price
                              ? `$${parseFloat(ord.limit_price).toFixed(2)}`
                              : ord.stop_price
                                ? `止损 $${parseFloat(ord.stop_price).toFixed(2)}`
                                : '—'}
                        </td>
                        <td className="py-3 px-4 font-mono uppercase text-slate-400">
                          {ord.tif}
                        </td>
                        <td className="py-3 px-4">
                          {getOrderStatusBadge(ord.status)}
                        </td>
                        <td className="py-3 px-4 text-slate-300 max-w-xs truncate">
                          {ord.note || <span className="text-slate-500 italic">无</span>}
                        </td>
                        <td className="py-3 px-4 text-right">
                          {isOpen ? (
                            <Button
                              size="xs"
                              variant="danger"
                              isLoading={isCancelling}
                              onClick={() => handleCancelOrder(ord.id)}
                            >
                              一键撤单
                            </Button>
                          ) : (
                            <span className="text-slate-500 text-[11px]">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default PositionsAndOrdersView;
