from pathlib import Path

class Vault:

    def __init__(self, root):
        self.root = Path(root)

    def markdown_files(self):

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