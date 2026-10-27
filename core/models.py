from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ModelConfig:
    provider: str
    host: str
    name: str


@dataclass(slots=True)
class VaultConfig:
    path: Path


@dataclass(slots=True)
class FileSystemConfig:
    allowed: list[Path]


@dataclass(slots=True)
class PermissionConfig:
    read: bool
    write: bool
    shell: bool


@dataclass(slots=True)
class RagConfig:
    top_k: int


@dataclass(slots=True)
class AppConfig:
    model: ModelConfig
    vault: VaultConfig
    filesystem: FileSystemConfig
    permissions: PermissionConfig
    rag: RagConfig