import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import {
  BookOpen,
  DollarSign,
  PieChart,
  TrendingUp,
} from 'lucide-react';
import { simbrokerApi } from '../../api/simbroker';
import type {
  AccountCreate,
  AccountOverview,
  AccountResponse,
  OrderResponse,
  PerformanceMetrics,
  PositionResponse,
  RiskOverview,
  TradeJournalResponse,
  TradeResponse,
} from '../../api/types';
import {
  mockAccountOverview,
  mockAccounts,
  mockOrders,
  mockPerformance,
  mockPositions,
  mockRisk,
  mockTradeJournals,
  mockTrades,
} from './mockData';
import { AccountOverviewView } from './AccountOverviewView';
import { OrderTradePanelView } from './OrderTradePanelView';
import { PositionsAndOrdersView } from './PositionsAndOrdersView';
import { TradingJournalView } from './TradingJournalView';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Modal } from '../../components/common/Modal';
import { ComplianceDisclaimer } from '../../components/compliance/ComplianceDisclaimer';
import { cn } from '../../utils/cn';

export type SimBrokerTabType = 'overview' | 'trade' | 'positions-orders' | 'journal';

export interface SimBrokerPageProps {
  initialTab?: SimBrokerTabType;
}

export const SimBrokerPage: React.FC<SimBrokerPageProps> = ({ initialTab }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Tab Sync
  const getInitialTab = (): SimBrokerTabType => {
    if (initialTab) return initialTab;
    const tabParam = searchParams.get('tab') as SimBrokerTabType;
    if (tabParam && ['overview', 'trade', 'positions-orders', 'journal'].includes(tabParam)) {
      return tabParam;
    }
    if (location.pathname.includes('/orders')) return 'positions-orders';
    if (location.pathname.includes('/journal')) return 'journal';
    return 'overview';
  };

  const [activeTab, setActiveTab] = useState<SimBrokerTabType>(getInitialTab);

  const isMockEnabled = import.meta.env.VITE_ENABLE_MOCK === 'true' || import.meta.env.MODE === 'test';

  // Core Data States
  const [accounts, setAccounts] = useState<AccountResponse[]>(() =>
    isMockEnabled ? mockAccounts : []
  );
  const [activeAccountId, setActiveAccountId] = useState<string>(() =>
    isMockEnabled ? (mockAccounts[0]?.id || '') : ''
  );
  const [overview, setOverview] = useState<AccountOverview | null>(() =>
    isMockEnabled ? mockAccountOverview : null
  );
  const [positions, setPositions] = useState<PositionResponse[]>(() =>
    isMockEnabled ? mockPositions : []
  );
  const [orders, setOrders] = useState<OrderResponse[]>(() =>
    isMockEnabled ? mockOrders : []
  );
  const [trades, setTrades] = useState<TradeResponse[]>(() =>
    isMockEnabled ? mockTrades : []
  );
  const [journals, setJournals] = useState<Record<string, TradeJournalResponse>>(() =>
    isMockEnabled ? mockTradeJournals : {}
  );
  const [performance, setPerformance] = useState<PerformanceMetrics | null>(() =>
    isMockEnabled ? mockPerformance : null
  );
  const [risk, setRisk] = useState<RiskOverview | null>(() =>
    isMockEnabled ? mockRisk : null
  );
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Quick Trade Prefill State (P0-2)
  const [prefillOrder, setPrefillOrder] = useState<{
    symbol: string;
    side: 'buy' | 'sell';
    quantity?: number;
  } | null>(null);

  // Quick Action Modals
  const [isDepositModalOpen, setIsDepositModalOpen] = useState<boolean>(false);
  const [depositAmount, setDepositAmount] = useState<string>('10000');
  const [depositType, setDepositType] = useState<'deposit' | 'withdraw'>('deposit');

  const [isCreateAccModalOpen, setIsCreateAccModalOpen] = useState<boolean>(false);
  const [newAccName, setNewAccName] = useState<string>('');
  const [newAccCash, setNewAccCash] = useState<string>('100000');
  const [createAccError, setCreateAccError] = useState<string | null>(null);

  useEffect(() => {
    loadAccounts();
  }, []);

  useEffect(() => {
    if (activeAccountId) {
      loadAccountData(activeAccountId);
    }
  }, [activeAccountId]);

  useEffect(() => {
    const tabParam = searchParams.get('tab') as SimBrokerTabType;
    if (tabParam && ['overview', 'trade', 'positions-orders', 'journal'].includes(tabParam)) {
      setActiveTab(tabParam);
    } else if (location.pathname.includes('/orders')) {
      setActiveTab('positions-orders');
    } else if (location.pathname.includes('/journal')) {
      setActiveTab('journal');
    } else if (location.pathname === '/simbroker') {
      setActiveTab('overview');
    }
  }, [location.pathname, searchParams]);

  const loadAccounts = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const accs = await simbrokerApi.listAccounts();
      if (accs && accs.length > 0) {
        setAccounts(accs);
        setActiveAccountId((current) => {
          if (current && accs.some((a) => a.id === current)) {
            return current;
          }
          return accs[0].id;
        });
      } else {
        setAccounts([]);
        setActiveAccountId('');
        setOverview(null);
        setPositions([]);
        setOrders([]);
        setTrades([]);
        setPerformance(null);
        setRisk(null);
      }
    } catch (err: unknown) {
      if (isMockEnabled) {
        setAccounts(mockAccounts);
        setActiveAccountId(mockAccounts[0]?.id || '');
      } else {
        setAccounts([]);
        setActiveAccountId('');
        setOverview(null);
        setPositions([]);
        setOrders([]);
        setTrades([]);
        setPerformance(null);
        setRisk(null);
        setErrorMessage(err instanceof Error ? err.message : '获取模拟账户列表失败');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const loadAccountData = async (accId: string) => {
    if (!accId) return;
    setIsLoading(true);
    try {
      const [ov, pos, ords, trds, perf, rsk] = await Promise.allSettled([
        simbrokerApi.getAccountOverview(accId),
        simbrokerApi.getPositions(accId),
        simbrokerApi.listOrders(accId),
        simbrokerApi.getTrades(accId),
        simbrokerApi.getPerformance(accId),
        simbrokerApi.getRisk(accId),
      ]);

      if (ov.status === 'fulfilled') setOverview(ov.value);
      if (pos.status === 'fulfilled') setPositions(pos.value);
      if (ords.status === 'fulfilled') setOrders(ords.value);
      if (trds.status === 'fulfilled') setTrades(trds.value);
      if (perf.status === 'fulfilled') setPerformance(perf.value);
      if (rsk.status === 'fulfilled') setRisk(rsk.value);
    } catch (err: unknown) {
      if (!isMockEnabled) {
        setErrorMessage(err instanceof Error ? err.message : '加载账户数据失败');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleDepositSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeAccountId || !depositAmount) return;

    try {
      if (depositType === 'deposit') {
        await simbrokerApi.deposit(activeAccountId, depositAmount);
      } else {
        await simbrokerApi.withdraw(activeAccountId, depositAmount);
      }
      await loadAccountData(activeAccountId);
      setIsDepositModalOpen(false);
    } catch (err: unknown) {
      if (isMockEnabled) {
        const delta = (depositType === 'deposit' ? 1 : -1) * parseFloat(depositAmount);
        setOverview((prev) =>
          prev
            ? {
                ...prev,
                cash: (parseFloat(prev.cash) + delta).toFixed(2),
                equity: (parseFloat(prev.equity) + delta).toFixed(2),
              }
            : null
        );
        setIsDepositModalOpen(false);
      } else {
        alert(`资金操作失败: ${err instanceof Error ? err.message : '请稍后重试'}`);
      }
    }
  };

  const handleCreateAccountSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAccName.trim()) return;
    setCreateAccError(null);

    const payload: AccountCreate = {
      name: newAccName.trim(),
      initial_cash: parseFloat(newAccCash) || 100000,
      slippage_bps: 5.0,
      pdt_enabled: true,
    };

    try {
      const created = await simbrokerApi.createAccount(payload);
      setAccounts((prev) => [...prev, created]);
      setActiveAccountId(created.id);
      setNewAccName('');
      setIsCreateAccModalOpen(false);
      await loadAccountData(created.id);
    } catch (err: unknown) {
      if (isMockEnabled) {
        const localAcc: AccountResponse = {
          id: `acc-local-${Date.now()}`,
          user_id: 'u-user-001',
          name: newAccName.trim(),
          initial_cash: newAccCash,
          cash: newAccCash,
          fee_model: {
            type: 'bps',
            per_share: '0.005',
            bps: '2.0',
            min_fee: '1.00',
            max_fee: '100.00',
          },
          slippage_bps: '5.0',
          pdt_enabled: true,
          status: 'active',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        setAccounts((prev) => [...prev, localAcc]);
        setActiveAccountId(localAcc.id);
        setNewAccName('');
        setIsCreateAccModalOpen(false);
      } else {
        const msg = err instanceof Error ? err.message : '创建模拟盘账户失败，请检查网络或后端状态';
        setCreateAccError(msg);
      }
    }
  };

  const handleResetAccount = async () => {
    if (!activeAccountId) return;
    setIsLoading(true);
    try {
      const resetOverview = await simbrokerApi.resetAccount(activeAccountId);
      setOverview(resetOverview);
      await loadAccountData(activeAccountId);
    } catch (err: unknown) {
      alert(`重置账户失败: ${err instanceof Error ? err.message : '网络通信或服务端异常'}`);
    } finally {
      setIsLoading(false);
    }
  };

  const tabs = [
    {
      id: 'overview' as const,
      label: '资产概览与净值',
      sub: 'Alpha 与最大回撤',
      icon: <TrendingUp className="h-4 w-4 text-emerald-400" />,
    },
    {
      id: 'trade' as const,
      label: '模拟交易下单',
      sub: '市价/限价/止损单',
      icon: <DollarSign className="h-4 w-4 text-blue-400" />,
    },
    {
      id: 'positions-orders' as const,
      label: '持仓与委托订单',
      sub: '浮动盈亏与一键撤单',
      icon: <PieChart className="h-4 w-4 text-indigo-400" />,
    },
    {
      id: 'journal' as const,
      label: '交易复盘日志',
      sub: '入场逻辑与经验教训',
      icon: <BookOpen className="h-4 w-4 text-amber-400" />,
    },
  ];

  return (
    <div className="space-y-6">
      {/* Top Error Alert Banner */}
      {errorMessage && (
        <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
          <span>{errorMessage}</span>
          <button
            onClick={() => {
              setErrorMessage(null);
              loadAccounts();
            }}
            className="underline font-semibold ml-2 hover:text-white cursor-pointer"
          >
            点击重试
          </button>
        </div>
      )}

      {/* Top Banner & Header */}
      <div className="pb-2 border-b border-slate-800">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <span>SimBroker 模拟盘控制台</span>
              <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-mono">
                实时撮合就绪
              </span>
              {isLoading && (
                <span className="text-[11px] text-slate-500 font-mono animate-pulse">
                  加载中...
                </span>
              )}
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              高仿真美股模拟撮合引擎，支持市价单、限价单与止损单，深度追踪 Alpha/Beta 与 PDT 合规，提供结构化交易复盘日志。
            </p>
          </div>

          {/* Navigation Tab Buttons */}
          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-900 border border-slate-800 shrink-0 self-start">
            {tabs.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => {
                    setActiveTab(tab.id);
                    navigate(tab.id === 'overview' ? '/simbroker' : `/simbroker?tab=${tab.id}`);
                  }}
                  className={cn(
                    'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all select-none',
                    isActive
                      ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60',
                  )}
                >
                  {tab.icon}
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Empty State when no accounts exist */}
      {accounts.length === 0 && !isLoading ? (
        <div className="p-12 rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 text-center space-y-4">
          <div className="h-14 w-14 rounded-2xl bg-blue-600/10 border border-blue-500/20 text-blue-400 flex items-center justify-center mx-auto">
            <PieChart className="h-7 w-7" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white">暂无模拟盘账户</h3>
            <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
              当前尚未创建任何模拟交易账户。立即创建您的首个模拟账户，开启高仿真美股撮合与多因子策略追踪。
            </p>
          </div>
          <Button
            variant="primary"
            size="md"
            onClick={() => {
              setCreateAccError(null);
              setIsCreateAccModalOpen(true);
            }}
            leftIcon={<DollarSign className="h-4 w-4" />}
          >
            立即创建模拟账户
          </Button>
        </div>
      ) : (
        /* Main Tab Content */
        <div className="pt-2">
          {activeTab === 'overview' && overview && (
            <AccountOverviewView
              overview={overview}
              accounts={accounts}
              activeAccountId={activeAccountId}
              onSelectAccount={(id) => setActiveAccountId(id)}
              performance={performance}
              risk={risk}
              onOpenDeposit={() => {
                setDepositType('deposit');
                setIsDepositModalOpen(true);
              }}
              onOpenCreateAccount={() => {
                setCreateAccError(null);
                setIsCreateAccModalOpen(true);
              }}
              onResetAccount={handleResetAccount}
            />
          )}

          {activeTab === 'trade' && (
            overview ? (
              <OrderTradePanelView
                overview={overview}
                positions={positions}
                onOrderSubmitted={() => loadAccountData(activeAccountId)}
                prefillOrder={prefillOrder}
                onClearPrefill={() => setPrefillOrder(null)}
              />
            ) : (
              <div className="p-8 text-center text-slate-400 text-xs">
                正在加载账户数据以准备交易面板...
              </div>
            )
          )}

          {activeTab === 'positions-orders' && (
            <PositionsAndOrdersView
              accountId={activeAccountId}
              positions={positions}
              orders={orders}
              onRefresh={() => loadAccountData(activeAccountId)}
              onQuickTrade={(symbol, side, quantity) => {
                setPrefillOrder({ symbol, side, quantity });
                setActiveTab('trade');
                navigate('/simbroker?tab=trade');
              }}
            />
          )}

          {activeTab === 'journal' && (
            <TradingJournalView
              trades={trades}
              journals={journals}
              onJournalUpdated={(tradeId, updated) =>
                setJournals((prev) => ({ ...prev, [tradeId]: updated }))
              }
            />
          )}
        </div>
      )}

      <ComplianceDisclaimer variant="card" />

      {/* Modal: Deposit & Withdraw */}
      <Modal
        isOpen={isDepositModalOpen}
        onClose={() => setIsDepositModalOpen(false)}
        title={depositType === 'deposit' ? '模拟账户资金充值 (Deposit)' : '模拟账户资金提现 (Withdraw)'}
      >
        <form onSubmit={handleDepositSubmit} className="space-y-4 text-xs">
          <div className="flex gap-2 p-1 rounded-lg bg-slate-950 border border-slate-800">
            <button
              type="button"
              onClick={() => setDepositType('deposit')}
              className={cn(
                'flex-1 py-1.5 rounded text-xs font-semibold transition-colors',
                depositType === 'deposit' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white',
              )}
            >
              资金充值
            </button>
            <button
              type="button"
              onClick={() => setDepositType('withdraw')}
              className={cn(
                'flex-1 py-1.5 rounded text-xs font-semibold transition-colors',
                depositType === 'withdraw' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white',
              )}
            >
              资金提取
            </button>
          </div>

          <div className="space-y-1">
            <label className="font-semibold text-slate-300">操作金额 ($)</label>
            <Input
              type="number"
              step="100"
              min="100"
              value={depositAmount}
              onChange={(e) => setDepositAmount(e.target.value)}
              className="font-mono text-sm"
              required
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" type="button" onClick={() => setIsDepositModalOpen(false)}>
              取消
            </Button>
            <Button variant="primary" type="submit">
              确认提交
            </Button>
          </div>
        </form>
      </Modal>

      {/* Modal: Create Account */}
      <Modal
        isOpen={isCreateAccModalOpen}
        onClose={() => {
          setCreateAccError(null);
          setIsCreateAccModalOpen(false);
        }}
        title="新建模拟盘账户"
      >
        <form onSubmit={handleCreateAccountSubmit} className="space-y-4 text-xs">
          {createAccError && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
              {createAccError}
            </div>
          )}

          <div className="space-y-1">
            <label className="font-semibold text-slate-300">账户名称 *</label>
            <Input
              placeholder="例如：趋势策略测试盘 #3"
              value={newAccName}
              onChange={(e) => setNewAccName(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div className="space-y-1">
            <label className="font-semibold text-slate-300">初始本金 ($)</label>
            <Input
              type="number"
              step="1000"
              value={newAccCash}
              onChange={(e) => setNewAccCash(e.target.value)}
              className="font-mono text-sm"
              required
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="ghost"
              type="button"
              onClick={() => {
                setCreateAccError(null);
                setIsCreateAccModalOpen(false);
              }}
            >
              取消
            </Button>
            <Button variant="primary" type="submit">
              确认创建
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default SimBrokerPage;
