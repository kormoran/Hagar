from __future__ import annotations

import re

from html import unescape
from urllib.parse import urlparse

import feedparser
import requests


class Feeder:

    MAX_BYTES = 5_000_000

    TIMEOUT = 15

    def _validate_url(
        self,
        url: str,
    ) -> str:

        if not isinstance(url, str) or not url.strip():

            raise ValueError(
                "url must be a non-empty string"
            )

        candidate = url.strip()

        parsed = urlparse(candidate)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError(
                "feed URL must use http or https"
            )

        if not parsed.netloc:
            raise ValueError("feed URL has no host")

        return candidate

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

            url = self._validate_url(url)

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

            response = requests.get(
                url,
                timeout=self.TIMEOUT,
                headers={
                    "User-Agent": "Hagar/0.2.0",
                },
            )

            response.raise_for_status()

            content = response.content

            if len(content) > self.MAX_BYTES:

                raise ValueError(
                    "feed is larger than "
                    f"{self.MAX_BYTES} bytes"
                )

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
