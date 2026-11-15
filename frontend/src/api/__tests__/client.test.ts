import { describe, it, expect, beforeEach } from 'vitest';
import { storage, AUTH_TOKEN_KEY } from '../../utils/storage';
import { parseApiError, AppError } from '../../utils/errors';
import { formatPrice, formatPercent, formatLargeNumber, formatDateTime } from '../../utils/format';
import { httpClient } from '../client';

describe('Frontend Storage Utility', () => {
  beforeEach(() => {
    storage.remove(AUTH_TOKEN_KEY);
    storage.remove('test_json');
  });

  it('correctly sets and retrieves token', () => {
    expect(storage.get(AUTH_TOKEN_KEY)).toBeNull();
    storage.set(AUTH_TOKEN_KEY, 'test_token_abc');
    expect(storage.get(AUTH_TOKEN_KEY)).toBe('test_token_abc');
    storage.remove(AUTH_TOKEN_KEY);
    expect(storage.get(AUTH_TOKEN_KEY)).toBeNull();
  });

  it('correctly parses and writes JSON values', () => {
    const data = { user: 'alice', quota: 20 };
    storage.setJSON('test_json', data);
    const retrieved = storage.getJSON<{ user: string; quota: number }>('test_json');
    expect(retrieved).toEqual(data);
  });
});

describe('Error Model & Parsing', () => {
  it('parses standard backend structured errors', () => {
    const mockAxiosError = {
      isAxiosError: true,
      response: {
        status: 409,
        data: {
          error: {
            code: 'STATE_CONFLICT',
            message: '标的 AAPL 已存在于自选清单中',
            details: { symbol: 'AAPL' },
          },
        },
      },
    };

    const parsed = parseApiError(mockAxiosError);
    expect(parsed).toBeInstanceOf(AppError);
    expect(parsed.code).toBe('STATE_CONFLICT');
    expect(parsed.message).toBe('标的 AAPL 已存在于自选清单中');
    expect(parsed.status).toBe(409);
    expect(parsed.details).toEqual({ symbol: 'AAPL' });
  });

  it('falls back to standard HTTP status mapping when error body is plain', () => {
    const error401 = { isAxiosError: true, response: { status: 401 } };
    expect(parseApiError(error401).code).toBe('UNAUTHENTICATED');

    const error429 = { isAxiosError: true, response: { status: 429 } };
    expect(parseApiError(error429).code).toBe('QUOTA_EXCEEDED');

    const error503 = { isAxiosError: true, response: { status: 503 } };
    expect(parseApiError(error503).code).toBe('BUDGET_CIRCUIT_OPEN');
  });

  it('handles standard Error objects', () => {
    const err = new Error('Generic failure');
    const parsed = parseApiError(err);
    expect(parsed.message).toBe('Generic failure');
    expect(parsed.code).toBe('CLIENT_ERROR');
  });
});

describe('Financial Formatting Utilities', () => {
  it('formats stock prices correctly', () => {
    expect(formatPrice(185.5)).toBe('$185.50');
    expect(formatPrice('145.20')).toBe('$145.20');
    expect(formatPrice(0.0456)).toBe('$0.0456');
    expect(formatPrice(null)).toBe('--');
    expect(formatPrice(undefined)).toBe('--');
  });

  it('formats percentages with optional sign', () => {
    expect(formatPercent(2.456)).toBe('+2.46%');
    expect(formatPercent(-1.2)).toBe('-1.20%');
    expect(formatPercent(0)).toBe('0.00%');
    expect(formatPercent(null)).toBe('--');
  });

  it('formats large numbers into compact units', () => {
    expect(formatLargeNumber(1500)).toBe('1.50K');
    expect(formatLargeNumber(2500000)).toBe('2.50M');
    expect(formatLargeNumber(3200000000)).toBe('3.20B');
    expect(formatLargeNumber(4100000000000)).toBe('4.10T');
  });

  it('formats ISO dates correctly', () => {
    const formatted = formatDateTime('2026-11-15T10:00:00Z');
    expect(formatted).not.toBe('--');
    expect(formatted.length).toBeGreaterThan(5);
  });
});

describe('HTTP Client Request Interceptor', () => {
  it('attaches Bearer token from storage to outbound request config', async () => {
    storage.set(AUTH_TOKEN_KEY, 'bearer_token_xyz');

    // 直接对 request 拦截器进行单元逻辑验证
    const interceptor = (httpClient.interceptors.request as unknown as {
      handlers: Array<{ fulfilled: (config: unknown) => unknown }>;
    }).handlers[0].fulfilled;

    const dummyConfig = { headers: {} as Record<string, string> };
    const processed = (await interceptor(dummyConfig)) as { headers: Record<string, string> };

    expect(processed.headers.Authorization).toBe('Bearer bearer_token_xyz');
    expect(processed.headers['X-Request-ID']).toBeDefined();
    expect(processed.headers['X-Request-ID']).toMatch(/^req_\d+_/);
  });
});
