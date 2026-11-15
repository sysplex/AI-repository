/**
 * 统一前端 HTTP 客户端。
 * 遵循 CONTRACTS.md 规范：
 * - 自动携带 Bearer Token；
 * - 401 拦截并尝试静默刷新令牌，失效触发登出；
 * - 统一捕获与解析后端错误结构，包装为 AppError；
 * - 自动附带 X-Request-ID。
 */

import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { AUTH_TOKEN_KEY, REFRESH_TOKEN_KEY, storage } from '../utils/storage';
import { parseApiError } from '../utils/errors';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export const httpClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

const processQueue = (err: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (token) {
      prom.resolve(token);
    } else {
      prom.reject(err);
    }
  });
  failedQueue = [];
};

// =============================================================================
// 1. 请求拦截器
// =============================================================================
httpClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = storage.get(AUTH_TOKEN_KEY);
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // 生成或补充 X-Request-ID 链路追踪
    if (config.headers && !config.headers['X-Request-ID']) {
      config.headers['X-Request-ID'] = `req_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    }

    return config;
  },
  (error) => {
    return Promise.reject(parseApiError(error));
  }
);

// =============================================================================
// 2. 响应拦截器
// =============================================================================
httpClient.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;

    // 401 未认证且未重试过：尝试静默刷新令牌
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      // 避免登录和刷新接口本身的 401 死循环
      if (originalRequest.url?.includes('/auth/login') || originalRequest.url?.includes('/auth/refresh')) {
        return Promise.reject(parseApiError(error));
      }

      const refreshToken = storage.get(REFRESH_TOKEN_KEY);
      if (!refreshToken) {
        storage.remove(AUTH_TOKEN_KEY);
        window.dispatchEvent(new CustomEvent('auth:unauthorized'));
        return Promise.reject(parseApiError(error));
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              if (originalRequest.headers) {
                originalRequest.headers.Authorization = `Bearer ${token}`;
              }
              resolve(httpClient(originalRequest));
            },
            reject: (err: unknown) => {
              reject(err);
            },
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const refreshResponse = await axios.post<{ access_token: string; refresh_token?: string }>(
          `${API_BASE_URL}/auth/refresh`,
          { refresh_token: refreshToken }
        );

        const newAccessToken = refreshResponse.data.access_token;
        storage.set(AUTH_TOKEN_KEY, newAccessToken);
        if (refreshResponse.data.refresh_token) {
          storage.set(REFRESH_TOKEN_KEY, refreshResponse.data.refresh_token);
        }

        processQueue(null, newAccessToken);

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        }
        return httpClient(originalRequest);
      } catch (refreshErr) {
        processQueue(refreshErr, null);
        storage.remove(AUTH_TOKEN_KEY);
        storage.remove(REFRESH_TOKEN_KEY);
        window.dispatchEvent(new CustomEvent('auth:unauthorized'));
        return Promise.reject(parseApiError(refreshErr));
      } finally {
        isRefreshing = false;
      }
    }

    if (error.response?.status === 429) {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('api:quota_exceeded', { detail: error.response.data }));
      }
    } else if (error.response?.status === 503) {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('api:circuit_breaker', { detail: error.response.data }));
      }
    }

    return Promise.reject(parseApiError(error));
  }
);

// =============================================================================
// 3. 类型安全的快捷方法
// =============================================================================
export const api = {
  get<T>(url: string, params?: Record<string, unknown>) {
    return httpClient.get<T>(url, { params }).then((res) => res.data);
  },

  post<T>(url: string, data?: unknown) {
    return httpClient.post<T>(url, data).then((res) => res.data);
  },

  put<T>(url: string, data?: unknown) {
    return httpClient.put<T>(url, data).then((res) => res.data);
  },

  patch<T>(url: string, data?: unknown) {
    return httpClient.patch<T>(url, data).then((res) => res.data);
  },

  delete<T>(url: string) {
    return httpClient.delete<T>(url).then((res) => res.data);
  },
};

export default api;
