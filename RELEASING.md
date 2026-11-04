# Releasing Hagar

This checklist is for the maintainer. It assumes the repository is
`kormoran/Hagar` and that the release is a GitHub release, not a PyPI
publish.

## 1. Prepare

1. Bump the version in **both** places:
   - `pyproject.toml`
   - `hagar.py` (`__version__`)
2. Update `Docs/it/CHANGELOG.md` with the release section.
3. Update `Docs/it/ROADMAP.md` and, if needed, `Docs/it/ARCHITECTURE.md`.
4. Regenerate `Docs/en` and the top-level English `README.md` from the
   Italian sources. They are frozen during normal development.
5. Check `hagar.example.yaml` and `policy.yaml` still describe the
   current configuration.
6. Do not commit `hagar.yaml`, `testvault/`, `logs/` or token caches.

## 2. Verify

```bash
python -m pip install -e ".[dev]"
./tools/run_tests.sh
python -m build
python -m twine check dist/*
```

On Windows:

```powershell
.\tools\run_tests.ps1
```

The GitHub CI matrix runs the suite on Linux, macOS and Windows for
Python 3.11, 3.12 and 3.13. Wait for it to be green.

## 3. Tag

```bash
git status
git tag -a v0.3.0 -m "Hagar 0.3.0"
git push origin main
git push origin v0.3.0
```

The `Release` workflow builds the sdist/wheel and creates the GitHub
release with generated notes.

## 4. After the release

- Verify the release assets and the install command in a clean
  environment.
- Do not move or reuse a published tag.
- Open the next `Non rilasciato` section in the changelog.

## If something goes wrong

Delete the GitHub release and the tag, fix the problem, bump the patch
version if the tag was already public. Never rewrite a tag that users
may have downloaded.
