/**
 * ResearchPortal Client Application Logic
 */

let state = {
  activeTab: 'monitor',
  system: null,
  notebooks: [],
  accounts: [],
  previews: [],
  operations: [],
  expandedLogs: {},
  autoRefreshInterval: null,
};

// --- Toast System ---
function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  const colors = {
    success: 'bg-emerald-950 border border-emerald-800 text-emerald-200',
    error: 'bg-rose-950 border border-rose-800 text-rose-200',
    info: 'bg-slate-900 border border-slate-700 text-slate-200',
  }[type] || 'bg-slate-900 text-white';

  toast.className = `toast ${colors}`;
  toast.innerHTML = `
    <span>${message}</span>
    <button onclick="this.parentElement.remove()" class="ml-3 text-slate-400 hover:text-white">&times;</button>
  `;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// --- Tab Switching ---
function switchTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));

  const targetTab = document.getElementById(`tab-content-${tabId}`) || document.getElementById(`tab-${tabId}`);
  const targetNav = document.getElementById(`nav-${tabId}`);

  if (targetTab) targetTab.classList.remove('hidden');
  if (targetNav) targetNav.classList.add('active');

  if (tabId === 'monitor') fetchNotebooks();
  else if (tabId === 'submit') { fetchAccounts(); fetchPreviews(); }
  else if (tabId === 'accounts') fetchAccounts();
  else if (tabId === 'operations') fetchOperations();
}

function toggleModal(modalId) {
  const el = document.getElementById(modalId);
  if (el) el.classList.toggle('hidden');
}

// --- System Status ---
async function fetchSystemStatus() {
  try {
    const res = await fetch('/api/system/status');
    if (!res.ok) return;
    const data = await res.json();
    state.system = data;

    const badgeMode = document.getElementById('badge-mode');
    if (badgeMode) {
      badgeMode.textContent = data.mode.toUpperCase();
      badgeMode.className = data.mode === 'live'
        ? 'px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800'
        : 'px-2.5 py-1 text-xs font-semibold rounded-full bg-slate-800 text-slate-300 border border-slate-700';
    }

    const workerDot = document.getElementById('worker-dot');
    const workerText = document.getElementById('worker-text');
    if (workerDot && workerText) {
      if (data.worker_online) {
        workerDot.className = 'h-2 w-2 rounded-full bg-emerald-400 animate-pulse';
        workerText.textContent = 'Worker: Active';
      } else {
        workerDot.className = 'h-2 w-2 rounded-full bg-amber-400';
        workerText.textContent = 'Worker: Inactive';
      }
    }
  } catch (err) {
    console.error('Failed to fetch system status', err);
  }
}

// --- Notebooks & Monitor ---
async function fetchNotebooks(showFeedback = false) {
  try {
    const res = await fetch('/api/notebooks');
    if (!res.ok) throw new Error('Failed to load notebooks');
    const notebooks = await res.json();
    state.notebooks = notebooks;

    updateMonitorStats(notebooks);
    renderNotebooks(notebooks);
    if (showFeedback) showToast('Notebook observations refreshed');
  } catch (err) {
    console.error(err);
    showToast(err.message, 'error');
  }
}

function updateMonitorStats(notebooks) {
  document.getElementById('stat-total').textContent = notebooks.length;
  document.getElementById('stat-progressing').textContent = notebooks.filter(n => n.health?.health === 'progressing').length;
  document.getElementById('stat-running').textContent = notebooks.filter(n => n.health?.provider_state === 'running').length;
  document.getElementById('stat-stalled').textContent = notebooks.filter(n => n.health?.health === 'suspected_stall').length;
}

function renderNotebooks(notebooks) {
  const container = document.getElementById('notebooks-container');
  if (!notebooks.length) {
    container.innerHTML = `
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center">
        <p class="text-slate-400 text-sm">No notebooks attached yet.</p>
        <button onclick="toggleModal('modal-attach')" class="btn-primary mt-4 text-xs">Attach Your First Notebook</button>
      </div>`;
    return;
  }

  container.innerHTML = notebooks.map(nb => {
    const health = nb.health || {};
    const healthState = health.health || 'unknown';
    const stateBadgeColor = {
      progressing: 'bg-emerald-950 text-emerald-400 border-emerald-800',
      running: 'bg-blue-950 text-blue-400 border-blue-800',
      suspected_stall: 'bg-amber-950 text-amber-400 border-amber-800',
      terminal: 'bg-slate-800 text-slate-300 border-slate-700',
      pending: 'bg-purple-950 text-purple-400 border-purple-800',
      unknown: 'bg-slate-900 text-slate-400 border-slate-800',
    }[healthState] || 'bg-slate-900 text-slate-400 border-slate-800';

    const latestKaggle = nb.latest_kaggle || {};
    const kData = latestKaggle.data || {};
    const logs = kData.logs || {};
    const logProg = logs.progress || {};
    const logText = logs.text || '';
    const logLines = logText ? logText.split('\n').length : 0;
    const isLogOpen = !!state.expandedLogs[nb.id];

    return `
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm hover:border-slate-700 transition">
        <!-- Notebook Header -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div class="space-y-1">
            <div class="flex items-center space-x-3">
              <span class="text-base font-bold text-white font-mono">${escapeHtml(nb.kernel)}</span>
              <span class="px-2.5 py-0.5 text-xs font-semibold rounded-full border ${stateBadgeColor}">
                ${healthState.toUpperCase()}
              </span>
              ${nb.remote_version ? `<span class="px-2 py-0.5 text-xs font-semibold rounded bg-sky-950 text-sky-300 border border-sky-800 font-mono">v${escapeHtml(nb.remote_version)}</span>` : ''}
              <span class="text-xs text-slate-500 font-mono">(${health.provider_state || 'unknown'})</span>
            </div>
            <div class="text-xs text-slate-400 flex flex-wrap items-center gap-x-2 gap-y-1">
              <span>Connection: <strong class="text-slate-300">${escapeHtml(nb.account_name)}</strong></span>
              ${nb.run_ref ? `<span>· W&B: <strong class="text-slate-300 font-mono">${escapeHtml(nb.run_ref)}</strong></span>` : ''}
              ${nb.attempt_id ? `<span>· Attempt: <strong class="text-slate-400 font-mono text-[10px]">${nb.attempt_id.slice(0, 8)}...</strong></span>` : ''}
              ${nb.remote_version ? `<span class="text-sky-300 bg-sky-950/60 px-2 py-0.5 rounded text-[11px] border border-sky-800/60" title="Mẹo phiên bản Kaggle">💡 Mở ra v1? Tại Kaggle, mở tab <strong>Versions</strong> bên phải ➔ chọn <strong>v${escapeHtml(nb.remote_version)}</strong> ➔ <em>Pin as Default Version</em></span>` : ''}
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center space-x-2">
            <button onclick="checkNotebookNow('${nb.id}')" class="btn-primary text-xs px-3 py-1.5 shadow-sm" id="btn-check-${nb.id}">
              <svg class="w-3.5 h-3.5 mr-1 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
              Check Now
            </button>
            <a href="https://www.kaggle.com/code/${nb.kernel}" target="_blank" class="btn-secondary text-xs px-3 py-1.5" title="Mở trang notebook trên Kaggle">
              Open Kaggle ${nb.remote_version ? `(v${nb.remote_version})` : ''} ↗
            </a>
            ${nb.run_ref ? `<a href="https://wandb.ai/${nb.run_ref}" target="_blank" class="btn-secondary text-xs px-3 py-1.5">Open W&B ↗</a>` : ''}
          </div>
        </div>

        <!-- Metric Pills (when log progress or wandb iteration available) -->
        ${(logProg.epoch || logProg.iteration !== undefined || logProg.loss !== undefined || health.last_iteration) ? `
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-950 p-3 rounded-lg border border-slate-800/80">
            <div>
              <div class="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Epoch</div>
              <div class="text-sm font-bold text-white mt-0.5">${logProg.epoch || '—'}</div>
            </div>
            <div>
              <div class="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Iteration / Step</div>
              <div class="text-sm font-bold text-emerald-400 mt-0.5">${logProg.iteration ?? health.last_iteration ?? '—'}</div>
            </div>
            <div>
              <div class="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Loss</div>
              <div class="text-sm font-bold text-amber-400 mt-0.5">${logProg.loss !== undefined ? Number(logProg.loss).toFixed(4) : '—'}</div>
            </div>
            <div>
              <div class="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Log Source</div>
              <div class="text-xs font-mono text-slate-300 mt-1">${logs.source === 'cli_kernels_logs' ? 'Kaggle CLI Logs' : (logs.source || 'None')}</div>
            </div>
          </div>
        ` : ''}

        ${logProg.recent_line ? `
          <div class="text-xs text-slate-400 bg-slate-950/60 px-3 py-1.5 rounded font-mono border border-slate-800/50 flex items-center justify-between">
            <span class="truncate">Latest stdout: <span class="text-slate-300">${escapeHtml(logProg.recent_line)}</span></span>
            <span class="text-[10px] text-slate-500 shrink-0 ml-2">${latestKaggle.fetched_at ? new Date(latestKaggle.fetched_at).toLocaleTimeString() : ''}</span>
          </div>
        ` : ''}

        <!-- Collapsible Terminal Log Viewer -->
        <div class="pt-1">
          <div class="flex items-center justify-between">
            <button onclick="toggleNotebookLog('${nb.id}')" class="text-xs font-medium text-slate-400 hover:text-white flex items-center gap-1.5 transition">
              <svg class="w-3.5 h-3.5 transform ${isLogOpen ? 'rotate-90' : ''} transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
              <span>Execution Logs (${logLines} lines · ${logs.availability || 'unavailable'})</span>
            </button>
            ${isLogOpen ? `
              <div class="flex items-center space-x-2">
                <button onclick="copyLog('${nb.id}')" class="text-[11px] text-slate-400 hover:text-emerald-400 font-mono">Copy Log</button>
              </div>
            ` : ''}
          </div>

          ${isLogOpen ? `
            <div class="terminal-window mt-2">
              <div class="terminal-header">
                <div class="flex items-center space-x-1.5">
                  <span class="h-2.5 w-2.5 rounded-full bg-rose-500/80"></span>
                  <span class="h-2.5 w-2.5 rounded-full bg-amber-500/80"></span>
                  <span class="h-2.5 w-2.5 rounded-full bg-emerald-500/80"></span>
                  <span class="text-xs text-slate-400 font-mono ml-2">kaggle kernels logs ${escapeHtml(nb.kernel)}</span>
                </div>
                <span class="text-[10px] text-slate-500 font-mono">${logs.truncated ? 'Truncated to 64KB tail' : 'Full Output'}</span>
              </div>
              <div class="terminal-body" id="term-${nb.id}">${escapeHtml(logText || 'No log output published yet.')}</div>
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
}

function toggleNotebookLog(nbId) {
  state.expandedLogs[nbId] = !state.expandedLogs[nbId];
  renderNotebooks(state.notebooks);
}

function copyLog(nbId) {
  const nb = state.notebooks.find(n => n.id === nbId);
  const text = nb?.latest_kaggle?.data?.logs?.text || '';
  navigator.clipboard.writeText(text);
  showToast('Logs copied to clipboard');
}

async function checkNotebookNow(nbId) {
  const btn = document.getElementById(`btn-check-${nbId}`);
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`/api/notebooks/${nbId}/check`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Check request failed');
    showToast('Check enqueued. Refreshing observations in 2s...');
    setTimeout(() => {
      fetchNotebooks();
      if (btn) btn.disabled = false;
    }, 2000);
  } catch (err) {
    showToast(err.message, 'error');
    if (btn) btn.disabled = false;
  }
}

async function submitAttachNotebook() {
  const account_id = document.getElementById('attach-account').value;
  const kernel = document.getElementById('attach-kernel').value.trim();
  const wandb_account_id = document.getElementById('attach-wandb-acc').value || null;
  const run_ref = document.getElementById('attach-run').value.trim() || null;
  const new_attempt = document.getElementById('attach-new-attempt').checked;

  if (!kernel || !account_id) {
    showToast('Please provide Kaggle account and kernel slug', 'error');
    return;
  }

  try {
    const res = await fetch('/api/notebooks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id, kernel, wandb_account_id, run_ref, new_attempt }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Attach failed');
    showToast('Notebook attached successfully');
    toggleModal('modal-attach');
    fetchNotebooks();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// --- Accounts Management ---
async function fetchAccounts() {
  try {
    const res = await fetch('/api/accounts');
    if (!res.ok) throw new Error('Failed to load accounts');
    const accounts = await res.json();
    state.accounts = accounts;
    renderAccounts(accounts);
    populateAccountSelects(accounts);
  } catch (err) {
    console.error(err);
    showToast(err.message, 'error');
  }
}

function renderAccounts(accounts) {
  const tbody = document.getElementById('accounts-table-body');
  if (!tbody) return;
  if (!accounts.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-slate-500">No connections configured.</td></tr>`;
    return;
  }

  tbody.innerHTML = accounts.map(acc => `
    <tr class="hover:bg-slate-800/40 transition">
      <td class="px-6 py-4 font-semibold text-white">
        <div class="flex items-center space-x-2">
          <span>${escapeHtml(acc.name)}</span>
          <span class="text-xs px-2 py-0.5 rounded font-mono ${acc.provider === 'kaggle' ? 'bg-sky-950 text-sky-400 border border-sky-800' : 'bg-amber-950 text-amber-400 border border-amber-800'}">
            ${acc.provider.toUpperCase()}
          </span>
          ${acc.is_default ? '<span class="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded">DEFAULT</span>' : ''}
        </div>
      </td>
      <td class="px-6 py-4 font-mono text-xs text-slate-300">${escapeHtml(acc.principal)}</td>
      <td class="px-6 py-4">
        <span class="px-2 py-0.5 text-xs rounded font-medium ${acc.enabled ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'}">
          ${acc.enabled ? 'Enabled' : 'Disabled'}
        </span>
      </td>
      <td class="px-6 py-4 text-xs font-mono">
        ${acc.test_result ? `<span class="${acc.test_result === 'verified' ? 'text-emerald-400' : 'text-rose-400'}">${escapeHtml(acc.test_result)}</span>` : '<span class="text-slate-500">Not tested</span>'}
      </td>
      <td class="px-6 py-4 text-xs font-mono text-slate-400">rev ${acc.revision}</td>
      <td class="px-6 py-4 text-right space-x-2">
        <button onclick="testAccountConnection('${acc.id}')" class="btn-secondary text-xs py-1 px-2.5">Test</button>
        <button onclick="openEditAccountModal('${acc.id}')" class="btn-secondary text-xs py-1 px-2.5">Edit</button>
        <button onclick="archiveAccountConnection('${acc.id}', ${acc.revision})" class="text-rose-400 hover:text-rose-300 text-xs px-2">Archive</button>
      </td>
    </tr>
  `).join('');
}

function populateAccountSelects(accounts) {
  const kaggleAccounts = accounts.filter(a => a.provider === 'kaggle' && a.enabled);
  const wandbAccounts = accounts.filter(a => a.provider === 'wandb' && a.enabled);

  const submitAccount = document.getElementById('submit-account');
  if (submitAccount) {
    submitAccount.innerHTML = kaggleAccounts.map(a => `<option value="${a.id}">${escapeHtml(a.name)} (${escapeHtml(a.principal)})</option>`).join('');
  }

  const attachAccount = document.getElementById('attach-account');
  if (attachAccount) {
    attachAccount.innerHTML = kaggleAccounts.map(a => `<option value="${a.id}">${escapeHtml(a.name)}</option>`).join('');
  }

  const attachWandb = document.getElementById('attach-wandb-acc');
  if (attachWandb) {
    attachWandb.innerHTML = '<option value="">None (Monitor via Kaggle CLI logs only)</option>' +
      wandbAccounts.map(a => `<option value="${a.id}">${escapeHtml(a.name)} (${escapeHtml(a.principal)})</option>`).join('');
  }
}

function openNewAccountModal() {
  document.getElementById('modal-account-title').textContent = 'New Connection';
  document.getElementById('acc-id').value = '';
  document.getElementById('acc-rev').value = '';
  document.getElementById('acc-provider').value = 'kaggle';
  document.getElementById('acc-name').value = '';
  document.getElementById('acc-slug').value = '';
  document.getElementById('acc-principal').value = '';
  document.getElementById('acc-secret').value = '';
  document.getElementById('acc-enabled').checked = true;
  document.getElementById('acc-default').checked = false;
  toggleModal('modal-account');
}

function openEditAccountModal(accId) {
  const acc = state.accounts.find(a => a.id === accId);
  if (!acc) return;
  document.getElementById('modal-account-title').textContent = 'Edit Connection';
  document.getElementById('acc-id').value = acc.id;
  document.getElementById('acc-rev').value = acc.revision;
  document.getElementById('acc-provider').value = acc.provider;
  document.getElementById('acc-name').value = acc.name;
  document.getElementById('acc-slug').value = acc.slug;
  document.getElementById('acc-principal').value = acc.principal;
  document.getElementById('acc-secret').value = '';
  document.getElementById('acc-enabled').checked = acc.enabled;
  document.getElementById('acc-default').checked = acc.is_default;
  toggleModal('modal-account');
}

async function submitSaveAccount() {
  const id = document.getElementById('acc-id').value || null;
  const rev = document.getElementById('acc-rev').value ? parseInt(document.getElementById('acc-rev').value) : null;
  const provider = document.getElementById('acc-provider').value;
  const name = document.getElementById('acc-name').value.trim();
  const slug = document.getElementById('acc-slug').value.trim();
  const principal = document.getElementById('acc-principal').value.trim();
  const secret = document.getElementById('acc-secret').value;
  const enabled = document.getElementById('acc-enabled').checked;
  const is_default = document.getElementById('acc-default').checked;

  if (!name || !slug || !principal) {
    showToast('Name, slug and principal are required', 'error');
    return;
  }

  try {
    const res = await fetch('/api/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_id: id,
        revision: rev,
        provider,
        name,
        slug,
        principal,
        secret,
        enabled,
        is_default,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Save failed');
    showToast('Connection saved successfully');
    toggleModal('modal-account');
    fetchAccounts();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function testAccountConnection(accId) {
  try {
    const res = await fetch(`/api/accounts/${accId}/test`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Test connection enqueued failed');
    showToast('Test operation queued. Re-checking in 2s...');
    setTimeout(fetchAccounts, 2000);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function archiveAccountConnection(accId, rev) {
  if (!confirm('Are you sure you want to archive this connection?')) return;
  try {
    const res = await fetch(`/api/accounts/${accId}?revision=${rev}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Archive failed');
    showToast('Connection archived');
    fetchAccounts();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// --- Submit & Previews ---
function toggleResumeOptions() {
  const isResume = document.getElementById('submit-resume').checked;
  document.getElementById('resume-fields').classList.toggle('hidden', !isResume);
}

function getSubmitOptions() {
  const isResume = document.getElementById('submit-resume').checked;
  return {
    task: document.getElementById('submit-task').value,
    slug: document.getElementById('submit-slug').value.trim(),
    title: document.getElementById('submit-title').value.trim(),
    dataset: document.getElementById('submit-dataset').value.trim(),
    gpu: document.getElementById('submit-gpu').value === 'true',
    tracking: document.getElementById('submit-tracking').value,
    resume_run: isResume ? document.getElementById('submit-resume-run').value.trim() : '',
    resume_mode: isResume ? document.getElementById('submit-resume-mode').value : '',
    checkpoint: isResume ? document.getElementById('submit-resume-checkpoint').value : '',
  };
}

async function requestBuild() {
  const account_id = document.getElementById('submit-account').value;
  if (!account_id) {
    showToast('Please select a target Kaggle account', 'error');
    return;
  }
  const options = getSubmitOptions();

  try {
    showToast('Queuing build preview...');
    const res = await fetch('/api/previews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id, options }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Build preview request failed');
    showToast('Preview build enqueued! Fetching previews in 2s...');
    setTimeout(fetchPreviews, 2500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function fetchPreviews() {
  try {
    const res = await fetch('/api/previews');
    if (!res.ok) throw new Error('Failed to load previews');
    const previews = await res.json();
    state.previews = previews;

    const select = document.getElementById('preview-select');
    if (!select) return;
    if (!previews.length) {
      select.innerHTML = '<option value="">No completed previews</option>';
      document.getElementById('preview-details').classList.add('hidden');
      document.getElementById('preview-empty').classList.remove('hidden');
      return;
    }

    select.innerHTML = previews.map(p => {
      const date = new Date(p.created_at).toLocaleString();
      return `<option value="${p.id}">${escapeHtml(p.manifest?.kernel || p.id)} · ${date}</option>`;
    }).join('');

    loadPreviewDetail();
  } catch (err) {
    console.error(err);
  }
}

function loadPreviewDetail() {
  const select = document.getElementById('preview-select');
  const previewId = select.value;
  const p = state.previews.find(x => x.id === previewId);
  if (!p) {
    document.getElementById('preview-details').classList.add('hidden');
    document.getElementById('preview-empty').classList.remove('hidden');
    return;
  }

  document.getElementById('preview-details').classList.remove('hidden');
  document.getElementById('preview-empty').classList.add('hidden');

  document.getElementById('prev-id').textContent = p.id;
  document.getElementById('prev-kernel').textContent = p.manifest?.kernel || '—';
  document.getElementById('prev-digest').textContent = p.manifest?.bundle_digest || '—';
  document.getElementById('prev-created').textContent = new Date(p.created_at).toLocaleString();
  document.getElementById('submit-confirm').checked = false;
}

function downloadPreviewZip() {
  const select = document.getElementById('preview-select');
  if (!select.value) return;
  window.open(`/api/previews/${select.value}/download`, '_blank');
}

async function submitToKaggle() {
  const select = document.getElementById('preview-select');
  const preview_id = select.value;
  const confirmed = document.getElementById('submit-confirm').checked;

  if (!preview_id) {
    showToast('Select a preview first', 'error');
    return;
  }
  if (!confirmed) {
    showToast('Please check the confirmation box before dispatching', 'error');
    return;
  }

  const options = getSubmitOptions();

  try {
    const res = await fetch('/api/submissions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preview_id, options }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Submission dispatch failed');
    showToast('Submission dispatched successfully! Switching to Monitor...');
    setTimeout(() => {
      switchTab('monitor');
      fetchNotebooks();
    }, 1500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// --- Operations Ledger ---
async function fetchOperations() {
  try {
    const res = await fetch('/api/operations');
    if (!res.ok) throw new Error('Failed to load operations');
    const ops = await res.json();
    state.operations = ops;
    renderOperations(ops);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function renderOperations(ops) {
  const container = document.getElementById('operations-container');
  if (!container) return;
  if (!ops.length) {
    container.innerHTML = `<div class="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-500">No operations recorded yet.</div>`;
    return;
  }

  container.innerHTML = ops.map(op => {
    const stateColor = {
      succeeded: 'bg-emerald-950 text-emerald-400 border-emerald-800',
      running: 'bg-blue-950 text-blue-400 border-blue-800',
      queued: 'bg-purple-950 text-purple-400 border-purple-800',
      failed: 'bg-rose-950 text-rose-400 border-rose-800',
      unknown: 'bg-amber-950 text-amber-400 border-amber-800',
    }[op.state] || 'bg-slate-800 text-slate-400 border-slate-700';

    return `
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 text-xs space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span class="font-bold text-white uppercase tracking-wider">${escapeHtml(op.kind)}</span>
            <span class="font-mono text-slate-400">${escapeHtml(op.id)}</span>
            <span class="px-2 py-0.5 rounded border ${stateColor} font-semibold">${op.state.toUpperCase()}</span>
          </div>
          <span class="text-slate-500 font-mono">${new Date(op.created_at).toLocaleString()}</span>
        </div>
        <div class="text-slate-400">Target: <strong class="text-slate-200 font-mono">${escapeHtml(op.target || 'None')}</strong></div>
        ${op.result ? `
          <pre class="bg-slate-950 p-2.5 rounded border border-slate-800/80 overflow-x-auto text-slate-300 font-mono text-[11px]">${escapeHtml(JSON.stringify(op.result_parsed || op.result, null, 2))}</pre>
        ` : ''}
      </div>
    `;
  }).join('');
}

// --- Utilities ---
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// --- Initialize App ---
document.addEventListener('DOMContentLoaded', () => {
  fetchSystemStatus();
  fetchNotebooks();
  fetchAccounts();

  // Auto-polling for monitor tab every 12 seconds
  setInterval(() => {
    if (state.activeTab === 'monitor') {
      fetchNotebooks();
    }
  }, 12000);
});

