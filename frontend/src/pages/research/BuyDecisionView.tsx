import React, { useState } from 'react';
import {
  ShieldCheck,
  Zap,
  Target,
  Sparkles,
  TrendingDown,
  ArrowRight,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { researchApi } from '../../api/research';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/common/Card';
import { DataFreshnessTag } from '../../components/compliance/DataFreshnessTag';
import { AIPromptVersionBadge } from '../../components/compliance/AIPromptVersionBadge';
import { ComplianceDisclaimer } from '../../components/compliance/ComplianceDisclaimer';
import { MOCK_BUY_DECISION_DATA } from './mockData';
import type { BuyDecisionRequest, ResearchEnvelope } from '../../api/types';

export interface BuyDecisionViewProps {
  initialSymbol?: string;
  onSelectSymbol?: (symbol: string) => void;
}

export const BuyDecisionView: React.FC<BuyDecisionViewProps> = ({
  initialSymbol = 'NVDA',
  onSelectSymbol,
}) => {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [targetPrice, setTargetPrice] = useState('140.00');
  const [horizon, setHorizon] = useState<'short' | 'medium' | 'long'>('medium');
  const [riskLevel, setRiskLevel] = useState<'conservative' | 'moderate' | 'aggressive'>('moderate');

  const [activeParams, setActiveParams] = useState<BuyDecisionRequest>({
    symbol: initialSymbol,
    target_price: parseFloat(targetPrice) || 140.0,
    horizon: 'medium',
    risk_level: 'moderate',
  });

  // 当外部传入 initialSymbol 改变时，同步更新内部状态与查询参数
  React.useEffect(() => {
    if (initialSymbol && initialSymbol !== symbol) {
      setSymbol(initialSymbol);
      setActiveParams((prev) => ({
        ...prev,
        symbol: initialSymbol,
      }));
    }
  }, [initialSymbol]);

  const isMockEnabled = import.meta.env.VITE_ENABLE_MOCK === 'true' || import.meta.env.MODE === 'test';

  const [decisionData, setDecisionData] = useState<ResearchEnvelope | null>(() => {
    if (isMockEnabled) {
      return MOCK_BUY_DECISION_DATA[initialSymbol] || null;
    }
    return null;
  });

  const query = useQuery({
    queryKey: ['ai-buy-decision', activeParams],
    queryFn: async () => {
      try {
        const res = await researchApi.getBuyDecision(activeParams);
        setDecisionData(res);
        return res;
      } catch (err) {
        if (import.meta.env.VITE_ENABLE_MOCK === 'true') {
          const mock = MOCK_BUY_DECISION_DATA[activeParams.symbol];
          if (mock) {
            setDecisionData(mock);
            return mock;
          }
        }
        throw err;
      }
    },
    staleTime: 5 * 60 * 1000,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanSym = symbol.trim().toUpperCase();
    const numPrice = parseFloat(targetPrice);
    if (cleanSym && !isNaN(numPrice) && numPrice > 0) {
      setDecisionData(null);
      setActiveParams({
        symbol: cleanSym,
        target_price: numPrice,
        horizon,
        risk_level: riskLevel,
      });
      onSelectSymbol?.(cleanSym);
    }
  };

  const currentData = query.data || decisionData;
  const payload = (currentData?.payload || {}) as Record<string, any>;
  const verdict: 'BUY' | 'WAIT' | 'AVOID' = (payload.verdict as any) || 'BUY';

  const verdictStyles = {
    BUY: {
      bg: 'bg-emerald-950/60 border-emerald-500/50 text-emerald-300',
      tag: 'bg-emerald-500 text-white',
      title: '建议买入 / 分批建仓 (BUY ON PULLBACK)',
    },
    WAIT: {
      bg: 'bg-amber-950/60 border-amber-500/50 text-amber-300',
      tag: 'bg-amber-500 text-slate-900',
      title: '耐心观望 / 等待更优入场位 (WAIT & WATCH)',
    },
    AVOID: {
      bg: 'bg-rose-950/60 border-rose-500/50 text-rose-300',
      tag: 'bg-rose-500 text-white',
      title: '规避风险 / 暂不建仓 (AVOID)',
    },
  };

  return (
    <div className="space-y-6">
      {/* 头部元数据栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <ShieldCheck className="h-6 w-6 text-blue-500" />
              买入决策评估工作台
            </h2>
            <AIPromptVersionBadge model="deepseek-chat" promptVersion="v1.2.0" />
          </div>
          <p className="text-xs text-slate-400 mt-1">
            结合目标买入价、投资周期与风险偏好，由 AI 多因子系统综合测算安全边际与执行建议。
          </p>
        </div>
        <DataFreshnessTag asOf={currentData?.as_of} />
      </div>

      {/* 输入控制卡片 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <Target className="h-4 w-4 text-blue-400" />
            输入决策评估参数
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            <div>
              <Input
                label="标的代码 (Symbol)"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                placeholder="NVDA"
              />
            </div>
            <div>
              <Input
                label="拟买入目标价 ($)"
                type="number"
                step="0.01"
                value={targetPrice}
                onChange={(e) => setTargetPrice(e.target.value)}
                placeholder="140.00"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                投资预期持有期
              </label>
              <select
                value={horizon}
                onChange={(e) => setHorizon(e.target.value as any)}
                className="w-full bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-lg py-2 px-3 focus:outline-none focus:border-blue-500"
              >
                <option value="short">短线 (数日–1月)</option>
                <option value="medium">中线 (1–6月)</option>
                <option value="long">长线 (6月–数年)</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                个人风险偏好
              </label>
              <select
                value={riskLevel}
                onChange={(e) => setRiskLevel(e.target.value as any)}
                className="w-full bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-lg py-2 px-3 focus:outline-none focus:border-blue-500"
              >
                <option value="conservative">保守型 (稳健保本)</option>
                <option value="moderate">平衡型 (合理风险)</option>
                <option value="aggressive">进取型 (追求超额)</option>
              </select>
            </div>
            <div className="flex items-end">
              <Button
                variant="primary"
                size="md"
                className="w-full"
                type="submit"
                isLoading={query.isLoading}
                leftIcon={<Zap className="h-4 w-4" />}
              >
                执行决策评估
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Loading state */}
      {query.isLoading && (
        <div className="p-12 rounded-xl border border-slate-800 bg-slate-900/40 text-center space-y-3">
          <Sparkles className="h-8 w-8 text-blue-400 mx-auto animate-pulse" />
          <h3 className="text-sm font-semibold text-white">正在调用 AI 多因子模型评估 {activeParams.symbol}...</h3>
          <p className="text-xs text-slate-400">正在分析财务数据、量价因子与宏观催化剂，生成结构化决策报告。</p>
        </div>
      )}

      {/* Error state */}
      {query.isError && (
        <div className="p-6 rounded-xl border border-rose-500/30 bg-rose-500/10 text-rose-300 text-xs space-y-2">
          <div className="flex items-center gap-2 font-bold text-sm text-rose-400">
            <TrendingDown className="h-4 w-4" />
            <span>AI 买入决策评估生成失败</span>
          </div>
          <p>{(query.error as Error)?.message || '后端服务异常或当前标的数据暂不可用'}</p>
          <div className="pt-2">
            <Button size="sm" variant="outline" onClick={() => query.refetch()}>
              重新评估
            </Button>
          </div>
        </div>
      )}

      {/* 核心决策结论卡片 */}
      {currentData && (
        <>
          <div className={`rounded-xl border p-5 shadow-lg space-y-4 ${verdictStyles[verdict].bg}`}>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span
                  className={`px-3 py-1 rounded-lg text-sm font-black tracking-wider uppercase ${verdictStyles[verdict].tag}`}
                >
                  {verdict}
                </span>
                <span className="text-base font-bold text-white">{verdictStyles[verdict].title}</span>
              </div>

              <div className="flex items-center gap-2 text-xs font-mono">
                <span className="text-slate-300">AI 置信度评分:</span>
                <span className="text-lg font-bold text-white">
                  {payload.confidence_score !== undefined && payload.confidence_score !== null
                    ? `${payload.confidence_score} / 100`
                    : payload.confidence !== undefined && payload.confidence !== null
                      ? `${Math.round(Number(payload.confidence) * 100)} / 100`
                      : '--'}
                </span>
              </div>
            </div>

            <p className="text-xs sm:text-sm text-slate-200 leading-relaxed font-sans border-t border-slate-800/60 pt-3">
              {currentData.summary}
            </p>

            {/* 关键测算指标一览 */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
              <div className="bg-slate-950/80 p-3 rounded-lg border border-slate-800">
                <div className="text-[11px] text-slate-400">现行市场价</div>
                <div className="text-base font-bold font-mono text-white mt-0.5">
                  {payload.current_price !== undefined && payload.current_price !== null
                    ? `$${payload.current_price}`
                    : '--'}
                </div>
              </div>
              <div className="bg-slate-950/80 p-3 rounded-lg border border-slate-800">
                <div className="text-[11px] text-slate-400">输入目标买入价</div>
                <div className="text-base font-bold font-mono text-white mt-0.5">
                  {payload.target_price !== undefined && payload.target_price !== null
                    ? `$${payload.target_price}`
                    : targetPrice
                      ? `$${targetPrice}`
                      : '--'}
                </div>
              </div>
              <div className="bg-slate-950/80 p-3 rounded-lg border border-slate-800">
                <div className="text-[11px] text-slate-400">安全边际 (Margin of Safety)</div>
                <div className="text-base font-bold font-mono text-emerald-400 mt-0.5">
                  {payload.margin_of_safety !== undefined && payload.margin_of_safety !== null
                    ? `${Number(payload.margin_of_safety) > 0 ? '+' : ''}${payload.margin_of_safety}%`
                    : '--'}
                </div>
              </div>
              <div className="bg-slate-950/80 p-3 rounded-lg border border-slate-800">
                <div className="text-[11px] text-slate-400">建议分批入场区间</div>
                <div className="text-sm font-bold font-mono text-sky-300 mt-0.5 truncate">
                  {Array.isArray(payload.suggested_entry_range)
                    ? `$${payload.suggested_entry_range[0]} - $${payload.suggested_entry_range[1]}`
                    : payload.suggested_entry_range || payload.better_entry_note || '--'}
                </div>
              </div>
            </div>
          </div>

          {/* 详细执行步骤与下行风险 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <ArrowRight className="h-4 w-4 text-emerald-400" />
                  建议分批操作行动方案 (Actionable Plan)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-slate-300 leading-relaxed">
                  {payload.actionable_plan ||
                    '首批仓位（30%）可于现价小额建仓，第二批加仓（40%）挂单于支撑位附近，严格防守止损位。'}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm text-rose-400 flex items-center gap-2">
                  <TrendingDown className="h-4 w-4" />
                  最大潜在下行风险测算 (Downside Risk)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-slate-300 leading-relaxed">
                  {payload.max_downside_risk || '-16.5%（若跌破关键均线支撑位，将触发阶段性防御离场）'}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* 催化剂清单 */}
          {payload.key_catalysts && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-amber-400" />
                  关注催化剂与上行驱动 (Key Catalysts)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1.5 text-xs text-slate-300">
                  {payload.key_catalysts.map((cat: string, idx: number) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-amber-400">✦</span>
                      <span>{cat}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* 合规免责声明 */}
      <ComplianceDisclaimer variant="card" />
    </div>
  );
};

export default BuyDecisionView;
