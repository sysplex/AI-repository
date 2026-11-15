/**
 * API 统一错误模型与解析工具。
 * 遵循 CONTRACTS.md 错误规约。
 */

import { AxiosError } from 'axios';

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

export interface ApiErrorResponse {
  error: ApiErrorDetail;
}

export class AppError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly details?: Record<string, unknown> | null;

  constructor(message: string, code = 'INTERNAL_ERROR', status = 500, details?: Record<string, unknown> | null) {
    super(message);
    this.name = 'AppError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export function parseApiError(err: unknown): AppError {
  if (err instanceof AppError) {
    return err;
  }

  if (err && typeof err === 'object' && 'isAxiosError' in err) {
    const axiosErr = err as AxiosError<ApiErrorResponse>;
    const status = axiosErr.response?.status ?? 500;
    const body = axiosErr.response?.data;

    if (body?.error) {
      let message = body.error.message || '操作失败';
      const details = body.error.details as Record<string, unknown> | undefined;
      if (details && Array.isArray(details.errors) && details.errors.length > 0) {
        const fieldMsgs = details.errors
          .map((e: { message?: string }) => e.message?.replace(/^Value error,\s*/i, ''))
          .filter(Boolean);
        if (fieldMsgs.length > 0) {
          message = fieldMsgs.join('；');
        }
      }
      return new AppError(message, body.error.code || 'UNKNOWN_ERROR', status, body.error.details);
    }

    if (status === 401) {
      return new AppError('认证已过期，请重新登录', 'UNAUTHENTICATED', 401);
    }
    if (status === 403) {
      return new AppError('暂无权限执行此操作', 'PERMISSION_DENIED', 403);
    }
    if (status === 404) {
      return new AppError('请求的资源未找到', 'NOT_FOUND', 404);
    }
    if (status === 409) {
      return new AppError('操作冲突，资源已存在或状态不匹配', 'STATE_CONFLICT', 409);
    }
    if (status === 422) {
      return new AppError('参数校验失败，请检查输入格式', 'VALIDATION_ERROR', 422);
    }
    if (status === 429) {
      return new AppError('今日 AI 配额已达上限，请明日重试或联系管理员', 'QUOTA_EXCEEDED', 429);
    }
    if (status === 503) {
      return new AppError('服务熔断保护已触发，请稍后重试', 'BUDGET_CIRCUIT_OPEN', 503);
    }

    return new AppError(axiosErr.message || '网络通信异常', 'NETWORK_ERROR', status);
  }

  if (err instanceof Error) {
    return new AppError(err.message, 'CLIENT_ERROR', 500);
  }

  return new AppError('未知系统错误', 'UNKNOWN_ERROR', 500);
}
