"""Runner host per le ricette dev.run."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.dev_recipes import (
    DevRecipe,
    DevRecipeError,
    DevRecipeLoader,
    RecipeBook,
)


class DevExecutionError(RuntimeError):
    pass


@dataclass
class DevResult:
    recipe: str
    exit_code: int | None
    success: bool
    timed_out: bool
    duration_ms: float
    stdout: str
    stderr: str
    truncated: bool = False
    artifact_id: str | None = None
    backend: str = "host"

    def as_dict(self) -> dict[str, Any]:
        return {
            "recipe": self.recipe,
            "backend": self.backend,
            "exit_code": self.exit_code,
            "success": self.success,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "truncated": self.truncated,
            "artifact_id": self.artifact_id,
        }


class DevRunner:

    def __init__(
        self,
        filesystem,
        book: RecipeBook,
        audit: Any = None,
        artifact_store: Any = None,
        max_output_chars: int = 100_000,
        copy_workspace: bool = True,
    ) -> None:

        self.fs = filesystem
        self.book = book
        self.audit = audit
        self.artifact_store = artifact_store
        self.max_output_chars = max(1, int(max_output_chars))
        self.copy_workspace = bool(copy_workspace)
        self._lock = threading.Lock()
        self.loader = DevRecipeLoader()

    def list_recipes(self) -> list[dict[str, Any]]:
        return [
            recipe.as_dict()
            for recipe in sorted(
                self.book.recipes.values(),
                key=lambda item: item.name,
            )
        ]

    def run(
        self,
        recipe_name: str,
        parameters: dict[str, Any] | None = None,
    ) -> DevResult:

        if not self._lock.acquire(blocking=False):
            raise DevExecutionError("another dev.run is already running")

        try:
            return self._run_locked(recipe_name, parameters)
        finally:
            self._lock.release()

    def _run_locked(
        self,
        recipe_name: str,
        parameters: dict[str, Any] | None,
    ) -> DevResult:

        recipe = self.book.recipes.get(recipe_name)

        if recipe is None:
            raise DevExecutionError(f"unknown recipe: {recipe_name}")

        values = self.loader.resolve_parameters(recipe, parameters)

        for name, parameter in recipe.parameters.items():
            if parameter.kind == "path":
                try:
                    self.fs.resolve_path(str(values[name]))
                except Exception as exc:
                    raise DevExecutionError(
                        f"parameter {name} is outside the sandbox"
                    ) from exc

        argv = self.loader.render_argv(recipe, values)

        source_cwd = self._resolve_cwd(recipe)

        if recipe.stdin_file:
            stdin_source = self.fs.resolve_path(recipe.stdin_file)
            if not stdin_source.is_file():
                raise DevExecutionError("stdin file not found")
            stdin_data = stdin_source.read_bytes()
        else:
            stdin_data = None

        self._record(
            "dev.run.start",
            recipe=recipe.name,
            argv_hash=_hash_argv(argv),
            cwd=recipe.cwd,
            backend="host",
        )

        started = time.perf_counter()

        try:
            if self.copy_workspace:
                with tempfile.TemporaryDirectory(
                    prefix="hagar-dev-"
                ) as temporary:
                    run_cwd = Path(temporary) / "workspace"
                    self._copy_workspace(source_cwd, run_cwd)
                    result = self._execute(
                        recipe,
                        argv,
                        run_cwd,
                        stdin_data,
                        started,
                    )
            else:
                result = self._execute(
                    recipe,
                    argv,
                    source_cwd,
                    stdin_data,
                    started,
                )

        except Exception as exc:
            self._record(
                "dev.run.error",
                recipe=recipe.name,
                error=str(exc),
            )
            raise

        self._record(
            "dev.run.result",
            recipe=recipe.name,
            exit_code=result.exit_code,
            success=result.success,
            timed_out=result.timed_out,
            duration_ms=result.duration_ms,
            backend=result.backend,
        )

        return result

    def _resolve_cwd(self, recipe: DevRecipe) -> Path:
        try:
            target = self.fs.resolve_path(recipe.cwd)
        except Exception as exc:
            raise DevExecutionError(
                f"invalid recipe cwd: {recipe.cwd}"
            ) from exc

        if not target.is_dir():
            raise DevExecutionError("recipe cwd is not a directory")

        return target

    def _copy_workspace(self, source: Path, destination: Path) -> None:
        if not source.is_dir():
            raise DevExecutionError("workspace is not a directory")

        if source == source.parent:
            raise DevExecutionError("refusing to copy a filesystem root")

        def ignore(directory, names):
            ignored = set()
            for name in names:
                if name in {
                    ".git",
                    "__pycache__",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".ruff_cache",
                    "build",
                    "dist",
                    ".tox",
                }:
                    ignored.add(name)
            return ignored

        try:
            shutil.copytree(
                source,
                destination,
                ignore=ignore,
                symlinks=False,
            )
        except OSError as exc:
            raise DevExecutionError(
                f"cannot copy workspace: {exc}"
            ) from exc

    def _execute(
        self,
        recipe: DevRecipe,
        argv: tuple[str, ...],
        cwd: Path,
        stdin_data: bytes | None,
        started: float,
    ) -> DevResult:

        env = self._environment(cwd, recipe.env)

        creationflags = 0
        start_new_session = False

        if os.name == "nt":
            creationflags = getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0,
            )
        else:
            start_new_session = True

        try:
            process = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=env,
                stdin=(
                    subprocess.PIPE
                    if stdin_data is not None
                    else subprocess.DEVNULL
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                creationflags=creationflags,
                start_new_session=start_new_session,
            )
        except OSError as exc:
            raise DevExecutionError(
                f"cannot start recipe: {exc}"
            ) from exc

        timed_out = False

        try:
            stdout, stderr = process.communicate(
                input=stdin_data,
                timeout=recipe.timeout,
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_tree(process)
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()

        duration = round(
            (time.perf_counter() - started) * 1000,
            1,
        )
        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        truncated = False
        if len(stdout_text) > self.max_output_chars:
            stdout_text = stdout_text[: self.max_output_chars]
            truncated = True
        if len(stderr_text) > self.max_output_chars:
            stderr_text = stderr_text[: self.max_output_chars]
            truncated = True

        artifact_id = None
        if truncated and self.artifact_store is not None:
            ref = self.artifact_store.put_text(
                (
                    "STDOUT\n" + stdout_text
                    + "\n\nSTDERR\n" + stderr_text
                ),
                owner="dev",
            )
            artifact_id = ref.artifact_id

        exit_code = None if timed_out else process.returncode
        success = (
            not timed_out
            and exit_code in recipe.success_codes
        )

        if timed_out:
            self._record(
                "dev.run.timeout",
                recipe=recipe.name,
                timeout=recipe.timeout,
            )

        return DevResult(
            recipe=recipe.name,
            exit_code=exit_code,
            success=success,
            timed_out=timed_out,
            duration_ms=duration,
            stdout=stdout_text,
            stderr=stderr_text,
            truncated=truncated,
            artifact_id=artifact_id,
        )

    @staticmethod
    def _kill_tree(process: subprocess.Popen) -> None:
        if os.name == "nt":
            subprocess.run(
                [
                    "taskkill",
                    "/F",
                    "/T",
                    "/PID",
                    str(process.pid),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            try:
                os.killpg(
                    os.getpgid(process.pid),
                    signal.SIGKILL,
                )
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    process.kill()
                except OSError:
                    pass

    @staticmethod
    def _environment(
        cwd: Path,
        recipe_env: dict[str, str],
    ) -> dict[str, str]:
        env = {
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "TMP": str(cwd),
            "TEMP": str(cwd),
        }

        for key in (
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "PATHEXT",
        ):
            value = os.environ.get(key)
            if value:
                env[key] = value

        env.update(recipe_env)
        return env

    def _record(self, event: str, **fields: Any) -> None:
        if self.audit is not None:
            self.audit.record(event, **fields)


def _hash_argv(argv: tuple[str, ...]) -> str:
    import hashlib

    return hashlib.sha256(
        "\0".join(argv).encode("utf-8")
    ).hexdigest()[:16]
