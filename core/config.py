from pathlib import Path

import yaml

from .models import (
    AppConfig,
    ModelConfig,
    VaultConfig,
    FileSystemConfig,
    PermissionConfig,
    RagConfig,
)


class ConfigError(RuntimeError):
    pass


class ConfigLoader:

    @staticmethod
    def load(filename: str | Path) -> AppConfig:

        path = Path(filename)

        if not path.exists():
            raise ConfigError(
                f"Configuration file not found: {path}"
            )

        with open(path, "r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp)

        return ConfigLoader._parse(data)
        

    @staticmethod
    def _parse(data: dict) -> AppConfig:

        try:

            model = ModelConfig(
                provider=data["model"]["provider"],
                host=data["model"]["host"],
                name=data["model"]["name"],
            )

            vault = VaultConfig(
                path=Path(
                    data["vault"]["path"]
                ).expanduser()
            )

            filesystem = FileSystemConfig(
                allowed=[
                    Path(p).expanduser()
                    for p in data["filesystem"]["allowed"]
                ]
            )

            # -------------------------
            # Permissions (optional)
            # -------------------------

            permissions_data = data.get(
                "permissions",
                {}
            )

            read = permissions_data.get(
                "read",
                True
            )

            write = permissions_data.get(
                "write",
                False
            )

            shell = permissions_data.get(
                "shell",
                False
            )

            for name, value in {
                "read": read,
                "write": write,
                "shell": shell,
            }.items():

                if not isinstance(value, bool):
                    raise ConfigError(
                        f"permissions.{name} must be a boolean"
                    )

            permissions = PermissionConfig(
                read=read,
                write=write,
                shell=shell,
            )

            # -------------------------
            # RAG (optional)
            # -------------------------

            rag_data = data.get(
                "rag",
                {}
            )

            top_k = rag_data.get(
                "top_k",
                8
            )

            if not isinstance(top_k, int):
                raise ConfigError(
                    "rag.top_k must be an integer"
                )

            if top_k <= 0:
                raise ConfigError(
                    "rag.top_k must be greater than zero"
                )

            rag = RagConfig(
                top_k=top_k
            )

            return AppConfig(
                model=model,
                vault=vault,
                filesystem=filesystem,
                permissions=permissions,
                rag=rag,
            )

        except KeyError as ex:

            raise ConfigError(
                f"Missing configuration key: {ex}"
            ) from ex