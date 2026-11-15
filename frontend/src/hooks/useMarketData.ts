import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import marketApi from '../api/market';
import type { Bar } from '../api/types';
import {
  calculateSMA,
  computeVolumeData,
  findKeySupportResistanceLevels,
  type CandleDataPoint,
} from '../utils/indicators';
import { useAuth } from './useAuth';

export interface UseMarketDataOptions {
  symbol: string;
  interval?: '1d' | '1w';
  lookbackDays?: number;
  enabled?: boolean;
}

export function useMarketData({
  symbol,
  interval = '1d',
  lookbackDays = 180,
  enabled = true,
}: UseMarketDataOptions) {
  const { colorScheme } = useAuth();

  const { start, end } = useMemo(() => {
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(endDate.getDate() - lookbackDays);

    return {
      start: startDate.toISOString().split('T')[0],
      end: endDate.toISOString().split('T')[0],
    };
  }, [lookbackDays]);

  const query = useQuery<Bar[]>({
    queryKey: ['market-bars', symbol, interval, start, end],
    queryFn: () => marketApi.getBars({ symbol, start, end, interval }),
    enabled: enabled && !!symbol,
    staleTime: 60 * 1000, // 1 分钟缓存
  });

  const formattedCandles: CandleDataPoint[] = useMemo(() => {
    if (!query.data || !Array.isArray(query.data)) return [];

    return query.data
      .map((bar) => ({
        time: bar.trade_date,
        open: parseFloat(bar.open),
        high: parseFloat(bar.high),
        low: parseFloat(bar.low),
        close: parseFloat(bar.close),
        volume: bar.volume,
      }))
      .sort((a, b) => a.time.localeCompare(b.time));
  }, [query.data]);

  const sma20 = useMemo(() => calculateSMA(formattedCandles, 20), [formattedCandles]);
  const sma50 = useMemo(() => calculateSMA(formattedCandles, 50), [formattedCandles]);
  const sma200 = useMemo(() => calculateSMA(formattedCandles, 200), [formattedCandles]);

  const volumeBars = useMemo(
    () => computeVolumeData(formattedCandles, colorScheme),
    [formattedCandles, colorScheme],
  );

  const keyLevels = useMemo(
    () => findKeySupportResistanceLevels(formattedCandles, 40),
    [formattedCandles],
  );

  const latestBar = formattedCandles.length > 0 ? formattedCandles[formattedCandles.length - 1] : null;
  const prevBar = formattedCandles.length > 1 ? formattedCandles[formattedCandles.length - 2] : null;

  const priceChange = latestBar && prevBar ? latestBar.close - prevBar.close : 0;
  const priceChangePercent = latestBar && prevBar && prevBar.close > 0
    ? (priceChange / prevBar.close) * 100
    : 0;

  return {
    ...query,
    candles: formattedCandles,
    volumeBars,
    sma20,
    sma50,
    sma200,
    keyLevels,
    latestBar,
    priceChange,
    priceChangePercent,
  };
}
