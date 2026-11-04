import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Layers, RefreshCw, AlertCircle, CheckCircle2, Clock, HelpCircle } from 'lucide-react';
import { api } from '../../lib/api';
import { Operation } from '../../types';
import { useToast } from '../../components/Toast';
import { Modal } from '../../components/Modal';

interface OperationsViewProps {
  operations: Operation[];
}

export const OperationsView: React.FC<OperationsViewProps> = ({ operations }) => {
  const queryClient = useQueryClient();
  const { showSuccess, showError, showInfo } = useToast();
  const [filterState, setFilterState] = useState<string>('all');
  const [selectedOp, setSelectedOp] = useState<Operation | null>(null);
  const [resolveAccepted, setResolveAccepted] = useState(true);
  const [resolveEvidence, setResolveEvidence] = useState('');
  const [remoteVersion, setRemoteVersion] = useState('');

  const reconcileMutation = useMutation({
    mutationFn: (opId: string) => api.reconcileOperation(opId),
    onSuccess: (data) => {
      showInfo('Reconciliation completed', data.message || 'Operation reconciled.');
      queryClient.invalidateQueries({ queryKey: ['operations'] });
    },
    onError: (err: any) => {
      showError('Reconcile failed', err?.message || 'Failed to reconcile operation.');
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (payload: { opId: string; accepted: boolean; evidence: string; remote_version?: string }) =>
      api.resolveOperation(payload.opId, {
        accepted: payload.accepted,
        evidence: payload.evidence,
        remote_version: payload.remote_version || undefined,
      }),
    onSuccess: () => {
      showSuccess('Ambiguity resolved', 'Resolution recorded and lock released.');
      setSelectedOp(null);
      queryClient.invalidateQueries({ queryKey: ['operations'] });
    },
    onError: (err: any) => {
      showError('Resolution failed', err?.message || 'Could not record resolution.');
    },
  });

  const filteredOps = operations.filter(op => {
    if (filterState === 'all') return true;
    return op.state === filterState;
  });

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Layers className="w-4 h-4 text-indigo-400" /> Operation Ledger (Queue, Audit & Fencing)
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Strict idempotency ledger. All submit and check dispatches are locked and audited to prevent duplicate actions.
          </p>
        </div>

        {/* Filter Badges */}
        <div className="flex items-center space-x-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
          {['all', 'queued', 'running', 'succeeded', 'failed', 'unknown'].map(state => (
            <button
              key={state}
              onClick={() => setFilterState(state)}
              className={`px-2.5 py-1 rounded capitalize transition ${
                filterState === state ? 'bg-slate-800 text-white font-bold' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {state}
            </button>
          ))}
        </div>
      </div>

      <div className="divide-y divide-slate-800">
        {filteredOps.length === 0 ? (
          <div className="py-8 text-center text-slate-500 text-xs font-mono">
            No operations found matching filter "{filterState}".
          </div>
        ) : (
          filteredOps.map(op => (
            <div key={op.id} className="py-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs font-mono">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <strong className="text-slate-200 text-sm">{op.kind}</strong>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold flex items-center gap-1 ${
                      op.state === 'succeeded'
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                        : op.state === 'failed'
                        ? 'bg-rose-950 text-rose-400 border border-rose-800'
                        : op.state === 'unknown'
                        ? 'bg-amber-950 text-amber-400 border border-amber-800'
                        : op.state === 'running'
                        ? 'bg-blue-950 text-blue-400 border border-blue-800'
                        : 'bg-slate-950 text-slate-400 border border-slate-800'
                    }`}
                  >
                    {op.state === 'succeeded' && <CheckCircle2 className="w-3 h-3" />}
                    {op.state === 'failed' && <AlertCircle className="w-3 h-3" />}
                    {op.state === 'running' && <RefreshCw className="w-3 h-3 animate-spin" />}
                    {op.state === 'queued' && <Clock className="w-3 h-3" />}
                    {op.state === 'unknown' && <HelpCircle className="w-3 h-3" />}
                    {op.state}
                  </span>
                  <span className="text-slate-500 text-[11px]">#{op.id.slice(0, 8)}</span>
                </div>

                <div className="text-slate-400 text-[11px] flex flex-wrap gap-x-3 gap-y-0.5">
                  <span>Target: <strong className="text-slate-300">{op.target || 'general'}</strong></span>
                  <span>·</span>
                  <span>Enqueued: {new Date(op.enqueued_at).toLocaleTimeString()}</span>
                  {op.dispatched_at && (
                    <>
                      <span>·</span>
                      <span>Dispatched: {new Date(op.dispatched_at).toLocaleTimeString()}</span>
                    </>
                  )}
                </div>

                {op.error && (
                  <div className="text-rose-400 text-[11px] bg-rose-950/30 p-2 rounded border border-rose-900/40 mt-1 max-w-xl">
                    Error: {op.error}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-2 self-start md:self-center">
                {op.state === 'unknown' && (
                  <>
                    <button
                      onClick={() => reconcileMutation.mutate(op.id)}
                      className="px-2.5 py-1 text-xs rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
                    >
                      Reconcile
                    </button>
                    <button
                      onClick={() => setSelectedOp(op)}
                      className="px-2.5 py-1 text-xs rounded bg-amber-600 hover:bg-amber-500 text-white transition font-semibold"
                    >
                      Resolve Ambiguity
                    </button>
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Resolve Modal */}
      <Modal
        isOpen={Boolean(selectedOp)}
        onClose={() => setSelectedOp(null)}
        title={selectedOp ? `Operator Resolution for #${selectedOp.id.slice(0, 8)}` : 'Resolve Ambiguity'}
        description="When a remote dispatch times out or exits with unknown status, the kernel fence lock is retained until an operator verifies external evidence."
        icon={<HelpCircle className="w-4 h-4 text-amber-400" />}
        maxWidth="md"
      >
        {selectedOp && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (resolveEvidence) {
                resolveMutation.mutate({
                  opId: selectedOp.id,
                  accepted: resolveAccepted,
                  evidence: resolveEvidence,
                  remote_version: remoteVersion,
                });
              }
            }}
            className="space-y-4 text-xs"
          >
            <div>
              <span className="block text-slate-300 font-medium mb-1.5">Reconciliation Decision</span>
              <div className="flex flex-col sm:flex-row gap-3 bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
                  <input
                    type="radio"
                    name="decision"
                    checked={resolveAccepted}
                    onChange={() => setResolveAccepted(true)}
                    className="text-indigo-600 focus:ring-0"
                  />
                  <span>Accept (Confirmed executed on Kaggle)</span>
                </label>
                <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
                  <input
                    type="radio"
                    name="decision"
                    checked={!resolveAccepted}
                    onChange={() => setResolveAccepted(false)}
                    className="text-indigo-600 focus:ring-0"
                  />
                  <span>Reject (Failed / Release lock)</span>
                </label>
              </div>
            </div>

            <div>
              <label htmlFor="resolve-evidence" className="block text-slate-300 font-medium mb-1">
                Audit Log & Remote Evidence <span className="text-rose-400">*</span>
              </label>
              <textarea
                id="resolve-evidence"
                rows={3}
                placeholder="e.g. Verified Kaggle version 3 was successfully received, queued, and completed."
                value={resolveEvidence}
                onChange={e => setResolveEvidence(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono text-xs"
                required
              />
            </div>

            {resolveAccepted && (
              <div>
                <label htmlFor="resolve-version" className="block text-slate-300 font-medium mb-1">
                  Remote Kaggle Version <span className="text-slate-500 text-[11px]">(optional)</span>
                </label>
                <input
                  id="resolve-version"
                  type="text"
                  placeholder="e.g. 3"
                  value={remoteVersion}
                  onChange={e => setRemoteVersion(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 font-mono text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-800/80">
              <button
                type="button"
                onClick={() => setSelectedOp(null)}
                className="px-3.5 py-2 text-xs rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 transition"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!resolveEvidence || resolveMutation.isPending}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-amber-600 hover:bg-amber-500 text-white disabled:opacity-50 transition shadow-sm"
              >
                {resolveMutation.isPending ? 'Recording...' : 'Record Resolution'}
              </button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
};

