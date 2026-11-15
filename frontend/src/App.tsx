import React from 'react';
import { BrowserRouter, Routes, Route, Link, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  Shield,
  TrendingUp,
  BarChart2,
  Layers,
  Compass,
  Sliders,
  Zap,
  Users,
  LogOut,
} from 'lucide-react';
import { AuthProvider } from './contexts/AuthContext';
import { useAuth } from './hooks/useAuth';
import ProtectedRoute from './components/auth/ProtectedRoute';
import AdminRoute from './components/auth/AdminRoute';
import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import ForgotPasswordPage from './pages/auth/ForgotPasswordPage';
import ResetPasswordPage from './pages/auth/ResetPasswordPage';
import SettingsPage from './pages/settings/SettingsPage';
import UsagePage from './pages/settings/UsagePage';
import AdminUsersPage from './pages/settings/AdminUsersPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30000,
    },
  },
});

const NavigationHeader: React.FC = () => {
  const { user, isAuthenticated, isAdmin, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <header className="border-b bg-white px-6 py-3.5 flex items-center justify-between shadow-sm sticky top-0 z-40">
      <div className="flex items-center gap-3">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="bg-brand-600 p-2 rounded-xl text-white shadow-sm">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-gray-900 leading-none">Stockpilot</h1>
            <p className="text-[10px] text-gray-500 font-medium">智能美股投研与模拟交易</p>
          </div>
        </Link>
      </div>

      <nav className="flex items-center gap-6 text-sm font-medium text-gray-600">
        <Link to="/" className="hover:text-brand-600 transition-colors flex items-center gap-1.5">
          <Compass className="w-4 h-4" /> 市场环境
        </Link>
        <Link to="/watchlists" className="hover:text-brand-600 transition-colors flex items-center gap-1.5">
          <Layers className="w-4 h-4" /> 自选与主题
        </Link>
        <Link to="/screener" className="hover:text-brand-600 transition-colors flex items-center gap-1.5">
          <BarChart2 className="w-4 h-4" /> 策略筛选
        </Link>

        {isAuthenticated ? (
          <>
            <Link to="/usage" className="hover:text-brand-600 transition-colors flex items-center gap-1.5">
              <Zap className="w-4 h-4 text-amber-500" /> AI 用量
            </Link>

            {isAdmin && (
              <Link to="/admin/users" className="hover:text-purple-600 transition-colors flex items-center gap-1.5 text-purple-700">
                <Users className="w-4 h-4" /> 用户管理
              </Link>
            )}

            <div className="flex items-center gap-3 pl-3 border-l">
              <Link
                to="/settings"
                className="flex items-center gap-2 text-xs font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200 px-3 py-1.5 rounded-lg transition-colors"
              >
                <Sliders className="w-3.5 h-3.5 text-gray-500" />
                <span className="max-w-[120px] truncate">{user?.email}</span>
              </Link>

              <button
                onClick={handleLogout}
                title="退出登录"
                className="text-gray-400 hover:text-red-600 p-1.5 rounded-md hover:bg-red-50 transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </>
        ) : (
          <div className="flex items-center gap-3">
            <Link
              to="/login"
              className="px-4 py-1.5 text-xs font-semibold text-brand-600 border border-brand-200 rounded-lg hover:bg-brand-50 transition-colors"
            >
              登录
            </Link>
            <Link
              to="/register"
              className="px-4 py-1.5 text-xs font-semibold text-white bg-brand-600 rounded-lg hover:bg-brand-700 transition-colors shadow-sm"
            >
              免费注册
            </Link>
          </div>
        )}
      </nav>
    </header>
  );
};

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <div className="min-h-screen bg-gray-50 text-gray-900 flex flex-col">
            <NavigationHeader />

            {/* Main Content Area */}
            <main className="flex-1 max-w-7xl w-full mx-auto p-6">
              <Routes>
                {/* 公开路由 */}
                <Route
                  path="/"
                  element={
                    <div className="bg-white rounded-xl shadow-sm border p-8 text-center max-w-2xl mx-auto mt-8">
                      <h2 className="text-2xl font-bold mb-3">欢迎使用 Stockpilot 智能控制台</h2>
                      <p className="text-gray-600 mb-6 text-sm leading-relaxed">
                        基于 React 18 + TypeScript + Vite + Tailwind CSS 构建。包含完整用户认证体系、多租户上下文隔离与 AI 配额实时统计。
                      </p>
                      <div className="grid grid-cols-3 gap-4 text-left">
                        <div className="p-4 border rounded-xl bg-gray-50">
                          <div className="font-semibold text-gray-900 mb-1 text-sm">用户认证体系</div>
                          <div className="text-xs text-gray-500">双令牌轮转、自动静默刷新与租户隔离</div>
                        </div>
                        <div className="p-4 border rounded-xl bg-gray-50">
                          <div className="font-semibold text-gray-900 mb-1 text-sm">AI 用量控制</div>
                          <div className="text-xs text-gray-500">每日 20 次配额仪表盘、熔断与高精计费</div>
                        </div>
                        <div className="p-4 border rounded-xl bg-gray-50">
                          <div className="font-semibold text-gray-900 mb-1 text-sm">管理员权限</div>
                          <div className="text-xs text-gray-500">RBAC 角色守卫与全租户用户监控</div>
                        </div>
                      </div>
                    </div>
                  }
                />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/register" element={<RegisterPage />} />
                <Route path="/forgot-password" element={<ForgotPasswordPage />} />
                <Route path="/reset-password" element={<ResetPasswordPage />} />

                {/* 登录受保护路由 */}
                <Route
                  path="/settings"
                  element={
                    <ProtectedRoute>
                      <SettingsPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/usage"
                  element={
                    <ProtectedRoute>
                      <UsagePage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/watchlists"
                  element={
                    <ProtectedRoute>
                      <div className="bg-white rounded-xl shadow-sm border p-6">
                        <h2 className="text-xl font-bold mb-2">自选清单与热门主题</h2>
                        <p className="text-sm text-gray-500">由 M9-T06 交付完整功能</p>
                      </div>
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/screener"
                  element={
                    <ProtectedRoute>
                      <div className="bg-white rounded-xl shadow-sm border p-6">
                        <h2 className="text-xl font-bold mb-2">策略量化筛选器</h2>
                        <p className="text-sm text-gray-500">由 M9-T06 交付完整功能</p>
                      </div>
                    </ProtectedRoute>
                  }
                />

                {/* 管理员受保护路由 */}
                <Route
                  path="/admin/users"
                  element={
                    <AdminRoute>
                      <AdminUsersPage />
                    </AdminRoute>
                  }
                />
              </Routes>
            </main>

            {/* Footer */}
            <footer className="border-t bg-white px-6 py-4 text-center text-xs text-gray-500">
              <div className="flex items-center justify-center gap-1.5 mb-1 text-gray-600 font-medium">
                <Shield className="w-4 h-4 text-brand-600" />
                <span>法定合规免责声明</span>
              </div>
              <p>本平台所展示之所有信息与 AI 生成内容仅供个人研究与模拟学习，不构成任何投资建议。市场有风险，投资需谨慎。</p>
            </footer>
          </div>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
};

export default App;
