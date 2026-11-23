import { renderToString } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../../../contexts/AuthContext';
import { WatchlistsView } from '../WatchlistsView';
import { ThemesView } from '../ThemesView';
import { ScreenerConsoleView } from '../ScreenerConsoleView';
import { ScreenerPage } from '../ScreenerPage';
import { MANDATORY_LEGAL_DISCLAIMER } from '../../../components/compliance/ComplianceDisclaimer';

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

describe('Screener, Themes & Watchlists Views', () => {
  describe('WatchlistsView', () => {
    it('renders watchlist tabs, item lists, target prices, and quick add form', () => {
      const html = renderWithProviders(<WatchlistsView />);

      expect(html).toContain('核心底仓与长期增长');
      expect(html).toContain('突破形态观察池');
      expect(html).toContain('NVDA');
      expect(html).toContain('MSFT');
      expect(html).toContain('LLY');
      expect(html).toContain('AAPL');
      expect(html).toContain('快捷加入');
      expect(html).toContain('新建清单');
      expect(html).toContain('一键多股横向对比');
      expect(html).toContain('组合优化分析');
      expect(html).toContain('目标监控价');
      expect(html).toContain('AI 芯片');
    });
  });

  describe('ThemesView', () => {
    it('renders 6 preset themes, category filters, component stocks, and AI research cards', () => {
      const html = renderWithProviders(<ThemesView />);

      // Preset theme cards
      expect(html).toContain('AI 算力与半导体芯片');
      expect(html).toContain('GLP-1 重磅减肥药与慢病管理');
      expect(html).toContain('高股息红利现金牛');
      expect(html).toContain('云安全与零信任防御');
      expect(html).toContain('云原生企业级 SaaS 与 AI Copilot');
      expect(html).toContain('全球清洁能源与电网变革');

      // Category filters
      expect(html).toContain('全部主题');
      expect(html).toContain('硬核科技');
      expect(html).toContain('医疗健康');
      expect(html).toContain('高息红利');
      expect(html).toContain('清洁能源');

      // AI Cards & facts
      expect(html).toContain('AI 深度单股投研卡片');
      expect(html).toContain('核心看点与关注理由');
      expect(html).toContain('财务亮点（代码级 Facts 真实溯源）');
      expect(html).toContain('主要潜在风险要素');
      expect(html).toContain('适合投资者画像');
      expect(html).toContain('一键全量导入自选');
      expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
    });
  });

  describe('ScreenerConsoleView', () => {
    it('renders universe options, strategy models, parameter tuning, and ranked results', () => {
      const html = renderWithProviders(<ScreenerConsoleView />);

      // Universes
      expect(html).toContain('标普 500 (S&amp;P 500)');
      expect(html).toContain('纳斯达克 100 (Nasdaq 100)');
      expect(html).toContain('道琼斯工业指数 30 (Dow 30)');

      // Strategies
      expect(html).toContain('道氏趋势突破策略');
      expect(html).toContain('多头 RSI 回调企稳策略');
      expect(html).toContain('123 法则反转突破策略');
      expect(html).toContain('海龟 20/55 日突破策略');

      // Controls & Actions
      expect(html).toContain('策略筛选控制台');
      expect(html).toContain('开始全池策略筛选');
      expect(html).toContain('筛选结果排名榜单');
      expect(html).toContain('量化综合得分');
      expect(html).toContain('BUY');
      expect(html).toContain('横向对比');
      expect(html).toContain('组合配置');
      expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
    });
  });

  describe('ScreenerPage', () => {
    it('renders top navigation tabs and mounts appropriate view according to initialTab', () => {
      const htmlScreener = renderWithProviders(<ScreenerPage initialTab="screener" />, '/screener');
      expect(htmlScreener).toContain('策略筛选与主题自选工作台');
      expect(htmlScreener).toContain('策略筛选控制台');

      const htmlThemes = renderWithProviders(<ScreenerPage initialTab="themes" />, '/themes');
      expect(htmlThemes).toContain('热门宏观投资主题库');

      const htmlWatchlists = renderWithProviders(<ScreenerPage initialTab="watchlists" />, '/watchlists');
      expect(htmlWatchlists).toContain('自选清单');
      expect(htmlWatchlists).toContain('核心底仓与长期增长');
    });
  });
});
