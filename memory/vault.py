# memory/vault.py

from __future__ import annotations

from pathlib import Path


class VaultError(RuntimeError):
    pass


class Vault:
    """
    Accesso minimale a un vault Obsidian.

    Tutti i percorsi sono relativi alla radice del vault e vengono
    risolti verificando che non escano dalla radice stessa.
    """

    def __init__(
        self,
        root: str | Path,
    ) -> None:

        self.root = Path(root)

    def exists(self) -> bool:
        """True se la radice del vault esiste ed è una directory."""

        return self.root.is_dir()

    def _resolve(
        self,
        relative: str | Path,
    ) -> Path:

        root = self.root.resolve()

        candidate = (root / relative).resolve()

        if (
            candidate != root
            and root not in candidate.parents
        ):

            raise VaultError(
                f"Path escapes the vault: {relative}"
            )

        return candidate

    def file_exists(
        self,
        relative: str | Path,
    ) -> bool:

        try:
            return self._resolve(relative).is_file()

        except VaultError:
            return False

    def read(
        self,
        relative: str | Path,
    ) -> str:

        return self._resolve(relative).read_text(
            encoding="utf-8"
        )

    def write(
        self,
        relative: str | Path,
        text: str,
    ) -> Path:

        path = self._resolve(relative)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            text,
            encoding="utf-8",
            newline="\n",
        )

        return path

    def ensure_dir(
        self,
        relative: str | Path,
    ) -> Path:

        path = self._resolve(relative)

        path.mkdir(
            parents=True,
            exist_ok=True,
        )

        return path

    def append(
        self,
        relative: str | Path,
        text: str,
    ) -> Path:

        path = self._resolve(relative)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open(
            "a",
            encoding="utf-8",
            newline="\n",
        ) as handle:

            handle.write(text)

        return path

    def move(
        self,
        relative: str | Path,
        destination: str | Path,
    ) -> Path:

        source = self._resolve(relative)
        target = self._resolve(destination)

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        source.replace(target)

        return target

    def list_files(
        self,
        relative: str | Path = ".",
        pattern: str = "*.md",
    ) -> list[Path]:

        directory = self._resolve(relative)

        if not directory.is_dir():
            return []

        return sorted(
            directory.glob(pattern)
        )

    def markdown_files(self):

        if not self.root.is_dir():
            return []

        return list(
            self.root.rglob("*.md")
        )

    def load_all(self):

        docs = []

        for file in self.markdown_files():

            docs.append({
                "path": str(file),
                "text": file.read_text(
                    encoding="utf8",
                    errors="ignore"
                )
            })

        return docs
