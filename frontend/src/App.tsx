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
import { ToastProvider } from './components/Toast';

export const AppContent: React.FC = () => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'monitor' | 'accounts' | 'build' | 'operations'>('monitor');

  // Queries with background visibility throttling
  const { data: status } = useQuery({
    queryKey: ['systemStatus'],
    queryFn: api.getSystemStatus,
    refetchInterval: 12000,
    refetchIntervalInBackground: false,
  });

  const { data: notebooks = [], isFetching: isFetchingNotebooks } = useQuery({
    queryKey: ['notebooks'],
    queryFn: api.getNotebooks,
    refetchInterval: 10000,
    refetchIntervalInBackground: false,
  });

  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: api.getAccounts,
    staleTime: 30000,
  });

  const { data: operations = [] } = useQuery({
    queryKey: ['operations'],
    queryFn: api.getOperations,
    refetchInterval: 8000,
    refetchIntervalInBackground: false,
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex flex-col md:flex-row md:items-center justify-between gap-4">
          {/* Identity & Status */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/25 text-sm flex-shrink-0">
                RP
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
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
                <div className="text-[11px] text-slate-400 font-mono flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5">
                  <span>Worker: {status?.worker_online ? <strong className="text-emerald-400">online</strong> : <span className="text-rose-400">offline</span>}</span>
                  <span>·</span>
                  <span>Revision: {status?.active_revision?.slice(0, 8) || 'pinned'}</span>
                  <span>·</span>
                  <span className="flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3 text-slate-500" />
                    Submit: {status?.allow_live_submit ? <strong className="text-emerald-400">live enabled</strong> : 'safe simulated'}
                  </span>
                </div>
              </div>
            </div>

            {/* Mobile Refresh Button */}
            <div className="md:hidden">
              <button
                onClick={() => queryClient.invalidateQueries()}
                className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition"
                title="Refresh Data"
                aria-label="Refresh Data"
              >
                <RefreshCw className={`w-4 h-4 ${isFetchingNotebooks ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* Navigation Tabs and Desktop Actions */}
          <div className="flex items-center gap-2 w-full md:w-auto overflow-x-auto pb-1 md:pb-0 scrollbar-none">
            <nav className="flex items-center space-x-1.5 bg-slate-950 p-1.5 rounded-xl border border-slate-800 text-xs w-full sm:w-auto" role="tablist">
              <button
                role="tab"
                aria-selected={activeTab === 'monitor'}
                onClick={() => setActiveTab('monitor')}
                className={`flex-1 sm:flex-initial flex items-center justify-center gap-2 px-3.5 min-h-[40px] rounded-lg font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 focus-visible:ring-offset-slate-950 ${
                  activeTab === 'monitor'
                    ? 'bg-slate-800 text-white shadow-sm font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`}
              >
                <Activity className="w-4 h-4 text-emerald-400" />
                <span>Monitor</span>
                <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-900 text-slate-300 font-mono">
                  {notebooks.length}
                </span>
              </button>
              <button
                role="tab"
                aria-selected={activeTab === 'accounts'}
                onClick={() => setActiveTab('accounts')}
                className={`flex-1 sm:flex-initial flex items-center justify-center gap-2 px-3.5 min-h-[40px] rounded-lg font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 focus-visible:ring-offset-slate-950 ${
                  activeTab === 'accounts'
                    ? 'bg-slate-800 text-white shadow-sm font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`}
              >
                <KeyRound className="w-4 h-4 text-indigo-400" />
                <span>Accounts</span>
                <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-900 text-slate-300 font-mono">
                  {accounts.length}
                </span>
              </button>
              <button
                role="tab"
                aria-selected={activeTab === 'build'}
                onClick={() => setActiveTab('build')}
                className={`flex-1 sm:flex-initial flex items-center justify-center gap-2 px-3.5 min-h-[40px] rounded-lg font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 focus-visible:ring-offset-slate-950 ${
                  activeTab === 'build'
                    ? 'bg-slate-800 text-white shadow-sm font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`}
              >
                <Cpu className="w-4 h-4 text-amber-400" />
                <span>Build & Submit</span>
              </button>
              <button
                role="tab"
                aria-selected={activeTab === 'operations'}
                onClick={() => setActiveTab('operations')}
                className={`flex-1 sm:flex-initial flex items-center justify-center gap-2 px-3.5 min-h-[40px] rounded-lg font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 focus-visible:ring-offset-slate-950 ${
                  activeTab === 'operations'
                    ? 'bg-slate-800 text-white shadow-sm font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`}
              >
                <Layers className="w-4 h-4 text-sky-400" />
                <span>Ops</span>
                <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-900 text-slate-300 font-mono">
                  {operations.length}
                </span>
              </button>
            </nav>

            <button
              onClick={() => queryClient.invalidateQueries()}
              className="hidden md:flex min-h-[44px] min-w-[44px] items-center justify-center rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-white transition flex-shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
              title="Refresh Data"
              aria-label="Refresh Data"
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

export const App: React.FC = () => {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
};

export default App;
