import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  Layers,
  KeyRound,
  RefreshCw,
  Cpu,
  ShieldCheck,
} from 'lucide-react';
import { api } from './lib/api';
import { MonitorView } from './features/monitor/MonitorView';
import { AccountsView } from './features/accounts/AccountsView';
import { BuildView } from './features/build/BuildView';
import { OperationsView } from './features/operations/OperationsView';

export const App: React.FC = () => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'monitor' | 'accounts' | 'build' | 'operations'>('monitor');

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

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/30">
              RP
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm font-bold tracking-tight text-white">ResearchPortal</h1>
                <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${
                  status?.mode === 'live' ? 'bg-amber-950 text-amber-400 border border-amber-800' : 'bg-slate-800 text-slate-300 border border-slate-700'
                }`}>
                  {status?.mode || 'fixture'}
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono text-slate-400 bg-slate-800 border border-slate-700">
                  React 19
                </span>
              </div>
              <div className="text-[11px] text-slate-400 font-mono flex items-center gap-2">
                <span>Worker: {status?.worker_online ? <strong className="text-emerald-400">online</strong> : <span className="text-rose-400">offline</span>}</span>
                <span>·</span>
                <span>Revision: {status?.active_revision?.slice(0, 8) || 'pinned'}</span>
                <span>·</span>
                <span className="flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3 text-slate-500" />
                  Live submit: {status?.allow_live_submit ? <strong className="text-emerald-400">enabled</strong> : 'disabled'}
                </span>
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
              onClick={() => setActiveTab('build')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg font-medium transition ${
                activeTab === 'build'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Cpu className="w-3.5 h-3.5" /> Build & Submit
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
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full space-y-6">
        {activeTab === 'monitor' && (
          <MonitorView
            notebooks={notebooks}
            accounts={accounts}
            isFetchingNotebooks={isFetchingNotebooks}
          />
        )}

        {activeTab === 'accounts' && (
          <AccountsView accounts={accounts} />
        )}

        {activeTab === 'build' && (
          <BuildView
            accounts={accounts}
            status={status}
          />
        )}

        {activeTab === 'operations' && (
          <OperationsView operations={operations} />
        )}
      </main>
    </div>
  );
};

export default App;
