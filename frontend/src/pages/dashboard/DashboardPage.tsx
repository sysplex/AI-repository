import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, BarChart3, Brain, Compass, LineChart, Sparkles, TrendingUp } from 'lucide-react';
import { MetricCard } from '../../components/financial/MetricCard';
import { FinancialTable, Column } from '../../components/financial/FinancialTable';
import { PriceDisplay } from '../../components/financial/PriceDisplay';
import { ChangePercent } from '../../components/financial/ChangePercent';
import { DataFreshnessTag } from '../../components/compliance/DataFreshnessTag';
import { AIPromptVersionBadge } from '../../components/compliance/AIPromptVersionBadge';
import { ComplianceDisclaimer } from '../../components/compliance/ComplianceDisclaimer';
import { Button } from '../../components/common/Button';
import { StockDetailModal } from '../../components/chart/StockDetailModal';
import { formatLargeNumber } from '../../utils/format';
import { marketApi } from '../../api/market';
import { api } from '../../api/client';
import type { Quote, Signal } from '../../api/types';

interface MarketIndexItem {
  name: string;
  symbol: string;
  value: string;
  change: number;
  changeAmount: number;
  subtext: string;
}

interface StockOverviewItem {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  changeAmount: number;
  volume: number;
  marketCap?: number | null;
  aiSignal?: 'BULLISH' | 'NEUTRAL' | 'BEARISH' | null;
  aiScore?: number | null;
}

const INDEX_CONFIG = [
  { symbol: 'SPY', name: '标普 500 ETF (SPY)', subtext: '大盘宏观基准权重' },
  { symbol: 'QQQ', name: '纳指 100 ETF (QQQ)', subtext: '科技与创新成长龙头' },
  { symbol: 'DIA', name: '道琼斯 ETF (DIA)', subtext: '传统工业蓝筹支柱' },
  { symbol: 'IWM', name: '罗素 2000 ETF (IWM)', subtext: '美股中小盘成长代表' },
];

const HOT_STOCKS_CONFIG = [
  { symbol: 'NVDA', name: 'NVIDIA Corp' },
  { symbol: 'AAPL', name: 'Apple Inc' },
  { symbol: 'MSFT', name: 'Microsoft Corp' },
  { symbol: 'TSLA', name: 'Tesla Inc' },
  { symbol: 'AMZN', name: 'Amazon.com Inc' },
  { symbol: 'PLTR', name: 'Palantir Technologies' },
];

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [selectedStock, setSelectedStock] = useState<StockOverviewItem | null>(null);

  const [marketIndices, setMarketIndices] = useState<MarketIndexItem[]>([]);
  const [hotStocks, setHotStocks] = useState<StockOverviewItem[]>([]);
  const [modalSignals, setModalSignals] = useState<Signal[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [asOf, setAsOf] = useState<string>(new Date().toISOString());

  const fetchDashboardData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const allSymbols = [...INDEX_CONFIG.map((i) => i.symbol), ...HOT_STOCKS_CONFIG.map((s) => s.symbol)];
      const quotesList = await marketApi.getQuotes(allSymbols);
      const quotesMap: Record<string, Quote> = {};
      quotesList.forEach((q) => {
        quotesMap[q.symbol.toUpperCase()] = q;
      });

      // 并发拉取热门标的基本面以获取真实市值（若未连接或异常则为 null，严禁硬编码虚假数据）
      const fundamentalsResults = await Promise.allSettled(
        HOT_STOCKS_CONFIG.map((cfg) => marketApi.getFundamentals(cfg.symbol))
      );
      const fundMap: Record<string, number | null> = {};
      fundamentalsResults.forEach((res, idx) => {
        const sym = HOT_STOCKS_CONFIG[idx].symbol;
        if (res.status === 'fulfilled' && res.value && res.value.market_cap) {
          const parsed = parseFloat(res.value.market_cap);
          fundMap[sym] = isNaN(parsed) ? null : parsed;
        } else {
          fundMap[sym] = null;
        }
      });

      // 尝试扫描道氏趋势策略以获取真实技术量化信号
      const today = new Date().toISOString().split('T')[0];
      const scanMap: Record<string, Signal> = {};
      try {
        const scanned = await api.post<Signal[]>('/strategy/scan', {
          strategy_id: 'dow_trend',
          symbols: HOT_STOCKS_CONFIG.map((s) => s.symbol),
          as_of: today,
          params: {},
        });
        if (Array.isArray(scanned)) {
          scanned.forEach((sig) => {
            if (sig && sig.symbol) scanMap[sig.symbol.toUpperCase()] = sig;
          });
        }
      } catch {
        // 策略扫描未就绪或行情不足时不伪造假信号
      }

      const indices: MarketIndexItem[] = INDEX_CONFIG.map((cfg) => {
        const q = quotesMap[cfg.symbol];
        const priceNum = q ? parseFloat(q.price) : 0;
        const changeNum = q ? parseFloat(q.change_pct) : 0;
        const changeAmt = q ? parseFloat(q.change) : 0;
        return {
          name: cfg.name,
          symbol: cfg.symbol,
          value: priceNum ? priceNum.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--',
          change: changeNum,
          changeAmount: changeAmt,
          subtext: cfg.subtext,
        };
      });
      setMarketIndices(indices);

      const stocks: StockOverviewItem[] = HOT_STOCKS_CONFIG.map((cfg) => {
        const q = quotesMap[cfg.symbol];
        const priceNum = q ? parseFloat(q.price) : 0;
        const changeNum = q ? parseFloat(q.change_pct) : 0;
        const changeAmt = q ? parseFloat(q.change) : 0;
        const sig = scanMap[cfg.symbol];

        let aiSignal: 'BULLISH' | 'NEUTRAL' | 'BEARISH' | null = null;
        let aiScore: number | null = null;
        if (sig) {
          if (sig.direction === 'long') {
            aiSignal = 'BULLISH';
          } else if (sig.direction === 'short') {
            aiSignal = 'BEARISH';
          } else {
            aiSignal = 'NEUTRAL';
          }
          aiScore = sig.strength;
        }

        return {
          symbol: cfg.symbol,
          name: cfg.name,
          price: priceNum,
          changePercent: changeNum,
          changeAmount: changeAmt,
          volume: q?.volume || 0,
          marketCap: fundMap[cfg.symbol] ?? null,
          aiSignal,
          aiScore,
        };
      });
      setHotStocks(stocks);

      const latestAsOf = quotesList.find((q) => q.as_of)?.as_of;
      if (latestAsOf) {
        setAsOf(latestAsOf);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '获取市场行情失败';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  // 选中标的时，真实调用后端策略信号接口计算信号，绝不伪造硬编码假信号
  useEffect(() => {
    if (!selectedStock) {
      setModalSignals([]);
      return;
    }
    let cancelled = false;
    const fetchSignals = async () => {
      try {
        const today = new Date().toISOString().split('T')[0];
        const res = await api.post<Signal>('/strategy/evaluate', {
          strategy_id: 'dow_trend',
          symbol: selectedStock.symbol,
          as_of: today,
          params: {},
        });
        if (!cancelled && res && res.strategy_id) {
          setModalSignals([res]);
        }
      } catch {
        if (!cancelled) {
          setModalSignals([]);
        }
      }
    };
    fetchSignals();
    return () => {
      cancelled = true;
    };
  }, [selectedStock]);

  const columns: Column<StockOverviewItem>[] = [
    {
      key: 'symbol',
      title: '标的代码',
      dataIndex: 'symbol',
      sortable: true,
      render: (_, record) => (
        <div className="flex flex-col">
          <span className="font-bold text-white font-mono hover:text-blue-400 transition-colors">
            {record.symbol}
          </span>
          <span className="text-[11px] text-slate-400 truncate max-w-[140px]">{record.name}</span>
        </div>
      ),
    },
    {
      key: 'price',
      title: '现价 (USD)',
      dataIndex: 'price',
      sortable: true,
      align: 'right',
      render: (val, record) => (
        <PriceDisplay value={val} colored changeValue={record.changePercent} />
      ),
    },
    {
      key: 'changePercent',
      title: '24h 涨跌幅',
      dataIndex: 'changePercent',
      sortable: true,
      align: 'right',
      render: (val, record) => (
        <ChangePercent value={val} changeAmount={record.changeAmount} mode="badge" />
      ),
    },
    {
      key: 'volume',
      title: '成交量',
      dataIndex: 'volume',
      sortable: true,
      align: 'right',
      render: (val) => <span className="font-mono text-slate-300">{formatLargeNumber(val)}</span>,
    },
    {
      key: 'marketCap',
      title: '总市值',
      dataIndex: 'marketCap',
      sortable: true,
      align: 'right',
      render: (val) => (
        <span className="font-mono text-slate-300">
          {val ? `$${formatLargeNumber(val)}` : '--'}
        </span>
      ),
    },
    {
      key: 'aiSignal',
      title: 'AI 研判倾向',
      dataIndex: 'aiScore',
      sortable: true,
      align: 'center',
      render: (_, record) => {
        if (!record.aiSignal || record.aiScore === undefined || record.aiScore === null) {
          return (
            <span className="text-[11px] text-slate-500 font-mono">
              待触发研判
            </span>
          );
        }
        const signalStyles = {
          BULLISH: 'bg-emerald-950/60 text-emerald-300 border-emerald-500/30',
          NEUTRAL: 'bg-slate-800 text-slate-300 border-slate-700',
          BEARISH: 'bg-rose-950/60 text-rose-300 border-rose-500/30',
        };
        const signalText = {
          BULLISH: '偏多',
          NEUTRAL: '中性',
          BEARISH: '偏空',
        };

        return (
          <div className="inline-flex items-center gap-1.5">
            <span
              className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${signalStyles[record.aiSignal]}`}
            >
              {signalText[record.aiSignal]} ({record.aiScore})
            </span>
          </div>
        );
      },
    },
    {
      key: 'actions',
      title: '快捷操作',
      align: 'right',
      render: (_, record) => (
        <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
          <Button
            variant="outline"
            size="xs"
            onClick={() => setSelectedStock(record)}
            leftIcon={<LineChart className="h-3 w-3 text-sky-400" />}
          >
            K线
          </Button>
          <Button
            variant="ghost"
            size="xs"
            onClick={() => navigate(`/research?symbol=${record.symbol}`)}
            leftIcon={<Sparkles className="h-3 w-3 text-purple-400" />}
          >
            研报
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <Compass className="h-6 w-6 text-blue-500" />
              美股市场全景总览
            </h1>
            <AIPromptVersionBadge model="deepseek-chat" promptVersion="v1.2.0" />
          </div>
          <p className="text-xs text-slate-400 mt-1">
            实时汇聚大盘宏观指数、板块轮动状态与核心标的 AI 多因子量化信号。
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <DataFreshnessTag asOf={asOf} />
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/50 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-rose-200">
          <div>
            <div className="font-semibold text-rose-400">行情数据加载异常</div>
            <div className="text-xs text-rose-300 mt-1">{error}</div>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="border-rose-500/50 text-rose-300 hover:bg-rose-900/40"
            onClick={fetchDashboardData}
          >
            重试
          </Button>
        </div>
      )}

      {/* Market Indices Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 animate-pulse">
          <div className="h-28 bg-slate-800/40 rounded-xl" />
          <div className="h-28 bg-slate-800/40 rounded-xl" />
          <div className="h-28 bg-slate-800/40 rounded-xl" />
          <div className="h-28 bg-slate-800/40 rounded-xl" />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {marketIndices.map((idx) => (
            <MetricCard
              key={idx.symbol}
              title={idx.name}
              value={idx.value}
              change={idx.change}
              changeAmount={idx.changeAmount}
              subtext={idx.subtext}
              icon={<TrendingUp className="h-4 w-4" />}
            />
          ))}
        </div>
      )}

      {/* Main Content Area: Hot Watchlist Table */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-blue-400" />
            <h2 className="text-base font-semibold text-white">热门标的动态与 AI 决策评分</h2>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="xs"
              onClick={() => navigate('/screener')}
              leftIcon={<BarChart3 className="h-3.5 w-3.5" />}
            >
              高级策略筛选
            </Button>
            <Button
              variant="primary"
              size="xs"
              onClick={() => navigate('/research')}
              leftIcon={<Brain className="h-3.5 w-3.5" />}
            >
              启动 AI 深度投研
            </Button>
          </div>
        </div>

        {isLoading ? (
          <div className="h-64 bg-slate-800/30 rounded-xl animate-pulse" />
        ) : (
          <FinancialTable
            columns={columns}
            data={hotStocks}
            rowKey={(r) => r.symbol}
            onRowClick={(r) => setSelectedStock(r)}
          />
        )}
      </div>

      {/* Compliance Disclaimer */}
      <ComplianceDisclaimer variant="card" />

      {/* Stock Candlestick Chart & Signal Modal */}
      <StockDetailModal
        isOpen={!!selectedStock}
        onClose={() => setSelectedStock(null)}
        symbol={selectedStock?.symbol || ''}
        name={selectedStock?.name}
        signals={modalSignals}
        onOpenResearch={(sym) => navigate(`/research?symbol=${sym}`)}
      />
    </div>
  );
};

export default DashboardPage;
