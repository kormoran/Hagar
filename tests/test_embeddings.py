"""Test del motore di embedding dedicato."""

from __future__ import annotations

import pytest

from core.config import ConfigLoader
from core.models import EmbeddingConfig
from memory.embeddings import EmbeddingEngine
from memory.embeddings import EmbeddingError


class FakeProvider:
    available = True
    loaded = True

    def __init__(self):
        self.texts = []

    def embed(self, texts):
        self.texts.extend(texts)
        return [
            [1.0, 0.0, 0.0, 0.0]
            for _ in texts
        ]


def test_engine_uses_query_and_document_prefixes():
    provider = FakeProvider()
    engine = EmbeddingEngine(
        EmbeddingConfig(
            enabled=True,
            dimensions=4,
            query_prefix="query: ",
            document_prefix="passage: ",
        ),
        provider=provider,
    )

    engine.embed_documents(["documento"])
    engine.embed_query("domanda")

    assert provider.texts == [
        "passage: documento",
        "query: domanda",
    ]

    assert engine.embed_documents(["altro"])[0] == [
        1.0,
        0.0,
        0.0,
        0.0,
    ]


def test_engine_normalizes_vectors():
    class Unnormalized:
        available = True
        loaded = True

        def embed(self, texts):
            return [[3.0, 4.0]]

    engine = EmbeddingEngine(
        EmbeddingConfig(
            enabled=True,
            dimensions=2,
            normalize=True,
            document_prefix="",
            query_prefix="",
        ),
        provider=Unnormalized(),
    )

    vector = engine.embed_documents(["x"])[0]

    assert vector == pytest.approx([0.6, 0.8])


def test_engine_rejects_wrong_dimensions():
    class Wrong:
        available = True
        loaded = True

        def embed(self, texts):
            return [[1.0, 2.0]]

    engine = EmbeddingEngine(
        EmbeddingConfig(
            enabled=True,
            dimensions=4,
            document_prefix="",
        ),
        provider=Wrong(),
    )

    with pytest.raises(EmbeddingError, match="dimension"):
        engine.embed_documents(["x"])


def test_embedding_config_section(tmp_path):
    path = tmp_path / "hagar.yaml"
    path.write_text(
        """
model:
  provider: ollama
  name: test
vault:
  path: .
filesystem:
  sandbox:
    - alias: workspace
      path: .
policy:
  path: policy.yaml
embedding:
  enabled: true
  model: intfloat/multilingual-e5-small
  dimensions: 384
  batch_size: 8
  normalize: false
""",
        encoding="utf-8",
    )

    cfg = ConfigLoader.load(path)

    assert cfg.embedding.enabled is True
    assert cfg.embedding.model == "intfloat/multilingual-e5-small"
    assert cfg.embedding.dimensions == 384
    assert cfg.embedding.batch_size == 8
    assert cfg.embedding.normalize is False
    assert cfg.embedding.provider == "builtin"
