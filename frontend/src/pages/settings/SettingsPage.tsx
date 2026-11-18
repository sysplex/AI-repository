import React, { useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import authApi from '../../api/auth';
import researchApi from '../../api/research';
import { AppError } from '../../utils/errors';
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Eye,
  EyeOff,
  Globe,
  KeyRound,
  Loader2,
  Palette,
  ShieldAlert,
  Sliders,
  Sparkles,
  User,
} from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const { user, refreshUser, colorScheme, setColorScheme } = useAuth();

  const [language, setLanguage] = useState<'zh-CN' | 'en'>(
    (user?.settings?.language as 'zh-CN' | 'en') || 'zh-CN'
  );
  const [riskProfile, setRiskProfile] = useState<'conservative' | 'balanced' | 'aggressive'>(
    (user?.settings?.risk_profile as 'conservative' | 'balanced' | 'aggressive') || 'balanced'
  );
  const [scheme, setScheme] = useState<'us' | 'cn'>(colorScheme);

  // AI 模型与接口偏好
  const userSettings = (user?.settings || {}) as Record<string, unknown>;
  const [aiProvider, setAiProvider] = useState<'mock' | 'google'>(
    (userSettings.ai_provider as 'mock' | 'google') || 'mock'
  );
  const [googleApiKey, setGoogleApiKey] = useState<string>(
    (userSettings.google_api_key as string) || ''
  );
  const [googleModel, setGoogleModel] = useState<string>(
    (userSettings.google_model as string) || 'gemini-3.5-flash-lite'
  );
  const [showApiKey, setShowApiKey] = useState(false);
  const [isTestingKey, setIsTestingKey] = useState(false);
  const [testResult, setTestResult] = useState<{
    valid: boolean;
    message: string;
    latency_ms?: number;
  } | null>(null);

  const [isSaving, setIsSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleTestKey = async () => {
    if (aiProvider === 'google' && !googleApiKey.trim()) {
      setTestResult({
        valid: false,
        message: '请先输入 Google Gemini API Key',
      });
      return;
    }
    setIsTestingKey(true);
    setTestResult(null);
    try {
      const res = await researchApi.testApiKey({
        provider: aiProvider,
        api_key: googleApiKey.trim(),
        model: googleModel,
      });
      setTestResult(res);
    } catch (err: unknown) {
      setTestResult({
        valid: false,
        message: err instanceof Error ? err.message : '连接测试请求失败',
      });
    } finally {
      setIsTestingKey(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSuccessMsg(null);
    setErrorMsg(null);

    try {
      await authApi.updateMe({
        settings: {
          language,
          risk_profile: riskProfile,
          ai_provider: aiProvider,
          google_api_key: googleApiKey.trim(),
          google_model: googleModel,
        },
      });
      setColorScheme(scheme);
      await refreshUser();
      setSuccessMsg('偏好设置与 AI 模型配置已成功保存！');
    } catch (err: unknown) {
      if (err instanceof AppError) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg('保存设置失败，请稍后重试');
      }
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Page Title */}
      <div className="border-b pb-4">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">用户设置与偏好</h1>
        <p className="mt-1 text-sm text-gray-500">管理您的个人投资偏好、AI 模型接口、界面涨跌配色与多租户账户状态</p>
      </div>

      {successMsg && (
        <div className="flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
          <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0" />
          <span className="font-medium">{successMsg}</span>
        </div>
      )}

      {errorMsg && (
        <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <AlertCircle className="h-5 w-5 text-red-600 shrink-0" />
          <span className="font-medium">{errorMsg}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        {/* Account Info */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2.5 mb-4 text-gray-900 font-semibold border-b pb-3">
            <User className="h-5 w-5 text-brand-600" />
            <span>账号与租户信息</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div>
              <label className="text-xs text-gray-500 font-medium">注册邮箱</label>
              <div className="mt-1 font-semibold text-gray-800">{user?.email || '--'}</div>
            </div>
            <div>
              <label className="text-xs text-gray-500 font-medium">租户唯一标识 (User ID)</label>
              <div className="mt-1 font-mono text-xs text-gray-600">{user?.id || '--'}</div>
            </div>
            <div>
              <label className="text-xs text-gray-500 font-medium">用户角色</label>
              <div className="mt-1">
                <span className="inline-flex items-center rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-blue-700 border border-blue-200">
                  {user?.role === 'admin' ? '系统管理员 (Admin)' : '标准投资者 (User)'}
                </span>
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-500 font-medium">账号状态</label>
              <div className="mt-1">
                <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200">
                  正常活跃 (Active)
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Investment & Risk Preferences */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2.5 mb-4 text-gray-900 font-semibold border-b pb-3">
            <ShieldAlert className="h-5 w-5 text-brand-600" />
            <span>投资与风控偏好</span>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                默认风险偏好 (Risk Profile)
              </label>
              <p className="text-xs text-gray-500 mb-2">
                此设置将影响买入决策评估、投资组合配置与仓位计算的风控权重参数。
              </p>
              <div className="grid grid-cols-3 gap-3">
                {[
                  { id: 'conservative', label: '保守型', desc: '注重资本保全与低波动' },
                  { id: 'balanced', label: '平衡型', desc: '追求稳健成长与适中波动' },
                  { id: 'aggressive', label: '进取型', desc: '容忍高波动以换取高收益' },
                ].map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setRiskProfile(item.id as 'conservative' | 'balanced' | 'aggressive')}
                    className={`rounded-lg border p-3.5 text-left transition-all ${
                      riskProfile === item.id
                        ? 'border-brand-600 bg-brand-50 text-brand-900 ring-1 ring-brand-600'
                        : 'border-gray-200 bg-white hover:border-gray-300'
                    }`}
                  >
                    <div className="font-semibold text-sm">{item.label}</div>
                    <div className="text-xs text-gray-500 mt-1">{item.desc}</div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* AI Model & Provider Configuration */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2.5 mb-4 text-gray-900 font-semibold border-b pb-3">
            <Bot className="h-5 w-5 text-brand-600" />
            <span>AI 模型与接口配置 (AI Model & API Provider)</span>
          </div>

          <div className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                选择 AI 驱动源
              </label>
              <p className="text-xs text-gray-500 mb-3">
                选择系统在生成个股深度研报、买入决策评估与智能选股时使用的 AI 分析引擎。
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setAiProvider('mock');
                    setTestResult(null);
                  }}
                  className={`rounded-lg border p-4 text-left transition-all ${
                    aiProvider === 'mock'
                      ? 'border-brand-600 bg-brand-50 text-brand-900 ring-1 ring-brand-600'
                      : 'border-gray-200 bg-white hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm">系统默认 / Mock 模拟</span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 font-medium">离线模拟</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-2">
                    基于内置确定性算法快速返回测试数据，无需配置外部网络或 API 密钥。
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setAiProvider('google');
                    setTestResult(null);
                  }}
                  className={`rounded-lg border p-4 text-left transition-all ${
                    aiProvider === 'google'
                      ? 'border-brand-600 bg-brand-50 text-brand-900 ring-1 ring-brand-600'
                      : 'border-gray-200 bg-white hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm flex items-center gap-1.5">
                      <Sparkles className="h-4 w-4 text-amber-500" />
                      Google Gemini 官方 API
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-medium">支持免费层</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-2">
                    调用 Google Gemini 官方大模型，生成深度研究洞察与投资决策分析。
                  </div>
                </button>
              </div>
            </div>

            {aiProvider === 'google' && (
              <div className="rounded-lg border border-brand-200 bg-brand-50/40 p-4 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 mb-1">
                      选择 Gemini 模型版本
                    </label>
                    <select
                      value={googleModel}
                      onChange={(e) => setGoogleModel(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 py-2 px-3 text-sm text-gray-900 bg-white focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                    >
                      <option value="gemini-3.5-flash-lite">gemini-3.5-flash-lite（推荐 · 免费层支持 · 毫秒级极速响应）</option>
                      <option value="gemini-3.1-flash-lite">gemini-3.1-flash-lite（轻量高效 · 免费层支持）</option>
                      <option value="gemini-3.8-flash">gemini-3.8-flash（高性能 · 深度思考）</option>
                      <option value="gemini-2.5-flash">gemini-2.5-flash（多模态通用）</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-gray-700 mb-1">
                      Google Gemini API Token / Key
                    </label>
                    <div className="relative">
                      <KeyRound className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                      <input
                        type={showApiKey ? 'text' : 'password'}
                        value={googleApiKey}
                        onChange={(e) => setGoogleApiKey(e.target.value)}
                        placeholder="例如: AQ.Ab8RN6K..."
                        className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-10 text-sm font-mono text-gray-900 bg-white focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
                        title={showApiKey ? '隐藏密钥' : '显示密钥'}
                      >
                        {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pt-1 border-t border-brand-200/60">
                  <p className="text-xs text-gray-500">
                    💡 可在 <a href="https://aistudio.google.com/" target="_blank" rel="noreferrer" className="text-brand-600 hover:underline font-medium">Google AI Studio</a> 免费生成 API Key。新项目无需信用卡即可享有 1,500 次/天免费额度。
                  </p>
                  <button
                    type="button"
                    onClick={handleTestKey}
                    disabled={isTestingKey}
                    className="flex items-center gap-1.5 rounded-lg border border-brand-600 bg-white px-3.5 py-1.5 text-xs font-semibold text-brand-700 shadow-sm hover:bg-brand-50 focus:outline-none disabled:opacity-50 transition-colors shrink-0"
                  >
                    {isTestingKey ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        正在测试...
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-3.5 w-3.5 text-brand-600" />
                        测试连通性
                      </>
                    )}
                  </button>
                </div>

                {testResult && (
                  <div
                    className={`flex items-start gap-2.5 rounded-lg p-3 text-xs ${
                      testResult.valid
                        ? 'border border-emerald-200 bg-emerald-50 text-emerald-800'
                        : 'border border-red-200 bg-red-50 text-red-800'
                    }`}
                  >
                    {testResult.valid ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" />
                    ) : (
                      <AlertCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
                    )}
                    <div>
                      <div className="font-semibold">{testResult.valid ? '验证成功' : '验证失败'}</div>
                      <div className="mt-0.5">{testResult.message}</div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Display & Financial Coloring */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2.5 mb-4 text-gray-900 font-semibold border-b pb-3">
            <Palette className="h-5 w-5 text-brand-600" />
            <span>视觉与色彩体系（CONTRACTS.md §3）</span>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                涨跌色彩偏好
              </label>
              <p className="text-xs text-gray-500 mb-2">
                选择适合您的股票涨跌色彩习惯。K 线图与价格变动将依此方案渲染。
              </p>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setScheme('us')}
                  className={`rounded-lg border p-4 text-left transition-all ${
                    scheme === 'us'
                      ? 'border-brand-600 bg-brand-50 text-brand-900 ring-1 ring-brand-600'
                      : 'border-gray-200 bg-white hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm">美股 / 国际惯例（推荐）</span>
                    <span className="flex items-center gap-1 text-xs">
                      <span className="text-emerald-600 font-bold">▲ 绿涨</span>
                      <span className="text-red-600 font-bold">▼ 红跌</span>
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">绿色代表上涨，红色代表下跌</div>
                </button>

                <button
                  type="button"
                  onClick={() => setScheme('cn')}
                  className={`rounded-lg border p-4 text-left transition-all ${
                    scheme === 'cn'
                      ? 'border-brand-600 bg-brand-50 text-brand-900 ring-1 ring-brand-600'
                      : 'border-gray-200 bg-white hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm">A 股 / 港股习惯</span>
                    <span className="flex items-center gap-1 text-xs">
                      <span className="text-red-600 font-bold">▲ 红涨</span>
                      <span className="text-emerald-600 font-bold">▼ 绿跌</span>
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">红色代表上涨，绿色代表下跌</div>
                </button>
              </div>
            </div>

            <div className="pt-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">界面语言</label>
              <div className="relative max-w-xs">
                <Globe className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value as 'zh-CN' | 'en')}
                  className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm text-gray-900 bg-white focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                >
                  <option value="zh-CN">简体中文 (zh-CN)</option>
                  <option value="en">English (en)</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* Submit */}
        <div className="flex justify-end gap-3 pt-2">
          <button
            type="submit"
            disabled={isSaving}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-600 focus:ring-offset-2 disabled:opacity-60 transition-colors"
          >
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                正在保存...
              </>
            ) : (
              <>
                <Sliders className="h-4 w-4" />
                保存偏好设置
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

export default SettingsPage;
