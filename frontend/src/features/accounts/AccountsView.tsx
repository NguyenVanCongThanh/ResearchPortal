import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { KeyRound, CheckCircle2, AlertCircle, Plus, ShieldCheck } from 'lucide-react';
import { api } from '../../lib/api';
import { Account } from '../../types';

interface AccountsViewProps {
  accounts: Account[];
}

export const AccountsView: React.FC<AccountsViewProps> = ({ accounts }) => {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [testingIds, setTestingIds] = useState<Record<string, boolean>>({});

  const [form, setForm] = useState({
    provider: 'kaggle' as 'kaggle' | 'wandb',
    name: '',
    slug: '',
    principal: '',
    secret: '',
    description: '',
    is_default: false,
  });

  const testMutation = useMutation({
    mutationFn: (accountId: string) => api.testAccount(accountId),
    onSuccess: (_, accountId) => {
      setTestingIds(prev => ({ ...prev, [accountId]: false }));
      alert('Connection test enqueued. Results will update shortly.');
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
    },
    onError: (err: any, accountId) => {
      setTestingIds(prev => ({ ...prev, [accountId]: false }));
      alert(`Test request failed: ${err.message}`);
    },
  });

  const saveMutation = useMutation({
    mutationFn: api.saveAccount,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
      setIsModalOpen(false);
      setForm({
        provider: 'kaggle',
        name: '',
        slug: '',
        principal: '',
        secret: '',
        description: '',
        is_default: false,
      });
    },
    onError: (err: any) => {
      alert(`Save failed: ${err.message}`);
    },
  });

  const handleTest = (accountId: string) => {
    setTestingIds(prev => ({ ...prev, [accountId]: true }));
    testMutation.mutate(accountId);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-indigo-400" /> Configured Accounts & API Credentials
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Kaggle uses legacy username/API key. W&B uses explicit API key and entity. Credentials live in encrypted runtime storage outside Git.
          </p>
        </div>
        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition shadow-sm"
        >
          <Plus className="w-3.5 h-3.5" /> Add Connection
        </button>
      </div>

      <div className="divide-y divide-slate-800">
        {accounts.length === 0 ? (
          <div className="py-8 text-center text-slate-500 text-xs font-mono">
            No accounts configured yet. Click "Add Connection" to add Kaggle or W&B credentials.
          </div>
        ) : (
          accounts.map(acc => (
            <div key={acc.id} className="py-3.5 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-sm text-white">{acc.name}</span>
                  <span className={`text-[11px] px-2 py-0.5 rounded uppercase font-mono font-bold ${
                    acc.provider === 'kaggle' ? 'bg-sky-950 text-sky-400 border border-sky-800' : 'bg-amber-950 text-amber-400 border border-amber-800'
                  }`}>
                    {acc.provider}
                  </span>
                  {acc.is_default && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800 font-mono">
                      default
                    </span>
                  )}
                  {acc.test_result === 'verified' ? (
                    <span className="text-[11px] text-emerald-400 flex items-center gap-1 font-mono">
                      <CheckCircle2 className="w-3.5 h-3.5" /> verified
                    </span>
                  ) : acc.test_result ? (
                    <span className="text-[11px] text-rose-400 flex items-center gap-1 font-mono">
                      <AlertCircle className="w-3.5 h-3.5" /> {acc.test_result}
                    </span>
                  ) : (
                    <span className="text-[11px] text-slate-500 font-mono">untested</span>
                  )}
                </div>
                <div className="text-xs text-slate-400 font-mono mt-1 flex items-center gap-3">
                  <span>Principal: <strong className="text-slate-300">{acc.principal}</strong></span>
                  <span>·</span>
                  <span>Slug: {acc.slug}</span>
                  <span>·</span>
                  <span className="flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3 text-slate-500" />
                    {acc.has_credential ? 'Secret stored' : 'No secret'}
                  </span>
                </div>
                {acc.description && (
                  <div className="text-xs text-slate-500 mt-0.5 italic">{acc.description}</div>
                )}
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleTest(acc.id)}
                  disabled={testingIds[acc.id]}
                  className="px-3 py-1.5 text-xs rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition disabled:opacity-50"
                >
                  {testingIds[acc.id] ? 'Testing...' : 'Test Connection'}
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Add Account Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <KeyRound className="w-4 h-4 text-indigo-400" /> New Connection
            </h3>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1">Provider</label>
                <select
                  value={form.provider}
                  onChange={e => setForm({ ...form, provider: e.target.value as any })}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200"
                >
                  <option value="kaggle">Kaggle (Legacy API Key)</option>
                  <option value="wandb">Weights & Biases (W&B API Key)</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Display Name</label>
                <input
                  type="text"
                  placeholder="e.g. My Kaggle Account"
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Identifier Slug (unique)</label>
                <input
                  type="text"
                  placeholder="e.g. kaggle-prod"
                  value={form.slug}
                  onChange={e => setForm({ ...form, slug: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 font-mono text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Principal (Username or Entity)</label>
                <input
                  type="text"
                  placeholder="e.g. bokhnhl"
                  value={form.principal}
                  onChange={e => setForm({ ...form, principal: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 font-mono text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">API Key / Token (stored isolated outside git)</label>
                <input
                  type="password"
                  placeholder="Enter API Key"
                  value={form.secret}
                  onChange={e => setForm({ ...form, secret: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 font-mono text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Description (optional)</label>
                <input
                  type="text"
                  placeholder="e.g. Primary team training account"
                  value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200"
                />
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="is_default"
                  checked={form.is_default}
                  onChange={e => setForm({ ...form, is_default: e.target.checked })}
                  className="rounded bg-slate-950 border-slate-800 text-indigo-600 focus:ring-0"
                />
                <label htmlFor="is_default" className="text-slate-300">Set as default connection</label>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setIsModalOpen(false)}
                className="px-3 py-1.5 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={() => saveMutation.mutate(form)}
                disabled={!form.name || !form.principal || saveMutation.isPending}
                className="px-4 py-1.5 text-xs font-semibold rounded bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50"
              >
                {saveMutation.isPending ? 'Saving...' : 'Save Connection'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

