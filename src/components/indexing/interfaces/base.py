"""Indexing interfaces — abstractions for embedding and vector persistence.

The chunker depends only on these ABCs, so Jina can be swapped for
Google Embedding (or OpenSearch for another vector store) without
changing chunking logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..schemas.chunk import ClinicalChunk


class IEmbeddingProvider(ABC):
    """Abstract embedding provider. Implementations wrap a concrete API client."""

    @abstractmethod
    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of passage texts into vectors."""

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """Embed a single search query into a vector."""

    @abstractmethod
    def dimensions(self) -> int:
        """Return the vector dimension of the configured model."""


class IChunkRepository(ABC):
    """Abstract vector/persistent repository for chunks."""

    @abstractmethod
    def ensure_index(self) -> None:
        """Create the target index if it does not exist."""

    @abstractmethod
    def upsert_chunks(self, chunks: list[ClinicalChunk], embeddings: list[list[float]]) -> int:
        """Idempotently upsert chunks with their embeddings. Returns count indexed."""

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        patient_id: str | None = None,
        file_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Vector search filtered by patient_id AND file_id when provided."""
