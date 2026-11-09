"""Tool read-only per trasformazioni testuali bounded."""

from __future__ import annotations

import json
import re

from core.filesystem import FileSystemSandbox
from core.permissions import Capability
from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry


MAX_INPUT_CHARS = 1_000_000
MAX_OUTPUT_CHARS = 100_000
MAX_PATTERN_CHARS = 1_000
MAX_MATCHES = 10_000


class TextTransformError(RuntimeError):
    pass


class TextTransformer:

    def __init__(
        self,
        filesystem: FileSystemSandbox,
    ) -> None:

        self.fs = filesystem

    def transform(
        self,
        operation: str,
        path: str | None = None,
        text: str | None = None,
        pattern: str | None = None,
        replacement: str | None = None,
        ignore_case: bool = False,
        invert: bool = False,
        line_numbers: bool = False,
        numeric: bool = False,
        reverse: bool = False,
        unique: bool = False,
        delimiter: str = "\t",
        fields: str = "1",
        set1: str = "",
        set2: str = "",
        count: int = 10,
        unit: str = "lines",
        global_replace: bool = True,
    ) -> dict:

        source = self._source(path, text)

        if operation == "grep":
            return self._grep(
                source,
                pattern,
                ignore_case,
                invert,
                line_numbers,
            )

        if operation == "sort":
            return self._sort(
                source,
                numeric,
                reverse,
                unique,
            )

        if operation == "uniq":
            return self._uniq(source)

        if operation == "cut":
            return self._cut(source, delimiter, fields)

        if operation == "tr":
            return self._tr(source, set1, set2)

        if operation == "wc":
            return self._wc(source, unit)

        if operation in {"head", "tail"}:
            return self._head_tail(
                source,
                operation,
                count,
            )

        if operation == "sed_replace":
            return self._sed_replace(
                source,
                pattern,
                replacement,
                ignore_case,
                global_replace,
            )

        raise TextTransformError(
            f"unsupported text transform: {operation}"
        )

    def _source(
        self,
        path: str | None,
        text: str | None,
    ) -> str:

        if (path is None) == (text is None):
            raise TextTransformError(
                "provide exactly one of path or text"
            )

        if path is not None:
            return self._read_path(path)

        if len(text) > MAX_INPUT_CHARS:
            raise TextTransformError("input text is too large")

        return text

    def _read_path(self, path: str) -> str:

        try:
            content = self.fs.read_file(path)
        except ValueError as exc:
            if "larger than one chunk" not in str(exc):
                raise

            pieces = []
            offset = 0

            while True:
                chunk = self.fs.read_chunk(
                    path,
                    offset=offset,
                    length=65536,
                )
                pieces.append(chunk["content"])
                offset = chunk["next_offset"]

                if not chunk["has_more"]:
                    break

                if offset > MAX_INPUT_CHARS:
                    raise TextTransformError("input file is too large")

            content = "".join(pieces)

        if len(content) > MAX_INPUT_CHARS:
            raise TextTransformError("input file is too large")

        return content

    @staticmethod
    def _bounded(text: str) -> tuple[str, bool]:
        if len(text) <= MAX_OUTPUT_CHARS:
            return text, False
        return text[:MAX_OUTPUT_CHARS], True

    def _grep(
        self,
        text: str,
        pattern: str | None,
        ignore_case: bool,
        invert: bool,
        line_numbers: bool,
    ) -> dict:

        if not isinstance(pattern, str) or not pattern:
            raise TextTransformError("grep requires a pattern")

        if len(pattern) > MAX_PATTERN_CHARS:
            raise TextTransformError("grep pattern is too long")

        try:
            expression = re.compile(
                pattern,
                re.IGNORECASE if ignore_case else 0,
            )
        except re.error as exc:
            raise TextTransformError(f"invalid pattern: {exc}") from exc

        lines = []
        matches = 0

        for number, line in enumerate(text.splitlines(), 1):
            found = bool(expression.search(line))
            if found == invert:
                continue
            matches += 1
            if matches > MAX_MATCHES:
                raise TextTransformError("too many matches")
            lines.append(
                (f"{number}:" if line_numbers else "") + line
            )

        output = "\n".join(lines) + ("\n" if lines else "")
        output, truncated = self._bounded(output)

        return {
            "operation": "grep",
            "text": output,
            "matches": matches,
            "truncated": truncated,
        }

    def _sort(
        self,
        text: str,
        numeric: bool,
        reverse: bool,
        unique: bool,
    ) -> dict:

        lines = text.splitlines()

        if numeric:
            try:
                lines.sort(
                    key=float,
                    reverse=reverse,
                )
            except ValueError as exc:
                raise TextTransformError(
                    "sort -n requires numeric lines"
                ) from exc
        else:
            lines.sort(reverse=reverse)

        if unique:
            lines = list(dict.fromkeys(lines))

        output, truncated = self._bounded(
            "\n".join(lines) + ("\n" if lines else "")
        )
        return {
            "operation": "sort",
            "text": output,
            "matches": len(lines),
            "truncated": truncated,
        }

    def _uniq(self, text: str) -> dict:

        lines = []
        previous = object()

        for line in text.splitlines():
            if line != previous:
                lines.append(line)
                previous = line

        output, truncated = self._bounded(
            "\n".join(lines) + ("\n" if lines else "")
        )
        return {
            "operation": "uniq",
            "text": output,
            "matches": len(lines),
            "truncated": truncated,
        }

    def _cut(
        self,
        text: str,
        delimiter: str,
        fields: str,
    ) -> dict:

        if not delimiter:
            raise TextTransformError("cut delimiter cannot be empty")

        try:
            selected = [
                int(value) - 1
                for value in fields.split(",")
            ]
        except ValueError as exc:
            raise TextTransformError("invalid cut fields") from exc

        result = []

        for line in text.splitlines():
            parts = line.split(delimiter)
            result.append(
                delimiter.join(
                    parts[index]
                    for index in selected
                    if 0 <= index < len(parts)
                )
            )

        output, truncated = self._bounded(
            "\n".join(result) + ("\n" if result else "")
        )
        return {
            "operation": "cut",
            "text": output,
            "matches": len(result),
            "truncated": truncated,
        }

    def _tr(
        self,
        text: str,
        set1: str,
        set2: str,
    ) -> dict:

        if not set1:
            raise TextTransformError("tr requires SET1")

        try:
            table = str.maketrans(set1, set2)
        except ValueError as exc:
            raise TextTransformError("tr sets have different lengths") from exc

        output, truncated = self._bounded(text.translate(table))
        return {
            "operation": "tr",
            "text": output,
            "truncated": truncated,
        }

    def _wc(self, text: str, unit: str) -> dict:

        if unit == "lines":
            value = len(text.splitlines())
        elif unit == "words":
            value = len(text.split())
        elif unit == "bytes":
            value = len(text.encode("utf-8"))
        else:
            raise TextTransformError(
                "wc unit must be lines, words or bytes"
            )

        return {
            "operation": "wc",
            "text": f"{value}\n",
            "matches": value,
            "truncated": False,
        }

    def _head_tail(
        self,
        text: str,
        operation: str,
        count: int,
    ) -> dict:

        if count < 0:
            raise TextTransformError("count must be >= 0")

        lines = text.splitlines()
        selected = (
            lines[:count]
            if operation == "head"
            else lines[-count:]
        )
        output, truncated = self._bounded(
            "\n".join(selected) + ("\n" if selected else "")
        )
        return {
            "operation": operation,
            "text": output,
            "matches": len(selected),
            "truncated": truncated,
        }

    def _sed_replace(
        self,
        text: str,
        pattern: str | None,
        replacement: str | None,
        ignore_case: bool,
        global_replace: bool,
    ) -> dict:

        if not isinstance(pattern, str) or not pattern:
            raise TextTransformError("sed requires a pattern")

        if not isinstance(replacement, str):
            raise TextTransformError("sed requires a replacement")

        if len(pattern) > MAX_PATTERN_CHARS:
            raise TextTransformError("sed pattern is too long")

        try:
            expression = re.compile(
                pattern,
                re.IGNORECASE if ignore_case else 0,
            )
        except re.error as exc:
            raise TextTransformError(f"invalid pattern: {exc}") from exc

        output = expression.sub(
            replacement,
            text,
            count=0 if global_replace else 1,
        )
        output, truncated = self._bounded(output)

        return {
            "operation": "sed_replace",
            "text": output,
            "truncated": truncated,
        }


class TextTransformToolProvider:

    def __init__(
        self,
        filesystem: FileSystemSandbox,
    ) -> None:

        self.transformer = TextTransformer(filesystem)

    def register_tools(self, registry: ToolRegistry) -> None:

        registry.register(
            ToolDefinition(
                name="text.transform",
                description=(
                    "Apply a bounded, declarative text transformation "
                    "to a sandbox file or inline text. Operations: "
                    "grep, sort, uniq, cut, tr, wc, head, tail, "
                    "sed_replace. This tool is read-only."
                ),
                category="text",
                capabilities=(
                    Capability.FILESYSTEM_READ
                    | Capability.COMPUTE
                ),
                parameters=[
                    ToolParameter("operation", "string", "Operation name."),
                    ToolParameter("path", "string", "Input path.", required=False, default=None),
                    ToolParameter("text", "string", "Inline input.", required=False, default=None),
                    ToolParameter("pattern", "string", "grep/sed pattern.", required=False, default=None),
                    ToolParameter("replacement", "string", "sed replacement.", required=False, default=None),
                    ToolParameter("ignore_case", "boolean", "Case-insensitive.", required=False, default=False),
                    ToolParameter("invert", "boolean", "Invert grep.", required=False, default=False),
                    ToolParameter("line_numbers", "boolean", "Grep line numbers.", required=False, default=False),
                    ToolParameter("numeric", "boolean", "Numeric sort.", required=False, default=False),
                    ToolParameter("reverse", "boolean", "Reverse sort.", required=False, default=False),
                    ToolParameter("unique", "boolean", "Unique sort.", required=False, default=False),
                    ToolParameter("delimiter", "string", "Cut delimiter.", required=False, default="\t"),
                    ToolParameter("fields", "string", "Cut fields.", required=False, default="1"),
                    ToolParameter("set1", "string", "tr source set.", required=False, default=""),
                    ToolParameter("set2", "string", "tr destination set.", required=False, default=""),
                    ToolParameter("count", "integer", "head/tail lines.", required=False, default=10),
                    ToolParameter("unit", "string", "wc unit.", required=False, default="lines"),
                    ToolParameter("global_replace", "boolean", "sed global.", required=False, default=True),
                ],
                handler=self.transform,
            )
        )

    def transform(
        self,
        operation: str,
        path: str | None = None,
        text: str | None = None,
        pattern: str | None = None,
        replacement: str | None = None,
        ignore_case: bool = False,
        invert: bool = False,
        line_numbers: bool = False,
        numeric: bool = False,
        reverse: bool = False,
        unique: bool = False,
        delimiter: str = "\t",
        fields: str = "1",
        set1: str = "",
        set2: str = "",
        count: int = 10,
        unit: str = "lines",
        global_replace: bool = True,
    ) -> str:

        result = self.transformer.transform(
            operation=operation,
            path=path,
            text=text,
            pattern=pattern,
            replacement=replacement,
            ignore_case=ignore_case,
            invert=invert,
            line_numbers=line_numbers,
            numeric=numeric,
            reverse=reverse,
            unique=unique,
            delimiter=delimiter,
            fields=fields,
            set1=set1,
            set2=set2,
            count=count,
            unit=unit,
            global_replace=global_replace,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
