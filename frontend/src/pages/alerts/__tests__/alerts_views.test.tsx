import { renderToString } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../../../contexts/AuthContext';
import { AlertRulesView } from '../AlertRulesView';
import { AlertHistoryView } from '../AlertHistoryView';
import { ChannelsConfigView } from '../ChannelsConfigView';
import { AlertsPage } from '../AlertsPage';
import { DailyReportsPage } from '../../reports/DailyReportsPage';
import { ReviewsDashboardView } from '../../research/ReviewsDashboardView';
import { AlertRead, NotificationChannelRead, AlertHistoryRead } from '../../../api/alerts';
import { MANDATORY_LEGAL_DISCLAIMER } from '../../../components/compliance/ComplianceDisclaimer';

function renderWithProviders(ui: React.ReactElement, initialRoute = '/alerts'): string {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return renderToString(
    <MemoryRouter initialEntries={[initialRoute]}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{ui}</AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const mockAlerts: AlertRead[] = [
  {
    id: 'alt-1',
    user_id: 'u-1',
    symbol: 'AAPL',
    alert_type: 'price',
    title: 'AAPL 突破 $230 阻力位',
    conditions: { direction: 'cross_above', target_price: 230 },
    channel_ids: [],
    status: 'active',
    last_triggered_at: null,
    trigger_count: 2,
    cooldown_minutes: 1440,
    created_at: '2026-11-17T12:00:00Z',
    updated_at: '2026-11-17T12:00:00Z',
  },
  {
    id: 'alt-2',
    user_id: 'u-1',
    symbol: 'NVDA',
    alert_type: 'thesis_breaker',
    title: '[NVDA] 论文破裂监控 - 毛利率低于 70%',
    conditions: { metric: 'gross_margin', operator: 'lt', threshold: 0.7, description: '毛利率低于 70%' },
    channel_ids: [],
    status: 'disabled',
    last_triggered_at: null,
    trigger_count: 0,
    cooldown_minutes: 1440,
    created_at: '2026-11-17T12:00:00Z',
    updated_at: '2026-11-17T12:00:00Z',
  },
];

const mockChannels: NotificationChannelRead[] = [
  {
    id: 'ch-1',
    user_id: 'u-1',
    channel_type: 'webhook',
    name: '飞书核心监控群',
    config: { webhook_url: 'https://open.feishu.cn/hook/test' },
    is_enabled: true,
    created_at: '2026-11-17T12:00:00Z',
    updated_at: '2026-11-17T12:00:00Z',
  },
];

const mockHistory: AlertHistoryRead[] = [
  {
    id: 'h-1',
    alert_id: 'alt-1',
    user_id: 'u-1',
    symbol: 'AAPL',
    alert_type: 'price',
    triggered_value: { current_price: 231.5 },
    message: 'AAPL 价格突破 $230 阈值，现价 $231.50',
    delivery_status: 'sent',
    delivered_channels: [{ channel_type: 'webhook', success: true }],
    created_at: '2026-11-17T15:30:00Z',
  },
];

describe('Alerts, Daily Reports & Reviews Views', () => {
  describe('AlertRulesView', () => {
    it('renders rules list, condition text, status badges and modal triggers', () => {
      const html = renderWithProviders(
        <AlertRulesView alerts={mockAlerts} onRefresh={vi.fn()} />,
      );

      expect(html).toContain('智能提醒与长期投资论文破裂规则');
      expect(html).toContain('AAPL');
      expect(html).toContain('NVDA');
      expect(html).toContain('AAPL 突破 $230 阻力位');
      expect(html).toContain('论文破裂');
      expect(html).toContain('新建提醒规则');
    });
  });

  describe('AlertHistoryView', () => {
    it('renders triggered audit log table, symbol and delivery status', () => {
      const html = renderWithProviders(
        <AlertHistoryView history={mockHistory} onRefresh={vi.fn()} />,
      );

      expect(html).toContain('提醒触发与分发历史审计流水');
      expect(html).toContain('AAPL');
      expect(html).toContain('全部送达');
      expect(html).toContain('详情快照');
    });
  });

  describe('ChannelsConfigView', () => {
    it('renders channel cards, test connectivity button and add channel trigger', () => {
      const html = renderWithProviders(
        <ChannelsConfigView channels={mockChannels} onRefresh={vi.fn()} />,
      );

      expect(html).toContain('多通道通知分发网关配置');
      expect(html).toContain('飞书核心监控群');
      expect(html).toContain('webhook');
      expect(html).toContain('测试连通性');
      expect(html).toContain('添加通知渠道');
    });
  });

  describe('AlertsPage', () => {
    it('renders top tabs and mandatory compliance disclaimer', () => {
      const html = renderWithProviders(<AlertsPage />);

      expect(html).toContain('提醒规则配置');
      expect(html).toContain('触发历史审计');
      expect(html).toContain('通知渠道与网关');
      expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
    });
  });

  describe('DailyReportsPage', () => {
    it('renders date selector, report type buttons and compliance footer', () => {
      const html = renderWithProviders(<DailyReportsPage />, '/reports/daily');

      expect(html).toContain('收盘全流程复盘与投研日报');
      expect(html).toContain('全市场收盘简报');
      expect(html).toContain('模拟投资组合复盘');
      expect(html).toContain('手动执行收盘工作流');
      expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
    });
  });

  describe('ReviewsDashboardView', () => {
    it('renders AI review dashboard header, metrics explanation and filter controls', () => {
      const html = renderWithProviders(<ReviewsDashboardView />);

      expect(html).toContain('AI 投资建议事后表现评估与胜率看板');
      expect(html).toContain('无未来函数严格复盘');
      expect(html).toContain('全部结论类型');
    });
  });
});
