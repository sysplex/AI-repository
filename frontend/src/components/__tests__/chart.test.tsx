import { renderToString } from 'react-dom/server';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChartToolbar } from '../chart/ChartToolbar';
import { SignalLegend } from '../chart/SignalLegend';
import { marketApi } from '../../api/market';
import { httpClient } from '../../api/client';
import type { Bar, CompanyProfile, Quote } from '../../api/types';

describe('Chart Components & Market API', () => {
  describe('ChartToolbar', () => {
    it('renders interval buttons and indicator toggle states', () => {
      const html = renderToString(
        <ChartToolbar
          interval="1d"
          onIntervalChange={() => {}}
          showSMA20={true}
          onToggleSMA20={() => {}}
          showSMA50={false}
          onToggleSMA50={() => {}}
          showSMA200={true}
          onToggleSMA200={() => {}}
          showSupportResistance={true}
          onToggleSupportResistance={() => {}}
          showSignals={true}
          onToggleSignals={() => {}}
          onResetZoom={() => {}}
        />,
      );

      expect(html).toContain('日 K (1D)');
      expect(html).toContain('周 K (1W)');
      expect(html).toContain('SMA 20');
      expect(html).toContain('SMA 50');
      expect(html).toContain('SMA 200');
      expect(html).toContain('支撑/阻力线');
      expect(html).toContain('策略买卖信号');
      expect(html).toContain('重置视口');
    });
  });

  describe('SignalLegend', () => {
    it('renders trading signals and key support resistance levels', () => {
      const html = renderToString(
        <SignalLegend supportLevel={138.5} resistanceLevel={155.0} />,
      );

      expect(html).toContain('BUY (多头买入点)');
      expect(html).toContain('SELL (空头平仓点)');
      expect(html).toContain('SMA20');
      expect(html).toContain('SMA50');
      expect(html).toContain('SMA200');
      expect(html).toContain('支撑位: $138.50');
      expect(html).toContain('阻力位: $155.00');
    });
  });

  describe('Market API Client', () => {
    beforeEach(() => {
      vi.restoreAllMocks();
    });

    it('getBars dispatches get request with formatted params', async () => {
      const mockBars: Bar[] = [
        {
          symbol: 'NVDA',
          trade_date: '2026-11-14',
          open: '143.50',
          high: '146.20',
          low: '142.80',
          close: '145.89',
          volume: 48900000,
          adj_close: '145.89',
        },
      ];

      const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({
        data: mockBars,
      });

      const res = await marketApi.getBars({
        symbol: 'NVDA',
        start: '2026-05-18',
        end: '2026-11-14',
        interval: '1d',
      });

      expect(getSpy).toHaveBeenCalledWith('/market/bars/NVDA', {
        params: {
          start: '2026-05-18',
          end: '2026-11-14',
          interval: '1d',
          adjusted: true,
        },
      });
      expect(res).toHaveLength(1);
      expect(res[0].symbol).toBe('NVDA');
    });

    it('getQuotes queries comma-separated symbols', async () => {
      const mockQuotes: Quote[] = [
        {
          symbol: 'AAPL',
          price: '228.25',
          change: '1.92',
          change_pct: '0.85',
          volume: 32000000,
          as_of: '2026-11-14T16:00:00Z',
          delayed_seconds: 0,
          stale: false,
        },
      ];

      const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({
        data: mockQuotes,
      });

      const res = await marketApi.getQuotes(['AAPL', 'NVDA']);

      expect(getSpy).toHaveBeenCalledWith('/market/quotes', {
        params: {
          symbols: 'AAPL,NVDA',
        },
      });
      expect(res).toHaveLength(1);
    });

    it('getProfile fetches company profile by symbol', async () => {
      const mockProfile: CompanyProfile = {
        symbol: 'NVDA',
        name: 'NVIDIA Corporation',
        sector: 'Technology',
        industry: 'Semiconductors',
        country: 'US',
        exchange: 'NASDAQ',
        description: 'AI hardware & compute',
      };

      const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({
        data: mockProfile,
      });

      const res = await marketApi.getProfile('NVDA');
      expect(getSpy).toHaveBeenCalledWith('/market/profile/NVDA', {
        params: undefined,
      });
      expect(res.symbol).toBe('NVDA');
      expect(res.name).toBe('NVIDIA Corporation');
    });
  });
});
