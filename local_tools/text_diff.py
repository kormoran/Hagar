"""Diff unificato tra due testi."""

from __future__ import annotations

import difflib


class TextDiff:

    MAX_INPUT_CHARS = 20000

    MAX_OUTPUT_CHARS = 20000

    def compare(
        self,
        left: str,
        right: str,
        context: int = 3,
    ) -> dict:
        """Restituisce un diff unificato, con limiti di sicurezza."""

        if not isinstance(left, str) or not isinstance(right, str):

            return {
                "success": False,
                "error": "left and right must be strings",
            }

        if len(left) > self.MAX_INPUT_CHARS:

            return {
                "success": False,
                "error": (
                    "left exceeds MAX_INPUT_CHARS "
                    f"({self.MAX_INPUT_CHARS})"
                ),
            }

        if len(right) > self.MAX_INPUT_CHARS:

            return {
                "success": False,
                "error": (
                    "right exceeds MAX_INPUT_CHARS "
                    f"({self.MAX_INPUT_CHARS})"
                ),
            }

        try:

            context_lines = int(context)

        except (TypeError, ValueError):

            return {
                "success": False,
                "error": "context must be an integer",
            }

        context_lines = max(0, min(context_lines, 10))

        if left == right:

            return {
                "success": True,
                "identical": True,
                "diff": "",
                "added_lines": 0,
                "removed_lines": 0,
                "truncated": False,
            }

        lines = list(
            difflib.unified_diff(
                left.splitlines(),
                right.splitlines(),
                fromfile="left",
                tofile="right",
                lineterm="",
                n=context_lines,
            )
        )

        diff = "\n".join(lines)

        truncated = len(diff) > self.MAX_OUTPUT_CHARS

        if truncated:

            diff = (
                diff[: self.MAX_OUTPUT_CHARS]
                .rstrip()
                + "\n… diff troncato"
            )

        added = sum(
            1
            for line in lines
            if line.startswith("+")
            and not line.startswith("+++")
        )
        removed = sum(
            1
            for line in lines
            if line.startswith("-")
            and not line.startswith("---")
        )

        return {
            "success": True,
            "identical": False,
            "diff": diff,
            "added_lines": added,
            "removed_lines": removed,
            "truncated": truncated,
        }
