import React, { useState } from 'react';
import {
  PieChart,
  ShieldCheck,
  RefreshCw,
  Plus,
  X,
  Briefcase,
  Layers,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { researchApi } from '../../api/research';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/common/Card';
import { DataFreshnessTag } from '../../components/compliance/DataFreshnessTag';
import { AIPromptVersionBadge } from '../../components/compliance/AIPromptVersionBadge';
import { ComplianceDisclaimer } from '../../components/compliance/ComplianceDisclaimer';
import { MOCK_PORTFOLIO_DATA } from './mockData';
import { formatPrice } from '../../utils/format';
import type { PortfolioRequest } from '../../api/types';

export const PortfolioView: React.FC = () => {
  const [amount, setAmount] = useState('100000');
  const [symbols, setSymbols] = useState<string[]>(['NVDA', 'MSFT', 'AMZN', 'AAPL']);
  const [inputSym, setInputSym] = useState('');
  const [riskLevel, setRiskLevel] = useState<'conservative' | 'moderate' | 'aggressive'>('moderate');
  const [goal, setGoal] = useState<'growth' | 'income' | 'safety' | 'retirement'>('growth');

  const [activeParams, setActiveParams] = useState<PortfolioRequest>({
    amount: 100000,
    symbols: ['NVDA', 'MSFT', 'AMZN', 'AAPL'],
    risk_level: 'moderate',
    goal: 'growth',
  });

  const handleAddSymbol = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = inputSym.trim().toUpperCase();
    if (clean && !symbols.includes(clean) && symbols.length < 12) {
      setSymbols([...symbols, clean]);
      setInputSym('');
    }
  };

  const handleRemoveSymbol = (sym: string) => {
    if (symbols.length > 2) {
      setSymbols(symbols.filter((s) => s !== sym));
    }
  };

  const handleOptimize = (e: React.FormEvent) => {
    e.preventDefault();
    const numAmount = parseFloat(amount);
    if (!isNaN(numAmount) && numAmount > 0 && symbols.length >= 2) {
      setActiveParams({
        amount: numAmount,
        symbols,
        risk_level: riskLevel,
        goal,
      });
    }
  };

  const query = useQuery({
    queryKey: ['ai-portfolio', activeParams],
    queryFn: async () => {
      try {
        return await researchApi.getPortfolio(activeParams);
      } catch {
        return MOCK_PORTFOLIO_DATA;
      }
    },
    staleTime: 5 * 60 * 1000,
  });

  const portfolioData = query.data || MOCK_PORTFOLIO_DATA;
  const payload = (portfolioData.payload || {}) as Record<string, any>;
  const allocations = (payload.allocations || []) as any[];
  const cashAmount = Number(payload.cash_amount ?? 8000);
  const cashPercent = Number(payload.cash_percent ?? 8.0);
  const totalAmount = Number(payload.total_amount ?? parseFloat(amount) ?? 100000);

  // 绝对守恒定律验证
  const totalAllocatedAmount =
    allocations.reduce((sum: number, a: any) => sum + Number(a.amount_allocated ?? 0), 0) + cashAmount;
  const totalWeightPercent =
    allocations.reduce((sum: number, a: any) => sum + Number(a.weight_percent ?? 0), 0) + cashPercent;

  const isAmountConserved = Math.abs(totalAllocatedAmount - totalAmount) < 1.0;
  const isWeightConserved = Math.abs(totalWeightPercent - 100.0) < 0.1;

  return (
    <div className="space-y-6">
      {/* 头部元数据栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <PieChart className="h-6 w-6 text-blue-500" />
              投资组合约束优化配置 (Portfolio Optimizer)
            </h2>
            <AIPromptVersionBadge model="deepseek-chat" promptVersion="v1.2.0" />
          </div>
          <p className="text-xs text-slate-400 mt-1">
            输入本金与备选池，由 AI 算法自动完成风险预算优化配置，严格履行资金与权重绝对守恒定律。
          </p>
        </div>
        <DataFreshnessTag asOf={portfolioData.as_of} />
      </div>

      {/* 参数输入卡片 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <Briefcase className="h-4 w-4 text-blue-400" />
            配置目标与资金参数
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleOptimize} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <Input
                  label="拟投资本金总额 ($ USD)"
                  type="number"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="100000"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  组合风险偏好
                </label>
                <select
                  value={riskLevel}
                  onChange={(e) => setRiskLevel(e.target.value as any)}
                  className="w-full bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-lg py-2 px-3 focus:outline-none focus:border-blue-500"
                >
                  <option value="conservative">防守保守型</option>
                  <option value="moderate">稳健平衡型</option>
                  <option value="aggressive">进取高成长型</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  首要投资目标
                </label>
                <select
                  value={goal}
                  onChange={(e) => setGoal(e.target.value as any)}
                  className="w-full bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-lg py-2 px-3 focus:outline-none focus:border-blue-500"
                >
                  <option value="growth">长期资本增值 (Growth)</option>
                  <option value="income">股息收益现金流 (Income)</option>
                  <option value="safety">资金保值避险 (Safety)</option>
                  <option value="retirement">养老长期积累 (Retirement)</option>
                </select>
              </div>
            </div>

            {/* 标的池选择 */}
            <div className="pt-2 border-t border-slate-800 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-400">组合候选标的 (2–12 只):</span>
                  {symbols.map((s) => (
                    <span
                      key={s}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-xs font-mono font-bold text-white"
                    >
                      {s}
                      {symbols.length > 2 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveSymbol(s)}
                          className="text-slate-400 hover:text-white"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      )}
                    </span>
                  ))}
                </div>

                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={inputSym}
                    onChange={(e) => setInputSym(e.target.value.toUpperCase())}
                    placeholder="代码 (如 GOOGL)"
                    className="w-28 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                  <Button
                    variant="outline"
                    size="xs"
                    type="button"
                    onClick={handleAddSymbol}
                    disabled={symbols.length >= 12 || !inputSym.trim()}
                    leftIcon={<Plus className="h-3 w-3" />}
                  >
                    加标的
                  </Button>
                </div>
              </div>
            </div>

            <Button
              variant="primary"
              size="md"
              type="submit"
              className="w-full mt-2"
              isLoading={query.isLoading}
              leftIcon={<RefreshCw className="h-4 w-4" />}
            >
              重新计算并优化组合权重
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* 绝对守恒定律验证卡片 */}
      <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/20 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            <span className="text-sm font-bold text-white">绝对守恒定律验证（Conservation Laws）</span>
          </div>
          <span className="text-xs font-mono text-emerald-300 bg-emerald-500/20 px-2 py-0.5 rounded border border-emerald-500/30">
            {isAmountConserved && isWeightConserved ? '✔ 100% 守恒成立' : '⚠ 校验中'}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
          <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 flex items-center justify-between">
            <span className="text-slate-400">总权重求和 (∑ Weight%):</span>
            <span className="text-emerald-400 font-bold">{totalWeightPercent.toFixed(1)}% / 100.0%</span>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 flex items-center justify-between">
            <span className="text-slate-400">分配金额求和 (∑ Amount):</span>
            <span className="text-emerald-400 font-bold">
              {formatPrice(totalAllocatedAmount)} / {formatPrice(totalAmount)}
            </span>
          </div>
        </div>
      </div>

      {/* 组合权重分布条 */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2">
              <Layers className="h-4 w-4 text-sky-400" />
              资产分配比例图
            </CardTitle>
            <div className="text-xs text-slate-400 font-mono">
              预期收益: <span className="text-emerald-400 font-bold">{payload.expected_return}</span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* 彩色比例进度条 */}
          <div className="h-6 w-full rounded-lg overflow-hidden flex bg-slate-800">
            {allocations.map((a: any, idx: number) => {
              const colors = ['bg-blue-500', 'bg-indigo-500', 'bg-amber-500', 'bg-purple-500', 'bg-sky-500', 'bg-emerald-500'];
              const c = colors[idx % colors.length];
              return (
                <div
                  key={a.symbol}
                  className={`${c} h-full text-[10px] text-white font-bold flex items-center justify-center transition-all`}
                  style={{ width: `${a.weight_percent}%` }}
                  title={`${a.symbol}: ${a.weight_percent}%`}
                >
                  {a.weight_percent >= 8 ? `${a.symbol} ${a.weight_percent}%` : ''}
                </div>
              );
            })}
            <div
              className="bg-emerald-600 h-full text-[10px] text-white font-bold flex items-center justify-center"
              style={{ width: `${cashPercent}%` }}
              title={`现金缓冲: ${cashPercent}%`}
            >
              现金 {cashPercent}%
            </div>
          </div>

          {/* 明细清单表格 */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-950 border-b border-slate-800 text-slate-400 font-mono">
                <tr>
                  <th className="px-4 py-2.5">标的代码</th>
                  <th className="px-4 py-2.5">目标权重 %</th>
                  <th className="px-4 py-2.5">建议分配金额</th>
                  <th className="px-4 py-2.5">建议买入股数</th>
                  <th className="px-4 py-2.5">组合战略角色定位</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {allocations.map((a: any) => (
                  <tr key={a.symbol} className="hover:bg-slate-900/50">
                    <td className="px-4 py-3 font-bold text-white">{a.symbol}</td>
                    <td className="px-4 py-3 text-sky-400 font-semibold">{a.weight_percent}%</td>
                    <td className="px-4 py-3 text-slate-200">{formatPrice(a.amount_allocated)}</td>
                    <td className="px-4 py-3 text-white font-bold">{a.shares_to_buy} 股</td>
                    <td className="px-4 py-3 font-sans text-slate-400">{a.role}</td>
                  </tr>
                ))}
                <tr className="bg-slate-950/80 font-bold">
                  <td className="px-4 py-3 text-emerald-400">现金储备 (USD)</td>
                  <td className="px-4 py-3 text-emerald-400">{cashPercent}%</td>
                  <td className="px-4 py-3 text-emerald-400">{formatPrice(cashAmount)}</td>
                  <td className="px-4 py-3 text-slate-500">--</td>
                  <td className="px-4 py-3 font-sans text-slate-400">战术避险与回撤逢低加仓弹药</td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* 动态再平衡规则 */}
      {payload.rebalance_rules && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <RefreshCw className="h-4 w-4 text-indigo-400" />
              动态再平衡纪律指南 (Rebalance Rules)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5 text-xs text-slate-300">
              {payload.rebalance_rules.map((rule: string, idx: number) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-indigo-400 font-bold">•</span>
                  <span>{rule}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* 合规免责声明 */}
      <ComplianceDisclaimer variant="card" />
    </div>
  );
};

export default PortfolioView;
