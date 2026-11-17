"""Motore di embedding dedicato, separato dal modello di chat."""

from __future__ import annotations

import importlib.util
import hashlib
import math
import os
import threading

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


class OnnxE5Provider:
    """ONNX Runtime diretto per intfloat/multilingual-e5-small."""

    MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

    MODEL_FILES = {
        "model.onnx": "model_O4.onnx",
        "tokenizer.json": "tokenizer.json",
    }

    MODEL_SHA256 = {
        "model.onnx": (
            "4654c156f3e4171abc9c716cdb771bf9116455d15ac1aab364aeeede0e3205b0"
        ),
        "tokenizer.json": (
            "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"
        ),
    }

    def __init__(
        self,
        config: EmbeddingConfig,
    ) -> None:

        self.config = config
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
            or self.MODEL_SHA256.get(local_name)
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

                for local_name, remote_name in self.MODEL_FILES.items():

                    self._download(
                        "https://huggingface.co/"
                        f"{self.config.model}/resolve/"
                        f"{self.MODEL_REVISION}/onnx/{remote_name}",
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

        if "token_type_ids" in input_names:
            feed["token_type_ids"] = np.zeros_like(input_ids)

        try:

            output = session.run(None, feed)[0]

        except Exception as exc:

            raise EmbeddingError(
                f"embedding failed: {exc}"
            ) from exc

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
            "model": self.config.model,
            "dimensions": self.dimensions,
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
