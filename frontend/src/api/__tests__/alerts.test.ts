import { describe, it, expect, vi, beforeEach } from 'vitest';
import { alertsApi, AlertRead, NotificationChannelRead, AlertHistoryRead } from '../alerts';
import { httpClient } from '../client';

describe('Alerts & Channels API Client Module', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockAlert: AlertRead = {
    id: 'alt-1',
    user_id: 'u-1',
    symbol: 'AAPL',
    alert_type: 'price',
    title: 'AAPL 突破 $230',
    conditions: { direction: 'cross_above', target_price: 230 },
    channel_ids: ['ch-1'],
    status: 'active',
    last_triggered_at: null,
    trigger_count: 0,
    cooldown_minutes: 1440,
    created_at: '2026-11-17T12:00:00Z',
    updated_at: '2026-11-17T12:00:00Z',
  };

  const mockChannel: NotificationChannelRead = {
    id: 'ch-1',
    user_id: 'u-1',
    channel_type: 'webhook',
    name: '飞书群',
    config: { webhook_url: 'https://open.feishu.cn/hook' },
    is_enabled: true,
    created_at: '2026-11-17T12:00:00Z',
    updated_at: '2026-11-17T12:00:00Z',
  };

  it('createAlert posts to /alerts', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({ data: mockAlert });
    const payload = {
      symbol: 'AAPL',
      alert_type: 'price' as const,
      title: 'AAPL 突破 $230',
      conditions: { direction: 'cross_above', target_price: 230 },
    };

    const res = await alertsApi.createAlert(payload);
    expect(postSpy).toHaveBeenCalledWith('/alerts', payload);
    expect(res.id).toBe('alt-1');
  });

  it('listAlerts calls GET /alerts with filters', async () => {
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: [mockAlert] });
    const res = await alertsApi.listAlerts({ symbol: 'AAPL', alert_type: 'price' });
    expect(getSpy).toHaveBeenCalledWith('/alerts', { params: { symbol: 'AAPL', alert_type: 'price' } });
    expect(res).toHaveLength(1);
  });

  it('getAlert calls GET /alerts/:id', async () => {
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockAlert });
    const res = await alertsApi.getAlert('alt-1');
    expect(getSpy).toHaveBeenCalledWith('/alerts/alt-1', { params: undefined });
    expect(res.id).toBe('alt-1');
  });

  it('updateAlert calls PATCH /alerts/:id', async () => {
    const patchSpy = vi.spyOn(httpClient, 'patch').mockResolvedValueOnce({ data: { ...mockAlert, status: 'disabled' } });
    const res = await alertsApi.updateAlert('alt-1', { status: 'disabled' });
    expect(patchSpy).toHaveBeenCalledWith('/alerts/alt-1', { status: 'disabled' });
    expect(res.status).toBe('disabled');
  });

  it('deleteAlert calls DELETE /alerts/:id', async () => {
    const delSpy = vi.spyOn(httpClient, 'delete').mockResolvedValueOnce({ data: undefined });
    await alertsApi.deleteAlert('alt-1');
    expect(delSpy).toHaveBeenCalledWith('/alerts/alt-1');
  });

  it('listAlertHistory calls GET /alerts/history', async () => {
    const mockHist: AlertHistoryRead = {
      id: 'h-1',
      alert_id: 'alt-1',
      user_id: 'u-1',
      symbol: 'AAPL',
      alert_type: 'price',
      triggered_value: { current_price: 231 },
      message: 'AAPL 价格突破',
      delivery_status: 'sent',
      delivered_channels: [],
      created_at: '2026-11-17T12:00:00Z',
    };
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: [mockHist] });
    const res = await alertsApi.listAlertHistory({ symbol: 'AAPL' });
    expect(getSpy).toHaveBeenCalledWith('/alerts/history', { params: { symbol: 'AAPL' } });
    expect(res).toHaveLength(1);
  });

  it('batchCreateThesisBreakers posts to /alerts/thesis-breakers', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({ data: [mockAlert] });
    const req = { symbol: 'AAPL', breakers: [{ metric: 'gross_margin', threshold: 0.4 }] };
    const res = await alertsApi.batchCreateThesisBreakers(req);
    expect(postSpy).toHaveBeenCalledWith('/alerts/thesis-breakers', req);
    expect(res).toHaveLength(1);
  });

  it('channel CRUD and testChannel work correctly', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({ data: mockChannel });
    const c1 = await alertsApi.createChannel({ channel_type: 'webhook', name: '飞书群', config: {} });
    expect(postSpy).toHaveBeenCalledWith('/notification-channels', expect.any(Object));
    expect(c1.id).toBe('ch-1');

    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: [mockChannel] });
    const list = await alertsApi.listChannels();
    expect(getSpy).toHaveBeenCalledWith('/notification-channels', { params: undefined });
    expect(list).toHaveLength(1);

    const testSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({
      data: { channel_id: 'ch-1', channel_name: '飞书群', success: true, results: [] },
    });
    const testRes = await alertsApi.testChannel('ch-1');
    expect(testSpy).toHaveBeenCalledWith('/notification-channels/ch-1/test', undefined);
    expect(testRes.success).toBe(true);

    const delSpy = vi.spyOn(httpClient, 'delete').mockResolvedValueOnce({ data: undefined });
    await alertsApi.deleteChannel('ch-1');
    expect(delSpy).toHaveBeenCalledWith('/notification-channels/ch-1');
  });
});
