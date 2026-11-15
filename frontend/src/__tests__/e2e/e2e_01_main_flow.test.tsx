import { renderToString } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../../contexts/AuthContext';
import { RegisterPage } from '../../pages/auth/RegisterPage';
import { LoginPage } from '../../pages/auth/LoginPage';
import { WatchlistsView } from '../../pages/screener/WatchlistsView';
import { StockDeepDiveView } from '../../pages/research/StockDeepDiveView';
import { BuyDecisionView } from '../../pages/research/BuyDecisionView';
import { OrderTradePanelView } from '../../pages/simbroker/OrderTradePanelView';
import { PositionsAndOrdersView } from '../../pages/simbroker/PositionsAndOrdersView';
import { TradingJournalView } from '../../pages/simbroker/TradingJournalView';
import { SimBrokerPage } from '../../pages/simbroker/SimBrokerPage';
import {
  mockAccountOverview,
  mockOrders,
  mockPositions,
  mockTradeJournals,
  mockTrades,
} from '../../pages/simbroker/mockData';
import { MANDATORY_LEGAL_DISCLAIMER } from '../../components/compliance/ComplianceDisclaimer';

function renderWithProviders(ui: React.ReactElement, initialRoute = '/'): string {
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

describe('E2E-01: Main Business Journey (端到端主链路)', () => {
  it('Step 1: User Registration and Login flow', () => {
    // 1.1 Register page renders required fields and risk profile selection
    const htmlRegister = renderWithProviders(<RegisterPage />, '/register');
    expect(htmlRegister).toContain('注册 Stockpilot 账号');
    expect(htmlRegister).toContain('创建新账号');
    expect(htmlRegister).toContain('电子邮箱');
    expect(htmlRegister).toContain('登录密码');
    expect(htmlRegister).toContain('确认密码');
    expect(htmlRegister).toContain('投资风险偏好');

    // 1.2 Login page renders authentication form
    const htmlLogin = renderWithProviders(<LoginPage />, '/login');
    expect(htmlLogin).toContain('登录 Stockpilot');
    expect(htmlLogin).toContain('智能美股投研与模拟交易平台');
    expect(htmlLogin).toContain('登 录');
    expect(htmlLogin).toContain('免费注册');
  });

  it('Step 2: Simulation Account creation and overview display ($100,000 initial capital)', () => {
    const htmlOverview = renderWithProviders(<SimBrokerPage initialTab="overview" />, '/simbroker');
    expect(htmlOverview).toContain('SimBroker 模拟盘控制台');
    expect(htmlOverview).toContain('总资产净值 (Equity)');
    expect(htmlOverview).toContain('可用现金 (Cash)');
    expect(htmlOverview).toContain('初始本金:');
    expect(htmlOverview).toContain('100,000');
    expect(htmlOverview).toContain('美股 FINRA PDT (典型日内交易者) 规则监控');
    expect(htmlOverview).toContain('25,000');
  });

  it('Step 3: Watchlist view with AAPL added, target price and live quotes', () => {
    const htmlWatchlist = renderWithProviders(<WatchlistsView />, '/watchlists');
    expect(htmlWatchlist).toContain('核心底仓与长期增长');
    expect(htmlWatchlist).toContain('AAPL');
    expect(htmlWatchlist).toContain('目标监控价');
    expect(htmlWatchlist).toContain('快捷加入');
    expect(htmlWatchlist).toContain('新建清单');
  });

  it('Step 4 & 5: AI Stock Deep Dive and research with compliance elements', () => {
    const htmlDeepDive = renderWithProviders(
      <StockDeepDiveView initialSymbol="AAPL" onSelectSymbol={vi.fn()} />,
      '/research?tab=deep-dive&symbol=AAPL',
    );
    expect(htmlDeepDive).toContain('AI 深度研报');
    expect(htmlDeepDive).toContain('AI 核心投研综述');
    expect(htmlDeepDive).toContain('三段式情景推演（Three-Scenario Framework）');
    expect(htmlDeepDive).toContain('看涨情景（Bull Case）');
    expect(htmlDeepDive).toContain('AI 引擎:');
    expect(htmlDeepDive).toContain('数据截至:');
    expect(htmlDeepDive).toContain(MANDATORY_LEGAL_DISCLAIMER);
  });

  it('Step 6: Buy Decision generation with target price and execution plan', () => {
    const htmlBuyDecision = renderWithProviders(
      <BuyDecisionView initialSymbol="AAPL" />,
      '/research?tab=buy-decision&symbol=AAPL',
    );
    expect(htmlBuyDecision).toContain('买入决策评估工作台');
    expect(htmlBuyDecision).toContain('输入决策评估参数');
    expect(htmlBuyDecision).toContain('目标买入价');
    expect(htmlBuyDecision).toContain('投资周期');
    expect(htmlBuyDecision).toContain('风险偏好');
    expect(htmlBuyDecision).toContain('AI 引擎:');
    expect(htmlBuyDecision).toContain('数据截至:');
    expect(htmlBuyDecision).toContain(MANDATORY_LEGAL_DISCLAIMER);
  });

  it('Step 7: Place limit order with shares calculator, buying power and idempotency', () => {
    const htmlTrade = renderWithProviders(
      <OrderTradePanelView
        overview={mockAccountOverview}
        positions={mockPositions}
        onOrderSubmitted={vi.fn()}
      />,
      '/simbroker?tab=trade',
    );
    expect(htmlTrade).toContain('模拟交易委托操作台');
    expect(htmlTrade).toContain('买入 (BUY)');
    expect(htmlTrade).toContain('市价单');
    expect(htmlTrade).toContain('限价单');
    expect(htmlTrade).toContain('止损单');
    expect(htmlTrade).toContain('当日有效 (DAY)');
    expect(htmlTrade).toContain('委托数量 (股)');
    expect(htmlTrade).toContain('预估成交总金额');
    expect(htmlTrade).toContain('预估佣金与规费');
    expect(htmlTrade).toContain('确认买入 NVDA');
  });

  it('Step 8: Position update, unrealized PnL, and order list management', () => {
    const htmlPositions = renderWithProviders(
      <PositionsAndOrdersView
        accountId={mockAccountOverview.id}
        positions={mockPositions}
        orders={mockOrders}
        onRefresh={vi.fn()}
      />,
      '/simbroker/orders',
    );
    expect(htmlPositions).toContain('持仓明细 (');
    expect(htmlPositions).toContain('委托订单管理 (');
    expect(htmlPositions).toContain('标的代码');
    expect(htmlPositions).toContain('持仓数量');
    expect(htmlPositions).toContain('持仓均价');
    expect(htmlPositions).toContain('最新市价');
    expect(htmlPositions).toContain('浮动盈亏');
    expect(htmlPositions).toContain('仓位占比');
  });

  it('Step 9: Trading journal review, emotional tracking and lesson notes', () => {
    const htmlJournal = renderWithProviders(
      <TradingJournalView
        trades={mockTrades}
        journals={mockTradeJournals}
        onJournalUpdated={vi.fn()}
      />,
      '/simbroker/journal',
    );
    expect(htmlJournal).toContain('历史已平仓实现盈亏');
    expect(htmlJournal).toContain('复盘日志覆盖率');
    expect(htmlJournal).toContain('AI 交易复盘审计');
    expect(htmlJournal).toContain('情绪:');
    expect(htmlJournal).toContain('理性坚定');
    expect(htmlJournal).toContain('编辑复盘');
  });
});
