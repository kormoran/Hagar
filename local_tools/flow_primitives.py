"""Primitive interne del DSL flow."""

from __future__ import annotations

from dataclasses import asdict

from core.boxes import BoxRunner
from core.permissions import Capability
from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry


class FlowPrimitiveProvider:

    def __init__(
        self,
        filesystem,
        box_runner: BoxRunner | None = None,
    ) -> None:

        self.fs = filesystem
        self.box_runner = box_runner
        self.primitives: set[str] = set()

    def register_tools(self, registry: ToolRegistry) -> None:

        self._register(
            registry,
            name="fs.read",
            description="Legge un file della sandbox.",
            parameters=[ToolParameter("path", "string", "Percorso.")],
            capabilities=Capability.FILESYSTEM_READ,
            handler=self.read,
        )
        self._register(
            registry,
            name="fs.write",
            description="Scrive un file della sandbox.",
            parameters=[
                ToolParameter("path", "string", "Percorso."),
                ToolParameter("text", "string", "Contenuto."),
            ],
            capabilities=(
                Capability.FILESYSTEM_WRITE
                | Capability.FILESYSTEM_CREATE
            ),
            handler=self.write,
        )
        self._register(
            registry,
            name="fs.edit",
            description="Sostituisce testo in un file.",
            parameters=[
                ToolParameter("path", "string", "Percorso."),
                ToolParameter("old", "string", "Testo da sostituire."),
                ToolParameter("new", "string", "Nuovo testo."),
                ToolParameter(
                    "replace_all",
                    "boolean",
                    "Sostituisce tutte le occorrenze.",
                    required=False,
                    default=False,
                ),
            ],
            capabilities=Capability.FILESYSTEM_WRITE,
            handler=self.edit,
        )
        self._register(
            registry,
            name="fs.list",
            description="Elenca i file di una directory.",
            parameters=[
                ToolParameter(
                    "path",
                    "string",
                    "Directory.",
                    required=False,
                    default=".",
                )
            ],
            capabilities=Capability.FILESYSTEM_READ,
            handler=self.list_dir,
        )
        self._register(
            registry,
            name="fs.exists",
            description="Verifica se un percorso esiste.",
            parameters=[ToolParameter("path", "string", "Percorso.")],
            capabilities=Capability.FILESYSTEM_READ,
            handler=self.exists,
        )
        self._register(
            registry,
            name="fs.stat",
            description="Restituisce i metadati di un percorso.",
            parameters=[ToolParameter("path", "string", "Percorso.")],
            capabilities=Capability.FILESYSTEM_READ,
            handler=self.stat,
        )
        self._register(
            registry,
            name="fs.mkdir",
            description="Crea una directory.",
            parameters=[ToolParameter("path", "string", "Percorso.")],
            capabilities=Capability.FILESYSTEM_CREATE,
            handler=self.mkdir,
        )

        if self.box_runner is not None:

            self._register(
                registry,
                name="box.summarize",
                description="Riassume un documento.",
                parameters=[
                    ToolParameter("input", "string", "File di input."),
                    ToolParameter("output", "string", "File di output."),
                    ToolParameter(
                        "style",
                        "string",
                        "short, detailed o bullet.",
                        required=False,
                        default="short",
                    ),
                ],
                capabilities=Capability.BOX_EXEC,
                handler=self.summarize,
            )
            self._register(
                registry,
                name="box.translate",
                description="Traduce un documento.",
                parameters=[
                    ToolParameter("input", "string", "File di input."),
                    ToolParameter("output", "string", "File di output."),
                    ToolParameter(
                        "target",
                        "string",
                        "Lingua di destinazione.",
                        required=False,
                        default="it",
                    ),
                ],
                capabilities=Capability.BOX_EXEC,
                handler=self.translate,
            )
            self._register(
                registry,
                name="box.extract_json",
                description="Estrae un oggetto JSON da un documento.",
                parameters=[
                    ToolParameter("input", "string", "File di input."),
                    ToolParameter("output", "string", "File di output."),
                ],
                capabilities=Capability.BOX_EXEC,
                handler=self.extract_json,
            )

    def _register(
        self,
        registry: ToolRegistry,
        *,
        name: str,
        description: str,
        parameters: list[ToolParameter],
        capabilities: Capability,
        handler,
    ) -> None:

        self.primitives.add(name)
        registry.register(
            ToolDefinition(
                name=name,
                description=description,
                category="flow-primitive",
                parameters=parameters,
                capabilities=capabilities,
                handler=handler,
                origin="flow",
            )
        )

    # --------------------------------------------------
    # Filesystem
    # --------------------------------------------------

    def read(self, path: str) -> str:

        try:
            return self.fs.read_file(path)
        except ValueError as exc:
            if "larger than one chunk" not in str(exc):
                raise

            pieces = []
            offset = 0

            while True:
                payload = self.fs.read_chunk(
                    path,
                    offset=offset,
                    length=65536,
                )
                pieces.append(payload["content"])
                offset = payload["next_offset"]

                if not payload["has_more"]:
                    break

            return "".join(pieces)

    def write(self, path: str, text: str) -> None:

        target = self.fs.resolve_path(path)

        if target.exists():
            self.fs.read_chunk(path, 0, 1)
            self.fs.write_file(path, text)
        else:
            self.fs.create_file(path, text)

    def edit(
        self,
        path: str,
        old: str,
        new: str,
        replace_all: bool = False,
    ) -> int:
        return self.fs.edit_file(
            path,
            old,
            new,
            replace_all=replace_all,
        )

    def list_dir(self, path: str = ".") -> list[str]:
        payload = self.fs.list_dir(path, limit=1000)
        return [
            entry.path
            for entry in payload["entries"]
        ]

    def exists(self, path: str) -> bool:
        return bool(self.fs.stat(path).exists)

    def stat(self, path: str) -> dict:
        return asdict(self.fs.stat(path))

    def mkdir(self, path: str) -> None:
        self.fs.mkdir(path)

    # --------------------------------------------------
    # Box
    # --------------------------------------------------

    def summarize(
        self,
        input: str,
        output: str,
        style: str = "short",
    ) -> None:
        self.box_runner.run(
            "summarize",
            input,
            output,
            {"style": style},
        )

    def translate(
        self,
        input: str,
        output: str,
        target: str = "it",
    ) -> None:
        self.box_runner.run(
            "translate",
            input,
            output,
            {"target": target},
        )

    def extract_json(self, input: str, output: str) -> None:
        self.box_runner.run(
            "extract_json",
            input,
            output,
        )
