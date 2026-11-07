const messages = document.getElementById('messages');
const input = document.getElementById('input');
const send = document.getElementById('send');
const state = document.getElementById('state');
const modal = document.getElementById('modal');
let pendingConfirmation = null;
let busy = false;
let thinking = null;

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function add(role, text) {
  const node = el('div', 'message ' + role, text);
  messages.appendChild(node);
  messages.scrollTop = messages.scrollHeight;
  return node;
}

function setBusy(value, label) {
  busy = value;
  send.disabled = value;
  input.disabled = value;
  state.textContent = label || (value ? 'in corso...' : 'pronta');
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Hagar-Token': TOKEN,
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
  return data;
}

function renderUsage(usage) {
  if (!usage) return;
  const total = usage.total_tokens || 0;
  const input = usage.input_tokens || 0;
  const output = usage.output_tokens || 0;
  document.getElementById('usage-total').textContent =
    total.toLocaleString('it-IT');
  document.getElementById('usage-detail').textContent =
    'in ' + input.toLocaleString('it-IT') +
    ' · out ' + output.toLocaleString('it-IT');
}

function renderStatus(data) {
  document.getElementById('model').textContent =
    data.model.provider + ' / ' + data.model.name;
  const p = data.project;
  document.getElementById('project').textContent =
    p ? (p.title + ' [' + p.id + ']') : 'attività libera';
  const m = data.memory || {};
  document.getElementById('memory').textContent =
    m.enabled ? 'attiva' : 'disattivata';
  const a = data.audit || {};
  document.getElementById('audit').textContent =
    a.enabled ? 'attivo' : 'disattivato';
  renderUsage(data.usage);
  if (Array.isArray(data.tools)) {
    const box = document.getElementById('tools');
    box.replaceChildren();
    for (const name of data.tools) box.appendChild(el('div', '', name));
  }
}

async function refreshStatus() {
  try { renderStatus(await api('/api/status')); } catch (e) { console.error(e); }
}

async function refreshProjects() {
  try {
    const data = await api('/api/projects');
    const box = document.getElementById('projects');
    box.replaceChildren();
    if (!data.projects.length) box.appendChild(el('div', '', 'Nessun progetto'));
    for (const project of data.projects) {
      const row = document.createElement('div');
      const button = el('button', '', project.title);
      button.onclick = () => selectProject(project.id);
      row.appendChild(button);
      row.appendChild(el('span', 'muted', ' ' + project.id));
      box.appendChild(row);
    }
  } catch (e) { console.error(e); }
}

async function selectProject(id) {
  try {
    await api('/api/project', {
      method: 'POST',
      body: JSON.stringify({ action: 'select', id }),
    });
    await refreshStatus();
    await refreshProjects();
  } catch (e) { add('error', String(e)); }
}

document.getElementById('project-refresh').onclick = refreshProjects;
document.getElementById('project-free').onclick = async () => {
  try {
    await api('/api/project', {
      method: 'POST',
      body: JSON.stringify({ action: 'free' }),
    });
    await refreshStatus();
  } catch (e) { add('error', String(e)); }
};
document.getElementById('project-new').onclick = async () => {
  const name = prompt('Nome del nuovo progetto:');
  if (!name) return;
  try {
    await api('/api/project', {
      method: 'POST',
      body: JSON.stringify({ action: 'new', name }),
    });
    await refreshStatus();
    await refreshProjects();
  } catch (e) { add('error', String(e)); }
};

function openConfirmation(data) {
  pendingConfirmation = data.id;
  document.getElementById('confirm-title').textContent =
    'Conferma: ' + data.tool;
  document.getElementById('confirm-reason').textContent =
    data.reason || '';
  document.getElementById('confirm-tool').textContent = data.tool;
  document.getElementById('confirm-capabilities').textContent =
    (data.capabilities || []).join(', ');
  document.getElementById('confirm-arguments').textContent =
    JSON.stringify(data.arguments || {}, null, 2);
  modal.classList.add('open');
}

async function answerConfirmation(approved) {
  if (!pendingConfirmation) return;
  const id = pendingConfirmation;
  pendingConfirmation = null;
  modal.classList.remove('open');
  try {
    await api('/api/confirm', {
      method: 'POST',
      body: JSON.stringify({ id, approved }),
    });
  } catch (e) {
    add('error', String(e));
  }
}

document.getElementById('confirm-allow').onclick = () => answerConfirmation(true);
document.getElementById('confirm-deny').onclick = () => answerConfirmation(false);

const source = new EventSource('/api/events?token=' + encodeURIComponent(TOKEN));

source.onmessage = (event) => {
  let payload;
  try { payload = JSON.parse(event.data); } catch (e) { return; }
  const type = payload.type;
  const data = payload.data || {};
  if (type === 'status') { renderStatus(data); return; }
  if (type === 'usage.updated') { renderUsage(data); return; }
  if (type === 'turn.start') {
    setBusy(true, 'in corso...');
    thinking = add('assistant', '…');
    return;
  }
  if (type === 'tool.call') {
    add('tool', '→ ' + data.tool + ' ' + JSON.stringify(data.arguments || {}));
    return;
  }
  if (type === 'tool.result') {
    const text = data.success
      ? ('✓ ' + data.tool + ' (' + data.duration_ms + ' ms)\n' + (data.output || ''))
      : ('✗ ' + data.tool + ': ' + (data.error || 'errore'));
    add('tool', text);
    return;
  }
  if (type === 'permission.decision') {
    if (data.effect === 'DENY') {
      add('error', 'Permesso negato: ' + data.tool + ' — ' + (data.reason || ''));
    }
    return;
  }
  if (type === 'confirmation.request') {
    openConfirmation(data);
    return;
  }
  if (type === 'confirmation.resolved') {
    if (pendingConfirmation === data.id) {
      pendingConfirmation = null;
      modal.classList.remove('open');
    }
    return;
  }
  if (type === 'turn.answer') {
    if (thinking) { thinking.remove(); thinking = null; }
    add('assistant', data.answer || '');
    setBusy(false);
    refreshStatus();
    return;
  }
  if (type === 'turn.error') {
    if (thinking) { thinking.remove(); thinking = null; }
    add('error', data.error || 'Errore');
    setBusy(false);
    return;
  }
  if (type === 'session.finished') {
    setBusy(false, 'sessione terminata');
  }
};

source.onerror = () => {
  state.textContent = 'connessione persa';
};

document.getElementById('composer').onsubmit = async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text || busy) return;
  add('user', text);
  input.value = '';
  try {
    await api('/api/message', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  } catch (e) {
    add('error', String(e));
    setBusy(false);
  }
};

refreshStatus();
refreshProjects();
