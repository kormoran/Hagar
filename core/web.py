"""Web UI locale minimale: HTTP, SSE e conferme ASK."""

from __future__ import annotations

import json
import queue
import secrets
import sys
import threading
import time

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import unquote
from urllib.parse import urlparse

from core.admin import AdminError
from core.admin import AdminService
from core.audit import read_entries
from core.config import ConfigError
from core.confirmations import QueueConfirmationProvider
from core.events import ServiceEvent
from core.events import make_event
from core.images import MAX_IMAGES
from core.images import ImageInput
from core.images import ImageInputError
from core.model_browser import (
    list_local_models,
    run_model_benchmark,
)
from core.service import HarnessService
from core.session_log import SessionLog
from memory.projects import ProjectError


STATIC_TYPES = {
    "style.css": "text/css; charset=utf-8",
    "admin.css": "text/css; charset=utf-8",
    "models.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
    "admin.js": "application/javascript; charset=utf-8",
    "models.js": "application/javascript; charset=utf-8",
    "control.js": "application/javascript; charset=utf-8",
    "sandbox.js": "application/javascript; charset=utf-8",
}

# Quattro immagini da 10 MB in base64 occupano circa 53 MB.
MAX_BODY_BYTES = 64 * 1024 * 1024


def _read_web_asset(name: str) -> bytes:
    """Legge un asset dal package o dal sorgente in editable mode."""

    try:
        return files("web").joinpath(name).read_bytes()

    except (ModuleNotFoundError, FileNotFoundError):
        source = (
            Path(__file__).resolve().parent.parent
            / "web"
            / name
        )
        return source.read_bytes()


def render_page(
    name: str,
    token: str,
) -> bytes:

    html = _read_web_asset(name).decode("utf-8")

    return html.replace(
        "__HAGAR_TOKEN__",
        json.dumps(token),
    ).encode("utf-8")


def render_index(token: str) -> bytes:

    return render_page("index.html", token)


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
        self.log = SessionLog()

        self.confirmation.event_sink = self._publish

        self.service = HarnessService(
            harness,
            event_sink=self._publish,
        )

        self.admin = AdminService(
            harness,
            usage_sink=self.service.usage.record,
        )

        self._lock = threading.Lock()
        self._busy = False
        self._closed = False
        self._bench_lock = threading.Lock()
        self._bench_jobs: dict[str, dict[str, Any]] = {}
        self._bench_active: str | None = None

    def _publish(
        self,
        event: ServiceEvent,
    ) -> None:

        self.log.record(event)
        self.bus.publish(event)

    # ==================================================
    # Modelli locali
    # ==================================================

    def models(self) -> dict[str, Any]:

        return list_local_models(self.harness.config)

    def start_model_benchmark(
        self,
        provider: str,
        model: str,
    ) -> dict[str, Any]:

        if self.is_busy():
            raise RuntimeError("a turn is running")

        with self._bench_lock:

            if self._bench_active is not None:
                raise RuntimeError("a benchmark is already running")

            job_id = secrets.token_urlsafe(12)
            job = {
                "id": job_id,
                "provider": provider,
                "model": model,
                "status": "running",
                "error": None,
                "result": None,
                "started_at": time.time(),
                "finished_at": None,
            }
            self._bench_jobs[job_id] = job
            self._bench_active = job_id

        thread = threading.Thread(
            target=self._run_model_benchmark,
            args=(job_id, provider, model),
            name="hagar-model-benchmark",
            daemon=True,
        )
        thread.start()

        return dict(job)

    def _run_model_benchmark(
        self,
        job_id: str,
        provider: str,
        model: str,
    ) -> None:

        try:
            agent = getattr(self.harness, "agent", None)
            registry = getattr(agent, "tools", None)
            result = run_model_benchmark(
                self.harness.config,
                provider,
                model,
                registry=registry,
            )
        except Exception as exc:
            with self._bench_lock:
                job = self._bench_jobs[job_id]
                job["status"] = "failed"
                job["error"] = str(exc)
                job["finished_at"] = time.time()
                self._bench_active = None
            return

        with self._bench_lock:
            job = self._bench_jobs[job_id]
            job["status"] = "completed"
            job["result"] = result
            job["finished_at"] = time.time()
            self._bench_active = None

    def model_benchmark(self, job_id: str) -> dict[str, Any] | None:

        with self._bench_lock:
            job = self._bench_jobs.get(job_id)

            if job is None:
                return None

            result = dict(job)

            return result

    # ==================================================
    # Turni
    # ==================================================

    def send(
        self,
        text: str,
        images: list[ImageInput] | None = None,
    ) -> bool:
        """Avvia un turno; False se uno è già in corso."""

        with self._lock:

            if self._busy or self._closed:
                return False

            self._busy = True

        thread = threading.Thread(
            target=self._run_turn,
            args=(text, images),
            name="hagar-web-turn",
            daemon=True,
        )
        thread.start()

        return True

    def is_busy(self) -> bool:

        with self._lock:
            return self._busy

    def stop(self) -> bool:
        """Richiede l'interruzione del turno corrente."""

        with self._lock:

            if not self._busy:
                return False

        agent = getattr(self.harness, "agent", None)

        if agent is None or not hasattr(agent, "cancel"):
            return False

        agent.cancel()
        self.bus.publish(
            make_event("turn.stop_requested")
        )

        return True

    def _run_turn(
        self,
        text: str,
        images: list[ImageInput] | None = None,
    ) -> None:

        try:

            self.service.ask(text, images=images)

        except Exception:
            # HarnessService emette già turn.error prima di rilanciare.
            pass

        finally:

            with self._lock:
                self._busy = False

    # ==================================================
    # Stato
    # ==================================================

    def new_chat(self) -> str:
        """Crea una nuova sessione; il contesto precedente non entra."""

        with self._lock:

            if self._busy:
                raise RuntimeError(
                    "a turn is already running"
                )

        session_id = self.service.new_chat()
        self.log.clear()

        return session_id

    def history(self) -> list[dict[str, Any]]:

        return self.service.history()

    def load_chat(self, session_id: str) -> list[dict[str, Any]]:

        return self.service.load_chat(session_id)

    def resume_chat(self, session_id: str) -> list[dict[str, Any]]:

        with self._lock:

            if self._busy:
                raise RuntimeError(
                    "a turn is already running"
                )

        self.log.clear()
        return self.service.resume_chat(session_id)

    def memories(
        self,
        query: str = "",
        limit: int = 200,
    ) -> dict[str, Any]:

        return self.service.memories(query, limit)

    def read_memory(
        self,
        path: str,
    ) -> dict[str, Any] | None:

        return self.service.read_memory(path)

    def status(self) -> dict[str, Any]:

        data = self.service.status()

        with self._lock:
            data["busy"] = self._busy
            data["closed"] = self._closed

        data["confirmations"] = (
            self.confirmation.pending_requests()
        )
        data["usage"] = self.service.usage.snapshot()

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

    def close(
        self,
        summarize: bool = True,
    ) -> None:

        with self._lock:

            if self._closed:
                return

            self._closed = True

        self.confirmation.cancel_all()

        # In una GUI il summary può attendere il modello per minuti:
        # durante Ctrl-C non deve bloccare la chiusura del processo.
        if summarize:
            self.service.finish_session(interactive=False)


class HagarHTTPServer(ThreadingHTTPServer):
    """Server HTTP locale; ogni connessione SSE ha il proprio thread."""

    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        session: WebSession,
    ) -> None:

        super().__init__(address, HagarRequestHandler)
        self.session = session

    def handle_error(
        self,
        request: Any,
        client_address: Any,
    ) -> None:
        """Non stampare traceback per disconnessioni del browser."""

        exc = sys.exc_info()[1]

        if isinstance(exc, (ConnectionError, OSError)):
            return

        super().handle_error(request, client_address)


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

        if length < 0 or length > MAX_BODY_BYTES:
            return None

        raw = self.rfile.read(length)

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

        return data if isinstance(data, dict) else None

    def _admin_ready(self) -> bool:
        """Rifiuta mutazioni amministrative durante un turno."""

        if self.session.is_busy():

            self._error(
                "a turn is running",
                HTTPStatus.CONFLICT,
            )
            return False

        return True

    # ==================================================
    # GET
    # ==================================================

    def do_GET(self) -> None:

        parsed = urlparse(self.path)

        if parsed.path == "/":

            body = render_index(self.session.token)

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

        page = {
            "/control": "control.html",
            "/models": "models.html",
            "/sandbox": "sandbox.html",
        }.get(parsed.path.rstrip("/"))

        if page is not None:

            body = render_page(
                page,
                self.session.token,
            )

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

        if parsed.path.startswith("/static/"):

            name = parsed.path[len("/static/"):]
            content_type = STATIC_TYPES.get(name)

            if content_type is None:

                self._error("not found", HTTPStatus.NOT_FOUND)
                return

            body = _read_web_asset(name)

            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Content-Type",
                content_type,
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

        if parsed.path == "/api/models":

            try:
                self._json(self.session.models())
            except Exception as exc:
                self._error(str(exc), HTTPStatus.BAD_GATEWAY)
            return

        if parsed.path == "/api/models/benchmark":

            params = parse_qs(parsed.query)
            job_id = params.get("id", [""])[0]

            if not job_id:
                self._error("missing benchmark id")
                return

            job = self.session.model_benchmark(job_id)

            if job is None:
                self._error("benchmark not found", HTTPStatus.NOT_FOUND)
                return

            self._json(job)
            return

        if parsed.path == "/api/admin/control":

            params = parse_qs(parsed.query)
            force = params.get(
                "refresh",
                ["0"],
            )[0] in {"1", "true", "yes"}

            try:
                self._json(
                    self.session.admin.control(
                        force=force
                    )
                )

            except AdminError as exc:
                self._error(str(exc))

            return

        if parsed.path == "/api/admin/sandbox":

            params = parse_qs(parsed.query)
            path = params.get("path", [""])[0] or None

            try:
                offset = int(params.get("offset", ["0"])[0])
            except ValueError:
                offset = 0

            try:
                limit = int(params.get("limit", ["500"])[0])
            except ValueError:
                limit = 500

            try:
                data = self.session.admin.sandbox_list(
                    path,
                    offset=offset,
                    limit=limit,
                )

            except AdminError as exc:
                self._error(str(exc))
                return

            self._json(data)
            return

        if parsed.path == "/api/projects":

            self._json(
                {
                    "projects": self.session.service.list_projects(),
                    "current": self.session.service.project_id,
                }
            )
            return

        if parsed.path == "/api/history":

            self._json(
                {"chats": self.session.history()}
            )
            return

        if parsed.path == "/api/memories":

            params = parse_qs(parsed.query)
            query = params.get("query", [""])[0]

            try:
                limit = int(params.get("limit", ["200"])[0])
            except ValueError:
                limit = 200

            try:
                data = self.session.memories(query, limit)
            except Exception as exc:
                self._error(
                    f"memory index unavailable: {exc}",
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            self._json(data)
            return

        if parsed.path == "/api/memory":

            params = parse_qs(parsed.query)
            path = params.get("path", [""])[0]

            if not path:
                self._error("path is required")
                return

            try:
                document = self.session.read_memory(path)
            except Exception as exc:
                self._error(
                    f"memory index unavailable: {exc}",
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            if document is None:
                self._error(
                    "memory not found",
                    HTTPStatus.NOT_FOUND,
                )
                return

            self._json({"memory": document})
            return

        if parsed.path == "/api/tools":

            self._json(
                {"tools": self.session.log.tools()}
            )
            return

        if parsed.path == "/api/thinking":

            self._json(
                {
                    "timeline": self.session.log.timeline(),
                    "thinking": self.session.log.thinking(),
                }
            )
            return

        if parsed.path == "/api/audit":

            audit = self.session.harness.audit

            if not audit.enabled:

                self._json(
                    {"enabled": False, "entries": []}
                )
                return

            try:
                entries = read_entries(audit.path)
            except (OSError, ValueError) as exc:
                self._error(str(exc))
                return

            self._json(
                {
                    "enabled": True,
                    "entries": entries[-200:],
                }
            )
            return

        if parsed.path.startswith("/api/history/"):

            session_id = unquote(
                parsed.path[len("/api/history/"):]
            )

            try:

                turns = self.session.load_chat(session_id)

            except Exception as exc:

                self._error(
                    str(exc),
                    HTTPStatus.BAD_REQUEST,
                )
                return

            self._json(
                {
                    "session": session_id,
                    "turns": turns,
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

            raw_images = payload.get("images") or []

            if not isinstance(raw_images, list):

                self._error("images must be a list")
                return

            if len(raw_images) > MAX_IMAGES:

                self._error(
                    f"too many images (max {MAX_IMAGES})"
                )
                return

            try:

                images = [
                    ImageInput.from_data_url(value)
                    for value in raw_images
                ]

            except ImageInputError as exc:

                self._error(str(exc))
                return

            if not text and not images:

                self._error("text or image is required")
                return

            if not text:

                text = "Descrivi questa immagine."

            if not self.session.send(text, images):

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

        if parsed.path == "/api/stop":

            if not self.session.stop():

                self._error(
                    "no turn is running",
                    HTTPStatus.CONFLICT,
                )
                return

            self._json(
                {"stopping": True},
                status=HTTPStatus.ACCEPTED,
            )
            return

        if parsed.path == "/api/new-chat":

            try:

                session_id = self.session.new_chat()

            except RuntimeError as exc:

                self._error(
                    str(exc),
                    HTTPStatus.CONFLICT,
                )
                return

            self._json({"session": session_id})
            return

        if parsed.path == "/api/resume":

            session_id = str(
                payload.get("session", "")
            ).strip()

            if not session_id:

                self._error("session is required")
                return

            try:

                turns = self.session.resume_chat(
                    session_id,
                )

            except RuntimeError as exc:

                self._error(
                    str(exc),
                    HTTPStatus.CONFLICT,
                )
                return

            self._json(
                {
                    "session": session_id,
                    "turns": turns,
                }
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

        if parsed.path == "/api/admin/tool":

            if not self._admin_ready():
                return

            try:

                tool = self.session.admin.set_tool(
                    str(payload.get("name", "")),
                    payload.get("enabled"),
                )

            except (AdminError, ValueError) as exc:

                self._error(str(exc))
                return

            self._json({"tool": tool})
            return

        if parsed.path == "/api/models/benchmark":

            if not self._admin_ready():
                return

            provider = str(
                payload.get("provider", "")
            ).strip()
            model = str(payload.get("model", "")).strip()

            if not provider or not model:
                self._error("provider and model are required")
                return

            try:
                job = self.session.start_model_benchmark(
                    provider,
                    model,
                )
            except RuntimeError as exc:
                self._error(str(exc), HTTPStatus.CONFLICT)
                return

            self._json(job)
            return

        if parsed.path == "/api/admin/model":

            if not self._admin_ready():
                return

            try:

                model = self.session.admin.change_model(
                    str(payload.get("provider", "")),
                    str(payload.get("model", "")),
                )

            except (
                AdminError,
                ConfigError,
                ValueError,
            ) as exc:

                self._error(str(exc))
                return

            self._json({"model": model})
            return

        if parsed.path == "/api/admin/settings":

            if not self._admin_ready():
                return

            try:

                if payload.get("reset") is True:

                    data = (
                        self.session.admin
                        .reset_from_config()
                    )
                    self._json(data)

                else:

                    settings = (
                        self.session.admin
                        .update_settings(
                            payload.get("values")
                        )
                    )

                    self._json(
                        {
                            "settings": settings,
                            "model": (
                                self.session.admin
                                .model_state()
                            ),
                        }
                    )

            except (
                AdminError,
                ConfigError,
                ValueError,
            ) as exc:

                self._error(str(exc))

            return

        if parsed.path == "/api/admin/sandbox/permissions":

            if not self._admin_ready():
                return

            try:

                data = (
                    self.session.admin
                    .sandbox_set_permissions(
                        str(payload.get("path", "")),
                        payload.get("read", False),
                        payload.get("write", False),
                        payload.get("execute", False),
                    )
                )

            except (AdminError, ValueError) as exc:

                self._error(str(exc))
                return

            self._json(data)
            return

        if parsed.path == "/api/admin/sandbox/mkdir":

            if not self._admin_ready():
                return

            try:

                entry = (
                    self.session.admin
                    .sandbox_mkdir(
                        str(payload.get("path", "")),
                        str(payload.get("name", "")),
                    )
                )

            except (AdminError, ValueError) as exc:

                self._error(str(exc))
                return

            self._json({"entry": entry})
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

        except (
            BrokenPipeError,
            ConnectionError,
            ConnectionAbortedError,
            OSError,
        ):
            # Il browser ha chiuso la connessione SSE: è normale.
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

        # serve_forever è già uscito: chiamare shutdown() dallo stesso
        # thread può bloccare l'uscita. server_close() chiude la socket e
        # i thread handlers sono daemon.
        server.server_close()
        session.close(summarize=False)
