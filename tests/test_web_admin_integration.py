"""Test d'integrazione delle API amministrative con harness reale."""

from __future__ import annotations

import http.client
import json
import threading

from pathlib import Path

import yaml

import core.admin as admin_module

from core.config import ConfigLoader
from core.confirmations import QueueConfirmationProvider
from core.web import HagarHTTPServer, WebSession
from hagar import build_harness


def write_config(tmp_path: Path) -> Path:

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    vault = tmp_path / "vault"
    vault.mkdir()

    policy = tmp_path / "policy.yaml"
    policy.write_text(
        "version: 1\n"
        "subjects:\n"
        "  assistant:\n"
        "    default: allow\n",
        encoding="utf-8",
    )

    data = {
        "model": {
            "provider": "ollama",
            "host": "http://localhost:11434",
            "name": "qwen3:8b",
        },
        "audit": {"enabled": False},
        "policy": {
            "path": str(policy),
            "subject": "assistant",
        },
        "vault": {"path": str(vault)},
        "memory": {"enabled": False},
        "filesystem": {
            "sandbox": [
                {
                    "alias": "workspace",
                    "path": str(workspace),
                    "permissions": "RWX",
                }
            ],
        },
        "permissions": {
            "read": True,
            "write": True,
            "shell": False,
        },
        "hifi": {
            "enabled": False,
            "margin": 0.2,
            "interpretations": 3,
        },
        "tools": {
            "timeout": 120,
            "repeat_limit": 3,
        },
    }

    path = tmp_path / "hagar.yaml"
    path.write_text(
        yaml.safe_dump(data),
        encoding="utf-8",
    )

    return path


def test_admin_http_integration(
    tmp_path,
    monkeypatch,
):

    monkeypatch.setattr(
        admin_module,
        "model_catalog",
        lambda config, force=False: {
            "current": {
                "provider": config.model.provider,
                "name": config.model.name,
            },
            "providers": [],
        },
    )

    config = ConfigLoader.load(
        write_config(tmp_path)
    )
    harness = build_harness(config)

    provider = QueueConfirmationProvider(timeout=5)
    session = WebSession(harness, provider)
    server = HagarHTTPServer(
        ("127.0.0.1", 0),
        session,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    port = server.server_address[1]

    def request(method, path, body=None):

        connection = http.client.HTTPConnection(
            "127.0.0.1",
            port,
            timeout=5,
        )
        headers = {
            "X-Hagar-Token": session.token,
            "Content-Type": "application/json",
        }
        payload = (
            json.dumps(body)
            if body is not None
            else None
        )

        connection.request(
            method,
            path,
            body=payload,
            headers=headers,
        )
        response = connection.getresponse()
        data = response.read()
        connection.close()

        return response.status, json.loads(
            data.decode("utf-8")
        )

    try:

        status, payload = request(
            "GET",
            "/api/admin/control",
        )

        assert status == 200
        assert any(
            item["name"] == "calculator.evaluate"
            for item in payload["tools"]
        )

        status, payload = request(
            "POST",
            "/api/admin/tool",
            {
                "name": "calculator.evaluate",
                "enabled": False,
            },
        )

        assert status == 200
        assert payload["tool"]["enabled"] is False

        _, current = request(
            "GET",
            "/api/admin/control",
        )
        settings = {
            field["key"]: field["value"]
            for group in current["settings"]["groups"]
            for field in group["fields"]
        }
        settings["hifi.enabled"] = True
        settings["tools.timeout"] = 5

        status, payload = request(
            "POST",
            "/api/admin/settings",
            {"values": settings},
        )

        assert status == 200
        assert harness.config.hifi.enabled is True
        assert harness.registry.default_timeout == 5

        status, payload = request(
            "GET",
            "/api/admin/sandbox?path=%2Fhome%2Fai%2Fworkspace",
        )

        assert status == 200
        assert payload["real_path"] == str(
            (tmp_path / "workspace").resolve()
        )

        status, payload = request(
            "POST",
            "/api/admin/sandbox/mkdir",
            {
                "path": "/home/ai/workspace",
                "name": "created",
            },
        )

        assert status == 200
        assert (
            tmp_path / "workspace" / "created"
        ).is_dir()

        status, payload = request(
            "POST",
            "/api/admin/sandbox/permissions",
            {
                "path": "/home/ai/workspace",
                "read": True,
                "write": False,
                "execute": True,
            },
        )

        assert status == 200
        assert payload["permissions"]["write"] is False

        status, payload = request(
            "POST",
            "/api/admin/settings",
            {"reset": True},
        )

        assert status == 200
        assert harness.config.hifi.enabled is False
        assert harness.registry.default_timeout == 120
        assert harness.registry.get(
            "calculator.evaluate"
        ).enabled is True
        assert harness.filesystem.effective_permissions(
            tmp_path / "workspace"
        ).write is True

    finally:

        server.shutdown()
        server.server_close()
        session.close(summarize=False)
        thread.join(timeout=2)
