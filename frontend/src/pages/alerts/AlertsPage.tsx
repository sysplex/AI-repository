import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Bell, History, Radio } from 'lucide-react';
import {
  AlertHistoryRead,
  AlertRead,
  NotificationChannelRead,
  alertsApi,
} from '../../api/alerts';
import { AlertRulesView } from './AlertRulesView';
import { AlertHistoryView } from './AlertHistoryView';
import { ChannelsConfigView } from './ChannelsConfigView';
import { ComplianceDisclaimer } from '../../components/compliance/ComplianceDisclaimer';

export type AlertsTabType = 'rules' | 'history' | 'channels';

export const AlertsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = (searchParams.get('tab') as AlertsTabType) || 'rules';
  const [activeTab, setActiveTab] = useState<AlertsTabType>(initialTab);

  const [alerts, setAlerts] = useState<AlertRead[]>([]);
  const [history, setHistory] = useState<AlertHistoryRead[]>([]);
  const [channels, setChannels] = useState<NotificationChannelRead[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const loadAllData = async () => {
    setLoading(true);
    try {
      const [alertsRes, historyRes, channelsRes] = await Promise.all([
        alertsApi.listAlerts({ limit: 100 }),
        alertsApi.listAlertHistory({ limit: 100 }),
        alertsApi.listChannels(),
      ]);
      setAlerts(alertsRes || []);
      setHistory(historyRes || []);
      setChannels(channelsRes || []);
    } catch (err: unknown) {
      console.error('Failed to load alerts data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAllData();
  }, []);

  const handleTabChange = (tab: AlertsTabType) => {
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Top Navigation Tabs */}
      <div className="border-b border-slate-800">
        <nav className="flex space-x-6">
          <button
            onClick={() => handleTabChange('rules')}
            className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
              activeTab === 'rules'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <Bell className="w-4 h-4" />
            提醒规则配置
            <span className="ml-1 px-1.5 py-0.5 text-xs bg-slate-800 text-slate-300 rounded-full">
              {alerts.length}
            </span>
          </button>

          <button
            onClick={() => handleTabChange('history')}
            className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
              activeTab === 'history'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <History className="w-4 h-4" />
            触发历史审计
            <span className="ml-1 px-1.5 py-0.5 text-xs bg-slate-800 text-slate-300 rounded-full">
              {history.length}
            </span>
          </button>

          <button
            onClick={() => handleTabChange('channels')}
            className={`flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
              activeTab === 'channels'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
            }`}
          >
            <Radio className="w-4 h-4" />
            通知渠道与网关
            <span className="ml-1 px-1.5 py-0.5 text-xs bg-slate-800 text-slate-300 rounded-full">
              {channels.length}
            </span>
          </button>
        </nav>
      </div>

      {/* Main Tab Content */}
      {loading ? (
        <div className="p-12 text-center text-slate-400">正在加载数据...</div>
      ) : (
        <>
          {activeTab === 'rules' && <AlertRulesView alerts={alerts} onRefresh={loadAllData} />}
          {activeTab === 'history' && (
            <AlertHistoryView history={history} onRefresh={loadAllData} />
          )}
          {activeTab === 'channels' && (
            <ChannelsConfigView channels={channels} onRefresh={loadAllData} />
          )}
        </>
      )}

      {/* Compliance Disclaimer Footer */}
      <ComplianceDisclaimer variant="banner" />
    </div>
  );
};

export default AlertsPage;
