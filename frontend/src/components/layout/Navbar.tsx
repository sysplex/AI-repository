import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Menu,
  Search,
  Settings,
  Shield,
  User as UserIcon,
  LogOut,
  Zap,
  Palette,
  ChevronDown,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { getUSMarketStatus } from '../../utils/market';
import { Badge } from '../common/Badge';

export interface NavbarProps {
  onOpenMobileMenu: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onOpenMobileMenu }) => {
  const { user, logout, isAdmin, colorScheme, setColorScheme } = useAuth();
  const navigate = useNavigate();

  const [searchQuery, setSearchQuery] = useState('');
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const marketStatus = getUSMarketStatus();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const symbol = searchQuery.trim().toUpperCase();
    if (symbol) {
      navigate(`/research?symbol=${encodeURIComponent(symbol)}`);
      setSearchQuery('');
    }
  };

  const toggleColorScheme = () => {
    setColorScheme(colorScheme === 'us' ? 'cn' : 'us');
  };

  const handleLogout = async () => {
    setIsUserMenuOpen(false);
    await logout();
    navigate('/login');
  };

  return (
    <header className="sticky top-0 z-30 h-16 w-full border-b border-slate-800 bg-slate-900/90 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between gap-4">
      {/* Left side: Mobile menu toggle + Global quick search */}
      <div className="flex items-center gap-3 flex-1 max-w-lg">
        <button
          onClick={onOpenMobileMenu}
          className="lg:hidden text-slate-400 hover:text-white p-2 rounded-lg hover:bg-slate-800 transition-colors"
          aria-label="打开导航菜单"
        >
          <Menu className="h-5 w-5" />
        </button>

        {/* Global Stock Search */}
        <form onSubmit={handleSearch} className="relative w-full max-w-xs sm:max-w-sm">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
            <Search className="h-4 w-4" />
          </div>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索代码 (如 AAPL, NVDA)..."
            className="w-full rounded-lg bg-slate-950/80 border border-slate-700/80 pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
          />
        </form>
      </div>

      {/* Right side: Market Status + Quota + Theme Toggle + User Menu */}
      <div className="flex items-center gap-2.5 sm:gap-4 shrink-0">
        {/* US Market Status */}
        <div
          className={`hidden md:inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-mono border ${marketStatus.badgeClass}`}
          title={`美股交易时段: ${marketStatus.sublabel}`}
        >
          <span className="relative flex h-2 w-2">
            <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${marketStatus.dotClass}`} />
            <span className={`relative inline-flex rounded-full h-2 w-2 ${marketStatus.dotClass.replace('animate-ping', '').replace('animate-pulse', '')}`} />
          </span>
          <span className="font-medium">{marketStatus.label}</span>
        </div>

        {/* Quota Link */}
        <Link
          to="/settings/usage"
          className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium text-slate-300 bg-slate-800/80 border border-slate-700 hover:border-slate-600 transition-colors"
          title="每日 AI 投研免费配额（20 次/日）"
        >
          <Zap className="h-3.5 w-3.5 text-amber-400" />
          <span>配额中心</span>
        </Link>

        {/* Color Scheme Switcher */}
        <button
          onClick={toggleColorScheme}
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium text-slate-300 bg-slate-800/60 border border-slate-700 hover:border-slate-600 transition-colors"
          title={`当前色彩模式: ${colorScheme === 'us' ? '美股国际模式（绿涨红跌）' : 'A 股习惯模式（红涨绿跌）'}，点击切换`}
        >
          <Palette className="h-3.5 w-3.5 text-blue-400" />
          <span className="hidden sm:inline font-mono">
            {colorScheme === 'us' ? '绿涨红跌' : '红涨绿跌'}
          </span>
        </button>

        {/* User Profile Dropdown */}
        <div className="relative">
          <button
            onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
            className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
            aria-expanded={isUserMenuOpen}
          >
            <div className="h-8 w-8 rounded-full bg-blue-600/30 border border-blue-500/40 flex items-center justify-center text-blue-300 font-semibold text-xs">
              {user?.email?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="hidden lg:flex flex-col items-start text-left">
              <span className="text-xs font-medium text-slate-200 max-w-[120px] truncate">
                {user?.email || '账户'}
              </span>
              <span className="text-[10px] text-slate-400 capitalize">{user?.role || 'user'}</span>
            </div>
            <ChevronDown className="h-3.5 w-3.5 text-slate-400 hidden lg:inline" />
          </button>

          {isUserMenuOpen && (
            <>
              <div
                className="fixed inset-0 z-30"
                onClick={() => setIsUserMenuOpen(false)}
                aria-hidden="true"
              />
              <div className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-700/80 bg-slate-900 py-1 text-slate-200 shadow-xl z-40">
                <div className="px-4 py-3 border-b border-slate-800">
                  <p className="text-xs text-slate-400">当前登录用户</p>
                  <p className="text-sm font-medium text-white truncate mt-0.5">{user?.email}</p>
                  {isAdmin && (
                    <Badge variant="purple" size="xs" className="mt-1.5">
                      <Shield className="h-2.5 w-2.5" />
                      管理员权限
                    </Badge>
                  )}
                </div>

                <div className="py-1">
                  <Link
                    to="/settings"
                    onClick={() => setIsUserMenuOpen(false)}
                    className="flex items-center gap-2.5 px-4 py-2 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
                  >
                    <Settings className="h-4 w-4 text-slate-400" />
                    偏好与风险设置
                  </Link>
                  <Link
                    to="/settings/usage"
                    onClick={() => setIsUserMenuOpen(false)}
                    className="flex items-center gap-2.5 px-4 py-2 text-xs text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
                  >
                    <Zap className="h-4 w-4 text-amber-400" />
                    配额与用量统计
                  </Link>
                  {isAdmin && (
                    <Link
                      to="/admin/users"
                      onClick={() => setIsUserMenuOpen(false)}
                      className="flex items-center gap-2.5 px-4 py-2 text-xs text-purple-300 hover:bg-slate-800 hover:text-purple-200 transition-colors"
                    >
                      <UserIcon className="h-4 w-4 text-purple-400" />
                      多租户用户管理
                    </Link>
                  )}
                </div>

                <div className="border-t border-slate-800 pt-1">
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2.5 px-4 py-2 text-xs text-rose-400 hover:bg-rose-950/30 hover:text-rose-300 transition-colors"
                  >
                    <LogOut className="h-4 w-4" />
                    退出登录
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
};
