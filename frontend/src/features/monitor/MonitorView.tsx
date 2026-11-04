import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Radio, Plus } from 'lucide-react';
import { api } from '../../lib/api';
import { NotebookCard } from '../../components/NotebookCard';
import { Account, Notebook } from '../../types';
import { useToast } from '../../components/Toast';
import { Modal } from '../../components/Modal';

interface MonitorViewProps {
  notebooks: Notebook[];
  accounts: Account[];
  isFetchingNotebooks: boolean;
}

export const MonitorView: React.FC<MonitorViewProps> = ({
  notebooks,
  accounts,
  isFetchingNotebooks: _isFetchingNotebooks,
}) => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();
  const [isAttachModalOpen, setIsAttachModalOpen] = useState(false);
  const [checkingIds, setCheckingIds] = useState<Record<string, boolean>>({});

  const [attachForm, setAttachForm] = useState({
    account_id: '',
    kernel: '',
    wandb_account_id: '',
    run_ref: '',
  });

  const attachMutation = useMutation({
    mutationFn: api.attachNotebook,
    onSuccess: () => {
      const kernelName = attachForm.kernel;
      queryClient.invalidateQueries({ queryKey: ['notebooks'] });
      setIsAttachModalOpen(false);
      setAttachForm({ account_id: '', kernel: '', wandb_account_id: '', run_ref: '' });
      showSuccess('Notebook attached', `Attached ${kernelName || 'kernel'} to monitor.`);
    },
    onError: (err: any) => {
      showError('Attach failed', err?.message || 'Could not attach notebook.');
    },
  });

  const handleCheck = async (id: string) => {
    setCheckingIds(prev => ({ ...prev, [id]: true }));
    try {
      await api.checkNotebook(id);
      showSuccess('Check dispatched', `Status check queued for notebook ${id.slice(0, 8)}`);
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['notebooks'] });
        setCheckingIds(prev => ({ ...prev, [id]: false }));
      }, 1500);
    } catch (err: any) {
      showError('Check failed', err?.message || 'Failed to dispatch status check.');
      setCheckingIds(prev => ({ ...prev, [id]: false }));
    }
  };

  const progressingCount = notebooks.filter(n => n.health?.health === 'progressing').length;
  const runningCount = notebooks.filter(n => n.health?.provider_state?.toLowerCase() === 'running').length;
  const stalledCount = notebooks.filter(n => n.health?.health === 'suspected_stall').length;

  return (
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
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-white">Active Kernels & Training Monitors</h2>
          <button
            onClick={() => setIsAttachModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition"
          >
            <Plus className="w-3.5 h-3.5" /> Attach Notebook
          </button>
        </div>

        {notebooks.length === 0 ? (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center">
            <p className="text-slate-400 text-sm">No notebooks attached yet.</p>
            <button
              onClick={() => setIsAttachModalOpen(true)}
              className="mt-4 px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 transition"
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

      {/* Attach Modal */}
      <Modal
        isOpen={isAttachModalOpen}
        onClose={() => setIsAttachModalOpen(false)}
        title="Attach Existing Kaggle Kernel"
        description="Connect a running or finished Kaggle kernel to live polling and telemetry."
        maxWidth="md"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (attachForm.account_id && attachForm.kernel) {
              attachMutation.mutate(attachForm);
            }
          }}
          className="space-y-4 text-xs"
        >
          <div>
            <label htmlFor="attach-account" className="block text-slate-300 font-medium mb-1">
              Kaggle Account <span className="text-rose-400">*</span>
            </label>
            <select
              id="attach-account"
              value={attachForm.account_id}
              onChange={e => setAttachForm({ ...attachForm, account_id: e.target.value })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              required
            >
              <option value="">Select Kaggle account</option>
              {accounts.filter(a => a.provider === 'kaggle').map(a => (
                <option key={a.id} value={a.id}>{a.name} ({a.principal})</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="attach-kernel" className="block text-slate-300 font-medium mb-1">
              Kernel Reference <span className="text-rose-400">*</span>
            </label>
            <input
              id="attach-kernel"
              type="text"
              placeholder="e.g. username/slug-title"
              value={attachForm.kernel}
              onChange={e => setAttachForm({ ...attachForm, kernel: e.target.value })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 font-mono text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              required
            />
            <p className="text-[11px] text-slate-500 mt-1">Must match the Kaggle author/slug format.</p>
          </div>

          <div>
            <label htmlFor="attach-wandb-acc" className="block text-slate-300 font-medium mb-1">
              Weights & Biases Connection <span className="text-slate-500 text-[11px]">(optional)</span>
            </label>
            <select
              id="attach-wandb-acc"
              value={attachForm.wandb_account_id}
              onChange={e => setAttachForm({ ...attachForm, wandb_account_id: e.target.value })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">None (telemetry will rely only on Kaggle logs)</option>
              {accounts.filter(a => a.provider === 'wandb').map(a => (
                <option key={a.id} value={a.id}>{a.name} ({a.principal})</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="attach-run-ref" className="block text-slate-300 font-medium mb-1">
              W&B Run Reference <span className="text-slate-500 text-[11px]">(optional)</span>
            </label>
            <input
              id="attach-run-ref"
              type="text"
              placeholder="entity/project/run-id"
              value={attachForm.run_ref}
              onChange={e => setAttachForm({ ...attachForm, run_ref: e.target.value })}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 font-mono text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-800/80">
            <button
              type="button"
              onClick={() => setIsAttachModalOpen(false)}
              className="px-3 py-2 text-xs rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!attachForm.account_id || !attachForm.kernel || attachMutation.isPending}
              className="px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 transition"
            >
              {attachMutation.isPending ? 'Attaching...' : 'Attach Kernel'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
