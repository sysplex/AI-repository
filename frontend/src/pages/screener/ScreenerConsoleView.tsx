import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  Filter,
  History,
  Layers,
  Play,
  Plus,
  RefreshCw,
  Share2,
  TrendingUp,
} from 'lucide-react';
import { screenerApi } from '../../api/screener';
import type {
  ScreenerRunCreate,
  ScreenerRunRead,
  UniverseInfo,
  WatchlistRead,
} from '../../api/types';
import {
  mockCompletedScreenerRun,
  mockStrategyOptions,
  mockUniverses,
} from './mockData';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Modal } from '../../components/common/Modal';
import { ChangePercent } from '../../components/financial/ChangePercent';
import { PriceDisplay } from '../../components/financial/PriceDisplay';
import { ComplianceDisclaimer } from '../../components/compliance/ComplianceDisclaimer';
import { cn } from '../../utils/cn';

export const ScreenerConsoleView: React.FC = () => {
  const navigate = useNavigate();

  // Control Form States
  const [universes, setUniverses] = useState<UniverseInfo[]>(mockUniverses);
  const [selectedUniverse, setSelectedUniverse] = useState<string>('sp500');
  const [customSymbolsInput, setCustomSymbolsInput] = useState<string>('NVDA, AAPL, MSFT, AMZN, GOOGL, META, TSLA');
  const [selectedStrategyId, setSelectedStrategyId] = useState<string>('trend_following');

  // Strategy Tuning Parameters
  const activeStrategy =
    mockStrategyOptions.find((s) => s.id === selectedStrategyId) || mockStrategyOptions[0];
  const [strategyParams, setStrategyParams] = useState<Record<string, any>>(activeStrategy.defaultParams);

  // Active Screener Run State
  const [currentRun, setCurrentRun] = useState<ScreenerRunRead | null>(mockCompletedScreenerRun);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [runProgressMessage, setRunProgressMessage] = useState<string>('');

  // History Runs List
  const [historyRuns, setHistoryRuns] = useState<ScreenerRunRead[]>([mockCompletedScreenerRun]);
  const [showHistory, setShowHistory] = useState<boolean>(false);

  // Results Selection & Batch Actions
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [watchlists, setWatchlists] = useState<WatchlistRead[]>([]);
  const [isBatchImportModalOpen, setIsBatchImportModalOpen] = useState<boolean>(false);
  const [targetWatchlistId, setTargetWatchlistId] = useState<string>('');
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const pollIntervalRef = useRef<number | null>(null);

  useEffect(() => {
    loadInitialData();
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  // Update default params when strategy changes
  useEffect(() => {
    if (activeStrategy) {
      setStrategyParams(activeStrategy.defaultParams);
    }
  }, [selectedStrategyId]);

  const loadInitialData = async () => {
    try {
      const [uData, wData, rData] = await Promise.allSettled([
        screenerApi.listUniverses(),
        screenerApi.listWatchlists(),
        screenerApi.listScreenerRuns(10),
      ]);

      if (uData.status === 'fulfilled' && uData.value.length > 0) {
        setUniverses(uData.value);
      }
      if (wData.status === 'fulfilled' && wData.value.length > 0) {
        setWatchlists(wData.value);
        const def = wData.value.find((w) => w.is_default) || wData.value[0];
        setTargetWatchlistId(def.id);
      }
      if (rData.status === 'fulfilled' && rData.value.length > 0) {
        setHistoryRuns(rData.value);
        setCurrentRun(rData.value[0]);
      }
    } catch {
      // Keep mock initial states
    }
  };

  // Trigger Screener Execution
  const handleStartScreener = async () => {
    setIsRunning(true);
    setRunProgressMessage('正在初始化股票池与行情快照...');
    setSelectedSymbols([]);

    const customSymbols =
      selectedUniverse === 'custom'
        ? customSymbolsInput
            .split(/[,，\s]+/)
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean)
        : null;

    const payload: ScreenerRunCreate = {
      universe: selectedUniverse,
      strategy_id: selectedStrategyId,
      params: strategyParams,
      custom_symbols: customSymbols,
    };

    try {
      const createdRun = await screenerApi.createScreenerRun(payload);
      setCurrentRun(createdRun);

      // If already succeeded or failed immediately
      if (createdRun.status === 'succeeded' || createdRun.status === 'failed') {
        setIsRunning(false);
        setHistoryRuns((prev) => [createdRun, ...prev.filter((r) => r.id !== createdRun.id)]);
        return;
      }

      // Poll until completion
      setRunProgressMessage('策略模型并行扫描与多因子打分中...');
      let attempts = 0;
      pollIntervalRef.current = window.setInterval(async () => {
        attempts++;
        try {
          const polled = await screenerApi.getScreenerRun(createdRun.id);
          setCurrentRun(polled);

          if (polled.status === 'succeeded' || polled.status === 'failed' || attempts > 20) {
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
            setIsRunning(false);
            setHistoryRuns((prev) => [polled, ...prev.filter((r) => r.id !== polled.id)]);
          }
        } catch {
          // Poll fallback
          if (attempts > 3) {
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
            setIsRunning(false);
          }
        }
      }, 1200);
    } catch {
      // Simulate fast local run for mock environment
      setTimeout(() => {
        setRunProgressMessage('正在聚合技术指标与估值分位数...');
        setTimeout(() => {
          setIsRunning(false);
          const simulatedRun: ScreenerRunRead = {
            ...mockCompletedScreenerRun,
            id: `run-${Date.now()}`,
            strategy_id: selectedStrategyId,
            universe: selectedUniverse,
            created_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
          };
          setCurrentRun(simulatedRun);
          setHistoryRuns((prev) => [simulatedRun, ...prev]);
        }, 800);
      }, 600);
    }
  };

  // Toggle selection
  const handleToggleSelectAll = () => {
    if (!currentRun?.results) return;
    if (selectedSymbols.length === currentRun.results.length) {
      setSelectedSymbols([]);
    } else {
      setSelectedSymbols(currentRun.results.map((r) => r.symbol));
    }
  };

  const handleToggleSymbol = (symbol: string) => {
    setSelectedSymbols((prev) =>
      prev.includes(symbol) ? prev.filter((s) => s !== symbol) : [...prev, symbol],
    );
  };

  // Batch import to watchlist
  const handleConfirmBatchImport = async () => {
    if (!targetWatchlistId || selectedSymbols.length === 0) return;

    let successCount = 0;
    for (const sym of selectedSymbols) {
      try {
        await screenerApi.addWatchlistItem(targetWatchlistId, {
          symbol: sym,
          notes: `来自策略筛选「${activeStrategy.name}」`,
          theme_tags: ['量化筛选'],
        });
        successCount++;
      } catch {
        // Continue
      }
    }

    setIsBatchImportModalOpen(false);
    showToast(`已成功将 ${successCount} 只标的添加至自选清单！`);
    setSelectedSymbols([]);
  };

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  // Export to Research / Compare
  const handleExportSelected = (action: 'compare' | 'portfolio') => {
    const symbols = selectedSymbols.length > 0
      ? selectedSymbols
      : (currentRun?.results || []).slice(0, 6).map((r) => r.symbol);

    if (symbols.length === 0) {
      alert('暂无标的可供导出');
      return;
    }

    if (action === 'compare') {
      navigate(`/research?tab=compare&symbols=${symbols.slice(0, 8).join(',')}`);
    } else {
      navigate(`/research?tab=portfolio&symbols=${symbols.slice(0, 10).join(',')}`);
    }
  };

  const getSignalBadge = (signal: string) => {
    const s = signal.toUpperCase();
    if (s.includes('STRONG_BUY') || s.includes('BUY')) {
      return (
        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
          {s}
        </span>
      );
    }
    if (s.includes('SELL')) {
      return (
        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
          {s}
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
        {s}
      </span>
    );
  };

  return (
    <div className="space-y-8">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-20 right-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 text-white font-medium text-xs shadow-lg shadow-blue-500/20 animate-in fade-in">
          <CheckCircle2 className="h-4 w-4" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Control Console Card */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 space-y-6 shadow-md">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Filter className="h-5 w-5 text-blue-500" />
              <span>策略筛选控制台</span>
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              设定股票池与量化模型，多进程极速回测并实时生成标的综合排名与核心技术快照。
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowHistory(!showHistory)}
              leftIcon={<History className="h-4 w-4 text-slate-400" />}
            >
              历史筛选任务 ({historyRuns.length})
            </Button>
          </div>
        </div>

        {/* Console Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Step 1: Universe Selection (4 cols) */}
          <div className="lg:col-span-4 space-y-3">
            <label className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase tracking-wider">
              <span className="h-4 w-4 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-mono">
                1
              </span>
              <span>选择目标股票池</span>
            </label>

            <div className="space-y-2">
              {universes.map((uni) => {
                const isSelected = selectedUniverse === uni.id;
                return (
                  <div
                    key={uni.id}
                    onClick={() => setSelectedUniverse(uni.id)}
                    className={cn(
                      'p-3 rounded-xl border text-left cursor-pointer transition-all select-none',
                      isSelected
                        ? 'bg-blue-950/40 border-blue-500 text-white shadow-sm'
                        : 'bg-slate-950/60 border-slate-800 hover:border-slate-700 text-slate-300',
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-xs">{uni.name}</span>
                      {uni.symbol_count > 0 && (
                        <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                          {uni.symbol_count} 只
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-slate-400 mt-1 line-clamp-1">
                      {uni.description}
                    </p>
                  </div>
                );
              })}
            </div>

            {selectedUniverse === 'custom' && (
              <div className="space-y-1.5 pt-2">
                <label className="text-[11px] text-slate-300 font-medium">输入自定义标的代码 (逗号隔开)</label>
                <textarea
                  rows={2}
                  value={customSymbolsInput}
                  onChange={(e) => setCustomSymbolsInput(e.target.value)}
                  placeholder="例如 NVDA, AAPL, MSFT, TSLA"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 p-2 text-xs font-mono text-white focus:border-blue-500 focus:outline-none"
                />
              </div>
            )}
          </div>

          {/* Step 2: Strategy Model (4 cols) */}
          <div className="lg:col-span-4 space-y-3">
            <label className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase tracking-wider">
              <span className="h-4 w-4 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-mono">
                2
              </span>
              <span>选择量化策略模型</span>
            </label>

            <div className="space-y-2">
              {mockStrategyOptions.map((strat) => {
                const isSelected = selectedStrategyId === strat.id;
                return (
                  <div
                    key={strat.id}
                    onClick={() => setSelectedStrategyId(strat.id)}
                    className={cn(
                      'p-3 rounded-xl border text-left cursor-pointer transition-all select-none',
                      isSelected
                        ? 'bg-indigo-950/40 border-indigo-500 text-white shadow-sm'
                        : 'bg-slate-950/60 border-slate-800 hover:border-slate-700 text-slate-300',
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-xs">{strat.name}</span>
                      <Badge variant="neutral" size="xs">
                        {strat.category}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-1 line-clamp-2">
                      {strat.description}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Step 3: Parameter Tuning & Execute (4 cols) */}
          <div className="lg:col-span-4 space-y-4 flex flex-col justify-between">
            <div className="space-y-3">
              <label className="text-xs font-bold text-slate-200 flex items-center gap-1.5 uppercase tracking-wider">
                <span className="h-4 w-4 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-mono">
                  3
                </span>
                <span>策略微调参数</span>
              </label>

              <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 space-y-3">
                {Object.entries(strategyParams).map(([key, val]) => (
                  <div key={key} className="flex items-center justify-between gap-2">
                    <span className="text-xs font-mono text-slate-300">{key}</span>
                    <input
                      type="number"
                      step={typeof val === 'number' && val < 5 ? '0.1' : '1'}
                      value={val}
                      onChange={(e) =>
                        setStrategyParams((prev) => ({
                          ...prev,
                          [key]: parseFloat(e.target.value) || 0,
                        }))
                      }
                      className="w-24 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-right text-xs font-mono text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                ))}
                <div className="pt-1 text-[10px] text-slate-500 text-right">
                  支持自定义数值，回车即可生效
                </div>
              </div>
            </div>

            <Button
              size="lg"
              variant="primary"
              onClick={handleStartScreener}
              isLoading={isRunning}
              leftIcon={<Play className="h-4 w-4 fill-white" />}
              className="w-full py-3 text-sm font-bold shadow-lg shadow-blue-600/30"
            >
              {isRunning ? '量化计算执行中...' : '开始全池策略筛选'}
            </Button>
          </div>
        </div>

        {/* Running Progress Notification */}
        {isRunning && (
          <div className="flex items-center gap-3 p-4 rounded-xl bg-blue-950/40 border border-blue-800 text-blue-200 text-xs">
            <RefreshCw className="h-4 w-4 animate-spin text-blue-400 shrink-0" />
            <div className="flex-1">
              <p className="font-semibold">{runProgressMessage || '任务已提交，正在排队执行...'}</p>
              <div className="h-1.5 w-full bg-slate-800 rounded-full mt-2 overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full animate-pulse w-3/4" />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* History Drawer / Modal */}
      {showHistory && (
        <Modal
          isOpen={showHistory}
          onClose={() => setShowHistory(false)}
          title="历史策略筛选记录"
        >
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {historyRuns.map((run) => (
              <div
                key={run.id}
                onClick={() => {
                  setCurrentRun(run);
                  setShowHistory(false);
                }}
                className={cn(
                  'p-3 rounded-lg border text-xs cursor-pointer transition-colors flex items-center justify-between',
                  currentRun?.id === run.id
                    ? 'border-blue-500 bg-blue-950/30'
                    : 'border-slate-800 bg-slate-900 hover:bg-slate-800/80',
                )}
              >
                <div>
                  <div className="font-semibold text-white flex items-center gap-2">
                    <span>{run.strategy_id}</span>
                    <Badge variant="neutral" size="xs">
                      {run.universe}
                    </Badge>
                  </div>
                  <span className="text-[10px] text-slate-400 font-mono">
                    命中 {run.matched_count} 只 / 扫描 {run.total_symbols} 只
                  </span>
                </div>
                <div className="text-right">
                  <Badge variant={run.status === 'succeeded' ? 'success' : 'warning'} size="xs">
                    {run.status}
                  </Badge>
                  <p className="text-[10px] text-slate-500 font-mono mt-1">
                    {new Date(run.created_at).toLocaleTimeString()}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Modal>
      )}

      {/* Results Section */}
      {currentRun && (
        <div className="space-y-4">
          {/* Results Summary Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl border border-slate-800 bg-slate-900/60">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400">
                <CheckCircle2 className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <span>筛选结果排名榜单</span>
                  <Badge variant="success" size="xs">
                    命中 {currentRun.matched_count || currentRun.results?.length || 0} 只
                  </Badge>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5 font-mono">
                  股票池: {currentRun.universe.toUpperCase()} ｜ 策略模型: {currentRun.strategy_id} ｜ 共扫描 {currentRun.total_symbols} 只标的
                </p>
              </div>
            </div>

            {/* Batch Action Buttons */}
            <div className="flex items-center gap-2 shrink-0">
              <Button
                size="sm"
                variant="outline"
                disabled={selectedSymbols.length === 0}
                onClick={() => setIsBatchImportModalOpen(true)}
                leftIcon={<Plus className="h-3.5 w-3.5 text-blue-400" />}
              >
                加入自选 ({selectedSymbols.length})
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleExportSelected('compare')}
                leftIcon={<Share2 className="h-3.5 w-3.5 text-indigo-400" />}
              >
                横向对比
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleExportSelected('portfolio')}
                leftIcon={<Layers className="h-3.5 w-3.5 text-purple-400" />}
              >
                组合配置
              </Button>
            </div>
          </div>

          {/* Results Table */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/80 overflow-hidden shadow-sm">
            {(!currentRun.results || currentRun.results.length === 0) ? (
              <div className="p-12 text-center text-slate-400 space-y-2">
                <Filter className="h-8 w-8 text-slate-600 mx-auto" />
                <p className="text-sm">在当前参数与股票池下未找到满足全部条件的标的</p>
                <p className="text-xs text-slate-500">建议放宽过滤阈值（例如 RSI 或均线周期）后重新运行。</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                    <tr>
                      <th className="py-3 px-4 w-10 text-center">
                        <input
                          type="checkbox"
                          checked={
                            selectedSymbols.length === (currentRun.results?.length || 0) &&
                            (currentRun.results?.length || 0) > 0
                          }
                          onChange={handleToggleSelectAll}
                          className="rounded border-slate-700 bg-slate-800 text-blue-600 focus:ring-blue-500"
                        />
                      </th>
                      <th className="py-3 px-4 w-16">排名</th>
                      <th className="py-3 px-4">标的代码</th>
                      <th className="py-3 px-4">量化综合得分</th>
                      <th className="py-3 px-4">策略信号</th>
                      <th className="py-3 px-4">最新价格</th>
                      <th className="py-3 px-4">当日涨跌</th>
                      <th className="py-3 px-4">RSI (14)</th>
                      <th className="py-3 px-4">PE 估值</th>
                      <th className="py-3 px-4">核心形态快照</th>
                      <th className="py-3 px-4 text-right">投研动作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-sans">
                    {currentRun.results.map((item) => {
                      const isSelected = selectedSymbols.includes(item.symbol);
                      const metrics = (item.metrics_snapshot || {}) as Record<string, any>;
                      const price = metrics.price || 150.0;
                      const changePct = metrics.change_pct !== undefined ? metrics.change_pct : 1.5;
                      const rsi = metrics.rsi_14 !== undefined ? metrics.rsi_14 : 55.0;
                      const pe = metrics.pe_ratio !== undefined ? metrics.pe_ratio : 25.0;
                      const trendStatus = metrics.trend_status || '多头排列企稳';

                      return (
                        <tr
                          key={item.symbol}
                          className={cn(
                            'hover:bg-slate-800/40 transition-colors',
                            isSelected && 'bg-blue-950/20',
                          )}
                        >
                          <td className="py-3 px-4 text-center">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => handleToggleSymbol(item.symbol)}
                              className="rounded border-slate-700 bg-slate-800 text-blue-600 focus:ring-blue-500"
                            />
                          </td>
                          <td className="py-3 px-4 font-mono font-bold text-slate-300">
                            #{item.rank}
                          </td>
                          <td className="py-3 px-4 font-mono font-extrabold text-white">
                            <button
                              onClick={() => navigate(`/research?symbol=${item.symbol}`)}
                              className="hover:text-blue-400 transition-colors flex items-center gap-1 group"
                            >
                              <span>{item.symbol}</span>
                              <ExternalLink className="h-3 w-3 opacity-0 group-hover:opacity-100" />
                            </button>
                          </td>
                          <td className="py-3 px-4 font-mono">
                            <span className="font-bold text-amber-400 text-sm">
                              {parseFloat(item.score).toFixed(1)}
                            </span>
                            <span className="text-[10px] text-slate-500"> / 100</span>
                          </td>
                          <td className="py-3 px-4">
                            {getSignalBadge(item.signal)}
                          </td>
                          <td className="py-3 px-4 font-mono font-medium text-white">
                            <PriceDisplay value={price} />
                          </td>
                          <td className="py-3 px-4">
                            <ChangePercent value={changePct} />
                          </td>
                          <td className="py-3 px-4 font-mono text-slate-300">
                            {typeof rsi === 'number' ? rsi.toFixed(1) : rsi}
                          </td>
                          <td className="py-3 px-4 font-mono text-slate-300">
                            {typeof pe === 'number' ? `${pe.toFixed(1)}x` : pe}
                          </td>
                          <td className="py-3 px-4 text-slate-300 font-medium">
                            <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-200 border border-slate-700/60">
                              {trendStatus}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => navigate(`/research?symbol=${item.symbol}`)}
                                title="AI 深度个股研报"
                                leftIcon={<TrendingUp className="h-3.5 w-3.5 text-blue-400" />}
                              >
                                研报
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() =>
                                  navigate(`/research?tab=buy-decision&symbol=${item.symbol}`)
                                }
                                title="买入决策评估"
                                leftIcon={<ArrowRight className="h-3.5 w-3.5 text-emerald-400" />}
                              >
                                决策
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <ComplianceDisclaimer variant="card" />
        </div>
      )}

      {/* Modal: Batch Add to Watchlist */}
      <Modal
        isOpen={isBatchImportModalOpen}
        onClose={() => setIsBatchImportModalOpen(false)}
        title={`批量添加选定标的 (${selectedSymbols.length} 只)`}
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-300">
            即将把选中的标的 ({selectedSymbols.join(', ')}) 批量添加至以下自选清单：
          </p>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-200">目标自选清单</label>
            {watchlists.length === 0 ? (
              <p className="text-xs text-amber-400">暂无自选清单，请在自选模块中创建。</p>
            ) : (
              <select
                value={targetWatchlistId}
                onChange={(e) => setTargetWatchlistId(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white focus:border-blue-500 focus:outline-none"
              >
                {watchlists.map((wl) => (
                  <option key={wl.id} value={wl.id}>
                    {wl.name} {wl.is_default ? '(默认清单)' : ''} ({wl.items?.length || 0} 只)
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={() => setIsBatchImportModalOpen(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              disabled={watchlists.length === 0 || !targetWatchlistId}
              onClick={handleConfirmBatchImport}
              leftIcon={<Plus className="h-4 w-4" />}
            >
              确认批量添加
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ScreenerConsoleView;
