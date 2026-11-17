const memoryState = {
  kind: 'project',
  loading: false,
};

const memoryLabels = {
  project: 'Memorie di progetto candidate',
  skill: 'Skill candidate',
  summary: 'Sommari candidati',
};

function setMemoryStatus(text, isError) {
  const box = document.getElementById('status');
  box.textContent = text || '';
  box.classList.toggle('error', Boolean(isError));
}

function memoryText(item) {
  const text = String(item.text || '').replace(/\s+/g, ' ').trim();
  return text || '(vuoto)';
}

function memoryMeta(item) {
  const parts = [];
  if (item.project) {
    parts.push(item.project_title || item.project);
  }
  if (item.created_at) {
    parts.push(item.created_at);
  }
  return parts.join(' · ');
}

async function actOnMemory(item, action) {
  if (memoryState.loading) return;

  if (action === 'delete') {
    const ok = confirm(
      'Eliminare definitivamente questa memoria?\n\n' +
      (item.title || item.id)
    );
    if (!ok) return;
  }

  memoryState.loading = true;
  setMemoryStatus(
    action === 'delete' ? 'Eliminazione…' : 'Aggiornamento…'
  );

  try {
    await adminApi('/api/memories/action', {
      method: 'POST',
      body: JSON.stringify({
        kind: memoryState.kind,
        id: item.id,
        action,
      }),
    });
    await loadMemories();
    setMemoryStatus('Memoria aggiornata.');
  } catch (error) {
    setMemoryStatus(String(error), true);
  } finally {
    memoryState.loading = false;
  }
}

function renderMemories(items) {
  const box = document.getElementById('memory-list');
  box.replaceChildren();

  if (!items.length) {
    box.appendChild(el('div', 'muted', 'Nessuna memoria in questa vista.'));
    return;
  }

  for (const item of items) {
    const row = el('div', 'memory-row');

    const line = el('div', 'memory-line');
    line.appendChild(
      el(
        'span',
        'memory-kind',
        item.kind === 'project' ? 'progetto' : item.kind
      )
    );
    line.appendChild(
      el('span', 'memory-title', item.title || item.id)
    );
    line.appendChild(
      el('span', 'memory-text', memoryText(item))
    );

    const meta = memoryMeta(item);
    if (meta) {
      line.appendChild(el('span', 'memory-meta', meta));
    }

    const actions = el('div', 'memory-actions');

    for (const [action, label] of [
      ['confirm', 'Conferma'],
      ['archive', 'Archivia'],
      ['delete', 'Elimina'],
    ]) {
      const button = el(
        'button',
        'memory-action ' + action,
        label
      );
      button.type = 'button';
      button.onclick = () => actOnMemory(item, action);
      actions.appendChild(button);
    }

    row.append(line, actions);
    box.appendChild(row);
  }
}

async function loadMemories() {
  const label = document.getElementById('memory-kind-label');
  label.textContent = memoryLabels[memoryState.kind] || 'Memorie';

  try {
    const data = await adminApi(
      '/api/memories?kind=' +
        encodeURIComponent(memoryState.kind)
    );
    renderMemories(data.items || []);
    setMemoryStatus('');
  } catch (error) {
    setMemoryStatus(String(error), true);
  }
}

for (const tab of document.querySelectorAll('.memory-tab')) {
  tab.onclick = () => {
    memoryState.kind = tab.dataset.kind;
    for (const item of document.querySelectorAll('.memory-tab')) {
      item.classList.toggle('active', item === tab);
    }
    loadMemories();
  };
}

document.getElementById('memory-refresh').onclick = () => {
  if (!memoryState.loading) loadMemories();
};

loadMemories();
