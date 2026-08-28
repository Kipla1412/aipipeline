"""Indexing interfaces package — re-exports the ABCs."""

from .base import IChunkRepository, IEmbeddingProvider

__all__ = ["IChunkRepository", "IEmbeddingProvider"]
