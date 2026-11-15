import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  BookmarkCheck,
  Check,
  Edit2,
  ExternalLink,
  Layers,
  Plus,
  Share2,
  Star,
  Target,
  Trash2,
} from 'lucide-react';
import { screenerApi } from '../../api/screener';
import { marketApi } from '../../api/market';
import type {
  Quote,
  WatchlistCreate,
  WatchlistItemCreate,
  WatchlistItemRead,
  WatchlistItemUpdate,
  WatchlistRead,
  WatchlistUpdate,
} from '../../api/types';
import { mockDefaultWatchlists } from './mockData';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Modal } from '../../components/common/Modal';
import { Badge } from '../../components/common/Badge';
import { PriceDisplay } from '../../components/financial/PriceDisplay';
import { ChangePercent } from '../../components/financial/ChangePercent';
import { cn } from '../../utils/cn';

export const WatchlistsView: React.FC = () => {
  const navigate = useNavigate();

  // Watchlists state
  const [watchlists, setWatchlists] = useState<WatchlistRead[]>(mockDefaultWatchlists);
  const [activeWatchlistId, setActiveWatchlistId] = useState<string>(
    mockDefaultWatchlists[0]?.id || '',
  );
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});

  // Quick Add Item Form
  const [addSymbol, setAddSymbol] = useState<string>('');
  const [addNotes, setAddNotes] = useState<string>('');
  const [addTargetPrice, setAddTargetPrice] = useState<string>('');
  const [addTags, setAddTags] = useState<string>('');
  const [isAddingItem, setIsAddingItem] = useState<boolean>(false);

  // Modals state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [newListName, setNewListName] = useState<string>('');
  const [newListDesc, setNewListDesc] = useState<string>('');
  const [newListIsDefault, setNewListIsDefault] = useState<boolean>(false);

  const [isEditModalOpen, setIsEditModalOpen] = useState<boolean>(false);
  const [editListName, setEditListName] = useState<string>('');
  const [editListDesc, setEditListDesc] = useState<string>('');
  const [editListIsDefault, setEditListIsDefault] = useState<boolean>(false);

  // Edit Single Item Modal
  const [editingItem, setEditingItem] = useState<WatchlistItemRead | null>(null);
  const [editItemNotes, setEditItemNotes] = useState<string>('');
  const [editItemTargetPrice, setEditItemTargetPrice] = useState<string>('');
  const [editItemTags, setEditItemTags] = useState<string>('');

  // 409 Conflict Friendly Modal
  const [conflictSymbol, setConflictSymbol] = useState<string | null>(null);

  // Current active watchlist
  const activeWatchlist =
    watchlists.find((w) => w.id === activeWatchlistId) || watchlists[0] || null;

  // Initial load
  useEffect(() => {
    loadWatchlists();
  }, []);

  // Fetch live quotes whenever active watchlist items change
  useEffect(() => {
    if (!activeWatchlist || !activeWatchlist.items || activeWatchlist.items.length === 0) return;
    const symbols = activeWatchlist.items.map((i) => i.symbol);
    fetchQuotes(symbols);
  }, [activeWatchlistId, watchlists]);

  const loadWatchlists = async () => {
    setIsLoading(true);
    try {
      const data = await screenerApi.listWatchlists();
      if (data && data.length > 0) {
        setWatchlists(data);
        if (!activeWatchlistId || !data.some((w) => w.id === activeWatchlistId)) {
          const defaultList = data.find((w) => w.is_default) || data[0];
          setActiveWatchlistId(defaultList.id);
        }
      }
    } catch {
      // Keep mock fallback gracefully
    } finally {
      setIsLoading(false);
    }
  };

  const fetchQuotes = async (symbols: string[]) => {
    try {
      const res = await marketApi.getQuotes(symbols);
      if (res && res.length > 0) {
        const map: Record<string, Quote> = {};
        res.forEach((q) => {
          map[q.symbol.toUpperCase()] = q;
        });
        setQuotes((prev) => ({ ...prev, ...map }));
      }
    } catch {
      // Keep static or current quotes
    }
  };

  // Create Watchlist
  const handleCreateWatchlist = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newListName.trim()) return;

    const payload: WatchlistCreate = {
      name: newListName.trim(),
      description: newListDesc.trim(),
      is_default: newListIsDefault,
    };

    try {
      const created = await screenerApi.createWatchlist(payload);
      setWatchlists((prev) => {
        const next = newListIsDefault
          ? prev.map((w) => ({ ...w, is_default: false }))
          : [...prev];
        return [...next, created];
      });
      setActiveWatchlistId(created.id);
    } catch {
      // Local fallback
      const localCreated: WatchlistRead = {
        id: `wl-local-${Date.now()}`,
        user_id: 'u-local',
        name: newListName.trim(),
        description: newListDesc.trim(),
        is_default: newListIsDefault,
        items: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setWatchlists((prev) => {
        const next = newListIsDefault
          ? prev.map((w) => ({ ...w, is_default: false }))
          : [...prev];
        return [...next, localCreated];
      });
      setActiveWatchlistId(localCreated.id);
    }

    setNewListName('');
    setNewListDesc('');
    setNewListIsDefault(false);
    setIsCreateModalOpen(false);
  };

  // Update Watchlist
  const handleUpdateWatchlist = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWatchlist || !editListName.trim()) return;

    const payload: WatchlistUpdate = {
      name: editListName.trim(),
      description: editListDesc.trim(),
      is_default: editListIsDefault,
    };

    try {
      const updated = await screenerApi.updateWatchlist(activeWatchlist.id, payload);
      setWatchlists((prev) =>
        prev.map((w) => {
          if (w.id === activeWatchlist.id) return updated;
          if (editListIsDefault && w.is_default) return { ...w, is_default: false };
          return w;
        }),
      );
    } catch {
      setWatchlists((prev) =>
        prev.map((w) => {
          if (w.id === activeWatchlist.id) {
            return {
              ...w,
              name: editListName.trim(),
              description: editListDesc.trim(),
              is_default: editListIsDefault,
              updated_at: new Date().toISOString(),
            };
          }
          if (editListIsDefault && w.is_default) return { ...w, is_default: false };
          return w;
        }),
      );
    }

    setIsEditModalOpen(false);
  };

  // Delete Watchlist
  const handleDeleteWatchlist = async () => {
    if (!activeWatchlist) return;
    if (watchlists.length <= 1) {
      alert('至少保留一个自选清单，无法全部删除。');
      return;
    }
    if (!window.confirm(`确认删除自选清单「${activeWatchlist.name}」及其所有标的吗？此操作无法撤销。`)) {
      return;
    }

    try {
      await screenerApi.deleteWatchlist(activeWatchlist.id);
    } catch {
      // Local fallback
    }

    setWatchlists((prev) => {
      const remaining = prev.filter((w) => w.id !== activeWatchlist.id);
      setActiveWatchlistId(remaining[0]?.id || '');
      return remaining;
    });
  };

  // Set as Default
  const handleSetDefault = async () => {
    if (!activeWatchlist || activeWatchlist.is_default) return;
    try {
      await screenerApi.updateWatchlist(activeWatchlist.id, { is_default: true });
    } catch {
      // Local fallback
    }
    setWatchlists((prev) =>
      prev.map((w) => ({
        ...w,
        is_default: w.id === activeWatchlist.id,
      })),
    );
  };

  // Add Item to active watchlist
  const handleAddItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWatchlist || !addSymbol.trim()) return;

    const symbolUpper = addSymbol.trim().toUpperCase();

    // Check duplicate locally first (and handle 409)
    const exists = activeWatchlist.items?.some((i) => i.symbol.toUpperCase() === symbolUpper);
    if (exists) {
      setConflictSymbol(symbolUpper);
      return;
    }

    setIsAddingItem(true);
    const tags = addTags
      .split(/[,，\s]+/)
      .map((t) => t.trim())
      .filter(Boolean);

    const payload: WatchlistItemCreate = {
      symbol: symbolUpper,
      notes: addNotes.trim(),
      target_price: addTargetPrice.trim() ? parseFloat(addTargetPrice.trim()) : null,
      theme_tags: tags.length > 0 ? tags : undefined,
    };

    try {
      const createdItem = await screenerApi.addWatchlistItem(activeWatchlist.id, payload);
      setWatchlists((prev) =>
        prev.map((w) => {
          if (w.id === activeWatchlist.id) {
            return {
              ...w,
              items: [...(w.items || []), createdItem],
            };
          }
          return w;
        }),
      );
      setAddSymbol('');
      setAddNotes('');
      setAddTargetPrice('');
      setAddTags('');
      fetchQuotes([symbolUpper]);
    } catch (err: any) {
      if (err?.response?.status === 409 || err?.message?.includes('409') || err?.message?.includes('冲突')) {
        setConflictSymbol(symbolUpper);
      } else {
        // Fallback local addition if network mock
        const localItem: WatchlistItemRead = {
          id: `wli-local-${Date.now()}`,
          watchlist_id: activeWatchlist.id,
          symbol: symbolUpper,
          notes: addNotes.trim(),
          target_price: addTargetPrice.trim() || null,
          theme_tags: tags,
          created_at: new Date().toISOString(),
        };
        setWatchlists((prev) =>
          prev.map((w) => {
            if (w.id === activeWatchlist.id) {
              return {
                ...w,
                items: [...(w.items || []), localItem],
              };
            }
            return w;
          }),
        );
        setAddSymbol('');
        setAddNotes('');
        setAddTargetPrice('');
        setAddTags('');
      }
    } finally {
      setIsAddingItem(false);
    }
  };

  // Remove Item
  const handleRemoveItem = async (itemId: string) => {
    if (!activeWatchlist) return;
    try {
      await screenerApi.removeWatchlistItem(activeWatchlist.id, itemId);
    } catch {
      // Local fallback
    }

    setWatchlists((prev) =>
      prev.map((w) => {
        if (w.id === activeWatchlist.id) {
          return {
            ...w,
            items: (w.items || []).filter((i) => i.id !== itemId),
          };
        }
        return w;
      }),
    );
  };

  // Open Edit Item Modal
  const openEditItemModal = (item: WatchlistItemRead) => {
    setEditingItem(item);
    setEditItemNotes(item.notes || '');
    setEditItemTargetPrice(item.target_price ? String(item.target_price) : '');
    setEditItemTags((item.theme_tags || []).join(', '));
  };

  // Save Item Update
  const handleUpdateItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWatchlist || !editingItem) return;

    const tags = editItemTags
      .split(/[,，\s]+/)
      .map((t) => t.trim())
      .filter(Boolean);

    const payload: WatchlistItemUpdate = {
      notes: editItemNotes.trim(),
      target_price: editItemTargetPrice.trim() ? parseFloat(editItemTargetPrice.trim()) : null,
      theme_tags: tags,
    };

    try {
      const updated = await screenerApi.updateWatchlistItem(
        activeWatchlist.id,
        editingItem.id,
        payload,
      );
      setWatchlists((prev) =>
        prev.map((w) => {
          if (w.id === activeWatchlist.id) {
            return {
              ...w,
              items: (w.items || []).map((i) => (i.id === editingItem.id ? updated : i)),
            };
          }
          return w;
        }),
      );
    } catch {
      setWatchlists((prev) =>
        prev.map((w) => {
          if (w.id === activeWatchlist.id) {
            return {
              ...w,
              items: (w.items || []).map((i) => {
                if (i.id === editingItem.id) {
                  return {
                    ...i,
                    notes: editItemNotes.trim(),
                    target_price: editItemTargetPrice.trim() || null,
                    theme_tags: tags,
                  };
                }
                return i;
              }),
            };
          }
          return w;
        }),
      );
    }

    setEditingItem(null);
  };

  // Export to Research / Compare
  const handleExport = (targetAction: 'compare' | 'portfolio' | 'deep_research') => {
    if (!activeWatchlist || !activeWatchlist.items || activeWatchlist.items.length === 0) {
      alert('当前自选清单为空，请先添加标的。');
      return;
    }

    const symbols = activeWatchlist.items.map((i) => i.symbol);
    if (targetAction === 'compare') {
      navigate(`/research?tab=compare&symbols=${symbols.slice(0, 8).join(',')}`);
    } else if (targetAction === 'portfolio') {
      navigate(`/research?tab=portfolio&symbols=${symbols.slice(0, 10).join(',')}`);
    } else {
      navigate(`/research?symbol=${symbols[0]}`);
    }
  };

  return (
    <div className="space-y-6">
      {/* 409 Duplicate Alert Modal */}
      {conflictSymbol && (
        <Modal
          isOpen={!!conflictSymbol}
          onClose={() => setConflictSymbol(null)}
          title="标的已存在提示"
        >
          <div className="space-y-4">
            <div className="flex items-center gap-3 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300">
              <AlertCircle className="h-6 w-6 shrink-0 text-amber-400" />
              <div>
                <p className="font-semibold text-sm">
                  标的 <span className="font-mono font-bold text-amber-200">{conflictSymbol}</span>{' '}
                  已在当前清单中
                </p>
                <p className="text-xs text-amber-400/80 mt-0.5">
                  自选清单不允许重复添加同一标的。如需补充说明或调整目标价，可直接编辑该标的备注。
                </p>
              </div>
            </div>
            <div className="flex justify-end">
              <Button variant="secondary" onClick={() => setConflictSymbol(null)}>
                我知道了
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Top Bar: Multi-Watchlists Switcher & Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow-sm">
        <div className="flex items-center gap-2 overflow-x-auto pb-1 md:pb-0 scrollbar-none">
          <div className="flex items-center gap-1.5 shrink-0 text-xs text-slate-400 font-medium mr-2">
            <Layers className="h-4 w-4 text-blue-400" />
            <span>自选清单:</span>
          </div>
          {watchlists.map((wl) => {
            const isActive = wl.id === activeWatchlistId;
            return (
              <button
                key={wl.id}
                onClick={() => setActiveWatchlistId(wl.id)}
                className={cn(
                  'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all shrink-0',
                  isActive
                    ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20 border border-blue-500'
                    : 'bg-slate-800/80 text-slate-300 hover:bg-slate-700/80 border border-slate-700/60',
                )}
              >
                <span>{wl.name}</span>
                <span className="text-[10px] opacity-75 font-mono px-1 rounded bg-black/20">
                  {wl.items?.length || 0}
                </span>
                {wl.is_default && (
                  <span title="默认清单" className="text-amber-400">
                    <Star className="h-3 w-3 fill-amber-400" />
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {isLoading && (
            <span className="text-[11px] text-slate-500 animate-pulse font-mono">加载中...</span>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setNewListName('');
              setNewListDesc('');
              setNewListIsDefault(false);
              setIsCreateModalOpen(true);
            }}
            leftIcon={<Plus className="h-3.5 w-3.5" />}
          >
            新建清单
          </Button>

          {activeWatchlist && (
            <>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditListName(activeWatchlist.name);
                  setEditListDesc(activeWatchlist.description || '');
                  setEditListIsDefault(activeWatchlist.is_default);
                  setIsEditModalOpen(true);
                }}
                leftIcon={<Edit2 className="h-3.5 w-3.5" />}
              >
                编辑
              </Button>

              {!activeWatchlist.is_default && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleSetDefault}
                  leftIcon={<Star className="h-3.5 w-3.5" />}
                  title="设为默认自选清单"
                >
                  设为默认
                </Button>
              )}

              {watchlists.length > 1 && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                  onClick={handleDeleteWatchlist}
                  leftIcon={<Trash2 className="h-3.5 w-3.5" />}
                  title="删除当前自选清单"
                  aria-label="删除当前自选清单"
                />
              )}
            </>
          )}
        </div>
      </div>

      {/* Active Watchlist Meta Header */}
      {activeWatchlist && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-1">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-white">{activeWatchlist.name}</h2>
              {activeWatchlist.is_default && (
                <Badge variant="warning" size="sm">
                  默认关注
                </Badge>
              )}
              <span className="text-xs text-slate-400 font-mono">
                共 {activeWatchlist.items?.length || 0} 只标的
              </span>
            </div>
            {activeWatchlist.description && (
              <p className="text-xs text-slate-400 mt-1 max-w-2xl">
                {activeWatchlist.description}
              </p>
            )}
          </div>

          {/* Export Actions Bar */}
          {activeWatchlist.items && activeWatchlist.items.length > 0 && (
            <div className="flex items-center gap-2 shrink-0">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleExport('compare')}
                leftIcon={<Share2 className="h-3.5 w-3.5 text-blue-400" />}
              >
                一键多股横向对比
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleExport('portfolio')}
                leftIcon={<Layers className="h-3.5 w-3.5 text-indigo-400" />}
              >
                组合优化分析
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Quick Add Form Bar */}
      <form
        onSubmit={handleAddItem}
        className="p-4 rounded-xl border border-slate-800 bg-slate-900/40 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3 items-end"
      >
        <div className="space-y-1">
          <label className="text-[11px] font-medium text-slate-300">标的代码 *</label>
          <Input
            placeholder="例如 NVDA, AAPL"
            value={addSymbol}
            onChange={(e) => setAddSymbol(e.target.value.toUpperCase())}
            required
            className="uppercase font-mono"
          />
        </div>

        <div className="space-y-1">
          <label className="text-[11px] font-medium text-slate-300">目标监控价 ($)</label>
          <Input
            type="number"
            step="0.01"
            placeholder="例如 145.00"
            value={addTargetPrice}
            onChange={(e) => setAddTargetPrice(e.target.value)}
            className="font-mono"
          />
        </div>

        <div className="space-y-1">
          <label className="text-[11px] font-medium text-slate-300">主题标签 (逗号隔开)</label>
          <Input
            placeholder="例如 AI 芯片, 算力"
            value={addTags}
            onChange={(e) => setAddTags(e.target.value)}
          />
        </div>

        <div className="space-y-1 sm:col-span-2 md:col-span-1">
          <label className="text-[11px] font-medium text-slate-300">个人自选备注</label>
          <Input
            placeholder="例如 突破加仓, 业绩超预期"
            value={addNotes}
            onChange={(e) => setAddNotes(e.target.value)}
          />
        </div>

        <Button
          type="submit"
          variant="primary"
          isLoading={isAddingItem}
          leftIcon={<Plus className="h-4 w-4" />}
          className="w-full"
        >
          快捷加入
        </Button>
      </form>

      {/* Watchlist Items Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/80 overflow-hidden shadow-sm">
        {(!activeWatchlist?.items || activeWatchlist.items.length === 0) ? (
          <div className="p-12 text-center text-slate-400 space-y-3">
            <BookmarkCheck className="h-10 w-10 text-slate-600 mx-auto" />
            <p className="text-sm">当前自选清单中暂无标的</p>
            <p className="text-xs text-slate-500">
              您可以在上方输入代码添加，或前往「热门主题」一键导入主题成分股。
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4">标的代码</th>
                  <th className="py-3 px-4">最新现价</th>
                  <th className="py-3 px-4">当日涨跌</th>
                  <th className="py-3 px-4">目标监控价</th>
                  <th className="py-3 px-4">主题标签</th>
                  <th className="py-3 px-4 min-w-[200px]">个人备注</th>
                  <th className="py-3 px-4 text-right">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-sans">
                {activeWatchlist.items.map((item) => {
                  const quote = quotes[item.symbol.toUpperCase()];
                  const currentPrice = quote ? parseFloat(quote.price) : 150.0;
                  const changePct = quote ? parseFloat(quote.change_pct) : 1.25;
                  const targetPriceNum = item.target_price ? parseFloat(item.target_price) : null;
                  const upsidePct =
                    targetPriceNum && currentPrice > 0
                      ? ((targetPriceNum - currentPrice) / currentPrice) * 100
                      : null;

                  return (
                    <tr
                      key={item.id}
                      className="hover:bg-slate-800/40 transition-colors group"
                    >
                      {/* Symbol */}
                      <td className="py-3 px-4 font-mono">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => navigate(`/research?symbol=${item.symbol}`)}
                            className="font-bold text-white hover:text-blue-400 transition-colors flex items-center gap-1 group-hover:underline"
                          >
                            <span>{item.symbol}</span>
                            <ExternalLink className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                          </button>
                        </div>
                      </td>

                      {/* Current Price */}
                      <td className="py-3 px-4 font-mono font-medium text-white">
                        <PriceDisplay value={currentPrice} />
                      </td>

                      {/* Change % */}
                      <td className="py-3 px-4">
                        <ChangePercent value={changePct} />
                      </td>

                      {/* Target Price */}
                      <td className="py-3 px-4 font-mono">
                        {targetPriceNum ? (
                          <div className="flex flex-col">
                            <span className="text-slate-200">${targetPriceNum.toFixed(2)}</span>
                            {upsidePct !== null && (
                              <span
                                className={cn(
                                  'text-[10px]',
                                  upsidePct >= 0 ? 'text-emerald-400' : 'text-rose-400',
                                )}
                              >
                                {upsidePct >= 0 ? `+${upsidePct.toFixed(1)}%` : `${upsidePct.toFixed(1)}%`}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>

                      {/* Theme Tags */}
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1">
                          {item.theme_tags && item.theme_tags.length > 0 ? (
                            item.theme_tags.map((tag, idx) => (
                              <span
                                key={idx}
                                className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700/60"
                              >
                                {tag}
                              </span>
                            ))
                          ) : (
                            <span className="text-slate-500 text-[10px]">无标签</span>
                          )}
                        </div>
                      </td>

                      {/* Personal Notes */}
                      <td className="py-3 px-4 text-slate-300">
                        <div
                          onClick={() => openEditItemModal(item)}
                          className="cursor-pointer hover:text-blue-300 transition-colors line-clamp-2 text-xs"
                          title="点击编辑备注与目标价"
                        >
                          {item.notes || <span className="text-slate-500 italic">点击添加备注...</span>}
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => navigate(`/research?symbol=${item.symbol}`)}
                            title="查看 AI 深度研报"
                            aria-label="查看 AI 深度研报"
                            leftIcon={<Target className="h-3.5 w-3.5 text-blue-400" />}
                          />
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => openEditItemModal(item)}
                            title="编辑标的"
                            aria-label="编辑标的"
                            leftIcon={<Edit2 className="h-3.5 w-3.5 text-slate-400" />}
                          />
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleRemoveItem(item.id)}
                            title="从清单中移除"
                            aria-label="从清单中移除"
                            leftIcon={<Trash2 className="h-3.5 w-3.5 text-rose-400 hover:text-rose-300" />}
                          />
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

      {/* Modal: Create Watchlist */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title="创建新自选清单"
      >
        <form onSubmit={handleCreateWatchlist} className="space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-200">清单名称 *</label>
            <Input
              placeholder="例如：科技红利核心池"
              value={newListName}
              onChange={(e) => setNewListName(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-200">清单描述（可选）</label>
            <Input
              placeholder="说明清单定位、投资策略或跟踪周期"
              value={newListDesc}
              onChange={(e) => setNewListDesc(e.target.value)}
            />
          </div>

          <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300">
            <input
              type="checkbox"
              checked={newListIsDefault}
              onChange={(e) => setNewListIsDefault(e.target.checked)}
              className="rounded border-slate-700 bg-slate-800 text-blue-600 focus:ring-blue-500"
            />
            <span>设为默认自选清单（登录后优先展示）</span>
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" type="button" onClick={() => setIsCreateModalOpen(false)}>
              取消
            </Button>
            <Button variant="primary" type="submit">
              确认创建
            </Button>
          </div>
        </form>
      </Modal>

      {/* Modal: Edit Watchlist Metadata */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        title="修改自选清单信息"
      >
        <form onSubmit={handleUpdateWatchlist} className="space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-200">清单名称 *</label>
            <Input
              value={editListName}
              onChange={(e) => setEditListName(e.target.value)}
              required
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-200">清单描述</label>
            <Input
              value={editListDesc}
              onChange={(e) => setEditListDesc(e.target.value)}
            />
          </div>

          <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300">
            <input
              type="checkbox"
              checked={editListIsDefault}
              onChange={(e) => setEditListIsDefault(e.target.checked)}
              className="rounded border-slate-700 bg-slate-800 text-blue-600 focus:ring-blue-500"
            />
            <span>设为默认自选清单</span>
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" type="button" onClick={() => setIsEditModalOpen(false)}>
              取消
            </Button>
            <Button variant="primary" type="submit">
              保存更改
            </Button>
          </div>
        </form>
      </Modal>

      {/* Modal: Edit Item Notes & Target Price */}
      {editingItem && (
        <Modal
          isOpen={!!editingItem}
          onClose={() => setEditingItem(null)}
          title={`编辑标的备注与目标价 - ${editingItem.symbol}`}
        >
          <form onSubmit={handleUpdateItem} className="space-y-4">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-200">目标监控价 ($)</label>
              <Input
                type="number"
                step="0.01"
                placeholder="例如 150.00"
                value={editItemTargetPrice}
                onChange={(e) => setEditItemTargetPrice(e.target.value)}
                className="font-mono"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-200">主题标签（逗号隔开）</label>
              <Input
                placeholder="例如 半导体, 高成长"
                value={editItemTags}
                onChange={(e) => setEditItemTags(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-200">个人投研备注</label>
              <textarea
                rows={3}
                className="w-full rounded-lg border border-slate-700 bg-slate-900/90 px-3 py-2 text-xs text-slate-100 placeholder:text-slate-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="记录关注理由、催化剂事件、建仓止损纪律..."
                value={editItemNotes}
                onChange={(e) => setEditItemNotes(e.target.value)}
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" type="button" onClick={() => setEditingItem(null)}>
                取消
              </Button>
              <Button variant="primary" type="submit" leftIcon={<Check className="h-3.5 w-3.5" />}>
                保存
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};

export default WatchlistsView;
