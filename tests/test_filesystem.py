# core/filesystem.py

from __future__ import annotations

import logging
import shutil

from pathlib import Path
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DirectoryPermissions:
    """
    None = eredita dal padre
    """

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
            Path(root).resolve(): perms
            for root, perms in roots.items()
        }

        self.current_directory = (
            Path(current_directory)
            .resolve()
        )

        self.hidden_paths: set[Path] = set()

        self._scan_for_symlinks()

    # =====================================================
    # Security scan
    # =====================================================

    def _scan_for_symlinks(self) -> None:

        count = 0

        for root in self.roots:

            try:

                for entry in root.rglob("*"):

                    if entry.is_symlink():

                        count += 1

                        self.hidden_paths.add(
                            entry.resolve()
                        )

                        self.hidden_paths.add(
                            entry
                        )

                        message = (
                            f"SECURITY WARNING: "
                            f"symlink hidden "
                            f"from sandbox: {entry}"
                        )

                        logger.warning(message)

                        print(message)

            except Exception as ex:

                logger.warning(
                    "Unable to scan %s : %s",
                    root,
                    ex,
                )

        logger.info(
            "Sandbox initialized. "
            "Hidden symlinks: %d",
            count,
        )

    # =====================================================
    # Paths
    # =====================================================

    def _resolve_path(
        self,
        path: str | Path | None,
    ) -> Path:

        if path is None:
            return self.current_directory

        path = Path(path)

        if not path.is_absolute():
            path = (
                self.current_directory
                / path
            )

        return path.resolve()

    # =====================================================
    # Permissions
    # =====================================================

    def _effective_permissions(
        self,
        path: Path,
    ) -> DirectoryPermissions:

        path = path.resolve()

        matches: list[
            tuple[
                Path,
                DirectoryPermissions
            ]
        ] = []

        for root, perms in self.roots.items():

            try:

                path.relative_to(root)

                matches.append(
                    (
                        root,
                        perms,
                    )
                )

            except ValueError:
                continue

        if not matches:

            raise PermissionError(
                f"Path outside sandbox: {path}"
            )

        matches.sort(
            key=lambda item:
            len(item[0].parts)
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

    # =====================================================
    # Guardian
    # =====================================================

    def FS_Guardian(
        self,
        operation: str,
        target: Path,
        required_space: int = 0,
    ) -> str:

        target = target.resolve()

        if (
            target in self.hidden_paths
            or target.parent
            in self.hidden_paths
        ):
            return (
                "Access denied: "
                "resource hidden "
                "by security policy."
            )

        try:

            permissions = (
                self._effective_permissions(
                    target
                )
            )

        except PermissionError:

            return (
                f"Access denied: "
                f"{target} is outside "
                f"allowed directories."
            )

        if (
            operation == "read"
            and not permissions.read
        ):
            return (
                f"Read access denied: "
                f"{target}"
            )

        if (
            operation == "write"
            and not permissions.write
        ):
            return (
                f"Write access denied: "
                f"{target}"
            )

        if (
            operation == "create"
            and not permissions.create
        ):
            return (
                f"Create access denied: "
                f"{target}"
            )

        try:

            free = shutil.disk_usage(
                target.parent
            ).free

        except FileNotFoundError:

            free = shutil.disk_usage(
                self.current_directory
            ).free

        if free < required_space:

            return (
                "Insufficient disk space. "
                f"Required={required_space} "
                f"Available={free}"
            )

        return ""

    # =====================================================
    # Directory operations
    # =====================================================

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

        self.current_directory = (
            target
        )

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

    # =====================================================
    # File operations
    # =====================================================

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
            encoding="utf-8"
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
            encoding="utf-8"
        )

    # =====================================================
    # Disk info
    # =====================================================

    def free_space(self) -> int:

        return shutil.disk_usage(
            self.current_directory
        ).free