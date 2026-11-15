import { renderToString } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { AxiosError } from 'axios';
import { DataFreshnessTag } from '../../components/compliance/DataFreshnessTag';
import { ComplianceDisclaimer, MANDATORY_LEGAL_DISCLAIMER } from '../../components/compliance/ComplianceDisclaimer';
import { AIPromptVersionBadge } from '../../components/compliance/AIPromptVersionBadge';
import { parseApiError, AppError } from '../../utils/errors';

describe('E2E-03: Failure Handling & Graceful Degradation (异常与降级验收)', () => {
  describe('Data Freshness and Stale Warnings', () => {
    it('displays warning badge "[数据可能延迟]" when data source is stale or delayed', () => {
      const htmlStale = renderToString(
        <DataFreshnessTag asOf="2026-11-15T09:30:00Z" stale={true} marketTimezone="EST" />,
      );

      expect(htmlStale).toContain('[数据可能延迟]');
      expect(htmlStale).toContain('数据截至:');
      expect(htmlStale).toContain('EST');
      expect(htmlStale).toContain('text-amber');
    });

    it('displays normal freshness indicator when data source is real-time and healthy', () => {
      const htmlFresh = renderToString(
        <DataFreshnessTag asOf="2026-11-15T15:59:00Z" stale={false} marketTimezone="EST" />,
      );

      expect(htmlFresh).not.toContain('[数据可能延迟]');
      expect(htmlFresh).toContain('数据截至:');
      expect(htmlFresh).toContain('数据更新正常');
    });
  });

  describe('API Error Interception and User-Friendly Messaging', () => {
    it('intercepts 429 QUOTA_EXCEEDED and converts to actionable friendly message', () => {
      const mockAxiosErr429 = {
        isAxiosError: true,
        response: {
          status: 429,
          data: {},
        },
      } as unknown as AxiosError;

      const appErr = parseApiError(mockAxiosErr429);
      expect(appErr).toBeInstanceOf(AppError);
      expect(appErr.status).toBe(429);
      expect(appErr.code).toBe('QUOTA_EXCEEDED');
      expect(appErr.message).toContain('今日 AI 配额已达上限');
    });

    it('intercepts 503 BUDGET_CIRCUIT_OPEN and presents system circuit break warning', () => {
      const mockAxiosErr503 = {
        isAxiosError: true,
        response: {
          status: 503,
          data: {},
        },
      } as unknown as AxiosError;

      const appErr = parseApiError(mockAxiosErr503);
      expect(appErr).toBeInstanceOf(AppError);
      expect(appErr.status).toBe(503);
      expect(appErr.code).toBe('BUDGET_CIRCUIT_OPEN');
      expect(appErr.message).toContain('服务熔断保护已触发');
    });

    it('intercepts 401 UNAUTHENTICATED session expiration', () => {
      const mockAxiosErr401 = {
        isAxiosError: true,
        response: {
          status: 401,
          data: {},
        },
      } as unknown as AxiosError;

      const appErr = parseApiError(mockAxiosErr401);
      expect(appErr.status).toBe(401);
      expect(appErr.code).toBe('UNAUTHENTICATED');
      expect(appErr.message).toContain('认证已过期，请重新登录');
    });
  });

  describe('Compliance Guardrails Retention during Degradation', () => {
    it('always preserves mandatory legal disclaimer even in degraded states', () => {
      const htmlDisclaimer = renderToString(<ComplianceDisclaimer variant="card" />);
      expect(htmlDisclaimer).toContain(MANDATORY_LEGAL_DISCLAIMER);
      expect(htmlDisclaimer).toContain('合规免责声明（Legal Disclaimer）');
    });

    it('provides AI engine model and prompt template audit badge for all outputs', () => {
      const htmlBadge = renderToString(
        <AIPromptVersionBadge model="gpt-4o" promptVersion="v1.0.0" />,
      );
      expect(htmlBadge).toContain('AI 引擎: gpt-4o');
      expect(htmlBadge).toContain('模板: v1.0.0');
    });
  });
});
