"""Indexing factory — pure composition point for chunker + embedder + repository.

Builds the ClinicalDocumentIndexer from PipelineConfig-style dicts using
the existing ConnectorFactory for Jina and OpenSearch. Contains no
business logic — only wiring.
"""

from __future__ import annotations

import logging
from typing import Any

from ..connectors.factory import ConnectorFactory
from ..utils.config import PipelineConfig
from .chunker import ClinicalDocumentChunker
from .embeddings.jina import JinaEmbeddingProvider
from .indexer import ClinicalDocumentIndexer
from .repository.opensearch import OpenSearchRepository

logger = logging.getLogger(__name__)


class IndexingFactory:
    """Creates a fully-wired ClinicalDocumentIndexer from config."""

    @classmethod
    def create_indexer(cls, config: PipelineConfig | None = None) -> ClinicalDocumentIndexer:
        """
        Purpose:
            Wires the chunker, embedding provider, and OpenSearch repository
            from a PipelineConfig instance.

        Args:
            config (PipelineConfig | None): Config; defaults to PipelineConfig().

        Returns:
            ClinicalDocumentIndexer: Ready-to-use indexer.

        Raises:
            ValueError: If indexing is not configured (missing Jina/OpenSearch creds).
        """
        cfg = config or PipelineConfig()
        if not cfg.indexing_enabled:
            raise ValueError(
                "Indexing not configured — set JINA_API_KEY and OPENSEARCH_* in .env"
            )

        chunker = ClinicalDocumentChunker(cfg.get_chunking_config())

        jina_config = cfg.get_jina_config()
        jina_connector = ConnectorFactory.get_connector("jina", jina_config)
        embedder = JinaEmbeddingProvider(jina_connector, cfg.get_embedding_config())

        os_config = cfg.get_opensearch_config()
        os_config["dimensions"] = cfg.JINA_DIMENSIONS
        os_config["batch_size"] = cfg.INDEXING_BATCH_SIZE
        os_connector = ConnectorFactory.get_connector("opensearch", os_config)
        repository = OpenSearchRepository(os_connector, os_config)

        return ClinicalDocumentIndexer(
            chunker=chunker,
            embedder=embedder,
            repository=repository,
            batch_size=cfg.INDEXING_BATCH_SIZE,
        )
