from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ModelConfig:
    """
    Configurazione del backend LLM.

    ``host`` serve solo a Ollama (default localhost). Le chiavi API non
    stanno nel file di configurazione: ``api_key_env`` indica quale
    variabile d'ambiente leggere, se il nome predefinito non va bene.
    """

    provider: str
    name: str
    host: str | None = None
    max_tokens: int = 1024
    api_key_env: str | None = None


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
class AuditConfig:
    """
    Configurazione dell'audit log.

    ``path`` relativo viene risolto rispetto alla directory del file di
    configurazione, non alla directory di lavoro.
    """

    enabled: bool = True
    path: Path = Path("logs/audit.jsonl")
    max_field_chars: int = 2000


@dataclass(slots=True)
class MCPServerConfig:
    endpoint: str
    namespace: str


@dataclass(slots=True)
class AppConfig:
    model: ModelConfig
    vault: VaultConfig
    filesystem: FileSystemConfig
    permissions: PermissionConfig
    rag: RagConfig
    mcp_servers: list[MCPServerConfig] = field(
        default_factory=list
    )
    audit: AuditConfig = field(
        default_factory=AuditConfig
    )


@dataclass
class PolicyRule:

    subject: str

    capability: str

    resource: str

    action: PolicyAction