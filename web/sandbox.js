let selectedEntry = null;
let treeBusy = false;

function selectEntry(entry, row) {
  selectedEntry = entry;

  for (const previous of document.querySelectorAll(
    '.tree-row.selected'
  )) {
    previous.classList.remove('selected');
  }

  if (row) row.classList.add('selected');

  const status = document.getElementById('path-status');
  status.replaceChildren();
  status.appendChild(document.createTextNode('Path reale: '));
  const value = document.createElement('strong');
  value.textContent = entry.real_path || '(non disponibile)';
  status.appendChild(value);

  const newButton = document.getElementById('new-dir');
  newButton.disabled = entry.kind !== 'directory';
}

function permissionInput(
  entry,
  axis,
  row,
) {
  const label = document.createElement('label');
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.dataset.axis = axis;
  input.checked = Boolean(entry.permissions[axis]);
  input.title = axis.toUpperCase();

  input.onclick = (event) => event.stopPropagation();

  input.onchange = async () => {
    if (treeBusy) {
      input.checked = !input.checked;
      return;
    }
    treeBusy = true;

    const next = {
      read: Boolean(entry.permissions.read),
      write: Boolean(entry.permissions.write),
      execute: Boolean(entry.permissions.execute),
    };
    next[axis] = input.checked;

    try {
      const data = await adminApi(
        '/api/admin/sandbox/permissions',
        {
          method: 'POST',
          body: JSON.stringify({
            path: entry.path,
            ...next,
          }),
        }
      );
      entry.permissions = data.permissions;
      for (const box of row.querySelectorAll(
        'input[data-axis]'
      )) {
        box.checked = Boolean(
          entry.permissions[box.dataset.axis]
        );
      }
      setAdminStatus('Permessi aggiornati: ' + entry.path);
    } catch (error) {
      input.checked = !input.checked;
      setAdminStatus(String(error), true);
    } finally {
      treeBusy = false;
    }
  };

  label.appendChild(input);
  label.appendChild(document.createTextNode(axis[0].toUpperCase()));
  return label;
}

function renderEntry(entry, parent) {
  const node = el('div', 'tree-node');
  const row = el('div', 'tree-row');

  const toggle = el('button', 'tree-toggle', '▸');
  const children = el('div', 'tree-children');
  children.hidden = true;

  if (entry.kind !== 'directory') {
    toggle.classList.add('spacer');
    toggle.disabled = true;
  }

  const name = el(
    'span',
    'tree-name ' + (entry.kind === 'directory' ? 'dir' : 'file'),
    entry.name
  );

  const rwx = el('span', 'rwx');
  rwx.appendChild(permissionInput(entry, 'read', row));
  rwx.appendChild(permissionInput(entry, 'write', row));
  rwx.appendChild(permissionInput(entry, 'execute', row));

  const size = el(
    'span',
    'tree-size',
    entry.kind === 'file'
      ? formatBytes(entry.size_bytes)
      : ''
  );

  toggle.onclick = async (event) => {
    event.stopPropagation();

    if (entry.kind !== 'directory') return;

    if (!children.dataset.loaded) {
      try {
        const data = await adminApi(
          '/api/admin/sandbox?path=' +
            encodeURIComponent(entry.path)
        );
        for (const child of data.entries) {
          renderEntry(child, children);
        }
        children.dataset.loaded = '1';
        if (data.message) setAdminStatus(data.message);
      } catch (error) {
        setAdminStatus(String(error), true);
        return;
      }
    }

    children.hidden = !children.hidden;
    toggle.textContent = children.hidden ? '▸' : '▾';
  };

  row.onclick = () => selectEntry(entry, row);
  row.appendChild(toggle);
  row.appendChild(name);
  row.appendChild(size);
  row.appendChild(rwx);

  node.appendChild(row);
  node.appendChild(children);
  parent.appendChild(node);
}

async function loadTree() {
  const tree = document.getElementById('tree');
  selectedEntry = null;
  document.getElementById('new-dir').disabled = true;
  setAdminStatus('Caricamento sandbox...');

  try {
    const data = await adminApi(
      '/api/admin/sandbox?path=%2Fhome%2Fai'
    );
    tree.replaceChildren();
    for (const entry of data.entries) {
      renderEntry(entry, tree);
    }
    if (!data.entries.length) {
      tree.appendChild(el('div', 'empty', 'sandbox vuota'));
    }
    setAdminStatus(data.message || 'Pronto.');
  } catch (error) {
    setAdminStatus(String(error), true);
  }
}

document.getElementById('new-dir').onclick = async () => {
  if (treeBusy || !selectedEntry) return;

  if (selectedEntry.kind !== 'directory') {
    setAdminStatus('Seleziona una directory.', true);
    return;
  }

  const input = document.getElementById('new-dir-name');
  const name = input.value.trim();

  if (!name) {
    setAdminStatus('Inserisci il nome della directory.', true);
    return;
  }

  treeBusy = true;

  try {
    await adminApi('/api/admin/sandbox/mkdir', {
      method: 'POST',
      body: JSON.stringify({
        path: selectedEntry.path,
        name,
      }),
    });
    input.value = '';
    setAdminStatus('Directory creata: ' + name);
    selectedEntry = null;
    await loadTree();
  } catch (error) {
    setAdminStatus(String(error), true);
  } finally {
    treeBusy = false;
  }
};

loadTree();
