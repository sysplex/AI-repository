import React, { useEffect, useState } from 'react';
import authApi from '../../api/auth';
import type { UsageResponse } from '../../api/types';
import { AppError } from '../../utils/errors';
import { formatPrice } from '../../utils/format';
import { AlertCircle, Clock, Info, Loader2, RefreshCw, Zap } from 'lucide-react';

export const UsagePage: React.FC = () => {
  const [usage, setUsage] = useState<UsageResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchUsage = async (isManual = false) => {
    if (isManual) setIsRefreshing(true);
    setError(null);
    try {
      const data = await authApi.getUsage();
      setUsage(data);
    } catch (err: unknown) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('加载用量数据失败，请重试');
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    void fetchUsage();
  }, []);

  const count = usage?.quota_used ?? 0;
  const quota = usage?.quota ?? 20;
  const remaining = Math.max(0, quota - count);
  const pct = quota > 0 ? Math.min(100, Math.round((count / quota) * 100)) : 100;

  let progressColor = 'bg-brand-600';
  if (pct >= 90) {
    progressColor = 'bg-red-500';
  } else if (pct >= 70) {
    progressColor = 'bg-amber-500';
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between border-b pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">AI 用量与配额仪表盘</h1>
          <p className="mt-1 text-sm text-gray-500">
            查看您当前的每日 AI 智能分析额度、消耗账本与模型调用统计（ADR-016）
          </p>
        </div>
        <button
          onClick={() => void fetchUsage(true)}
          disabled={isRefreshing}
          className="flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
          刷新数据
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <AlertCircle className="h-5 w-5 text-red-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {isLoading ? (
        <div className="flex min-h-[30vh] items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-brand-600" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Main Meter Card */}
          <div className="rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-gray-900 font-bold">
                <Zap className="h-5 w-5 text-amber-500" />
                <span>当日 AI 调用额度</span>
              </div>
              <span className="text-xs text-gray-500 font-mono">账本日期: {usage?.usage_date || '--'}</span>
            </div>

            <div className="mb-6">
              <div className="flex items-baseline justify-between mb-2">
                <span className="text-3xl font-extrabold tracking-tight text-gray-900">
                  {count} <span className="text-lg font-normal text-gray-400">/ {quota} 次</span>
                </span>
                <span className="text-sm font-semibold text-gray-700">已使用 {pct}%</span>
              </div>

              {/* Progress bar */}
              <div className="h-3 w-full rounded-full bg-gray-100 overflow-hidden">
                <div
                  className={`h-full ${progressColor} transition-all duration-500 rounded-full`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t text-sm">
              <div className="p-3.5 rounded-xl bg-gray-50 border border-gray-100">
                <div className="text-xs text-gray-500 font-medium">今日剩余可用</div>
                <div className="text-xl font-bold text-emerald-600 mt-1">{remaining} 次</div>
                <div className="text-xs text-gray-400 mt-0.5">每项深度分析扣减 1 次</div>
              </div>

              <div className="p-3.5 rounded-xl bg-gray-50 border border-gray-100">
                <div className="text-xs text-gray-500 font-medium">累计预估 Token 成本</div>
                <div className="text-xl font-bold text-gray-900 mt-1">
                  {formatPrice(usage?.cost_usd ?? 0, 4)}
                </div>
                <div className="text-xs text-gray-400 mt-0.5">高精 Decimal 账本计费</div>
              </div>

              <div className="p-3.5 rounded-xl bg-gray-50 border border-gray-100">
                <div className="text-xs text-gray-500 font-medium">额度刷新周期</div>
                <div className="text-sm font-semibold text-gray-800 mt-1 flex items-center gap-1.5">
                  <Clock className="h-4 w-4 text-gray-500" />
                  <span>每日 00:00 UTC</span>
                </div>
                <div className="text-xs text-gray-400 mt-0.5">北京时间每日 08:00 重置</div>
              </div>
            </div>
          </div>

          {/* Info Banner */}
          <div className="rounded-xl border border-blue-200 bg-blue-50 p-5 text-sm text-blue-900">
            <div className="flex items-start gap-3">
              <Info className="h-5 w-5 text-blue-600 mt-0.5 shrink-0" />
              <div className="space-y-1 text-xs leading-relaxed">
                <div className="font-bold text-sm text-blue-950">关于 AI 配额与系统安全防线</div>
                <p>
                  1. **多租户隔离**：每位用户的配额与用量按用户唯一 ID（Tenant ID）严格原子扣减，租户之间物理/逻辑隔离互不影响。
                </p>
                <p>
                  2. **熔断与限流**：当单日配额耗尽后，系统将自动防御拦截新的生成请求（返回 429 QUOTA_EXCEEDED）。如需提升额度，请联系系统管理员。
                </p>
                <p>
                  3. **智能缓存**：相同标的相同输入快照命中缓存时，将返回已有研报，**不扣减任何每日配额**，实现零成本复用。
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default UsagePage;
