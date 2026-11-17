import { describe, it, expect, vi, beforeEach } from 'vitest';
import { reviewsApi, ReviewSummaryResponse } from '../reviews';
import { httpClient } from '../client';

describe('Reviews API Client Module', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockReviewSummary: ReviewSummaryResponse = {
    total_recommendations: 12,
    evaluated_count: 10,
    avg_return_5d: 0.03,
    avg_return_20d: 0.065,
    avg_return_60d: 0.12,
    avg_alpha_20d: 0.04,
    win_rate_20d: 0.8,
    by_verdict: {
      buy: {
        verdict: 'buy',
        total_count: 8,
        evaluated_5d_count: 8,
        evaluated_20d_count: 8,
        evaluated_60d_count: 6,
        avg_return_5d: 0.035,
        avg_return_20d: 0.075,
        avg_return_60d: 0.14,
        avg_alpha_20d: 0.045,
        win_rate_20d: 0.875,
      },
    },
    items: [],
  };

  it('getOutcomesSummary calls GET /reviews/ai-outcomes', async () => {
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockReviewSummary });
    const res = await reviewsApi.getOutcomesSummary({ verdict: 'buy', symbol: 'NVDA' });
    expect(getSpy).toHaveBeenCalledWith('/reviews/ai-outcomes', {
      params: { verdict: 'buy', symbol: 'NVDA' },
    });
    expect(res.total_recommendations).toBe(12);
    expect(res.win_rate_20d).toBe(0.8);
    expect(res.by_verdict.buy.win_rate_20d).toBe(0.875);
  });
});
