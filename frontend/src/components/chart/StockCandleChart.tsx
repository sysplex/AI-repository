import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type IPriceLine,
} from 'lightweight-charts';
import { useAuth } from '../../hooks/useAuth';
import type { CandleDataPoint, TimePricePoint, VolumeBarPoint } from '../../utils/indicators';
import type { Signal } from '../../api/types';
import { ChartToolbar } from './ChartToolbar';
import { SignalLegend } from './SignalLegend';
import { formatPercent, formatPrice, formatLargeNumber } from '../../utils/format';
import { cn } from '../../utils/cn';

export interface StockCandleChartProps {
  symbol: string;
  candles: CandleDataPoint[];
  volumeBars?: VolumeBarPoint[];
  sma20?: TimePricePoint[];
  sma50?: TimePricePoint[];
  sma200?: TimePricePoint[];
  signals?: Signal[];
  supportLevel?: number;
  resistanceLevel?: number;
  interval?: '1d' | '1w';
  onIntervalChange?: (interval: '1d' | '1w') => void;
  height?: number;
  className?: string;
  overrideScheme?: 'us' | 'cn';
}

export const StockCandleChart: React.FC<StockCandleChartProps> = ({
  symbol,
  candles,
  volumeBars,
  sma20,
  sma50,
  sma200,
  signals = [],
  supportLevel,
  resistanceLevel,
  interval = '1d',
  onIntervalChange,
  height = 460,
  className,
  overrideScheme,
}) => {
  const { colorScheme: authScheme } = useAuth();
  const colorScheme = overrideScheme || authScheme || 'us';

  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const sma20SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const sma50SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const sma200SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);

  // 指标图层显隐开关
  const [showSMA20, setShowSMA20] = useState(true);
  const [showSMA50, setShowSMA50] = useState(true);
  const [showSMA200, setShowSMA200] = useState(true);
  const [showSupportResistance, setShowSupportResistance] = useState(true);
  const [showSignals, setShowSignals] = useState(true);

  // 悬浮十字光标实时 Bar 数据
  const [hoveredBar, setHoveredBar] = useState<CandleDataPoint | null>(null);

  // 初始化与重建 Chart 实例
  useEffect(() => {
    if (!containerRef.current) return;

    const isUS = colorScheme === 'us';
    const upColor = isUS ? '#10b981' : '#ef4444';
    const downColor = isUS ? '#ef4444' : '#10b981';

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: height - 85, // 减去工具栏与图例高度
      layout: {
        background: { type: ColorType.Solid, color: '#090d16' },
        textColor: '#94a3b8',
        fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
      },
      grid: {
        vertLines: { color: 'rgba(30, 41, 59, 0.4)' },
        horzLines: { color: 'rgba(30, 41, 59, 0.4)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: 'rgba(148, 163, 184, 0.5)',
          width: 1,
          style: LineStyle.Dotted,
          labelBackgroundColor: '#1e293b',
        },
        horzLine: {
          color: 'rgba(148, 163, 184, 0.5)',
          width: 1,
          style: LineStyle.Dotted,
          labelBackgroundColor: '#1e293b',
        },
      },
      rightPriceScale: {
        borderColor: 'rgba(51, 65, 85, 0.6)',
        scaleMargins: {
          top: 0.08,
          bottom: 0.22, // 底部留给成交量副图
        },
      },
      timeScale: {
        borderColor: 'rgba(51, 65, 85, 0.6)',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // 1. K 线主图
    const candleSeries = chart.addCandlestickSeries({
      upColor,
      downColor,
      borderVisible: true,
      borderUpColor: upColor,
      borderDownColor: downColor,
      wickUpColor: upColor,
      wickDownColor: downColor,
    });
    candleSeriesRef.current = candleSeries;

    // 2. 成交量副图
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '', // 独立副图
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.82,
        bottom: 0,
      },
    });
    volumeSeriesRef.current = volumeSeries;

    // 3. 均线叠加系列
    const sma20Series = chart.addLineSeries({
      color: '#38bdf8',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      title: 'SMA 20',
    });
    sma20SeriesRef.current = sma20Series;

    const sma50Series = chart.addLineSeries({
      color: '#f59e0b',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      title: 'SMA 50',
    });
    sma50SeriesRef.current = sma50Series;

    const sma200Series = chart.addLineSeries({
      color: '#a855f7',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      title: 'SMA 200',
    });
    sma200SeriesRef.current = sma200Series;

    // 十字光标移动事件
    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData || !candleSeriesRef.current) {
        setHoveredBar(null);
        return;
      }
      const data = param.seriesData.get(candleSeriesRef.current) as any;
      if (data && data.open !== undefined) {
        setHoveredBar({
          time: String(param.time),
          open: data.open,
          high: data.high,
          low: data.low,
          close: data.close,
          volume: 0, // lightweight charts 数据结构
        });
      }
    });

    // 窗口尺寸自适应观察器
    const resizeObserver = new ResizeObserver((entries) => {
      if (!entries || entries.length === 0 || !containerRef.current) return;
      const { width } = entries[0].contentRect;
      if (width > 0) {
        chart.applyOptions({ width });
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      sma20SeriesRef.current = null;
      sma50SeriesRef.current = null;
      sma200SeriesRef.current = null;
    };
  }, [colorScheme, height]);

  // 更新蜡烛与成交量数据
  useEffect(() => {
    if (!candleSeriesRef.current || !candles || candles.length === 0) return;

    const chartCandles = candles.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    candleSeriesRef.current.setData(chartCandles);

    if (volumeSeriesRef.current && volumeBars) {
      const chartVolumes = volumeBars.map((v) => ({
        time: v.time as Time,
        value: v.value,
        color: v.color,
      }));
      volumeSeriesRef.current.setData(chartVolumes);
    }

    // 自动适配全屏 K 线
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [candles, volumeBars]);

  // 更新 SMA 20
  useEffect(() => {
    if (!sma20SeriesRef.current) return;
    if (showSMA20 && sma20 && sma20.length > 0) {
      sma20SeriesRef.current.setData(
        sma20.map((p) => ({ time: p.time as Time, value: p.value })),
      );
    } else {
      sma20SeriesRef.current.setData([]);
    }
  }, [sma20, showSMA20]);

  // 更新 SMA 50
  useEffect(() => {
    if (!sma50SeriesRef.current) return;
    if (showSMA50 && sma50 && sma50.length > 0) {
      sma50SeriesRef.current.setData(
        sma50.map((p) => ({ time: p.time as Time, value: p.value })),
      );
    } else {
      sma50SeriesRef.current.setData([]);
    }
  }, [sma50, showSMA50]);

  // 更新 SMA 200
  useEffect(() => {
    if (!sma200SeriesRef.current) return;
    if (showSMA200 && sma200 && sma200.length > 0) {
      sma200SeriesRef.current.setData(
        sma200.map((p) => ({ time: p.time as Time, value: p.value })),
      );
    } else {
      sma200SeriesRef.current.setData([]);
    }
  }, [sma200, showSMA200]);

  // 更新支撑阻力线与策略水平位
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    // 清理既有水平价格线
    priceLinesRef.current.forEach((line) => {
      try {
        candleSeriesRef.current?.removePriceLine(line);
      } catch {
        // ignore
      }
    });
    priceLinesRef.current = [];

    if (showSupportResistance) {
      if (supportLevel && supportLevel > 0) {
        const supportLine = candleSeriesRef.current.createPriceLine({
          price: supportLevel,
          color: '#10b981',
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: '支撑位 S',
        });
        priceLinesRef.current.push(supportLine);
      }

      if (resistanceLevel && resistanceLevel > 0) {
        const resLine = candleSeriesRef.current.createPriceLine({
          price: resistanceLevel,
          color: '#ef4444',
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: '阻力位 R',
        });
        priceLinesRef.current.push(resLine);
      }
    }

    // 若有具体 Signal 的关键水平线
    if (showSignals && signals.length > 0) {
      const latestSig = signals[signals.length - 1];
      if (latestSig.levels) {
        if (latestSig.levels.stop_loss) {
          const stopVal = parseFloat(latestSig.levels.stop_loss);
          if (!isNaN(stopVal) && stopVal > 0) {
            const stopLine = candleSeriesRef.current.createPriceLine({
              price: stopVal,
              color: '#f43f5e',
              lineWidth: 1,
              lineStyle: LineStyle.Dashed,
              axisLabelVisible: true,
              title: '止损 SL',
            });
            priceLinesRef.current.push(stopLine);
          }
        }

        if (latestSig.levels.target) {
          const targetVal = parseFloat(latestSig.levels.target);
          if (!isNaN(targetVal) && targetVal > 0) {
            const targetLine = candleSeriesRef.current.createPriceLine({
              price: targetVal,
              color: '#10b981',
              lineWidth: 1,
              lineStyle: LineStyle.Dashed,
              axisLabelVisible: true,
              title: '目标 TP',
            });
            priceLinesRef.current.push(targetLine);
          }
        }
      }
    }
  }, [supportLevel, resistanceLevel, showSupportResistance, showSignals, signals]);

  // 更新策略买卖信号 Markers
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    if (!showSignals || !signals || signals.length === 0) {
      candleSeriesRef.current.setMarkers([]);
      return;
    }

    const markers: SeriesMarker<Time>[] = [];
    signals.forEach((sig) => {
      const isLong = sig.direction === 'long';
      const isShort = sig.direction === 'short';

      if (isLong) {
        markers.push({
          time: sig.as_of as Time,
          position: 'belowBar',
          color: '#10b981',
          shape: 'arrowUp',
          text: `BUY (${sig.strength})`,
        });
      } else if (isShort) {
        markers.push({
          time: sig.as_of as Time,
          position: 'aboveBar',
          color: '#ef4444',
          shape: 'arrowDown',
          text: `SELL (${sig.strength})`,
        });
      }
    });

    // Markers 必须按时间排序
    markers.sort((a, b) => String(a.time).localeCompare(String(b.time)));
    candleSeriesRef.current.setMarkers(markers);
  }, [signals, showSignals]);

  const handleResetZoom = useCallback(() => {
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, []);

  // 顶栏实时报价与当前悬停 Bar 数据
  const activeBar = hoveredBar || (candles.length > 0 ? candles[candles.length - 1] : null);
  const barChange = activeBar ? activeBar.close - activeBar.open : 0;
  const barChangePercent = activeBar && activeBar.open > 0 ? (barChange / activeBar.open) * 100 : 0;

  return (
    <div
      className={cn(
        'rounded-xl border border-slate-800 bg-slate-950 overflow-hidden shadow-lg flex flex-col',
        className,
      )}
    >
      {/* 顶部工具栏 */}
      <ChartToolbar
        interval={interval}
        onIntervalChange={onIntervalChange || (() => {})}
        showSMA20={showSMA20}
        onToggleSMA20={() => setShowSMA20(!showSMA20)}
        showSMA50={showSMA50}
        onToggleSMA50={() => setShowSMA50(!showSMA50)}
        showSMA200={showSMA200}
        onToggleSMA200={() => setShowSMA200(!showSMA200)}
        showSupportResistance={showSupportResistance}
        onToggleSupportResistance={() => setShowSupportResistance(!showSupportResistance)}
        showSignals={showSignals}
        onToggleSignals={() => setShowSignals(!showSignals)}
        onResetZoom={handleResetZoom}
      />

      {/* 实时 OHLCV 十字光标数值栏 */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-2 bg-slate-900/60 border-b border-slate-800/80 text-xs font-mono select-none">
        <div className="flex items-center gap-2">
          <span className="font-bold text-white text-sm">{symbol}</span>
          <span className="text-slate-400">{activeBar ? activeBar.time : '--'}</span>
        </div>

        {activeBar ? (
          <div className="flex flex-wrap items-center gap-3 text-slate-300 text-[11px] sm:text-xs">
            <div>
              <span className="text-slate-500 mr-1">开:</span>
              <span className="text-white font-medium">{formatPrice(activeBar.open)}</span>
            </div>
            <div>
              <span className="text-slate-500 mr-1">高:</span>
              <span className="text-white font-medium">{formatPrice(activeBar.high)}</span>
            </div>
            <div>
              <span className="text-slate-500 mr-1">低:</span>
              <span className="text-white font-medium">{formatPrice(activeBar.low)}</span>
            </div>
            <div>
              <span className="text-slate-500 mr-1">收:</span>
              <span className="text-white font-medium">{formatPrice(activeBar.close)}</span>
            </div>
            <div className={barChange >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
              <span className="font-semibold">{formatPercent(barChangePercent)}</span>
              <span className="ml-1 opacity-80">
                ({barChange >= 0 ? `+${formatPrice(barChange)}` : formatPrice(barChange)})
              </span>
            </div>
            {activeBar.volume > 0 && (
              <div>
                <span className="text-slate-500 mr-1">量:</span>
                <span className="text-slate-200">{formatLargeNumber(activeBar.volume)}</span>
              </div>
            )}
          </div>
        ) : (
          <span className="text-slate-500 text-xs">加载 K 线数据中...</span>
        )}
      </div>

      {/* Lightweight Charts 挂载容器 */}
      <div ref={containerRef} className="w-full relative flex-1" style={{ height: `${height - 85}px` }} />

      {/* 底部图例 */}
      <SignalLegend supportLevel={supportLevel} resistanceLevel={resistanceLevel} />
    </div>
  );
};

export default StockCandleChart;
