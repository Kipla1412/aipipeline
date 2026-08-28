"""JinaEmbeddingProvider — adapter over the existing JinaEmbeddingsService.

Reuses the existing JinaConnector + JinaEmbeddingsService from the
embedder package. The chunker and indexer depend only on
IEmbeddingProvider, so this adapter can be swapped for a Google
Embedding provider without touching chunking or indexing logic.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ...embedder.jina import JinaEmbeddingsService
from ...connectors.jina import JinaConnector
from ..interfaces.base import IEmbeddingProvider

logger = logging.getLogger(__name__)


class JinaEmbeddingProvider(IEmbeddingProvider):
    """IEmbeddingProvider backed by Jina Embeddings v3."""

    def __init__(self, connection: JinaConnector, config: dict[str, Any]):
        """
        Purpose:
            Initializes the provider with a Jina connector and embedding config.

        Args:
            connection (JinaConnector): Existing JinaConnector instance.
            config (dict): model, dimensions, tasks, batch_size,
                max_retries, base_backoff.
        """
        self._connection = connection
        self._service = JinaEmbeddingsService(connection, config)
        self._dimensions = int(config["dimensions"])

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """
        Purpose:
            Embeds a batch of passages via the existing Jina service.

        Returns:
            list[list[float]]: Embedding vectors, one per input text.
        """
        if not texts:
            return []
        embeddings = await self._service.embed_passages(texts)
        logger.info("Generated %d embeddings (model dim=%d)", len(embeddings), self._dimensions)
        return embeddings

    def embed_query(self, query: str) -> list[float]:
        """
        Purpose:
            Embeds a single query (sync wrapper over the async service).

        Returns:
            list[float]: The query embedding vector.
        """
        return asyncio.run(self._service.embed_query(query))

    def dimensions(self) -> int:
        """Return the configured embedding vector dimension."""
        return self._dimensions
