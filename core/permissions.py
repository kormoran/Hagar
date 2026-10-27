from pathlib import Path

class PermissionManager:

    def __init__(self, allowed_paths):
        self.allowed_paths = [
            p.resolve()
            for p in allowed_paths
        ]

    def is_allowed(self, path: Path) -> bool:

        path = path.resolve()

        for allowed in self.allowed_paths:
            try:
                path.relative_to(allowed)
                return True
            except ValueError:
                pass

        return False