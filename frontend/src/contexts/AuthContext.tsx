import React, { createContext, useCallback, useEffect, useState } from 'react';
import authApi from '../api/auth';
import type { LoginRequest, RegisterRequest, UserPublic } from '../api/types';
import { AUTH_TOKEN_KEY, COLOR_SCHEME_KEY, REFRESH_TOKEN_KEY, storage } from '../utils/storage';

export interface AuthContextType {
  user: UserPublic | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<UserPublic>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  colorScheme: 'us' | 'cn';
  setColorScheme: (scheme: 'us' | 'cn') => void;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [token, setToken] = useState<string | null>(() => storage.get(AUTH_TOKEN_KEY));
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [colorScheme, setColorSchemeState] = useState<'us' | 'cn'>(() => {
    return (storage.get(COLOR_SCHEME_KEY) as 'us' | 'cn') || 'us';
  });

  const setColorScheme = useCallback((scheme: 'us' | 'cn') => {
    setColorSchemeState(scheme);
    storage.set(COLOR_SCHEME_KEY, scheme);
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const profile = await authApi.getMe();
      setUser(profile);
    } catch {
      setUser(null);
      storage.remove(AUTH_TOKEN_KEY);
      storage.remove(REFRESH_TOKEN_KEY);
      setToken(null);
    }
  }, []);

  // 应用初始化时校验与恢复用户会话
  useEffect(() => {
    const initAuth = async () => {
      const storedToken = storage.get(AUTH_TOKEN_KEY);
      if (storedToken) {
        setToken(storedToken);
        await refreshUser();
      }
      setIsLoading(false);
    };

    void initAuth();

    // 监听全局未授权登出事件（来自 HTTP 拦截器）
    const handleUnauthorized = () => {
      setUser(null);
      setToken(null);
      storage.remove(AUTH_TOKEN_KEY);
      storage.remove(REFRESH_TOKEN_KEY);
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => {
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, [refreshUser]);

  const login = useCallback(
    async (credentials: LoginRequest) => {
      setIsLoading(true);
      try {
        const tokens = await authApi.login(credentials);
        storage.set(AUTH_TOKEN_KEY, tokens.access_token);
        storage.set(REFRESH_TOKEN_KEY, tokens.refresh_token);
        setToken(tokens.access_token);

        const profile = await authApi.getMe();
        setUser(profile);
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const register = useCallback(async (data: RegisterRequest) => {
    return authApi.register(data);
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = storage.get(REFRESH_TOKEN_KEY);
    if (refreshToken) {
      try {
        await authApi.logout(refreshToken);
      } catch {
        // 登出清理保证幂等忽略网络失败
      }
    }
    storage.remove(AUTH_TOKEN_KEY);
    storage.remove(REFRESH_TOKEN_KEY);
    setUser(null);
    setToken(null);
  }, []);

  const isAuthenticated = !!user;
  const isAdmin = user?.role === 'admin';

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated,
        isAdmin,
        login,
        register,
        logout,
        refreshUser,
        colorScheme,
        setColorScheme,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
