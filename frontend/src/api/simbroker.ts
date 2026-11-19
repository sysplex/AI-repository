import { api, httpClient } from './client';
import type {
  AccountCreate,
  AccountOverview,
  AccountResponse,
  DepositRequest,
  OrderCreate,
  OrderResponse,
  PerformanceMetrics,
  PositionResponse,
  RiskOverview,
  TradeJournalResponse,
  TradeJournalUpdate,
  TradeResponse,
} from './types';

export const simbrokerApi = {
  // ---------------------------------------------------------------------------
  // 1. 模拟账户管理
  // ---------------------------------------------------------------------------
  async createAccount(data: AccountCreate): Promise<AccountResponse> {
    return api.post<AccountResponse>('/sim/accounts', data);
  },

  async listAccounts(): Promise<AccountResponse[]> {
    return api.get<AccountResponse[]>('/sim/accounts');
  },

  async getAccountOverview(accountId: string): Promise<AccountOverview> {
    return api.get<AccountOverview>(`/sim/accounts/${accountId}`);
  },

  async resetAccount(
    accountId: string,
    data?: { initial_cash?: number | string },
  ): Promise<AccountOverview> {
    return api.post<AccountOverview>(`/sim/accounts/${accountId}/reset`, data || {});
  },

  // ---------------------------------------------------------------------------
  // 2. 出入金与资金流
  // ---------------------------------------------------------------------------
  async deposit(
    accountId: string,
    amount: number | string,
  ): Promise<{ account_id: string; cash: string }> {
    const payload: DepositRequest = { amount };
    return api.post<{ account_id: string; cash: string }>(
      `/sim/accounts/${accountId}/deposit`,
      payload,
    );
  },

  async withdraw(
    accountId: string,
    amount: number | string,
  ): Promise<{ account_id: string; cash: string }> {
    const payload: DepositRequest = { amount };
    return api.post<{ account_id: string; cash: string }>(
      `/sim/accounts/${accountId}/withdraw`,
      payload,
    );
  },

  // ---------------------------------------------------------------------------
  // 3. 订单交易生命周期
  // ---------------------------------------------------------------------------
  async submitOrder(
    accountId: string,
    data: OrderCreate,
    idempotencyKey?: string,
  ): Promise<OrderResponse> {
    const key =
      idempotencyKey ||
      `order_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    const res = await httpClient.post<OrderResponse>(
      `/sim/accounts/${accountId}/orders`,
      data,
      {
        headers: {
          'Idempotency-Key': key,
        },
      },
    );
    return res.data;
  },

  async listOrders(accountId: string, status?: string): Promise<OrderResponse[]> {
    const params = status ? { status } : undefined;
    return api.get<OrderResponse[]>(`/sim/accounts/${accountId}/orders`, params);
  },

  async cancelOrder(accountId: string, orderId: string): Promise<OrderResponse> {
    const res = await httpClient.delete<OrderResponse>(
      `/sim/accounts/${accountId}/orders/${orderId}`,
    );
    return res.data;
  },

  // ---------------------------------------------------------------------------
  // 4. 持仓明细与历史成交
  // ---------------------------------------------------------------------------
  async getPositions(accountId: string): Promise<PositionResponse[]> {
    return api.get<PositionResponse[]>(`/sim/accounts/${accountId}/positions`);
  },

  async getTrades(accountId: string): Promise<TradeResponse[]> {
    return api.get<TradeResponse[]>(`/sim/accounts/${accountId}/trades`);
  },

  // ---------------------------------------------------------------------------
  // 5. 业绩分析与持仓风险体检
  // ---------------------------------------------------------------------------
  async getPerformance(accountId: string): Promise<PerformanceMetrics> {
    return api.get<PerformanceMetrics>(`/sim/accounts/${accountId}/performance`);
  },

  async getRisk(accountId: string): Promise<RiskOverview> {
    return api.get<RiskOverview>(`/sim/accounts/${accountId}/risk`);
  },

  // ---------------------------------------------------------------------------
  // 6. 交易复盘日志录入
  // ---------------------------------------------------------------------------
  async updateTradeJournal(
    tradeId: string,
    data: TradeJournalUpdate,
  ): Promise<TradeJournalResponse> {
    return api.put<TradeJournalResponse>(`/sim/trades/${tradeId}/journal`, data);
  },
};

export default simbrokerApi;
