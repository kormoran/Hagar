from pathlib import Path

class FileSystemTools:

    def __init__(self, permissions):
        self.permissions = permissions

    def read_file(self, path: str):

        p = Path(path)

        if not self.permissions.is_allowed(p):
            return "ACCESS DENIED"

        return p.read_text(
            encoding="utf8",
            errors="ignore"
        )

    def list_directory(self, path: str):

        p = Path(path)

        if not self.permissions.is_allowed(p):
            return []

        return [
            x.name
            for x in p.iterdir()
        ]