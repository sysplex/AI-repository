/**
 * M10: 智能提醒与通知渠道前端 API 客户端。
 */

import { api } from './client';

export type AlertType = 'price' | 'technical_signal' | 'earnings_date' | 'thesis_breaker';
export type AlertStatus = 'active' | 'triggered' | 'disabled' | 'cooldown';
export type ChannelType = 'email' | 'webhook' | 'in_app';
export type DeliveryStatus = 'sent' | 'partial' | 'failed';

export interface AlertCreate {
  symbol?: string | null;
  alert_type: AlertType;
  title: string;
  conditions: Record<string, unknown>;
  channel_ids?: string[];
  cooldown_minutes?: number;
}

export interface AlertUpdate {
  title?: string;
  conditions?: Record<string, unknown>;
  channel_ids?: string[];
  status?: AlertStatus;
  cooldown_minutes?: number;
}

export interface AlertRead {
  id: string;
  user_id: string;
  symbol: string | null;
  alert_type: AlertType;
  title: string;
  conditions: Record<string, unknown>;
  channel_ids: string[];
  status: AlertStatus;
  last_triggered_at: string | null;
  trigger_count: number;
  cooldown_minutes: number;
  created_at: string;
  updated_at: string;
}

export interface NotificationChannelCreate {
  channel_type: ChannelType;
  name: string;
  config: Record<string, unknown>;
  is_enabled?: boolean;
}

export interface NotificationChannelUpdate {
  name?: string;
  config?: Record<string, unknown>;
  is_enabled?: boolean;
}

export interface NotificationChannelRead {
  id: string;
  user_id: string;
  channel_type: ChannelType;
  name: string;
  config: Record<string, unknown>;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChannelTestResult {
  channel_id: string;
  channel_name: string;
  success: boolean;
  results: Array<Record<string, unknown>>;
}

export interface AlertHistoryRead {
  id: string;
  alert_id: string;
  user_id: string;
  symbol: string | null;
  alert_type: AlertType;
  triggered_value: Record<string, unknown>;
  message: string;
  delivery_status: DeliveryStatus;
  delivered_channels: Array<Record<string, unknown>>;
  created_at: string;
}

export interface BatchThesisBreakersRequest {
  symbol: string;
  breakers: Array<Record<string, unknown>>;
  channel_ids?: string[];
  cooldown_minutes?: number;
}

export const alertsApi = {
  // ---------------------------------------------------------------------------
  // 1. 提醒规则
  // ---------------------------------------------------------------------------
  async createAlert(data: AlertCreate): Promise<AlertRead> {
    return api.post<AlertRead>('/alerts', data);
  },

  async listAlerts(params?: {
    symbol?: string;
    alert_type?: AlertType;
    status?: AlertStatus;
    limit?: number;
    offset?: number;
  }): Promise<AlertRead[]> {
    return api.get<AlertRead[]>('/alerts', params as Record<string, unknown>);
  },

  async getAlert(id: string): Promise<AlertRead> {
    return api.get<AlertRead>(`/alerts/${id}`);
  },

  async updateAlert(id: string, data: AlertUpdate): Promise<AlertRead> {
    return api.patch<AlertRead>(`/alerts/${id}`, data);
  },

  async deleteAlert(id: string): Promise<void> {
    return api.delete<void>(`/alerts/${id}`);
  },

  async listAlertHistory(params?: {
    alert_id?: string;
    symbol?: string;
    limit?: number;
    offset?: number;
  }): Promise<AlertHistoryRead[]> {
    return api.get<AlertHistoryRead[]>('/alerts/history', params as Record<string, unknown>);
  },

  async batchCreateThesisBreakers(data: BatchThesisBreakersRequest): Promise<AlertRead[]> {
    return api.post<AlertRead[]>('/alerts/thesis-breakers', data);
  },

  // ---------------------------------------------------------------------------
  // 2. 通知渠道
  // ---------------------------------------------------------------------------
  async createChannel(data: NotificationChannelCreate): Promise<NotificationChannelRead> {
    return api.post<NotificationChannelRead>('/notification-channels', data);
  },

  async listChannels(): Promise<NotificationChannelRead[]> {
    return api.get<NotificationChannelRead[]>('/notification-channels');
  },

  async getChannel(id: string): Promise<NotificationChannelRead> {
    return api.get<NotificationChannelRead>(`/notification-channels/${id}`);
  },

  async updateChannel(
    id: string,
    data: NotificationChannelUpdate,
  ): Promise<NotificationChannelRead> {
    return api.patch<NotificationChannelRead>(`/notification-channels/${id}`, data);
  },

  async deleteChannel(id: string): Promise<void> {
    return api.delete<void>(`/notification-channels/${id}`);
  },

  async testChannel(id: string): Promise<ChannelTestResult> {
    return api.post<ChannelTestResult>(`/notification-channels/${id}/test`);
  },
};

export default alertsApi;
