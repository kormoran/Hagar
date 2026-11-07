"""Test della GUI web locale (senza browser reale)."""

from __future__ import annotations

import http.client
import json
import threading
import time

from types import SimpleNamespace

from core.confirmations import QueueConfirmationProvider
from core.web import HagarHTTPServer
from core.web import WebSession
from core.web import serve


class FakeAgent:
    def __init__(self):
        self.answer = "risposta web"
        self.project_id = None
        self.cancelled = False
        self.questions = []

    def ask(self, question, images=None):
        self.questions.append((question, images))
        return self.answer

    def cancel(self):
        self.cancelled = True


class FakeAudit:
    enabled = True
    path = "audit.jsonl"
    session_id = "web-session"

    def record(self, event, **fields):
        pass


class FakeRegistry:
    def tool_names(self):
        return ["demo.echo"]

    def list_definitions(self):
        return []


def make_harness():
    config = SimpleNamespace(
        model=SimpleNamespace(
            provider="lmstudio",
            name="local-model",
        ),
        policy=SimpleNamespace(
            path="policy.yaml",
            subject="assistant",
        ),
        vault=SimpleNamespace(path="vault"),
        memory=SimpleNamespace(
            vault_subdir="Hagar",
            summary_max_chars=4000,
        ),
        mcp_servers=[],
    )

    return SimpleNamespace(
        config=config,
        audit=FakeAudit(),
        registry=FakeRegistry(),
        memory=None,
        memory_error=None,
        policy_error=None,
        project_store=None,
        project_id=None,
        project_state={"id": None},
        agent=FakeAgent(),
    )


class RunningServer:
    def __init__(self):
        self.provider = QueueConfirmationProvider(timeout=5)
        self.session = WebSession(
            make_harness(),
            self.provider,
        )
        self.server = HagarHTTPServer(
            ("127.0.0.1", 0),
            self.session,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.port = self.server.server_address[1]

    def request(
        self,
        method,
        path,
        body=None,
        token=True,
    ):
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.port,
            timeout=3,
        )
        headers = {}

        if token:
            headers["X-Hagar-Token"] = self.session.token

        payload = None

        if body is not None:
            payload = json.dumps(body)
            headers["Content-Type"] = "application/json"

        connection.request(
            method,
            path,
            body=payload,
            headers=headers,
        )
        response = connection.getresponse()
        data = response.read()
        connection.close()

        return response.status, data

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.session.close()
        self.thread.join(timeout=2)


def test_index_contains_token_and_ui():
    server = RunningServer()

    try:
        status, body = server.request("GET", "/", token=False)
        text = body.decode("utf-8")

        assert status == 200
        assert server.session.token in text
        assert "Comandi chat" not in text
        assert "Hagar" in text
        assert "/static/app.js" in text

    finally:
        server.close()


def test_static_assets_are_served_without_token():
    server = RunningServer()

    try:
        status, body = server.request(
            "GET",
            "/static/style.css",
            token=False,
        )
        assert status == 200
        assert b"--bg" in body

        status, body = server.request(
            "GET",
            "/static/app.js",
            token=False,
        )
        assert status == 200
        assert b"__HAGAR_TOKEN__" not in body

        status, _ = server.request(
            "GET",
            "/static/missing.js",
            token=False,
        )
        assert status == 404

    finally:
        server.close()


def test_api_requires_token():
    server = RunningServer()

    try:
        status, _ = server.request(
            "GET",
            "/api/status",
            token=False,
        )

        assert status == 401

    finally:
        server.close()


def test_status_and_message_roundtrip():
    server = RunningServer()

    try:
        status, body = server.request(
            "GET",
            "/api/status",
        )
        assert status == 200
        data = json.loads(body)
        assert data["session_id"] == "web-session"
        assert data["busy"] is False

        status, body = server.request(
            "POST",
            "/api/message",
            {"text": "ciao"},
        )
        assert status == 202

        deadline = time.time() + 3

        while time.time() < deadline:
            _, body = server.request("GET", "/api/status")
            if not json.loads(body)["busy"]:
                break
            time.sleep(0.02)

        assert json.loads(body)["busy"] is False

    finally:
        server.close()


def test_stop_requests_agent_cancellation():
    server = RunningServer()

    try:
        server.session._busy = True
        assert server.session.stop() is True
        assert server.session.harness.agent.cancelled is True

    finally:
        server.close()


def test_message_accepts_image_data_url():
    server = RunningServer()

    try:
        image = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0l"
            "EQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        status, _ = server.request(
            "POST",
            "/api/message",
            {
                "text": "cosa vedi?",
                "images": [image],
            },
        )

        assert status == 202

        deadline = time.time() + 3

        while time.time() < deadline:
            if server.session.harness.agent.questions:
                break
            time.sleep(0.02)

        _, images = server.session.harness.agent.questions[0]

        assert len(images) == 1
        assert images[0].mime_type == "image/png"

    finally:
        server.close()


def test_confirmation_resolve_via_http():
    server = RunningServer()

    try:
        # Crea una richiesta pendente in un thread, come farebbe un tool.
        result = []

        def worker():
            from core.permissions import Capability
            from core.permissions import ConfirmationRequest

            result.append(
                server.provider.confirm(
                    ConfirmationRequest(
                        subject="assistant",
                        tool="filesystem.write_file",
                        capabilities=Capability.FILESYSTEM_WRITE,
                        arguments={"path": "x"},
                        reason="test",
                    )
                )
            )

        thread = threading.Thread(target=worker)
        thread.start()

        deadline = time.time() + 2
        pending = []

        while time.time() < deadline:
            pending = server.provider.pending_requests()
            if pending:
                break
            time.sleep(0.01)

        assert pending

        status, _ = server.request(
            "POST",
            "/api/confirm",
            {
                "id": pending[0]["id"],
                "approved": True,
            },
        )

        assert status == 200
        thread.join(timeout=2)
        assert result == [True]

    finally:
        server.close()


def test_connection_abort_does_not_print_traceback(capsys):
    server = RunningServer()

    try:
        try:
            raise ConnectionAbortedError(
                "client disconnected"
            )
        except ConnectionAbortedError:
            server.server.handle_error(None, None)

        assert capsys.readouterr().err == ""

    finally:
        server.close()


def test_serve_exits_on_keyboard_interrupt(monkeypatch):
    def interrupt(self):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        HagarHTTPServer,
        "serve_forever",
        interrupt,
    )

    provider = QueueConfirmationProvider(timeout=1)

    # Non deve bloccare su shutdown() o sul summary della sessione.
    serve(
        make_harness(),
        provider,
        host="127.0.0.1",
        port=0,
    )
