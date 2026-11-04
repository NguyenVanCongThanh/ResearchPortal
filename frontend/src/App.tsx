import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  Layers,
  KeyRound,
  RefreshCw,
  Plus,
  Radio,
  CheckCircle2,
} from 'lucide-react';
import { api } from './lib/api';
import { NotebookCard } from './components/NotebookCard';

export const App: React.FC = () => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'monitor' | 'accounts' | 'build' | 'operations'>('monitor');
  const [isAttachModalOpen, setIsAttachModalOpen] = useState(false);
  const [checkingIds, setCheckingIds] = useState<Record<string, boolean>>({});

  // Form states for attach
  const [attachForm, setAttachForm] = useState({
    account_id: '',
    kernel: '',
    wandb_account_id: '',
    run_ref: '',
  });

  // Queries
  const { data: status } = useQuery({
    queryKey: ['systemStatus'],
    queryFn: api.getSystemStatus,
    refetchInterval: 10000,
  });

  const { data: notebooks = [], isFetching: isFetchingNotebooks } = useQuery({
    queryKey: ['notebooks'],
    queryFn: api.getNotebooks,
    refetchInterval: 8000,
  });

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: api.getAccounts,
  });

  const { data: operations = [] } = useQuery({
    queryKey: ['operations'],
    queryFn: api.getOperations,
    refetchInterval: 5000,
  });

  // Check Notebook
  const handleCheck = async (id: string) => {
    setCheckingIds(prev => ({ ...prev, [id]: true }));
    try {
      await api.checkNotebook(id);
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['notebooks'] });
        setCheckingIds(prev => ({ ...prev, [id]: false }));
      }, 2000);
    } catch (err: any) {
      alert(err.message || 'Check failed');
      setCheckingIds(prev => ({ ...prev, [id]: false }));
    }
  };

  // Attach Notebook Mutation
  const attachMutation = useMutation({
    mutationFn: api.attachNotebook,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notebooks'] });
      setIsAttachModalOpen(false);
      setAttachForm({ account_id: '', kernel: '', wandb_account_id: '', run_ref: '' });
    },
    onError: (err: any) => {
      alert(err.message || 'Attach failed');
    },
  });

  const progressingCount = notebooks.filter(n => n.health?.health === 'progressing').length;
  const runningCount = notebooks.filter(n => n.health?.provider_state === 'running').length;
  const stalledCount = notebooks.filter(n => n.health?.health === 'suspected_stall').length;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Navigation */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
              <Activity className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-base tracking-tight text-white">ResearchPortal</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase font-bold tracking-wider bg-indigo-950 text-indigo-300 border border-indigo-800">
                  {status?.mode || 'live'}
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono text-slate-400 bg-slate-800 border border-slate-700">
                  React 19
                </span>
              </div>
              <div className="text-[11px] text-slate-400 font-mono">
                Worker: {status?.worker_online ? 'online' : 'offline'} · Revision: {status?.active_revision?.slice(0, 8) || 'pinned'}
              </div>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex space-x-1 bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
            <button
              onClick={() => setActiveTab('monitor')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg font-medium transition ${
                activeTab === 'monitor'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Activity className="w-3.5 h-3.5" /> Monitor ({notebooks.length})
            </button>
            <button
              onClick={() => setActiveTab('accounts')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg font-medium transition ${
                activeTab === 'accounts'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <KeyRound className="w-3.5 h-3.5" /> Accounts ({accounts.length})
            </button>
            <button
              onClick={() => setActiveTab('operations')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg font-medium transition ${
                activeTab === 'operations'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3.5 h-3.5" /> Ops ({operations.length})
            </button>
          </nav>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => queryClient.invalidateQueries()}
              className="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-white transition"
              title="Refresh Data"
            >
              <RefreshCw className={`w-4 h-4 ${isFetchingNotebooks ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={() => setIsAttachModalOpen(true)}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition"
            >
              <Plus className="w-3.5 h-3.5" /> Attach Notebook
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full space-y-6">
        {activeTab === 'monitor' && (
          <div className="space-y-6">
            {/* Top Stat Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
                <div className="text-xs text-slate-400 font-medium">Total Tracked</div>
                <div className="text-2xl font-bold text-white mt-1 font-mono">{notebooks.length}</div>
              </div>
              <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
                <div className="text-xs text-emerald-400 font-medium flex items-center gap-1">
                  <Radio className="w-3.5 h-3.5 animate-pulse" /> Progressing
                </div>
                <div className="text-2xl font-bold text-emerald-400 mt-1 font-mono">{progressingCount}</div>
              </div>
              <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
                <div className="text-xs text-blue-400 font-medium">Kaggle Running</div>
                <div className="text-2xl font-bold text-blue-400 mt-1 font-mono">{runningCount}</div>
              </div>
              <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl">
                <div className="text-xs text-amber-400 font-medium">Suspected Stalls</div>
                <div className="text-2xl font-bold text-amber-400 mt-1 font-mono">{stalledCount}</div>
              </div>
            </div>

            {/* Notebook List */}
            <div className="space-y-4">
              {notebooks.length === 0 ? (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center">
                  <p className="text-slate-400 text-sm">No notebooks attached yet.</p>
                  <button
                    onClick={() => setIsAttachModalOpen(true)}
                    className="mt-4 px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 text-white"
                  >
                    Attach First Notebook
                  </button>
                </div>
              ) : (
                notebooks.map(nb => (
                  <NotebookCard
                    key={nb.id}
                    notebook={nb}
                    onCheck={handleCheck}
                    isChecking={Boolean(checkingIds[nb.id])}
                  />
                ))
              )}
            </div>
          </div>
        )}

        {activeTab === 'accounts' && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-base font-bold text-white">Configured Accounts</h2>
            <div className="divide-y divide-slate-800">
              {accounts.map(acc => (
                <div key={acc.id} className="py-3 flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-white">{acc.name}</span>
                      <span className="text-xs px-2 py-0.5 rounded bg-slate-950 border border-slate-800 font-mono text-slate-300">
                        {acc.provider}
                      </span>
                      {acc.test_result === 'verified' && (
                        <span className="text-[10px] text-emerald-400 flex items-center gap-1 font-mono">
                          <CheckCircle2 className="w-3 h-3" /> verified
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-400 font-mono mt-0.5">
                      Principal: {acc.principal} · Slug: {acc.slug}
                    </div>
                  </div>
                  <button
                    onClick={() => api.testAccount(acc.id).then(() => alert('Connection test enqueued'))}
                    className="px-3 py-1 text-xs rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
                  >
                    Test Connection
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'operations' && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-base font-bold text-white">Recent Operations (Queue & Audit)</h2>
            <div className="divide-y divide-slate-800">
              {operations.map(op => (
                <div key={op.id} className="py-3 flex items-center justify-between text-xs font-mono">
                  <div>
                    <div className="flex items-center gap-2">
                      <strong className="text-slate-200">{op.kind}</strong>
                      <span className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold ${
                        op.state === 'succeeded' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' :
                        op.state === 'failed' ? 'bg-rose-950 text-rose-400 border border-rose-800' :
                        'bg-blue-950 text-blue-400 border border-blue-800'
                      }`}>
                        {op.state}
                      </span>
                    </div>
                    <div className="text-slate-400 text-[11px] mt-0.5">
                      Target: {op.target} · Enqueued: {new Date(op.enqueued_at).toLocaleTimeString()}
                    </div>
                  </div>
                  {op.error && (
                    <span className="text-rose-400 text-[11px] truncate max-w-xs">{op.error}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Attach Modal */}
      {isAttachModalOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h3 className="text-base font-bold text-white">Attach Existing Notebook</h3>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1">Kaggle Account</label>
                <select
                  value={attachForm.account_id}
                  onChange={e => setAttachForm({ ...attachForm, account_id: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200"
                >
                  <option value="">Select Kaggle Account</option>
                  {accounts.filter(a => a.provider === 'kaggle').map(a => (
                    <option key={a.id} value={a.id}>{a.name} ({a.principal})</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Kernel Ref (username/slug)</label>
                <input
                  type="text"
                  placeholder="e.g. bokhnhl/kaggle-bhsd-mean-teacher-dual-gpu"
                  value={attachForm.kernel}
                  onChange={e => setAttachForm({ ...attachForm, kernel: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 font-mono text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">W&B Account (Optional)</label>
                <select
                  value={attachForm.wandb_account_id}
                  onChange={e => setAttachForm({ ...attachForm, wandb_account_id: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200"
                >
                  <option value="">Select W&B Account</option>
                  {accounts.filter(a => a.provider === 'wandb').map(a => (
                    <option key={a.id} value={a.id}>{a.name} ({a.principal})</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">W&B Run Ref (entity/project/run-id)</label>
                <input
                  type="text"
                  placeholder="e.g. entity/project/devkj8qd"
                  value={attachForm.run_ref}
                  onChange={e => setAttachForm({ ...attachForm, run_ref: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 font-mono text-slate-200"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setIsAttachModalOpen(false)}
                className="px-3 py-1.5 text-xs rounded bg-slate-800 text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={() => attachMutation.mutate(attachForm)}
                disabled={!attachForm.account_id || !attachForm.kernel}
                className="px-4 py-1.5 text-xs font-semibold rounded bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50"
              >
                Attach
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default App;
