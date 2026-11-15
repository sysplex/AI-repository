/**
 * 用户认证与权限管理 API 通信模块。
 * 遵循 CONTRACTS.md 与 OpenAPI 类型规范。
 */

import api, { httpClient } from './client';
import type {
  LoginRequest,
  LogoutRequest,
  PaginatedUsers,
  PasswordResetConfirm,
  PasswordResetRequest,
  RegisterRequest,
  SettingsUpdate,
  TokenPair,
  UsageResponse,
  UserPublic,
} from './types';

export const authApi = {
  /** 用户注册 */
  register(data: RegisterRequest): Promise<UserPublic> {
    return api.post<UserPublic>('/auth/register', data);
  },

  /** 登录并签发双令牌 */
  login(data: LoginRequest): Promise<TokenPair> {
    return api.post<TokenPair>('/auth/login', data);
  },

  /** 轮换刷新令牌 */
  refresh(refreshToken: string): Promise<TokenPair> {
    return api.post<TokenPair>('/auth/refresh', { refresh_token: refreshToken });
  },

  /** 登出并注销 refresh 令牌 */
  async logout(refreshToken: string): Promise<void> {
    const payload: LogoutRequest = { refresh_token: refreshToken };
    await httpClient.post('/auth/logout', payload);
  },

  /** 请求重置密码 */
  requestPasswordReset(data: PasswordResetRequest): Promise<{ status: string }> {
    return api.post<{ status: string }>('/auth/password/reset-request', data);
  },

  /** 确认重置密码 */
  async confirmPasswordReset(data: PasswordResetConfirm): Promise<void> {
    await httpClient.post('/auth/password/reset-confirm', data);
  },

  /** 获取当前登录用户信息 */
  getMe(): Promise<UserPublic> {
    return api.get<UserPublic>('/me');
  },

  /** 更新个人偏好与风险设置 */
  updateMe(data: SettingsUpdate): Promise<UserPublic> {
    return api.patch<UserPublic>('/me', data);
  },

  /** 获取当日 AI 调用用量与配额账本 */
  getUsage(): Promise<UsageResponse> {
    return api.get<UsageResponse>('/me/usage');
  },

  /** 管理员查询全量用户列表 */
  getAdminUsers(params?: { offset?: number; limit?: number }): Promise<PaginatedUsers> {
    return api.get<PaginatedUsers>('/admin/users', params as Record<string, unknown>);
  },
};

export default authApi;
