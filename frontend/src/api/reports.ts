/**
 * M10: 每日投研简报与收盘批处理调度前端 API 客户端。
 */

import { api } from './client';

export type DailyReportType = 'market_digest' | 'portfolio_digest';
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface DailyReportRead {
  id: string;
  user_id: string | null;
  report_date: string;
  report_type: DailyReportType;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface PipelineStepStatus {
  name: string;
  status: JobStatus;
  started_at: string;
  finished_at: string | null;
  error_message?: string | null;
  details: Record<string, unknown>;
}

export interface PipelineRunResult {
  trade_date: string;
  status: JobStatus;
  started_at: string;
  finished_at: string | null;
  is_trading_day: boolean;
  steps: PipelineStepStatus[];
  error_message?: string | null;
}

export const reportsApi = {
  async listDailyReports(params?: {
    date?: string;
    report_type?: DailyReportType;
    limit?: number;
    offset?: number;
  }): Promise<DailyReportRead[]> {
    return api.get<DailyReportRead[]>('/reports/daily', params as Record<string, unknown>);
  },

  async getDailyReport(id: string): Promise<DailyReportRead> {
    return api.get<DailyReportRead>(`/reports/daily/${id}`);
  },

  async runPostMarketPipeline(data?: {
    trade_date?: string;
    force?: boolean;
  }): Promise<PipelineRunResult> {
    return api.post<PipelineRunResult>('/scheduler/run-post-market', data || {});
  },
};

export default reportsApi;
