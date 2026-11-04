import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Play, Download, AlertTriangle, Layers, Cpu } from 'lucide-react';
import { api } from '../../lib/api';
import { Account, BuildPreview, SystemStatus } from '../../types';
import { useToast } from '../../components/Toast';
import { Modal } from '../../components/Modal';

interface BuildViewProps {
  accounts: Account[];
  status?: SystemStatus;
}

export const BuildView: React.FC<BuildViewProps> = ({ accounts, status }) => {
  const queryClient = useQueryClient();
  const { showSuccess, showError, showInfo } = useToast();
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [selectedPreview, setSelectedPreview] = useState<BuildPreview | null>(null);
  const [confirmSubmitOpen, setConfirmSubmitOpen] = useState(false);

  // Hyperparameters
  const [task, setTask] = useState<'multiclass' | 'binary'>('multiclass');
  const [epochs, setEpochs] = useState(30);
  const [lr, setLr] = useState(0.001);
  const [batchSize, setBatchSize] = useState(8);
  const [alpha, setAlpha] = useState(0.99);
  const [consistencyCost, setConsistencyCost] = useState(0.1);
  const [resumeRunId, setResumeRunId] = useState('');

  // Fetch previews
  const { data: previews = [], isLoading: isLoadingPreviews } = useQuery({
    queryKey: ['previews'],
    queryFn: () => api.getPreviews(),
    refetchInterval: 5000,
  });

  const kaggleAccounts = accounts.filter(a => a.provider === 'kaggle');

  // Build Mutation
  const buildMutation = useMutation({
    mutationFn: (payload: { account_id: string; options: any }) => api.requestBuild(payload),
    onSuccess: (data) => {
      showInfo('Build enqueued', `Operation #${data?.operation_id?.slice(0, 8) || 'active'} enqueued. Generating preview.`);
      queryClient.invalidateQueries({ queryKey: ['previews'] });
      queryClient.invalidateQueries({ queryKey: ['operations'] });
    },
    onError: (err: any) => {
      showError('Build request failed', err?.message || 'Could not queue build preview.');
    },
  });

  // Submit Mutation
  const submitMutation = useMutation({
    mutationFn: (payload: { preview_id: string; options: any }) => api.requestSubmit(payload),
    onSuccess: (data) => {
      setConfirmSubmitOpen(false);
      showSuccess('Submit enqueued', `Operation #${data?.operation_id?.slice(0, 8) || 'submit'} dispatched. Check Operations tab.`);
      queryClient.invalidateQueries({ queryKey: ['operations'] });
    },
    onError: (err: any) => {
      showError('Submit request failed', err?.message || 'Could not dispatch submit.');
    },
  });

  const handleBuild = () => {
    const accId = selectedAccountId || (kaggleAccounts[0]?.id ?? '');
    if (!accId) {
      showError('Missing account', 'Please select or configure a Kaggle account first.');
      return;
    }

    const options = {
      task,
      epochs: Number(epochs),
      lr: Number(lr),
      batch_size: Number(batchSize),
      mean_teacher_alpha: Number(alpha),
      mean_teacher_consistency_cost: Number(consistencyCost),
      resume_run_id: resumeRunId.trim() || undefined,
    };

    buildMutation.mutate({ account_id: accId, options });
  };

  const handleOpenSubmit = (preview: BuildPreview) => {
    setSelectedPreview(preview);
    setConfirmSubmitOpen(true);
  };

  return (
    <div className="space-y-6">
      {/* Parameter Configuration & Builder */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Cpu className="w-4 h-4 text-indigo-400" /> Model Build & Parameter Studio
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Build a reproducible Kaggle notebook bundle without pushing directly. Inspect parameters, manifest and source hash before submission.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          <div>
            <label className="block text-slate-400 mb-1">Target Kaggle Account</label>
            <select
              value={selectedAccountId}
              onChange={e => setSelectedAccountId(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200"
            >
              {kaggleAccounts.map(a => (
                <option key={a.id} value={a.id}>{a.name} ({a.principal})</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Segmentation Task</label>
            <select
              value={task}
              onChange={e => setTask(e.target.value as any)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200"
            >
              <option value="multiclass">Multiclass (Mean Teacher)</option>
              <option value="binary">Binary (Mean Teacher)</option>
            </select>
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Epochs</label>
            <input
              type="number"
              value={epochs}
              onChange={e => setEpochs(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 font-mono text-slate-200"
            />
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Base Learning Rate</label>
            <input
              type="number"
              step="0.0001"
              value={lr}
              onChange={e => setLr(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 font-mono text-slate-200"
            />
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Batch Size</label>
            <input
              type="number"
              value={batchSize}
              onChange={e => setBatchSize(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 font-mono text-slate-200"
            />
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Mean Teacher Alpha (EMA)</label>
            <input
              type="number"
              step="0.01"
              value={alpha}
              onChange={e => setAlpha(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 font-mono text-slate-200"
            />
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Consistency Weight Cost</label>
            <input
              type="number"
              step="0.01"
              value={consistencyCost}
              onChange={e => setConsistencyCost(Number(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 font-mono text-slate-200"
            />
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Resume W&B Run ID (Optional)</label>
            <input
              type="text"
              placeholder="e.g. devkj8qd"
              value={resumeRunId}
              onChange={e => setResumeRunId(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 font-mono text-slate-200"
            />
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <button
            onClick={handleBuild}
            disabled={buildMutation.isPending}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition disabled:opacity-50 shadow-sm"
          >
            <Play className="w-3.5 h-3.5" />
            {buildMutation.isPending ? 'Enqueuing Build...' : 'Generate Build Preview'}
          </button>
        </div>
      </div>

      {/* Generated Previews List */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
        <h2 className="text-base font-bold text-white flex items-center gap-2">
          <Layers className="w-4 h-4 text-indigo-400" /> Generated Preview Bundles ({previews.length})
        </h2>

        {isLoadingPreviews ? (
          <div className="py-6 text-center text-slate-500 text-xs font-mono">Loading previews...</div>
        ) : previews.length === 0 ? (
          <div className="py-8 text-center text-slate-500 text-xs font-mono">
            No preview bundles generated yet. Configure parameters above and click "Generate Build Preview".
          </div>
        ) : (
          <div className="space-y-3">
            {previews.map(preview => (
              <div
                key={preview.id}
                className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-4 flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-indigo-400">Bundle #{preview.id.slice(0, 8)}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300 font-mono">
                      {preview.options?.task || 'multiclass'}
                    </span>
                    <span className="text-[11px] text-slate-400 font-mono">
                      Created: {new Date(preview.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 font-mono flex flex-wrap gap-x-4 gap-y-1 pt-1">
                    <span>Epochs: <strong className="text-slate-200">{preview.options?.epochs}</strong></span>
                    <span>LR: <strong className="text-slate-200">{preview.options?.lr}</strong></span>
                    <span>Batch: <strong className="text-slate-200">{preview.options?.batch_size}</strong></span>
                    <span>Alpha: <strong className="text-slate-200">{preview.options?.mean_teacher_alpha}</strong></span>
                    <span>Kernel: <strong className="text-slate-300">{preview.manifest?.kernel_slug || 'pending'}</strong></span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <a
                    href={`/api/previews/${preview.id}/download`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition"
                  >
                    <Download className="w-3.5 h-3.5" /> Download (.zip)
                  </a>
                  <button
                    onClick={() => handleOpenSubmit(preview)}
                    className="flex items-center gap-1 px-3.5 py-1.5 text-xs font-semibold rounded bg-emerald-600 hover:bg-emerald-500 text-white transition shadow-sm"
                  >
                    <Play className="w-3.5 h-3.5" /> Submit to Kaggle
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Submit Confirmation Modal */}
      <Modal
        isOpen={confirmSubmitOpen && Boolean(selectedPreview)}
        onClose={() => setConfirmSubmitOpen(false)}
        title="Confirm Kaggle Submission"
        description="Verify dataset references, GPU accelerator quota, and secrets before dispatching."
        icon={<AlertTriangle className="w-4 h-4 text-amber-400" />}
        maxWidth="lg"
      >
        {selectedPreview && (
          <div className="space-y-4 text-xs">
            {!status?.allow_live_submit && (
              <div className="p-3 rounded-lg bg-amber-950/60 border border-amber-800 text-xs text-amber-300 space-y-1">
                <strong>Notice:</strong> <code>allow_live_submit</code> is currently <code>false</code> in settings. This submit will run in simulated mode or will be rejected if live mode is enforced.
              </div>
            )}

            <div className="space-y-2 bg-slate-950 p-4 rounded-lg border border-slate-800 font-mono text-slate-300">
              <div className="flex justify-between">
                <span className="text-slate-400">Preview Bundle ID:</span>
                <span className="text-indigo-400 font-bold">{selectedPreview.id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Target Kernel:</span>
                <span className="text-white font-bold">{selectedPreview.manifest?.kernel_slug}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Task Type:</span>
                <span className="text-white uppercase">{selectedPreview.options?.task}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Epochs / LR:</span>
                <span className="text-white">{selectedPreview.options?.epochs} epochs · lr {selectedPreview.options?.lr}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Mean Teacher Alpha:</span>
                <span className="text-white">{selectedPreview.options?.mean_teacher_alpha}</span>
              </div>
            </div>

            <p className="text-slate-400 leading-relaxed">
              Dispatching writes an immutable operation to the idempotency ledger and fences the target kernel against concurrent execution.
            </p>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-800/80">
              <button
                type="button"
                onClick={() => setConfirmSubmitOpen(false)}
                className="px-3.5 py-2 text-xs rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => submitMutation.mutate({ preview_id: selectedPreview.id, options: selectedPreview.options })}
                disabled={submitMutation.isPending}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 transition shadow-sm"
              >
                {submitMutation.isPending ? 'Submitting...' : 'Confirm & Dispatch Submit'}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

