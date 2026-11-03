from __future__ import annotations

import json

from dataclasses import asdict

from .tool_definition import (
    ToolDefinition,
    ToolParameter,
)
from .tool_registry import ToolRegistry
from .filesystem import FileSystemSandbox
from .permissions import Capability


class FileSystemToolProvider:

    def __init__(
        self,
        filesystem: FileSystemSandbox,
    ) -> None:

        self.fs = filesystem

    def register_tools(
        self,
        registry: ToolRegistry,
    ) -> None:

        registry.register(
            ToolDefinition(
                name="filesystem.read_file",
                capabilities=Capability.FILESYSTEM_READ,
                description=(
                    "Read a UTF-8 text file "
                    "from the sandbox."
                ),
                category="filesystem",
                parameters=[
                    ToolParameter(
                        name="path",
                        param_type="string",
                        description=(
                            "Path of the file "
                            "to read."
                        ),
                    )
                ],
                handler=self.read_file,
            )
        )

        registry.register(
            ToolDefinition(
                name="filesystem.write_file",
                capabilities=Capability.FILESYSTEM_WRITE,
                description=(
                    "Write content to an "
                    "existing file."
                ),
                category="filesystem",
                parameters=[
                    ToolParameter(
                        name="path",
                        param_type="string",
                        description="Target file.",
                    ),
                    ToolParameter(
                        name="content",
                        param_type="string",
                        description=(
                            "Content to write."
                        ),
                    ),
                ],
                handler=self.write_file,
            )
        )

        registry.register(
            ToolDefinition(
                name="filesystem.create_file",
                capabilities=Capability.FILESYSTEM_CREATE,
                description=(
                    "Create a new file."
                ),
                category="filesystem",
                parameters=[
                    ToolParameter(
                        name="path",
                        param_type="string",
                        description=(
                            "New file path."
                        ),
                    ),
                    ToolParameter(
                        name="content",
                        param_type="string",
                        description=(
                            "Initial content."
                        ),
                        required=False,
                        default="",
                    ),
                ],
                handler=self.create_file,
            )
        )

        registry.register(
            ToolDefinition(
                name="filesystem.mkdir",
                capabilities=Capability.FILESYSTEM_CREATE,
                description=(
                    "Create a directory."
                ),
                category="filesystem",
                parameters=[
                    ToolParameter(
                        name="path",
                        param_type="string",
                        description=(
                            "Directory path."
                        ),
                    ),
                ],
                handler=self.mkdir,
            )
        )

        registry.register(
            ToolDefinition(
                name="filesystem.chdir",
                capabilities=Capability.FILESYSTEM_READ,
                description=(
                    "Change current working "
                    "directory."
                ),
                category="filesystem",
                parameters=[
                    ToolParameter(
                        name="path",
                        param_type="string",
                        description=(
                            "Directory path."
                        ),
                    ),
                ],
                handler=self.chdir,
            )
        )

        registry.register(
            ToolDefinition(
                name="filesystem.delete_file",
                capabilities=Capability.FILESYSTEM_DELETE,
                description=(
                    "Delete a file."
                ),
                category="filesystem",
                parameters=[
                    ToolParameter(
                        name="path",
                        param_type="string",
                        description=(
                            "File to remove."
                        ),
                    ),
                ],
                handler=self.delete_file,
            )
        )

        registry.register(
            ToolDefinition(
                name="filesystem.free_space",
                capabilities=Capability.FILESYSTEM_READ,
                description=(
                    "Return free disk space."
                ),
                category="filesystem",
                parameters=[],
                handler=self.free_space,
            )
        )

        registry.register(
            ToolDefinition(
                name="filesystem.stat",
                capabilities=Capability.FILESYSTEM_READ,
                description=(
                    "Return metadata for a path: "
                    "type (file/directory), size in "
                    "bytes, creation/modification/access "
                    "timestamps and the effective sandbox "
                    "permissions. A missing path returns "
                    "exists=false."
                ),
                category="filesystem",
                parameters=[
                    ToolParameter(
                        name="path",
                        param_type="string",
                        description=(
                            "Path to inspect, relative to "
                            "the current sandbox directory "
                            "(e.g. 'notes.txt')."
                        ),
                    )
                ],
                handler=self.stat,
            )
        )

    # ==========================================
    # Tool handlers
    # ==========================================

    def read_file(
        self,
        path: str,
    ) -> str:

        return self.fs.read_file(path)

    def write_file(
        self,
        path: str,
        content: str,
    ) -> str:

        self.fs.write_file(
            path,
            content,
        )

        return (
            f"File written successfully: "
            f"{path}"
        )

    def create_file(
        self,
        path: str,
        content: str = "",
    ) -> str:

        self.fs.create_file(
            path,
            content,
        )

        return (
            f"File created successfully: "
            f"{path}"
        )

    def mkdir(
        self,
        path: str,
    ) -> str:

        self.fs.mkdir(path)

        return (
            f"Directory created: {path}"
        )

    def chdir(
        self,
        path: str,
    ) -> str:

        self.fs.chdir(path)

        return (
            "Current directory changed "
            f"to {self.fs.current_directory}"
        )

    def delete_file(
        self,
        path: str,
    ) -> str:

        self.fs.delete_file(path)

        return (
            f"File deleted: {path}"
        )

    def free_space(
        self,
    ) -> str:

        return str(
            self.fs.free_space()
        )

    def stat(
        self,
        path: str,
    ) -> str:
        """
        Restituisce i metadati come JSON: il modello legge struttura e
        unità senza doverle dedurre da una stringa libera.
        """

        return json.dumps(
            asdict(
                self.fs.stat(path)
            ),
            ensure_ascii=False,
            indent=2,
        )