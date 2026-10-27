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

            permissions = PermissionConfig(
                read=data["permissions"].get(
                    "read",
                    True
                ),
                write=data["permissions"].get(
                    "write",
                    False
                ),
                shell=data["permissions"].get(
                    "shell",
                    False
                ),
            )

            rag = RagConfig(
                top_k=data["rag"].get(
                    "top_k",
                    8
                )
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