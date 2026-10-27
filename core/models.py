from dataclasses import dataclass
from pathlib import Path

@dataclass
class ToolResult:
    success: bool
    content: str

@dataclass
class AgentConfig:
    vault_path: Path
    allowed_paths: list[Path]