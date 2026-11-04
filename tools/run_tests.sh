#!/usr/bin/env bash
# Esecuzione della suite su Linux/macOS (e Git Bash).
#
# Su Windows usare tools/run_tests.ps1: lo shim per il mode 0o700 serve
# solo con il token ristretto della sandbox DSH.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
elif [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then
    PYTHON="$ROOT/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    PYTHON="python"
fi

export PYTHONDONTWRITEBYTECODE=1

exec "$PYTHON" -m pytest -p no:cacheprovider "$@"
