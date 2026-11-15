import { renderToString } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../../../contexts/AuthContext';
import { StockDeepDiveView } from '../StockDeepDiveView';
import { BuyDecisionView } from '../BuyDecisionView';
import { StockCompareView } from '../StockCompareView';
import { LongTermView } from '../LongTermView';
import { PortfolioView } from '../PortfolioView';
import { MANDATORY_LEGAL_DISCLAIMER } from '../../../components/compliance/ComplianceDisclaimer';

function renderWithProviders(ui: React.ReactElement): string {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return renderToString(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{ui}</AuthProvider>
    </QueryClientProvider>,
  );
}

describe('AI Research & Decision Views', () => {
  describe('StockDeepDiveView', () => {
    it('renders stock overview, 3-scenario analysis, moat, and earnings', () => {
      const html = renderWithProviders(<StockDeepDiveView initialSymbol="NVDA" />);

      expect(html).toContain('NVDA');
      expect(html).toContain('AI 核心投研综述');
      expect(html).toContain('看涨情景（Bull Case）');
      expect(html).toContain('中性基准（Base Case）');
      expect(html).toContain('看跌情景（Bear Case）');
      expect(html).toContain('商业模式与变现逻辑');
      expect(html).toContain('经济护城河深度');
      expect(html).toContain('最新财报深度解读');
      expect(html).toContain('EPS 每股收益');
      expect(html).toContain('单季营收 Revenue');
      expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
    });
  });

  describe('BuyDecisionView', () => {
    it('renders decision parameters, verdict badge, and margin of safety', () => {
      const html = renderWithProviders(<BuyDecisionView initialSymbol="NVDA" />);

      expect(html).toContain('买入决策评估工作台');
      expect(html).toContain('拟买入目标价');
      expect(html).toContain('BUY');
      expect(html).toContain('AI 置信度评分');
      expect(html).toContain('安全边际 (Margin of Safety)');
      expect(html).toContain('建议分批入场区间');
      expect(html).toContain('建议分批操作行动方案');
      expect(html).toContain('最大潜在下行风险测算');
      expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
    });
  });

  describe('StockCompareView', () => {
    it('renders comparison tags, winners ribbon, rankings, and dimension matrix', () => {
      const html = renderWithProviders(<StockCompareView />);

      expect(html).toContain('多标的横向对比矩阵');
      expect(html).toContain('对比标的池');
      expect(html).toContain('NVDA');
      expect(html).toContain('MSFT');
      expect(html).toContain('AAPL');
      expect(html).toContain('维度最佳标的');
      expect(html).toContain('适合投资者画像');
      expect(html).toContain('多维度定性与量化对比矩阵');
      expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
    });
  });

  describe('LongTermView', () => {
    it('renders 7 pillars of long-term value and thesis breakers alert cards', () => {
      const html = renderWithProviders(<LongTermView initialSymbol="NVDA" />);

      expect(html).toContain('长期持有价值与论文破裂监控');
      expect(html).toContain('7 大长期价值支柱综合评定');
      expect(html).toContain('商业模式与可持续性');
      expect(html).toContain('经济护城河深度');
      expect(html).toContain('行业发展跑道 (TAM)');
      expect(html).toContain('资本配置与管理层');
      expect(html).toContain('资产负债表与财务堡垒');
      expect(html).toContain('估值合理性与安全边际');
      expect(html).toContain('反脆弱性与适应力');
      expect(html).toContain('论文破裂条件监控预警');
      expect(html).toContain('CRITICAL');
      expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
    });
  });

  describe('PortfolioView', () => {
    it('renders portfolio configuration, conservation law check, and allocations', () => {
      const html = renderWithProviders(<PortfolioView />);

      expect(html).toContain('投资组合约束优化配置');
      expect(html).toContain('拟投资本金总额');
      expect(html).toContain('绝对守恒定律验证');
      expect(html).toContain('100% 守恒成立');
      expect(html).toContain('总权重求和 (∑ Weight%):');
      expect(html).toContain('分配金额求和 (∑ Amount):');
      expect(html).toContain('现金储备 (USD)');
      expect(html).toContain('动态再平衡纪律指南');
      expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
    });
  });
});
