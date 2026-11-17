import React, { useState } from 'react';
import {
  AlertTriangle,
  Bell,
  Clock,
  Filter,
  Plus,
  Power,
  Trash2,
} from 'lucide-react';
import {
  AlertCreate,
  AlertRead,
  AlertStatus,
  AlertType,
  alertsApi,
} from '../../api/alerts';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Card } from '../../components/common/Card';
import { Input } from '../../components/common/Input';
import { Modal } from '../../components/common/Modal';

export interface AlertRulesViewProps {
  alerts: AlertRead[];
  onRefresh: () => void;
}

export const AlertRulesView: React.FC<AlertRulesViewProps> = ({ alerts, onRefresh }) => {
  const [filterType, setFilterType] = useState<string>('all');
  const [filterSymbol, setFilterSymbol] = useState<string>('');
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Form State
  const [symbol, setSymbol] = useState<string>('');
  const [alertType, setAlertType] = useState<AlertType>('price');
  const [title, setTitle] = useState<string>('');
  const [priceDirection, setPriceDirection] = useState<'cross_above' | 'cross_below'>('cross_above');
  const [targetPrice, setTargetPrice] = useState<string>('');
  const [techIndicator, setTechIndicator] = useState<string>('RSI');
  const [techOperator, setTechOperator] = useState<string>('gt');
  const [techThreshold, setTechThreshold] = useState<string>('70');
  const [earningsDaysBefore, setEarningsDaysBefore] = useState<number>(3);
  const [thesisMetric, setThesisMetric] = useState<string>('gross_margin');
  const [thesisOperator, setThesisOperator] = useState<string>('lt');
  const [thesisThreshold, setThesisThreshold] = useState<string>('0.40');
  const [thesisDesc, setThesisDesc] = useState<string>('毛利率低于 40% 说明护城河受损');
  const [cooldownMinutes, setCooldownMinutes] = useState<number>(1440);

  const filteredAlerts = alerts.filter((a) => {
    if (filterType !== 'all' && a.alert_type !== filterType) return false;
    if (filterSymbol.trim() && a.symbol && !a.symbol.toLowerCase().includes(filterSymbol.toLowerCase().trim())) {
      return false;
    }
    return true;
  });

  const handleToggleStatus = async (alert: AlertRead) => {
    try {
      const newStatus: AlertStatus = alert.status === 'active' ? 'disabled' : 'active';
      await alertsApi.updateAlert(alert.id, { status: newStatus });
      onRefresh();
    } catch (err: unknown) {
      console.error('Failed to toggle alert status', err);
    }
  };

  const handleDelete = async (alertId: string) => {
    if (!window.confirm('确认删除该提醒规则？')) return;
    try {
      await alertsApi.deleteAlert(alertId);
      onRefresh();
    } catch (err: unknown) {
      console.error('Failed to delete alert', err);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSubmitting(true);

    try {
      let conditions: Record<string, unknown> = {};

      if (alertType === 'price') {
        if (!targetPrice || Number(targetPrice) <= 0) {
          throw new Error('请输入有效的目标触发价格');
        }
        conditions = {
          direction: priceDirection,
          target_price: Number(targetPrice),
        };
      } else if (alertType === 'technical_signal') {
        conditions = {
          indicator: techIndicator,
          operator: techOperator,
          threshold: Number(techThreshold),
        };
      } else if (alertType === 'earnings_date') {
        conditions = {
          days_before: Number(earningsDaysBefore),
        };
      } else if (alertType === 'thesis_breaker') {
        conditions = {
          metric: thesisMetric,
          operator: thesisOperator,
          threshold: Number(thesisThreshold),
          description: thesisDesc,
        };
      }

      const payload: AlertCreate = {
        symbol: symbol.trim() ? symbol.trim().toUpperCase() : null,
        alert_type: alertType,
        title: title.trim() || `${symbol || '大盘'} ${alertType} 提醒`,
        conditions,
        cooldown_minutes: Number(cooldownMinutes) || 1440,
      };

      await alertsApi.createAlert(payload);
      setIsModalOpen(false);
      resetForm();
      onRefresh();
    } catch (err: any) {
      setErrorMsg(err.message || '创建提醒规则失败');
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setSymbol('');
    setTitle('');
    setTargetPrice('');
    setErrorMsg(null);
  };

  const renderConditionsText = (alert: AlertRead) => {
    const c = alert.conditions || {};
    if (alert.alert_type === 'price') {
      const dirText = c.direction === 'cross_above' ? '向上突破' : '向下跌破';
      return `现价 ${dirText} $${c.target_price}`;
    }
    if (alert.alert_type === 'technical_signal') {
      return `指标 ${c.indicator} ${c.operator} ${c.threshold}`;
    }
    if (alert.alert_type === 'earnings_date') {
      return `距离财报披露日前 ${c.days_before} 天`;
    }
    if (alert.alert_type === 'thesis_breaker') {
      return `[破裂] ${c.description || `${c.metric} ${c.operator} ${c.threshold}`}`;
    }
    return JSON.stringify(c);
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Bell className="w-5 h-5 text-indigo-400" />
            智能提醒与长期投资论文破裂规则
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            实时监测股价穿越、量化指标信号、财报日程以及 M7 长期持有护城河论文破裂风险。
          </p>
        </div>

        <Button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500"
        >
          <Plus className="w-4 h-4" />
          新建提醒规则
        </Button>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center gap-3 bg-slate-900/80 p-3 rounded-lg border border-slate-800">
        <Filter className="w-4 h-4 text-slate-400" />
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded px-3 py-1.5 focus:outline-none focus:border-indigo-500"
        >
          <option value="all">全部类型</option>
          <option value="price">价格预警</option>
          <option value="technical_signal">技术形态</option>
          <option value="earnings_date">财报提醒</option>
          <option value="thesis_breaker">论文破裂</option>
        </select>

        <input
          type="text"
          placeholder="按标的代码筛选 (如 AAPL)"
          value={filterSymbol}
          onChange={(e) => setFilterSymbol(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded px-3 py-1.5 w-48 focus:outline-none focus:border-indigo-500"
        />

        <div className="text-xs text-slate-400 ml-auto">
          当前生效: <span className="text-emerald-400 font-semibold">{filteredAlerts.length}</span> 条规则
        </div>
      </div>

      {/* Rules List */}
      {filteredAlerts.length === 0 ? (
        <Card className="p-8 text-center text-slate-400 border border-slate-800">
          <Bell className="w-12 h-12 mx-auto mb-3 text-slate-600 opacity-60" />
          <p className="text-base font-medium">暂无符合条件的提醒规则</p>
          <p className="text-sm text-slate-500 mt-1">点击右上角“新建提醒规则”开始监控</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredAlerts.map((alert) => (
            <Card
              key={alert.id}
              className={`p-4 border transition-colors ${
                alert.status === 'active'
                  ? 'border-slate-800 bg-slate-900/60'
                  : 'border-slate-800/40 bg-slate-950/40 opacity-75'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    {alert.symbol && (
                      <span className="font-mono font-bold text-base text-indigo-300">
                        {alert.symbol}
                      </span>
                    )}
                    <Badge
                      variant={
                        alert.alert_type === 'thesis_breaker'
                          ? 'danger'
                          : alert.alert_type === 'price'
                          ? 'info'
                          : 'default'
                      }
                    >
                      {alert.alert_type === 'price' && '价格突破'}
                      {alert.alert_type === 'technical_signal' && '技术信号'}
                      {alert.alert_type === 'earnings_date' && '财报日'}
                      {alert.alert_type === 'thesis_breaker' && '论文破裂'}
                    </Badge>
                    <Badge variant={alert.status === 'active' ? 'success' : 'neutral'}>
                      {alert.status === 'active' ? '监控中' : '已停用'}
                    </Badge>
                  </div>

                  <h3 className="text-sm font-semibold text-slate-200 mt-1 truncate">
                    {alert.title}
                  </h3>

                  <p className="text-xs text-slate-300 mt-2 bg-slate-800/50 p-2 rounded border border-slate-800/80">
                    <span className="text-slate-400">触发条件：</span>
                    {renderConditionsText(alert)}
                  </p>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    onClick={() => handleToggleStatus(alert)}
                    title={alert.status === 'active' ? '停用规则' : '启用规则'}
                    className={`p-1.5 rounded text-xs transition-colors ${
                      alert.status === 'active'
                        ? 'text-emerald-400 hover:bg-emerald-500/10'
                        : 'text-slate-500 hover:bg-slate-800'
                    }`}
                  >
                    <Power className="w-4 h-4" />
                  </button>

                  <button
                    onClick={() => handleDelete(alert.id)}
                    title="删除规则"
                    className="p-1.5 rounded text-xs text-rose-400 hover:bg-rose-500/10 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-800/60 text-xs text-slate-400">
                <span className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5 text-slate-500" />
                  冷却: {alert.cooldown_minutes} 分钟
                </span>
                <span>累计触发: {alert.trigger_count} 次</span>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Alert Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          resetForm();
        }}
        title="新建智能提醒规则"
      >
        <form onSubmit={handleCreate} className="space-y-4">
          {errorMsg && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded text-rose-400 text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {errorMsg}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              提醒规则类型
            </label>
            <select
              value={alertType}
              onChange={(e) => setAlertType(e.target.value as AlertType)}
              className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="price">价格预警 (Price Alert)</option>
              <option value="technical_signal">技术指标形态 (Technical Signal)</option>
              <option value="earnings_date">财报日前夕倒计时 (Earnings Date)</option>
              <option value="thesis_breaker">长期持有论文破裂 (Thesis Breaker)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              标的代码 (Symbol)
            </label>
            <Input
              type="text"
              placeholder="例如 AAPL, NVDA, TSLA"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              规则标题简述
            </label>
            <Input
              type="text"
              placeholder="例如: AAPL 突破 $230 阻力位"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          {/* Dynamic Condition Inputs */}
          {alertType === 'price' && (
            <div className="grid grid-cols-2 gap-3 p-3 bg-slate-900/60 rounded border border-slate-800">
              <div>
                <label className="block text-xs text-slate-400 mb-1">触发方向</label>
                <select
                  value={priceDirection}
                  onChange={(e) => setPriceDirection(e.target.value as any)}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200"
                >
                  <option value="cross_above">向上突破 (≥)</option>
                  <option value="cross_below">向下跌破 (≤)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">目标价格 ($)</label>
                <Input
                  type="number"
                  step="0.01"
                  placeholder="230.00"
                  value={targetPrice}
                  onChange={(e) => setTargetPrice(e.target.value)}
                />
              </div>
            </div>
          )}

          {alertType === 'technical_signal' && (
            <div className="grid grid-cols-3 gap-2 p-3 bg-slate-900/60 rounded border border-slate-800">
              <div>
                <label className="block text-xs text-slate-400 mb-1">指标名</label>
                <Input
                  type="text"
                  value={techIndicator}
                  onChange={(e) => setTechIndicator(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">比较符号</label>
                <select
                  value={techOperator}
                  onChange={(e) => setTechOperator(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
                >
                  <option value="gt">&gt; (大于)</option>
                  <option value="lt">&lt; (小于)</option>
                  <option value="gte">&ge; (大于等于)</option>
                  <option value="lte">&le; (小于等于)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">阈值</label>
                <Input
                  type="number"
                  step="0.1"
                  value={techThreshold}
                  onChange={(e) => setTechThreshold(e.target.value)}
                />
              </div>
            </div>
          )}

          {alertType === 'earnings_date' && (
            <div className="p-3 bg-slate-900/60 rounded border border-slate-800">
              <label className="block text-xs text-slate-400 mb-1">提前提醒天数</label>
              <Input
                type="number"
                min="0"
                max="30"
                value={earningsDaysBefore}
                onChange={(e) => setEarningsDaysBefore(Number(e.target.value))}
              />
            </div>
          )}

          {alertType === 'thesis_breaker' && (
            <div className="space-y-3 p-3 bg-slate-900/60 rounded border border-slate-800">
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">监控指标</label>
                  <Input
                    type="text"
                    value={thesisMetric}
                    onChange={(e) => setThesisMetric(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">比较符号</label>
                  <select
                    value={thesisOperator}
                    onChange={(e) => setThesisOperator(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
                  >
                    <option value="lt">&lt; (跌破)</option>
                    <option value="lte">&le; (低于或等于)</option>
                    <option value="gt">&gt; (超过)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">破裂阈值</label>
                  <Input
                    type="number"
                    step="0.01"
                    value={thesisThreshold}
                    onChange={(e) => setThesisThreshold(e.target.value)}
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">业务破坏性假说描述</label>
                <Input
                  type="text"
                  value={thesisDesc}
                  onChange={(e) => setThesisDesc(e.target.value)}
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              防骚扰冷却时间（分钟，默认 1440 = 24 小时）
            </label>
            <Input
              type="number"
              min="1"
              value={cooldownMinutes}
              onChange={(e) => setCooldownMinutes(Number(e.target.value))}
            />
          </div>

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
              {submitting ? '提交中...' : '立即创建'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default AlertRulesView;
