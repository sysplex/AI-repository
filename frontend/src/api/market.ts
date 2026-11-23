import { api } from './client';
import type { Bar, CompanyProfile, Fundamentals, Quote } from './types';

export interface GetBarsParams {
  symbol: string;
  start: string;
  end: string;
  interval?: string; // '1d', '1w', '1h'
  adjusted?: boolean;
}

export const marketApi = {
  /**
   * 获取指定标的历史 K 线蜡烛数据
   */
  async getBars(params: GetBarsParams): Promise<Bar[]> {
    return api.get<Bar[]>(`/market/bars/${encodeURIComponent(params.symbol)}`, {
      start: params.start,
      end: params.end,
      interval: params.interval || '1d',
      adjusted: params.adjusted !== undefined ? params.adjusted : true,
    });
  },

  /**
   * 批量获取标的实时或延时最新报价（统一归一化为 Quote[]）
   */
  async getQuotes(symbols: string[]): Promise<Quote[]> {
    if (!symbols || symbols.length === 0) return [];
    const query = symbols.join(',');
    const data = await api.get<Record<string, Quote> | Quote[]>('/market/quotes', { symbols: query });
    if (Array.isArray(data)) {
      return data;
    }
    if (data && typeof data === 'object') {
      return Object.values(data);
    }
    return [];
  },

  /**
   * 获取公司档案概况
   */
  async getProfile(symbol: string): Promise<CompanyProfile> {
    return api.get<CompanyProfile>(`/market/profile/${encodeURIComponent(symbol)}`);
  },

  /**
   * 获取基本面财务指标
   */
  async getFundamentals(symbol: string): Promise<Fundamentals> {
    return api.get<Fundamentals>(`/market/fundamentals/${encodeURIComponent(symbol)}`);
  },
};

export default marketApi;
