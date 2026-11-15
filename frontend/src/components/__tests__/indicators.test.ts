import { describe, it, expect } from 'vitest';
import {
  calculateSMA,
  computeVolumeData,
  findKeySupportResistanceLevels,
  type CandleDataPoint,
} from '../../utils/indicators';

describe('Technical Indicator Calculations', () => {
  const sampleBars: CandleDataPoint[] = [
    { time: '2026-01-01', open: 100, high: 105, low: 98, close: 102, volume: 1000 },
    { time: '2026-01-02', open: 102, high: 108, low: 101, close: 107, volume: 1500 },
    { time: '2026-01-03', open: 107, high: 110, low: 104, close: 105, volume: 1200 },
    { time: '2026-01-04', open: 105, high: 106, low: 99, close: 100, volume: 900 },
    { time: '2026-01-05', open: 100, high: 103, low: 97, close: 101, volume: 1100 },
  ];

  describe('calculateSMA', () => {
    it('returns empty array when bars count is less than period', () => {
      const sma = calculateSMA(sampleBars, 10);
      expect(sma).toEqual([]);
    });

    it('returns empty array for non-positive period', () => {
      expect(calculateSMA(sampleBars, 0)).toEqual([]);
      expect(calculateSMA(sampleBars, -1)).toEqual([]);
    });

    it('accurately computes 3-period SMA', () => {
      const sma = calculateSMA(sampleBars, 3);
      // Index 2 (Day 3): (102 + 107 + 105) / 3 = 314 / 3 = 104.6667
      // Index 3 (Day 4): (107 + 105 + 100) / 3 = 312 / 3 = 104.0
      // Index 4 (Day 5): (105 + 100 + 101) / 3 = 306 / 3 = 102.0
      expect(sma).toHaveLength(3);
      expect(sma[0].time).toBe('2026-01-03');
      expect(sma[0].value).toBeCloseTo(104.6667, 3);
      expect(sma[1].time).toBe('2026-01-04');
      expect(sma[1].value).toBe(104.0);
      expect(sma[2].time).toBe('2026-01-05');
      expect(sma[2].value).toBe(102.0);
    });
  });

  describe('computeVolumeData', () => {
    it('assigns green to up bars and red to down bars in US mode', () => {
      const volumes = computeVolumeData(sampleBars, 'us');
      expect(volumes).toHaveLength(5);

      // Day 1: close 102 >= open 100 -> UP -> green
      expect(volumes[0].color).toContain('16, 185, 129');
      // Day 3: close 105 < open 107 -> DOWN -> red
      expect(volumes[2].color).toContain('239, 68, 68');
      // Day 4: close 100 < open 105 -> DOWN -> red
      expect(volumes[3].color).toContain('239, 68, 68');
      // Day 5: close 101 >= open 100 -> UP -> green
      expect(volumes[4].color).toContain('16, 185, 129');
    });

    it('assigns red to up bars and green to down bars in CN mode', () => {
      const volumes = computeVolumeData(sampleBars, 'cn');
      expect(volumes).toHaveLength(5);

      // Day 1: UP -> red
      expect(volumes[0].color).toContain('239, 68, 68');
      // Day 3: DOWN -> green
      expect(volumes[2].color).toContain('16, 185, 129');
    });
  });

  describe('findKeySupportResistanceLevels', () => {
    it('identifies min low and max high accurately', () => {
      const levels = findKeySupportResistanceLevels(sampleBars, 30);
      // Min low is 97 (Day 5)
      expect(levels.support).toBe(97);
      // Max high is 110 (Day 3)
      expect(levels.resistance).toBe(110);
    });

    it('returns zero for empty bars array', () => {
      const levels = findKeySupportResistanceLevels([]);
      expect(levels).toEqual({ support: 0, resistance: 0 });
    });
  });
});
