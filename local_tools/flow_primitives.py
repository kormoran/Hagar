"""Primitive interne del DSL flow."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from core.boxes import BoxRunner
from core.permissions import Capability
from core.tool_definition import ToolDefinition, ToolParameter
from core.tool_registry import ToolRegistry


class FlowPrimitiveProvider:

    def __init__(
        self,
        filesystem,
        box_runner: BoxRunner | None = None,
        memory=None,
        project_store=None,
        project_id_getter=None,
    ) -> None:

        self.fs = filesystem
        self.box_runner = box_runner
        self.memory = memory
        self.project_store = project_store
        self.project_id_getter = project_id_getter
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

        if self.memory is not None:

            self._register(
                registry,
                name="memory.search",
                description="Cerca nella memoria e nell'indice.",
                parameters=[
                    ToolParameter("query", "string", "Testo da cercare."),
                    ToolParameter(
                        "kind",
                        "string",
                        "Filtro opzionale.",
                        required=False,
                        default="",
                    ),
                    ToolParameter(
                        "status",
                        "string",
                        "Filtro opzionale.",
                        required=False,
                        default="",
                    ),
                    ToolParameter(
                        "limit",
                        "integer",
                        "Numero massimo di risultati.",
                        required=False,
                        default=10,
                    ),
                ],
                capabilities=Capability.MEMORY_READ,
                policy_namespace="search",
                handler=self.memory_search,
            )

            self._register(
                registry,
                name="memory.context",
                description="Legge i turni recenti o cercati.",
                parameters=[
                    ToolParameter(
                        "limit",
                        "integer",
                        "Numero massimo di turni.",
                        required=False,
                        default=5,
                    ),
                    ToolParameter(
                        "query",
                        "string",
                        "Ricerca testuale.",
                        required=False,
                        default="",
                    ),
                    ToolParameter(
                        "session",
                        "string",
                        "Sessione opzionale.",
                        required=False,
                        default="",
                    ),
                ],
                capabilities=Capability.MEMORY_READ,
                policy_namespace="chat",
                handler=self.memory_context,
            )

            self._register(
                registry,
                name="memory.skill",
                description="Legge una skill completa per id.",
                parameters=[
                    ToolParameter(
                        "skill_id",
                        "string",
                        "Id della skill.",
                    )
                ],
                capabilities=Capability.MEMORY_READ,
                policy_namespace="skills",
                handler=self.memory_skill,
            )

        if self.project_store is not None:

            self._register(
                registry,
                name="project.context",
                description="Legge le decisioni del progetto attivo.",
                parameters=[
                    ToolParameter(
                        "query",
                        "string",
                        "Filtro opzionale.",
                        required=False,
                        default="",
                    ),
                    ToolParameter(
                        "limit",
                        "integer",
                        "Numero massimo di decisioni.",
                        required=False,
                        default=10,
                    ),
                ],
                capabilities=Capability.MEMORY_READ,
                policy_namespace="projects",
                handler=self.project_context,
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
        policy_namespace: str | None = None,
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
                policy_namespace=policy_namespace,
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
    # Memory
    # --------------------------------------------------

    def memory_search(
        self,
        query: str,
        kind: str = "",
        status: str = "",
        limit: int = 10,
    ) -> list[dict]:

        query = query.strip()

        if not query:
            raise ValueError("query is required")

        results = self.memory.index.search(
            query,
            kind=kind or None,
            status=status or None,
            limit=_clamp(limit, 10, 50),
        )

        # Il backend Markdown usa kind="skill"; SQLite usa fact/procedure.
        # Normalizza i filtri delle skill solo per il backend legacy.
        legacy_markdown = not hasattr(self.memory, "database")

        if (
            not results
            and legacy_markdown
            and kind in {"skill", "fact", "procedure"}
        ):
            results = self.memory.index.search(
                query,
                kind=None,
                status=status or None,
                limit=_clamp(limit, 10, 50),
            )
            results = [
                item
                for item in results
                if "skills/" in str(item.get("path", ""))
            ]

        for item in results:
            path = item.get("path")

            if isinstance(path, str) and "skills/" in path:
                item["id"] = Path(path).stem

        return results

    def memory_context(
        self,
        limit: int = 5,
        query: str = "",
        session: str = "",
    ) -> list[dict]:

        amount = _clamp(limit, 5, 50)
        session_id = session.strip() or None
        query_text = query.strip()

        if query_text:
            turns = self.memory.search_turns(
                query_text,
                limit=amount,
                session=session_id,
            )
        else:
            turns = self.memory.recent_turns(
                limit=amount,
                session=session_id,
            )

        return [turn.as_dict() for turn in turns]

    def memory_skill(self, skill_id: str) -> dict | None:

        value = skill_id.strip()

        if value.endswith(".md") or "/" in value or "\\" in value:
            value = Path(value).stem

        skill = self.memory.get_skill(value)

        if skill is None:
            return None

        return {
            **skill.summary(),
            "content": skill.content,
        }

    def project_context(
        self,
        query: str = "",
        limit: int = 10,
    ) -> list[dict]:

        project_id = (
            self.project_id_getter()
            if self.project_id_getter is not None
            else None
        )

        if not project_id:
            raise ValueError("nessun progetto attivo")

        amount = _clamp(limit, 10, 50)
        query_text = query.strip()

        if query_text:
            decisions = self.project_store.search_decisions(
                project_id,
                query_text,
                limit=amount,
            )
        else:
            decisions = self.project_store.list_decisions(
                project_id,
                status="active",
                limit=amount,
            )

        return [
            {
                **item.summary(),
                "decision": item.decision,
                "alternatives": list(item.alternatives),
                "rationale": item.rationale,
            }
            for item in decisions
        ]

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


def _clamp(value, default: int, maximum: int) -> int:
    if value is None or isinstance(value, bool):
        number = default
    else:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default

    return max(1, min(number, maximum))
