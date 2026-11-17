/**
 * M10: AI 投资建议事后表现复盘与超额收益评估前端 API 客户端。
 */

import { api } from './client';

export interface VerdictStatsResponse {
  verdict: string;
  total_count: number;
  evaluated_5d_count: number;
  evaluated_20d_count: number;
  evaluated_60d_count: number;
  avg_return_5d: number | null;
  avg_return_20d: number | null;
  avg_return_60d: number | null;
  avg_alpha_20d: number | null;
  win_rate_20d: number | null;
}

export interface AIRecommendationOutcomeResponse {
  id: string;
  report_id: string;
  symbol: string;
  verdict: string;
  p0: number | string | null;
  p_5d: number | string | null;
  p_20d: number | string | null;
  p_60d: number | string | null;
  ret_5d: number | string | null;
  ret_20d: number | string | null;
  ret_60d: number | string | null;
  ret_vs_spy_20d: number | string | null;
  created_at: string;
}

export interface ReviewSummaryResponse {
  total_recommendations: number;
  evaluated_count: number;
  avg_return_5d: number | null;
  avg_return_20d: number | null;
  avg_return_60d: number | null;
  avg_alpha_20d: number | null;
  win_rate_20d: number | null;
  by_verdict: Record<string, VerdictStatsResponse>;
  items: AIRecommendationOutcomeResponse[];
}

export const reviewsApi = {
  async getOutcomesSummary(params?: {
    verdict?: string;
    symbol?: string;
    start_date?: string;
    end_date?: string;
    limit?: number;
    offset?: number;
  }): Promise<ReviewSummaryResponse> {
    return api.get<ReviewSummaryResponse>('/reviews/ai-outcomes', params as Record<string, unknown>);
  },
};

export default reviewsApi;
