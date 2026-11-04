import React, { useState } from 'react';
import { Play, ExternalLink, Terminal, Copy, CheckCircle, Clock } from 'lucide-react';
import { Notebook, NotebookLogs } from '../types';
import { MetricChart } from './MetricChart';
import { api } from '../lib/api';

interface NotebookCardProps {
  notebook: Notebook;
  onCheck: (id: string) => void;
  isChecking: boolean;
}

export const NotebookCard: React.FC<NotebookCardProps> = ({
  notebook: nb,
  onCheck,
  isChecking,
}) => {
  const [isLogOpen, setIsLogOpen] = useState(false);
  const [logs, setLogs] = useState<NotebookLogs | null>(null);
  const [copied, setCopied] = useState(false);

  const health = nb.health || {};
  const healthState = health.health || 'unknown';

  const badgeColor = {
    progressing: 'bg-emerald-950/80 text-emerald-400 border-emerald-800',
    running: 'bg-blue-950/80 text-blue-400 border-blue-800',
    suspected_stall: 'bg-amber-950/80 text-amber-400 border-amber-800',
    terminal: 'bg-slate-800/80 text-slate-300 border-slate-700',
    pending: 'bg-purple-950/80 text-purple-400 border-purple-800',
    unknown: 'bg-slate-900 text-slate-400 border-slate-800',
  }[healthState] || 'bg-slate-900 text-slate-400 border-slate-800';

  const wData = nb.latest_wandb?.data || {};
  const wSummary = wData.summary || {};
  const liveMetrics = wData.live_metrics || {};
  const curves = wData.curves || {};
  const trainCurve = curves.train || [];
  const valCurve = curves.val || [];

  const handleToggleLog = async () => {
    const next = !isLogOpen;
    setIsLogOpen(next);
    if (next && !logs) {
      try {
        const fetched = await api.getNotebookLogs(nb.id);
        setLogs(fetched);
      } catch (err) {
        console.error('Failed to fetch logs', err);
      }
    }
  };

  const handleCopyLog = () => {
    const text = logs?.text || logs?.wandb_live_text || '';
    if (text) {
      navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const bestDice = liveMetrics.best_dice ?? wSummary['best_mDice'] ?? wSummary['val/best_mDice'];
  const bestIter = liveMetrics.best_iter ?? wSummary['train/best_iter'];
  const supLoss = liveMetrics.supervised_loss ?? wSummary['train/supervised'];
  const runtimeSec = liveMetrics.runtime_seconds ?? wSummary['_runtime'];

  const formatSec = (s?: number) => {
    if (typeof s !== 'number' || s < 0) return null;
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  };

  const activeLogText = logs?.text || logs?.wandb_live_text || '';
  const isWandbLiveStream = !logs?.text && Boolean(logs?.wandb_live_text);

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm hover:border-slate-700/80 transition">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-bold text-white font-mono">{nb.kernel}</span>
            <span className={`px-2.5 py-0.5 text-xs font-semibold rounded-full border ${badgeColor}`}>
              HEALTH: {healthState.toUpperCase()}
            </span>
            <span className="px-2 py-0.5 text-xs rounded bg-slate-950 border border-slate-800 font-mono text-slate-300">
              Kaggle: {health.provider_state || 'unknown'}
            </span>
            {health.status_stale && (
              <span className="px-2 py-0.5 text-[11px] font-semibold rounded bg-amber-950/80 text-amber-300 border border-amber-800">
                STALE
              </span>
            )}
            {nb.remote_version ? (
              <span className="px-2 py-0.5 text-xs font-semibold rounded bg-sky-950 text-sky-300 border border-sky-800 font-mono">
                v{nb.remote_version}
              </span>
            ) : (
              <span className="text-[11px] text-slate-500 font-mono">version: unverified</span>
            )}
          </div>
          <div className="text-xs text-slate-400 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>Connection: <strong className="text-slate-300">{nb.account_name}</strong></span>
            {nb.run_ref && (
              <span>· W&B: <strong className="text-slate-300 font-mono">{nb.run_ref}</strong> ({nb.wandb_account_name || 'bound'})</span>
            )}
            {nb.attempt_id && (
              <span>· Attempt: <strong className="text-slate-400 font-mono text-[10px]">{nb.attempt_id.slice(0, 8)}...</strong> (submitted: {nb.submitted_version || 'unverified'})</span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-2 pt-1 sm:pt-0">
          <button
            onClick={() => onCheck(nb.id)}
            disabled={isChecking}
            className="flex items-center gap-1.5 px-3.5 py-2 min-h-[38px] text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm disabled:opacity-50 transition active:scale-[0.98]"
          >
            <Play className={`w-3.5 h-3.5 ${isChecking ? 'animate-spin' : ''}`} />
            {isChecking ? 'Checking...' : 'Check Now'}
          </button>
          <a
            href={`https://www.kaggle.com/code/${nb.kernel}`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 px-3.5 py-2 min-h-[38px] text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition active:scale-[0.98]"
          >
            Kaggle <ExternalLink className="w-3.5 h-3.5" />
          </a>
          {nb.run_ref && (
            <a
              href={`https://wandb.ai/${nb.run_ref}`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3.5 py-2 min-h-[38px] text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition active:scale-[0.98]"
            >
              W&B <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
        </div>
      </div>

      {/* Metric Highlights */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 bg-slate-950 p-3 rounded-lg border border-slate-800/80">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Iteration / Step</div>
          <div className="text-sm font-bold text-emerald-400 mt-0.5">
            {health.last_iteration ?? nb.logs_summary?.progress?.iteration ?? 'Unavailable'}
          </div>
          <div className="text-[10px] text-slate-500 font-mono">
            {wData.last_iteration !== undefined ? 'Source: W&B' : 'Source: Logs'}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Best mDice</div>
          <div className="text-sm font-bold text-amber-400 mt-0.5">
            {typeof bestDice === 'number' ? bestDice.toFixed(4) : '—'}
            {typeof bestIter === 'number' && <span className="text-[11px] font-normal text-slate-400 ml-1">@{bestIter}</span>}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Sup Loss</div>
          <div className="text-sm font-bold text-sky-400 mt-0.5">
            {typeof supLoss === 'number' ? supLoss.toFixed(4) : '—'}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Runtime</div>
          <div className="text-xs font-mono text-slate-300 mt-1 flex items-center gap-1">
            <Clock className="w-3 h-3 text-slate-500" />
            {formatSec(runtimeSec) || '—'}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Log Status</div>
          <div className="text-xs font-mono text-slate-300 mt-1">
            {nb.logs_summary?.availability || 'not_yet_published'}
          </div>
        </div>
      </div>

      {/* Realtime Charts */}
      {(trainCurve.length > 0 || valCurve.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
          <MetricChart
            data={trainCurve}
            title="W&B Training Loss (Realtime)"
            emptyLabel="Waiting for training loss steps..."
            series={[
              { key: 'sup', name: 'Sup Loss', color: '#10b981' },
              { key: 'cons', name: 'Cons Loss', color: '#38bdf8' },
            ]}
          />
          <MetricChart
            data={valCurve}
            title="W&B Validation mDice (Realtime)"
            emptyLabel="Waiting for validation steps..."
            series={[
              { key: 'dice', name: 'Val mDice', color: '#a78bfa' },
              { key: 'best', name: 'Best mDice', color: '#fbbf24', strokeDasharray: '4 4' },
            ]}
          />
        </div>
      )}

      {/* Terminal Logs Collapsible */}
      <div className="pt-1">
        <div className="flex items-center justify-between">
          <button
            onClick={handleToggleLog}
            className="text-xs font-medium text-slate-400 hover:text-white flex items-center gap-1.5 transition"
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>
              Execution Logs ({nb.logs_summary?.line_count || nb.logs_summary?.wandb_live_lines || 0} lines ·{' '}
              {nb.logs_summary?.availability || 'not_yet_published'})
            </span>
          </button>
          {isLogOpen && (
            <button
              onClick={handleCopyLog}
              className="text-[11px] text-slate-400 hover:text-emerald-400 flex items-center gap-1 font-mono transition"
            >
              {copied ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? 'Copied' : 'Copy Log'}
            </button>
          )}
        </div>

        {isLogOpen && (
          <div className="terminal-window mt-2">
            <div className="terminal-header">
              <div className="flex items-center space-x-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-rose-500/80" />
                <span className="h-2.5 w-2.5 rounded-full bg-amber-500/80" />
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-500/80" />
                <span className="text-xs text-slate-400 font-mono ml-2">
                  {isWandbLiveStream ? `wandb live-stream ${nb.run_ref}` : `kaggle kernels logs ${nb.kernel}`}
                </span>
              </div>
              <span className="text-[10px] text-slate-500 font-mono">
                {isWandbLiveStream ? 'W&B Realtime Step Stream' : 'Output'}
              </span>
            </div>
            <div className="terminal-body font-mono text-[11px]">
              {activeLogText || 'No log output published yet.'}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
