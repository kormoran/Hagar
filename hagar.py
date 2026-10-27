from core.config import Config
from core.permissions import PermissionManager
from core.tool_registry import ToolRegistry
from core.agent import Agent

from llm.ollama_client import OllamaClient

from memory.vault import Vault

from tools.filesystem import FileSystemTools


def main():

    cfg = Config("config.yaml")

    permissions = PermissionManager(
        cfg.allowed_paths
    )

    fs = FileSystemTools(
        permissions
    )

    registry = ToolRegistry()

    registry.register(
        "read_file",
        fs.read_file
    )

    registry.register(
        "list_directory",
        fs.list_directory
    )

    llm = OllamaClient(
        cfg.data["model"]["host"],
        cfg.data["model"]["model"]
    )

    vault = Vault(
        cfg.vault_path
    )

    agent = Agent(
        llm,
        registry,
        vault
    )

    while True:

        question = input("> ")

        if question == "exit":
            break

        answer = agent.ask(
            question
        )

        print(answer)


if __name__ == "__main__":
    main()