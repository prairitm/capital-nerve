"""Embedding providers for document-page vector indexing.

Mirrors the isolation pattern in `pipeline/llm.py`: callers use
`get_embedding_provider()` and never import OpenAI directly elsewhere.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    name: str

    @property
    def is_available(self) -> bool: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class MockEmbeddingProvider:
    """No-op provider — vector indexing is skipped; RAG uses FTS-only retrieval."""

    name = "mock:none"

    @property
    def is_available(self) -> bool:
        return False

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("Mock embedding provider cannot embed texts.")


class OpenAIEmbeddingProvider:
    def __init__(self, *, model: str, api_key: str) -> None:
        from openai import OpenAI  # type: ignore

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.name = f"openai:{model}"

    @property
    def is_available(self) -> bool:
        return True

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self._model, input=texts)
        ordered = sorted(resp.data, key=lambda row: row.index)
        return [row.embedding for row in ordered]


def get_embedding_provider() -> EmbeddingProvider:
    provider_name = (settings.EMBEDDING_PROVIDER or "mock").lower()
    if provider_name == "openai":
        api_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            if settings.is_production:
                raise RuntimeError(
                    "EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY in production."
                )
            logger.warning(
                "EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is not set; skipping vectors."
            )
            return MockEmbeddingProvider()
        return OpenAIEmbeddingProvider(model=settings.EMBEDDING_MODEL, api_key=api_key)
    return MockEmbeddingProvider()
