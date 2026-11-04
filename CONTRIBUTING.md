# Contributing to Hagar

Hagar is a small, synchronous Python harness. Changes should stay
readable and should not turn the project into a framework.

## Development setup

Python 3.11 or newer is required.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
./tools/run_tests.sh
```

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
.\tools\run_tests.ps1
```

The Windows runner also puts `tools/pytest_shim` on `PYTHONPATH`. The
shim only works around a restricted-token issue with `tmp_path`; it is
not needed in normal CI.

Live tests are excluded by default:

```bash
./tools/run_tests.sh --live
```

They need a local Ollama server and, optionally, provider API keys. Do
not add tests that require network access to the default suite.

## What to change

- Keep the synchronous, single-agent design. Do not introduce asyncio
  or a plugin runtime without a design discussion first.
- New local tools belong in `local_tools/`, not `core/`.
- The model never receives host filesystem paths. Virtual paths are
  always POSIX under `/home/ai/<alias>`.
- A new tool must declare capabilities and a policy namespace.
- A filesystem or memory write must have a failure path that is visible
  in the audit log, not silently swallowed.

## Documentation

The maintained documentation is **`Docs/it`**. `Docs/en` and the
top-level English `README.md` are frozen: the maintainer regenerates
them from the Italian version before a release. Do not edit them in a
normal pull request.

## Tests

- Add a regression test for every bug fix.
- Run the full suite on at least one Unix platform and on Windows when
  the change touches paths, symlinks, permissions or the CLI.
- Do not commit `hagar.yaml`, `testvault/`, `logs/` or OAuth token
  caches.

## Pull requests

Keep commits focused. Describe:

- the problem;
- the chosen behavior;
- what is deliberately out of scope;
- the tests you ran and on which platform.

Security issues go through `SECURITY.md`, not a public pull request.
