import { SystemStatus, Account, Notebook, NotebookLogs, Operation, BuildPreview } from '../types';

async function handleResponse<T>(res: Response): Promise<T> {
  const data = await res.json();
  if (!res.ok) {
    const msg = data.detail || data.error || (data.warnings && data.warnings[0]) || 'API request failed';
    throw new Error(msg);
  }
  return data;
}

export const api = {
  getSystemStatus: (): Promise<SystemStatus> =>
    fetch('/api/system/status').then(r => handleResponse<SystemStatus>(r)),

  getAccounts: (): Promise<Account[]> =>
    fetch('/api/accounts').then(r => handleResponse<Account[]>(r)),

  saveAccount: (payload: any): Promise<{ success: boolean; account: Account }> =>
    fetch('/api/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(r => handleResponse(r)),

  testAccount: (accountId: string): Promise<{ success: boolean; operation_id: string }> =>
    fetch(`/api/accounts/${encodeURIComponent(accountId)}/test`, { method: 'POST' }).then(r => handleResponse(r)),

  archiveAccount: (accountId: string, revision: number): Promise<{ success: boolean }> =>
    fetch(`/api/accounts/${encodeURIComponent(accountId)}?revision=${revision}`, { method: 'DELETE' }).then(r => handleResponse(r)),

  getNotebooks: (): Promise<Notebook[]> =>
    fetch('/api/notebooks').then(r => handleResponse<Notebook[]>(r)),

  getNotebookLogs: (notebookId: string): Promise<NotebookLogs> =>
    fetch(`/api/notebooks/${encodeURIComponent(notebookId)}/logs`).then(r => handleResponse<NotebookLogs>(r)),

  checkNotebook: (notebookId: string): Promise<{ success: boolean; operation_ids: string[] }> =>
    fetch(`/api/notebooks/${encodeURIComponent(notebookId)}/check`, { method: 'POST' }).then(r => handleResponse(r)),

  attachNotebook: (payload: { account_id: string; kernel: string; wandb_account_id?: string; run_ref?: string; new_attempt?: boolean }) =>
    fetch('/api/notebooks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(r => handleResponse(r)),

  getOperations: (): Promise<Operation[]> =>
    fetch('/api/operations').then(r => handleResponse<Operation[]>(r)),

  getPreviews: (accountId?: string): Promise<BuildPreview[]> =>
    fetch(`/api/previews${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''}`).then(r => handleResponse<BuildPreview[]>(r)),

  getPreviewDetail: (previewId: string): Promise<BuildPreview> =>
    fetch(`/api/previews/${encodeURIComponent(previewId)}`).then(r => handleResponse<BuildPreview>(r)),

  requestBuild: (payload: { account_id: string; options: any }): Promise<{ success: boolean; operation_id: string }> =>
    fetch('/api/previews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(r => handleResponse(r)),

  requestSubmit: (payload: { preview_id: string; options: any }): Promise<{ success: boolean; operation_id: string }> =>
    fetch('/api/submissions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(r => handleResponse(r)),

  reconcileOperation: (opId: string): Promise<{ success: boolean; message: string }> =>
    fetch(`/api/operations/${encodeURIComponent(opId)}/reconcile`, { method: 'POST' }).then(r => handleResponse(r)),

  resolveOperation: (opId: string, payload: { accepted: boolean; evidence: string; remote_version?: string }): Promise<{ success: boolean }> =>
    fetch(`/api/operations/${encodeURIComponent(opId)}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(r => handleResponse(r)),
};

