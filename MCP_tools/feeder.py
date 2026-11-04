from __future__ import annotations

import re
from html import unescape

import feedparser


class Feeder:

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

        if hasattr(
            entry,
            "published",
        ):
            return entry.published

        if hasattr(
            entry,
            "updated",
        ):
            return entry.updated

        return None

    def read(
        self,
        url: str,
        max_items: int = 20,
    ) -> dict:

        try:

            max_items = max(
                1,
                min(
                    max_items,
                    100,
                ),
            )

            parsed = feedparser.parse(
                url
            )

            if (
                hasattr(
                    parsed,
                    "bozo"
                )
                and parsed.bozo
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

            feed_info = parsed.feed

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