import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/auth/ProtectedRoute';
import AdminRoute from './components/auth/AdminRoute';
import { AppLayout } from './components/layout/AppLayout';
import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import ForgotPasswordPage from './pages/auth/ForgotPasswordPage';
import ResetPasswordPage from './pages/auth/ResetPasswordPage';
import DashboardPage from './pages/dashboard/DashboardPage';
import SettingsPage from './pages/settings/SettingsPage';
import UsagePage from './pages/settings/UsagePage';
import AdminUsersPage from './pages/settings/AdminUsersPage';
import { ComplianceDisclaimer } from './components/compliance/ComplianceDisclaimer';
import { AIPromptVersionBadge } from './components/compliance/AIPromptVersionBadge';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30000,
    },
  },
});

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            {/* 独立认证页面（无侧边栏布局） */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />

            {/* 主应用路由（全部在 AppLayout 统一框架中呈现） */}
            <Route element={<AppLayout />}>
              {/* 公开/访客首页与仪表盘 */}
              <Route path="/" element={<DashboardPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />

              {/* 登录受保护业务路由 */}
              <Route
                path="/research"
                element={
                  <ProtectedRoute>
                    <div className="space-y-6">
                      <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                        <div>
                          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
                            AI 投研与多维买入决策全景
                          </h1>
                          <p className="text-xs text-slate-400 mt-1">
                            包含技术面判定、基本面财务雷达、多标的对比与长线持有价值推演
                          </p>
                        </div>
                        <AIPromptVersionBadge model="deepseek-chat" promptVersion="v1.2.0" />
                      </div>
                      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-8 text-center text-slate-400 space-y-3">
                        <p className="text-sm">该模块核心视图由 M9-T05 交付，已准备就绪。</p>
                      </div>
                      <ComplianceDisclaimer variant="card" />
                    </div>
                  </ProtectedRoute>
                }
              />

              <Route
                path="/screener"
                element={
                  <ProtectedRoute>
                    <div className="space-y-6">
                      <div className="pb-2 border-b border-slate-800">
                        <h1 className="text-2xl font-bold text-white">策略筛选器</h1>
                        <p className="text-xs text-slate-400 mt-1">多因子指标筛选与估值分位数过滤</p>
                      </div>
                      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-8 text-center text-slate-400">
                        <p className="text-sm">该模块核心视图由 M9-T06 交付，已准备就绪。</p>
                      </div>
                      <ComplianceDisclaimer variant="card" />
                    </div>
                  </ProtectedRoute>
                }
              />

              <Route
                path="/themes"
                element={
                  <ProtectedRoute>
                    <div className="space-y-6">
                      <div className="pb-2 border-b border-slate-800">
                        <h1 className="text-2xl font-bold text-white">主题投研与自选清单</h1>
                        <p className="text-xs text-slate-400 mt-1">热门宏观主题（AI 算力、半导体、减肥药）与定制自选组</p>
                      </div>
                      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-8 text-center text-slate-400">
                        <p className="text-sm">该模块核心视图由 M9-T06 交付，已准备就绪。</p>
                      </div>
                      <ComplianceDisclaimer variant="card" />
                    </div>
                  </ProtectedRoute>
                }
              />

              <Route path="/watchlists" element={<Navigate to="/themes" replace />} />

              <Route
                path="/simbroker"
                element={
                  <ProtectedRoute>
                    <div className="space-y-6">
                      <div className="pb-2 border-b border-slate-800">
                        <h1 className="text-2xl font-bold text-white">SimBroker 模拟盘控制台</h1>
                        <p className="text-xs text-slate-400 mt-1">模拟买卖下单、持仓浮盈与 AI 交易复盘日志</p>
                      </div>
                      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-8 text-center text-slate-400">
                        <p className="text-sm">该模块核心视图由 M9-T07 交付，已准备就绪。</p>
                      </div>
                      <ComplianceDisclaimer variant="card" />
                    </div>
                  </ProtectedRoute>
                }
              />

              <Route
                path="/settings"
                element={
                  <ProtectedRoute>
                    <SettingsPage />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/settings/usage"
                element={
                  <ProtectedRoute>
                    <UsagePage />
                  </ProtectedRoute>
                }
              />
              <Route path="/usage" element={<Navigate to="/settings/usage" replace />} />

              {/* 管理员受保护路由 */}
              <Route
                path="/admin/users"
                element={
                  <AdminRoute>
                    <AdminUsersPage />
                  </AdminRoute>
                }
              />

              {/* 兜底 404 跳转首页 */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
};

export default App;
