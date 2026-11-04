# core/filesystem.py

from __future__ import annotations

import os
import shutil
import stat as stat_module

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class DirectoryPermissions:
    """
    Permessi applicabili a una radice della sandbox.

    ``None`` significa "eredita dalla radice più esterna": i valori
    impostati da una radice più specifica sovrascrivono quelli ereditati.
    """

    read: bool | None = None
    write: bool | None = None
    create: bool | None = None
    rename: bool | None = None
    delete: bool | None = None
    execute: bool | None = None


@dataclass(slots=True)
class FileInfo:
    """
    Metadati di un percorso, nella prospettiva della sandbox.

    ``permissions`` non riflette le ACL del sistema operativo (che
    l'agente non deve conoscere) ma i permessi effettivi concessi dalla
    configurazione del harness per quel percorso.
    """

    path: str
    exists: bool
    kind: str | None = None
    size_bytes: int | None = None
    created_at: str | None = None
    modified_at: str | None = None
    accessed_at: str | None = None
    permissions: dict[str, bool] = field(
        default_factory=dict
    )


def _iso_timestamp(seconds: float) -> str:
    """Timestamp ISO 8601 nel fuso locale, con offset esplicito."""

    return datetime.fromtimestamp(
        seconds,
        tz=timezone.utc,
    ).astimezone().isoformat(timespec="seconds")


def _permissions_dict(
    permissions: DirectoryPermissions,
) -> dict[str, bool]:

    return {
        "read": bool(permissions.read),
        "write": bool(permissions.write),
        "create": bool(permissions.create),
        "rename": bool(permissions.rename),
        "delete": bool(permissions.delete),
        "execute": bool(permissions.execute),
    }


class FileSystemSandbox:
    """
    Filesystem virtuale dell'agente.

    L'agente non vede mai percorsi reali: ogni richiesta viene risolta
    rispetto alla directory corrente, verificata contro le radici concesse
    e filtrata dai permessi effettivi.

    La radice virtuale del sandbox è ``/home/ai``. Ogni directory
    configurata è esposta come ``/home/ai/<alias>``: non esistono volumi
    o directory intermedie sintetiche. Tutti i percorsi restituiti dai
    tool sono virtuali, indipendentemente dal sistema operativo.
    """

    VIRTUAL_ROOT = "/home/ai"

    def __init__(
        self,
        roots: dict[Path, DirectoryPermissions],
        current_directory: Path,
        aliases: dict[str, Path] | None = None,
    ) -> None:

        self.roots = {
            p.resolve(): perms
            for p, perms in roots.items()
        }

        self.current_directory = (
            current_directory.resolve()
        )

        if aliases is None:

            aliases = {
                (
                    "root"
                    if len(self.roots) == 1
                    else f"root{index}"
                ): root
                for index, root in enumerate(self.roots)
            }

        if not aliases:

            raise ValueError(
                "FileSystemSandbox requires at least one alias"
            )

        self.aliases = {
            alias: Path(path).resolve()
            for alias, path in aliases.items()
        }

        self._alias_lookup = {
            alias.casefold(): alias
            for alias in self.aliases
        }

        self.alias_by_root: dict[Path, str] = {}

        for alias, root in self.aliases.items():

            if root not in self.roots:

                raise ValueError(
                    f"Alias {alias!r} points outside roots"
                )

            self.alias_by_root[root] = alias

        self.virtual_root = self.VIRTUAL_ROOT

    # ==================================================
    # Path helpers
    # ==================================================

    def is_virtual_root(
        self,
        path: str | Path | None,
    ) -> bool:

        if path is None:
            return False

        raw = str(path).replace("\\", "/").rstrip("/")

        return raw == self.VIRTUAL_ROOT

    def resolve_path(
        self,
        path: str | Path | None,
    ) -> Path:

        if path is None:
            return self.current_directory

        raw = str(path).replace("\\", "/")

        if (
            raw == self.VIRTUAL_ROOT
            or raw.startswith(self.VIRTUAL_ROOT + "/")
        ):

            relative = raw[len(self.VIRTUAL_ROOT):].lstrip("/")

            if not relative:

                raise PermissionError(
                    f"{self.VIRTUAL_ROOT} is virtual; "
                    "choose an alias"
                )

            alias, _, suffix = relative.partition("/")

            canonical = self._alias_lookup.get(
                alias.casefold()
            )

            if canonical is None:

                raise PermissionError(
                    f"Unknown sandbox alias: {alias}"
                )

            root = self.aliases[canonical]

            target = (root / suffix).resolve() if suffix else root

            if (
                target != root
                and root not in target.parents
            ):

                raise PermissionError(
                    "Virtual path escapes its alias"
                )

            return target

        path = Path(path)

        if not path.is_absolute():
            path = self.current_directory / path

        return path.resolve()

    def virtual_path(
        self,
        path: str | Path,
    ) -> str:
        """
        Percorso mostrato all'agente: ``/home/ai/<alias>/...``.

        Non restituisce mai il percorso fisico della sandbox.
        """

        target = self.resolve_path(path)

        candidates = [
            (root, alias)
            for root, alias in self.alias_by_root.items()
            if (
                target == root
                or root in target.parents
            )
        ]

        if not candidates:

            raise PermissionError(
                "Path outside configured aliases"
            )

        root, alias = max(
            candidates,
            key=lambda item: len(item[0].parts),
        )

        relative = target.relative_to(root)

        if str(relative) == ".":
            return f"{self.VIRTUAL_ROOT}/{alias}"

        return (
            f"{self.VIRTUAL_ROOT}/{alias}/"
            f"{relative.as_posix()}"
        )

    def _display(
        self,
        path: Path,
    ) -> str:
        """Percorso sicuro per i messaggi d'errore."""

        try:
            return self.virtual_path(path)

        except Exception:
            return "outside sandbox"

    def parent_path(
        self,
        path: str | Path,
    ) -> Path:

        return self.resolve_path(path).parent

    def path_exists(
        self,
        path: str | Path,
    ) -> bool:

        return self.resolve_path(path).exists()

    def contains_symlink(
        self,
        path: str | Path,
    ) -> bool:

        target = self.resolve_path(path)

        current = Path(target.anchor)

        for part in target.parts[1:]:

            current /= part

            try:
                if current.is_symlink():
                    return True
            except OSError:
                pass

        return False

    # ==================================================
    # Permission helpers
    # ==================================================

    def effective_permissions(
        self,
        path: Path,
    ) -> DirectoryPermissions:

        path = path.resolve()

        matches: list[
            tuple[Path, DirectoryPermissions]
        ] = []

        for root, perms in self.roots.items():

            root = root.resolve()

            try:
                path.relative_to(root)
                matches.append((root, perms))

            except ValueError:
                pass

        if not matches:

            raise PermissionError(
                "Path outside sandbox"
            )

        #
        # Dalla radice più esterna alla più interna:
        # la più specifica vince.
        #

        matches.sort(
            key=lambda item: len(item[0].parts)
        )

        effective = DirectoryPermissions(
            read=True,
            write=False,
            create=False,
            rename=False,
            delete=False,
            execute=False,
        )

        for _, perms in matches:

            if perms.read is not None:
                effective.read = perms.read

            if perms.write is not None:
                effective.write = perms.write

            if perms.create is not None:
                effective.create = perms.create

            if perms.rename is not None:
                effective.rename = perms.rename

            if perms.delete is not None:
                effective.delete = perms.delete

            if perms.execute is not None:
                effective.execute = perms.execute

        return effective

    def find_root(
        self,
        path: Path,
    ) -> tuple[Path, DirectoryPermissions] | None:

        for root, perms in self.roots.items():

            try:
                path.relative_to(root)
                return root, perms

            except ValueError:
                continue

        return None

    # ==================================================
    # Disk helpers
    # ==================================================

    def check_disk_space(
        self,
        target: Path,
        required_space: int,
    ) -> str | None:

        candidate = target.parent

        while (
            not candidate.exists()
            and candidate != candidate.parent
        ):
            candidate = candidate.parent

        free_space = shutil.disk_usage(
            candidate
        ).free

        if free_space < required_space:

            return (
                f"Insufficient disk space. "
                f"Required={required_space} bytes, "
                f"Available={free_space} bytes."
            )

        return None

    # ==================================================
    # Legacy guardian
    #
    # Da rimuovere quando sarà introdotto
    # PermissionEvaluator.
    # ==================================================

    def FS_Guardian(
        self,
        operation: str,
        target: Path,
        required_space: int = 0,
    ) -> str:
        """
        Restituisce stringa vuota se l'operazione è concessa,
        altrimenti il messaggio di diniego.
        """

        try:
            permissions = (
                self.effective_permissions(
                    target
                )
            )

        except PermissionError:

            return (
                f"Access denied: "
                f"{self._display(target)} is outside "
                f"allowed directories. Use a path "
                f"relative to the current sandbox "
                f"directory."
            )

        if self.contains_symlink(target):

            return (
                f"Access denied: "
                f"path '{self._display(target)}' "
                f"contains a symbolic link."
            )

        if operation == "read":

            if not permissions.read:

                return (
                    f"Read access denied: "
                    f"{self._display(target)}"
                )

        elif operation == "write":

            if not permissions.write:

                return (
                    f"Write access denied: "
                    f"{self._display(target)}"
                )

        elif operation == "create":

            if not permissions.create:

                return (
                    f"Create access denied: "
                    f"{self._display(target)}"
                )

        elif operation == "rename":

            if not permissions.rename:

                return (
                    f"Rename access denied: "
                    f"{self._display(target)}"
                )

        elif operation == "delete":

            if not permissions.delete:

                return (
                    f"Delete access denied: "
                    f"{self._display(target)}"
                )

        elif operation == "execute":

            if not permissions.execute:

                return (
                    f"Enter access denied: "
                    f"{self._display(target)}"
                )

        disk_error = self.check_disk_space(
            target,
            required_space,
        )

        if disk_error:
            return disk_error

        return ""

    # ==================================================
    # Directory operations
    # ==================================================

    def chdir(
        self,
        path: str | Path,
    ) -> None:

        if self.is_virtual_root(path):

            raise PermissionError(
                f"{self.VIRTUAL_ROOT} is virtual; "
                "choose an alias"
            )

        target = self.resolve_path(path)

        error = self.FS_Guardian(
            "execute",
            target,
        )

        if error:
            raise PermissionError(error)

        if not target.is_dir():
            raise FileNotFoundError(self._display(target))

        self.current_directory = target

    def mkdir(
        self,
        path: str | Path,
    ) -> None:

        target = self.resolve_path(path)

        error = self.FS_Guardian(
            "create",
            target,
        )

        if error:
            raise PermissionError(error)

        target.mkdir(
            parents=True,
            exist_ok=True,
        )

    def list_dir(
        self,
        path: str | Path = ".",
    ) -> list[FileInfo]:

        if self.is_virtual_root(path):

            entries: list[FileInfo] = []

            for alias in sorted(
                self.aliases,
                key=str.casefold,
            ):

                try:
                    entries.append(
                        self.stat(self.aliases[alias])
                    )

                except PermissionError:
                    continue

            return entries

        target = self.resolve_path(path)

        error = self.FS_Guardian(
            "read",
            target,
        )

        if error:
            raise PermissionError(error)

        if not target.exists():
            raise FileNotFoundError(self._display(target))

        if not target.is_dir():
            raise NotADirectoryError(self._display(target))

        entries: list[FileInfo] = []

        for entry in sorted(
            target.iterdir(),
            key=lambda p: (
                not p.is_dir(),
                p.name.lower(),
            ),
        ):
            entries.append(
                self.stat(entry)
            )
        return entries


    # ==================================================
    # File operations
    # ==================================================


    def search(
        self,
        pattern: str,
        path: str | Path = ".",
        max_results: int = 1000,
    ) -> dict:

        if not isinstance(pattern, str) or not pattern.strip():

            raise ValueError(
                "pattern must be a non-empty string"
            )

        pattern_path = Path(pattern)

        if pattern_path.is_absolute() or ".." in pattern_path.parts:

            raise ValueError(
                "pattern must stay inside the sandbox"
            )

        max_results = max(
            1,
            min(int(max_results), 5000),
        )

        if self.is_virtual_root(path):

            results: list[FileInfo] = []
            total_matches = 0

            for alias in sorted(
                self.aliases,
                key=str.casefold,
            ):

                try:
                    partial = self.search(
                        pattern,
                        self.aliases[alias],
                        max_results,
                    )

                except (
                    PermissionError,
                    FileNotFoundError,
                    NotADirectoryError,
                ):
                    continue

                total_matches += partial["total_matches"]

                for item in partial["results"]:

                    if len(results) < max_results:
                        results.append(item)

            return {
                "pattern": pattern,
                "searched_path": self.VIRTUAL_ROOT,
                "total_matches": total_matches,
                "returned_matches": len(results),
                "truncated": total_matches > max_results,
                "results": results,
            }

        target = self.resolve_path(path)

        error = self.FS_Guardian(
            "read",
            target,
        )

        if error:
            raise PermissionError(error)

        if not target.exists():
            raise FileNotFoundError(self._display(target))

        if not target.is_dir():
            raise NotADirectoryError(self._display(target))

        results: list[FileInfo] = []

        total_matches = 0

        for entry in sorted(
            target.rglob(pattern),
            key=lambda p: str(p).lower(),
        ):

            total_matches += 1

            if len(results) >= max_results:
                continue

            try:

                results.append(
                    self.stat(entry)
                )

            except (PermissionError, OSError):
                continue

        return {
            "pattern": pattern,
            "searched_path": self.virtual_path(target),
            "total_matches": total_matches,
            "returned_matches": len(results),
            "truncated": (
                total_matches > max_results
            ),
            "results": results,
        }


    def read_chunk(
        self,
        path: str | Path,
        offset: int = 0,
        length: int = 4096,
    ) -> dict:

        if offset < 0:

            raise ValueError(
                "offset must be >= 0"
            )

        if length <= 0:

            raise ValueError(
                "length must be > 0"
            )

        length = min(int(length), 1_048_576)

        target = self.resolve_path(path)

        error = self.FS_Guardian(
            "read",
            target,
        )

        if error:
            raise PermissionError(error)

        if not target.is_file():
            raise FileNotFoundError(self._display(target))

        file_size = target.stat().st_size

        with open(
            target,
            "rb",
        ) as f:

            f.seek(offset)

            data = f.read(length)

        content = data.decode(
            "utf-8",
            errors="replace",
        )

        return {
            "path": self.virtual_path(target),
            "offset": offset,
            "length": len(data),
            "has_more": (
                offset + len(data)
                < file_size
            ),
            "content": content,
        }

    def read_file(
        self,
        path: str | Path,
    ) -> str:

        target = self.resolve_path(path)

        error = self.FS_Guardian(
            "read",
            target,
        )

        if error:
            raise PermissionError(error)

        if not target.is_file():
            raise FileNotFoundError(self._display(target))

        return target.read_text(
            encoding="utf-8"
        )

    def copy_file(
        self,
        source: str | Path,
        destination: str | Path,
    ) -> None:

        src = self.resolve_path(source)
        dst = self.resolve_path(destination)

        error = self.FS_Guardian(
            "read",
            src,
        )

        if error:
            raise PermissionError(error)

        if not src.is_file():
            raise FileNotFoundError(self._display(src))

        required_space = src.stat().st_size

        error = self.FS_Guardian(
            "create",
            dst,
            required_space,
        )

        if error:
            raise PermissionError(error)

        if dst.exists():
            raise FileExistsError(self._display(dst))

        shutil.copy2(
            src,
            dst,
        )
    
    def rename(
        self,
        source: str | Path,
        destination: str | Path,
    ) -> None:
        """
        Rinomina o sposta un file.

        Questa implementazione verifica soltanto il permesso
        "rename" sul percorso sorgente.

        In futuro potrebbe essere opportuno introdurre una
        versione più rigorosa che richieda anche il permesso
        "create" sulla destinazione, impedendo ad esempio
        uno spostamento verso directory in cui la creazione
        di nuovi file non sarebbe normalmente consentita.
        """

        src = self.resolve_path(source)
        dst = self.resolve_path(destination)

        error = self.FS_Guardian(
            "rename",
            src,
        )

        if error:
            raise PermissionError(error)

        if not src.exists():
            raise FileNotFoundError(self._display(src))

        error = self.FS_Guardian(
            "create",
            dst,
        )

        if error:
            raise PermissionError(error)

        if dst.exists():
            raise FileExistsError(self._display(dst))

        src.rename(dst)

    def write_file(
        self,
        path: str | Path,
        content: str,
    ) -> None:
        """
        Sovrascrive un file esistente.

        La creazione di un nuovo file richiede il permesso ``create`` e
        passa da :meth:`create_file`: in questo modo non è possibile
        aggirare il divieto di creazione scrivendo un percorso nuovo.
        """

        target = self.resolve_path(path)

        required_space = len(
            content.encode("utf-8")
        )

        error = self.FS_Guardian(
            "write",
            target,
            required_space,
        )

        if error:
            raise PermissionError(error)

        if not target.exists():
            raise FileNotFoundError(self._display(target))

        if target.is_dir():
            raise IsADirectoryError(self._display(target))

        target.write_text(
            content,
            encoding="utf-8",
        )

    def create_file(
        self,
        path: str | Path,
        content: str = "",
    ) -> None:

        target = self.resolve_path(path)

        required_space = len(
            content.encode("utf-8")
        )

        error = self.FS_Guardian(
            "create",
            target,
            required_space,
        )

        if error:
            raise PermissionError(error)

        if target.exists():
            raise FileExistsError(self._display(target))

        if not target.parent.is_dir():
            raise FileNotFoundError(self._display(target.parent))

        target.write_text(
            content,
            encoding="utf-8",
        )

    def delete_file(
        self,
        path: str | Path,
    ) -> None:

        target = self.resolve_path(path)

        error = self.FS_Guardian(
            "delete",
            target,
        )

        if error:
            raise PermissionError(error)

        if not target.exists():
            raise FileNotFoundError(self._display(target))

        if target.is_dir():
            raise IsADirectoryError(self._display(target))

        target.unlink()

    # ==================================================
    # Metadata
    # ==================================================

    def stat(
        self,
        path: str | Path,
    ) -> FileInfo:
        """
        Restituisce tipo, dimensione, date e permessi effettivi.

        Un percorso inesistente non è un errore: ``exists`` è ``False``
        e ``permissions`` riporta comunque ciò che la sandbox
        permetterebbe su quel percorso. Un percorso fuori dalla sandbox
        resta un errore.
        """

        if self.is_virtual_root(path):

            return FileInfo(
                path=self.VIRTUAL_ROOT,
                exists=True,
                kind="directory",
                permissions={
                    "read": True,
                    "write": False,
                    "create": False,
                    "rename": False,
                    "delete": False,
                    "execute": False,
                },
            )

        target = self.resolve_path(path)

        error = self.FS_Guardian(
            "read",
            target,
        )

        if error:
            raise PermissionError(error)

        permissions = _permissions_dict(
            self.effective_permissions(target)
        )

        if not target.exists():

            return FileInfo(
                path=self.virtual_path(target),
                exists=False,
                permissions=permissions,
            )

        info = target.stat()

        if stat_module.S_ISREG(info.st_mode):
            kind = "file"
        elif stat_module.S_ISDIR(info.st_mode):
            kind = "directory"
        else:
            kind = "other"

        #
        # La dimensione di una directory non è una misura utile:
        # dipende dal filesystem.
        #

        size_bytes = (
            info.st_size
            if kind == "file"
            else None
        )

        created = getattr(
            info,
            "st_birthtime",
            None,
        )

        if created is None and os.name == "nt":

            #
            # Su Windows st_ctime è la data di creazione.
            #

            created = info.st_ctime

        return FileInfo(
            path=self.virtual_path(target),
            exists=True,
            kind=kind,
            size_bytes=size_bytes,
            created_at=(
                _iso_timestamp(created)
                if created is not None
                else None
            ),
            modified_at=_iso_timestamp(
                info.st_mtime
            ),
            accessed_at=_iso_timestamp(
                info.st_atime
            ),
            permissions=permissions,
        )

    # ==================================================
    # Disk info
    # ==================================================

    def free_space(self) -> int:

        return shutil.disk_usage(
            self.current_directory
        ).free
