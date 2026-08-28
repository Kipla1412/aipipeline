"""Indexing layer — document-chat chunking, embedding, and vector search.

Pipeline:
    Clinical JSON
        → ClinicalDocumentChunker (semantic chunks)
        → IEmbeddingProvider (JinaEmbeddingProvider wraps the existing Jina service)
        → IChunkRepository (OpenSearchRepository wraps the existing connector)
        → idempotent upsert

Kept fully separate from FHIR persistence. FHIR mapping runs only after
human approval; indexing runs whenever Clinical JSON is available.
"""

import logging

from .chunker import ClinicalDocumentChunker
from .embeddings.jina import JinaEmbeddingProvider
from .factory import IndexingFactory
from .indexer import ClinicalDocumentIndexer
from .interfaces.base import IChunkRepository, IEmbeddingProvider
from .repository.opensearch import OpenSearchRepository
from .schemas.chunk import ChunkingConfig, ChunkMetadata, ClinicalChunk

__all__ = [
    "ClinicalDocumentChunker",
    "ClinicalDocumentIndexer",
    "IndexingFactory",
    "JinaEmbeddingProvider",
    "OpenSearchRepository",
    "IChunkRepository",
    "IEmbeddingProvider",
    "ChunkingConfig",
    "ChunkMetadata",
    "ClinicalChunk",
]

logging.getLogger(__name__).addHandler(logging.NullHandler())
