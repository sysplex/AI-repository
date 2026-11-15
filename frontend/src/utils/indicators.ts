export interface TimePricePoint {
  time: string;
  value: number;
}

export interface VolumeBarPoint {
  time: string;
  value: number;
  color: string;
}

export interface CandleDataPoint {
  time: string; // YYYY-MM-DD
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/**
 * 计算简单移动平均线（Simple Moving Average, SMA）
 * @param bars K 线数组（按时间升序）
 * @param period 周期（如 20, 50, 200）
 */
export function calculateSMA(bars: CandleDataPoint[], period: number): TimePricePoint[] {
  if (!bars || bars.length < period || period <= 0) {
    return [];
  }

  const result: TimePricePoint[] = [];
  let sum = 0;

  for (let i = 0; i < bars.length; i++) {
    sum += bars[i].close;

    if (i >= period) {
      sum -= bars[i - period].close;
    }

    if (i >= period - 1) {
      const avg = sum / period;
      result.push({
        time: bars[i].time,
        value: parseFloat(avg.toFixed(4)),
      });
    }
  }

  return result;
}

/**
 * 计算成交量柱状图配色（根据 K 线收盘价与开盘价关系以及用户配色偏好）
 */
export function computeVolumeData(
  bars: CandleDataPoint[],
  scheme: 'us' | 'cn' = 'us',
): VolumeBarPoint[] {
  return bars.map((bar) => {
    const isUp = bar.close >= bar.open;
    const isGreen = (isUp && scheme === 'us') || (!isUp && scheme === 'cn');

    // 半透明柱体，避免遮挡蜡烛图
    const color = isGreen ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)';

    return {
      time: bar.time,
      value: bar.volume,
      color,
    };
  });
}

/**
 * 根据历史高低点快速计算近期关键支撑位与阻力位
 */
export function findKeySupportResistanceLevels(
  bars: CandleDataPoint[],
  lookback = 30,
): { support: number; resistance: number } {
  if (!bars || bars.length === 0) {
    return { support: 0, resistance: 0 };
  }

  const slice = bars.slice(-lookback);
  let minLow = Infinity;
  let maxHigh = -Infinity;

  for (const b of slice) {
    if (b.low < minLow) minLow = b.low;
    if (b.high > maxHigh) maxHigh = b.high;
  }

  return {
    support: minLow === Infinity ? 0 : parseFloat(minLow.toFixed(2)),
    resistance: maxHigh === -Infinity ? 0 : parseFloat(maxHigh.toFixed(2)),
  };
}
