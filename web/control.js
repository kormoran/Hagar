let control = null;
let selectedModel = null;
let busy = false;

function renderTools() {
  const box = document.getElementById('tools');
  box.replaceChildren();

  for (const tool of control.tools) {
    const row = el(
      'div',
      'tool-row' + (tool.enabled ? '' : ' denied')
    );
    const name = el('div', 'tool-name', tool.name);
    const meta = el(
      'div',
      'tool-meta',
      [
        tool.category,
        tool.origin,
        ...(tool.capabilities || []),
      ].filter(Boolean).join(' · ')
    );
    const state = el(
      'span',
      'tool-state ' + (tool.enabled ? 'allowed' : 'denied'),
      tool.enabled ? 'allow' : 'deny'
    );

    row.title = tool.description || '';
    row.append(name, meta, state);
    row.onclick = async () => {
      if (busy) return;
      busy = true;
      try {
        const data = await adminApi('/api/admin/tool', {
          method: 'POST',
          body: JSON.stringify({
            name: tool.name,
            enabled: !tool.enabled,
          }),
        });
        Object.assign(tool, data.tool);
        renderTools();
        setAdminStatus(
          (tool.enabled ? 'Tool abilitato: ' : 'Tool negato: ') +
            tool.name
        );
      } catch (error) {
        setAdminStatus(String(error), true);
      } finally {
        busy = false;
      }
    };
    box.appendChild(row);
  }
}

function renderModels() {
  const current = control.model.current;
  document.getElementById('current-model').textContent =
    'Modello attivo: ' + current.provider + ' / ' + current.name;

  const box = document.getElementById('providers');
  box.replaceChildren();

  const filter = document.getElementById('provider-filter');
  const previous = filter.value;
  filter.replaceChildren(new Option('Tutti', ''));
  for (const provider of control.model.providers) {
    filter.appendChild(new Option(provider.name, provider.name));
  }
  filter.value = previous;

  const visible = filter.value
    ? control.model.providers.filter(
        (provider) => provider.name === filter.value
      )
    : control.model.providers;

  for (const provider of visible) {
    const block = el('div', 'provider-block');
    block.appendChild(el('div', 'provider-name', provider.name));

    const list = el('div', 'model-list');

    if (!provider.models.length) {
      list.appendChild(el('span', 'muted', 'nessun modello rilevato'));
    }

    for (const model of provider.models) {
      const button = el('button', 'model-button', model);
      if (
        selectedModel &&
        selectedModel.provider === provider.name &&
        selectedModel.model === model
      ) {
        button.classList.add('selected');
      }
      if (
        current.provider === provider.name &&
        current.name === model
      ) {
        button.classList.add('current');
      }
      button.onclick = () => {
        selectedModel = {
          provider: provider.name,
          model,
        };
        renderModels();
      };
      list.appendChild(button);
    }

    block.appendChild(list);
    box.appendChild(block);
  }

  const change = document.getElementById('change-model');
  change.disabled = !selectedModel ||
    (
      selectedModel.provider === current.provider &&
      selectedModel.model === current.name
    );
}

function renderSettings() {
  const box = document.getElementById('settings');
  box.replaceChildren();

  for (const group of control.settings.groups) {
    const groupBox = el('div', 'settings-group');
    groupBox.appendChild(el('h3', '', group.name));

    for (const field of group.fields) {
      if (field.type === 'bool') {
        const label = el('label', 'check');
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.dataset.key = field.key;
        input.checked = Boolean(field.value);
        label.appendChild(input);
        label.appendChild(el('span', '', field.label));
        groupBox.appendChild(label);
        continue;
      }

      const label = el('label', 'field');
      label.appendChild(el('span', '', field.label));
      const input = document.createElement('input');
      input.type = 'number';
      input.dataset.key = field.key;
      input.value = field.value;
      if (field.min !== undefined && field.min !== null) {
        input.min = field.min;
      }
      if (field.max !== undefined && field.max !== null) {
        input.max = field.max;
      }
      if (field.step !== undefined && field.step !== null) {
        input.step = field.step;
      }
      label.appendChild(input);
      groupBox.appendChild(label);
    }

    box.appendChild(groupBox);
  }
}

function collectSettings() {
  const values = {};

  for (const input of document.querySelectorAll(
    '#settings [data-key]'
  )) {
    values[input.dataset.key] = input.type === 'checkbox'
      ? input.checked
      : Number(input.value);
  }

  return values;
}

function render() {
  renderTools();
  renderModels();
  renderSettings();
}

async function loadControl(force) {
  setAdminStatus('Caricamento...');
  try {
    control = await adminApi(
      '/api/admin/control' + (force ? '?refresh=1' : '')
    );
    render();
    setAdminStatus('Pronto.');
  } catch (error) {
    setAdminStatus(String(error), true);
  }
}

document.getElementById('change-model').onclick = async () => {
  if (!selectedModel || busy) return;
  const label = selectedModel.provider + ' / ' + selectedModel.model;
  if (!confirm('Cambiare modello in ' + label + '?')) return;

  busy = true;
  setAdminStatus('Cambio modello in corso...');
  try {
    const data = await adminApi('/api/admin/model', {
      method: 'POST',
      body: JSON.stringify(selectedModel),
    });
    control.model = data.model;
    selectedModel = null;
    renderModels();
    setAdminStatus('Modello cambiato: ' + label);
  } catch (error) {
    setAdminStatus(String(error), true);
  } finally {
    busy = false;
  }
};

document.getElementById('provider-filter').onchange = () => {
  renderModels();
};

document.getElementById('refresh-models').onclick = () => {
  if (busy) return;
  loadControl(true);
};

document.getElementById('apply-settings').onclick = async () => {
  if (busy) return;
  busy = true;
  setAdminStatus('Applicazione...');
  try {
    const data = await adminApi('/api/admin/settings', {
      method: 'POST',
      body: JSON.stringify({ values: collectSettings() }),
    });
    control.settings = data.settings;
    control.model = data.model;
    renderSettings();
    renderModels();
    setAdminStatus('Configurazione applicata.');
  } catch (error) {
    setAdminStatus(String(error), true);
  } finally {
    busy = false;
  }
};

document.getElementById('reset-settings').onclick = async () => {
  if (busy) return;
  if (!confirm('Ricaricare i valori da hagar.yaml?')) return;
  busy = true;
  setAdminStatus('Ricarica da hagar.yaml...');
  try {
    control = await adminApi('/api/admin/settings', {
      method: 'POST',
      body: JSON.stringify({ reset: true }),
    });
    selectedModel = null;
    render();
    setAdminStatus('Valori ricaricati da hagar.yaml.');
  } catch (error) {
    setAdminStatus(String(error), true);
  } finally {
    busy = false;
  }
};

loadControl();
