from pathlib import Path
import yaml

class Config:
    def __init__(self, filename: str):
        with open(filename, "r", encoding="utf8") as f:
            self.data = yaml.safe_load(f)

    @property
    def vault_path(self) -> Path:
        return Path(self.data["vault"]["path"])

    @property
    def allowed_paths(self):
        return [Path(p) for p in self.data["filesystem"]["allowed"]]