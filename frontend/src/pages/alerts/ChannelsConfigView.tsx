import React, { useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Mail,
  Plus,
  Radio,
  Send,
  Trash2,
  Webhook,
} from 'lucide-react';
import {
  ChannelTestResult,
  ChannelType,
  NotificationChannelCreate,
  NotificationChannelRead,
  alertsApi,
} from '../../api/alerts';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Card } from '../../components/common/Card';
import { Input } from '../../components/common/Input';
import { Modal } from '../../components/common/Modal';

export interface ChannelsConfigViewProps {
  channels: NotificationChannelRead[];
  onRefresh: () => void;
}

export const ChannelsConfigView: React.FC<ChannelsConfigViewProps> = ({ channels, onRefresh }) => {
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ChannelTestResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Form State
  const [channelType, setChannelType] = useState<ChannelType>('webhook');
  const [name, setName] = useState<string>('');
  const [webhookUrl, setWebhookUrl] = useState<string>('');
  const [emailAddress, setEmailAddress] = useState<string>('');

  const handleTestChannel = async (channelId: string) => {
    setTestingId(channelId);
    setTestResult(null);
    try {
      const res = await alertsApi.testChannel(channelId);
      setTestResult(res);
    } catch (err: any) {
      alert(err.message || '连通性测试失败');
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = async (channelId: string) => {
    if (!window.confirm('确认删除该通知渠道？删除后关联规则将走默认站内信。')) return;
    try {
      await alertsApi.deleteChannel(channelId);
      onRefresh();
    } catch (err: unknown) {
      console.error('Failed to delete channel', err);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSubmitting(true);

    try {
      let config: Record<string, unknown> = {};

      if (channelType === 'webhook') {
        if (!webhookUrl.trim().startsWith('http')) {
          throw new Error('请输入以 http:// 或 https:// 开头的合法 Webhook URL');
        }
        config = { webhook_url: webhookUrl.trim() };
      } else if (channelType === 'email') {
        if (!emailAddress.includes('@')) {
          throw new Error('请输入有效的邮箱地址');
        }
        config = { email: emailAddress.trim() };
      }

      const payload: NotificationChannelCreate = {
        channel_type: channelType,
        name: name.trim() || `${channelType.toUpperCase()} 渠道`,
        config,
        is_enabled: true,
      };

      await alertsApi.createChannel(payload);
      setIsModalOpen(false);
      resetForm();
      onRefresh();
    } catch (err: any) {
      setErrorMsg(err.message || '创建通知渠道失败');
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setName('');
    setWebhookUrl('');
    setEmailAddress('');
    setErrorMsg(null);
  };

  const getChannelIcon = (type: ChannelType) => {
    switch (type) {
      case 'webhook':
        return <Webhook className="w-5 h-5 text-indigo-400" />;
      case 'email':
        return <Mail className="w-5 h-5 text-sky-400" />;
      case 'in_app':
      default:
        return <Radio className="w-5 h-5 text-emerald-400" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Radio className="w-5 h-5 text-indigo-400" />
            多通道通知分发网关配置
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            配置外部 Webhook（飞书、企业微信、钉钉、Discord）与邮件通知，支持一键发送测试探测包。
          </p>
        </div>

        <Button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500"
        >
          <Plus className="w-4 h-4" />
          添加通知渠道
        </Button>
      </div>

      {/* Test Result Toast/Banner */}
      {testResult && (
        <div
          className={`p-4 rounded-lg border flex items-center justify-between ${
            testResult.success
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
          }`}
        >
          <div className="flex items-center gap-2 text-sm">
            {testResult.success ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
            ) : (
              <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
            )}
            <span>
              渠道 <strong>[{testResult.channel_name}]</strong> 连通性测试{' '}
              {testResult.success ? '成功送达！' : '投递失败，请检查配置参数与网络可达性。'}
            </span>
          </div>
          <button
            onClick={() => setTestResult(null)}
            className="text-xs text-slate-400 hover:text-slate-200"
          >
            ✕
          </button>
        </div>
      )}

      {/* Channels Grid */}
      {channels.length === 0 ? (
        <Card className="p-8 text-center text-slate-400 border border-slate-800">
          <Radio className="w-12 h-12 mx-auto mb-3 text-slate-600 opacity-60" />
          <p className="text-base font-medium">尚未配置外部通知渠道</p>
          <p className="text-sm text-slate-500 mt-1">
            系统默认将提醒路由至站内信。添加 Webhook 或邮箱可实现即时移动端推达。
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {channels.map((ch) => (
            <Card
              key={ch.id}
              className="p-5 border border-slate-800 bg-slate-900/60 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 bg-slate-800 rounded-lg">{getChannelIcon(ch.channel_type)}</div>
                    <div>
                      <h3 className="text-sm font-semibold text-slate-100">{ch.name}</h3>
                      <span className="text-xs text-slate-400 uppercase font-mono">
                        {ch.channel_type}
                      </span>
                    </div>
                  </div>

                  <Badge variant={ch.is_enabled ? 'success' : 'neutral'}>
                    {ch.is_enabled ? '已启用' : '已停用'}
                  </Badge>
                </div>

                <div className="mt-4 p-2.5 bg-slate-950/60 rounded border border-slate-800/80 text-xs font-mono text-slate-300 break-all">
                  {ch.channel_type === 'webhook' && (
                    <span>URL: {String(ch.config?.webhook_url || '-')}</span>
                  )}
                  {ch.channel_type === 'email' && (
                    <span>邮箱: {String(ch.config?.email || '-')}</span>
                  )}
                  {ch.channel_type === 'in_app' && <span>系统默认站内信箱</span>}
                </div>
              </div>

              <div className="flex items-center justify-between mt-5 pt-3 border-t border-slate-800/60">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={testingId === ch.id}
                  onClick={() => handleTestChannel(ch.id)}
                  className="flex items-center gap-1.5 text-xs text-indigo-300 border-indigo-500/30 hover:bg-indigo-500/10"
                >
                  <Send className="w-3.5 h-3.5" />
                  {testingId === ch.id ? '正在探测...' : '测试连通性'}
                </Button>

                <button
                  onClick={() => handleDelete(ch.id)}
                  title="删除渠道"
                  className="p-1.5 text-rose-400 hover:bg-rose-500/10 rounded transition-colors text-xs"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          resetForm();
        }}
        title="配置新的通知渠道"
      >
        <form onSubmit={handleCreate} className="space-y-4">
          {errorMsg && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded text-rose-400 text-xs">
              {errorMsg}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">渠道类型</label>
            <select
              value={channelType}
              onChange={(e) => setChannelType(e.target.value as ChannelType)}
              className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="webhook">外部 Webhook（飞书 / 企微 / 钉钉 / Discord）</option>
              <option value="email">电子邮件通知 (Email)</option>
              <option value="in_app">系统内站内信 (In-App)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">渠道展示名称</label>
            <Input
              type="text"
              placeholder="例如: 核心持仓异动监控群"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {channelType === 'webhook' && (
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Webhook 目标 URL
              </label>
              <Input
                type="url"
                placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
              />
              <p className="text-xs text-slate-500 mt-1">
                支持通用 JSON Webhook，自动适配飞书、企业微信群机器人标准。
              </p>
            </div>
          )}

          {channelType === 'email' && (
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">接收通知邮箱</label>
              <Input
                type="email"
                placeholder="investor@example.com"
                value={emailAddress}
                onChange={(e) => setEmailAddress(e.target.value)}
              />
            </div>
          )}

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setIsModalOpen(false);
                resetForm();
              }}
            >
              取消
            </Button>
            <Button
              type="submit"
              disabled={submitting}
              className="bg-indigo-600 hover:bg-indigo-500"
            >
              {submitting ? '保存中...' : '添加并启用'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default ChannelsConfigView;
