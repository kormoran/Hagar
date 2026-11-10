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
    timeout: int = 120
    api_key_env: str | None = None
    native_tools: bool = True


@dataclass(slots=True)
class VaultConfig:
    path: Path


@dataclass(slots=True)
class SandboxMount:
    """
    Una radice della sandbox, esposta all'agente come
    ``/home/ai/<alias>``.

    ``permissions`` è la stringa canonica composta da ``R``, ``W``, ``X``.
    """

    alias: str
    path: Path
    permissions: str = "R"


@dataclass(slots=True)
class FileSystemLimits:
    """
    Budget di scrittura della sandbox.

    ``0`` disabilita il singolo limite. I byte sono cumulativi per
    sessione del ``FileSystemSandbox``.
    """

    max_write_bytes: int = 0
    min_free_bytes: int = 0
    session_write_bytes: int = 0
    ask_over_bytes: int = 0


@dataclass(slots=True)
class FileSystemConfig:
    sandbox: list[SandboxMount]
    limits: FileSystemLimits = field(
        default_factory=FileSystemLimits
    )


@dataclass(slots=True)
class PermissionConfig:
    read: bool
    write: bool
    shell: bool
    network: bool = False
    agents: bool = False


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
    Memoria persistente.

    ``backend=sqlite`` usa un database locale come fonte di verità.
    ``backend=markdown`` mantiene il vecchio Vault per compatibilità.
    """

    enabled: bool = True
    backend: str = "sqlite"
    database: str | None = None
    vault_subdir: str = "Hagar"
    context_turns: int = 10
    context_skills: int = 3
    max_skill_chars: int = 4000
    context_project_memories: int = 10
    max_context_chars: int = 6000
    project_max_active: int = 200
    summary_max_chars: int = 4000


@dataclass(slots=True)
class DecisionProviderConfig:
    """Provider di decisione: LLM oppure classificatore lineare locale."""

    name: str
    type: str = "llm"
    path: str | None = None
    model: str | None = None


@dataclass(slots=True)
class DecisionsConfig:
    enabled: bool = True
    default: str = "llm"
    providers: list[DecisionProviderConfig] = field(
        default_factory=list
    )


@dataclass(slots=True)
class HiFiConfig:
    """Pre-pass di disambiguazione della richiesta utente."""

    enabled: bool = False
    margin: float = 0.20
    interpretations: int = 3


@dataclass(slots=True)
class ToolsConfig:
    """Limiti runtime per l'esecuzione dei tool."""

    timeout: float | None = 120.0
    repeat_limit: int = 3


@dataclass(slots=True)
class DevConfig:
    """Ricette locali per test, debug e build."""

    enabled: bool = False
    recipes: str = "recipes.yaml"
    copy_workspace: bool = True
    max_output_chars: int = 100_000


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
    audience: str | None = None
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

    decisions: DecisionsConfig = field(
        default_factory=DecisionsConfig
    )

    hifi: HiFiConfig = field(
        default_factory=HiFiConfig
    )

    tools: ToolsConfig = field(
        default_factory=ToolsConfig
    )

    dev: DevConfig = field(
        default_factory=DevConfig
    )
