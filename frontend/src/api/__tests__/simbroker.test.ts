import { describe, it, expect, vi, beforeEach } from 'vitest';
import { simbrokerApi } from '../simbroker';
import { httpClient } from '../client';
import type {
  AccountCreate,
  AccountOverview,
  AccountResponse,
  OrderCreate,
  OrderResponse,
  PerformanceMetrics,
  PositionResponse,
  RiskOverview,
  TradeJournalResponse,
  TradeJournalUpdate,
  TradeResponse,
} from '../types';

describe('SimBroker API Client Module', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockAccResponse: AccountResponse = {
    id: 'acc-1',
    user_id: 'u-1',
    name: 'Test Sim Account',
    initial_cash: '100000.00',
    cash: '100000.00',
    fee_model: {
      type: 'bps',
      per_share: '0.005',
      bps: '2.0',
      min_fee: '1.00',
    },
    slippage_bps: '5.0',
    pdt_enabled: true,
    status: 'active',
    created_at: '2026-11-15T12:00:00Z',
    updated_at: '2026-11-15T12:00:00Z',
  };

  it('createAccount posts payload to /sim/accounts', async () => {
    const payload: AccountCreate = {
      name: 'Test Sim Account',
      initial_cash: 100000,
      slippage_bps: 5.0,
      pdt_enabled: true,
    };
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({ data: mockAccResponse });

    const res = await simbrokerApi.createAccount(payload);
    expect(postSpy).toHaveBeenCalledWith('/sim/accounts', payload);
    expect(res.id).toBe('acc-1');
  });

  it('listAccounts calls GET /sim/accounts', async () => {
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: [mockAccResponse] });

    const res = await simbrokerApi.listAccounts();
    expect(getSpy).toHaveBeenCalledWith('/sim/accounts', { params: undefined });
    expect(res).toHaveLength(1);
  });

  it('getAccountOverview calls GET /sim/accounts/{accountId}', async () => {
    const mockOverview: AccountOverview = {
      id: 'acc-1',
      name: 'Test Sim Account',
      status: 'active',
      initial_cash: '100000.00',
      cash: '80000.00',
      market_value: '25000.00',
      equity: '105000.00',
      daily_pnl: '1200.00',
      daily_pnl_pct: '1.15',
      total_pnl: '5000.00',
      total_pnl_pct: '5.00',
      pdt_day_trades_count: 1,
      pdt_warning: false,
    };
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockOverview });

    const res = await simbrokerApi.getAccountOverview('acc-1');
    expect(getSpy).toHaveBeenCalledWith('/sim/accounts/acc-1', { params: undefined });
    expect(res.equity).toBe('105000.00');
  });

  it('deposit posts payload to /sim/accounts/{accountId}/deposit', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({
      data: { account_id: 'acc-1', cash: '110000.00' },
    });

    const res = await simbrokerApi.deposit('acc-1', 10000);
    expect(postSpy).toHaveBeenCalledWith('/sim/accounts/acc-1/deposit', { amount: 10000 });
    expect(res.cash).toBe('110000.00');
  });

  it('withdraw posts payload to /sim/accounts/{accountId}/withdraw', async () => {
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({
      data: { account_id: 'acc-1', cash: '90000.00' },
    });

    const res = await simbrokerApi.withdraw('acc-1', 10000);
    expect(postSpy).toHaveBeenCalledWith('/sim/accounts/acc-1/withdraw', { amount: 10000 });
    expect(res.cash).toBe('90000.00');
  });

  it('submitOrder posts order to /sim/accounts/{accountId}/orders with Idempotency-Key header', async () => {
    const payload: OrderCreate = {
      symbol: 'NVDA',
      side: 'buy',
      type: 'limit',
      qty: 10,
      limit_price: 145.0,
      tif: 'day',
      source: 'manual',
    };
    const mockOrder: OrderResponse = {
      id: 'ord-1',
      user_id: 'u-1',
      account_id: 'acc-1',
      symbol: 'NVDA',
      side: 'buy',
      type: 'limit',
      qty: '10',
      limit_price: '145.00',
      stop_price: null,
      tif: 'day',
      status: 'accepted',
      idempotency_key: 'custom_idem_key',
      source: 'manual',
      created_at: '2026-11-15T12:00:00Z',
      updated_at: '2026-11-15T12:00:00Z',
    };
    const postSpy = vi.spyOn(httpClient, 'post').mockResolvedValueOnce({ data: mockOrder });

    const res = await simbrokerApi.submitOrder('acc-1', payload, 'custom_idem_key');
    expect(postSpy).toHaveBeenCalledWith(
      '/sim/accounts/acc-1/orders',
      payload,
      {
        headers: {
          'Idempotency-Key': 'custom_idem_key',
        },
      },
    );
    expect(res.id).toBe('ord-1');
  });

  it('listOrders calls GET /sim/accounts/{accountId}/orders with optional status', async () => {
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: [] });

    await simbrokerApi.listOrders('acc-1', 'accepted');
    expect(getSpy).toHaveBeenCalledWith('/sim/accounts/acc-1/orders', {
      params: { status: 'accepted' },
    });
  });

  it('cancelOrder calls DELETE /sim/accounts/{accountId}/orders/{orderId}', async () => {
    const mockOrder: OrderResponse = {
      id: 'ord-1',
      user_id: 'u-1',
      account_id: 'acc-1',
      symbol: 'NVDA',
      side: 'buy',
      type: 'limit',
      qty: '10',
      status: 'cancelled',
      idempotency_key: 'key-1',
      tif: 'day',
      source: 'manual',
      created_at: '2026-11-15T12:00:00Z',
      updated_at: '2026-11-15T12:00:00Z',
    };
    const deleteSpy = vi.spyOn(httpClient, 'delete').mockResolvedValueOnce({ data: mockOrder });

    const res = await simbrokerApi.cancelOrder('acc-1', 'ord-1');
    expect(deleteSpy).toHaveBeenCalledWith('/sim/accounts/acc-1/orders/ord-1');
    expect(res.status).toBe('cancelled');
  });

  it('getPositions calls GET /sim/accounts/{accountId}/positions', async () => {
    const mockPositions: PositionResponse[] = [
      {
        id: 'pos-1',
        account_id: 'acc-1',
        symbol: 'NVDA',
        qty: '100',
        avg_cost: '130.00',
        current_price: '148.00',
        market_value: '14800.00',
        unrealized_pnl: '1800.00',
        unrealized_pnl_pct: '13.85',
        realized_pnl: '0.00',
        weight_pct: '20.00',
      },
    ];
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockPositions });

    const res = await simbrokerApi.getPositions('acc-1');
    expect(getSpy).toHaveBeenCalledWith('/sim/accounts/acc-1/positions', { params: undefined });
    expect(res[0].symbol).toBe('NVDA');
  });

  it('getTrades calls GET /sim/accounts/{accountId}/trades', async () => {
    const mockTrades: TradeResponse[] = [
      {
        id: 'trd-1',
        user_id: 'u-1',
        account_id: 'acc-1',
        order_id: 'ord-1',
        symbol: 'NVDA',
        side: 'buy',
        qty: '100',
        price: '130.00',
        fee: '1.00',
        realized_pnl: '0.00',
        executed_at: '2026-11-15T12:00:00Z',
      },
    ];
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockTrades });

    const res = await simbrokerApi.getTrades('acc-1');
    expect(getSpy).toHaveBeenCalledWith('/sim/accounts/acc-1/trades', { params: undefined });
    expect(res[0].id).toBe('trd-1');
  });

  it('getPerformance calls GET /sim/accounts/{accountId}/performance', async () => {
    const mockPerf: PerformanceMetrics = {
      account_id: 'acc-1',
      initial_cash: '100000.00',
      current_equity: '115000.00',
      total_return: '15000.00',
      total_return_pct: '15.00',
      max_drawdown: '4.50',
      win_rate: '70.0',
      profit_loss_ratio: '3.0',
      total_trades: 10,
      winning_trades: 7,
      losing_trades: 3,
    };
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockPerf });

    const res = await simbrokerApi.getPerformance('acc-1');
    expect(getSpy).toHaveBeenCalledWith('/sim/accounts/acc-1/performance', { params: undefined });
    expect(res.total_return_pct).toBe('15.00');
  });

  it('getRisk calls GET /sim/accounts/{accountId}/risk', async () => {
    const mockRisk: RiskOverview = {
      account_id: 'acc-1',
      cash_ratio: '35.00',
      pdt_day_trades_count: 1,
      pdt_warning: false,
    };
    const getSpy = vi.spyOn(httpClient, 'get').mockResolvedValueOnce({ data: mockRisk });

    const res = await simbrokerApi.getRisk('acc-1');
    expect(getSpy).toHaveBeenCalledWith('/sim/accounts/acc-1/risk', { params: undefined });
    expect(res.cash_ratio).toBe('35.00');
  });

  it('updateTradeJournal puts payload to /sim/trades/{tradeId}/journal', async () => {
    const payload: TradeJournalUpdate = {
      notes: 'Executed per trend rule',
      tags: ['Trend', 'Breakout'],
      emotion: 'Disciplined',
    };
    const mockJournal: TradeJournalResponse = {
      id: 'jnl-1',
      trade_id: 'trd-1',
      notes: 'Executed per trend rule',
      tags: ['Trend', 'Breakout'],
      emotion: 'Disciplined',
      created_at: '2026-11-15T12:00:00Z',
      updated_at: '2026-11-15T12:00:00Z',
    };
    const putSpy = vi.spyOn(httpClient, 'put').mockResolvedValueOnce({ data: mockJournal });

    const res = await simbrokerApi.updateTradeJournal('trd-1', payload);
    expect(putSpy).toHaveBeenCalledWith('/sim/trades/trd-1/journal', payload);
    expect(res.emotion).toBe('Disciplined');
  });
});
