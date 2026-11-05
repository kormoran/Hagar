"""OAuth 2.1 interattivo per server MCP HTTP.

Supporta il flusso authorization code + PKCE con callback su loopback,
discovery dei metadata OAuth, registrazione dinamica del client, cache
locale dei token e refresh. Non gestisce device flow, DPoP, mTLS o
client assertion.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
import webbrowser

from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from queue import Empty, Queue
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from core.models import MCPOAuthConfig

CALLBACK_PATH = "/oauth/callback"

DEFAULT_TIMEOUT = 300


class OAuthError(RuntimeError):
    """Errore del flusso OAuth."""


@dataclass(slots=True)
class OAuthClient:
    client_id: str
    client_secret: str | None = None
    secret_env: str | None = None
    auth_method: str = "none"
    redirect_uri: str | None = None


@dataclass(slots=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    scope: str | None = None
    expires_at: float | None = None

    @classmethod
    def from_response(
        cls,
        data: dict[str, Any],
    ) -> "OAuthTokens":

        access_token = data.get("access_token")

        if not isinstance(access_token, str) or not access_token:

            raise OAuthError(
                "OAuth token response has no access_token"
            )

        expires_at: float | None = None

        expires_in = data.get("expires_in")

        if isinstance(expires_in, (int, float)):

            expires_at = time.time() + float(expires_in)

        return cls(
            access_token=access_token,
            refresh_token=(
                data.get("refresh_token")
                if isinstance(
                    data.get("refresh_token"),
                    str,
                )
                else None
            ),
            token_type=(
                data.get("token_type")
                if isinstance(
                    data.get("token_type"),
                    str,
                )
                else "Bearer"
            ),
            scope=(
                data.get("scope")
                if isinstance(data.get("scope"), str)
                else None
            ),
            expires_at=expires_at,
        )


class TokenCache:
    """Cache JSON locale, con permessi ristretti quando possibile."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any] | None:

        try:

            raw = self.path.read_text(encoding="utf-8")

            data = json.loads(raw)

        except (OSError, json.JSONDecodeError):

            return None

        if not isinstance(data, dict):
            return None

        return data

    def save(self, data: dict[str, Any]) -> None:

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:

            os.chmod(self.path.parent, 0o700)

        except OSError:

            pass

        temporary = self.path.with_name(
            self.path.name + ".tmp"
        )

        temporary.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        os.replace(temporary, self.path)

        try:

            os.chmod(self.path, 0o600)

        except OSError:

            pass


def pkce_pair() -> tuple[str, str]:

    verifier = secrets.token_urlsafe(64)

    digest = hashlib.sha256(
        verifier.encode("ascii")
    ).digest()

    challenge = (
        base64.urlsafe_b64encode(digest)
        .rstrip(b"=")
        .decode("ascii")
    )

    return verifier, challenge


def default_cache_path(
    server_name: str,
) -> Path:

    safe = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        server_name,
    )

    return (
        Path.home()
        / ".hagar"
        / "oauth"
        / f"{safe}.json"
    )


def _get_json(
    url: str,
    timeout: int,
) -> dict[str, Any]:

    try:

        response = requests.get(
            url,
            headers={"Accept": "application/json"},
            timeout=timeout,
        )

    except requests.RequestException as exc:

        raise OAuthError(
            f"OAuth discovery failed for {url}"
        ) from exc

    if response.status_code != 200:

        raise OAuthError(
            f"OAuth discovery failed for {url}: "
            f"HTTP {response.status_code}"
        )

    try:

        data = response.json()

    except ValueError as exc:

        raise OAuthError(
            f"OAuth discovery returned no JSON: {url}"
        ) from exc

    if not isinstance(data, dict):

        raise OAuthError(
            f"OAuth discovery returned no object: {url}"
        )

    return data


def _resource_metadata_urls(
    resource_url: str,
) -> list[str]:

    parsed = urlparse(resource_url)

    origin = f"{parsed.scheme}://{parsed.netloc}"

    path = parsed.path.rstrip("/")

    candidates = [
        f"{origin}/.well-known/oauth-protected-resource{path}",
        f"{origin}/.well-known/oauth-protected-resource",
        f"{resource_url.rstrip('/')}/.well-known/oauth-protected-resource",
    ]

    return list(dict.fromkeys(candidates))


def _authorization_server_urls(
    issuer: str,
) -> list[str]:

    base = issuer.rstrip("/")

    parsed = urlparse(base)

    origin = f"{parsed.scheme}://{parsed.netloc}"

    path = parsed.path

    candidates = [
        f"{origin}/.well-known/oauth-authorization-server{path}",
        f"{base}/.well-known/oauth-authorization-server",
        f"{base}/.well-known/openid-configuration",
    ]

    return list(dict.fromkeys(candidates))


def discover_protected_resource(
    resource_url: str,
    timeout: int = 30,
) -> str:
    """
    Trova l'authorization server dai metadata della risorsa MCP.

    Restituisce l'URL del primo ``authorization_servers``.
    """

    errors: list[str] = []

    for url in _resource_metadata_urls(resource_url):

        try:

            data = _get_json(url, timeout)

        except OAuthError as exc:

            errors.append(str(exc))
            continue

        servers = data.get("authorization_servers")

        if (
            isinstance(servers, list)
            and servers
            and isinstance(servers[0], str)
            and servers[0].strip()
        ):

            return servers[0].strip()

        errors.append(
            f"{url}: no authorization_servers"
        )

    raise OAuthError(
        "OAuth protected resource metadata not found: "
        + "; ".join(errors[:3])
    )


def discover_authorization_server(
    issuer: str,
    timeout: int = 30,
) -> dict[str, Any]:

    errors: list[str] = []

    for url in _authorization_server_urls(issuer):

        try:

            data = _get_json(url, timeout)

        except OAuthError as exc:

            errors.append(str(exc))
            continue

        if (
            isinstance(
                data.get("authorization_endpoint"),
                str,
            )
            and isinstance(
                data.get("token_endpoint"),
                str,
            )
        ):

            return data

        errors.append(
            f"{url}: missing authorization_endpoint "
            "or token_endpoint"
        )

    raise OAuthError(
        "OAuth authorization server metadata not found: "
        + "; ".join(errors[:3])
    )


class _CallbackHandler(BaseHTTPRequestHandler):

    def do_GET(self) -> None:

        parsed = urlparse(self.path)

        if parsed.path != CALLBACK_PATH:

            self.send_error(404)
            return

        params = {
            key: values[0]
            for key, values in parse_qs(
                parsed.query
            ).items()
            if values
        }

        self.server.result.put(params)

        body = (
            "<html><body>"
            "<h1>Autenticazione completata</h1>"
            "<p>Puoi chiudere questa finestra.</p>"
            "</body></html>"
        ).encode("utf-8")

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8",
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.end_headers()

        self.wfile.write(body)

    def log_message(
        self,
        format: str,
        *args: Any,
    ) -> None:

        pass


class LoopbackServer:
    """Server HTTP temporaneo su 127.0.0.1 per il redirect OAuth."""

    def __init__(self, port: int = 0) -> None:

        self._httpd = HTTPServer(
            ("127.0.0.1", port),
            _CallbackHandler,
        )

        self._httpd.result = Queue()

        self.port = self._httpd.server_address[1]

        self.redirect_uri = (
            f"http://localhost:{self.port}"
            f"{CALLBACK_PATH}"
        )

        self._thread: threading.Thread | None = None

        self._stopped = False

    def start(self) -> None:

        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True,
        )

        self._thread.start()

    def wait(
        self,
        timeout: int,
    ) -> dict[str, str] | None:

        try:

            return self._httpd.result.get(
                timeout=timeout
            )

        except Empty:

            return None

    def stop(self) -> None:

        if self._stopped:
            return

        self._stopped = True

        self._httpd.shutdown()

        self._httpd.server_close()


def _parse_redirect(
    value: str,
) -> dict[str, str]:

    parsed = urlparse(value.strip())

    if not parsed.query:

        raise OAuthError(
            "Incolla l'URL completo di reindirizzamento "
            "(deve contenere code e state)."
        )

    return {
        key: values[0]
        for key, values in parse_qs(
            parsed.query
        ).items()
        if values
    }


def _oauth_error(response) -> str:

    try:

        data = response.json()

    except ValueError:

        return (
            f"HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    if not isinstance(data, dict):

        return f"HTTP {response.status_code}"

    error = data.get("error")
    description = data.get("error_description")

    if error and description:

        return f"{error}: {description}"

    if error:

        return str(error)

    return f"HTTP {response.status_code}"


class OAuthProvider:
    """
    Fornisce un access token OAuth, rinnovandolo o avviando il flusso
    interattivo quando necessario.
    """

    def __init__(
        self,
        config: MCPOAuthConfig,
        resource_url: str,
        server_name: str,
        browser: Any = None,
        input_func: Any = None,
    ) -> None:

        self.config = config

        self.resource_url = resource_url.rstrip("/")

        self.server_name = server_name

        self.browser = browser or webbrowser.open

        self.input_func = input_func or input

        self.timeout = (
            config.timeout or DEFAULT_TIMEOUT
        )

        self.cache = TokenCache(
            config.token_cache
            or default_cache_path(server_name)
        )

        self._lock = threading.Lock()

        self._loaded = False

        self._tokens: OAuthTokens | None = None

        self._client: OAuthClient | None = None

        self._metadata: dict[str, Any] | None = None

        self._authorization_server = (
            config.authorization_server
        )

        self._token_endpoint: str | None = None

    # ==================================================
    # Public API
    # ==================================================

    def token(self) -> str:
        """Access token valido, con refresh o login interattivo."""

        with self._lock:

            self._load()

            if (
                self._tokens is not None
                and not self._expired(self._tokens)
            ):

                return self._tokens.access_token

            if (
                self._tokens is not None
                and self._tokens.refresh_token
            ):

                try:

                    self._refresh_locked()

                    return self._tokens.access_token

                except OAuthError:

                    pass

            self._interactive_locked()

            return self._tokens.access_token

    def refresh(self) -> None:
        """Forza il rinnovo; se impossibile, riapre il browser."""

        with self._lock:

            self._load()

            if (
                self._tokens is not None
                and self._tokens.refresh_token
            ):

                try:

                    self._refresh_locked()

                    return

                except OAuthError:

                    pass

            self._interactive_locked()

    # ==================================================
    # Storage
    # ==================================================

    def _load(self) -> None:

        if self._loaded:
            return

        self._loaded = True

        data = self.cache.load()

        if not data:
            return

        if data.get("resource") != self.resource_url:
            return

        client_data = data.get("client")

        if (
            isinstance(client_data, dict)
            and isinstance(
                client_data.get("client_id"),
                str,
            )
            and client_data["client_id"]
        ):

            self._client = OAuthClient(
                **{
                    key: client_data.get(key)
                    for key in (
                        "client_id",
                        "client_secret",
                        "secret_env",
                        "auth_method",
                        "redirect_uri",
                    )
                }
            )

        tokens_data = data.get("tokens")

        if isinstance(tokens_data, dict):

            try:

                self._tokens = OAuthTokens(
                    **{
                        key: tokens_data.get(key)
                        for key in (
                            "access_token",
                            "refresh_token",
                            "token_type",
                            "scope",
                            "expires_at",
                        )
                    }
                )

            except TypeError:

                self._tokens = None

        if isinstance(
            data.get("authorization_server"),
            str,
        ):

            self._authorization_server = data[
                "authorization_server"
            ]

        if isinstance(
            data.get("token_endpoint"),
            str,
        ):

            self._token_endpoint = data[
                "token_endpoint"
            ]

    def _save(self) -> None:

        if self._tokens is None:
            return

        client = (
            asdict(self._client)
            if self._client is not None
            else None
        )

        self.cache.save(
            {
                "resource": self.resource_url,
                "authorization_server": (
                    self._authorization_server
                ),
                "token_endpoint": self._token_endpoint,
                "client": client,
                "tokens": asdict(self._tokens),
            }
        )

    # ==================================================
    # Discovery / client
    # ==================================================

    def _ensure_metadata(self) -> None:

        if self._metadata is not None:
            return

        if not self._authorization_server:

            self._authorization_server = (
                discover_protected_resource(
                    self.resource_url,
                    timeout=30,
                )
            )

        self._metadata = discover_authorization_server(
            self._authorization_server,
            timeout=30,
        )

        self._token_endpoint = self._metadata[
            "token_endpoint"
        ]

    def _env_client_secret(self) -> str | None:

        env_name = self.config.client_secret_env

        if not env_name:
            return None

        value = os.environ.get(
            env_name,
            "",
        ).strip()

        if not value:

            raise OAuthError(
                "OAuth client secret missing: set the "
                f"{env_name} environment variable"
            )

        if not value.isascii():

            raise OAuthError(
                f"{env_name} contains non-ASCII characters"
            )

        return value

    @staticmethod
    def _auth_method(
        metadata: dict[str, Any],
    ) -> str:

        methods = metadata.get(
            "token_endpoint_auth_methods_supported",
            [],
        )

        if "client_secret_basic" in methods:
            return "client_secret_basic"

        if "client_secret_post" in methods:
            return "client_secret_post"

        return "client_secret_basic"

    def _ensure_client(
        self,
        redirect_uri: str,
        metadata: dict[str, Any],
    ) -> None:

        if (
            self._client is not None
            and self._client.redirect_uri
            == redirect_uri
        ):

            return

        if self.config.client_id:

            secret = bool(
                self.config.client_secret_env
            )

            self._client = OAuthClient(
                client_id=self.config.client_id,
                secret_env=(
                    self.config.client_secret_env
                ),
                auth_method=(
                    self._auth_method(metadata)
                    if secret
                    else "none"
                ),
                redirect_uri=redirect_uri,
            )

            return

        registration_endpoint = metadata.get(
            "registration_endpoint"
        )

        if not isinstance(
            registration_endpoint,
            str,
        ):

            raise OAuthError(
                "OAuth client_id missing and the server "
                "has no registration_endpoint"
            )

        try:

            response = requests.post(
                registration_endpoint,
                json={
                    "client_name": "Hagar",
                    "redirect_uris": [redirect_uri],
                    "grant_types": [
                        "authorization_code",
                        "refresh_token",
                    ],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "none",
                    "scope": " ".join(
                        self.config.scopes
                    ),
                },
                headers={"Accept": "application/json"},
                timeout=30,
            )

        except requests.RequestException as exc:

            raise OAuthError(
                "OAuth dynamic client registration failed"
            ) from exc

        if response.status_code not in {200, 201}:

            raise OAuthError(
                "OAuth dynamic client registration failed: "
                + _oauth_error(response)
            )

        try:

            data = response.json()

        except ValueError as exc:

            raise OAuthError(
                "OAuth registration returned no JSON"
            ) from exc

        client_id = data.get("client_id")

        if not isinstance(client_id, str) or not client_id:

            raise OAuthError(
                "OAuth registration returned no client_id"
            )

        client_secret = data.get("client_secret")

        if not isinstance(client_secret, str):
            client_secret = None

        auth_method = data.get(
            "token_endpoint_auth_method"
        )

        if not isinstance(auth_method, str):

            auth_method = (
                self._auth_method(metadata)
                if client_secret
                else "none"
            )

        if client_secret and auth_method == "none":

            auth_method = self._auth_method(metadata)

        self._client = OAuthClient(
            client_id=client_id,
            client_secret=client_secret,
            auth_method=auth_method,
            redirect_uri=redirect_uri,
        )

    # ==================================================
    # Interactive flow
    # ==================================================

    def _interactive_locked(self) -> None:

        self._ensure_metadata()

        assert self._metadata is not None

        callback: LoopbackServer | None = None

        try:

            try:

                callback = LoopbackServer(
                    self.config.redirect_port
                )

            except OSError:

                callback = LoopbackServer(0)

            callback.start()

            self._ensure_client(
                callback.redirect_uri,
                self._metadata,
            )

            assert self._client is not None

            #
            # Fallisce prima di aprire il browser se il secret
            # configurato non è disponibile.
            #

            self._client_secret()

            verifier, challenge = pkce_pair()

            state = secrets.token_urlsafe(24)

            params: dict[str, str] = {
                "response_type": "code",
                "client_id": self._client.client_id,
                "redirect_uri": callback.redirect_uri,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "resource": self.resource_url,
            }

            if self.config.scopes:

                params["scope"] = " ".join(
                    self.config.scopes
                )

                if "offline_access" in self.config.scopes:

                    params["prompt"] = "consent"

            if self.config.audience:

                params["audience"] = (
                    self.config.audience
                )

            endpoint = self._metadata[
                "authorization_endpoint"
            ]

            separator = (
                "&" if "?" in endpoint else "?"
            )

            url = (
                endpoint
                + separator
                + urlencode(params)
            )

            print(
                "OAuth MCP: autorizzazione richiesta "
                f"per '{self.server_name}'."
            )

            print("Apri questo URL nel browser:")
            print(url)

            try:

                self.browser(url)

            except Exception:

                pass

            result = callback.wait(self.timeout)

            if result is None:

                print(
                    "Nessun callback ricevuto; "
                    "incolla l'URL di reindirizzamento."
                )

                answer = self.input_func(
                    "URL di reindirizzamento: "
                ).strip()

                result = _parse_redirect(answer)

            if result.get("error"):

                raise OAuthError(
                    "OAuth authorization failed: "
                    f"{result.get('error')}"
                    + (
                        ": " + result["error_description"]
                        if result.get("error_description")
                        else ""
                    )
                )

            if result.get("state") != state:

                raise OAuthError(
                    "OAuth state mismatch"
                )

            code = result.get("code")

            if not code:

                raise OAuthError(
                    "OAuth callback has no code"
                )

            tokens = self._request_token(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": callback.redirect_uri,
                    "code_verifier": verifier,
                    "resource": self.resource_url,
                }
            )

            self._tokens = tokens

            self._save()

        finally:

            if callback is not None:
                callback.stop()

    # ==================================================
    # Token endpoint
    # ==================================================

    def _client_secret(self) -> str | None:

        if self._client is None:
            return None

        if self._client.client_secret:
            return self._client.client_secret

        return self._env_client_secret()

    def _request_token(
        self,
        data: dict[str, str],
    ) -> OAuthTokens:

        if self._token_endpoint is None:

            self._ensure_metadata()

        assert self._client is not None
        assert self._token_endpoint is not None

        payload = dict(data)

        payload["client_id"] = self._client.client_id

        if self.config.audience:

            payload["audience"] = (
                self.config.audience
            )

        secret = self._client_secret()

        auth = None

        if secret:

            if self._client.auth_method == (
                "client_secret_basic"
            ):

                auth = (
                    self._client.client_id,
                    secret,
                )

            else:

                payload["client_secret"] = secret

        try:

            response = requests.post(
                self._token_endpoint,
                data=payload,
                headers={"Accept": "application/json"},
                auth=auth,
                timeout=30,
            )

        except requests.RequestException as exc:

            raise OAuthError(
                "OAuth token request failed"
            ) from exc

        if response.status_code != 200:

            raise OAuthError(
                "OAuth token request failed: "
                + _oauth_error(response)
            )

        try:

            body = response.json()

        except ValueError as exc:

            raise OAuthError(
                "OAuth token response is not JSON"
            ) from exc

        if not isinstance(body, dict):

            raise OAuthError(
                "OAuth token response is not an object"
            )

        return OAuthTokens.from_response(body)

    def _refresh_locked(self) -> None:

        if (
            self._tokens is None
            or not self._tokens.refresh_token
        ):

            raise OAuthError(
                "OAuth refresh token missing"
            )

        previous_refresh = self._tokens.refresh_token

        tokens = self._request_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": previous_refresh,
                "resource": self.resource_url,
            }
        )

        if not tokens.refresh_token:

            tokens.refresh_token = previous_refresh

        self._tokens = tokens

        self._save()

    @staticmethod
    def _expired(
        tokens: OAuthTokens,
    ) -> bool:

        if tokens.expires_at is None:
            return False

        return time.time() >= tokens.expires_at - 30
