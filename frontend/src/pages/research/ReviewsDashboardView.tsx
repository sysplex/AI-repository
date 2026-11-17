import React, { useEffect, useState } from 'react';
import {
  Award,
  BarChart3,
  CheckCircle2,
  Filter,
  Percent,
  Search,
  TrendingUp,
} from 'lucide-react';
import { ReviewSummaryResponse, reviewsApi } from '../../api/reviews';
import { Badge } from '../../components/common/Badge';
import { Card } from '../../components/common/Card';

export const ReviewsDashboardView: React.FC = () => {
  const [summary, setSummary] = useState<ReviewSummaryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [filterVerdict, setFilterVerdict] = useState<string>('all');
  const [filterSymbol, setFilterSymbol] = useState<string>('');

  const loadOutcomes = async () => {
    setLoading(true);
    try {
      const data = await reviewsApi.getOutcomesSummary({
        verdict: filterVerdict === 'all' ? undefined : filterVerdict,
        symbol: filterSymbol.trim() ? filterSymbol.trim().toUpperCase() : undefined,
        limit: 100,
      });
      setSummary(data);
    } catch (err: unknown) {
      console.error('Failed to load AI review outcomes', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOutcomes();
  }, [filterVerdict]);

  const formatPct = (val: number | string | null | undefined) => {
    if (val === null || val === undefined) return '-';
    const num = Number(val) * 100;
    return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
          <Award className="w-5 h-5 text-indigo-400" />
          AI 投资建议事后表现评估与胜率看板
        </h2>
        <p className="text-sm text-slate-400 mt-1">
          无未来函数严格复盘：基于建议出具后 T+5 / T+20 / T+60 日真实交易日收盘表现，计算绝对收益与相对 SPY 超额 Alpha。
        </p>
      </div>

      {/* KPI Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="p-4 bg-slate-900/60 border border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>出具研报 / 已评估样本</span>
              <BarChart3 className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="text-xl font-bold font-mono text-slate-100 mt-2">
              {summary.total_recommendations} <span className="text-sm text-slate-500 font-normal">/ {summary.evaluated_count}</span>
            </div>
            <div className="text-xs text-slate-500 mt-1">历史累计 AI 决策</div>
          </Card>

          <Card className="p-4 bg-slate-900/60 border border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>20 日综合胜率 (Win Rate)</span>
              <Percent className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-xl font-bold font-mono text-emerald-400 mt-2">
              {summary.win_rate_20d !== null ? `${(Number(summary.win_rate_20d) * 100).toFixed(1)}%` : '-'}
            </div>
            <div className="text-xs text-slate-500 mt-1">看多正收益 / 看空避险</div>
          </Card>

          <Card className="p-4 bg-slate-900/60 border border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>相对 SPY 20日超额 Alpha</span>
              <TrendingUp className="w-4 h-4 text-indigo-400" />
            </div>
            <div
              className={`text-xl font-bold font-mono mt-2 ${
                Number(summary.avg_alpha_20d || 0) >= 0 ? 'text-indigo-400' : 'text-rose-400'
              }`}
            >
              {formatPct(summary.avg_alpha_20d)}
            </div>
            <div className="text-xs text-slate-500 mt-1">平均超越大盘幅度</div>
          </Card>

          <Card className="p-4 bg-slate-900/60 border border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>20 日平均绝对收益率</span>
              <CheckCircle2 className="w-4 h-4 text-sky-400" />
            </div>
            <div
              className={`text-xl font-bold font-mono mt-2 ${
                Number(summary.avg_return_20d || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {formatPct(summary.avg_return_20d)}
            </div>
            <div className="text-xs text-slate-500 mt-1">5日: {formatPct(summary.avg_return_5d)} ｜ 60日: {formatPct(summary.avg_return_60d)}</div>
          </Card>
        </div>
      )}

      {/* Breakdown by Verdict */}
      {summary && summary.by_verdict && Object.keys(summary.by_verdict).length > 0 && (
        <Card className="p-5 bg-slate-900/40 border border-slate-800 space-y-3">
          <h3 className="text-sm font-bold text-slate-200">按建议结论分类胜率与收益统计 (By Verdict)</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-800/80 uppercase text-slate-400 border-b border-slate-700/60">
                <tr>
                  <th className="py-2.5 px-3">结论标签</th>
                  <th className="py-2.5 px-3">研报数</th>
                  <th className="py-2.5 px-3">20日胜率</th>
                  <th className="py-2.5 px-3">5日均收益</th>
                  <th className="py-2.5 px-3">20日均收益</th>
                  <th className="py-2.5 px-3">60日均收益</th>
                  <th className="py-2.5 px-3">SPY 超额 Alpha</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {Object.entries(summary.by_verdict).map(([v, stat]) => (
                  <tr key={v} className="hover:bg-slate-800/30">
                    <td className="py-2.5 px-3 font-sans">
                      <Badge
                        variant={
                          ['buy', 'strong_buy'].includes(v)
                            ? 'success'
                            : ['avoid', 'sell'].includes(v)
                            ? 'danger'
                            : 'neutral'
                        }
                      >
                        {v}
                      </Badge>
                    </td>
                    <td className="py-2.5 px-3">{stat.total_count}</td>
                    <td className="py-2.5 px-3 text-emerald-400 font-semibold">
                      {stat.win_rate_20d !== null ? `${(Number(stat.win_rate_20d) * 100).toFixed(1)}%` : '-'}
                    </td>
                    <td className="py-2.5 px-3">{formatPct(stat.avg_return_5d)}</td>
                    <td className="py-2.5 px-3">{formatPct(stat.avg_return_20d)}</td>
                    <td className="py-2.5 px-3">{formatPct(stat.avg_return_60d)}</td>
                    <td className="py-2.5 px-3 text-indigo-300">{formatPct(stat.avg_alpha_20d)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Filter and Items Table */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3 bg-slate-900/80 p-3 rounded-lg border border-slate-800">
          <Filter className="w-4 h-4 text-slate-400" />
          <select
            value={filterVerdict}
            onChange={(e) => setFilterVerdict(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-3 py-1.5 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">全部结论类型</option>
            <option value="buy">买入 (buy)</option>
            <option value="strong_buy">强烈推荐买入 (strong_buy)</option>
            <option value="holdable">适合长持 (holdable)</option>
            <option value="neutral">中性观望 (neutral)</option>
            <option value="avoid">避开风险 (avoid)</option>
          </select>

          <div className="flex items-center gap-1.5 ml-auto">
            <input
              type="text"
              placeholder="搜索标的代码 (如 AAPL)"
              value={filterSymbol}
              onChange={(e) => setFilterSymbol(e.target.value)}
              className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-3 py-1.5 w-44 focus:outline-none focus:border-indigo-500"
            />
            <button
              onClick={loadOutcomes}
              className="p-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs"
            >
              <Search className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="p-8 text-center text-slate-400">正在计算复盘指标...</div>
        ) : !summary || summary.items.length === 0 ? (
          <Card className="p-8 text-center text-slate-400 border border-slate-800">
            <p className="text-sm">暂无符合条件的复盘标的明细</p>
          </Card>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/40">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-900/90 uppercase text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-3">出具日期</th>
                  <th className="py-2.5 px-3">标的代码</th>
                  <th className="py-2.5 px-3">建议结论</th>
                  <th className="py-2.5 px-3">基准价 (P0)</th>
                  <th className="py-2.5 px-3">5日收益率</th>
                  <th className="py-2.5 px-3">20日收益率</th>
                  <th className="py-2.5 px-3">60日收益率</th>
                  <th className="py-2.5 px-3">相对 SPY Alpha</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {summary.items.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-800/40">
                    <td className="py-2.5 px-3 whitespace-nowrap text-slate-400">
                      {item.created_at.split('T')[0]}
                    </td>
                    <td className="py-2.5 px-3 font-bold text-slate-200">{item.symbol}</td>
                    <td className="py-2.5 px-3 font-sans">
                      <Badge
                        variant={
                          ['buy', 'strong_buy'].includes(item.verdict)
                            ? 'success'
                            : ['avoid', 'sell'].includes(item.verdict)
                            ? 'danger'
                            : 'neutral'
                        }
                      >
                        {item.verdict}
                      </Badge>
                    </td>
                    <td className="py-2.5 px-3">${Number(item.p0 || 0).toFixed(2)}</td>
                    <td
                      className={`py-2.5 px-3 ${
                        Number(item.ret_5d || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {formatPct(item.ret_5d)}
                    </td>
                    <td
                      className={`py-2.5 px-3 font-bold ${
                        Number(item.ret_20d || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {formatPct(item.ret_20d)}
                    </td>
                    <td
                      className={`py-2.5 px-3 ${
                        Number(item.ret_60d || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {formatPct(item.ret_60d)}
                    </td>
                    <td
                      className={`py-2.5 px-3 ${
                        Number(item.ret_vs_spy_20d || 0) >= 0
                          ? 'text-indigo-400'
                          : 'text-rose-400'
                      }`}
                    >
                      {formatPct(item.ret_vs_spy_20d)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReviewsDashboardView;
