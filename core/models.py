from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ModelConfig:
    """
    Configurazione del backend LLM.

    ``host`` è la base URL del provider: per Ollama vale
    ``http://localhost:11434``, per gli altri il default dell'API. Le
    chiavi non stanno nel file di configurazione: ``api_key_env`` indica
    quale variabile d'ambiente leggere, se il nome predefinito non va
    bene.
    """

    provider: str
    name: str
    host: str | None = None
    max_tokens: int = 1024
    api_key_env: str | None = None
    native_tools: bool = True


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
    network: bool = False


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
    max_bytes: int = 5_000_000
    include_outputs: bool = True
    max_files: int = 100


@dataclass(slots=True)
class PolicyConfig:
    """
    File delle policy e soggetto usato dall'agente corrente.

    ``path`` relativo viene risolto rispetto alla directory del file di
    configurazione. Se il file non è leggibile, il harness degrada a
    DENY totale.
    """

    path: Path = Path("policy.yaml")
    subject: str = "assistant"


@dataclass(slots=True)
class MemoryConfig:
    """
    Memoria su vault Obsidian.

    ``enabled`` richiede che ``vault.path`` esista: in caso contrario la
    memoria viene disattivata con un avviso, senza fermare il harness.
    """

    enabled: bool = True
    vault_subdir: str = "Hagar"
    context_turns: int = 10
    context_skills: int = 3
    max_skill_chars: int = 4000


@dataclass(slots=True)
class MCPOAuthConfig:
    """
    Parametri del flusso OAuth interattivo per un server MCP.

    Con ``client_id`` assente si tenta la registrazione dinamica presso
    l'authorization server. Il token cache è un file locale con permessi
    ristretti; se assente si usa ``~/.hagar/oauth/<namespace>.json``.
    """

    authorization_server: str | None = None
    client_id: str | None = None
    client_secret_env: str | None = None
    scopes: list[str] = field(default_factory=list)
    redirect_port: int = 8765
    token_cache: Path | None = None
    timeout: int = 300


@dataclass(slots=True)
class MCPAuthConfig:
    """
    Autenticazione verso un server MCP.

    ``type`` è ``bearer``, ``header`` o ``oauth``. Per bearer/header il
    token si legge dalla variabile d'ambiente ``token_env``; per oauth i
    parametri stanno in ``oauth``.
    """

    type: str
    token_env: str | None = None
    header: str = "Authorization"
    oauth: MCPOAuthConfig | None = None


@dataclass(slots=True)
class MCPServerConfig:
    endpoint: str
    namespace: str
    auth: MCPAuthConfig | None = None


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

    policy: PolicyConfig = field(
        default_factory=PolicyConfig
    )

    memory: MemoryConfig = field(
        default_factory=MemoryConfig
    )
