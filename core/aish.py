"""AIsh: linguaggio di comando sopra i tool Hagar.

Non è una shell di sistema. Non usa subprocess, non espande variabili,
non esegue programmi e non conosce path host. Ogni comando viene
compilato in una chiamata al ToolRegistry, quindi passa da policy,
sandbox, checkpoint e audit.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import shlex
import sys

from typing import Any


class AishError(RuntimeError):
    pass


MUTATING = frozenset({
    "mkdir",
    "touch",
    "cp",
    "mv",
    "rm",
})

READ_ONLY = frozenset({
    "pwd", "cd", "ls", "stat", "cat", "head", "tail", "wc",
    "grep", "find", "echo", "printf", "sort", "uniq", "cut",
    "tr", "sha256sum", "df", "date", "basename", "dirname",
    "true", "false",
})

ALL_COMMANDS = MUTATING | READ_ONLY

MAX_OUTPUT_CHARS = 100_000
MAX_INPUT_CHARS = 1_000_000
MAX_COMMANDS = 50


class AishExecutor:
    """Esegue un piccolo linguaggio di comandi, senza shell host."""

    def __init__(
        self,
        registry: Any,
        filesystem: Any,
        audit: Any = None,
        max_output_chars: int = MAX_OUTPUT_CHARS,
    ) -> None:

        self.registry = registry
        self.fs = filesystem
        self.audit = audit
        self.max_output_chars = max_output_chars

    def execute(self, script: str) -> dict[str, Any]:

        if not isinstance(script, str) or not script.strip():
            raise AishError("script must be a non-empty string")

        if len(script) > MAX_INPUT_CHARS:
            raise AishError("script is too large")

        self._reject_shell_features(script)

        try:
            tokens = shlex.split(script, posix=True)
        except ValueError as exc:
            raise AishError(f"parse error: {exc}") from exc

        stages = self._split_pipeline(tokens)

        if len(stages) > MAX_COMMANDS:
            raise AishError("too many pipeline stages")

        stdin = ""
        commands: list[dict[str, Any]] = []
        final_output = ""

        for stage in stages:

            if not stage:
                raise AishError("empty command")

            name, args = stage[0], stage[1:]

            if name not in ALL_COMMANDS:
                raise AishError(f"command not allowed: {name}")

            if len(stages) > 1 and name in MUTATING:
                raise AishError(
                    f"{name} cannot be used inside a pipeline"
                )

            result = self._run(name, args, stdin)

            if isinstance(result, str):
                if len(result) > self.max_output_chars:
                    raise AishError(
                        f"command {name} produced too much output"
                    )
                stdin = result
                final_output = result

            commands.append({
                "command": name,
                "arguments": args,
            })

            self._record(
                "aish.command",
                command=name,
                arguments=args,
                pipeline=len(stages),
            )

        return {
            "success": True,
            "exit_code": 0,
            "stdout": final_output,
            "commands": commands,
        }

    @staticmethod
    def _reject_shell_features(script: str) -> None:

        forbidden = {
            "`": "command substitution",
            "$(": "command substitution",
            "${": "variable expansion",
            ";": "command separator",
            "&&": "conditional operator",
            "||": "conditional operator",
            "&": "background operator",
            ">": "redirection",
            "<": "redirection",
            "<<" : "here-doc",
        }

        for marker, reason in forbidden.items():

            if marker in script:
                raise AishError(
                    f"not supported in AIsh: {reason} ({marker})"
                )

    @staticmethod
    def _split_pipeline(
        tokens: list[str],
    ) -> list[list[str]]:

        stages: list[list[str]] = [[]]

        for token in tokens:

            if token == "|":
                if not stages[-1]:
                    raise AishError("empty pipeline stage")
                stages.append([])
                continue

            stages[-1].append(token)

        if not stages[-1]:
            raise AishError("empty pipeline stage")

        return stages

    def _run(
        self,
        name: str,
        args: list[str],
        stdin: str,
    ) -> str:

        handler = getattr(
            self,
            f"_cmd_{name}",
            None,
        )

        if handler is None:
            raise AishError(f"command not implemented: {name}")

        try:
            return handler(args, stdin)

        except AishError:
            raise
        except Exception as exc:
            raise AishError(f"{name}: {exc}") from exc

    # ==================================================
    # Helpers
    # ==================================================

    def _call(self, tool: str, **kwargs) -> Any:
        return self.registry.execute(tool, **kwargs)

    def _read_text(self, path: str) -> str:

        try:
            return self._call(
                "filesystem.read_file",
                path=path,
            )

        except Exception as exc:

            if "larger than one chunk" not in str(exc):
                raise

            pieces: list[str] = []
            offset = 0

            while True:

                payload = json.loads(
                    self._call(
                        "filesystem.read_chunk",
                        path=path,
                        offset=offset,
                        length=65536,
                    )
                )
                pieces.append(payload["content"])
                offset = payload["next_offset"]

                if not payload["has_more"]:
                    break

                if offset > MAX_INPUT_CHARS:
                    raise AishError("file is too large")

            return "".join(pieces)

    def _record(self, event: str, **fields: Any) -> None:

        if self.audit is not None:
            self.audit.record(event, **fields)

    # ==================================================
    # Read-only commands
    # ==================================================

    def _cmd_pwd(self, args, stdin):
        if args:
            raise AishError("pwd takes no arguments")
        return self.fs.virtual_path(self.fs.current_directory) + "\n"

    def _cmd_cd(self, args, stdin):
        if len(args) != 1:
            raise AishError("usage: cd PATH")
        self._call("filesystem.chdir", path=args[0])
        return ""

    def _cmd_ls(self, args, stdin):
        path = args[0] if args else "."
        payload = json.loads(
            self._call("filesystem.list_dir", path=path)
        )
        lines = [
            entry["path"].rsplit("/", 1)[-1]
            for entry in payload["entries"]
        ]
        return "\n".join(lines) + ("\n" if lines else "")

    def _cmd_stat(self, args, stdin):
        if len(args) != 1:
            raise AishError("usage: stat PATH")
        return self._call("filesystem.stat", path=args[0]) + "\n"

    def _cmd_cat(self, args, stdin):
        if not args:
            return stdin

        pieces = []
        for path in args:
            pieces.append(self._read_text(path))
        return "".join(pieces)

    def _cmd_head(self, args, stdin):
        count = 10
        paths = list(args)

        if paths[:1] == ["-n"]:
            if len(paths) < 2:
                raise AishError("usage: head -n N [FILE...]")
            count = int(paths[1])
            paths = paths[2:]

        text = self._read_text(paths[0]) if paths else stdin
        return "\n".join(text.splitlines()[:count]) + "\n"

    def _cmd_tail(self, args, stdin):
        count = 10
        paths = list(args)

        if paths[:1] == ["-n"]:
            if len(paths) < 2:
                raise AishError("usage: tail -n N [FILE...]")
            count = int(paths[1])
            paths = paths[2:]

        text = self._read_text(paths[0]) if paths else stdin
        return "\n".join(text.splitlines()[-count:]) + "\n"

    def _cmd_wc(self, args, stdin):
        mode = args[0] if args and args[0].startswith("-") else None
        paths = [arg for arg in args if not arg.startswith("-")]

        text = self._read_text(paths[0]) if paths else stdin

        if mode == "-l":
            return f"{len(text.splitlines())}\n"
        if mode == "-w":
            return f"{len(text.split())}\n"
        if mode == "-c":
            return f"{len(text.encode('utf-8'))}\n"

        raise AishError("usage: wc [-l|-w|-c] [FILE]")

    def _cmd_grep(self, args, stdin):
        ignore_case = False
        show_lines = False
        pattern = None
        paths: list[str] = []

        for arg in args:
            if arg == "-i":
                ignore_case = True
            elif arg == "-n":
                show_lines = True
            elif pattern is None:
                pattern = arg
            else:
                paths.append(arg)

        if pattern is None:
            raise AishError("usage: grep [-i] [-n] PATTERN [FILE...]")

        if len(pattern) > 200:
            raise AishError("grep pattern is too long")

        try:
            expression = re.compile(
                pattern,
                re.IGNORECASE if ignore_case else 0,
            )
        except re.error as exc:
            raise AishError(f"invalid grep pattern: {exc}") from exc

        sources = (
            [(path, self._read_text(path)) for path in paths]
            if paths
            else [("<stdin>", stdin)]
        )
        lines = []

        for source, text in sources:

            for number, line in enumerate(text.splitlines(), 1):

                if expression.search(line):
                    prefix = f"{source}:{number}:" if show_lines else ""
                    lines.append(prefix + line)

        return "\n".join(lines) + ("\n" if lines else "")

    def _cmd_find(self, args, stdin):
        path = "."
        pattern = "*"
        only_type = None

        index = 0
        while index < len(args):
            arg = args[index]
            if arg == "-name":
                index += 1
                if index >= len(args):
                    raise AishError("find: -name requires a pattern")
                pattern = args[index]
            elif arg == "-type":
                index += 1
                if index >= len(args):
                    raise AishError("find: -type requires f or d")
                only_type = args[index]
                if only_type not in {"f", "d"}:
                    raise AishError("find: only -type f or -type d")
            elif arg == "-maxdepth":
                raise AishError("find: -maxdepth is not supported")
            elif arg == "-exec":
                raise AishError("find: -exec is forbidden")
            elif arg.startswith("-"):
                raise AishError(f"find: unsupported option {arg}")
            else:
                path = arg
            index += 1

        payload = json.loads(
            self._call(
                "filesystem.search",
                pattern=pattern,
                path=path,
            )
        )
        lines = []

        for item in payload["results"]:
            if only_type == "f" and item["kind"] != "file":
                continue
            if only_type == "d" and item["kind"] != "directory":
                continue
            lines.append(item["path"])

        return "\n".join(lines) + ("\n" if lines else "")

    def _cmd_echo(self, args, stdin):
        return " ".join(args) + "\n"

    def _cmd_printf(self, args, stdin):
        if not args:
            raise AishError("usage: printf FORMAT [ARG...]")
        return args[0] % tuple(args[1:]) if len(args) > 1 else args[0]

    def _cmd_sort(self, args, stdin):
        reverse = "-r" in args
        numeric = "-n" in args
        unique = "-u" in args
        paths = [arg for arg in args if not arg.startswith("-")]
        text = self._read_text(paths[0]) if paths else stdin
        lines = text.splitlines()

        if numeric:
            lines.sort(
                key=lambda line: float(line),
                reverse=reverse,
            )
        else:
            lines.sort(reverse=reverse)

        if unique:
            lines = list(dict.fromkeys(lines))

        return "\n".join(lines) + ("\n" if lines else "")

    def _cmd_uniq(self, args, stdin):
        paths = [arg for arg in args if not arg.startswith("-")]
        text = self._read_text(paths[0]) if paths else stdin
        lines = []
        previous = object()

        for line in text.splitlines():
            if line != previous:
                lines.append(line)
                previous = line

        return "\n".join(lines) + ("\n" if lines else "")

    def _cmd_cut(self, args, stdin):
        delimiter = "\t"
        fields = "1"
        paths = []

        index = 0
        while index < len(args):
            if args[index] == "-d":
                index += 1
                delimiter = args[index]
            elif args[index] == "-f":
                index += 1
                fields = args[index]
            else:
                paths.append(args[index])
            index += 1

        text = self._read_text(paths[0]) if paths else stdin
        selected = [
            int(value) - 1
            for value in fields.split(",")
        ]
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

        return "\n".join(result) + ("\n" if result else "")

    def _cmd_tr(self, args, stdin):
        if len(args) != 2:
            raise AishError("usage: tr SET1 SET2")
        return stdin.translate(
            str.maketrans(args[0], args[1])
        )

    def _cmd_sha256sum(self, args, stdin):
        if len(args) != 1:
            raise AishError("usage: sha256sum FILE")
        data = self._read_text(args[0]).encode("utf-8")
        return f"{hashlib.sha256(data).hexdigest()}  {args[0]}\n"

    def _cmd_df(self, args, stdin):
        if args:
            raise AishError("df takes no arguments")
        return str(self._call("filesystem.free_space")) + "\n"

    def _cmd_date(self, args, stdin):
        if args:
            raise AishError("date takes no arguments")
        return self._call("clock.now") + "\n"

    def _cmd_basename(self, args, stdin):
        if len(args) != 1:
            raise AishError("usage: basename PATH")
        return posixpath.basename(args[0]) + "\n"

    def _cmd_dirname(self, args, stdin):
        if len(args) != 1:
            raise AishError("usage: dirname PATH")
        return posixpath.dirname(args[0]) + "\n"

    def _cmd_true(self, args, stdin):
        return ""

    def _cmd_false(self, args, stdin):
        raise AishError("false")

    # ==================================================
    # Mutating commands
    # ==================================================

    def _cmd_mkdir(self, args, stdin):
        paths = [arg for arg in args if arg != "-p"]
        if len(paths) != 1:
            raise AishError("usage: mkdir [-p] PATH")
        self._call("filesystem.mkdir", path=paths[0])
        return ""

    def _cmd_touch(self, args, stdin):
        if len(args) != 1:
            raise AishError("usage: touch FILE")

        try:
            self._call("filesystem.stat", path=args[0])
        except Exception:
            pass

        payload = json.loads(
            self._call("filesystem.stat", path=args[0])
        )

        if payload["exists"]:
            return ""

        self._call(
            "filesystem.create_file",
            path=args[0],
            content="",
        )
        return ""

    def _cmd_cp(self, args, stdin):
        if len(args) != 2:
            raise AishError("usage: cp SOURCE DESTINATION")
        self._call(
            "filesystem.copy_file",
            source=args[0],
            destination=args[1],
        )
        return ""

    def _cmd_mv(self, args, stdin):
        if len(args) != 2:
            raise AishError("usage: mv SOURCE DESTINATION")
        self._call(
            "filesystem.rename",
            source=args[0],
            destination=args[1],
        )
        return ""

    def _cmd_rm(self, args, stdin):
        if len(args) != 1:
            raise AishError("usage: rm FILE")
        self._call("filesystem.delete_file", path=args[0])
        return ""
