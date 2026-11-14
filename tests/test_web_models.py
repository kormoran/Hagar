"""Test della pagina web dei modelli locali."""

from __future__ import annotations

import http.client
import json
import threading

from types import SimpleNamespace

from core.confirmations import QueueConfirmationProvider
from core.web import HagarHTTPServer, WebSession


class FakeAgent:
    def __init__(self):
        self.tools = SimpleNamespace(list_definitions=lambda: [])

    def ask(self, question, images=None):
        return "ok"


class FakeHarness:
    def __init__(self):
        self.config = SimpleNamespace(
            model=SimpleNamespace(
                provider="lmstudio",
                name="local",
                host="http://localhost:1234/v1",
            ),
        )
        self.agent = FakeAgent()
        self.audit = SimpleNamespace(
            enabled=False,
            record=lambda *args, **kwargs: None,
        )


class Server:
    def __init__(self, monkeypatch):
        self.session = WebSession(
            FakeHarness(),
            QueueConfirmationProvider(timeout=2),
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

    def request(self, method, path, body=None, token=True):
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
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, data

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.session.close()
        self.thread.join(timeout=2)


def test_models_page_and_list(monkeypatch):
    import core.web as web

    server = Server(monkeypatch)

    try:
        status, body = server.request("GET", "/models", token=False)
        assert status == 200
        assert b"models.js" in body
        assert b"Modelli locali" in body

        monkeypatch.setattr(
            web,
            "list_local_models",
            lambda config: {
                "models": [
                    {
                        "id": "lmstudio/local",
                        "provider": "lmstudio",
                        "model": "local",
                        "type": "llm",
                        "state": "loaded",
                        "loaded": True,
                        "context_window": 4096,
                        "quantization": "Q4",
                        "capabilities": ["text_generation"],
                        "hagar_capabilities": ["chat"],
                        "has_benchmark": False,
                        "card": None,
                    }
                ],
                "errors": [],
            },
        )

        status, body = server.request("GET", "/api/models")
        data = json.loads(body)
        assert status == 200
        assert data["models"][0]["model"] == "local"

        status, _ = server.request("GET", "/api/models", token=False)
        assert status == 401
    finally:
        server.close()


def test_models_benchmark_job_api(monkeypatch):
    server = Server(monkeypatch)
    job = {
        "id": "job-1",
        "provider": "lmstudio",
        "model": "local",
        "status": "running",
        "error": None,
        "result": None,
    }

    monkeypatch.setattr(
        server.session,
        "start_model_benchmark",
        lambda provider, model: job,
    )
    monkeypatch.setattr(
        server.session,
        "model_benchmark",
        lambda job_id: job if job_id == "job-1" else None,
    )

    try:
        status, body = server.request(
            "POST",
            "/api/models/benchmark",
            {"provider": "lmstudio", "model": "local"},
        )
        assert status == 200
        assert json.loads(body)["id"] == "job-1"

        status, body = server.request(
            "GET",
            "/api/models/benchmark?id=job-1",
        )
        assert status == 200
        assert json.loads(body)["status"] == "running"
    finally:
        server.close()
