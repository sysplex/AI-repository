import { api } from './client';
import type {
  AIPromptInfo,
  BuyDecisionRequest,
  CompareRequest,
  EarningsAnalysisRequest,
  LongTermRequest,
  PortfolioRequest,
  QuotaStatus,
  ResearchEnvelope,
  ResearchRequest,
} from './types';

export const researchApi = {
  /**
   * F2: 个股深度研报生成（商业模式、护城河、风险、三段式情景）
   */
  async getResearch(symbol: string): Promise<ResearchEnvelope> {
    const payload: ResearchRequest = { symbol: symbol.toUpperCase() };
    return api.post<ResearchEnvelope>('/ai/research', payload);
  },

  /**
   * F3: 买入决策评估（目标价、持有期、风险承受、安全边际）
   */
  async getBuyDecision(params: BuyDecisionRequest): Promise<ResearchEnvelope> {
    return api.post<ResearchEnvelope>('/ai/buy-decision', {
      ...params,
      symbol: params.symbol.toUpperCase(),
    });
  },

  /**
   * F7: 财报深度解读（EPS、营收预期差、业绩指引）
   */
  async getEarnings(symbol: string): Promise<ResearchEnvelope> {
    const payload: EarningsAnalysisRequest = { symbol: symbol.toUpperCase() };
    return api.post<ResearchEnvelope>('/ai/earnings', payload);
  },

  /**
   * F4: 多标的横向对比（2–8 只股票自由对比矩阵）
   */
  async getCompare(symbols: string[]): Promise<ResearchEnvelope> {
    const payload: CompareRequest = {
      symbols: symbols.map((s) => s.toUpperCase()),
    };
    return api.post<ResearchEnvelope>('/ai/compare', payload);
  },

  /**
   * F5: 长期持有价值与论文破裂监控（5/10/15年持有、7大支柱评级）
   */
  async getLongTerm(symbol: string, years: 5 | 10 | 15 = 5): Promise<ResearchEnvelope> {
    const payload: LongTermRequest = {
      symbol: symbol.toUpperCase(),
      years,
    };
    return api.post<ResearchEnvelope>('/ai/long-term', payload);
  },

  /**
   * F8: 投资组合约束优化配置（资金分配、权重、守恒校验）
   */
  async getPortfolio(params: PortfolioRequest): Promise<ResearchEnvelope> {
    return api.post<ResearchEnvelope>('/ai/portfolio', {
      ...params,
      symbols: params.symbols.map((s) => s.toUpperCase()),
    });
  },

  /**
   * 查询系统当前提示词工程版本与模型配置
   */
  async getPrompts(): Promise<AIPromptInfo[]> {
    return api.get<AIPromptInfo[]>('/ai/prompts');
  },

  /**
   * 查询当前用户今日配额与熔断状态
   */
  async getQuota(): Promise<QuotaStatus> {
    return api.get<QuotaStatus>('/ai/quota');
  },

  /**
   * 测试第三方 AI API 密钥与模型可用性
   */
  async testApiKey(data: {
    provider: string;
    api_key: string;
    model?: string;
  }): Promise<{ valid: boolean; message: string; latency_ms: number }> {
    return api.post<{ valid: boolean; message: string; latency_ms: number }>('/ai/test-key', data);
  },
};

export default researchApi;
