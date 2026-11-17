import React, { useState } from 'react';
import { CheckCircle2, Clock, Filter, History, XCircle } from 'lucide-react';
import { AlertHistoryRead, DeliveryStatus } from '../../api/alerts';
import { Badge } from '../../components/common/Badge';
import { Card } from '../../components/common/Card';

export interface AlertHistoryViewProps {
  history: AlertHistoryRead[];
  onRefresh: () => void;
}

export const AlertHistoryView: React.FC<AlertHistoryViewProps> = ({ history }) => {
  const [filterSymbol, setFilterSymbol] = useState<string>('');
  const [selectedRecord, setSelectedRecord] = useState<AlertHistoryRead | null>(null);

  const filteredHistory = history.filter((h) => {
    if (filterSymbol.trim() && h.symbol && !h.symbol.toLowerCase().includes(filterSymbol.toLowerCase().trim())) {
      return false;
    }
    return true;
  });

  const getStatusBadge = (status: DeliveryStatus) => {
    switch (status) {
      case 'sent':
        return (
          <Badge variant="success" className="flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> 全部送达
          </Badge>
        );
      case 'partial':
        return (
          <Badge variant="warning" className="flex items-center gap-1">
            部分送达
          </Badge>
        );
      case 'failed':
      default:
        return (
          <Badge variant="danger" className="flex items-center gap-1">
            <XCircle className="w-3 h-3" /> 投递失败
          </Badge>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <History className="w-5 h-5 text-indigo-400" />
            提醒触发与分发历史审计流水
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            不可篡改的提醒事件触发记录，包含触发时行情或指标快照及各渠道投递详情。
          </p>
        </div>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3 bg-slate-900/80 p-3 rounded-lg border border-slate-800">
        <Filter className="w-4 h-4 text-slate-400" />
        <input
          type="text"
          placeholder="按标的代码筛选 (如 AAPL)"
          value={filterSymbol}
          onChange={(e) => setFilterSymbol(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded px-3 py-1.5 w-56 focus:outline-none focus:border-indigo-500"
        />
        <div className="text-xs text-slate-400 ml-auto">
          累计审计日志: <span className="text-indigo-400 font-semibold">{filteredHistory.length}</span> 条
        </div>
      </div>

      {/* History Table */}
      {filteredHistory.length === 0 ? (
        <Card className="p-8 text-center text-slate-400 border border-slate-800">
          <History className="w-12 h-12 mx-auto mb-3 text-slate-600 opacity-60" />
          <p className="text-base font-medium">暂无提醒触发记录</p>
          <p className="text-sm text-slate-500 mt-1">当规则条件命中时，系统将自动记录并派发通知</p>
        </Card>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/40">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-900/90 text-xs uppercase text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">触发时间</th>
                <th className="py-3 px-4">标的</th>
                <th className="py-3 px-4">提醒类型</th>
                <th className="py-3 px-4">触发行情快照</th>
                <th className="py-3 px-4">投递状态</th>
                <th className="py-3 px-4 text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-sans">
              {filteredHistory.map((item) => (
                <tr key={item.id} className="hover:bg-slate-850/50 transition-colors">
                  <td className="py-3 px-4 whitespace-nowrap text-xs text-slate-400">
                    <span className="flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 text-slate-500" />
                      {new Date(item.created_at).toLocaleString()}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-mono font-bold text-slate-200">
                    {item.symbol || '全市场/大盘'}
                  </td>
                  <td className="py-3 px-4">
                    <Badge variant="info">{item.alert_type}</Badge>
                  </td>
                  <td className="py-3 px-4 font-mono text-xs text-indigo-300 max-w-xs truncate">
                    {JSON.stringify(item.triggered_value)}
                  </td>
                  <td className="py-3 px-4 whitespace-nowrap">
                    {getStatusBadge(item.delivery_status)}
                  </td>
                  <td className="py-3 px-4 text-right">
                    <button
                      onClick={() => setSelectedRecord(item)}
                      className="text-xs text-indigo-400 hover:text-indigo-300 underline"
                    >
                      详情快照
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail Modal */}
      {selectedRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <Card className="w-full max-w-xl p-6 bg-slate-900 border border-slate-800 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <History className="w-4 h-4 text-indigo-400" />
                提醒触发审计详情
              </h3>
              <button
                onClick={() => setSelectedRecord(null)}
                className="text-slate-400 hover:text-slate-200 text-sm"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <span className="text-slate-400">消息文案：</span>
                <p className="text-slate-200 whitespace-pre-wrap mt-1 p-2.5 bg-slate-800/60 rounded border border-slate-700/60">
                  {selectedRecord.message}
                </p>
              </div>

              <div>
                <span className="text-slate-400">触发时快照参数：</span>
                <pre className="text-indigo-300 mt-1 p-2.5 bg-slate-950 rounded border border-slate-800 overflow-x-auto font-mono">
                  {JSON.stringify(selectedRecord.triggered_value, null, 2)}
                </pre>
              </div>

              <div>
                <span className="text-slate-400">送达渠道明细：</span>
                <pre className="text-emerald-300 mt-1 p-2.5 bg-slate-950 rounded border border-slate-800 overflow-x-auto font-mono">
                  {JSON.stringify(selectedRecord.delivered_channels, null, 2)}
                </pre>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setSelectedRecord(null)}
                className="px-4 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 rounded"
              >
                关闭
              </button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};

export default AlertHistoryView;
