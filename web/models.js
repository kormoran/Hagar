const token = window.HAGAR_TOKEN;

const els = {
  list: document.getElementById('model-list'),
  status: document.getElementById('models-status'),
  errors: document.getElementById('models-errors'),
  filter: document.getElementById('model-filter'),
  refresh: document.getElementById('refresh-models'),
  empty: document.getElementById('detail-empty'),
  detail: document.getElementById('model-detail'),
  provider: document.getElementById('detail-provider'),
  name: document.getElementById('detail-name'),
  badges: document.getElementById('detail-badges'),
  facts: document.getElementById('model-facts'),
  capabilities: document.getElementById('model-capabilities'),
  capabilitiesEmpty: document.getElementById('capabilities-empty'),
  benchmarkButton: document.getElementById('run-benchmark'),
  benchmarkStatus: document.getElementById('benchmark-status'),
  benchmarkEmpty: document.getElementById('benchmark-empty'),
  benchmarkContent: document.getElementById('benchmark-content'),
  benchmarkTimestamp: document.getElementById('benchmark-timestamp'),
};

const state = {
  models: [],
  selected: null,
  loading: false,
  job: null,
  polling: null,
};

function api(path, options = {}) {
  return fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Hagar-Token': token,
      ...(options.headers || {}),
    },
  }).then(async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    return data;
  });
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function fmt(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'n/d';
  }
  return Number(value).toFixed(digits);
}

function pct(value) {
  if (value === null || value === undefined) return 'n/d';
  const number = Number(value);
  return `${(number * 100).toFixed(number >= 0.995 ? 0 : 1)}%`;
}

function ms(value) {
  if (value === null || value === undefined) return 'n/d';
  const number = Number(value);
  if (number >= 1000) return `${(number / 1000).toFixed(1)} s`;
  return `${Math.round(number)} ms`;
}

function setStatus(text, kind = '') {
  els.status.textContent = text || '';
  els.status.className = `models-status ${kind}`.trim();
}

function setBenchmarkStatus(text, kind = '') {
  if (!text) {
    els.benchmarkStatus.hidden = true;
    els.benchmarkStatus.textContent = '';
    return;
  }
  els.benchmarkStatus.hidden = false;
  els.benchmarkStatus.textContent = text;
  els.benchmarkStatus.className = `benchmark-status ${kind}`.trim();
}

function groupModels(models) {
  const groups = new Map();
  for (const model of models) {
    if (!groups.has(model.provider)) groups.set(model.provider, []);
    groups.get(model.provider).push(model);
  }
  return groups;
}

function modelMatches(model, query) {
  if (!query) return true;
  const haystack = [
    model.model,
    model.provider,
    model.type,
    ...(model.capabilities || []),
    ...(model.hagar_capabilities || []),
  ].join(' ').toLowerCase();
  return haystack.includes(query);
}

function renderList() {
  const query = els.filter.value.trim().toLowerCase();
  const models = state.models.filter((model) => modelMatches(model, query));
  els.list.replaceChildren();

  if (!models.length) {
    setStatus(query ? 'Nessun modello corrisponde al filtro.' : 'Nessun modello locale trovato.');
    return;
  }

  setStatus(`${models.length} modelli`);

  for (const [provider, items] of groupModels(models)) {
    const group = node('div', 'model-group');
    group.appendChild(node('p', 'model-group-title', provider));

    for (const model of items) {
      const button = node('button', 'model-row');
      button.type = 'button';
      button.dataset.id = model.id;
      if (state.selected?.id === model.id) button.classList.add('selected');

      const name = node('span', 'model-row-name', model.model);
      const meta = node(
        'span',
        'model-row-meta',
        [
          model.type || 'unknown',
          model.context_window ? `${model.context_window} ctx` : null,
          model.quantization,
        ].filter(Boolean).join(' · ') || 'metadati non disponibili',
      );
      const badges = node('span', 'model-row-state');
      if (model.loaded) {
        badges.textContent = 'caricato';
        badges.classList.add('loaded');
      } else if (model.has_benchmark) {
        badges.textContent = 'scheda';
        badges.classList.add('benchmarked');
      } else {
        badges.textContent = model.state || 'n/d';
      }

      button.append(name, meta, badges);
      button.addEventListener('click', () => selectModel(model.id));
      group.appendChild(button);
    }

    els.list.appendChild(group);
  }
}

function fact(label, value) {
  const item = node('div', 'fact');
  item.appendChild(node('div', 'fact-label', label));
  item.appendChild(node('div', 'fact-value', value || 'n/d'));
  return item;
}

function metric(label, value) {
  const row = node('div', 'metric');
  row.appendChild(node('span', '', label));
  row.appendChild(node('strong', '', value));
  return row;
}

function benchmarkBlock(title) {
  const block = node('div', 'benchmark-block');
  block.appendChild(node('h4', '', title));
  return block;
}

function addMetric(block, label, value) {
  block.appendChild(metric(label, value));
}

function renderQuality(container, card) {
  const tasks = card?.quality?.tasks || {};
  const names = [
    ['summary', 'Summary'],
    ['translation', 'Translation'],
    ['extraction', 'Extraction'],
    ['instruction', 'Instruction'],
    ['reasoning', 'Reasoning'],
    ['coding', 'Coding'],
    ['coding_exec', 'Coding eseguibile'],
    ['memory', 'Memoria'],
  ];

  const rows = names
    .map(([key, label]) => {
      const value = tasks[key];
      return value ? [label, value] : null;
    })
    .filter(Boolean);

  if (!rows.length) return;

  const block = benchmarkBlock('Qualità per task');
  const table = node('table', 'quality-table');
  const head = node('tr');
  head.append(node('th', '', 'Task'), node('th', '', 'Mean'));
  table.appendChild(head);

  for (const [label, value] of rows) {
    const row = node('tr');
    row.append(
      node('td', '', label),
      node('td', '', fmt(value.mean, 4)),
    );
    table.appendChild(row);
  }

  block.appendChild(table);
  container.appendChild(block);
}

function renderMemory(container, card) {
  const memory = card?.memory?.tasks?.memory || card?.quality?.tasks?.memory;
  if (!memory) return;

  const block = benchmarkBlock('Memoria');
  addMetric(block, 'Overall', fmt(memory.mean, 4));
  addMetric(block, 'Casi', memory.cases ?? 'n/d');

  const cases = memory.case_results || [];
  for (const item of cases.slice(0, 6)) {
    addMetric(block, item.name, fmt(item.mean, 3));
  }

  container.appendChild(block);
}

function renderProduction(container, card) {
  const production = card?.production;
  if (!production) return;

  const block = benchmarkBlock('Prompt production');
  addMetric(block, 'p50', ms(production.p50_ms));
  addMetric(block, 'p95', ms(production.p95_ms));
  addMetric(block, 'Tool', production.tools ?? 'n/d');
  addMetric(block, 'Prompt', `${production.prompt_chars ?? 0} caratteri`);
  container.appendChild(block);
}

function renderBenchmarks(card) {
  els.benchmarkContent.replaceChildren();
  els.benchmarkTimestamp.textContent = card?.last_tested_at || '';
  const benchmarks = card?.benchmarks;

  if (!benchmarks && !card?.quality) {
    els.benchmarkEmpty.hidden = false;
    return;
  }

  els.benchmarkEmpty.hidden = true;
  const grid = node('div', 'benchmark-grid');

  if (benchmarks?.chat) {
    const chat = benchmarks.chat;
    const block = benchmarkBlock('Chat');
    addMetric(block, 'Successi', `${chat.successes ?? 0}/${chat.attempts ?? 0}`);
    addMetric(block, 'p50', ms(chat.duration_ms?.p50));
    addMetric(block, 'p95', ms(chat.duration_ms?.p95));
    addMetric(block, 'Token/s', fmt(chat.output_tokens_per_second, 2));
    if (chat.not_applicable) addMetric(block, 'Stato', 'non applicabile');
    grid.appendChild(block);
  }

  if (benchmarks?.structured) {
    const item = benchmarks.structured;
    const block = benchmarkBlock('JSON');
    addMetric(block, 'JSON valido', `${item.valid_json ?? 0}/${item.attempts ?? 0}`);
    addMetric(block, 'Schema valido', `${item.schema_valid ?? 0}/${item.attempts ?? 0}`);
    addMetric(block, 'Field F1', fmt(item.field_f1, 4));
    addMetric(block, 'Choice', `${item.valid_choice ?? 0}/${item.attempts ?? 0}`);
    grid.appendChild(block);
  }

  if (benchmarks?.tool_call) {
    const item = benchmarks.tool_call;
    const block = benchmarkBlock('Tool calling');
    addMetric(block, 'Tool corretto', `${item.successes ?? 0}/${item.attempts ?? 0}`);
    addMetric(block, 'Argomenti', pct(item.argument_accuracy));
    addMetric(block, 'Selection', pct(item.selection_accuracy));
    grid.appendChild(block);
  }

  if (card?.quality?.tasks) {
    const block = benchmarkBlock('Qualità');
    addMetric(block, 'Overall', fmt(card.quality.overall, 4));
    addMetric(block, 'Casi', card.quality.cases?.length ?? 'n/d');
    grid.appendChild(block);
  }

  if (benchmarks?.vision || card?.vision) {
    const vision = benchmarks?.vision || card.vision;
    const block = benchmarkBlock('Vision');
    addMetric(block, 'Overall', fmt(vision.overall, 4));
    addMetric(block, 'Casi', vision.tasks?.vision?.cases ?? 'n/d');
    if (vision.not_applicable) addMetric(block, 'Stato', 'non applicabile');
    grid.appendChild(block);
  }

  if (card?.coding?.overall !== undefined) {
    const block = benchmarkBlock('Coding');
    addMetric(block, 'Unit test', fmt(card.coding.overall, 4));
    addMetric(block, 'Casi', card.coding.tasks?.coding_exec?.cases ?? 'n/d');
    grid.appendChild(block);
  }

  renderQuality(grid, card);
  renderMemory(grid, card);
  renderProduction(grid, card);
  els.benchmarkContent.appendChild(grid);
}

function renderDetail(model) {
  if (!model) {
    els.empty.hidden = false;
    els.detail.hidden = true;
    return;
  }

  els.empty.hidden = true;
  els.detail.hidden = false;
  els.provider.textContent = model.provider;
  els.name.textContent = model.model;
  els.badges.replaceChildren();

  const badges = [
    model.type || 'unknown',
    model.loaded ? 'caricato' : model.state || 'stato n/d',
    model.has_benchmark ? 'benchmark disponibile' : 'senza benchmark',
  ];
  for (const label of badges) {
    const badge = node('span', 'badge', label);
    if (label === 'caricato') badge.classList.add('loaded');
    if (label === 'benchmark disponibile') badge.classList.add('benchmarked');
    els.badges.appendChild(badge);
  }

  els.facts.replaceChildren(
    fact('Provider', model.provider),
    fact('Tipo', model.type),
    fact('Stato', model.state),
    fact('Contesto', model.context_window ? `${model.context_window} token` : 'n/d'),
    fact('Quantizzazione', model.quantization),
    fact('Ultimo test', model.last_tested_at),
  );

  els.capabilities.replaceChildren();
  const capabilities = model.hagar_capabilities?.length
    ? model.hagar_capabilities
    : model.capabilities || [];
  for (const capability of capabilities) {
    els.capabilities.appendChild(node('span', 'chip', capability));
  }
  els.capabilitiesEmpty.hidden = capabilities.length > 0;

  renderBenchmarks(model.card);
  els.benchmarkButton.disabled = Boolean(state.job);

  if (state.job) {
    setBenchmarkStatus(
      state.job.status === 'running'
        ? `Benchmark in corso per ${state.job.model}…`
        : state.job.status === 'failed'
          ? `Benchmark fallito: ${state.job.error || 'errore sconosciuto'}`
          : 'Benchmark completato.',
      state.job.status === 'failed' ? 'error' : 'running',
    );
  } else {
    setBenchmarkStatus('');
  }
}

function selectModel(id) {
  const model = state.models.find((item) => item.id === id) || null;
  state.selected = model;
  renderList();
  renderDetail(model);
}

async function loadModels(options = {}) {
  if (state.loading) return;
  state.loading = true;
  els.refresh.disabled = true;
  setStatus('Lettura del runtime locale…');

  try {
    const data = await api('/api/models');
    state.models = data.models || [];
    els.errors.hidden = !(data.errors || []).length;
    els.errors.textContent = (data.errors || [])
      .map((item) => `${item.provider}: ${item.error}`)
      .join('\n');

    if (state.selected) {
      const next = state.models.find((item) => item.id === state.selected.id);
      state.selected = next || null;
    }

    if (!state.selected && state.models.length) {
      state.selected = state.models[0];
    }

    renderList();
    renderDetail(state.selected);
  } catch (error) {
    setStatus('Errore durante la lettura dei modelli.');
    els.errors.hidden = false;
    els.errors.textContent = String(error.message || error);
  } finally {
    state.loading = false;
    els.refresh.disabled = false;
  }
}

function stopPolling() {
  if (state.polling) {
    clearInterval(state.polling);
    state.polling = null;
  }
}

function pollJob(jobId) {
  stopPolling();
  state.polling = setInterval(async () => {
    try {
      const job = await api(`/api/models/benchmark?id=${encodeURIComponent(jobId)}`);
      state.job = job;

      if (job.status === 'running') {
        setBenchmarkStatus(`Benchmark in corso per ${job.model}…`, 'running');
        return;
      }

      stopPolling();
      state.job = job;

      if (job.status === 'completed') {
        setBenchmarkStatus('Benchmark completato. Aggiorno la scheda…', '');
        state.job = null;
        await loadModels();
      } else {
        setBenchmarkStatus(`Benchmark fallito: ${job.error || 'errore sconosciuto'}`, 'error');
        state.job = null;
        els.benchmarkButton.disabled = false;
      }
    } catch (error) {
      stopPolling();
      state.job = null;
      setBenchmarkStatus(`Errore nel polling: ${error.message || error}`, 'error');
      els.benchmarkButton.disabled = false;
    }
  }, 1500);
}

async function startBenchmark() {
  if (!state.selected || state.job) return;

  els.benchmarkButton.disabled = true;
  setBenchmarkStatus(`Avvio benchmark per ${state.selected.model}…`, 'running');

  try {
    const job = await api('/api/models/benchmark', {
      method: 'POST',
      body: JSON.stringify({
        provider: state.selected.provider,
        model: state.selected.model,
      }),
    });
    state.job = job;
    pollJob(job.id);
  } catch (error) {
    state.job = null;
    els.benchmarkButton.disabled = false;
    setBenchmarkStatus(`Avvio fallito: ${error.message || error}`, 'error');
  }
}

els.refresh.addEventListener('click', () => loadModels());
els.filter.addEventListener('input', () => renderList());
els.benchmarkButton.addEventListener('click', startBenchmark);

loadModels();
