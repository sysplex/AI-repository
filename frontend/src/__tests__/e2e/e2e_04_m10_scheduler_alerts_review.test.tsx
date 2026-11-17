import { renderToString } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../../contexts/AuthContext';
import { AlertsPage } from '../../pages/alerts/AlertsPage';
import { ChannelsConfigView } from '../../pages/alerts/ChannelsConfigView';
import { AlertRulesView } from '../../pages/alerts/AlertRulesView';
import { AlertHistoryView } from '../../pages/alerts/AlertHistoryView';
import { DailyReportsPage } from '../../pages/reports/DailyReportsPage';
import { ReviewsDashboardView } from '../../pages/research/ReviewsDashboardView';
import { AlertHistoryRead, AlertRead, NotificationChannelRead } from '../../api/alerts';
import { MANDATORY_LEGAL_DISCLAIMER } from '../../components/compliance/ComplianceDisclaimer';

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
  {
    id: 'ch-2',
    user_id: 'u-1',
    channel_type: 'email',
    name: '应急值班邮箱',
    config: { target_email: 'ops@stockpilot.internal' },
    is_enabled: true,
    created_at: '2026-11-17T12:00:00Z',
    updated_at: '2026-11-17T12:00:00Z',
  },
];

const mockAlerts: AlertRead[] = [
  {
    id: 'alt-1',
    user_id: 'u-1',
    symbol: 'AAPL',
    alert_type: 'price',
    title: 'AAPL 突破 $230 阻力位',
    conditions: { direction: 'cross_above', target_price: 230 },
    channel_ids: ['ch-1'],
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
    conditions: {
      metric: 'gross_margin',
      operator: 'lt',
      threshold: 0.7,
      description: '毛利率低于 70%',
    },
    channel_ids: ['ch-1'],
    status: 'disabled',
    last_triggered_at: null,
    trigger_count: 0,
    cooldown_minutes: 1440,
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

describe('E2E-04: M10 Scheduler, Alerts, Reviews & Ops Lifecycle (调度、提醒、复盘全流程)', () => {
  it('Step 1: Multi-Channel Notification Gateway Configuration (多渠道通知网关配置)', () => {
    // 渲染渠道配置视图
    const html = renderWithProviders(
      <ChannelsConfigView channels={mockChannels} onRefresh={vi.fn()} />,
    );

    // 1.1 核心说明文案与新增渠道按钮
    expect(html).toContain('多通道通知分发网关配置');
    expect(html).toContain('添加通知渠道');

    // 1.2 预置渠道展示 (Email / Webhook)
    expect(html).toContain('飞书核心监控群');
    expect(html).toContain('应急值班邮箱');
    expect(html).toContain('webhook');
    expect(html).toContain('email');
    expect(html).toContain('测试连通性');
  });

  it('Step 2: Smart Alert Rules & Thesis Breakers Management (智能告警与论文破裂规则管理)', () => {
    // 渲染提醒规则管理视图
    const html = renderWithProviders(<AlertRulesView alerts={mockAlerts} onRefresh={vi.fn()} />);

    // 2.1 规则标题与新增规则交互
    expect(html).toContain('智能提醒与长期投资论文破裂规则');
    expect(html).toContain('新建提醒规则');

    // 2.2 规则列表展示与标的代码
    expect(html).toContain('AAPL');
    expect(html).toContain('NVDA');
    expect(html).toContain('AAPL 突破 $230 阻力位');

    // 2.3 论文破裂与护城河特征
    expect(html).toContain('论文破裂');
  });

  it('Step 3: Alert Trigger Audit History & Channel Delivery Status (告警触发审计与投递流水)', () => {
    // 渲染警报历史视图
    const html = renderWithProviders(<AlertHistoryView history={mockHistory} onRefresh={vi.fn()} />);

    // 3.1 历史审计表头与状态
    expect(html).toContain('提醒触发与分发历史审计流水');
    expect(html).toContain('AAPL');
    expect(html).toContain('全部送达');
    expect(html).toContain('详情快照');
  });

  it('Step 4: Post-Market Daily Digest & Pipeline Trigger (收盘大盘/持仓日报与流水线补算)', () => {
    // 渲染每日复盘日报页面
    const html = renderWithProviders(<DailyReportsPage />, '/reports/daily');

    // 4.1 收盘日报核心要素与流水线触发按键
    expect(html).toContain('收盘全流程复盘与投研日报');
    expect(html).toContain('全市场收盘简报');
    expect(html).toContain('模拟投资组合复盘');
    expect(html).toContain('手动执行收盘工作流');

    // 4.2 合规免责声明底线
    expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
  });

  it('Step 5: AI Recommendation Outcomes & Continuous Review Dashboard (AI 投资建议事后收益与超额胜率复盘)', () => {
    // 渲染 AI 投资建议持续复盘看板
    const html = renderWithProviders(<ReviewsDashboardView />);

    // 5.1 整体复盘核心说明与评级过滤
    expect(html).toContain('AI 投资建议事后表现评估与胜率看板');
    expect(html).toContain('无未来函数严格复盘');
    expect(html).toContain('全部结论类型');
  });

  it('Step 6: Alerts Page Multi-Tab Seamless Navigation (提醒中心全景页面集成)', () => {
    // 渲染 AlertsPage 整合总页面
    const html = renderWithProviders(<AlertsPage />);

    expect(html).toContain('提醒规则配置');
    expect(html).toContain('触发历史审计');
    expect(html).toContain('通知渠道与网关');
    expect(html).toContain(MANDATORY_LEGAL_DISCLAIMER);
  });
});
