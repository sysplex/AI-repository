import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { BookmarkCheck, Filter, Flame } from 'lucide-react';
import { ScreenerConsoleView } from './ScreenerConsoleView';
import { ThemesView } from './ThemesView';
import { WatchlistsView } from './WatchlistsView';
import { cn } from '../../utils/cn';

export type ScreenerTabType = 'screener' | 'themes' | 'watchlists';

export interface ScreenerPageProps {
  initialTab?: ScreenerTabType;
}

export const ScreenerPage: React.FC<ScreenerPageProps> = ({ initialTab }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Determine active tab based on path or query param or initialTab prop
  const getInitialTab = (): ScreenerTabType => {
    if (initialTab) return initialTab;
    const tabParam = searchParams.get('tab') as ScreenerTabType;
    if (tabParam && ['screener', 'themes', 'watchlists'].includes(tabParam)) {
      return tabParam;
    }
    if (location.pathname.includes('/watchlists')) return 'watchlists';
    if (location.pathname.includes('/themes')) return 'themes';
    return 'screener';
  };

  const [activeTab, setActiveTab] = useState<ScreenerTabType>(getInitialTab);

  useEffect(() => {
    const tabParam = searchParams.get('tab') as ScreenerTabType;
    if (tabParam && ['screener', 'themes', 'watchlists'].includes(tabParam)) {
      setActiveTab(tabParam);
    } else if (location.pathname.includes('/watchlists')) {
      setActiveTab('watchlists');
    } else if (location.pathname.includes('/themes')) {
      setActiveTab('themes');
    } else if (location.pathname.includes('/screener')) {
      setActiveTab('screener');
    }
  }, [location.pathname, searchParams]);

  const handleTabChange = (tab: ScreenerTabType) => {
    setActiveTab(tab);
    navigate(`/${tab}`);
  };

  const tabs = [
    {
      id: 'screener' as const,
      label: '策略筛选器',
      sub: '多因子量化选股',
      icon: <Filter className="h-4 w-4" />,
    },
    {
      id: 'themes' as const,
      label: '热门主题投资库',
      sub: 'AI 成分股投研卡片',
      icon: <Flame className="h-4 w-4 text-amber-500" />,
    },
    {
      id: 'watchlists' as const,
      label: '自选清单工作台',
      sub: '多清单与目标价监控',
      icon: <BookmarkCheck className="h-4 w-4 text-blue-400" />,
    },
  ];

  return (
    <div className="space-y-6">
      {/* Top Banner & Tab Navigation */}
      <div className="pb-2 border-b border-slate-800">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              策略筛选与主题自选工作台
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              基于全股票池量化模型扫描、F9 热门宏观主题卡片与个性化多自选清单管理，无缝衔接 AI 深度投研与决策评估。
            </p>
          </div>

          {/* Navigation Tab Buttons */}
          <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-900 border border-slate-800 shrink-0 self-start">
            {tabs.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => handleTabChange(tab.id)}
                  className={cn(
                    'flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all select-none',
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

      {/* Tab Content Views */}
      <div className="pt-2">
        {activeTab === 'screener' && <ScreenerConsoleView />}
        {activeTab === 'themes' && <ThemesView />}
        {activeTab === 'watchlists' && <WatchlistsView />}
      </div>
    </div>
  );
};

export default ScreenerPage;
