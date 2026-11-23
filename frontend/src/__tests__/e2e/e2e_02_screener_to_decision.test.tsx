import { renderToString } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../../contexts/AuthContext';
import { ScreenerConsoleView } from '../../pages/screener/ScreenerConsoleView';
import { StockCompareView } from '../../pages/research/StockCompareView';
import { LongTermView } from '../../pages/research/LongTermView';
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

describe('E2E-02: Screener to Decision Pipeline (筛选到决策全流程)', () => {
  it('Step 1: Quant Screener model selection and candidate ranking', () => {
    const htmlScreener = renderWithProviders(<ScreenerConsoleView />, '/screener');

    // Universe selection
    expect(htmlScreener).toContain('标普 500 (S&amp;P 500)');
    expect(htmlScreener).toContain('纳斯达克 100 (Nasdaq 100)');
    expect(htmlScreener).toContain('道琼斯工业指数 30 (Dow 30)');

    // Model selection
    expect(htmlScreener).toContain('道氏趋势突破策略');
    expect(htmlScreener).toContain('多头 RSI 回调企稳策略');
    expect(htmlScreener).toContain('123 法则反转突破策略');

    // Controls and ranking results
    expect(htmlScreener).toContain('策略筛选控制台');
    expect(htmlScreener).toContain('开始全池策略筛选');
    expect(htmlScreener).toContain('筛选结果排名榜单');
    expect(htmlScreener).toContain('量化综合得分');
    expect(htmlScreener).toContain('BUY');
    expect(htmlScreener).toContain('横向对比');
    expect(htmlScreener).toContain('组合配置');
    expect(htmlScreener).toContain(MANDATORY_LEGAL_DISCLAIMER);
  });

  it('Step 2: Cross-stock multi-dimension comparison for selected candidates', () => {
    const htmlCompare = renderWithProviders(
      <StockCompareView />,
      '/research?tab=compare&symbols=NVDA,MSFT,AAPL',
    );

    // Header & metadata
    expect(htmlCompare).toContain('多标的横向对比矩阵 (Stock Compare)');
    expect(htmlCompare).toContain('对比标的池 (最多8只):');
    expect(htmlCompare).toContain('AI 引擎:');
    expect(htmlCompare).toContain('模板:');
    expect(htmlCompare).toContain('数据截至:');

    // Comparison ranking & Winner
    expect(htmlCompare).toContain('AI 对比综合结论');
    expect(htmlCompare).toContain('维度最佳标的:');
    expect(htmlCompare).toContain('综合最佳:');
    expect(htmlCompare).toContain('NVDA');
    expect(htmlCompare).toContain('MSFT');
    expect(htmlCompare).toContain('AAPL');
    expect(htmlCompare).toContain(MANDATORY_LEGAL_DISCLAIMER);
  });

  it('Step 3: Long-term hold durability evaluation and thesis-breakers monitoring for #1 winner', () => {
    const htmlLongTerm = renderWithProviders(
      <LongTermView initialSymbol="NVDA" />,
      '/research?tab=long-term&symbol=NVDA',
    );

    // Header & pillars
    expect(htmlLongTerm).toContain('长期持有价值与论文破裂监控');
    expect(htmlLongTerm).toContain('评估 5–15 年跨周期的 7 大价值支柱');
    expect(htmlLongTerm).toContain('分析评级');
    expect(htmlLongTerm).toContain('持有时间跨度:');

    // Thesis breakers & Disclaimers
    expect(htmlLongTerm).toContain('不可妥协的「投资逻辑破裂退出条件」');
    expect(htmlLongTerm).toContain('AI 引擎:');
    expect(htmlLongTerm).toContain(MANDATORY_LEGAL_DISCLAIMER);
  });
});
