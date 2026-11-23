import React from 'react';
import { renderToString } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import {
  ComplianceDisclaimer,
  MANDATORY_LEGAL_DISCLAIMER,
} from '../compliance/ComplianceDisclaimer';
import { DataFreshnessTag } from '../compliance/DataFreshnessTag';
import { AIPromptVersionBadge } from '../compliance/AIPromptVersionBadge';
import { getUSMarketStatus } from '../../utils/market';

describe('Compliance & Market Guardrails', () => {
  describe('ComplianceDisclaimer', () => {
    it('always renders the mandatory legal disclaimer text in card format', () => {
      const html = renderToString(React.createElement(ComplianceDisclaimer, { variant: 'card' }));
      expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
      expect(html).toContain('合规免责声明');
    });

    it('renders the mandatory legal disclaimer text in banner format', () => {
      const html = renderToString(React.createElement(ComplianceDisclaimer, { variant: 'banner' }));
      expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
    });

    it('renders inline format', () => {
      const html = renderToString(React.createElement(ComplianceDisclaimer, { variant: 'inline' }));
      expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
    });
  });

  describe('DataFreshnessTag', () => {
    it('renders fresh timestamp when stale is false', () => {
      const html = renderToString(
        React.createElement(DataFreshnessTag, {
          asOf: '2026-11-15T16:00:00Z',
          stale: false,
        }),
      );
      expect(html).toContain('数据截至:');
      expect(html).toContain('(ET)');
      expect(html).toContain('11:00:00'); // 16:00:00 UTC is 11:00:00 EST
      expect(html).not.toContain('[数据可能延迟]');
    });

    it('renders warning tag when data is stale', () => {
      const html = renderToString(
        React.createElement(DataFreshnessTag, {
          asOf: '2026-11-14T10:00:00Z',
          stale: true,
        }),
      );
      expect(html).toContain('数据截至:');
      expect(html).toContain('(ET)');
      expect(html).toContain('05:00:00'); // 10:00:00 UTC is 05:00:00 EST
      expect(html).toContain('[数据可能延迟]');
      expect(html).toContain('text-amber-300');
    });
  });

  describe('AIPromptVersionBadge', () => {
    it('renders model and prompt version audit badge per spec', () => {
      const html = renderToString(
        React.createElement(AIPromptVersionBadge, {
          model: 'gpt-4o',
          promptVersion: 'v1.0.0',
        }),
      );
      expect(html).toContain('AI 引擎: gpt-4o');
      expect(html).toContain('模板: v1.0.0');
    });

    it('renders custom model and prompt version', () => {
      const html = renderToString(
        React.createElement(AIPromptVersionBadge, {
          model: 'deepseek-chat',
          promptVersion: 'v1.2.0',
        }),
      );
      expect(html).toContain('AI 引擎: deepseek-chat');
      expect(html).toContain('模板: v1.2.0');
    });
  });

  describe('getUSMarketStatus', () => {
    it('returns closed for weekend dates', () => {
      // 2026-11-15 is Sunday
      const sunday = new Date('2026-11-15T15:00:00Z');
      const status = getUSMarketStatus(sunday);
      expect(status.status).toBe('closed');
      expect(status.label).toBe('已休市');
    });

    it('returns open during regular trading hours on weekdays', () => {
      // 2026-11-16 (Monday) 11:00 AM EST is 16:00 UTC
      const mondayTrading = new Date('2026-11-16T16:00:00Z');
      const status = getUSMarketStatus(mondayTrading);
      expect(status.status).toBe('open');
      expect(status.label).toBe('美股开盘中');
    });

    it('returns pre-market during 04:00-09:30 EST on weekdays', () => {
      // 2026-11-16 (Monday) 08:00 AM EST is 13:00 UTC
      const mondayPre = new Date('2026-11-16T13:00:00Z');
      const status = getUSMarketStatus(mondayPre);
      expect(status.status).toBe('pre');
      expect(status.label).toBe('盘前交易');
    });

    it('returns after-hours during 16:00-20:00 EST on weekdays', () => {
      // 2026-11-16 (Monday) 17:00 EST is 22:00 UTC
      const mondayAfter = new Date('2026-11-16T22:00:00Z');
      const status = getUSMarketStatus(mondayAfter);
      expect(status.status).toBe('after');
      expect(status.label).toBe('盘后交易');
    });
  });
});
