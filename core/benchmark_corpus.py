"""Corpus fisso e verificato per i benchmark."""

from __future__ import annotations

import hashlib
import os

from pathlib import Path
from typing import Any

import yaml


class BenchmarkCorpusError(RuntimeError):
    pass


def default_corpus_root() -> Path:

    override = os.environ.get("HAGAR_BENCHMARK_CORPUS")

    if override:
        return Path(override)

    repo_path = (
        Path(__file__).resolve().parent.parent
        / "benchmarks"
        / "corpus"
    )

    if repo_path.is_dir():
        return repo_path

    try:
        import benchmarks

        package_path = Path(benchmarks.__file__).parent / "corpus"

        if package_path.is_dir():
            return package_path

    except (ImportError, OSError, TypeError):
        pass

    return repo_path


def _sha256(path: Path) -> str:

    return hashlib.sha256(path.read_bytes()).hexdigest()


class BenchmarkCorpus:
    """Legge testi, reference e immagini dal manifest."""

    def __init__(
        self,
        root: str | Path,
        manifest: dict[str, Any],
    ) -> None:

        self.root = Path(root)
        self.manifest = manifest
        self.texts = self._entries("texts")
        self.references = self._entries("references")
        self.images = self._entries("images")
        self.quality = self._list("quality")
        self.vision = self._list("vision")
        self._validate()

    @classmethod
    def load(
        cls,
        root: str | Path | None = None,
    ) -> "BenchmarkCorpus":

        path = Path(root or default_corpus_root())
        manifest_path = path / "manifest.yaml"

        if not manifest_path.is_file():
            raise BenchmarkCorpusError(
                f"benchmark corpus manifest not found: "
                f"{manifest_path}"
            )

        try:
            payload = yaml.safe_load(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, yaml.YAMLError) as exc:
            raise BenchmarkCorpusError(
                f"cannot read benchmark corpus: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise BenchmarkCorpusError(
                "benchmark corpus manifest must be a mapping"
            )

        if payload.get("version") != 1:
            raise BenchmarkCorpusError(
                "unsupported benchmark corpus version"
            )

        return cls(path, payload)

    @property
    def suite_name(self) -> str:
        return str(self.manifest.get("suite") or "unknown")

    def text(self, sample_id: str) -> str:

        entry = self.texts.get(sample_id)

        if entry is None:
            raise BenchmarkCorpusError(
                f"unknown text sample: {sample_id}"
            )

        return self._resolve(entry["path"]).read_text(
            encoding="utf-8"
        )

    def reference(self, reference_id: str) -> str:

        entry = self.references.get(reference_id)

        if entry is None:
            raise BenchmarkCorpusError(
                f"unknown translation reference: {reference_id}"
            )

        return self._resolve(entry["path"]).read_text(
            encoding="utf-8"
        )

    def image(self, image_id: str) -> bytes:

        entry = self.images.get(image_id)

        if entry is None:
            raise BenchmarkCorpusError(
                f"unknown image sample: {image_id}"
            )

        return self._resolve(entry["path"]).read_bytes()

    def _entries(
        self,
        key: str,
    ) -> dict[str, dict[str, Any]]:

        entries = {}

        for entry in self._list(key):

            if not isinstance(entry, dict):
                raise BenchmarkCorpusError(
                    f"{key} entries must be mappings"
                )

            sample_id = entry.get("id")

            if not isinstance(sample_id, str) or not sample_id.strip():
                raise BenchmarkCorpusError(
                    f"{key} entry without id"
                )

            if sample_id in entries:
                raise BenchmarkCorpusError(
                    f"duplicate sample id: {sample_id}"
                )

            entries[sample_id] = entry

        return entries

    def _list(self, key: str) -> list[Any]:

        value = self.manifest.get(key, [])

        if not isinstance(value, list):
            raise BenchmarkCorpusError(
                f"manifest.{key} must be a list"
            )

        return value

    def _resolve(self, relative: Any) -> Path:

        if not isinstance(relative, str) or not relative.strip():
            raise BenchmarkCorpusError(
                "sample path must be a non-empty string"
            )

        path = (self.root / relative).resolve()
        root = self.root.resolve()

        if root != path and root not in path.parents:
            raise BenchmarkCorpusError(
                f"sample path escapes corpus: {relative}"
            )

        if not path.is_file():
            raise BenchmarkCorpusError(
                f"sample not found: {relative}"
            )

        return path

    def _validate(self) -> None:

        for group in (
            self.texts,
            self.references,
            self.images,
        ):
            for sample_id, entry in group.items():

                path = self._resolve(entry.get("path"))
                expected = entry.get("sha256")

                if not isinstance(expected, str) or not expected:
                    raise BenchmarkCorpusError(
                        f"missing sha256 for {sample_id}"
                    )

                actual = _sha256(path)

                if actual != expected:
                    raise BenchmarkCorpusError(
                        f"sha256 mismatch for {sample_id}"
                    )

        for case in self.quality:

            if not isinstance(case, dict):
                raise BenchmarkCorpusError(
                    "quality cases must be mappings"
                )

            sample = case.get("sample")

            if sample not in self.texts:
                raise BenchmarkCorpusError(
                    f"quality case references unknown text: {sample}"
                )

            reference = case.get("reference")

            if reference is not None and reference not in self.references:
                raise BenchmarkCorpusError(
                    "quality case references unknown translation "
                    f"reference: {reference}"
                )

        for case in self.vision:

            if not isinstance(case, dict):
                raise BenchmarkCorpusError(
                    "vision cases must be mappings"
                )

            image = case.get("image")

            if image not in self.images:
                raise BenchmarkCorpusError(
                    f"vision case references unknown image: {image}"
                )
