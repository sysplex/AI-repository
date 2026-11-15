import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Activity,
  BookmarkCheck,
  Brain,
  ChevronLeft,
  ChevronRight,
  Filter,
  LayoutDashboard,
  Settings,
  Shield,
  TrendingUp,
  Users,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { cn } from '../../utils/cn';

export interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  badge?: string;
  adminOnly?: boolean;
}

export const navItems: NavItem[] = [
  {
    label: '市场总览',
    path: '/dashboard',
    icon: <LayoutDashboard className="h-5 w-5" />,
  },
  {
    label: 'AI 投研决策',
    path: '/research',
    icon: <Brain className="h-5 w-5" />,
    badge: 'AI',
  },
  {
    label: '策略筛选器',
    path: '/screener',
    icon: <Filter className="h-5 w-5" />,
  },
  {
    label: '主题与自选',
    path: '/themes',
    icon: <BookmarkCheck className="h-5 w-5" />,
  },
  {
    label: '模拟盘交易',
    path: '/simbroker',
    icon: <TrendingUp className="h-5 w-5" />,
  },
  {
    label: '系统与偏好',
    path: '/settings',
    icon: <Settings className="h-5 w-5" />,
  },
  {
    label: '多租户管理',
    path: '/admin/users',
    icon: <Users className="h-5 w-5" />,
    adminOnly: true,
  },
];

export interface SidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isCollapsed, onToggleCollapse }) => {
  const { isAdmin } = useAuth();

  const filteredNavItems = navItems.filter((item) => !item.adminOnly || isAdmin);

  return (
    <aside
      className={cn(
        'hidden lg:flex flex-col border-r border-slate-800 bg-slate-950 transition-all duration-300 z-40 select-none',
        isCollapsed ? 'w-20' : 'w-64',
      )}
    >
      {/* Brand Header */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-slate-800">
        <NavLink
          to="/dashboard"
          className="flex items-center gap-2.5 overflow-hidden font-bold tracking-tight text-white hover:opacity-90 transition-opacity"
        >
          <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center text-white shadow-md shadow-blue-500/20 shrink-0">
            <Activity className="h-5 w-5" />
          </div>
          {!isCollapsed && (
            <div className="flex flex-col">
              <span className="text-base font-bold bg-gradient-to-r from-blue-400 via-indigo-300 to-white bg-clip-text text-transparent">
                StockPilot
              </span>
              <span className="text-[10px] text-slate-400 font-mono tracking-widest uppercase">
                AI Trading Suite
              </span>
            </div>
          )}
        </NavLink>

        <button
          onClick={onToggleCollapse}
          className="text-slate-500 hover:text-slate-200 p-1.5 rounded-lg hover:bg-slate-900 transition-colors"
          title={isCollapsed ? '展开导航栏' : '折叠导航栏'}
          aria-label={isCollapsed ? '展开导航栏' : '折叠导航栏'}
        >
          {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>

      {/* Navigation List */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {filteredNavItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all group relative',
                isActive
                  ? 'bg-blue-600 text-white shadow-sm shadow-blue-600/30'
                  : 'text-slate-400 hover:text-slate-100 hover:bg-slate-900',
                isCollapsed && 'justify-center px-0',
              )
            }
            title={isCollapsed ? item.label : undefined}
          >
            <span className="shrink-0">{item.icon}</span>
            {!isCollapsed && (
              <span className="flex-1 truncate">{item.label}</span>
            )}
            {!isCollapsed && item.badge && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                {item.badge}
              </span>
            )}
            {!isCollapsed && item.adminOnly && (
              <span className="p-0.5 text-purple-400">
                <Shield className="h-3 w-3" />
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer Info */}
      <div className="p-4 border-t border-slate-800/80 text-xs text-slate-500">
        {!isCollapsed ? (
          <div className="space-y-1">
            <div className="flex items-center justify-between font-mono text-[11px]">
              <span>StockPilot Web</span>
              <span className="text-slate-400">v0.9.0</span>
            </div>
            <p className="text-[10px] text-slate-400 truncate">模拟研究 · 严谨合规</p>
          </div>
        ) : (
          <div className="text-center font-mono text-[10px] text-slate-400">v0.9</div>
        )}
      </div>
    </aside>
  );
};
