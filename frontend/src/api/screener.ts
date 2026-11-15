import { api } from './client';
import type {
  ExportToResearchRequest,
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
} from './types';

export const screenerApi = {
  // ---------------------------------------------------------------------------
  // 股票池 (Universes)
  // ---------------------------------------------------------------------------
  async listUniverses(): Promise<UniverseInfo[]> {
    return api.get<UniverseInfo[]>('/universes');
  },

  // ---------------------------------------------------------------------------
  // 策略筛选任务 (Screener Runs)
  // ---------------------------------------------------------------------------
  async createScreenerRun(data: ScreenerRunCreate): Promise<ScreenerRunRead> {
    return api.post<ScreenerRunRead>('/screener/runs', data);
  },

  async getScreenerRun(id: string): Promise<ScreenerRunRead> {
    return api.get<ScreenerRunRead>(`/screener/runs/${id}`);
  },

  async listScreenerRuns(limit = 20, offset = 0): Promise<ScreenerRunRead[]> {
    return api.get<ScreenerRunRead[]>('/screener/runs', {
      limit: String(limit),
      offset: String(offset),
    });
  },

  async exportScreener(data: ExportToResearchRequest): Promise<Record<string, any>> {
    return api.post<Record<string, any>>('/screener/export', data);
  },

  // ---------------------------------------------------------------------------
  // 热门主题投资库 (Themes)
  // ---------------------------------------------------------------------------
  async listThemes(): Promise<ThemeInfo[]> {
    return api.get<ThemeInfo[]>('/themes');
  },

  async getTheme(id: string): Promise<ThemeInfo> {
    return api.get<ThemeInfo>(`/themes/${id}`);
  },

  async generateThemeCards(id: string): Promise<ThemeCardsResponse> {
    return api.post<ThemeCardsResponse>(`/themes/${id}/cards`, {});
  },

  // ---------------------------------------------------------------------------
  // 自选清单工作台 (Watchlists)
  // ---------------------------------------------------------------------------
  async listWatchlists(): Promise<WatchlistRead[]> {
    return api.get<WatchlistRead[]>('/watchlists');
  },

  async getWatchlist(id: string): Promise<WatchlistRead> {
    return api.get<WatchlistRead>(`/watchlists/${id}`);
  },

  async createWatchlist(data: WatchlistCreate): Promise<WatchlistRead> {
    return api.post<WatchlistRead>('/watchlists', data);
  },

  async updateWatchlist(id: string, data: WatchlistUpdate): Promise<WatchlistRead> {
    return api.put<WatchlistRead>(`/watchlists/${id}`, data);
  },

  async deleteWatchlist(id: string): Promise<void> {
    return api.delete<void>(`/watchlists/${id}`);
  },

  async addWatchlistItem(watchlistId: string, data: WatchlistItemCreate): Promise<WatchlistItemRead> {
    return api.post<WatchlistItemRead>(`/watchlists/${watchlistId}/items`, data);
  },

  async updateWatchlistItem(
    watchlistId: string,
    itemId: string,
    data: WatchlistItemUpdate,
  ): Promise<WatchlistItemRead> {
    return api.put<WatchlistItemRead>(`/watchlists/${watchlistId}/items/${itemId}`, data);
  },

  async removeWatchlistItem(watchlistId: string, itemId: string): Promise<void> {
    return api.delete<void>(`/watchlists/${watchlistId}/items/${itemId}`);
  },

  async exportWatchlist(
    watchlistId: string,
    targetAction: 'compare' | 'portfolio' | 'deep_research' = 'compare',
  ): Promise<Record<string, any>> {
    return api.post<Record<string, any>>(
      `/watchlists/${watchlistId}/export?target_action=${targetAction}`,
      {},
    );
  },
};

export default screenerApi;
