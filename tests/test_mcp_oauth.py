"""Test del flusso OAuth MCP (senza browser né server reali)."""

from __future__ import annotations

import base64
import hashlib
import json

from urllib.parse import parse_qs, urlparse

import pytest
import requests

import llm.mcp_oauth as oauth

from core.models import MCPOAuthConfig
from llm.mcp_oauth import (
    OAuthError,
    OAuthProvider,
    TokenCache,
    discover_authorization_server,
    discover_protected_resource,
    pkce_pair,
)


class FakeResponse:
    def __init__(
        self,
        payload,
        status_code=200,
        text="",
    ):
        self.payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self.payload


def test_pkce_uses_s256():
    verifier, challenge = pkce_pair()

    expected = (
        base64.urlsafe_b64encode(
            hashlib.sha256(
                verifier.encode("ascii")
            ).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )

    assert len(verifier) >= 43
    assert challenge == expected
    assert "=" not in challenge


def test_token_cache_roundtrip(tmp_path):
    cache = TokenCache(tmp_path / "tokens.json")

    assert cache.load() is None

    cache.save({"tokens": {"access_token": "x"}})

    assert cache.load() == {
        "tokens": {"access_token": "x"}
    }


def test_token_cache_ignores_invalid_json(tmp_path):
    path = tmp_path / "tokens.json"
    path.write_text("not-json", encoding="utf-8")

    assert TokenCache(path).load() is None


def test_discovery_uses_protected_resource(monkeypatch):
    def fake_get_json(url, timeout):
        if "oauth-protected-resource" in url:
            return {
                "authorization_servers": [
                    "https://auth.test"
                ]
            }

        if "oauth-authorization-server" in url:
            return {
                "authorization_endpoint": (
                    "https://auth.test/authorize"
                ),
                "token_endpoint": (
                    "https://auth.test/token"
                ),
            }

        raise AssertionError(url)

    monkeypatch.setattr(
        oauth,
        "_get_json",
        fake_get_json,
    )

    assert discover_protected_resource(
        "https://mcp.test/mcp"
    ) == "https://auth.test"

    metadata = discover_authorization_server(
        "https://auth.test"
    )

    assert metadata["token_endpoint"] == (
        "https://auth.test/token"
    )


def test_interactive_flow_and_cache(
    tmp_path,
    monkeypatch,
):
    metadata = {
        "authorization_endpoint": (
            "https://auth.test/authorize"
        ),
        "token_endpoint": "https://auth.test/token",
    }

    monkeypatch.setattr(
        oauth,
        "discover_authorization_server",
        lambda issuer, timeout=30: metadata,
    )

    seen: dict = {}

    def fake_post(
        url,
        data=None,
        json=None,
        headers=None,
        auth=None,
        timeout=None,
    ):
        seen["url"] = url
        seen["data"] = data
        return FakeResponse(
            {
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)

    def fake_browser(url):
        query = parse_qs(urlparse(url).query)
        seen["browser_query"] = query

        redirect = query["redirect_uri"][0]
        state = query["state"][0]

        response = requests.get(
            f"{redirect}?code=code-1&state={state}",
            timeout=5,
        )

        assert response.status_code == 200

        return True

    config = MCPOAuthConfig(
        authorization_server="https://auth.test",
        client_id="client-1",
        audience="api.atlassian.com",
        scopes=["read:me", "offline_access"],
        redirect_port=0,
        token_cache=tmp_path / "tokens.json",
        timeout=5,
    )

    provider = OAuthProvider(
        config,
        "https://mcp.test/mcp",
        "test",
        browser=fake_browser,
    )

    assert provider.token() == "access-1"

    assert seen["url"] == "https://auth.test/token"
    assert seen["data"]["grant_type"] == (
        "authorization_code"
    )
    assert seen["data"]["code"] == "code-1"
    assert seen["data"]["code_verifier"]
    assert seen["data"]["audience"] == "api.atlassian.com"
    assert seen["browser_query"]["audience"] == [
        "api.atlassian.com"
    ]
    assert seen["browser_query"]["prompt"] == ["consent"]
    assert seen["browser_query"]["scope"] == [
        "read:me offline_access"
    ]

    cache = json.loads(
        (tmp_path / "tokens.json").read_text(
            encoding="utf-8"
        )
    )

    assert cache["tokens"]["access_token"] == "access-1"
    assert cache["tokens"]["refresh_token"] == (
        "refresh-1"
    )

    calls: list[str] = []

    cached = OAuthProvider(
        config,
        "https://mcp.test/mcp",
        "test",
        browser=lambda url: calls.append(url),
    )

    assert cached.token() == "access-1"
    assert calls == []


def test_refresh_uses_refresh_token(
    tmp_path,
    monkeypatch,
):
    cache = TokenCache(tmp_path / "tokens.json")

    cache.save(
        {
            "resource": "https://mcp.test/mcp",
            "authorization_server": (
                "https://auth.test"
            ),
            "token_endpoint": "https://auth.test/token",
            "client": {
                "client_id": "client-1",
                "client_secret": None,
                "secret_env": None,
                "auth_method": "none",
                "redirect_uri": (
                    "http://127.0.0.1:1/callback"
                ),
            },
            "tokens": {
                "access_token": "old",
                "refresh_token": "refresh-1",
                "token_type": "Bearer",
                "scope": None,
                "expires_at": 1.0,
            },
        }
    )

    seen: dict = {}

    def fake_post(
        url,
        data=None,
        json=None,
        headers=None,
        auth=None,
        timeout=None,
    ):
        seen["data"] = data
        return FakeResponse(
            {
                "access_token": "new",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)

    provider = OAuthProvider(
        MCPOAuthConfig(
            token_cache=cache.path,
        ),
        "https://mcp.test/mcp",
        "test",
        browser=lambda url: pytest.fail(
            "il browser non deve aprirsi"
        ),
    )

    assert provider.token() == "new"
    assert seen["data"]["grant_type"] == (
        "refresh_token"
    )
    assert seen["data"]["refresh_token"] == (
        "refresh-1"
    )


def test_missing_refresh_token_requires_login(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        oauth,
        "discover_authorization_server",
        lambda issuer, timeout=30: {
            "authorization_endpoint": (
                "https://auth.test/authorize"
            ),
            "token_endpoint": (
                "https://auth.test/token"
            ),
        },
    )

    cache = TokenCache(tmp_path / "tokens.json")

    cache.save(
        {
            "resource": "https://mcp.test/mcp",
            "client": {
                "client_id": "client-1",
                "auth_method": "none",
            },
            "tokens": {
                "access_token": "old",
                "token_type": "Bearer",
                "expires_at": 1.0,
            },
        }
    )

    provider = OAuthProvider(
        MCPOAuthConfig(
            authorization_server="https://auth.test",
            client_id="client-1",
            token_cache=cache.path,
            timeout=1,
        ),
        "https://mcp.test/mcp",
        "test",
        browser=lambda url: False,
        input_func=lambda prompt: "",
    )

    with pytest.raises(OAuthError):
        provider.token()
