import React from 'react';
import { renderToString } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { getFinancialDirection, getFinancialColor } from '../../hooks/useFinancialColor';
import { PriceDisplay } from '../financial/PriceDisplay';
import { ChangePercent } from '../financial/ChangePercent';
import { MetricCard } from '../financial/MetricCard';

describe('Financial Components & Color Utilities', () => {
  describe('getFinancialDirection', () => {
    it('identifies up, down, and neutral values correctly', () => {
      expect(getFinancialDirection(10.5)).toBe('up');
      expect(getFinancialDirection(0.001)).toBe('up');
      expect(getFinancialDirection(-0.05)).toBe('down');
      expect(getFinancialDirection(-100)).toBe('down');
      expect(getFinancialDirection(0)).toBe('neutral');
      expect(getFinancialDirection(null)).toBe('neutral');
      expect(getFinancialDirection(undefined)).toBe('neutral');
      expect(getFinancialDirection(NaN)).toBe('neutral');
    });
  });

  describe('getFinancialColor logic (US vs CN modes)', () => {
    it('applies green for up and red for down under US scheme', () => {
      const upUs = getFinancialColor(5.0, 'us');
      expect(upUs.direction).toBe('up');
      expect(upUs.text).toContain('text-emerald-400');
      expect(upUs.fill).toBe('#10b981');

      const downUs = getFinancialColor(-5.0, 'us');
      expect(downUs.direction).toBe('down');
      expect(downUs.text).toContain('text-rose-400');
      expect(downUs.fill).toBe('#f43f5e');
    });

    it('applies red for up and green for down under CN scheme', () => {
      const upCn = getFinancialColor(5.0, 'cn');
      expect(upCn.direction).toBe('up');
      expect(upCn.text).toContain('text-rose-400');
      expect(upCn.fill).toBe('#f43f5e');

      const downCn = getFinancialColor(-5.0, 'cn');
      expect(downCn.direction).toBe('down');
      expect(downCn.text).toContain('text-emerald-400');
      expect(downCn.fill).toBe('#10b981');
    });

    it('applies neutral styling when value is 0 or null', () => {
      const neutral = getFinancialColor(0, 'us');
      expect(neutral.direction).toBe('neutral');
      expect(neutral.text).toContain('text-slate-400');
    });
  });

  describe('PriceDisplay component rendering', () => {
    it('renders standard US stock price with 2 decimals', () => {
      const html = renderToString(React.createElement(PriceDisplay, { value: 182.5 }));
      expect(html).toContain('$182.50');
    });

    it('renders micro-cap penny stock (< $1) with 4 decimals', () => {
      const html = renderToString(React.createElement(PriceDisplay, { value: 0.125 }));
      expect(html).toContain('$0.1250');
    });

    it('applies colored styling following US scheme', () => {
      const html = renderToString(
        React.createElement(PriceDisplay, {
          value: 145.89,
          colored: true,
          changeValue: 2.5,
          overrideScheme: 'us',
        }),
      );
      expect(html).toContain('$145.89');
      expect(html).toContain('text-emerald-400');
    });

    it('applies colored styling following CN scheme', () => {
      const html = renderToString(
        React.createElement(PriceDisplay, {
          value: 145.89,
          colored: true,
          changeValue: 2.5,
          overrideScheme: 'cn',
        }),
      );
      expect(html).toContain('$145.89');
      expect(html).toContain('text-rose-400');
    });

    it('renders placeholder -- when value is null or empty', () => {
      const html = renderToString(React.createElement(PriceDisplay, { value: null }));
      expect(html).toContain('--');
    });
  });

  describe('ChangePercent component rendering', () => {
    it('renders positive percentage with + sign and emerald badge under US mode', () => {
      const html = renderToString(
        React.createElement(ChangePercent, {
          value: 3.42,
          overrideScheme: 'us',
        }),
      );
      expect(html).toContain('+3.42%');
      expect(html).toContain('text-emerald-300');
    });

    it('renders negative percentage with rose badge under US mode', () => {
      const html = renderToString(
        React.createElement(ChangePercent, {
          value: -2.18,
          overrideScheme: 'us',
        }),
      );
      expect(html).toContain('-2.18%');
      expect(html).toContain('text-rose-300');
    });

    it('renders positive percentage with rose badge under CN mode', () => {
      const html = renderToString(
        React.createElement(ChangePercent, {
          value: 3.42,
          overrideScheme: 'cn',
        }),
      );
      expect(html).toContain('+3.42%');
      expect(html).toContain('text-rose-300');
    });

    it('renders text mode with changeAmount', () => {
      const html = renderToString(
        React.createElement(ChangePercent, {
          value: 1.5,
          changeAmount: 2.25,
          mode: 'text',
          overrideScheme: 'us',
        }),
      );
      expect(html).toContain('+$2.25');
      expect(html).toContain('+1.50%');
    });
  });

  describe('MetricCard component rendering', () => {
    it('renders title, value, change and subtext', () => {
      const html = renderToString(
        React.createElement(MetricCard, {
          title: '标普 500',
          value: '5,864.67',
          change: 0.75,
          subtext: '大盘权重企稳',
        }),
      );
      expect(html).toContain('标普 500');
      expect(html).toContain('5,864.67');
      expect(html).toContain('+0.75%');
      expect(html).toContain('大盘权重企稳');
    });

    it('renders loading skeleton when isLoading is true', () => {
      const html = renderToString(
        React.createElement(MetricCard, {
          title: '标普 500',
          value: '5,864.67',
          isLoading: true,
        }),
      );
      expect(html).toContain('animate-pulse');
      expect(html).not.toContain('5,864.67');
    });
  });
});
