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
  public readonly requestId?: string;

  constructor(
    message: string,
    code = 'INTERNAL_ERROR',
    status = 500,
    details?: Record<string, unknown> | null,
    requestId?: string
  ) {
    super(message);
    this.name = 'AppError';
    this.code = code;
    this.status = status;
    this.details = details;
    this.requestId = requestId;
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
    const requestId =
      (axiosErr.response?.headers?.['x-request-id'] as string | undefined) ||
      (axiosErr.config?.headers?.['X-Request-ID'] as string | undefined);

    if (body?.error) {
      let message = body.error.message || '操作失败';
      const details = (body.error.details as Record<string, unknown> | undefined) || {};
      if (Array.isArray(details.errors) && details.errors.length > 0) {
        const fieldMsgs = details.errors
          .map((e: { message?: string }) => e.message?.replace(/^Value error,\s*/i, ''))
          .filter(Boolean);
        if (fieldMsgs.length > 0) {
          message = fieldMsgs.join('；');
        }
      }
      return new AppError(
        message,
        body.error.code || 'UNKNOWN_ERROR',
        status,
        { ...details, request_id: requestId },
        requestId
      );
    }

    if (status === 401) {
      return new AppError('认证已过期，请重新登录', 'UNAUTHENTICATED', 401, { request_id: requestId }, requestId);
    }
    if (status === 403) {
      return new AppError('暂无权限执行此操作', 'PERMISSION_DENIED', 403, { request_id: requestId }, requestId);
    }
    if (status === 404) {
      return new AppError('请求的资源未找到', 'NOT_FOUND', 404, { request_id: requestId }, requestId);
    }
    if (status === 409) {
      return new AppError('操作冲突，资源已存在或状态不匹配', 'STATE_CONFLICT', 409, { request_id: requestId }, requestId);
    }
    if (status === 422) {
      return new AppError('参数校验失败，请检查输入格式', 'VALIDATION_ERROR', 422, { request_id: requestId }, requestId);
    }
    if (status === 429) {
      return new AppError('今日 AI 配额已达上限，请明日重试或联系管理员', 'QUOTA_EXCEEDED', 429, { request_id: requestId }, requestId);
    }
    if (status === 503) {
      return new AppError('服务熔断保护已触发，请稍后重试', 'BUDGET_CIRCUIT_OPEN', 503, { request_id: requestId }, requestId);
    }

    return new AppError(axiosErr.message || '网络通信异常', 'NETWORK_ERROR', status, { request_id: requestId }, requestId);
  }

  if (err instanceof Error) {
    return new AppError(err.message, 'CLIENT_ERROR', 500);
  }

  return new AppError('未知系统错误', 'UNKNOWN_ERROR', 500);
}
