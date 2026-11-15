import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screenerApi } from '../screener';
import { httpClient } from '../client';
import type {
  ScreenerRunCreate,
  ScreenerRunRead,
  ThemeCardsResponse,
  ThemeInfo,
  UniverseInfo,
  WatchlistCreate,
  WatchlistItemCreate,
  WatchlistItemRead,
  WatchlistItemUpdate,
  WatchlistRead,
  WatchlistUpdate,
} from '../types';

describe('Screener, Themes & Watchlists API Client Module', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  // 1. Universes
  it('listUniverses calls GET /universes', async () => {
    const mockUniverses: UniverseInfo[] = [
      { id: 'sp500', name: 'S&P 500', description: 'Large cap', symbol_count: 500 },
    ];
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockUniverses });

    const res = await screenerApi.listUniverses();
    expect(getSpy).toHaveBeenCalledWith('/universes', { params: undefined });
    expect(res).toEqual(mockUniverses);
  });

  // 2. Screener Runs
  it('createScreenerRun posts payload to /screener/runs', async () => {
    const payload: ScreenerRunCreate = {
      universe: 'sp500',
      strategy_id: 'trend_following',
      params: { period: 20 },
    };
    const mockRun: ScreenerRunRead = {
      id: 'run-001',
      user_id: 'u-1',
      universe: 'sp500',
      strategy_id: 'trend_following',
      params: { period: 20 },
      status: 'pending',
      total_symbols: 500,
      matched_count: 0,
      failed_count: 0,
      created_at: '2026-11-15T12:00:00Z',
    };
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({ data: mockRun });

    const res = await screenerApi.createScreenerRun(payload);
    expect(postSpy).toHaveBeenCalledWith('/screener/runs', payload);
    expect(res.id).toBe('run-001');
  });

  it('getScreenerRun calls GET /screener/runs/{id}', async () => {
    const mockRun: ScreenerRunRead = {
      id: 'run-001',
      user_id: 'u-1',
      universe: 'sp500',
      strategy_id: 'trend_following',
      params: {},
      status: 'succeeded',
      total_symbols: 500,
      matched_count: 5,
      failed_count: 0,
      created_at: '2026-11-15T12:00:00Z',
    };
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockRun });

    const res = await screenerApi.getScreenerRun('run-001');
    expect(getSpy).toHaveBeenCalledWith('/screener/runs/run-001', { params: undefined });
    expect(res.status).toBe('succeeded');
  });

  it('listScreenerRuns calls GET /screener/runs with limit and offset', async () => {
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: [] });

    await screenerApi.listScreenerRuns(10, 20);
    expect(getSpy).toHaveBeenCalledWith('/screener/runs', {
      params: { limit: '10', offset: '20' },
    });
  });

  it('exportScreener calls POST /screener/export', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({ data: { success: true } });

    const res = await screenerApi.exportScreener({
      symbols: ['NVDA', 'AAPL'],
      target_action: 'compare',
    });
    expect(postSpy).toHaveBeenCalledWith('/screener/export', {
      symbols: ['NVDA', 'AAPL'],
      target_action: 'compare',
    });
    expect(res.success).toBe(true);
  });

  // 3. Themes & Cards
  it('listThemes calls GET /themes', async () => {
    const mockThemes: ThemeInfo[] = [
      { id: 'ai_chips', name: 'AI Chips', category: 'tech', tagline: 'Power of AI', description: 'Chips' },
    ];
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockThemes });

    const res = await screenerApi.listThemes();
    expect(getSpy).toHaveBeenCalledWith('/themes', { params: undefined });
    expect(res[0].id).toBe('ai_chips');
  });

  it('getTheme calls GET /themes/{id}', async () => {
    const mockTheme: ThemeInfo = {
      id: 'ai_chips',
      name: 'AI Chips',
      category: 'tech',
      tagline: 'Power',
      description: 'Desc',
    };
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockTheme });

    const res = await screenerApi.getTheme('ai_chips');
    expect(getSpy).toHaveBeenCalledWith('/themes/ai_chips', { params: undefined });
    expect(res.name).toBe('AI Chips');
  });

  it('generateThemeCards calls POST /themes/{id}/cards', async () => {
    const mockResponse: ThemeCardsResponse = {
      theme_id: 'ai_chips',
      theme_name: 'AI Chips',
      as_of: '2026-11-15T12:00:00Z',
      prompt_version: 'v2.4.0',
      cards: [],
    };
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({ data: mockResponse });

    const res = await screenerApi.generateThemeCards('ai_chips');
    expect(postSpy).toHaveBeenCalledWith('/themes/ai_chips/cards', {});
    expect(res.theme_id).toBe('ai_chips');
  });

  // 4. Watchlists CRUD
  it('listWatchlists calls GET /watchlists', async () => {
    const mockWatchlists: WatchlistRead[] = [
      {
        id: 'wl-1',
        user_id: 'u-1',
        name: 'My Watchlist',
        description: 'Default',
        is_default: true,
        items: [],
        created_at: '2026-11-15T12:00:00Z',
        updated_at: '2026-11-15T12:00:00Z',
      },
    ];
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockWatchlists });

    const res = await screenerApi.listWatchlists();
    expect(getSpy).toHaveBeenCalledWith('/watchlists', { params: undefined });
    expect(res[0].name).toBe('My Watchlist');
  });

  it('createWatchlist posts payload to /watchlists', async () => {
    const payload: WatchlistCreate = {
      name: 'Tech Growth',
      description: 'Semis & Cloud',
      is_default: false,
    };
    const mockCreated: WatchlistRead = {
      id: 'wl-2',
      user_id: 'u-1',
      name: 'Tech Growth',
      description: 'Semis & Cloud',
      is_default: false,
      items: [],
      created_at: '2026-11-15T12:00:00Z',
      updated_at: '2026-11-15T12:00:00Z',
    };
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({ data: mockCreated });

    const res = await screenerApi.createWatchlist(payload);
    expect(postSpy).toHaveBeenCalledWith('/watchlists', payload);
    expect(res.id).toBe('wl-2');
  });

  it('updateWatchlist puts payload to /watchlists/{id}', async () => {
    const payload: WatchlistUpdate = { name: 'Renamed Watchlist' };
    const mockUpdated: WatchlistRead = {
      id: 'wl-1',
      user_id: 'u-1',
      name: 'Renamed Watchlist',
      description: '',
      is_default: true,
      items: [],
      created_at: '2026-11-15T12:00:00Z',
      updated_at: '2026-11-15T12:00:00Z',
    };
    const putSpy = vi.spyOn(httpClient, 'put').mockResolvedValueOnce({ data: mockUpdated });

    const res = await screenerApi.updateWatchlist('wl-1', payload);
    expect(putSpy).toHaveBeenCalledWith('/watchlists/wl-1', payload);
    expect(res.name).toBe('Renamed Watchlist');
  });

  it('deleteWatchlist calls DELETE /watchlists/{id}', async () => {
    const deleteSpy = vi.spyOn(httpClient, 'delete').mockResolvedValueOnce({ data: null });

    await screenerApi.deleteWatchlist('wl-1');
    expect(deleteSpy).toHaveBeenCalledWith('/watchlists/wl-1');
  });

  // 5. Watchlist Items CRUD & Export
  it('addWatchlistItem posts payload to /watchlists/{id}/items', async () => {
    const payload: WatchlistItemCreate = {
      symbol: 'NVDA',
      notes: 'AI Leader',
      target_price: 150,
      theme_tags: ['AI'],
    };
    const mockItem: WatchlistItemRead = {
      id: 'item-1',
      watchlist_id: 'wl-1',
      symbol: 'NVDA',
      notes: 'AI Leader',
      target_price: '150.00',
      theme_tags: ['AI'],
      created_at: '2026-11-15T12:00:00Z',
    };
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({ data: mockItem });

    const res = await screenerApi.addWatchlistItem('wl-1', payload);
    expect(postSpy).toHaveBeenCalledWith('/watchlists/wl-1/items', payload);
    expect(res.symbol).toBe('NVDA');
  });

  it('updateWatchlistItem puts payload to /watchlists/{id}/items/{itemId}', async () => {
    const payload: WatchlistItemUpdate = { notes: 'Updated note' };
    const mockItem: WatchlistItemRead = {
      id: 'item-1',
      watchlist_id: 'wl-1',
      symbol: 'NVDA',
      notes: 'Updated note',
      target_price: '150.00',
      theme_tags: ['AI'],
      created_at: '2026-11-15T12:00:00Z',
    };
    const putSpy = vi.spyOn(httpClient, 'put').mockResolvedValueOnce({ data: mockItem });

    const res = await screenerApi.updateWatchlistItem('wl-1', 'item-1', payload);
    expect(putSpy).toHaveBeenCalledWith('/watchlists/wl-1/items/item-1', payload);
    expect(res.notes).toBe('Updated note');
  });

  it('removeWatchlistItem calls DELETE /watchlists/{id}/items/{itemId}', async () => {
    const deleteSpy = vi.spyOn(httpClient, 'delete').mockResolvedValueOnce({ data: null });

    await screenerApi.removeWatchlistItem('wl-1', 'item-1');
    expect(deleteSpy).toHaveBeenCalledWith('/watchlists/wl-1/items/item-1');
  });

  it('exportWatchlist calls POST /watchlists/{id}/export with target_action', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({ data: { exported: true } });

    const res = await screenerApi.exportWatchlist('wl-1', 'compare');
    expect(postSpy).toHaveBeenCalledWith('/watchlists/wl-1/export?target_action=compare', {});
    expect(res.exported).toBe(true);
  });
});
