"""Web UI locale minimale: HTTP, SSE e conferme ASK."""

from __future__ import annotations

import json
import queue
import secrets
import threading

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import urlparse

from core.confirmations import QueueConfirmationProvider
from core.events import ServiceEvent
from core.service import HarnessService
from memory.projects import ProjectError


class EventBus:
    """Fan-out thread-safe degli eventi verso le connessioni SSE."""

    def __init__(self) -> None:

        self._subscribers: set[queue.Queue] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:

        channel: queue.Queue = queue.Queue(maxsize=500)

        with self._lock:
            self._subscribers.add(channel)

        return channel

    def unsubscribe(
        self,
        channel: queue.Queue,
    ) -> None:

        with self._lock:
            self._subscribers.discard(channel)

    def publish(
        self,
        event: ServiceEvent,
    ) -> None:

        with self._lock:
            channels = list(self._subscribers)

        for channel in channels:

            try:
                channel.put_nowait(event)

            except queue.Full:

                # Un client lento non deve bloccare il turno.
                try:
                    channel.get_nowait()
                except queue.Empty:
                    pass

                try:
                    channel.put_nowait(event)
                except queue.Full:
                    pass


class WebSession:
    """Stato di una singola sessione servita dal browser."""

    def __init__(
        self,
        harness: Any,
        confirmation: QueueConfirmationProvider,
    ) -> None:

        self.harness = harness
        self.confirmation = confirmation
        self.bus = EventBus()
        self.token = secrets.token_urlsafe(24)

        self.confirmation.event_sink = self.bus.publish

        self.service = HarnessService(
            harness,
            event_sink=self.bus.publish,
        )

        self._lock = threading.Lock()
        self._busy = False
        self._closed = False

    # ==================================================
    # Turni
    # ==================================================

    def send(
        self,
        text: str,
    ) -> bool:
        """Avvia un turno; False se uno è già in corso."""

        with self._lock:

            if self._busy or self._closed:
                return False

            self._busy = True

        thread = threading.Thread(
            target=self._run_turn,
            args=(text,),
            name="hagar-web-turn",
            daemon=True,
        )
        thread.start()

        return True

    def _run_turn(
        self,
        text: str,
    ) -> None:

        try:

            self.service.ask(text)

        except Exception:
            # HarnessService emette già turn.error prima di rilanciare.
            pass

        finally:

            with self._lock:
                self._busy = False

    # ==================================================
    # Stato
    # ==================================================

    def status(self) -> dict[str, Any]:

        data = self.service.status()

        with self._lock:
            data["busy"] = self._busy
            data["closed"] = self._closed

        data["confirmations"] = (
            self.confirmation.pending_requests()
        )

        return data

    def resolve(
        self,
        request_id: str,
        approved: bool,
    ) -> bool:

        return self.confirmation.resolve(
            request_id,
            approved,
        )

    def close(self) -> None:

        with self._lock:

            if self._closed:
                return

            self._closed = True

        self.confirmation.cancel_all()
        self.service.finish_session(interactive=False)


class HagarHTTPServer(ThreadingHTTPServer):
    """Server HTTP locale; ogni connessione SSE ha il proprio thread."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        session: WebSession,
    ) -> None:

        super().__init__(address, HagarRequestHandler)
        self.session = session


HTML = r"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hagar</title>
<style>
:root {
  color-scheme: dark;
  --bg: #101318;
  --panel: #171b22;
  --line: #2a303a;
  --text: #e6e9ef;
  --muted: #9aa4b2;
  --accent: #7aa2ff;
  --danger: #ff7a7a;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font: 15px/1.5 system-ui, sans-serif;
  color: var(--text);
  background: var(--bg);
  height: 100vh;
  display: grid;
  grid-template-columns: 280px 1fr;
}
aside {
  border-right: 1px solid var(--line);
  background: var(--panel);
  padding: 18px;
  overflow: auto;
}
main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
header {
  padding: 14px 18px;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}
#messages {
  flex: 1;
  overflow: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.message {
  max-width: 85%;
  padding: 10px 13px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.user { align-self: flex-end; border-color: #34446b; }
.assistant { align-self: flex-start; }
.tool {
  align-self: stretch;
  font-size: 13px;
  color: var(--muted);
  border-left: 3px solid var(--accent);
  padding: 8px 10px;
  background: #11151b;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.error { border-color: var(--danger); color: var(--danger); }
form {
  display: flex;
  gap: 10px;
  padding: 14px 18px;
  border-top: 1px solid var(--line);
}
textarea {
  flex: 1;
  min-height: 52px;
  max-height: 180px;
  resize: vertical;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: #0d1015;
  color: var(--text);
  font: inherit;
}
button {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #202632;
  color: var(--text);
  padding: 8px 12px;
  cursor: pointer;
  font: inherit;
}
button.primary { background: #2c4a86; border-color: #3c5fa5; }
button:disabled { opacity: .5; cursor: default; }
h1 { font-size: 17px; margin: 0; }
h2 { font-size: 12px; text-transform: uppercase; color: var(--muted); margin: 20px 0 8px; }
dl { display: grid; grid-template-columns: auto 1fr; gap: 4px 8px; font-size: 13px; }
dt { color: var(--muted); }
dd { margin: 0; overflow-wrap: anywhere; }
#tools { font-size: 12px; color: var(--muted); max-height: 220px; overflow: auto; }
#modal {
  position: fixed; inset: 0; display: none; place-items: center;
  background: rgb(0 0 0 / .65); padding: 20px;
}
#modal.open { display: grid; }
#modal .box {
  width: min(640px, 100%); background: var(--panel);
  border: 1px solid var(--line); border-radius: 12px; padding: 18px;
}
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 240px; overflow: auto; }
.row { display: flex; gap: 8px; flex-wrap: wrap; }
.muted { color: var(--muted); font-size: 13px; }
@media (max-width: 760px) {
  body { grid-template-columns: 1fr; }
  aside { display: none; }
}
</style>
</head>
<body>
<aside>
  <h1>Hagar</h1>
  <div class="muted" id="model">...</div>
  <h2>Sessione</h2>
  <dl>
    <dt>Progetto</dt><dd id="project">...</dd>
    <dt>Memoria</dt><dd id="memory">...</dd>
    <dt>Audit</dt><dd id="audit">...</dd>
  </dl>
  <h2>Progetti</h2>
  <div class="row">
    <button id="project-refresh">Aggiorna</button>
    <button id="project-free">Libera</button>
    <button id="project-new">Nuovo</button>
  </div>
  <div id="projects" class="muted"></div>
  <h2>Tool</h2>
  <div id="tools"></div>
</aside>
<main>
  <header>
    <strong>Chat</strong>
    <span class="muted" id="state">pronta</span>
  </header>
  <div id="messages"></div>
  <form id="composer">
    <textarea id="input" placeholder="Scrivi un messaggio..." autofocus></textarea>
    <button class="primary" id="send" type="submit">Invia</button>
  </form>
</main>
<div id="modal" role="dialog" aria-modal="true">
  <div class="box">
    <h3 id="confirm-title">Conferma richiesta</h3>
    <p class="muted" id="confirm-reason"></p>
    <dl>
      <dt>Tool</dt><dd id="confirm-tool"></dd>
      <dt>Capability</dt><dd id="confirm-capabilities"></dd>
    </dl>
    <pre id="confirm-arguments"></pre>
    <div class="row" style="justify-content:flex-end">
      <button id="confirm-deny">Rifiuta</button>
      <button class="primary" id="confirm-allow">Consenti</button>
    </div>
  </div>
</div>
<script>
const TOKEN = __HAGAR_TOKEN__;
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
</script>
</body>
</html>
"""


class HagarRequestHandler(BaseHTTPRequestHandler):
    """Router minimale per la GUI locale."""

    server_version = "HagarWeb/0.1"

    @property
    def session(self) -> WebSession:

        return self.server.session

    def log_message(
        self,
        format: str,
        *args: Any,
    ) -> None:

        # Il server è locale; non sporcare stdout.
        return

    # ==================================================
    # Utility
    # ==================================================

    def _token(self) -> str | None:

        header = self.headers.get("X-Hagar-Token")

        if header:
            return header

        query = parse_qs(
            urlparse(self.path).query
        ).get("token")

        return query[0] if query else None

    def _authorized(self) -> bool:

        return secrets.compare_digest(
            self._token() or "",
            self.session.token,
        )

    def _json(
        self,
        payload: dict[str, Any],
        status: int = HTTPStatus.OK,
    ) -> None:

        body = json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header(
            "Content-Length",
            str(len(body)),
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(
        self,
        message: str,
        status: int = HTTPStatus.BAD_REQUEST,
    ) -> None:

        self._json(
            {"error": message},
            status=status,
        )

    def _read_json(self) -> dict[str, Any] | None:

        try:
            length = int(
                self.headers.get("Content-Length", "0")
            )
        except ValueError:
            return None

        if length < 0 or length > 1_000_000:
            return None

        raw = self.rfile.read(length)

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

        return data if isinstance(data, dict) else None

    # ==================================================
    # GET
    # ==================================================

    def do_GET(self) -> None:

        parsed = urlparse(self.path)

        if parsed.path == "/":

            body = HTML.replace(
                "__HAGAR_TOKEN__",
                json.dumps(self.session.token),
            ).encode("utf-8")

            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8",
            )
            self.send_header(
                "Content-Length",
                str(len(body)),
            )
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/favicon.ico":

            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return

        if not self._authorized():

            self._error(
                "unauthorized",
                HTTPStatus.UNAUTHORIZED,
            )
            return

        if parsed.path == "/api/events":

            self._stream_events()
            return

        if parsed.path == "/api/status":

            self._json(self.session.status())
            return

        if parsed.path == "/api/projects":

            self._json(
                {
                    "projects": self.session.service.list_projects(),
                    "current": self.session.service.project_id,
                }
            )
            return

        if parsed.path == "/api/pending":

            self._json(
                {
                    "confirmations": (
                        self.session.confirmation.pending_requests()
                    )
                }
            )
            return

        self._error("not found", HTTPStatus.NOT_FOUND)

    # ==================================================
    # POST
    # ==================================================

    def do_POST(self) -> None:

        if not self._authorized():

            self._error(
                "unauthorized",
                HTTPStatus.UNAUTHORIZED,
            )
            return

        parsed = urlparse(self.path)
        payload = self._read_json()

        if payload is None:

            self._error("invalid JSON body")
            return

        if parsed.path == "/api/message":

            text = str(payload.get("text", "")).strip()

            if not text:

                self._error("text is required")
                return

            if not self.session.send(text):

                self._error(
                    "a turn is already running",
                    HTTPStatus.CONFLICT,
                )
                return

            self._json(
                {"accepted": True},
                status=HTTPStatus.ACCEPTED,
            )
            return

        if parsed.path == "/api/confirm":

            request_id = str(payload.get("id", ""))
            approved = bool(payload.get("approved", False))

            if not request_id:

                self._error("id is required")
                return

            if not self.session.resolve(
                request_id,
                approved,
            ):

                self._error(
                    "confirmation not found",
                    HTTPStatus.NOT_FOUND,
                )
                return

            self._json({"resolved": True})
            return

        if parsed.path == "/api/project":

            action = str(payload.get("action", ""))

            try:

                if action == "select":

                    self.session.service.set_project(
                        str(payload.get("id", ""))
                    )

                elif action == "new":

                    self.session.service.create_project(
                        str(payload.get("name", ""))
                    )

                elif action == "free":

                    self.session.service.clear_project()

                else:

                    self._error("unknown project action")
                    return

            except (ProjectError, ValueError) as exc:

                self._error(str(exc))
                return

            self._json(
                {
                    "project": (
                        self.session.service.current_project()
                    )
                }
            )
            return

        self._error("not found", HTTPStatus.NOT_FOUND)

    # ==================================================
    # SSE
    # ==================================================

    def _stream_events(self) -> None:

        channel = self.session.bus.subscribe()

        self.close_connection = True

        try:

            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Content-Type",
                "text/event-stream; charset=utf-8",
            )
            self.send_header(
                "Cache-Control",
                "no-cache, no-store",
            )
            self.send_header(
                "Connection",
                "keep-alive",
            )
            self.end_headers()

            initial = json.dumps(
                {
                    "type": "status",
                    "data": self.session.status(),
                    "ts": "",
                },
                ensure_ascii=False,
            )
            self.wfile.write(
                f"data: {initial}\n\n".encode("utf-8")
            )
            self.wfile.flush()

            while True:

                try:
                    event = channel.get(timeout=15)

                except queue.Empty:

                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue

                payload = json.dumps(
                    {
                        "type": event.type,
                        "data": event.data,
                        "ts": event.ts,
                    },
                    ensure_ascii=False,
                )
                self.wfile.write(
                    f"data: {payload}\n\n".encode("utf-8")
                )
                self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError):
            pass

        finally:

            self.session.bus.unsubscribe(channel)


def serve(
    harness: Any,
    confirmation: QueueConfirmationProvider,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """Avvia il server e blocca fino a Ctrl-C."""

    session = WebSession(
        harness=harness,
        confirmation=confirmation,
    )

    server = HagarHTTPServer(
        (host, port),
        session,
    )

    print(
        f"Hagar web: http://{host}:{server.server_address[1]}/"
    )
    print("Ctrl-C per terminare.")

    try:

        server.serve_forever()

    except KeyboardInterrupt:

        pass

    finally:

        server.shutdown()
        server.server_close()
        session.close()
