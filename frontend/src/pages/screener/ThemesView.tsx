import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  BookmarkCheck,
  Check,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  Flame,
  Lightbulb,
  Plus,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  UserCheck,
  Zap,
} from 'lucide-react';
import { screenerApi } from '../../api/screener';
import type {
  ThemeCardsResponse,
  ThemeInfo,
  WatchlistRead,
} from '../../api/types';
import { mockThemeCardsMap, mockThemes } from './mockData';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/common/Badge';
import { Modal } from '../../components/common/Modal';
import { Skeleton } from '../../components/common/Skeleton';
import { AIPromptVersionBadge } from '../../components/compliance/AIPromptVersionBadge';
import { DataFreshnessTag } from '../../components/compliance/DataFreshnessTag';
import { ComplianceDisclaimer } from '../../components/compliance/ComplianceDisclaimer';
import { cn } from '../../utils/cn';

export const ThemesView: React.FC = () => {
  const navigate = useNavigate();

  const isMockEnabled = import.meta.env.VITE_ENABLE_MOCK === 'true' || import.meta.env.MODE === 'test';

  // Themes state
  const [themes, setThemes] = useState<ThemeInfo[]>(() => (isMockEnabled ? mockThemes : []));
  const [activeThemeId, setActiveThemeId] = useState<string>(() => (isMockEnabled ? (mockThemes[0]?.id || 'ai_chips') : ''));
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [isLoadingThemes, setIsLoadingThemes] = useState<boolean>(false);
  const [themeError, setThemeError] = useState<string | null>(null);

  // Theme AI Cards state
  const [themeCards, setThemeCards] = useState<Record<string, ThemeCardsResponse>>(() => (isMockEnabled ? mockThemeCardsMap : {}));
  const [isGeneratingCards, setIsGeneratingCards] = useState<boolean>(false);

  // Watchlists for import
  const [watchlists, setWatchlists] = useState<WatchlistRead[]>([]);
  const [isImportModalOpen, setIsImportModalOpen] = useState<boolean>(false);
  const [targetWatchlistId, setTargetWatchlistId] = useState<string>('');
  const [importStockSymbol, setImportStockSymbol] = useState<string | null>(null); // null means import all
  const [importSuccessMessage, setImportSuccessMessage] = useState<string | null>(null);

  const activeTheme = themes.find((t) => t.id === activeThemeId) || themes[0];
  const activeCardsResponse = activeTheme ? themeCards[activeTheme.id] : null;

  useEffect(() => {
    loadThemes();
    loadWatchlists();
  }, []);

  const loadThemes = async () => {
    setIsLoadingThemes(true);
    setThemeError(null);
    try {
      const data = await screenerApi.listThemes();
      if (data && data.length > 0) {
        setThemes(data);
        if (!activeThemeId || !data.some((t) => t.id === activeThemeId)) {
          setActiveThemeId(data[0].id);
        }
      }
    } catch (err: unknown) {
      if (isMockEnabled) {
        setThemes(mockThemes);
      } else {
        const msg = err instanceof Error ? err.message : '获取热门主题列表失败，请检查网络或服务配置';
        setThemeError(msg);
      }
    } finally {
      setIsLoadingThemes(false);
    }
  };

  const loadWatchlists = async () => {
    try {
      const data = await screenerApi.listWatchlists();
      if (data && data.length > 0) {
        setWatchlists(data);
        const def = data.find((w) => w.is_default) || data[0];
        setTargetWatchlistId(def.id);
      }
    } catch {
      // Graceful fallback
    }
  };

  const handleGenerateCards = async () => {
    if (!activeTheme) return;
    setIsGeneratingCards(true);
    setThemeError(null);
    try {
      const res = await screenerApi.generateThemeCards(activeTheme.id);
      if (res && res.cards) {
        setThemeCards((prev) => ({ ...prev, [activeTheme.id]: res }));
      }
    } catch (err: unknown) {
      if (isMockEnabled) {
        // If endpoint not reachable or mock, use local mock cards if available
        if (mockThemeCardsMap[activeTheme.id]) {
          setThemeCards((prev) => ({
            ...prev,
            [activeTheme.id]: mockThemeCardsMap[activeTheme.id],
          }));
        } else {
          // Synthesize cards for themes without preset
          const synthResponse: ThemeCardsResponse = {
            theme_id: activeTheme.id,
            theme_name: activeTheme.name,
            as_of: new Date().toISOString(),
            prompt_version: 'v2.4.0-facts',
            cards: (activeTheme.stocks || []).map((s) => ({
              symbol: s.symbol,
              name: s.name,
              one_line_intro: `${s.name} 是 ${s.sector} 赛道中 ${s.sub_industry} 领域的代表性龙头。`,
              why_watch: `受益于「${activeTheme.name}」宏观产业景气度扩张与技术换代催化。`,
              financial_strengths: [
                `在 ${s.sub_industry} 细分赛道具备较高市场份额`,
                '资产负债表健康，自由现金流充裕',
                '持续的研发投入保持竞争护城河',
              ],
              main_risks: [
                '行业宏观周期波动与下游需求不确定性',
                '估值短期处于相对高位回撤风险',
              ],
              suitable_for: ['中长线成长型投资者', '产业趋势配置者'],
              more_attractive_when: '回撤至年线或重要支撑位，估值倍数回落至历史中位数时。',
            })),
          };
          setThemeCards((prev) => ({ ...prev, [activeTheme.id]: synthResponse }));
        }
      } else {
        const msg = err instanceof Error ? err.message : '生成主题投研卡片失败，请检查 AI 服务或重试';
        setThemeError(msg);
      }
    } finally {
      setIsGeneratingCards(false);
    }
  };

  // Open import modal
  const openImportModal = (symbol?: string) => {
    setImportStockSymbol(symbol || null);
    setIsImportModalOpen(true);
  };

  // Execute import to watchlist
  const handleConfirmImport = async () => {
    if (!activeTheme || !targetWatchlistId) return;

    const symbolsToAdd: string[] = importStockSymbol
      ? [importStockSymbol]
      : (activeTheme.stocks || []).map((s) => s.symbol);

    let addedCount = 0;
    for (const sym of symbolsToAdd) {
      try {
        await screenerApi.addWatchlistItem(targetWatchlistId, {
          symbol: sym,
          notes: `来自主题「${activeTheme.name}」`,
          theme_tags: [activeTheme.name],
        });
        addedCount++;
      } catch {
        // Skip duplicate or handle error gracefully
      }
    }

    setIsImportModalOpen(false);
    setImportSuccessMessage(
      `已成功将 ${addedCount} 只标的导入自选清单！`,
    );
    setTimeout(() => setImportSuccessMessage(null), 3000);
  };

  // Filtered themes
  const filteredThemes = themes.filter((t) => {
    if (categoryFilter === 'all') return true;
    return t.category.toLowerCase() === categoryFilter.toLowerCase();
  });

  const getTierBadge = (tier: string) => {
    switch (tier.toLowerCase()) {
      case 'mega':
        return <Badge variant="purple" size="xs">Mega 超大盘</Badge>;
      case 'large':
        return <Badge variant="info" size="xs">Large 大盘</Badge>;
      case 'mid':
        return <Badge variant="neutral" size="xs">Mid 中盘</Badge>;
      default:
        return <Badge variant="neutral" size="xs">{tier}</Badge>;
    }
  };

  const getCategoryLabel = (cat: string) => {
    switch (cat.toLowerCase()) {
      case 'tech':
        return '硬核科技';
      case 'healthcare':
        return '医疗健康';
      case 'dividend':
        return '高息红利';
      case 'energy':
        return '清洁能源';
      default:
        return cat;
    }
  };

  return (
    <div className="space-y-8">
      {/* Success Toast */}
      {importSuccessMessage && (
        <div className="fixed top-20 right-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500/90 text-white font-medium text-xs shadow-lg shadow-emerald-500/20 animate-in fade-in slide-in-from-top-2">
          <CheckCircle2 className="h-4 w-4" />
          <span>{importSuccessMessage}</span>
        </div>
      )}

      {/* Themes Header & Category Tabs */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Flame className="h-6 w-6 text-amber-500" />
            <h2 className="text-xl font-bold text-white">热门宏观投资主题库</h2>
            <Badge variant="warning" size="xs">F9 预设池</Badge>
          </div>
          <p className="text-xs text-slate-400 mt-1 max-w-2xl">
            覆盖产业高景气与高资本开支核心主线，结合严格 Fact 约束的 AI 单股投研卡片，助您快速看清商业模式与风险要素。
          </p>
        </div>

        {/* Category Filter Pills */}
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-900 border border-slate-800 self-start">
          {[
            { id: 'all', label: '全部主题' },
            { id: 'tech', label: '硬核科技' },
            { id: 'healthcare', label: '医疗健康' },
            { id: 'dividend', label: '高息红利' },
            { id: 'energy', label: '清洁能源' },
          ].map((cat) => (
            <button
              key={cat.id}
              onClick={() => setCategoryFilter(cat.id)}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                categoryFilter === cat.id
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60',
              )}
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error Banner */}
      {themeError && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/50 flex items-start justify-between gap-3 text-rose-200 text-sm">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-rose-400">错误:</span>
            <span>{themeError}</span>
          </div>
          <Button
            size="xs"
            variant="outline"
            className="border-rose-500/50 text-rose-300 hover:bg-rose-900/40"
            onClick={() => loadThemes()}
          >
            重试
          </Button>
        </div>
      )}

      {/* Loading Skeleton */}
      {isLoadingThemes && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="h-44 bg-slate-800/40 rounded-xl animate-pulse" />
          <div className="h-44 bg-slate-800/40 rounded-xl animate-pulse" />
          <div className="h-44 bg-slate-800/40 rounded-xl animate-pulse" />
        </div>
      )}

      {/* Themes Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredThemes.map((theme) => {
          const isSelected = theme.id === activeThemeId;
          return (
            <div
              key={theme.id}
              onClick={() => setActiveThemeId(theme.id)}
              className={cn(
                'group relative p-5 rounded-xl border transition-all cursor-pointer text-left flex flex-col justify-between select-none',
                isSelected
                  ? 'bg-gradient-to-b from-blue-900/30 to-slate-900/90 border-blue-500/80 shadow-lg shadow-blue-500/10'
                  : 'bg-slate-900/60 hover:bg-slate-800/50 border-slate-800/80 hover:border-slate-700',
              )}
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <Badge variant="neutral" size="xs">
                    {getCategoryLabel(theme.category)}
                  </Badge>
                  <span className="text-[11px] text-slate-400 font-mono">
                    {theme.stocks?.length || 0} 只成分股
                  </span>
                </div>

                <div>
                  <h3 className="text-base font-bold text-white group-hover:text-blue-400 transition-colors flex items-center justify-between">
                    <span>{theme.name}</span>
                    <ChevronRight
                      className={cn(
                        'h-4 w-4 transition-transform text-slate-500 group-hover:text-blue-400',
                        isSelected && 'rotate-90 text-blue-400',
                      )}
                    />
                  </h3>
                  <p className="text-xs font-medium text-amber-400/90 mt-1 line-clamp-1">
                    {theme.tagline}
                  </p>
                </div>

                <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                  {theme.description}
                </p>
              </div>

              {/* Sample stock pills */}
              <div className="pt-4 mt-3 border-t border-slate-800/60 flex items-center justify-between">
                <div className="flex items-center gap-1.5 overflow-hidden">
                  {(theme.stocks || []).slice(0, 4).map((s) => (
                    <span
                      key={s.symbol}
                      className="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-800/80 text-slate-300 border border-slate-700/50"
                    >
                      {s.symbol}
                    </span>
                  ))}
                  {(theme.stocks?.length || 0) > 4 && (
                    <span className="text-[10px] text-slate-500 font-mono">
                      +{(theme.stocks?.length || 0) - 4}
                    </span>
                  )}
                </div>

                <span className="text-[11px] font-medium text-blue-400 flex items-center gap-0.5 group-hover:translate-x-0.5 transition-transform">
                  查看卡片
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected Theme Detail & AI Cards Section */}
      {activeTheme && (
        <div className="space-y-6 pt-4 border-t border-slate-800">
          {/* Header of Active Theme */}
          <div className="p-6 rounded-2xl border border-slate-800 bg-gradient-to-r from-slate-900/90 via-slate-900/60 to-slate-950 flex flex-col md:flex-row md:items-center justify-between gap-6 shadow-md">
            <div className="space-y-2">
              <div className="flex items-center gap-2.5">
                <h3 className="text-2xl font-extrabold text-white">{activeTheme.name}</h3>
                <Badge variant="info">{getCategoryLabel(activeTheme.category)}</Badge>
                <span className="text-xs text-slate-400 font-mono">
                  共包含 {activeTheme.stocks?.length || 0} 只核心资产
                </span>
              </div>
              <p className="text-sm font-semibold text-amber-400">
                {activeTheme.tagline}
              </p>
              <p className="text-xs text-slate-300 max-w-3xl leading-relaxed">
                {activeTheme.description}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5 shrink-0">
              {isLoadingThemes && (
                <span className="text-[11px] text-slate-500 animate-pulse font-mono">加载中...</span>
              )}
              <Button
                variant="primary"
                onClick={handleGenerateCards}
                isLoading={isGeneratingCards}
                leftIcon={<Sparkles className="h-4 w-4" />}
              >
                生成 / 刷新 AI 投研卡片
              </Button>

              <Button
                variant="outline"
                onClick={() => openImportModal()}
                leftIcon={<Plus className="h-4 w-4" />}
              >
                一键全量导入自选
              </Button>
            </div>
          </div>

          {/* Component Stocks Table */}
          <div className="space-y-3">
            <div className="flex items-center justify-between px-1">
              <h4 className="text-sm font-bold text-white flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-blue-400" />
                <span>主题成分股明细 ({activeTheme.stocks?.length || 0})</span>
              </h4>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/80 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/60 text-slate-400 uppercase font-semibold border-b border-slate-800">
                    <tr>
                      <th className="py-3 px-4">代码</th>
                      <th className="py-3 px-4">公司全称</th>
                      <th className="py-3 px-4">一级板块</th>
                      <th className="py-3 px-4">细分赛道 / 产业环节</th>
                      <th className="py-3 px-4">市值梯队</th>
                      <th className="py-3 px-4 text-right">快捷操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-sans">
                    {(activeTheme.stocks || []).map((stock) => (
                      <tr key={stock.symbol} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-4 font-mono font-bold text-white">
                          <button
                            onClick={() => navigate(`/research?symbol=${stock.symbol}`)}
                            className="hover:text-blue-400 transition-colors flex items-center gap-1 group"
                          >
                            <span>{stock.symbol}</span>
                            <ExternalLink className="h-3 w-3 opacity-0 group-hover:opacity-100" />
                          </button>
                        </td>
                        <td className="py-3 px-4 text-slate-300 font-medium">
                          {stock.name}
                        </td>
                        <td className="py-3 px-4 text-slate-400">
                          {stock.sector}
                        </td>
                        <td className="py-3 px-4 text-slate-300">
                          {stock.sub_industry}
                        </td>
                        <td className="py-3 px-4">
                          {getTierBadge(stock.market_cap_tier)}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => openImportModal(stock.symbol)}
                              leftIcon={<Plus className="h-3.5 w-3.5 text-blue-400" />}
                              title="加入自选清单"
                            >
                              加入自选
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => navigate(`/research?symbol=${stock.symbol}`)}
                              leftIcon={<ArrowRight className="h-3.5 w-3.5 text-slate-400" />}
                              title="查看深度研报"
                              aria-label="查看深度研报"
                            />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* AI Stock Research Cards Section */}
          <div className="space-y-4 pt-2">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-1">
              <div className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-indigo-400" />
                <h4 className="text-base font-bold text-white">
                  AI 深度单股投研卡片（受 Facts 事实严谨约束）
                </h4>
              </div>

              {activeCardsResponse && (
                <div className="flex items-center gap-2">
                  <AIPromptVersionBadge
                    model="gemini-2.0-flash"
                    promptVersion={activeCardsResponse.prompt_version}
                  />
                  <DataFreshnessTag asOf={activeCardsResponse.as_of} />
                </div>
              )}
            </div>

            {isGeneratingCards ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="p-5 rounded-xl border border-slate-800 bg-slate-900/60 space-y-4">
                    <div className="flex justify-between items-center">
                      <Skeleton className="h-6 w-24" />
                      <Skeleton className="h-4 w-32" />
                    </div>
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-20 w-full" />
                    <Skeleton className="h-16 w-full" />
                  </div>
                ))}
              </div>
            ) : !activeCardsResponse || !activeCardsResponse.cards || activeCardsResponse.cards.length === 0 ? (
              <div className="p-10 rounded-xl border border-slate-800 bg-slate-900/50 text-center space-y-3">
                <Lightbulb className="h-8 w-8 text-amber-400 mx-auto" />
                <p className="text-sm font-semibold text-slate-300">
                  当前主题尚未生成 AI 单股投研卡片
                </p>
                <p className="text-xs text-slate-500 max-w-md mx-auto">
                  点击上方「生成 / 刷新 AI 投研卡片」，系统将基于财报底座事实 Facts 自动提炼商业模式、财务亮点与核心风险。
                </p>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={handleGenerateCards}
                  leftIcon={<Sparkles className="h-3.5 w-3.5" />}
                >
                  立即生成 AI 卡片
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {activeCardsResponse.cards.map((card) => (
                  <div
                    key={card.symbol}
                    className="p-5 rounded-xl border border-slate-800 bg-slate-900/90 shadow-md space-y-4 hover:border-slate-700 transition-all flex flex-col justify-between"
                  >
                    <div className="space-y-3.5">
                      {/* Card Header */}
                      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                        <div className="flex items-center gap-2.5">
                          <span className="text-lg font-mono font-extrabold text-white">
                            {card.symbol}
                          </span>
                          <span className="text-xs text-slate-400 font-medium">
                            {card.name}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => openImportModal(card.symbol)}
                            leftIcon={<Plus className="h-3.5 w-3.5 text-blue-400" />}
                            title="加入自选清单"
                          >
                            加自选
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => navigate(`/research?symbol=${card.symbol}`)}
                            leftIcon={<ExternalLink className="h-3.5 w-3.5 text-slate-400" />}
                            title="查看研报"
                            aria-label="查看研报"
                          />
                        </div>
                      </div>

                      {/* One Line Intro */}
                      <div className="p-2.5 rounded-lg bg-blue-950/30 border border-blue-900/40 text-xs text-blue-200 leading-relaxed font-medium">
                        {card.one_line_intro}
                      </div>

                      {/* Why Watch */}
                      <div className="space-y-1">
                        <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-400">
                          <Zap className="h-3.5 w-3.5 shrink-0" />
                          <span>核心看点与关注理由</span>
                        </div>
                        <p className="text-xs text-slate-300 leading-relaxed pl-5">
                          {card.why_watch}
                        </p>
                      </div>

                      {/* Financial Strengths */}
                      <div className="space-y-1.5">
                        <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-400">
                          <Check className="h-3.5 w-3.5 shrink-0" />
                          <span>财务亮点（代码级 Facts 真实溯源）</span>
                        </div>
                        <ul className="space-y-1 pl-5">
                          {card.financial_strengths.map((str, idx) => (
                            <li key={idx} className="text-xs text-slate-300 flex items-start gap-1.5">
                              <span className="text-emerald-500 font-bold">•</span>
                              <span>{str}</span>
                            </li>
                          ))}
                        </ul>
                      </div>

                      {/* Main Risks */}
                      <div className="space-y-1.5">
                        <div className="flex items-center gap-1.5 text-xs font-semibold text-rose-400">
                          <ShieldAlert className="h-3.5 w-3.5 shrink-0" />
                          <span>主要潜在风险要素</span>
                        </div>
                        <ul className="space-y-1 pl-5">
                          {card.main_risks.map((risk, idx) => (
                            <li key={idx} className="text-xs text-slate-300 flex items-start gap-1.5">
                              <span className="text-rose-500 font-bold">•</span>
                              <span>{risk}</span>
                            </li>
                          ))}
                        </ul>
                      </div>

                      {/* Suitable For */}
                      <div className="space-y-1.5">
                        <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-300">
                          <UserCheck className="h-3.5 w-3.5 shrink-0" />
                          <span>适合投资者画像</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5 pl-5">
                          {card.suitable_for.map((item, idx) => (
                            <span
                              key={idx}
                              className="px-2 py-0.5 rounded text-[11px] font-medium bg-indigo-950/50 text-indigo-200 border border-indigo-800/50"
                            >
                              {item}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* More Attractive When */}
                      <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-400 space-y-1">
                        <span className="font-semibold text-slate-300">何种情境更具吸引力：</span>
                        <p className="italic text-slate-300">{card.more_attractive_when}</p>
                      </div>
                    </div>

                    <div className="pt-3 mt-2 border-t border-slate-800 flex justify-end gap-2">
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => navigate(`/research?symbol=${card.symbol}`)}
                        leftIcon={<ArrowRight className="h-3.5 w-3.5" />}
                        className="w-full"
                      >
                        进入个股深度决策评估
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <ComplianceDisclaimer variant="card" />
        </div>
      )}

      {/* Modal: Import to Watchlist */}
      <Modal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        title={
          importStockSymbol
            ? `添加标的 ${importStockSymbol} 到自选清单`
            : `批量导入主题「${activeTheme?.name}」成分股`
        }
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-300">
            {importStockSymbol
              ? `请选择将标的 ${importStockSymbol} 添加至哪一个自选清单：`
              : `即将把主题「${activeTheme?.name}」的全部 ${activeTheme?.stocks?.length || 0} 只成分股批量添加至选定清单：`}
          </p>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-200">目标自选清单</label>
            {watchlists.length === 0 ? (
              <p className="text-xs text-amber-400">暂无自选清单，请先在「自选清单」工作台创建。</p>
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
            <Button variant="ghost" onClick={() => setIsImportModalOpen(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              disabled={watchlists.length === 0 || !targetWatchlistId}
              onClick={handleConfirmImport}
              leftIcon={<BookmarkCheck className="h-4 w-4" />}
            >
              确认导入
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ThemesView;
