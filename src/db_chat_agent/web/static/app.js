const state = {
  sessionId: null,
  schema: null,
  history: [],
};

const el = (id) => document.getElementById(id);

const chatFeed = el('chatFeed');
const schemaList = el('schemaList');
const resultJson = el('resultJson');
const sessionIdEl = el('sessionId');
const connectionStatus = el('connectionStatus');
const tableCount = el('tableCount');
const rowsStat = el('rowsStat');
const latencyStat = el('latencyStat');
const statusStat = el('statusStat');
const resultCount = el('resultCount');

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function setStatus(text, tone = 'neutral') {
  connectionStatus.textContent = text;
  connectionStatus.style.color = tone === 'error' ? '#fb7185' : tone === 'success' ? '#22c55e' : '';
}

function renderSchema(schema) {
  const tables = schema?.tables || {};
  const entries = Object.entries(tables);
  tableCount.textContent = `${entries.length} tables`;

  if (!entries.length) {
    schemaList.innerHTML = '<div class="empty-state">No tables available.</div>';
    return;
  }

  schemaList.innerHTML = entries.map(([name, meta]) => {
    const cols = (meta.columns || []).map((c) => `<span class="pill">${escapeHtml(c.name)} · ${escapeHtml(c.type)}</span>`).join('');
    const pk = (meta.primary_key || []).join(', ') || 'None';
    const fks = (meta.foreign_keys || []).length
      ? (meta.foreign_keys || []).map((fk) => `${fk.constrained_columns?.join(', ')} → ${fk.referred_table}(${fk.referred_columns?.join(', ')})`).join('<br/>')
      : 'None';

    return `
      <div class="schema-table">
        <h3>${escapeHtml(name)}</h3>
        <div class="columns">${cols || '<span class="empty-state">No columns</span>'}</div>
        <p class="muted"><strong>PK:</strong> ${escapeHtml(pk)}</p>
        <p class="muted"><strong>FK:</strong> ${fks}</p>
      </div>
    `;
  }).join('');
}

function addMessage(kind, payload) {
  const node = document.createElement('article');
  node.className = `message ${kind}`;
  if (kind === 'user') {
    node.innerHTML = `<span class="label">You</span><div>${escapeHtml(payload)}</div>`;
  } else {
    const sqlBlock = payload.sql ? `<pre class="sql-block">${escapeHtml(payload.sql)}</pre>` : '';
    const explanationBlock = payload.explanation ? `<div class="muted">${escapeHtml(payload.explanation)}</div>` : '';
    node.innerHTML = `
      <span class="label">Gemma DB Assistant</span>
      <div>${escapeHtml(payload.answer || 'No response')}</div>
      ${explanationBlock}
      ${sqlBlock}
    `;
  }
  chatFeed.appendChild(node);
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

async function connectDb() {
  const dbUri = el('dbUri').value.trim();
  if (!dbUri) {
    setStatus('Please enter a database URI.', 'error');
    return;
  }

  setStatus('Connecting to database…');
  statusStat.textContent = 'Connecting';
  const start = performance.now();

  try {
    const res = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ db_uri: dbUri }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to connect');

    state.sessionId = data.session_id;
    sessionIdEl.textContent = data.session_id;
    const schemaRes = await fetch(`/api/sessions/${data.session_id}/schema`);
    const schema = await schemaRes.json();
    if (!schemaRes.ok) throw new Error(schema.detail || 'Failed to load schema');

    state.schema = schema;
    renderSchema(schema);
    setStatus('Connected successfully.', 'success');
    statusStat.textContent = 'Connected';
    latencyStat.textContent = `${Math.round(performance.now() - start)} ms`;
    addMessage('assistant', {
      answer: `Connected to ${dbUri}. Schema loaded successfully.`,
      explanation: 'The backend created a dedicated session and inspected the database schema.',
    });
  } catch (err) {
    setStatus(err.message, 'error');
    statusStat.textContent = 'Error';
  }
}

async function sendQuestion(question) {
  if (!state.sessionId) {
    setStatus('Connect a database first.', 'error');
    return;
  }
  const text = question.trim();
  if (!text) return;

  const showSql = el('showSqlToggle').checked;
  addMessage('user', text);
  el('questionInput').value = '';
  statusStat.textContent = 'Running';
  setStatus('Generating SQL and executing query…');

  const start = performance.now();
  try {
    const res = await fetch(`/api/sessions/${state.sessionId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Query failed');

    state.history.push(data);
    resultJson.textContent = JSON.stringify(data.result, null, 2);
    rowsStat.textContent = `${data.result?.row_count ?? 0}`;
    resultCount.textContent = `${data.result?.row_count ?? 0} rows`;
    latencyStat.textContent = `${Math.round(performance.now() - start)} ms`;
    statusStat.textContent = 'Ready';
    setStatus('Query executed successfully.', 'success');

    addMessage('assistant', {
      answer: data.answer,
      explanation: data.explanation,
      sql: showSql ? data.sql : '',
    });
  } catch (err) {
    statusStat.textContent = 'Error';
    setStatus(err.message, 'error');
    addMessage('assistant', {
      answer: `Error: ${err.message}`,
      explanation: 'The backend rejected or failed to execute the request.',
      sql: '',
    });
  }
}

async function refreshSchema() {
  if (!state.sessionId) return;
  const res = await fetch(`/api/sessions/${state.sessionId}/analyze`, { method: 'POST' });
  const data = await res.json();
  if (!res.ok) {
    setStatus(data.detail || 'Failed to refresh schema', 'error');
    return;
  }
  state.schema = data;
  renderSchema(data);
  setStatus('Schema refreshed.', 'success');
}

function wireEvents() {
  el('connectBtn').addEventListener('click', connectDb);
  el('sendBtn').addEventListener('click', () => sendQuestion(el('questionInput').value));
  el('refreshSchemaBtn').addEventListener('click', refreshSchema);
  el('clearChatBtn').addEventListener('click', () => { chatFeed.innerHTML = ''; resultJson.textContent = 'No query executed yet.'; });
  el('questionInput').addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') sendQuestion(el('questionInput').value);
  });

  document.querySelectorAll('[data-prompt]').forEach((btn) => {
    btn.addEventListener('click', () => {
      el('questionInput').value = btn.getAttribute('data-prompt');
      el('questionInput').focus();
    });
  });
}

wireEvents();
addMessage('assistant', {
  answer: 'Connect to a database to begin.',
  explanation: 'Use the left panel to supply a SQLAlchemy database URI.',
  sql: '',
});
