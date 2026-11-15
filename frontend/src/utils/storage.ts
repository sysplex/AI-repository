/**
 * 安全持久化存储工具。
 * 封装 localStorage，支持安全读写、类型转换及在无 localStorage 环境下的内存回退。
 */

const MEMORY_STORAGE = new Map<string, string>();

function isStorageAvailable(): boolean {
  try {
    const testKey = '__test__';
    window.localStorage.setItem(testKey, testKey);
    window.localStorage.removeItem(testKey);
    return true;
  } catch {
    return false;
  }
}

const hasLocalStorage = typeof window !== 'undefined' && isStorageAvailable();

export const storage = {
  get(key: string): string | null {
    if (hasLocalStorage) {
      return window.localStorage.getItem(key);
    }
    return MEMORY_STORAGE.get(key) ?? null;
  },

  set(key: string, value: string): void {
    if (hasLocalStorage) {
      window.localStorage.setItem(key, value);
    } else {
      MEMORY_STORAGE.set(key, value);
    }
  },

  remove(key: string): void {
    if (hasLocalStorage) {
      window.localStorage.removeItem(key);
    } else {
      MEMORY_STORAGE.delete(key);
    }
  },

  getJSON<T>(key: string): T | null {
    const val = this.get(key);
    if (!val) return null;
    try {
      return JSON.parse(val) as T;
    } catch {
      return null;
    }
  },

  setJSON<T>(key: string, value: T): void {
    this.set(key, JSON.stringify(value));
  },
};

export const AUTH_TOKEN_KEY = 'stockpilot_access_token';
export const REFRESH_TOKEN_KEY = 'stockpilot_refresh_token';
export const USER_SETTINGS_KEY = 'stockpilot_user_settings';
export const COLOR_SCHEME_KEY = 'stockpilot_color_scheme'; // 'us' (green up) | 'cn' (red up)
