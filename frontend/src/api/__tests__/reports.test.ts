import { describe, it, expect, vi, beforeEach } from 'vitest';
import { reportsApi, DailyReportRead, PipelineRunResult } from '../reports';
import { httpClient } from '../client';

describe('Daily Reports & Scheduler API Client Module', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockReport: DailyReportRead = {
    id: 'rep-1',
    user_id: null,
    report_date: '2026-11-17',
    report_type: 'market_digest',
    title: '美股大盘收盘简报',
    summary: '三大指数普涨',
    payload: { sp500: '+0.8%' },
    created_at: '2026-11-17T21:15:00Z',
  };

  it('listDailyReports calls GET /reports/daily', async () => {
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: [mockReport] });
    const res = await reportsApi.listDailyReports({ date: '2026-11-17', report_type: 'market_digest' });
    expect(getSpy).toHaveBeenCalledWith('/reports/daily', { params: { date: '2026-11-17', report_type: 'market_digest' } });
    expect(res).toHaveLength(1);
    expect(res[0].id).toBe('rep-1');
  });

  it('getDailyReport calls GET /reports/daily/:id', async () => {
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockReport });
    const res = await reportsApi.getDailyReport('rep-1');
    expect(getSpy).toHaveBeenCalledWith('/reports/daily/rep-1', { params: undefined });
    expect(res.id).toBe('rep-1');
  });

  it('runPostMarketPipeline calls POST /scheduler/run-post-market', async () => {
    const mockPipelineRes: PipelineRunResult = {
      trade_date: '2026-11-17',
      status: 'completed',
      started_at: '2026-11-17T21:15:00Z',
      finished_at: '2026-11-17T21:15:10Z',
      is_trading_day: true,
      steps: [],
    };
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({ data: mockPipelineRes });
    const res = await reportsApi.runPostMarketPipeline({ trade_date: '2026-11-17', force: true });
    expect(postSpy).toHaveBeenCalledWith('/scheduler/run-post-market', { trade_date: '2026-11-17', force: true });
    expect(res.status).toBe('completed');
  });
});
