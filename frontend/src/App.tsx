import React from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Shield, TrendingUp, BarChart2, Layers, Compass } from 'lucide-react';

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
      <BrowserRouter>
        <div className="min-h-screen bg-gray-50 text-gray-900 flex flex-col">
          {/* Header */}
          <header className="border-b bg-white px-6 py-4 flex items-center justify-between shadow-sm">
            <div className="flex items-center gap-3">
              <div className="bg-brand-600 p-2 rounded-lg text-white">
                <TrendingUp className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight text-gray-900">Stockpilot</h1>
                <p className="text-xs text-gray-500">智能美股投研与模拟交易平台</p>
              </div>
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
              <Link to="/login" className="px-3.5 py-1.5 bg-brand-600 text-white rounded-md hover:bg-brand-700 transition-colors">
                登录 / 注册
              </Link>
            </nav>
          </header>

          {/* Main Body */}
          <main className="flex-1 max-w-7xl w-full mx-auto p-6">
            <Routes>
              <Route
                path="/"
                element={
                  <div className="bg-white rounded-xl shadow-sm border p-8 text-center max-w-2xl mx-auto mt-12">
                    <h2 className="text-2xl font-bold mb-3">欢迎使用 Stockpilot 前端控制台</h2>
                    <p className="text-gray-600 mb-6 leading-relaxed">
                      基于 React 18 + TypeScript + Vite + Tailwind CSS 构建。前后端通过 OpenAPI 规范实现类型零偏差通信。
                    </p>
                    <div className="grid grid-cols-3 gap-4 text-left">
                      <div className="p-4 border rounded-lg bg-gray-50">
                        <div className="font-semibold text-gray-900 mb-1">强类型契约</div>
                        <div className="text-xs text-gray-500">57 个 API 路径，77 个 Schema 全自动化生成</div>
                      </div>
                      <div className="p-4 border rounded-lg bg-gray-50">
                        <div className="font-semibold text-gray-900 mb-1">高性能图表</div>
                        <div className="text-xs text-gray-500">TradingView Lightweight Charts 毫秒级交互</div>
                      </div>
                      <div className="p-4 border rounded-lg bg-gray-50">
                        <div className="font-semibold text-gray-900 mb-1">安全与合规</div>
                        <div className="text-xs text-gray-500">多租户隔离、Token 自动轮转、法定免责声明</div>
                      </div>
                    </div>
                  </div>
                }
              />
              <Route
                path="/watchlists"
                element={
                  <div className="bg-white rounded-xl shadow-sm border p-6">
                    <h2 className="text-xl font-bold mb-2">自选清单与热门主题</h2>
                    <p className="text-sm text-gray-500">由 M9-T06 交付完整功能</p>
                  </div>
                }
              />
              <Route
                path="/screener"
                element={
                  <div className="bg-white rounded-xl shadow-sm border p-6">
                    <h2 className="text-xl font-bold mb-2">策略量化筛选器</h2>
                    <p className="text-sm text-gray-500">由 M9-T06 交付完整功能</p>
                  </div>
                }
              />
              <Route
                path="/login"
                element={
                  <div className="bg-white rounded-xl shadow-sm border p-6 max-w-md mx-auto">
                    <h2 className="text-xl font-bold mb-2">用户登录</h2>
                    <p className="text-sm text-gray-500">由 M9-T02 交付完整功能</p>
                  </div>
                }
              />
            </Routes>
          </main>

          {/* Footer with Compliance Disclaimer */}
          <footer className="border-t bg-white px-6 py-4 text-center text-xs text-gray-500">
            <div className="flex items-center justify-center gap-1.5 mb-1 text-gray-600 font-medium">
              <Shield className="w-4 h-4 text-brand-600" />
              <span>法定合规免责声明</span>
            </div>
            <p>本平台所展示之所有信息与 AI 生成内容仅供个人研究与模拟学习，不构成任何投资建议。市场有风险，投资需谨慎。</p>
          </footer>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

export default App;
