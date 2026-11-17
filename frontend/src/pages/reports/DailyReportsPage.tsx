import React, { useEffect, useState } from 'react';
import {
  Calendar,
  FileText,
  Play,
  RefreshCw,
  TrendingUp,
  User,
} from 'lucide-react';
import { DailyReportRead, DailyReportType, reportsApi } from '../../api/reports';
import { Badge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { Card } from '../../components/common/Card';
import { ComplianceDisclaimer } from '../../components/compliance/ComplianceDisclaimer';

export const DailyReportsPage: React.FC = () => {
  const [selectedDate, setSelectedDate] = useState<string>(() => {
    const d = new Date();
    return d.toISOString().split('T')[0];
  });
  const [reportType, setReportType] = useState<DailyReportType>('market_digest');
  const [reports, setReports] = useState<DailyReportRead[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [runningPipeline, setRunningPipeline] = useState<boolean>(false);
  const [pipelineResult, setPipelineResult] = useState<string | null>(null);

  const loadReports = async () => {
    setLoading(true);
    try {
      const data = await reportsApi.listDailyReports({
        date: selectedDate,
        report_type: reportType,
        limit: 10,
      });
      setReports(data || []);
    } catch (err: unknown) {
      console.error('Failed to load daily reports', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, [selectedDate, reportType]);

  const handleRunPipeline = async () => {
    if (!window.confirm(`确定手动执行美股收盘后批处理任务链（${selectedDate}）？`)) return;
    setRunningPipeline(true);
    setPipelineResult(null);
    try {
      const res = await reportsApi.runPostMarketPipeline({
        trade_date: selectedDate,
        force: true,
      });
      setPipelineResult(`收盘流水线执行完毕：状态 [${res.status}]，处理 ${res.steps?.length || 0} 个任务步骤。`);
      loadReports();
    } catch (err: any) {
      setPipelineResult(`执行出错: ${err.message || '未知错误'}`);
    } finally {
      setRunningPipeline(false);
    }
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <FileText className="w-6 h-6 text-indigo-400" />
            收盘全流程复盘与投研日报
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            每日美东 16:15 自动生成大盘宏观异动简报与模拟交易账户收盘对账复盘。
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            size="sm"
            variant="outline"
            disabled={runningPipeline}
            onClick={handleRunPipeline}
            className="flex items-center gap-1.5 border-indigo-500/40 text-indigo-300 hover:bg-indigo-500/10"
          >
            <Play className="w-4 h-4 text-indigo-400" />
            {runningPipeline ? '正在批处理...' : '手动执行收盘工作流'}
          </Button>

          <Button
            size="sm"
            variant="outline"
            onClick={loadReports}
            className="flex items-center gap-1 text-slate-300 hover:text-white"
          >
            <RefreshCw className="w-4 h-4" />
            刷新
          </Button>
        </div>
      </div>

      {pipelineResult && (
        <div className="p-3 bg-indigo-500/10 border border-indigo-500/30 rounded text-indigo-300 text-xs flex items-center justify-between">
          <span>{pipelineResult}</span>
          <button onClick={() => setPipelineResult(null)} className="text-slate-400 hover:text-white">
            ✕
          </button>
        </div>
      )}

      {/* Control Bar: Date Selector & Report Type */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-900/80 p-4 rounded-xl border border-slate-800">
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-slate-400" />
          <span className="text-xs text-slate-400">交易日期：</span>
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-3 py-1.5 focus:outline-none focus:border-indigo-500 font-mono"
          />
        </div>

        <div className="flex items-center gap-2 bg-slate-950 p-1 rounded-lg border border-slate-800">
          <button
            onClick={() => setReportType('market_digest')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              reportType === 'market_digest'
                ? 'bg-indigo-600 text-white'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            全市场收盘简报
          </button>
          <button
            onClick={() => setReportType('portfolio_digest')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              reportType === 'portfolio_digest'
                ? 'bg-indigo-600 text-white'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <User className="w-3.5 h-3.5" />
            模拟投资组合复盘
          </button>
        </div>
      </div>

      {/* Reports Content */}
      {loading ? (
        <div className="p-12 text-center text-slate-400">正在检索简报数据...</div>
      ) : reports.length === 0 ? (
        <Card className="p-12 text-center text-slate-400 border border-slate-800">
          <FileText className="w-12 h-12 mx-auto mb-3 text-slate-600 opacity-60" />
          <p className="text-base font-medium">该交易日暂无已出具的收盘简报</p>
          <p className="text-sm text-slate-500 mt-1">
            美股正常交易日收盘（16:15 ET）后将自动结算生成，或点击上方“手动执行收盘工作流”进行补算。
          </p>
        </Card>
      ) : (
        <div className="space-y-6">
          {reports.map((rep) => (
            <Card
              key={rep.id}
              className="p-6 border border-slate-800 bg-slate-900/60 space-y-4"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800/80 gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <Badge variant={rep.report_type === 'market_digest' ? 'info' : 'success'}>
                      {rep.report_type === 'market_digest' ? '市场大盘' : '个人持仓'}
                    </Badge>
                    <span className="font-mono text-xs text-slate-400">
                      交易日: {rep.report_date}
                    </span>
                  </div>
                  <h2 className="text-lg font-bold text-slate-100 mt-1">{rep.title}</h2>
                </div>
                <span className="text-xs text-slate-500 font-mono">
                  生成时间: {new Date(rep.created_at).toLocaleTimeString()}
                </span>
              </div>

              {/* Render Structured Markdown Content */}
              <div className="prose prose-invert prose-sm max-w-none bg-slate-950/50 p-5 rounded-lg border border-slate-800/60 font-sans text-slate-200 leading-relaxed whitespace-pre-wrap">
                {rep.summary}
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Compliance Disclaimer */}
      <ComplianceDisclaimer variant="banner" />
    </div>
  );
};

export default DailyReportsPage;
