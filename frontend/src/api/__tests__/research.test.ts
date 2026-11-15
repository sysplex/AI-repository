import { describe, it, expect, vi, beforeEach } from 'vitest';
import { researchApi } from '../research';
import { httpClient } from '../client';
import type {
  BuyDecisionRequest,
  PortfolioRequest,
  ResearchEnvelope,
} from '../types';

describe('Research API Client Module', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockEnvelope: ResearchEnvelope = {
    schema_version: '1.0',
    use_case: 'research',
    symbol: 'NVDA',
    as_of: '2026-11-15',
    summary: 'Mock research summary',
    payload: { score: 90 },
    evidence: [],
    data_gaps: [],
    disclaimer: 'Legal disclaimer',
  };

  it('getResearch posts symbol payload to /ai/research', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({
      data: mockEnvelope,
    });

    const res = await researchApi.getResearch('nvda');
    expect(postSpy).toHaveBeenCalledWith('/ai/research', { symbol: 'NVDA' });
    expect(res.symbol).toBe('NVDA');
  });

  it('getBuyDecision posts buy decision request to /ai/buy-decision', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({
      data: { ...mockEnvelope, use_case: 'buy_decision' },
    });

    const req: BuyDecisionRequest = {
      symbol: 'nvda',
      target_price: 140,
      horizon: 'medium',
      risk_level: 'moderate',
    };

    const res = await researchApi.getBuyDecision(req);
    expect(postSpy).toHaveBeenCalledWith('/ai/buy-decision', {
      symbol: 'NVDA',
      target_price: 140,
      horizon: 'medium',
      risk_level: 'moderate',
    });
    expect(res.use_case).toBe('buy_decision');
  });

  it('getEarnings posts symbol to /ai/earnings', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({
      data: { ...mockEnvelope, use_case: 'earnings' },
    });

    const res = await researchApi.getEarnings('aapl');
    expect(postSpy).toHaveBeenCalledWith('/ai/earnings', { symbol: 'AAPL' });
    expect(res.use_case).toBe('earnings');
  });

  it('getCompare posts uppercase symbols list to /ai/compare', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({
      data: { ...mockEnvelope, use_case: 'compare' },
    });

    const res = await researchApi.getCompare(['aapl', 'msft']);
    expect(postSpy).toHaveBeenCalledWith('/ai/compare', {
      symbols: ['AAPL', 'MSFT'],
    });
    expect(res.use_case).toBe('compare');
  });

  it('getLongTerm posts symbol and years to /ai/long-term', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({
      data: { ...mockEnvelope, use_case: 'long_term' },
    });

    const res = await researchApi.getLongTerm('tsla', 10);
    expect(postSpy).toHaveBeenCalledWith('/ai/long-term', {
      symbol: 'TSLA',
      years: 10,
    });
    expect(res.use_case).toBe('long_term');
  });

  it('getPortfolio posts portfolio allocation request to /ai/portfolio', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({
      data: { ...mockEnvelope, use_case: 'portfolio' },
    });

    const req: PortfolioRequest = {
      amount: 50000,
      symbols: ['nvda', 'msft'],
      risk_level: 'aggressive',
      goal: 'growth',
    };

    const res = await researchApi.getPortfolio(req);
    expect(postSpy).toHaveBeenCalledWith('/ai/portfolio', {
      amount: 50000,
      symbols: ['NVDA', 'MSFT'],
      risk_level: 'aggressive',
      goal: 'growth',
    });
    expect(res.use_case).toBe('portfolio');
  });

  it('getPrompts queries /ai/prompts', async () => {
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({
      data: [{ use_case: 'research', version: 'v1.2.0', description: 'Stock research', is_active: true }],
    });

    const res = await researchApi.getPrompts();
    expect(getSpy).toHaveBeenCalledWith('/ai/prompts', { params: undefined });
    expect(res).toHaveLength(1);
    expect(res[0].use_case).toBe('research');
  });

  it('getQuota queries /ai/quota', async () => {
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({
      data: { user_id: 'u1', usage_date: '2026-11-15', calls_today: 5, daily_quota: 20, remaining_calls: 15, is_exceeded: false },
    });

    const res = await researchApi.getQuota();
    expect(getSpy).toHaveBeenCalledWith('/ai/quota', { params: undefined });
    expect(res.remaining_calls).toBe(15);
  });
});
