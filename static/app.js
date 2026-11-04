/**
 * ResearchPortal Client Application Logic
 */

let state = {
  activeTab: 'monitor',
  system: null,
  notebooks: [],
  accounts: [],
  previews: [],
  activePreviewDetail: null,
  operations: [],
  expandedLogs: {},
  notebookLogs: {},
  autoRefreshInterval: null,
};

// --- Utilities ---
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function extractErrorMessage(data, fallback = 'Request failed') {
  if (!data) return fallback;
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail
      .map(item => {
        const loc = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : '';
        return loc ? `${loc}: ${item.msg}` : (item.msg || JSON.stringify(item));
      })
      .join('; ');
  }
  return fallback;
}

// --- Toast System ---
function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  const colors = {
    success: 'bg-emerald-950 border border-emerald-800 text-emerald-200',
    error: 'bg-rose-950 border border-rose-800 text-rose-200',
    info: 'bg-slate-900 border border-slate-700 text-slate-200',
  }[type] || 'bg-slate-900 text-white';

  toast.className = `toast ${colors}`;
  toast.innerHTML = `
    <span>${escapeHtml(message)}</span>
    <button onclick="this.parentElement.remove()" class="ml-3 text-slate-400 hover:text-white">&times;</button>
  `;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4500);
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
  else if (tabId === 'submit') { fetchAccounts().then(() => fetchPreviews()); }
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
      badgeMode.textContent = data.mode === 'fixture' ? 'FIXTURE / DEMO' : 'LIVE';
      badgeMode.className = data.mode === 'live'
        ? 'px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800'
        : 'px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-950 text-amber-300 border border-amber-800';
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
    updateDispatchButtonState();
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

    // Refresh any open log viewers
    const openLogIds = Object.keys(state.expandedLogs).filter(id => state.expandedLogs[id]);
    await Promise.all(openLogIds.map(id => fetchNotebookLogText(id)));

    updateMonitorStats(notebooks);
    renderNotebooks(notebooks);
    if (showFeedback) showToast('Notebook observations refreshed');
  } catch (err) {
    console.error(err);
    showToast(err.message, 'error');
  }
}

async function fetchNotebookLogText(nbId) {
  try {
    const res = await fetch(`/api/notebooks/${encodeURIComponent(nbId)}/logs`);
    if (res.ok) {
      state.notebookLogs[nbId] = await res.json();
    }
  } catch (err) {
    console.error('Failed to fetch logs for notebook', nbId, err);
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
  if (!container) return;
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
    const latestWandb = nb.latest_wandb || null;
    const wData = (latestWandb && !latestWandb.error) ? (latestWandb.data || {}) : {};
    const wSummary = wData.summary || {};

    const logsSummary = nb.logs_summary || {};
    const logProg = logsSummary.progress || {};
    const cachedLog = state.notebookLogs[nb.id] || {};
    const logText = cachedLog.text || '';
    const logLines = logsSummary.line_count ?? (logText ? logText.split('\n').length : 0);
    const isLogOpen = !!state.expandedLogs[nb.id];
    const safeId = escapeHtml(nb.id);
    const safeKernel = escapeHtml(nb.kernel);
    const safeVer = escapeHtml(nb.remote_version);

    const summaryMetrics = Object.entries(wSummary)
      .filter(([, v]) => typeof v === 'number')
      .slice(0, 4)
      .map(([k, v]) => `<span class="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 font-mono text-[11px] text-slate-300">${escapeHtml(k)}: <strong class="text-emerald-400">${Number(v).toFixed(4)}</strong></span>`)
      .join(' ');

    return `
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm hover:border-slate-700 transition">
        <!-- Notebook Header -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div class="space-y-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-base font-bold text-white font-mono">${safeKernel}</span>
              <span class="px-2.5 py-0.5 text-xs font-semibold rounded-full border ${stateBadgeColor}">
                HEALTH: ${escapeHtml(healthState.toUpperCase())}
              </span>
              <span class="px-2 py-0.5 text-xs rounded bg-slate-950 border border-slate-800 font-mono text-slate-300">
                Kaggle: ${escapeHtml(health.provider_state || 'unknown')}
              </span>
              ${health.status_stale ? `<span class="px-2 py-0.5 text-[11px] font-semibold rounded bg-amber-950/80 text-amber-300 border border-amber-800">STALE</span>` : ''}
              ${nb.remote_version ? `<span class="px-2 py-0.5 text-xs font-semibold rounded bg-sky-950 text-sky-300 border border-sky-800 font-mono">v${safeVer}</span>` : `<span class="text-[11px] text-slate-500 font-mono">version: unverified</span>`}
            </div>
            <div class="text-xs text-slate-400 flex flex-wrap items-center gap-x-2 gap-y-1">
              <span>Connection: <strong class="text-slate-300">${escapeHtml(nb.account_name)}</strong></span>
              ${nb.run_ref ? `<span>· W&amp;B: <strong class="text-slate-300 font-mono">${escapeHtml(nb.run_ref)}</strong> (${escapeHtml(nb.wandb_account_name || 'bound')})</span>` : ''}
              ${nb.attempt_id ? `<span>· Attempt: <strong class="text-slate-400 font-mono text-[10px]">${escapeHtml(nb.attempt_id.slice(0, 8))}...</strong> (submitted ver: ${escapeHtml(nb.submitted_version || 'unverified')})</span>` : ''}
              ${health.provider_observed_at ? `<span>· Observed: <span class="font-mono text-slate-400">${escapeHtml(new Date(health.provider_observed_at).toLocaleTimeString())}</span></span>` : ''}
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center space-x-2">
            <button onclick="checkNotebookNow('${safeId}')" class="btn-primary text-xs px-3 py-1.5 shadow-sm" id="btn-check-${safeId}">
              <svg class="w-3.5 h-3.5 mr-1 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
              Check Now
            </button>
            <a href="https://www.kaggle.com/code/${safeKernel}" target="_blank" rel="noopener noreferrer" class="btn-secondary text-xs px-3 py-1.5" title="Open notebook on Kaggle">
              Open Kaggle ${nb.remote_version ? `(v${safeVer})` : ''} ↗
            </a>
            ${nb.run_ref ? `<a href="https://wandb.ai/${escapeHtml(nb.run_ref)}" target="_blank" rel="noopener noreferrer" class="btn-secondary text-xs px-3 py-1.5">Open W&amp;B ↗</a>` : ''}
          </div>
        </div>

        <!-- Provider / W&B Check Error Warnings (Cached state preserved) -->
        ${health.last_check_error ? `
          <div class="p-2.5 rounded-lg bg-amber-950/50 border border-amber-800/80 text-xs text-amber-200 font-mono">
            ⚠️ Last Kaggle check error: <strong>${escapeHtml(health.last_check_error)}</strong> (at ${health.last_check_attempt_at ? escapeHtml(new Date(health.last_check_attempt_at).toLocaleTimeString()) : 'unknown'}). Cached provider state is preserved.
          </div>
        ` : ''}
        ${(latestWandb && latestWandb.error) ? `
          <div class="p-2.5 rounded-lg bg-amber-950/50 border border-amber-800/80 text-xs text-amber-200 font-mono">
            ⚠️ Last W&amp;B check error: <strong>${escapeHtml(latestWandb.error)}</strong> (at ${latestWandb.fetched_at ? escapeHtml(new Date(latestWandb.fetched_at).toLocaleTimeString()) : 'unknown'}).
          </div>
        ` : ''}

        <!-- Distinct Signals Panel: W&B Tracking vs Kaggle Log Progress -->
        <div class="grid grid-cols-2 sm:grid-cols-5 gap-3 bg-slate-950 p-3 rounded-lg border border-slate-800/80">
          <div>
            <div class="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Iteration / Step</div>
            <div class="text-sm font-bold text-emerald-400 mt-0.5">${escapeHtml(health.last_iteration ?? logProg.iteration ?? 'Unavailable')}</div>
            <div class="text-[10px] text-slate-500 font-mono">${wData.last_iteration !== undefined && wData.last_iteration !== null ? 'Source: W&B' : (logProg.iteration !== undefined ? 'Source: Kaggle Logs' : 'No progress axis yet')}</div>
          </div>
          <div>
            <div class="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Last Progress Increase</div>
            <div class="text-xs font-mono text-slate-200 mt-1">${health.last_progress_at ? escapeHtml(new Date(health.last_progress_at).toLocaleTimeString()) : 'Unverified'}</div>
          </div>
          <div>
            <div class="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">W&amp;B Heartbeat</div>
            <div class="text-xs font-mono text-slate-200 mt-1">${wData.last_telemetry_at ? escapeHtml(new Date(wData.last_telemetry_at).toLocaleTimeString()) : (nb.run_ref ? 'Unavailable' : 'No W&B bound')}</div>
            ${wData.state ? `<div class="text-[10px] text-slate-500 font-mono">Run state: ${escapeHtml(wData.state)}</div>` : ''}
          </div>
          <div>
            <div class="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Epoch / Loss (Logs)</div>
            <div class="text-xs font-mono text-amber-400 mt-1">
              ${escapeHtml(logProg.epoch || '—')} · ${logProg.loss !== undefined ? Number(logProg.loss).toFixed(4) : '—'}
            </div>
          </div>
          <div>
            <div class="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Log Availability</div>
            <div class="text-xs font-mono text-slate-300 mt-1">${escapeHtml(logsSummary.availability || 'not_yet_published')}</div>
            <div class="text-[10px] text-slate-500 font-mono">${escapeHtml(logsSummary.source || 'none')}</div>
          </div>
        </div>

        ${summaryMetrics ? `
          <div class="flex flex-wrap items-center gap-2 text-xs">
            <span class="text-slate-400 font-medium">W&amp;B Summary:</span>
            ${summaryMetrics}
          </div>
        ` : ''}

        ${logProg.recent_line ? `
          <div class="text-xs text-slate-400 bg-slate-950/60 px-3 py-1.5 rounded font-mono border border-slate-800/50 flex items-center justify-between">
            <span class="truncate">Latest stdout: <span class="text-slate-300">${escapeHtml(logProg.recent_line)}</span></span>
            <span class="text-[10px] text-slate-500 shrink-0 ml-2">${latestKaggle.fetched_at ? escapeHtml(new Date(latestKaggle.fetched_at).toLocaleTimeString()) : ''}</span>
          </div>
        ` : ''}

        <!-- Collapsible Terminal Log Viewer -->
        <div class="pt-1">
          <div class="flex items-center justify-between">
            <button onclick="toggleNotebookLog('${safeId}')" class="text-xs font-medium text-slate-400 hover:text-white flex items-center gap-1.5 transition">
              <svg class="w-3.5 h-3.5 transform ${isLogOpen ? 'rotate-90' : ''} transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
              <span>Execution Logs (${escapeHtml(logLines)} lines · ${escapeHtml(logsSummary.availability || 'unavailable')})</span>
            </button>
            ${isLogOpen ? `
              <div class="flex items-center space-x-2">
                <button onclick="copyLog('${safeId}')" class="text-[11px] text-slate-400 hover:text-emerald-400 font-mono">Copy Log</button>
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
                  <span class="text-xs text-slate-400 font-mono ml-2">kaggle kernels logs ${safeKernel}</span>
                </div>
                <span class="text-[10px] text-slate-500 font-mono">${logsSummary.truncated ? 'Truncated to 64KB tail' : 'Output'}</span>
              </div>
              <div class="terminal-body" id="term-${safeId}">${escapeHtml(logText || 'No log output published yet.')}</div>
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
}

async function toggleNotebookLog(nbId) {
  state.expandedLogs[nbId] = !state.expandedLogs[nbId];
  if (state.expandedLogs[nbId]) {
    await fetchNotebookLogText(nbId);
  }
  renderNotebooks(state.notebooks);
}

function copyLog(nbId) {
  const text = state.notebookLogs[nbId]?.text || '';
  navigator.clipboard.writeText(text);
  showToast('Logs copied to clipboard');
}

async function checkNotebookNow(nbId) {
  const btn = document.getElementById(`btn-check-${nbId}`);
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`/api/notebooks/${encodeURIComponent(nbId)}/check`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(extractErrorMessage(data, 'Check request failed'));
    showToast('Check enqueued. Refreshing observations in 1.5s...');
    setTimeout(() => {
      fetchNotebooks();
      if (btn) btn.disabled = false;
    }, 1500);
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
    showToast('Please provide Kaggle account and kernel owner/slug', 'error');
    return;
  }

  try {
    const res = await fetch('/api/notebooks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id, kernel, wandb_account_id, run_ref, new_attempt }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(extractErrorMessage(data, 'Attach failed'));
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

  tbody.innerHTML = accounts.map(acc => {
    const safeId = escapeHtml(acc.id);
    const rev = Number(acc.revision) || 1;
    return `
      <tr class="hover:bg-slate-800/40 transition">
        <td class="px-6 py-4 font-semibold text-white">
          <div class="flex items-center space-x-2">
            <span>${escapeHtml(acc.name)}</span>
            <span class="text-xs px-2 py-0.5 rounded font-mono ${acc.provider === 'kaggle' ? 'bg-sky-950 text-sky-400 border border-sky-800' : 'bg-amber-950 text-amber-400 border border-amber-800'}">
              ${escapeHtml(acc.provider.toUpperCase())}
            </span>
            ${acc.is_default ? '<span class="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded">DEFAULT</span>' : ''}
          </div>
          ${acc.description ? `<div class="text-xs text-slate-400 font-normal mt-0.5">${escapeHtml(acc.description)}</div>` : ''}
        </td>
        <td class="px-6 py-4 font-mono text-xs text-slate-300">${escapeHtml(acc.principal)}</td>
        <td class="px-6 py-4">
          <span class="px-2 py-0.5 text-xs rounded font-medium ${acc.enabled ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'}">
            ${acc.enabled ? 'Enabled' : 'Disabled'}
          </span>
          <span class="text-[11px] font-mono text-slate-500 ml-1">${acc.configured ? '(key set)' : '(no key)'}</span>
        </td>
        <td class="px-6 py-4 text-xs font-mono">
          ${acc.test_result ? `<span class="${acc.test_result === 'verified' ? 'text-emerald-400' : 'text-rose-400'}">${escapeHtml(acc.test_result)}</span>` : '<span class="text-slate-500">Not tested</span>'}
        </td>
        <td class="px-6 py-4 text-xs font-mono text-slate-400">rev ${rev}</td>
        <td class="px-6 py-4 text-right space-x-2">
          <button onclick="testAccountConnection('${safeId}')" class="btn-secondary text-xs py-1 px-2.5">Test</button>
          <button onclick="openEditAccountModal('${safeId}')" class="btn-secondary text-xs py-1 px-2.5">Edit</button>
          <button onclick="archiveAccountConnection('${safeId}', ${rev})" class="text-rose-400 hover:text-rose-300 text-xs px-2">Archive</button>
        </td>
      </tr>
    `;
  }).join('');
}

function populateAccountSelects(accounts) {
  const kaggleAccounts = accounts
    .filter(a => a.provider === 'kaggle' && a.enabled)
    .sort((a, b) => (b.is_default ? 1 : 0) - (a.is_default ? 1 : 0));
  const wandbAccounts = accounts.filter(a => a.provider === 'wandb' && a.enabled);

  const submitAccount = document.getElementById('submit-account');
  if (submitAccount) {
    const prevValue = submitAccount.value;
    submitAccount.innerHTML = kaggleAccounts.map(a => `<option value="${escapeHtml(a.id)}">${escapeHtml(a.name)} (${escapeHtml(a.principal)})</option>`).join('');
    if (prevValue && kaggleAccounts.some(a => a.id === prevValue)) {
      submitAccount.value = prevValue;
    }
  }

  const attachAccount = document.getElementById('attach-account');
  if (attachAccount) {
    attachAccount.innerHTML = kaggleAccounts.map(a => `<option value="${escapeHtml(a.id)}">${escapeHtml(a.name)}</option>`).join('');
  }

  const attachWandb = document.getElementById('attach-wandb-acc');
  if (attachWandb) {
    attachWandb.innerHTML = '<option value="">None (Monitor via Kaggle CLI logs only)</option>' +
      wandbAccounts.map(a => `<option value="${escapeHtml(a.id)}">${escapeHtml(a.name)} (${escapeHtml(a.principal)})</option>`).join('');
  }
}

function openNewAccountModal() {
  document.getElementById('modal-account-title').textContent = 'New Connection';
  document.getElementById('acc-id').value = '';
  document.getElementById('acc-rev').value = '';
  const providerEl = document.getElementById('acc-provider');
  providerEl.value = 'kaggle';
  providerEl.disabled = false;
  document.getElementById('acc-name').value = '';
  document.getElementById('acc-slug').value = '';
  document.getElementById('acc-principal').value = '';
  document.getElementById('acc-description').value = '';
  document.getElementById('acc-secret').value = '';
  document.getElementById('acc-enabled').checked = true;
  document.getElementById('acc-default').checked = false;
  toggleModal('modal-account');
}

function openEditAccountModal(accId) {
  const acc = state.accounts.find(a => a.id === accId);
  if (!acc) return;
  document.getElementById('modal-account-title').textContent = `Edit Connection (rev ${acc.revision})`;
  document.getElementById('acc-id').value = acc.id;
  document.getElementById('acc-rev').value = acc.revision;
  const providerEl = document.getElementById('acc-provider');
  providerEl.value = acc.provider;
  providerEl.disabled = true;
  document.getElementById('acc-name').value = acc.name;
  document.getElementById('acc-slug').value = acc.slug;
  document.getElementById('acc-principal').value = acc.principal;
  document.getElementById('acc-description').value = acc.description || '';
  document.getElementById('acc-secret').value = '';
  document.getElementById('acc-enabled').checked = Boolean(acc.enabled);
  document.getElementById('acc-default').checked = Boolean(acc.is_default);
  toggleModal('modal-account');
}

async function submitSaveAccount() {
  const id = document.getElementById('acc-id').value || null;
  const rev = document.getElementById('acc-rev').value ? parseInt(document.getElementById('acc-rev').value, 10) : null;
  const provider = document.getElementById('acc-provider').value;
  const name = document.getElementById('acc-name').value.trim();
  const slug = document.getElementById('acc-slug').value.trim();
  const principal = document.getElementById('acc-principal').value.trim();
  const description = document.getElementById('acc-description').value;
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
        description,
        secret,
        enabled,
        is_default,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(extractErrorMessage(data, 'Save failed'));
    showToast('Connection saved. Verification is a separate operation.');
    toggleModal('modal-account');
    fetchAccounts();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function testAccountConnection(accId) {
  try {
    const res = await fetch(`/api/accounts/${encodeURIComponent(accId)}/test`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(extractErrorMessage(data, 'Test connection failed'));
    showToast('Test operation queued. Re-checking in 1.5s...');
    setTimeout(fetchAccounts, 1500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function archiveAccountConnection(accId, rev) {
  if (!confirm('Archive this connection? Cached observations and lineage will be preserved.')) return;
  try {
    const res = await fetch(`/api/accounts/${encodeURIComponent(accId)}?revision=${encodeURIComponent(rev)}`, { method: 'DELETE' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(extractErrorMessage(data, 'Archive failed'));
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
  checkPreviewOptionParity();
}

function getSubmitOptions() {
  const isResume = document.getElementById('submit-resume').checked;
  return {
    template: 'mean_teacher',
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

function optionsMatch(a, b) {
  if (!a || !b) return true;
  const keys = ['template', 'task', 'slug', 'title', 'dataset', 'gpu', 'tracking', 'resume_run', 'resume_mode', 'checkpoint'];
  return keys.every(k => (a[k] ?? '') === (b[k] ?? ''));
}

function checkPreviewOptionParity() {
  const mismatchBanner = document.getElementById('prev-options-mismatch');
  if (!mismatchBanner || !state.activePreviewDetail) return;
  const current = getSubmitOptions();
  const matches = optionsMatch(current, state.activePreviewDetail.options);
  mismatchBanner.classList.toggle('hidden', matches);
  updateDispatchButtonState();
}

function updateDispatchButtonState() {
  const btn = document.getElementById('btn-dispatch');
  const confirmEl = document.getElementById('submit-confirm');
  const liveDisabledBanner = document.getElementById('live-submit-disabled-banner');
  if (!btn || !confirmEl) return;

  const isFixture = state.system?.mode === 'fixture';
  const liveAllowed = isFixture || Boolean(state.system?.allow_live_submit);

  if (liveDisabledBanner) {
    liveDisabledBanner.classList.toggle('hidden', isFixture || liveAllowed);
  }

  btn.textContent = isFixture ? '🧪 Simulate Submit (Fixture Mode)' : '🚀 Submit Notebook to Kaggle';

  const hasMatchingOptions = state.activePreviewDetail
    ? optionsMatch(getSubmitOptions(), state.activePreviewDetail.options)
    : false;

  btn.disabled = !(confirmEl.checked && liveAllowed && hasMatchingOptions);
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
    if (!res.ok) throw new Error(extractErrorMessage(data, 'Build preview request failed'));
    showToast('Preview build enqueued! Refreshing previews in 1.5s...');
    setTimeout(fetchPreviews, 1500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function fetchPreviews() {
  try {
    const accountId = document.getElementById('submit-account')?.value || '';
    const url = accountId ? `/api/previews?account_id=${encodeURIComponent(accountId)}` : '/api/previews';
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to load previews');
    const previews = await res.json();
    state.previews = previews;

    const select = document.getElementById('preview-select');
    if (!select) return;
    if (!previews.length) {
      state.activePreviewDetail = null;
      select.innerHTML = '<option value="">No completed previews for this account</option>';
      document.getElementById('preview-details').classList.add('hidden');
      document.getElementById('preview-empty').classList.remove('hidden');
      return;
    }

    select.innerHTML = previews.map(p => {
      const date = new Date(p.created_at).toLocaleString();
      const kernel = p.manifest?.kernel || p.id;
      return `<option value="${escapeHtml(p.id)}">${escapeHtml(kernel)} · ${escapeHtml(date)}</option>`;
    }).join('');

    await loadPreviewDetail();
  } catch (err) {
    console.error(err);
  }
}

async function loadPreviewDetail() {
  const select = document.getElementById('preview-select');
  const previewId = select?.value;
  if (!previewId) {
    state.activePreviewDetail = null;
    document.getElementById('preview-details').classList.add('hidden');
    document.getElementById('preview-empty').classList.remove('hidden');
    return;
  }

  try {
    const res = await fetch(`/api/previews/${encodeURIComponent(previewId)}`);
    if (!res.ok) throw new Error('Failed to load preview detail');
    const p = await res.json();
    state.activePreviewDetail = p;

    document.getElementById('preview-details').classList.remove('hidden');
    document.getElementById('preview-empty').classList.add('hidden');

    const manifest = p.manifest || {};
    const datasets = manifest.metadata?.dataset_sources || [];
    document.getElementById('prev-id').textContent = p.id;
    document.getElementById('prev-kernel').textContent = manifest.kernel || '—';
    document.getElementById('prev-datasets').textContent = datasets.length ? datasets.join(', ') : '(none / synthetic)';
    document.getElementById('prev-revision').textContent = manifest.source_revision || '—';
    document.getElementById('prev-digest').textContent = manifest.bundle_digest || '—';
    document.getElementById('prev-created').textContent = new Date(p.created_at).toLocaleString();

    const warningsEl = document.getElementById('prev-warnings');
    const warnings = manifest.warnings || [];
    if (warnings.length) {
      warningsEl.innerHTML = warnings.map(w => `<div>⚠️ ${escapeHtml(w)}</div>`).join('');
      warningsEl.classList.remove('hidden');
    } else {
      warningsEl.classList.add('hidden');
    }

    const codeEl = document.getElementById('prev-notebook-code');
    if (codeEl) {
      codeEl.textContent = p.notebook || '';
    }

    document.getElementById('submit-confirm').checked = false;
    checkPreviewOptionParity();
  } catch (err) {
    console.error(err);
  }
}

function togglePreviewNotebookCode() {
  const container = document.getElementById('prev-notebook-container');
  if (container) container.classList.toggle('hidden');
}

function downloadPreviewZip() {
  const select = document.getElementById('preview-select');
  if (!select?.value) return;
  window.open(`/api/previews/${encodeURIComponent(select.value)}/download`, '_blank');
}

async function submitToKaggle() {
  const select = document.getElementById('preview-select');
  const preview_id = select?.value;
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
    if (!res.ok) throw new Error(extractErrorMessage(data, 'Submission dispatch failed'));
    showToast('Submission operation queued! Switching to Monitor...');
    setTimeout(() => {
      switchTab('monitor');
      fetchNotebooks();
    }, 1500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// --- Operations Ledger & Ambiguous Submission Reconciliation ---
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
      reconciling: 'bg-amber-950 text-amber-400 border-amber-800',
      cancelled: 'bg-slate-800 text-slate-400 border-slate-700',
    }[op.state] || 'bg-slate-800 text-slate-400 border-slate-700';

    const safeId = escapeHtml(op.id);
    const needsAdjudication = op.kind === 'submit' && (op.state === 'unknown' || op.state === 'reconciling');

    return `
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 text-xs space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <span class="font-bold text-white uppercase tracking-wider">${escapeHtml(op.kind)}</span>
            <span class="font-mono text-slate-400">${safeId}</span>
            <span class="px-2 py-0.5 rounded border ${stateColor} font-semibold">${escapeHtml(op.state.toUpperCase())}</span>
          </div>
          <span class="text-slate-500 font-mono">${escapeHtml(new Date(op.created_at).toLocaleString())}</span>
        </div>
        <div class="flex flex-wrap gap-x-4 gap-y-1 text-slate-400">
          <span>Target: <strong class="text-slate-200 font-mono">${escapeHtml(op.target || 'None')}</strong></span>
          ${op.error ? `<span>Error: <strong class="text-rose-400 font-mono">${escapeHtml(op.error)}</strong></span>` : ''}
        </div>
        ${op.result ? `
          <pre class="bg-slate-950 p-2.5 rounded border border-slate-800/80 overflow-x-auto text-slate-300 font-mono text-[11px]">${escapeHtml(JSON.stringify(op.result_parsed || op.result, null, 2))}</pre>
        ` : ''}
        ${needsAdjudication ? `
          <div class="p-4 bg-amber-950/30 border border-amber-800/80 rounded-lg space-y-3">
            <div class="text-amber-200 font-medium">
              ⚠️ Ambiguous submission outcome: Target lock is held to prevent duplicate dispatch. Do not blindly retry push. Inspect remote Kaggle versions against the preview before adjudicating.
            </div>
            <div>
              <button onclick="reconcileOperation('${safeId}')" class="btn-secondary text-xs">
                Read Remote Reconciliation Evidence
              </button>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-amber-900/60">
              <div>
                <label class="form-label text-xs">Operator Finding</label>
                <select id="res-finding-${safeId}" class="form-input text-xs">
                  <option value="accepted">accepted (Remote kernel version confirmed)</option>
                  <option value="not_sent">not_sent (Release lock; build new preview to retry)</option>
                </select>
              </div>
              <div>
                <label class="form-label text-xs">Observed Remote Version (Required if accepted)</label>
                <input type="text" id="res-ver-${safeId}" placeholder="e.g. v3 or 3" class="form-input text-xs font-mono">
              </div>
            </div>
            <div>
              <label class="form-label text-xs">Operator Evidence (No tokens or signed URLs)</label>
              <textarea id="res-ev-${safeId}" rows="2" placeholder="Describe how you verified the remote version or absence of submission..." class="form-input text-xs"></textarea>
            </div>
            <div class="flex items-center justify-between pt-1">
              <label class="flex items-center space-x-2 text-xs text-amber-200">
                <input type="checkbox" id="res-chk-${safeId}" class="rounded border-amber-700 bg-slate-900 text-emerald-500">
                <span>I checked the remote version against this preview</span>
              </label>
              <button onclick="submitResolveOperation('${safeId}')" class="btn-primary text-xs">
                Record Operator Resolution
              </button>
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }).join('');
}

async function reconcileOperation(opId) {
  try {
    const res = await fetch(`/api/operations/${encodeURIComponent(opId)}/reconcile`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(extractErrorMessage(data, 'Reconciliation request failed'));
    showToast('Reconciliation probe queued. Refreshing operations in 1.5s...');
    setTimeout(fetchOperations, 1500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function submitResolveOperation(opId) {
  const verified = document.getElementById(`res-chk-${opId}`)?.checked;
  if (!verified) {
    showToast('Please confirm that you checked the remote version against this preview', 'error');
    return;
  }
  const finding = document.getElementById(`res-finding-${opId}`)?.value;
  const remote_version = document.getElementById(`res-ver-${opId}`)?.value.trim() || '';
  const evidence = document.getElementById(`res-ev-${opId}`)?.value.trim() || '';

  try {
    const res = await fetch(`/api/operations/${encodeURIComponent(opId)}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        accepted: finding === 'accepted',
        remote_version,
        evidence,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(extractErrorMessage(data, 'Operator resolution failed'));
    showToast('Operator resolution recorded');
    fetchOperations();
    fetchNotebooks();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// --- Initialize App ---
document.addEventListener('DOMContentLoaded', () => {
  fetchSystemStatus();
  fetchNotebooks();
  fetchAccounts();

  // Auto-polling for active monitor/operations tabs every 12 seconds
  setInterval(() => {
    fetchSystemStatus();
    if (state.activeTab === 'monitor') {
      fetchNotebooks();
    } else if (state.activeTab === 'operations') {
      fetchOperations();
    }
  }, 12000);
});
