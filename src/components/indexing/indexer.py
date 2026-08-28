"""ClinicalDocumentIndexer — orchestration of chunk → embed → index.

Flow:
    Clinical JSON
        → ClinicalDocumentChunker (structure-aware chunks)
        → IEmbeddingProvider (existing Jina service)
        → IChunkRepository (existing OpenSearch connector)
        → idempotent upsert

Each responsibility stays separate: chunking, embedding, and indexing
are independent and failures are raised (never swallowed) with clear
stage attribution.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .chunker import ClinicalDocumentChunker
from .interfaces.base import IChunkRepository
from .interfaces.base import IEmbeddingProvider
from .schemas.chunk import ClinicalChunk

logger = logging.getLogger(__name__)


class ClinicalDocumentIndexer:
    """Indexes a Clinical Domain Model JSON document for document chat."""

    def __init__(
        self,
        chunker: ClinicalDocumentChunker,
        embedder: IEmbeddingProvider,
        repository: IChunkRepository,
        batch_size: int = 50,
    ):
        """
        Purpose:
            Initializes the indexer with its three collaborators.

        Args:
            chunker (ClinicalDocumentChunker): Structure-aware chunker.
            embedder (IEmbeddingProvider): Embedding provider (Jina adapter).
            repository (IChunkRepository): Vector repository (OpenSearch).
            batch_size (int): Embedding/indexing batch size.
        """
        self._chunker = chunker
        self._embedder = embedder
        self._repository = repository
        self._batch_size = batch_size

    async def index(self, document: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Purpose:
            Chunks, embeds, and upserts a clinical document.

        Args:
            document (dict): Clinical Domain Model JSON.
            metadata (dict): patient_id, file_id, source_file, report_type, ...

        Returns:
            dict: Summary — file_id, chunks, embeddings, indexed, duration_ms.
        """
        started = time.monotonic()
        file_id = metadata.get("file_id") or metadata.get("filenest_file_id")
        source_file = metadata.get("source_file")
        logger.info("Indexing document: file_id=%s source=%s", file_id, source_file)

        # 1. Chunk
        chunks: list[ClinicalChunk] = self._chunker.chunk(document, metadata)
        logger.info("Created %d chunk(s) for file_id=%s", len(chunks), file_id)
        if not chunks:
            logger.warning("No chunks produced for file_id=%s — nothing to index", file_id)
            return {
                "file_id": file_id,
                "chunks": 0,
                "embeddings": 0,
                "indexed": 0,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }

        # 2. Embed (batched)
        texts = [c.text for c in chunks]
        try:
            embeddings = await self._embedder.embed_passages(texts)
        except Exception:
            logger.exception("Embedding failed for file_id=%s (after %d chunks)", file_id, len(chunks))
            raise

        # 3. Upsert
        try:
            indexed = self._repository.upsert_chunks(chunks, embeddings)
        except Exception:
            logger.exception("OpenSearch indexing failed for file_id=%s", file_id)
            raise

        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "Indexed file_id=%s: %d chunks, %d embeddings, %d indexed in %d ms",
            file_id,
            len(chunks),
            len(embeddings),
            indexed,
            duration_ms,
        )
        return {
            "file_id": file_id,
            "chunks": len(chunks),
            "embeddings": len(embeddings),
            "indexed": indexed,
            "duration_ms": duration_ms,
        }

    def close(self) -> None:
        """
        Purpose:
            Releases the underlying embedding connection (best-effort).

        Returns:
            None
        """
        connector = getattr(self._embedder, "_connection", None)
        closer = getattr(connector, "close", None)
        if closer is None:
            return
        try:
            result = closer()
            if hasattr(result, "__await__"):
                asyncio.run(result)
        except Exception:
            logger.warning("Failed to close embedding connection", exc_info=True)
