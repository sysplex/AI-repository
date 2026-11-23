import React, { useState } from 'react';
import {
  Hourglass,
  AlertTriangle,
  Award,
  Shield,
  Search,
  AlertOctagon,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { researchApi } from '../../api/research';
import { Button } from '../../components/common/Button';
import { Card, CardContent } from '../../components/common/Card';
import { DataFreshnessTag } from '../../components/compliance/DataFreshnessTag';
import { AIPromptVersionBadge } from '../../components/compliance/AIPromptVersionBadge';
import { ComplianceDisclaimer } from '../../components/compliance/ComplianceDisclaimer';
import { MOCK_LONG_TERM_DATA } from './mockData';

export const LongTermView: React.FC<{ initialSymbol?: string }> = ({ initialSymbol = 'NVDA' }) => {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [searchInput, setSearchInput] = useState(initialSymbol);
  const [years, setYears] = useState<5 | 10 | 15>(5);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = searchInput.trim().toUpperCase();
    if (clean) setSymbol(clean);
  };

  const isMockEnabled = import.meta.env.VITE_ENABLE_MOCK === 'true' || import.meta.env.MODE === 'test';

  const query = useQuery({
    queryKey: ['ai-long-term', symbol, years],
    queryFn: async () => {
      try {
        return await researchApi.getLongTerm(symbol, years);
      } catch (err) {
        if (isMockEnabled) {
          return MOCK_LONG_TERM_DATA[symbol] || MOCK_LONG_TERM_DATA.NVDA;
        }
        throw err;
      }
    },
    staleTime: 5 * 60 * 1000,
  });

  const longTermData = query.data || (isMockEnabled ? (MOCK_LONG_TERM_DATA[symbol] || MOCK_LONG_TERM_DATA.NVDA) : null);
  const payload = (longTermData?.payload || {}) as Record<string, any>;
  const pillars = (payload.pillars || []) as any[];
  const thesisBreakers = (payload.thesis_breakers || []) as any[];

  const tierBadgeStyle = (tier: string) => {
    if (tier.startsWith('Tier 1')) {
      return 'bg-gradient-to-r from-amber-500/20 via-yellow-500/20 to-amber-600/20 text-amber-300 border-amber-500/40';
    }
    if (tier.startsWith('Tier 2')) {
      return 'bg-blue-950/60 text-blue-300 border-blue-500/40';
    }
    return 'bg-slate-800 text-slate-300 border-slate-700';
  };

  const severityStyle = (sev: string) => {
    switch (sev.toUpperCase()) {
      case 'CRITICAL':
        return {
          card: 'border-rose-500/50 bg-rose-950/20',
          badge: 'bg-rose-500 text-white',
          icon: <AlertOctagon className="h-4 w-4 text-rose-400" />,
        };
      case 'HIGH':
        return {
          card: 'border-amber-500/50 bg-amber-950/20',
          badge: 'bg-amber-500 text-slate-900',
          icon: <AlertTriangle className="h-4 w-4 text-amber-400" />,
        };
      default:
        return {
          card: 'border-sky-500/40 bg-sky-950/20',
          badge: 'bg-sky-500 text-white',
          icon: <Shield className="h-4 w-4 text-sky-400" />,
        };
    }
  };

  return (
    <div className="space-y-6">
      {/* 头部元数据栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <Hourglass className="h-6 w-6 text-amber-500" />
              长期持有价值与论文破裂监控 (Long-Term Pillars & Thesis Breakers)
            </h2>
            <AIPromptVersionBadge model="deepseek-chat" promptVersion="v1.2.0" />
          </div>
          <p className="text-xs text-slate-400 mt-1">
            评估 5–15 年跨周期的 7 大价值支柱，并建立不可妥协的「投资逻辑破裂退出条件」监控体系。
          </p>
        </div>
        <DataFreshnessTag asOf={longTermData?.as_of} />
      </div>

      {/* 控制栏：标的代码与持有期切换 */}
      <Card>
        <CardContent className="p-4 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
          <form onSubmit={handleSearch} className="flex items-center gap-2 max-w-sm w-full">
            <div className="relative flex-1">
              <Search className="h-4 w-4 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
                placeholder="输入代码 (如 NVDA)"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
              />
            </div>
            <Button variant="primary" size="sm" type="submit" isLoading={query.isLoading}>
              分析评级
            </Button>
          </form>

          {/* 持有年限按钮 */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">持有时间跨度:</span>
            {([5, 10, 15] as const).map((yr) => (
              <button
                key={yr}
                onClick={() => setYears(yr)}
                className={`px-3 py-1 rounded-lg text-xs font-mono font-bold border transition-colors ${
                  years === yr
                    ? 'bg-amber-500 text-slate-900 border-amber-400 shadow-sm'
                    : 'bg-slate-950 text-slate-300 border-slate-800 hover:border-slate-700'
                }`}
              >
                {yr} 年期
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 错误展示 */}
      {query.isError && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/50 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-rose-200">
          <div>
            <div className="font-semibold text-rose-400">长期价值评估失败</div>
            <div className="text-xs text-rose-300 mt-1">
              {(query.error as Error)?.message || '无法获取标的长期价值支柱，请检查服务或稍后重试'}
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="border-rose-500/50 text-rose-300 hover:bg-rose-900/40"
            onClick={() => query.refetch()}
          >
            重试
          </Button>
        </div>
      )}

      {/* 加载骨架屏 */}
      {query.isLoading && (
        <div className="space-y-4 animate-pulse">
          <div className="h-28 bg-slate-800/40 rounded-xl" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="h-44 bg-slate-800/40 rounded-xl" />
            <div className="h-44 bg-slate-800/40 rounded-xl" />
          </div>
        </div>
      )}

      {longTermData && (
        <>
          {/* 评级大卡片 */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5 space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="text-xl font-bold font-mono text-white">{symbol}</span>
                <span className={`px-3 py-1 rounded-lg text-xs font-bold border ${tierBadgeStyle(payload.rating || '')}`}>
                  {payload.rating || '--'}
                </span>
              </div>
              <div className="flex items-center gap-2 font-mono text-xs">
                <span className="text-slate-400">7大支柱综合评分:</span>
                <span className="text-2xl font-black text-amber-400">{payload.score ?? '--'}</span>
                <span className="text-slate-500">/ 100</span>
              </div>
            </div>

            <p className="text-xs sm:text-sm text-slate-200 leading-relaxed font-sans border-t border-slate-800 pt-2">
              {longTermData.summary}
            </p>
          </div>

      {/* 7 大核心支柱评级网格 */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Award className="h-4 w-4 text-amber-400" />
            7 大长期价值支柱综合评定（7 Pillars Assessment）
          </h3>
          <span className="text-xs text-slate-400 font-mono">严格对齐 docs/06-ai-prompt-spec.md</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {pillars.map((p: any, idx: number) => (
            <div
              key={p.name}
              className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-2 hover:border-slate-700 transition-colors"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-200">
                  {idx + 1}. {p.name}
                </span>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  {p.tier} ({p.score}分)
                </span>
              </div>
              <p className="text-[11px] text-slate-400 leading-relaxed">{p.rationale}</p>
            </div>
          ))}
        </div>
      </div>

      {/* 论文破裂监控条件卡片 (Thesis Breakers) */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-rose-400 flex items-center gap-2">
            <AlertOctagon className="h-4 w-4" />
            论文破裂条件监控预警（Thesis Breakers Guardrails）
          </h3>
          <span className="text-xs text-slate-400">若任一条触发，应立刻重新审视持有逻辑</span>
        </div>

        <div className="space-y-3">
          {thesisBreakers.map((tb: any, i: number) => {
            const style = severityStyle(tb.severity);
            return (
              <div
                key={i}
                className={`rounded-xl border p-4 space-y-2.5 transition-all ${style.card}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {style.icon}
                    <span className="text-xs font-bold text-white uppercase tracking-wider">
                      破裂条件 #{i + 1}
                    </span>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${style.badge}`}>
                    {tb.severity}
                  </span>
                </div>

                <p className="text-xs text-slate-200 font-medium leading-relaxed">
                  {tb.condition}
                </p>

                <div className="p-2 rounded-lg bg-slate-950/80 border border-slate-800/80 text-[11px] text-slate-400 flex items-start gap-2">
                  <span className="text-slate-500 shrink-0">量化监测指标:</span>
                  <span className="font-mono text-slate-300">{tb.monitoring_metric}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      </>
      )}

      {/* 合规免责声明 */}
      <ComplianceDisclaimer variant="card" />
    </div>
  );
};

export default LongTermView;
