from __future__ import annotations

import ipaddress
import re
import socket

from html import unescape
from urllib.parse import urljoin, urlparse

import feedparser
import requests


class Feeder:

    MAX_BYTES = 5_000_000

    MAX_URL_CHARS = 2048

    MAX_REDIRECTS = 3

    TIMEOUT = 15

    def _validate_url(
        self,
        url: str,
    ) -> str:
        """
        Valida schema, host e destinazione.

        Non basta controllare la stringa: un hostname pubblico può
        risolvere su un indirizzo privato. Ogni indirizzo restituito da
        getaddrinfo deve essere globale (non loopback, privato,
        link-local, multicast o riservato).
        """

        if not isinstance(url, str) or not url.strip():

            raise ValueError(
                "url must be a non-empty string"
            )

        candidate = url.strip()

        if len(candidate) > self.MAX_URL_CHARS:

            raise ValueError("feed URL is too long")

        parsed = urlparse(candidate)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError(
                "feed URL must use http or https"
            )

        if not parsed.netloc:
            raise ValueError("feed URL has no host")

        if parsed.username or parsed.password:

            raise ValueError(
                "feed URL must not contain credentials"
            )

        host = parsed.hostname

        if not host:
            raise ValueError("feed URL has no host")

        port = parsed.port

        if port is None:
            port = 443 if parsed.scheme == "https" else 80

        try:

            addresses = socket.getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            )

        except socket.gaierror as ex:

            raise ValueError(
                f"feed host cannot be resolved: {ex}"
            ) from ex

        if not addresses:

            raise ValueError(
                "feed host has no addresses"
            )

        checked = 0

        for family, _, _, _, sockaddr in addresses:

            if family not in (socket.AF_INET, socket.AF_INET6):
                continue

            checked += 1

            raw_ip = sockaddr[0].split("%", 1)[0]

            try:
                address = ipaddress.ip_address(raw_ip)
            except ValueError as ex:

                raise ValueError(
                    f"feed host has invalid address: {raw_ip}"
                ) from ex

            if not address.is_global:

                raise ValueError(
                    "feed URL resolves to a non-public address"
                )

        if not checked:

            raise ValueError(
                "feed host has no usable addresses"
            )

        return candidate

    def _fetch(
        self,
        url: str,
    ) -> requests.Response:
        """
        Scarica il feed senza seguire redirect in automatico: ogni
        destinazione viene rivalidata contro la policy SSRF.
        """

        current = url

        for _ in range(self.MAX_REDIRECTS + 1):

            current = self._validate_url(current)

            response = requests.get(
                current,
                timeout=self.TIMEOUT,
                headers={
                    "User-Agent": "Hagar/0.2.0",
                },
                allow_redirects=False,
                stream=True,
            )

            if response.status_code in {
                301,
                302,
                303,
                307,
                308,
            }:

                location = response.headers.get(
                    "Location"
                )

                if not location:

                    raise ValueError(
                        "feed redirect has no Location"
                    )

                current = urljoin(
                    current,
                    location,
                )

                continue

            response.raise_for_status()

            return response

        raise ValueError("too many feed redirects")

    def _strip_html(
        self,
        text: str | None,
    ) -> str:

        if not text:
            return ""

        text = re.sub(
            r"<[^>]+>",
            " ",
            text,
        )

        text = unescape(text)

        return " ".join(
            text.split()
        )

    def _extract_date(
        self,
        entry,
    ) -> str | None:

        return (
            getattr(entry, "published", None)
            or getattr(entry, "updated", None)
        )

    def read(
        self,
        url: str,
        max_items: int = 20,
    ) -> dict:

        try:

            if isinstance(max_items, bool):
                raise ValueError(
                    "max_items must be an integer"
                )

            max_items = max(
                1,
                min(
                    int(max_items),
                    100,
                ),
            )

            response = self._fetch(url)

            content_length = response.headers.get(
                "Content-Length"
            )

            if content_length:

                try:
                    declared = int(content_length)
                except ValueError:
                    declared = 0

                if declared > self.MAX_BYTES:

                    raise ValueError(
                        "feed is larger than "
                        f"{self.MAX_BYTES} bytes"
                    )

            content = bytearray()

            for chunk in response.iter_content(
                chunk_size=65536
            ):

                content.extend(chunk)

                if len(content) > self.MAX_BYTES:

                    raise ValueError(
                        "feed is larger than "
                        f"{self.MAX_BYTES} bytes"
                    )

            content = bytes(content)

            parsed = feedparser.parse(content)

            if (
                getattr(parsed, "bozo", False)
                and not parsed.entries
            ):

                raise ValueError(
                    "Invalid feed format."
                )

            items = []

            total_items = len(
                parsed.entries
            )

            for entry in parsed.entries[
                :max_items
            ]:

                items.append(
                    {
                        "title":
                            getattr(
                                entry,
                                "title",
                                "",
                            ),
                        "link":
                            getattr(
                                entry,
                                "link",
                                "",
                            ),
                        "published":
                            self._extract_date(
                                entry
                            ),
                        "author":
                            getattr(
                                entry,
                                "author",
                                None,
                            ),
                        "summary":
                            self._strip_html(
                                getattr(
                                    entry,
                                    "summary",
                                    "",
                                )
                            ),
                    }
                )

            feed_info = getattr(
                parsed,
                "feed",
                {},
            )

            return {
                "success": True,
                "feed": {
                    "title":
                        getattr(
                            feed_info,
                            "title",
                            "",
                        ),
                    "description":
                        self._strip_html(
                            getattr(
                                feed_info,
                                "description",
                                "",
                            )
                        ),
                    "link":
                        getattr(
                            feed_info,
                            "link",
                            "",
                        ),
                    "type":
                        getattr(
                            parsed,
                            "version",
                            "unknown",
                        ),
                },
                "total_items":
                    total_items,
                "returned_items":
                    len(items),
                "truncated":
                    total_items
                    > max_items,
                "items":
                    items,
            }

        except Exception as ex:

            return {
                "success": False,
                "error": str(ex),
            }
