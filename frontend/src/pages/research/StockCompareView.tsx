import React, { useState } from 'react';
import {
  Scale,
  Plus,
  X,
  UserCheck,
  Sparkles,
  BarChart3,
  Trophy,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { researchApi } from '../../api/research';
import { Button } from '../../components/common/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/common/Card';
import { DataFreshnessTag } from '../../components/compliance/DataFreshnessTag';
import { AIPromptVersionBadge } from '../../components/compliance/AIPromptVersionBadge';
import { ComplianceDisclaimer } from '../../components/compliance/ComplianceDisclaimer';
import { MOCK_COMPARE_DATA } from './mockData';

export const StockCompareView: React.FC = () => {
  const [symbols, setSymbols] = useState<string[]>(['NVDA', 'MSFT', 'AAPL']);
  const [inputVal, setInputVal] = useState('');

  const presetGroups = [
    { name: '芯片算力巨头', list: ['NVDA', 'AMD', 'TSM', 'AVGO'] },
    { name: '美股科技前三', list: ['NVDA', 'MSFT', 'AAPL'] },
    { name: '云计算与SaaS', list: ['MSFT', 'AMZN', 'CRM'] },
    { name: 'AI 平台先锋', list: ['NVDA', 'PLTR', 'MSFT', 'GOOGL'] },
  ];

  const handleAddSymbol = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = inputVal.trim().toUpperCase();
    if (clean && !symbols.includes(clean) && symbols.length < 8) {
      setSymbols([...symbols, clean]);
      setInputVal('');
    }
  };

  const handleRemoveSymbol = (sym: string) => {
    if (symbols.length > 2) {
      setSymbols(symbols.filter((s) => s !== sym));
    }
  };

  const handleApplyPreset = (list: string[]) => {
    setSymbols(list);
  };

  const query = useQuery({
    queryKey: ['ai-compare', symbols],
    queryFn: async () => {
      try {
        return await researchApi.getCompare(symbols);
      } catch {
        return MOCK_COMPARE_DATA;
      }
    },
    staleTime: 5 * 60 * 1000,
  });

  const compareData = query.data || MOCK_COMPARE_DATA;
  const payload = (compareData.payload || {}) as Record<string, any>;
  const rankings = (payload.rankings || []) as any[];
  const winner = (payload.winner || {}) as Record<string, string>;
  const dimensionMatrix = (payload.dimension_matrix || []) as any[];

  return (
    <div className="space-y-6">
      {/* 头部元数据栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <Scale className="h-6 w-6 text-blue-500" />
              多标的横向对比矩阵 (Stock Compare)
            </h2>
            <AIPromptVersionBadge model="deepseek-chat" promptVersion="v1.2.0" />
          </div>
          <p className="text-xs text-slate-400 mt-1">
            支持 2–8 只股票横向多维对比，自动测算综合排名、定性维度胜率与不同投资风格画像匹配。
          </p>
        </div>
        <DataFreshnessTag asOf={compareData.as_of} />
      </div>

      {/* 对比标的管理与预设 */}
      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            {/* 标的标签列表 */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-400 mr-1">对比标的池 (最多8只):</span>
              {symbols.map((sym) => (
                <span
                  key={sym}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-blue-950/70 border border-blue-500/40 text-blue-200 text-xs font-mono font-bold"
                >
                  {sym}
                  {symbols.length > 2 && (
                    <button
                      onClick={() => handleRemoveSymbol(sym)}
                      className="hover:text-white p-0.5"
                      title="移除"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </span>
              ))}
            </div>

            {/* 新增输入 */}
            <form onSubmit={handleAddSymbol} className="flex items-center gap-2">
              <input
                type="text"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value.toUpperCase())}
                placeholder="添加代码 (如 TSM)"
                className="w-36 bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
              <Button
                variant="outline"
                size="sm"
                type="submit"
                disabled={symbols.length >= 8 || !inputVal.trim()}
                leftIcon={<Plus className="h-3.5 w-3.5" />}
              >
                添加
              </Button>
            </form>
          </div>

          {/* 预设方案 */}
          <div className="flex items-center gap-2 flex-wrap pt-2 border-t border-slate-800 text-xs">
            <span className="text-slate-500">一键套用对比组:</span>
            {presetGroups.map((p) => (
              <button
                key={p.name}
                onClick={() => handleApplyPreset(p.list)}
                className="px-2.5 py-1 rounded-md bg-slate-900 border border-slate-700/80 hover:border-slate-500 text-slate-300 text-[11px] transition-colors"
              >
                {p.name}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 结论摘要 */}
      <Card className="border-l-4 border-l-indigo-500">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-indigo-400" />
            AI 对比综合结论
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs sm:text-sm text-slate-200 leading-relaxed font-sans">
            {compareData.summary}
          </p>
        </CardContent>
      </Card>

      {/* 各维度胜出标的栏 */}
      {winner.overall && (
        <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl bg-slate-900 border border-slate-800 text-xs">
          <div className="flex items-center gap-1.5 text-amber-400 font-semibold">
            <Trophy className="h-4 w-4" />
            <span>维度最佳标的:</span>
          </div>
          <div className="flex flex-wrap items-center gap-3 font-mono">
            <div>
              <span className="text-slate-400 mr-1">综合最佳:</span>
              <span className="text-white font-bold">{winner.overall}</span>
            </div>
            {winner.growth && (
              <div>
                <span className="text-slate-400 mr-1">成长最快:</span>
                <span className="text-sky-300 font-bold">{winner.growth}</span>
              </div>
            )}
            {winner.value && (
              <div>
                <span className="text-slate-400 mr-1">估值最优:</span>
                <span className="text-emerald-300 font-bold">{winner.value}</span>
              </div>
            )}
            {winner.safety && (
              <div>
                <span className="text-slate-400 mr-1">抗风险最强:</span>
                <span className="text-purple-300 font-bold">{winner.safety}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 各维度胜出与综合排名 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {rankings.map((r: any) => (
          <div
            key={r.symbol}
            className={`rounded-xl border p-4 space-y-3 transition-all ${
              r.rank === 1
                ? 'bg-blue-950/30 border-blue-500/50 shadow-md shadow-blue-900/20'
                : 'bg-slate-900/60 border-slate-800'
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs ${
                    r.rank === 1
                      ? 'bg-amber-500 text-slate-900'
                      : r.rank === 2
                      ? 'bg-slate-300 text-slate-900'
                      : 'bg-slate-700 text-white'
                  }`}
                >
                  {r.rank}
                </span>
                <span className="text-lg font-bold font-mono text-white">{r.symbol}</span>
              </div>
              <span className="text-xs font-mono font-semibold text-blue-400">
                综合评分: {r.score}
              </span>
            </div>

            <div className="p-2 rounded bg-slate-950/70 border border-slate-800 text-xs">
              <div className="flex items-center gap-1.5 text-slate-400 font-medium mb-1">
                <UserCheck className="h-3.5 w-3.5 text-emerald-400" />
                适合投资者画像:
              </div>
              <p className="text-emerald-300 text-[11px] font-medium">{r.suitable_for}</p>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">{r.rationale}</p>
          </div>
        ))}
      </div>

      {/* 多维度量化对比矩阵表 */}
      {dimensionMatrix.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-sky-400" />
              多维度定性与量化对比矩阵 (100分制)
            </CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-950 border-b border-slate-800 text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-semibold">分析维度</th>
                  {symbols.map((sym) => (
                    <th key={sym} className="px-4 py-3 font-mono font-bold text-white text-center">
                      {sym}
                    </th>
                  ))}
                  <th className="px-4 py-3 font-semibold text-right">该项胜出</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {dimensionMatrix.map((row: any) => {
                  let maxScore = -1;
                  let maxSym = '';
                  symbols.forEach((s) => {
                    const sc = row.scores[s] ?? 0;
                    if (sc > maxScore) {
                      maxScore = sc;
                      maxSym = s;
                    }
                  });

                  return (
                    <tr key={row.dimension} className="hover:bg-slate-900/60">
                      <td className="px-4 py-3 font-sans text-slate-300 font-medium">
                        {row.dimension}
                      </td>
                      {symbols.map((s) => {
                        const sc = row.scores[s] ?? '--';
                        const isMax = s === maxSym;
                        return (
                          <td
                            key={s}
                            className={`px-4 py-3 text-center ${
                              isMax ? 'text-emerald-400 font-bold bg-emerald-950/20' : 'text-slate-400'
                            }`}
                          >
                            {sc}
                          </td>
                        );
                      })}
                      <td className="px-4 py-3 text-right">
                        <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                          {maxSym}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* 合规免责声明 */}
      <ComplianceDisclaimer variant="card" />
    </div>
  );
};

export default StockCompareView;
