"""Tool per aprire immagini dalla sandbox come allegati del modello."""

from __future__ import annotations

from core.filesystem import FileSystemSandbox
from core.images import ImageInput
from core.images import MAX_IMAGE_BYTES
from core.permissions import Capability
from core.tool_definition import ToolDefinition
from core.tool_definition import ToolParameter
from core.tool_registry import ToolRegistry
from core.tool_result import ToolResult


class VisionToolProvider:
    """Registra ``vision.open`` sul sandbox dell'agente."""

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
                name="vision.open",
                description=(
                    "Load a PNG, JPEG or WebP image from the sandbox "
                    "and attach it to the conversation so the model "
                    "can see it."
                ),
                category="vision",
                capabilities=Capability.FILESYSTEM_READ,
                parameters=[
                    ToolParameter(
                        name="path",
                        param_type="string",
                        description=(
                            "Image path in the sandbox."
                        ),
                    )
                ],
                handler=self.open_image,
            )
        )

    def open_image(
        self,
        path: str,
    ) -> ToolResult:

        data = self.fs.read_bytes(
            path,
            max_bytes=MAX_IMAGE_BYTES,
        )
        image = ImageInput.from_bytes(data)
        virtual = self.fs.virtual_path(
            self.fs.resolve_path(path)
        )

        return ToolResult(
            tool_name="vision.open",
            success=True,
            output=(
                f"Image loaded: {virtual} "
                f"({image.mime_type}, {len(image.data)} bytes)"
            ),
            images=(image,),
        )
