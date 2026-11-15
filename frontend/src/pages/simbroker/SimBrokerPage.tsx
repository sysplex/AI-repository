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

  // Core Data States
  const [accounts, setAccounts] = useState<AccountResponse[]>(mockAccounts);
  const [activeAccountId, setActiveAccountId] = useState<string>(mockAccounts[0]?.id || '');
  const [overview, setOverview] = useState<AccountOverview>(mockAccountOverview);
  const [positions, setPositions] = useState<PositionResponse[]>(mockPositions);
  const [orders, setOrders] = useState<OrderResponse[]>(mockOrders);
  const [trades, setTrades] = useState<TradeResponse[]>(mockTrades);
  const [journals, setJournals] = useState<Record<string, TradeJournalResponse>>(mockTradeJournals);
  const [performance, setPerformance] = useState<PerformanceMetrics>(mockPerformance);
  const [risk, setRisk] = useState<RiskOverview>(mockRisk);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Quick Action Modals
  const [isDepositModalOpen, setIsDepositModalOpen] = useState<boolean>(false);
  const [depositAmount, setDepositAmount] = useState<string>('10000');
  const [depositType, setDepositType] = useState<'deposit' | 'withdraw'>('deposit');

  const [isCreateAccModalOpen, setIsCreateAccModalOpen] = useState<boolean>(false);
  const [newAccName, setNewAccName] = useState<string>('');
  const [newAccCash, setNewAccCash] = useState<string>('100000');

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
    try {
      const accs = await simbrokerApi.listAccounts();
      if (accs && accs.length > 0) {
        setAccounts(accs);
        if (!activeAccountId || !accs.some((a) => a.id === activeAccountId)) {
          setActiveAccountId(accs[0].id);
        }
      }
    } catch {
      // Keep mock accounts
    } finally {
      setIsLoading(false);
    }
  };

  const loadAccountData = async (accId: string) => {
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
    } catch {
      // Keep mock data
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
      loadAccountData(activeAccountId);
    } catch {
      // Local fallback
      const delta = (depositType === 'deposit' ? 1 : -1) * parseFloat(depositAmount);
      setOverview((prev) => ({
        ...prev,
        cash: (parseFloat(prev.cash) + delta).toFixed(2),
        equity: (parseFloat(prev.equity) + delta).toFixed(2),
      }));
    }

    setIsDepositModalOpen(false);
  };

  const handleCreateAccountSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAccName.trim()) return;

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
    } catch {
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
    }

    setNewAccName('');
    setIsCreateAccModalOpen(false);
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

      {/* Main Tab Content */}
      <div className="pt-2">
        {activeTab === 'overview' && (
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
            onOpenCreateAccount={() => setIsCreateAccModalOpen(true)}
          />
        )}

        {activeTab === 'trade' && (
          <OrderTradePanelView
            overview={overview}
            positions={positions}
            onOrderSubmitted={() => loadAccountData(activeAccountId)}
          />
        )}

        {activeTab === 'positions-orders' && (
          <PositionsAndOrdersView
            accountId={activeAccountId}
            positions={positions}
            orders={orders}
            onRefresh={() => loadAccountData(activeAccountId)}
            onQuickTrade={() => setActiveTab('trade')}
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
        onClose={() => setIsCreateAccModalOpen(false)}
        title="新建模拟盘账户"
      >
        <form onSubmit={handleCreateAccountSubmit} className="space-y-4 text-xs">
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
            <Button variant="ghost" type="button" onClick={() => setIsCreateAccModalOpen(false)}>
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
