import { renderToString } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../../../contexts/AuthContext';
import { AccountOverviewView } from '../AccountOverviewView';
import { OrderTradePanelView } from '../OrderTradePanelView';
import { PositionsAndOrdersView } from '../PositionsAndOrdersView';
import { TradingJournalView } from '../TradingJournalView';
import { SimBrokerPage } from '../SimBrokerPage';
import {
  mockAccountOverview,
  mockAccounts,
  mockOrders,
  mockPerformance,
  mockPositions,
  mockRisk,
  mockTradeJournals,
  mockTrades,
} from '../mockData';
import { MANDATORY_LEGAL_DISCLAIMER } from '../../../components/compliance/ComplianceDisclaimer';

function renderWithProviders(ui: React.ReactElement, initialRoute = '/simbroker'): string {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return renderToString(
    <MemoryRouter initialEntries={[initialRoute]}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{ui}</AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('SimBroker Console & Trading Journal Views', () => {
  describe('AccountOverviewView', () => {
    it('renders account balance KPI cards, benchmark comparison, PDT rules and risk metrics', () => {
      const html = renderWithProviders(
        <AccountOverviewView
          overview={mockAccountOverview}
          accounts={mockAccounts}
          activeAccountId={mockAccountOverview.id}
          onSelectAccount={vi.fn()}
          performance={mockPerformance}
          risk={mockRisk}
          onOpenDeposit={vi.fn()}
          onOpenCreateAccount={vi.fn()}
        />,
      );

      // KPIs
      expect(html).toContain('总资产净值 (Equity)');
      expect(html).toContain('可用现金 (Cash)');
      expect(html).toContain('持仓总市值 (Market Value)');
      expect(html).toContain('当日浮动盈亏 (Daily PnL)');
      expect(html).toContain('累计总收益回报 (Total Return)');

      // PDT Banner & Rule
      expect(html).toContain('美股 FINRA PDT (典型日内交易者) 规则监控');
      expect(html).toContain('近 5 个交易日内完成');
      expect(html).toContain('25,000');

      // Alpha & Benchmark Performance
      expect(html).toContain('全周期资产净值走势与标普 500 基准走势对比');
      expect(html).toContain('超额 Alpha (年化)');
      expect(html).toContain('市场敏感度 Beta');
      expect(html).toContain('交易胜率 (Win Rate)');
      expect(html).toContain('历史最大回撤 (Max Drawdown)');

      // Risk Diagnostics
      expect(html).toContain('多因子业绩分析与体检指标');
      expect(html).toContain('前四大重仓标的集中度');
    });
  });

  describe('OrderTradePanelView', () => {
    it('renders trade order form, order types, buying power warnings and quick quote cards', () => {
      const html = renderWithProviders(
        <OrderTradePanelView
          overview={mockAccountOverview}
          positions={mockPositions}
          onOrderSubmitted={vi.fn()}
        />,
      );

      // Direction & Types
      expect(html).toContain('买入 (BUY)');
      expect(html).toContain('卖出 (SELL)');
      expect(html).toContain('市价单');
      expect(html).toContain('限价单');
      expect(html).toContain('止损单');
      expect(html).toContain('当日有效 (DAY)');
      expect(html).toContain('长期有效 (GTC)');

      // Inputs & Estimates
      expect(html).toContain('选择交易标的');
      expect(html).toContain('委托数量 (股)');
      expect(html).toContain('预估成交总金额');
      expect(html).toContain('预估佣金与规费');

      // Quick quotes
      expect(html).toContain('NVDA');
      expect(html).toContain('MSFT');
      expect(html).toContain('AAPL');

      // Submit Button
      expect(html).toContain('确认买入 NVDA');
    });
  });

  describe('PositionsAndOrdersView', () => {
    it('renders positions table, unrealized PnL, order book and quick trade buttons', () => {
      const html = renderWithProviders(
        <PositionsAndOrdersView
          accountId={mockAccountOverview.id}
          positions={mockPositions}
          orders={mockOrders}
          onRefresh={vi.fn()}
        />,
      );

      // Tabs
      expect(html).toContain('持仓明细 (');
      expect(html).toContain('委托订单管理 (');

      // Positions Table Headers & Contents
      expect(html).toContain('标的代码');
      expect(html).toContain('持仓数量');
      expect(html).toContain('持仓均价');
      expect(html).toContain('最新市价');
      expect(html).toContain('持仓总市值');
      expect(html).toContain('浮动盈亏');
      expect(html).toContain('仓位占比');
      expect(html).toContain('NVDA');
      expect(html).toContain('MSFT');
    });
  });

  describe('TradingJournalView', () => {
    it('renders trade journal feed, review tags, emotional analysis, and summary metrics', () => {
      const html = renderWithProviders(
        <TradingJournalView
          trades={mockTrades}
          journals={mockTradeJournals}
          onJournalUpdated={vi.fn()}
        />,
      );

      // Summary Header
      expect(html).toContain('历史已平仓实现盈亏');
      expect(html).toContain('复盘日志覆盖率');
      expect(html).toContain('AI 交易复盘审计');
      expect(html).toContain('成交记录与结构化复盘日志卡片');

      // Trade Items & Journal Content
      expect(html).toContain('情绪:');
      expect(html).toContain('理性坚定');
      expect(html).toContain('趋势突破');
      expect(html).toContain('编辑复盘');
    });
  });

  describe('SimBrokerPage', () => {
    it('renders top tabs, switches subviews and contains mandatory compliance disclaimer', () => {
      // Overview
      const htmlOverview = renderWithProviders(<SimBrokerPage initialTab="overview" />, '/simbroker');
      expect(htmlOverview).toContain('SimBroker 模拟盘控制台');
      expect(htmlOverview).toContain('总资产净值 (Equity)');
      expect(htmlOverview).toContain(MANDATORY_LEGAL_DISCLAIMER);

      // Trade
      const htmlTrade = renderWithProviders(<SimBrokerPage initialTab="trade" />, '/simbroker?tab=trade');
      expect(htmlTrade).toContain('买入 (BUY)');
      expect(htmlTrade).toContain('委托数量 (股)');

      // Positions & Orders
      const htmlOrders = renderWithProviders(<SimBrokerPage initialTab="positions-orders" />, '/simbroker/orders');
      expect(htmlOrders).toContain('持仓明细');

      // Journal
      const htmlJournal = renderWithProviders(<SimBrokerPage initialTab="journal" />, '/simbroker/journal');
      expect(htmlJournal).toContain('历史已平仓实现盈亏');
    });
  });
});
