import React, { useState } from 'react';
import {
  Brain,
  Search,
  Sparkles,
  TrendingUp,
  TrendingDown,
  ShieldAlert,
  Layers,
  FileText,
  BarChart2,
  Calendar,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { researchApi } from '../../api/research';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/common/Card';
import { StockCandleChart } from '../../components/chart/StockCandleChart';
import { DataFreshnessTag } from '../../components/compliance/DataFreshnessTag';
import { AIPromptVersionBadge } from '../../components/compliance/AIPromptVersionBadge';
import { ComplianceDisclaimer } from '../../components/compliance/ComplianceDisclaimer';
import { useMarketData } from '../../hooks/useMarketData';
import { MOCK_RESEARCH_DATA, MOCK_EARNINGS_DATA } from './mockData';

export interface StockDeepDiveViewProps {
  initialSymbol?: string;
  onSelectSymbol?: (symbol: string) => void;
}

export const StockDeepDiveView: React.FC<StockDeepDiveViewProps> = ({
  initialSymbol = 'NVDA',
  onSelectSymbol,
}) => {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [searchInput, setSearchInput] = useState(initialSymbol);
  const [showChart, setShowChart] = useState(true);

  const quickSymbols = ['NVDA', 'AAPL', 'MSFT', 'TSLA', 'PLTR', 'AMZN'];

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = searchInput.trim().toUpperCase();
    if (clean) {
      setSymbol(clean);
      onSelectSymbol?.(clean);
    }
  };

  const handleQuickSelect = (sym: string) => {
    setSymbol(sym);
    setSearchInput(sym);
    onSelectSymbol?.(sym);
  };

  // 1. 获取 AI 个股研报
  const researchQuery = useQuery({
    queryKey: ['ai-research', symbol],
    queryFn: async () => {
      try {
        return await researchApi.getResearch(symbol);
      } catch {
        return MOCK_RESEARCH_DATA[symbol] || MOCK_RESEARCH_DATA.NVDA;
      }
    },
    staleTime: 5 * 60 * 1000,
  });

  // 2. 获取财报解读
  const earningsQuery = useQuery({
    queryKey: ['ai-earnings', symbol],
    queryFn: async () => {
      try {
        return await researchApi.getEarnings(symbol);
      } catch {
        return MOCK_EARNINGS_DATA[symbol] || MOCK_EARNINGS_DATA.NVDA;
      }
    },
    staleTime: 5 * 60 * 1000,
  });

  // 3. 关联 K 线行情
  const {
    candles,
    volumeBars,
    sma20,
    sma50,
    sma200,
    keyLevels,
  } = useMarketData({
    symbol,
    interval: '1d',
    lookbackDays: 180,
    enabled: showChart,
  });

  const researchData = researchQuery.data || MOCK_RESEARCH_DATA.NVDA;
  const earningsData = earningsQuery.data || MOCK_EARNINGS_DATA.NVDA;

  const payload = (researchData.payload || {}) as Record<string, any>;
  const earningsPayload = (earningsData.payload || {}) as Record<string, any>;

  return (
    <div className="space-y-6">
      {/* 搜索与快捷标的栏 */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-slate-900/80 p-4 rounded-xl border border-slate-800">
        <form onSubmit={handleSearch} className="flex items-center gap-2 max-w-md w-full">
          <div className="relative flex-1">
            <Search className="h-4 w-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="输入美股代码 (如 NVDA, AAPL)..."
              className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>
          <Button variant="primary" size="sm" type="submit" isLoading={researchQuery.isLoading}>
            研报分析
          </Button>
        </form>

        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-slate-400 mr-1">热门标的:</span>
          {quickSymbols.map((s) => (
            <button
              key={s}
              onClick={() => handleQuickSelect(s)}
              className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium border transition-colors ${
                symbol === s
                  ? 'bg-blue-600 text-white border-blue-500 shadow-sm'
                  : 'bg-slate-950 text-slate-300 border-slate-800 hover:border-slate-700'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* 标的概览与合规元数据条 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold font-mono tracking-tight text-white">{symbol}</h2>
          <Badge variant="purple" size="sm">
            <Sparkles className="h-3 w-3" />
            AI 深度研报
          </Badge>
          <AIPromptVersionBadge model="deepseek-chat" promptVersion="v1.2.0" />
        </div>
        <div className="flex items-center gap-3">
          <DataFreshnessTag asOf={researchData.as_of} />
          <Button
            variant="outline"
            size="xs"
            onClick={() => setShowChart(!showChart)}
            leftIcon={<BarChart2 className="h-3.5 w-3.5" />}
          >
            {showChart ? '折叠 K 线' : '展开 K 线图'}
          </Button>
        </div>
      </div>

      {/* 嵌入 K 线图表 */}
      {showChart && candles.length > 0 && (
        <div className="space-y-2">
          <StockCandleChart
            symbol={symbol}
            candles={candles}
            volumeBars={volumeBars}
            sma20={sma20}
            sma50={sma50}
            sma200={sma200}
            supportLevel={keyLevels.support}
            resistanceLevel={keyLevels.resistance}
            height={400}
          />
        </div>
      )}

      {/* 1. 核心结论通俗摘要 */}
      <Card className="border-l-4 border-l-blue-500">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Brain className="h-4 w-4 text-blue-400" />
            AI 核心投研综述
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-200 leading-relaxed font-sans">{researchData.summary}</p>
        </CardContent>
      </Card>

      {/* 2. 三段式情景推演 (Bull / Neutral / Bear) */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
          <Layers className="h-4 w-4 text-indigo-400" />
          三段式情景推演（Three-Scenario Framework）
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Bull Case */}
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4 space-y-2">
            <div className="flex items-center gap-1.5 text-emerald-400 font-semibold text-sm">
              <TrendingUp className="h-4 w-4" />
              <span>看涨情景（Bull Case）</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              {payload.bull_case || '算力需求持续爆发，新一代产品加速放量，毛利率与净利率持续扩张。'}
            </p>
          </div>

          {/* Neutral Case */}
          <div className="rounded-xl border border-blue-500/30 bg-blue-950/20 p-4 space-y-2">
            <div className="flex items-center gap-1.5 text-blue-400 font-semibold text-sm">
              <BarChart2 className="h-4 w-4" />
              <span>中性基准（Base Case）</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              {payload.neutral_case || '业务平稳符合预期，算力支出保持中高增速，估值维持中枢区间。'}
            </p>
          </div>

          {/* Bear Case */}
          <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-4 space-y-2">
            <div className="flex items-center gap-1.5 text-rose-400 font-semibold text-sm">
              <TrendingDown className="h-4 w-4" />
              <span>看跌情景（Bear Case）</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              {payload.bear_case || '资本开支不及预期，市场竞争加剧导致产品降价，面临戴维斯双杀。'}
            </p>
          </div>
        </div>
      </div>

      {/* 3. 商业模式与护城河 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <FileText className="h-4 w-4 text-sky-400" />
              商业模式与变现逻辑 (Business Model)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-slate-300 leading-relaxed">
              {payload.business_model || '软硬件一体化生态，核心来自计算与网络设备的高毛利硬件销售与企业订阅服务。'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-emerald-400" />
              经济护城河深度 (Economic Moat)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-slate-300 leading-relaxed">
              {payload.moat || '极高的生态转移成本与开发者网络效应，底层生态绑定带来深厚的竞争护城河。'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 4. 核心风险点 */}
      {payload.risks && payload.risks.length > 0 && (
        <Card className="border-rose-900/40 bg-rose-950/10">
          <CardHeader>
            <CardTitle className="text-sm text-rose-400 flex items-center gap-2">
              <AlertCircle className="h-4 w-4" />
              主要投资风险提示 (Key Risks)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5 text-xs text-slate-300">
              {payload.risks.map((risk: string, i: number) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-rose-500 font-bold">•</span>
                  <span>{risk}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* 5. 财报解读板块 */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2">
              <Calendar className="h-4 w-4 text-purple-400" />
              最新财报深度解读（Earnings Interpretation）
            </CardTitle>
            <span className="text-xs font-mono text-purple-300 bg-purple-950/60 px-2 py-0.5 rounded border border-purple-500/30">
              {earningsPayload.quarter || 'FY2026 Q3'}
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {/* EPS */}
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
              <div className="text-[11px] text-slate-400">EPS 每股收益</div>
              <div className="text-lg font-bold font-mono text-white mt-1">
                ${earningsPayload.eps?.actual ?? 0.81}
              </div>
              <div className="text-[11px] text-emerald-400 mt-1 flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" />
                超预期 +{earningsPayload.eps?.surprise_percent ?? 8.0}%
              </div>
            </div>

            {/* Revenue */}
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
              <div className="text-[11px] text-slate-400">单季营收 Revenue</div>
              <div className="text-lg font-bold font-mono text-white mt-1">
                ${earningsPayload.revenue?.actual ?? 35.08}B
              </div>
              <div className="text-[11px] text-emerald-400 mt-1 flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" />
                超预期 +{earningsPayload.revenue?.surprise_percent ?? 5.8}%
              </div>
            </div>

            {/* Guidance */}
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
              <div className="text-[11px] text-slate-400">下季指引 Guidance</div>
              <div className="text-base font-semibold text-emerald-300 mt-1">上调 (Raised)</div>
              <div className="text-[11px] text-slate-400 mt-1 truncate">
                {earningsPayload.guidance?.details || '营收指引超市场一致预期'}
              </div>
            </div>
          </div>

          {/* Key Takeaways */}
          {earningsPayload.key_takeaways && (
            <div className="space-y-1 pt-2 border-t border-slate-800/80">
              <div className="text-xs font-semibold text-slate-300">电话会核心要点:</div>
              <ul className="space-y-1 text-xs text-slate-400">
                {earningsPayload.key_takeaways.map((point: string, idx: number) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-purple-400">✔</span>
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 合规免责声明 */}
      <ComplianceDisclaimer variant="card" />
    </div>
  );
};

export default StockDeepDiveView;
