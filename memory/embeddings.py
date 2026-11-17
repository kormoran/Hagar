"""Motore di embedding dedicato, separato dal modello di chat."""

from __future__ import annotations

import importlib.util
import hashlib
import math
import os
import threading

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Sequence

from core.models import EmbeddingConfig


class EmbeddingError(RuntimeError):
    pass


class EmbeddingUnavailable(EmbeddingError):
    pass


def default_embedding_cache() -> Path:

    import os

    if os.name == "nt":
        base = Path(
            os.environ.get("LOCALAPPDATA")
            or Path.home() / "AppData" / "Local"
        )
    else:
        base = Path(
            os.environ.get("XDG_CACHE_HOME")
            or Path.home() / ".cache"
        )

    return base / "Hagar" / "embedding-models"


E5_MODEL = "intfloat/multilingual-e5-small"
E5_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
E5_SHA256 = {
    "model.onnx": (
        "4654c156f3e4171abc9c716cdb771bf9116455d15ac1aab364aeeede0e3205b0"
    ),
    "tokenizer.json": (
        "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"
    ),
}
E5_FILES = {
    "model.onnx": "onnx/model_O4.onnx",
    "tokenizer.json": "onnx/tokenizer.json",
}


@dataclass(frozen=True, slots=True)
class OnnxModelManifest:
    """Descrizione dichiarativa di un modello ONNX supportato."""

    name: str
    revision: str
    dimensions: int
    files: dict[str, str]
    checksums: dict[str, str]
    pooling: str = "mean"
    output: str = "token"
    preset: str | None = None


E5_MANIFEST = OnnxModelManifest(
    name=E5_MODEL,
    revision=E5_REVISION,
    dimensions=384,
    files=E5_FILES,
    checksums=E5_SHA256,
    pooling="mean",
    output="token",
    preset="e5-small",
)


def build_manifest(config: EmbeddingConfig) -> OnnxModelManifest:

    preset = config.preset

    if preset is None and config.model == E5_MODEL:
        preset = "e5-small"

    if preset not in {None, "e5-small"}:
        raise EmbeddingError(
            f"unknown embedding preset: {preset}"
        )

    base = E5_MANIFEST if preset == "e5-small" else None
    files = config.files or (base.files if base else None)
    checksums = (
        config.model_sha256
        or (base.checksums if base else None)
    )
    revision = config.revision or (base.revision if base else None)

    if not files:
        raise EmbeddingError(
            "embedding.files is required for a custom model"
        )

    if not {"model.onnx", "tokenizer.json"} <= set(files):
        raise EmbeddingError(
            "embedding.files must define model.onnx and "
            "tokenizer.json"
        )

    if not checksums:
        raise EmbeddingError(
            "embedding.checksums is required for a custom model"
        )

    if not revision:
        raise EmbeddingError(
            "embedding.revision is required for a custom model"
        )

    if set(checksums) != set(files):
        raise EmbeddingError(
            "embedding.checksums must cover every file"
        )

    pooling = config.pooling or (base.pooling if base else "mean")
    output = config.output or (base.output if base else "token")

    if pooling not in {"mean", "cls"}:
        raise EmbeddingError(
            "embedding.pooling must be 'mean' or 'cls'"
        )

    if output not in {"token", "pooled"}:
        raise EmbeddingError(
            "embedding.output must be 'token' or 'pooled'"
        )

    return OnnxModelManifest(
        name=config.model,
        revision=revision,
        dimensions=int(config.dimensions),
        files=dict(files),
        checksums=dict(checksums),
        pooling=pooling,
        output=output,
        preset=preset,
    )


class OnnxProvider:
    """Provider ONNX generico; ``e5-small`` è il preset predefinito."""

    MODEL_REVISION = E5_REVISION

    MODEL_FILES = {
        "model.onnx": "model_O4.onnx",
        "tokenizer.json": "tokenizer.json",
    }

    MODEL_SHA256 = E5_SHA256

    def __init__(
        self,
        config: EmbeddingConfig,
    ) -> None:

        self.config = config
        self.manifest = build_manifest(config)
        self._session: Any = None
        self._tokenizer: Any = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:

        return (
            importlib.util.find_spec("onnxruntime")
            is not None
            and importlib.util.find_spec("tokenizers")
            is not None
            and importlib.util.find_spec("numpy") is not None
        )

    @property
    def loaded(self) -> bool:

        return self._session is not None

    def _cache_dir(self) -> Path:

        root = (
            Path(self.config.cache_dir)
            if self.config.cache_dir
            else default_embedding_cache()
        )
        name = self.config.model.replace("/", "--")
        return root / name

    @staticmethod
    def _sha256(path: Path) -> str:

        digest = hashlib.sha256()

        with path.open("rb") as handle:

            for chunk in iter(
                lambda: handle.read(1024 * 1024),
                b"",
            ):
                digest.update(chunk)

        return digest.hexdigest()

    def _verify(
        self,
        path: Path,
        local_name: str,
    ) -> None:

        expected = (
            (self.config.model_sha256 or {}).get(local_name)
            or self.manifest.checksums.get(local_name)
        )

        if not expected:
            raise EmbeddingError(
                f"no checksum configured for {local_name}"
            )

        actual = self._sha256(path)

        if actual != expected:
            raise EmbeddingError(
                f"embedding model checksum mismatch for "
                f"{local_name}: expected {expected}, got {actual}"
            )

    def _download(
        self,
        url: str,
        path: Path,
        local_name: str,
    ) -> None:

        if path.is_file() and path.stat().st_size > 0:

            try:
                self._verify(path, local_name)
                return
            except EmbeddingError:
                path.unlink(missing_ok=True)

        import requests

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")

        try:

            with requests.get(
                url,
                stream=True,
                timeout=120,
            ) as response:

                response.raise_for_status()

                with temporary.open("wb") as handle:

                    for chunk in response.iter_content(
                        chunk_size=1024 * 1024
                    ):
                        if chunk:
                            handle.write(chunk)

            self._verify(temporary, local_name)
            os.replace(temporary, path)

        finally:

            temporary.unlink(missing_ok=True)

    def load(self) -> tuple[Any, Any]:

        if self._session is not None:
            return self._session, self._tokenizer

        with self._lock:

            if self._session is not None:
                return self._session, self._tokenizer

            if not self.available:

                raise EmbeddingUnavailable(
                    "onnxruntime and tokenizers are not installed; "
                    "install hagar[embedding]"
                )

            try:

                import onnxruntime
                from tokenizers import Tokenizer

            except Exception as exc:

                raise EmbeddingUnavailable(
                    f"cannot import ONNX Runtime/tokenizers: {exc}"
                ) from exc

            cache = self._cache_dir()

            try:

                for local_name, remote_path in (
                    self.manifest.files.items()
                ):

                    self._download(
                        "https://huggingface.co/"
                        f"{self.manifest.name}/resolve/"
                        f"{self.manifest.revision}/{remote_path}",
                        cache / local_name,
                        local_name,
                    )

                self._tokenizer = Tokenizer.from_file(
                    str(cache / "tokenizer.json")
                )
                self._tokenizer.enable_truncation(
                    max_length=int(self.config.max_length)
                )
                self._tokenizer.enable_padding(
                    pad_id=(
                        self._tokenizer.token_to_id("<pad>")
                        if self._tokenizer.token_to_id("<pad>")
                        is not None
                        else 0
                    ),
                    pad_token="<pad>",
                )
                self._session = onnxruntime.InferenceSession(
                    str(cache / "model.onnx"),
                    providers=["CPUExecutionProvider"],
                )

            except Exception as exc:

                self._session = None
                self._tokenizer = None

                raise EmbeddingUnavailable(
                    "cannot load embedding model "
                    f"{self.config.model}: {exc}"
                ) from exc

            return self._session, self._tokenizer

    def embed(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:

        import numpy as np

        session, tokenizer = self.load()
        encodings = tokenizer.encode_batch(list(texts))

        input_ids = np.array(
            [encoding.ids for encoding in encodings],
            dtype=np.int64,
        )
        attention = np.array(
            [
                encoding.attention_mask
                for encoding in encodings
            ],
            dtype=np.int64,
        )

        feed = {
            "input_ids": input_ids,
            "attention_mask": attention,
        }
        input_names = {
            item.name for item in session.get_inputs()
        }

        if not {"input_ids", "attention_mask"} <= input_names:
            raise EmbeddingError(
                "ONNX model must accept input_ids and "
                "attention_mask"
            )

        if "token_type_ids" in input_names:
            feed["token_type_ids"] = np.zeros_like(input_ids)

        try:

            output = session.run(None, feed)[0]

        except Exception as exc:

            raise EmbeddingError(
                f"embedding failed: {exc}"
            ) from exc

        output = np.asarray(output)

        if self.manifest.output == "pooled":

            if output.ndim != 2:
                raise EmbeddingError(
                    "embedding output is not pooled: "
                    f"shape {output.shape}"
                )

            pooled = output

        else:

            if output.ndim != 3:
                raise EmbeddingError(
                    "embedding output is not token-level: "
                    f"shape {output.shape}"
                )

            if self.manifest.pooling == "cls":
                pooled = output[:, 0, :]
            else:
                mask = attention[..., None].astype(np.float32)
                masked = output * mask
                pooled = masked.sum(axis=1) / np.maximum(
                    mask.sum(axis=1),
                    1,
                )

        return [
            [float(value) for value in vector]
            for vector in pooled
        ]


OnnxE5Provider = OnnxProvider


class EmbeddingEngine:
    """Motore stabile: stessa istanza e stesso modello per tutta la sessione."""

    def __init__(
        self,
        config: EmbeddingConfig,
        *,
        provider: Any = None,
    ) -> None:

        self.config = config
        self.provider = provider or OnnxE5Provider(config)
        self._lock = threading.Lock()

    @property
    def dimensions(self) -> int:

        return int(self.config.dimensions)

    @property
    def key(self) -> str:
        """Chiave stabile per non mescolare provider/revisioni."""

        manifest = getattr(self.provider, "manifest", None)

        if manifest is None:
            return self.config.model

        if (
            manifest.preset == "e5-small"
            and self.config.model == E5_MODEL
            and self.config.revision in {None, E5_REVISION}
        ):
            return E5_MODEL

        return (
            f"{self.config.provider}:"
            f"{manifest.name}@{manifest.revision}"
        )

    def _decorate(
        self,
        text: str,
        prefix: str,
    ) -> str:

        value = text.strip()

        if not value:
            raise EmbeddingError("cannot embed an empty text")

        if prefix and not value.startswith(prefix):
            return prefix + value

        return value

    def _normalize(
        self,
        vector: list[float],
    ) -> list[float]:

        if not self.config.normalize:
            return vector

        norm = math.sqrt(
            sum(value * value for value in vector)
        )

        if norm <= 0:
            return vector

        return [value / norm for value in vector]

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:

        prepared = [
            self._decorate(text, self.config.document_prefix)
            for text in texts
        ]

        return self._embed_prepared(prepared)

    def _embed_prepared(
        self,
        prepared: Sequence[str],
    ) -> list[list[float]]:

        if not prepared:
            return []

        with self._lock:

            vectors = self.provider.embed(prepared)

        if len(vectors) != len(prepared):

            raise EmbeddingError(
                "embedding count mismatch: "
                f"{len(vectors)} != {len(prepared)}"
            )

        result = []

        for vector in vectors:

            if len(vector) != self.dimensions:

                raise EmbeddingError(
                    "embedding dimension mismatch: "
                    f"{len(vector)} != {self.dimensions}"
                )

            result.append(self._normalize(vector))

        return result

    def embed_query(
        self,
        text: str,
    ) -> list[float]:

        prepared = self._decorate(
            text,
            self.config.query_prefix,
        )

        return self._embed_prepared([prepared])[0]

    def status(self) -> dict[str, Any]:

        return {
            "enabled": bool(self.config.enabled),
            "provider": self.config.provider,
            "preset": getattr(
                getattr(self.provider, "manifest", None),
                "preset",
                self.config.preset,
            ),
            "model": self.config.model,
            "revision": getattr(
                getattr(self.provider, "manifest", None),
                "revision",
                self.config.revision,
            ),
            "dimensions": self.dimensions,
            "pooling": getattr(
                getattr(self.provider, "manifest", None),
                "pooling",
                self.config.pooling,
            ),
            "output": getattr(
                getattr(self.provider, "manifest", None),
                "output",
                self.config.output,
            ),
            "available": bool(
                getattr(self.provider, "available", False)
            ),
            "loaded": bool(
                getattr(self.provider, "loaded", False)
            ),
            "cache_dir": str(
                self.config.cache_dir
                or default_embedding_cache()
            ),
        }
