const messages = document.getElementById('messages');
const input = document.getElementById('input');
const send = document.getElementById('send');
const stop = document.getElementById('stop');
const state = document.getElementById('state');
const modal = document.getElementById('modal');
const imageInput = document.getElementById('image-input');
const previews = document.getElementById('previews');
const newChat = document.getElementById('new-chat');
const historyBox = document.getElementById('history');
const tabButtons = document.querySelectorAll('.tab');
const auditTab = document.getElementById('audit-tab');
const auditOff = document.getElementById('audit-off');
const auditLog = document.getElementById('audit-log');
const toolLog = document.getElementById('tool-log');
const thinkingLog = document.getElementById('thinking-log');
const memoryTab = document.querySelector('[data-tab="memories"]');
const memorySearch = document.getElementById('memory-search');
const memoryList = document.getElementById('memory-list');
const memoryContent = document.getElementById('memory-content');
let pendingConfirmation = null;
let pendingImages = [];
let busy = false;
let readOnly = false;
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
  send.disabled = value || readOnly;
  input.disabled = value || readOnly;
  imageInput.disabled = value || readOnly;
  newChat.disabled = value;
  stop.disabled = !value;
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
  window.__hagarStatus = data;
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
  auditTab.disabled = !a.enabled;
  auditTab.textContent = a.enabled ? 'Audit' : 'Audit off';
  auditOff.hidden = Boolean(a.enabled);
  const memory = data.memory || {};
  memoryTab.disabled = !memory.enabled;
  memoryTab.textContent = memory.enabled ? 'Memories' : 'Memories off';
  if (!a.enabled && auditTab.classList.contains('active')) {
    switchTab('chat');
  }
  if (!memory.enabled && memoryTab.classList.contains('active')) {
    switchTab('chat');
  }
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

function renderEntries(container, entries, render) {
  container.replaceChildren();
  if (!entries.length) {
    container.appendChild(el('div', 'empty', 'nessun elemento'));
    return;
  }
  for (const entry of entries) container.appendChild(render(entry));
}

async function refreshTools() {
  try {
    const data = await api('/api/tools');
    renderEntries(toolLog, data.tools, (tool) => {
      const box = el('div', 'log-entry');
      const status = tool.success === null
        ? 'in corso'
        : (tool.success ? 'ok' : 'errore');
      box.appendChild(el(
        'div',
        'meta',
        `[${tool.turn || '-'}:${tool.index || '-'}] ${tool.tool} · ${status}`
      ));
      if (tool.arguments && Object.keys(tool.arguments).length) {
        box.appendChild(el('div', '', 'args: ' + JSON.stringify(tool.arguments)));
      }
      if (tool.error) box.appendChild(el('div', 'error', tool.error));
      if (tool.output) box.appendChild(el('div', '', tool.output));
      return box;
    });
  } catch (e) { console.error(e); }
}

async function refreshAudit() {
  if (auditTab.disabled) return;
  try {
    const data = await api('/api/audit');
    auditOff.hidden = data.enabled;
    if (!data.enabled) {
      auditLog.replaceChildren();
      return;
    }
    renderEntries(auditLog, [...data.entries].reverse(), (entry) => {
      const box = el('div', 'log-entry');
      const meta = [entry.ts, entry.event].filter(Boolean).join(' · ');
      box.appendChild(el('div', 'meta', meta));
      const fields = ['tool', 'effect', 'error', 'turn'];
      for (const key of fields) {
        if (entry[key] !== undefined && entry[key] !== '') {
          box.appendChild(el('div', '', `${key}: ${entry[key]}`));
        }
      }
      return box;
    });
  } catch (e) { console.error(e); }
}

async function refreshThinking() {
  try {
    const data = await api('/api/thinking');
    thinkingLog.replaceChildren();
    for (const item of data.thinking || []) {
      const box = el('div', 'log-entry');
      box.appendChild(el('div', 'meta', 'reasoning · ' + item.ts));
      box.appendChild(el('div', '', item.text));
      thinkingLog.appendChild(box);
    }
    for (const item of data.timeline || []) {
      if (item.type === 'thinking') continue;
      const box = el('div', 'log-entry');
      box.appendChild(el('div', 'meta', item.ts + ' · ' + item.type));
      if (item.data && item.data.tool) {
        box.appendChild(el('div', '', item.data.tool));
      }
      thinkingLog.appendChild(box);
    }
    if (!thinkingLog.children.length) {
      thinkingLog.appendChild(el('div', 'empty', 'nessun evento'));
    }
  } catch (e) { console.error(e); }
}

async function refreshMemories() {
  if (memoryTab.disabled) return;
  try {
    const query = memorySearch.value.trim();
    const data = await api(
      '/api/memories?query=' + encodeURIComponent(query)
    );
    memoryList.replaceChildren();
    if (!data.documents.length) {
      memoryList.appendChild(el('div', 'empty', 'nessuna memoria'));
      return;
    }
    for (const item of data.documents) {
      const button = el('button', '', item.title || item.path);
      button.title = item.path;
      button.onclick = () => openMemory(item.path);
      memoryList.appendChild(button);
      const meta = [item.kind, item.project].filter(Boolean).join(' · ');
      if (meta) memoryList.appendChild(el('div', 'meta', meta));
    }
  } catch (e) {
    memoryList.replaceChildren(el('div', 'error', String(e)));
  }
}

async function openMemory(path) {
  try {
    const data = await api(
      '/api/memory?path=' + encodeURIComponent(path)
    );
    const memory = data.memory;
    memoryContent.textContent =
      (memory.title || memory.path) + '\n\n' + memory.content;
  } catch (e) {
    memoryContent.textContent = String(e);
  }
}

memorySearch.oninput = () => {
  clearTimeout(memorySearch._timer);
  memorySearch._timer = setTimeout(refreshMemories, 250);
};

function switchTab(name) {
  for (const button of tabButtons) {
    button.classList.toggle('active', button.dataset.tab === name);
  }
  for (const panel of document.querySelectorAll('.panel')) {
    panel.classList.toggle('active', panel.id === 'panel-' + name);
  }
  if (name === 'history') refreshHistory();
  if (name === 'tools') refreshTools();
  if (name === 'audit') refreshAudit();
  if (name === 'thinking') refreshThinking();
  if (name === 'memories') refreshMemories();
}

for (const button of tabButtons) {
  button.onclick = () => {
    if (!button.disabled) switchTab(button.dataset.tab);
  };
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

async function refreshHistory() {
  try {
    const data = await api('/api/history');
    const current = (window.__hagarStatus || {}).session_id;
    historyBox.replaceChildren();
    if (!data.chats.length) {
      historyBox.appendChild(el('div', 'muted', 'Nessuna chat'));
      return;
    }
    for (const chat of data.chats) {
      const button = el(
        'button',
        chat.id === current ? 'current' : '',
        (chat.archived ? '📦 ' : '') + chat.title
      );
      button.title = chat.date + ' · ' + chat.turns + ' turni';
      button.onclick = () => loadChat(chat.id);
      historyBox.appendChild(button);
    }
  } catch (e) { console.error(e); }
}

async function loadChat(sessionId) {
  if (busy) return;
  try {
    const data = await api('/api/resume', {
      method: 'POST',
      body: JSON.stringify({ session: sessionId }),
    });
    messages.replaceChildren();
    for (const turn of data.turns) {
      add('user', turn.question);
      add('assistant', turn.answer);
    }
    readOnly = false;
    setBusy(false, 'chat ripresa');
    switchTab('chat');
    messages.scrollTop = messages.scrollHeight;
    await refreshStatus();
    await refreshHistory();
  } catch (e) {
    add('error', String(e));
  }
}

async function startNewChat() {
  if (busy) return;
  try {
    await api('/api/new-chat', {
      method: 'POST',
      body: JSON.stringify({}),
    });
    messages.replaceChildren();
    pendingImages = [];
    renderPreviews();
    readOnly = false;
    setBusy(false);
    switchTab('chat');
    await refreshStatus();
    await refreshHistory();
  } catch (e) {
    add('error', String(e));
  }
}

newChat.onclick = startNewChat;

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
  if (type === 'turn.stop_requested') {
    state.textContent = 'interruzione...';
    return;
  }
  if (type === 'turn.cancelled') {
    if (thinking) { thinking.remove(); thinking = null; }
    add('tool', 'Turno interrotto.');
    setBusy(false);
    return;
  }
  if (type === 'tool.call') {
    add('tool', '→ ' + data.tool + ' ' + JSON.stringify(data.arguments || {}));
    if (document.getElementById('panel-tools').classList.contains('active')) refreshTools();
    return;
  }
  if (type === 'tool.result') {
    const text = data.success
      ? ('✓ ' + data.tool + ' (' + data.duration_ms + ' ms)\n' + (data.output || ''))
      : ('✗ ' + data.tool + ': ' + (data.error || 'errore'));
    add('tool', text);
    if (document.getElementById('panel-tools').classList.contains('active')) refreshTools();
    return;
  }
  if (type === 'thinking') {
    if (document.getElementById('panel-thinking').classList.contains('active')) refreshThinking();
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
    refreshHistory();
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

stop.onclick = async () => {
  stop.disabled = true;
  state.textContent = 'interruzione...';
  try {
    await api('/api/stop', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  } catch (e) {
    add('error', String(e));
    setBusy(true);
  }
};

function renderPreviews() {
  previews.replaceChildren();
  pendingImages.forEach((image, index) => {
    const box = el('div', 'preview');
    const img = document.createElement('img');
    img.src = image;
    const remove = el('button', '', '×');
    remove.title = 'Rimuovi immagine';
    remove.onclick = () => {
      pendingImages.splice(index, 1);
      renderPreviews();
    };
    box.appendChild(img);
    box.appendChild(remove);
    previews.appendChild(box);
  });
}

function pushImage(dataUrl) {
  if (pendingImages.length >= 4) return;
  pendingImages.push(dataUrl);
  renderPreviews();
}

function convertWebpToPng(dataUrl, done) {
  const image = new Image();
  image.onload = () => {
    const canvas = document.createElement('canvas');
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    canvas.getContext('2d').drawImage(image, 0, 0);
    done(canvas.toDataURL('image/png'));
  };
  image.onerror = () => add('error', 'Impossibile convertire il WebP.');
  image.src = dataUrl;
}

function addImages(files) {
  for (const file of files) {
    if (pendingImages.length >= 4) break;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      add('error', 'Formato immagine non supportato: ' + file.type);
      continue;
    }
    if (file.size > 10 * 1024 * 1024) {
      add('error', 'Immagine troppo grande (max 10 MB).');
      continue;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (file.type === 'image/webp') {
        convertWebpToPng(reader.result, pushImage);
      } else {
        pushImage(reader.result);
      }
    };
    reader.readAsDataURL(file);
  }
}

imageInput.onchange = () => {
  addImages(Array.from(imageInput.files || []));
  imageInput.value = '';
};

document.getElementById('composer').onsubmit = async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if ((!text && !pendingImages.length) || busy) return;
  const images = [...pendingImages];
  add('user', text || '[immagine]');
  if (images.length) add('tool', '🖼️ ' + images.length + ' immagine/i');
  input.value = '';
  pendingImages = [];
  renderPreviews();
  try {
    await api('/api/message', {
      method: 'POST',
      body: JSON.stringify({ text, images }),
    });
  } catch (e) {
    add('error', String(e));
    setBusy(false);
  }
};

(async () => {
  await refreshStatus();
  await refreshProjects();
  await refreshHistory();
})();
