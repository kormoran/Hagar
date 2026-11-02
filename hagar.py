from core.config import Config

from core.tool_registry import (
    ToolRegistry,
)

from core.agent import (
    Agent,
)

from core.mcp_client import (
    MCPClient,
)

from core.filesystem import (
    FileSystemSandbox,
    DirectoryPermissions,
)

from tools.filesystem_tools import (
    FileSystemToolProvider,
)

from llm.ollama_client import (
    OllamaClient,
)

from memory.vault import (
    Vault,
)

from pathlib import Path


def main():

    # ==========================================
    # Configuration
    # ==========================================

    cfg = Config("config.yaml")

    # ==========================================
    # Filesystem sandbox
    # ==========================================

    sandbox_roots = {
        Path(cfg.workspace_path):
        DirectoryPermissions(
            read=True,
            write=True,
            create=True,
            delete=True,
        )
    }

    filesystem = FileSystemSandbox(
        roots=sandbox_roots,
        current_directory=Path(
            cfg.workspace_path
        ),
    )

    # ==========================================
    # Registry
    # ==========================================

    registry = ToolRegistry()

    # ==========================================
    # Local filesystem tools
    # ==========================================

    fs_provider = (
        FileSystemToolProvider(
            filesystem
        )
    )

    fs_provider.register_tools(
        registry
    )

    # ==========================================
    # MCP servers
    # ==========================================

    for server_cfg in cfg.data.get(
        "mcp_servers",
        [],
    ):

        try:

            mcp = MCPClient(
                endpoint=server_cfg[
                    "endpoint"
                ],
                namespace=server_cfg[
                    "namespace"
                ],
            )

            mcp.register_tools(
                registry
            )

            print(
                "Loaded MCP namespace:",
                server_cfg[
                    "namespace"
                ]
            )

        except Exception as exc:

            print(
                "Failed to load MCP server",
                server_cfg[
                    "namespace"
                ],
                exc,
            )

    # ==========================================
    # LLM
    # ==========================================

    llm = OllamaClient(
        host=cfg.data["model"]["host"],
        model=cfg.data["model"]["model"],
    )

    # ==========================================
    # Vault
    # ==========================================

    vault = Vault(
        cfg.vault_path
    )

    # ==========================================
    # Agent
    # ==========================================

    agent = Agent(
        llm=llm,
        tool_registry=registry,
        vault=vault,
    )

    # ==========================================
    # Console
    # ==========================================

    print()

    print(
        "Harness ready."
    )

    print()

    print(
        "Available tools:"
    )

    for tool in registry.tool_names():

        print(
            f"  - {tool}"
        )

    print()

    while True:

        question = input("> ")

        if (
            question.lower()
            in {"exit", "quit"}
        ):
            break

        answer = agent.ask(
            question
        )

        print()
        print(answer)
        print()


if __name__ == "__main__":
    main()