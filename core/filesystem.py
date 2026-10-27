# core/filesystem.py

from __future__ import annotations

import shutil

from pathlib import Path
from dataclasses import dataclass


@dataclass(slots=True)
class DirectoryPermissions:

    read: bool | None = None
    write: bool | None = None
    create: bool | None = None


class FileSystemSandbox:

    def __init__(
        self,
        roots: dict[Path, DirectoryPermissions],
        current_directory: Path,
    ) -> None:

        self.roots = {
            p.resolve(): perms
            for p, perms in roots.items()
        }

        self.current_directory = (
            current_directory.resolve()
        )

    # ==================================================
    # Internal helpers
    # ==================================================

    def _resolve_path(
        self,
        path: str | Path | None,
    ) -> Path:

        if path is None:
            return self.current_directory

        path = Path(path)

        # percorso relativo → relativo alla current_directory
        if not path.is_absolute():
            path = self.current_directory / path

        return path.resolve()

    def _effective_permissions(
        self,
        path: Path,
    ) -> DirectoryPermissions:

        path = path.resolve()

        matches = []

        for root, perms in self.roots.items():

            root = root.resolve()

            try:
                path.relative_to(root)
                matches.append((root, perms))

            except ValueError:
                pass

        if not matches:
            raise PermissionError(
                f"Path outside sandbox: {path}"
            )

        matches.sort(
            key=lambda item: len(item[0].parts)
        )

        effective = DirectoryPermissions(
            read=True,
            write=False,
            create=False,
        )

        for _, perms in matches:

            if perms.read is not None:
                effective.read = perms.read

            if perms.write is not None:
                effective.write = perms.write

            if perms.create is not None:
                effective.create = perms.create

        return effective
    
    def _find_root(
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
    # Guardian
    # ==================================================

    def FS_Guardian(
        self,
        operation: str,
        target: Path,
        required_space: int = 0,
    ) -> str:

        try:
            permissions = self._effective_permissions(
                target
            )

        except PermissionError:
            return (
                f"Access denied: "
                f"{target} is outside "
                f"allowed directories."
            )
        permissions = self._effective_permissions(
            target
        )
        
        if operation == "read":

            if not permissions.read:
                return (
                    f"Read access denied: "
                    f"{target}"
                )

        elif operation == "write":

            if not permissions.write:
                return (
                    f"Write access denied: "
                    f"{target}"
                )

        elif operation == "create":

            if not permissions.create:
                return (
                    f"Create access denied: "
                    f"{target}"
                )

        free_space = shutil.disk_usage(
            target.parent
        ).free

        if free_space < required_space:

            return (
                f"Insufficient disk space. "
                f"Required={required_space} "
                f"bytes, "
                f"Available={free_space} bytes."
            )

        return ""

    # ==================================================
    # Directory operations
    # ==================================================

    def chdir(
        self,
        path: str | Path,
    ) -> None:

        target = self._resolve_path(path)

        error = self.FS_Guardian(
            "read",
            target,
        )

        if error:
            raise PermissionError(error)

        if not target.is_dir():
            raise FileNotFoundError(
                target
            )

        self.current_directory = target

    def mkdir(
        self,
        path: str | Path,
    ) -> None:

        target = self._resolve_path(path)

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

    # ==================================================
    # File operations
    # ==================================================

    def read_file(
        self,
        path: str | Path,
    ) -> str:

        target = self._resolve_path(path)

        error = self.FS_Guardian(
            "read",
            target,
        )

        if error:
            raise PermissionError(error)

        return target.read_text(
            encoding="utf-8"
        )

    def write_file(
        self,
        path: str | Path,
        content: str,
    ) -> None:

        target = self._resolve_path(path)

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

        target.write_text(
            content,
            encoding="utf-8",
        )

    def create_file(
        self,
        path: str | Path,
        content: str = "",
    ) -> None:

        target = self._resolve_path(path)

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

            raise FileExistsError(
                target
            )

        target.write_text(
            content,
            encoding="utf-8",
        )

    # ==================================================
    # Disk information
    # ==================================================

    def free_space(self) -> int:

        usage = shutil.disk_usage(
            self.current_directory
        )

        return usage.free