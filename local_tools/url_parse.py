"""Parsing e ispezione di URL, senza accesso alla rete."""

from __future__ import annotations

from urllib.parse import parse_qsl
from urllib.parse import urlsplit
from urllib.parse import urlunsplit


class UrlParser:

    MAX_URL_CHARS = 4096

    MAX_QUERY_PARAMS = 100

    def parse(
        self,
        url: str,
    ) -> dict:
        """Scompone un URL; non risolve DNS e non apre connessioni."""

        if not isinstance(url, str) or not url.strip():

            return {
                "success": False,
                "error": "url must be a non-empty string",
            }

        text = url.strip()

        if any(
            ord(char) < 32 or ord(char) == 127
            for char in url
        ):

            return {
                "success": False,
                "error": "url contains control characters",
            }

        if len(text) > self.MAX_URL_CHARS:

            return {
                "success": False,
                "error": (
                    "url exceeds MAX_URL_CHARS "
                    f"({self.MAX_URL_CHARS})"
                ),
            }

        try:

            parts = urlsplit(text)
            host = parts.hostname or ""
            port = parts.port

        except (ValueError, UnicodeError) as exc:

            return {
                "success": False,
                "error": f"invalid url: {exc}",
            }

        scheme = parts.scheme.lower()

        credentials = bool(
            parts.username or parts.password
        )

        if credentials:

            netloc = "***@"

            if host:

                netloc += host

            if port is not None:

                netloc += f":{port}"

            display_url = urlunsplit(
                (
                    parts.scheme,
                    netloc,
                    parts.path,
                    parts.query,
                    parts.fragment,
                )
            )

        else:

            display_url = text

        pairs = parse_qsl(
            parts.query,
            keep_blank_values=True,
        )

        params = [
            {
                "name": name,
                "value": value,
            }
            for name, value in pairs[
                : self.MAX_QUERY_PARAMS
            ]
        ]

        return {
            "success": True,
            "url": display_url,
            "scheme": scheme,
            "is_absolute": bool(scheme),
            "has_authority": bool(parts.netloc),
            "is_http": scheme in {"http", "https"},
            "host": host,
            "port": port,
            "path": parts.path,
            "query": parts.query,
            "fragment": parts.fragment,
            "query_params": params,
            "query_params_truncated": (
                len(pairs) > self.MAX_QUERY_PARAMS
            ),
            "has_credentials": credentials,
        }
