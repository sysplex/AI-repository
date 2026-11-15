import { describe, it, expect, vi, beforeEach } from 'vitest';
import authApi from '../auth';
import { httpClient } from '../client';
import type { LoginRequest, RegisterRequest, TokenPair, UsageResponse, UserPublic } from '../types';

describe('Auth API Client Module', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('correctly dispatches login request', async () => {
    const mockTokenPair: TokenPair = {
      access_token: 'mock_access_token_123',
      refresh_token: 'mock_refresh_token_456',
      token_type: 'bearer',
      expires_in: 3600,
    };

    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({
      data: mockTokenPair,
    });

    const payload: LoginRequest = { email: 'user@example.com', password: 'password123' };
    const res = await authApi.login(payload);

    expect(postSpy).toHaveBeenCalledWith('/auth/login', payload);
    expect(res.access_token).toBe('mock_access_token_123');
    expect(res.refresh_token).toBe('mock_refresh_token_456');
  });

  it('correctly dispatches register request', async () => {
    const mockUser: UserPublic = {
      id: '11111111-1111-1111-1111-111111111111',
      email: 'newuser@example.com',
      role: 'user',
      status: 'active',
      settings: {
        risk_profile: 'balanced',
        language: 'zh-CN',
      },
      created_at: '2026-11-15T10:00:00Z',
    };

    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({
      data: mockUser,
    });

    const payload: RegisterRequest = {
      email: 'newuser@example.com',
      password: 'password123',
      settings: { risk_profile: 'balanced', language: 'zh-CN' },
    };
    const res = await authApi.register(payload);

    expect(postSpy).toHaveBeenCalledWith('/auth/register', payload);
    expect(res.id).toBe(mockUser.id);
    expect(res.email).toBe(mockUser.email);
  });

  it('correctly dispatches getMe request', async () => {
    const mockUser: UserPublic = {
      id: '22222222-2222-2222-2222-222222222222',
      email: 'me@example.com',
      role: 'admin',
      status: 'active',
      settings: { risk_profile: 'aggressive', language: 'zh-CN' },
      created_at: '2026-11-15T10:00:00Z',
    };

    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({
      data: mockUser,
    });

    const res = await authApi.getMe();
    expect(getSpy).toHaveBeenCalledWith('/me', { params: undefined });
    expect(res.role).toBe('admin');
  });

  it('correctly dispatches updateMe request', async () => {
    const updatedUser: UserPublic = {
      id: '22222222-2222-2222-2222-222222222222',
      email: 'me@example.com',
      role: 'user',
      status: 'active',
      settings: { risk_profile: 'conservative', language: 'en' },
      created_at: '2026-11-15T10:00:00Z',
    };

    const patchSpy = vi.spyOn(httpClient, 'patch').mockResolvedValueOnce({
      data: updatedUser,
    });

    const res = await authApi.updateMe({
      settings: { risk_profile: 'conservative', language: 'en' },
    });
    expect(patchSpy).toHaveBeenCalledWith('/me', {
      settings: { risk_profile: 'conservative', language: 'en' },
    });
    expect(res.settings?.risk_profile).toBe('conservative');
  });

  it('correctly dispatches getUsage request', async () => {
    const mockUsage: UsageResponse = {
      usage_date: '2026-11-15',
      calls: 4,
      tokens_in: 1200,
      tokens_out: 800,
      quota_used: 4,
      quota: 20,
      cost_usd: '0.0420',
    };

    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({
      data: mockUsage,
    });

    const res = await authApi.getUsage();
    expect(getSpy).toHaveBeenCalledWith('/me/usage', { params: undefined });
    expect(res.quota_used).toBe(4);
    expect(res.quota).toBe(20);
  });

  it('correctly handles password reset workflow', async () => {
    const postSpy = vi.spyOn(httpClient, 'post');

    postSpy.mockResolvedValueOnce({ data: { status: 'accepted' } });
    const reqRes = await authApi.requestPasswordReset({ email: 'user@example.com' });
    expect(reqRes.status).toBe('accepted');

    postSpy.mockResolvedValueOnce({ data: {} });
    await authApi.confirmPasswordReset({ token: 'tok_123', new_password: 'new_pwd_888' });
    expect(postSpy).toHaveBeenCalledWith('/auth/password/reset-confirm', {
      token: 'tok_123',
      new_password: 'new_pwd_888',
    });
  });
});
