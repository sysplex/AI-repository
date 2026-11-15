import React, { useState } from 'react';
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
import type { Signal } from '../../api/types';

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
  marketCap: number;
  aiSignal: 'BULLISH' | 'NEUTRAL' | 'BEARISH';
  aiScore: number;
}

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [selectedStock, setSelectedStock] = useState<StockOverviewItem | null>(null);

  const sampleSignals: Record<string, Signal[]> = {
    NVDA: [
      {
        strategy_id: 'trend_momentum',
        symbol: 'NVDA',
        as_of: '2026-11-14',
        direction: 'long',
        strength: 88,
        reasons: ['突破50日均线', 'AI算力主题资金持续流入', '多头排列形态成立'],
        levels: {
          entry: '143.50',
          stop_loss: '138.20',
          target: '158.00',
        },
      },
    ],
    PLTR: [
      {
        strategy_id: 'breakout_growth',
        symbol: 'PLTR',
        as_of: '2026-11-13',
        direction: 'long',
        strength: 91,
        reasons: ['商业版AIP签约量放量', '创历史新高突破放量'],
        levels: {
          entry: '58.50',
          stop_loss: '54.00',
          target: '68.00',
        },
      },
    ],
  };

  const marketIndices: MarketIndexItem[] = [
    {
      name: '标普 500 (S&P 500)',
      symbol: '^GSPC',
      value: '5,864.67',
      change: 0.75,
      changeAmount: 43.68,
      subtext: '大盘权重企稳，科技板块领涨',
    },
    {
      name: '纳斯达克 100 (NDX)',
      symbol: '^NDX',
      value: '20,388.40',
      change: 1.12,
      changeAmount: 225.80,
      subtext: '半导体与 AI 算力龙头放量走强',
    },
    {
      name: '道琼斯工业 (DJI)',
      symbol: '^DJI',
      value: '43,444.99',
      change: -0.28,
      changeAmount: -122.15,
      subtext: '周期股微调，医疗与金融震荡',
    },
    {
      name: '恐慌指数 (VIX)',
      symbol: '^VIX',
      value: '14.85',
      change: -5.23,
      changeAmount: -0.82,
      subtext: '波动率回归低位，风险偏好回暖',
    },
  ];

  const hotStocks: StockOverviewItem[] = [
    {
      symbol: 'NVDA',
      name: 'NVIDIA Corp',
      price: 145.89,
      changePercent: 3.42,
      changeAmount: 4.82,
      volume: 48920000,
      marketCap: 3580000000000,
      aiSignal: 'BULLISH',
      aiScore: 88,
    },
    {
      symbol: 'AAPL',
      name: 'Apple Inc',
      price: 228.25,
      changePercent: 0.85,
      changeAmount: 1.92,
      volume: 32100000,
      marketCap: 3450000000000,
      aiSignal: 'NEUTRAL',
      aiScore: 65,
    },
    {
      symbol: 'MSFT',
      name: 'Microsoft Corp',
      price: 422.50,
      changePercent: 1.15,
      changeAmount: 4.80,
      volume: 21500000,
      marketCap: 3140000000000,
      aiSignal: 'BULLISH',
      aiScore: 82,
    },
    {
      symbol: 'TSLA',
      name: 'Tesla Inc',
      price: 338.74,
      changePercent: -2.18,
      changeAmount: -7.56,
      volume: 58900000,
      marketCap: 1080000000000,
      aiSignal: 'NEUTRAL',
      aiScore: 54,
    },
    {
      symbol: 'AMZN',
      name: 'Amazon.com Inc',
      price: 208.18,
      changePercent: 1.64,
      changeAmount: 3.36,
      volume: 26800000,
      marketCap: 2160000000000,
      aiSignal: 'BULLISH',
      aiScore: 79,
    },
    {
      symbol: 'PLTR',
      name: 'Palantir Technologies',
      price: 61.25,
      changePercent: 4.88,
      changeAmount: 2.85,
      volume: 64200000,
      marketCap: 138000000000,
      aiSignal: 'BULLISH',
      aiScore: 91,
    },
  ];

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
      render: (val) => <span className="font-mono text-slate-300">${formatLargeNumber(val)}</span>,
    },
    {
      key: 'aiSignal',
      title: 'AI 研判倾向',
      dataIndex: 'aiScore',
      sortable: true,
      align: 'center',
      render: (_, record) => {
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
          <DataFreshnessTag asOf={new Date().toISOString()} />
        </div>
      </div>

      {/* Market Indices Grid */}
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

        <FinancialTable
          columns={columns}
          data={hotStocks}
          rowKey={(r) => r.symbol}
          onRowClick={(r) => setSelectedStock(r)}
        />
      </div>

      {/* Compliance Disclaimer */}
      <ComplianceDisclaimer variant="card" />

      {/* Stock Candlestick Chart & Signal Modal */}
      <StockDetailModal
        isOpen={!!selectedStock}
        onClose={() => setSelectedStock(null)}
        symbol={selectedStock?.symbol || ''}
        name={selectedStock?.name}
        signals={selectedStock ? sampleSignals[selectedStock.symbol] || [] : []}
        onOpenResearch={(sym) => navigate(`/research?symbol=${sym}`)}
      />
    </div>
  );
};

export default DashboardPage;
