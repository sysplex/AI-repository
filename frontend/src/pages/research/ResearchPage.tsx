import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Brain,
  ShieldCheck,
  Scale,
  Hourglass,
  PieChart,
} from 'lucide-react';
import { StockDeepDiveView } from './StockDeepDiveView';
import { BuyDecisionView } from './BuyDecisionView';
import { StockCompareView } from './StockCompareView';
import { LongTermView } from './LongTermView';
import { PortfolioView } from './PortfolioView';
import { cn } from '../../utils/cn';

export type ResearchTabType =
  | 'deep-dive'
  | 'buy-decision'
  | 'compare'
  | 'long-term'
  | 'portfolio';

export const ResearchPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  const tabParam = (searchParams.get('tab') as ResearchTabType) || 'deep-dive';
  const symbolParam = searchParams.get('symbol') || 'NVDA';

  const [activeTab, setActiveTab] = useState<ResearchTabType>(tabParam);
  const [currentSymbol, setCurrentSymbol] = useState<string>(symbolParam);

  useEffect(() => {
    const t = searchParams.get('tab') as ResearchTabType;
    if (t && t !== activeTab) {
      setActiveTab(t);
    }
    const s = searchParams.get('symbol');
    if (s && s !== currentSymbol) {
      setCurrentSymbol(s);
    }
  }, [searchParams]);

  const handleTabChange = (tab: ResearchTabType) => {
    setActiveTab(tab);
    setSearchParams({ tab, symbol: currentSymbol });
  };

  const handleSelectSymbol = (sym: string) => {
    setCurrentSymbol(sym);
    setSearchParams({ tab: activeTab, symbol: sym });
  };

  const tabs = [
    {
      id: 'deep-dive' as const,
      label: '个股研报与财报',
      icon: <Brain className="h-4 w-4" />,
    },
    {
      id: 'buy-decision' as const,
      label: '买入决策评估',
      icon: <ShieldCheck className="h-4 w-4" />,
    },
    {
      id: 'compare' as const,
      label: '多标的横向对比',
      icon: <Scale className="h-4 w-4" />,
    },
    {
      id: 'long-term' as const,
      label: '长期持有与破裂监控',
      icon: <Hourglass className="h-4 w-4" />,
    },
    {
      id: 'portfolio' as const,
      label: '组合配置优化',
      icon: <PieChart className="h-4 w-4" />,
    },
  ];

  return (
    <div className="space-y-6">
      {/* 顶部主选项卡切换栏 */}
      <div className="border-b border-slate-800 bg-slate-900/60 p-1.5 rounded-xl flex items-center gap-1.5 overflow-x-auto select-none">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabChange(tab.id)}
            className={cn(
              'flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-all',
              activeTab === tab.id
                ? 'bg-blue-600 text-white shadow-sm shadow-blue-900/30'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/60',
            )}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* 渲染对应视图 */}
      <div>
        {activeTab === 'deep-dive' && (
          <StockDeepDiveView
            initialSymbol={currentSymbol}
            onSelectSymbol={handleSelectSymbol}
          />
        )}
        {activeTab === 'buy-decision' && (
          <BuyDecisionView initialSymbol={currentSymbol} />
        )}
        {activeTab === 'compare' && <StockCompareView />}
        {activeTab === 'long-term' && <LongTermView initialSymbol={currentSymbol} />}
        {activeTab === 'portfolio' && <PortfolioView />}
      </div>
    </div>
  );
};

export default ResearchPage;
