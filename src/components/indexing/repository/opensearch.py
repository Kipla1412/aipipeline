"""OpenSearchRepository — vector persistence for clinical chunks.

Uses the existing OpensearchConnector for the client and the existing
OpensearchBulkIngestor for index creation + bulk upsert. Chunks are
indexed idempotently: deterministic chunk_ids are used as document ids,
so re-indexing the same Clinical JSON upserts instead of duplicating.

patient_id and file_id are stored as top-level keyword fields (not only
inside the embedding text) so retrieval can filter before vector search.
"""

from __future__ import annotations

import logging
from typing import Any

from opensearchpy import OpenSearch

from ...connectors.opensearch import OpensearchConnector
from ..interfaces.base import IChunkRepository
from ..schemas.chunk import ClinicalChunk

logger = logging.getLogger(__name__)


class OpenSearchRepository(IChunkRepository):
    """IChunkRepository backed by OpenSearch kNN."""

    def __init__(self, connector: OpensearchConnector, config: dict[str, Any]):
        """
        Purpose:
            Initializes the repository with an existing OpenSearch connector.

        Args:
            connector (OpensearchConnector): Existing connector instance.
            config (dict): index_name, dimensions, batch_size.
        """
        self._connector = connector
        self._client: OpenSearch = connector()
        self._index_name = config.get("index_name", "clinical_documents")
        self._dimensions = int(config.get("dimensions", 1024))
        self._batch_size = int(config.get("batch_size", 50))

    # ------------------------------------------------------------------
    # IChunkRepository
    # ------------------------------------------------------------------
    def ensure_index(self) -> None:
        """
        Purpose:
            Creates the index with kNN mapping if it does not exist.

        Returns:
            None
        """
        if self._client.indices.exists(index=self._index_name):
            return
        body = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "index": {
                    "knn": True,
                },
            },
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "chunk_type": {"type": "keyword"},
                    "text": {"type": "text"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": self._dimensions,
                        "method": {
                            "name": "hnsw",
                            "space_type": "l2",
                            "engine": "lucene",
                            "parameters": {
                                "ef_construction": 128,
                                "m": 16,
                            },
                        },
                    },
                    "patient_id": {"type": "keyword"},
                    "file_id": {"type": "keyword"},
                    "source_file": {"type": "keyword"},
                    "report_type": {"type": "keyword"},
                    "encounter_id": {"type": "keyword"},
                    "service_request_id": {"type": "keyword"},
                }
            },
        }
        self._client.indices.create(index=self._index_name, body=body)
        logger.info("Created OpenSearch index '%s' (dim=%d)", self._index_name, self._dimensions)

    def upsert_chunks(self, chunks: list[ClinicalChunk], embeddings: list[list[float]]) -> int:
        """
        Purpose:
            Idempotently upserts chunks with their embeddings via bulk.

        Args:
            chunks (list[ClinicalChunk]): Chunks to index.
            embeddings (list[list[float]]): One embedding per chunk.

        Returns:
            int: Number of documents indexed/upserted.

        Raises:
            RuntimeError: If bulk indexing fails.
        """
        if not chunks:
            return 0
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunk/embedding count mismatch: {len(chunks)} chunks, {len(embeddings)} embeddings"
            )

        self.ensure_index()
        actions = []
        for chunk, emb in zip(chunks, embeddings):
            actions.append(
                {
                    "_op_type": "index",
                    "_index": self._index_name,
                    "_id": chunk.chunk_id,
                    "_source": self._to_doc(chunk, emb),
                }
            )

        try:
            from opensearchpy import helpers

            success, failed = helpers.bulk(
                self._client, actions, stats_only=False, refresh=True
            )
            if failed:
                sample = failed[0] if isinstance(failed, list) else failed
                logger.error("Bulk upsert failures: %s", sample)
                raise RuntimeError(f"OpenSearch bulk upsert failed: {failed}")
            logger.info("Upserted %d chunk(s) into '%s'", success, self._index_name)
            return success
        except Exception as e:
            logger.exception("OpenSearch bulk upsert failed")
            raise

    def search(
        self,
        query_embedding: list[float],
        patient_id: str | None = None,
        file_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Purpose:
            kNN vector search filtered by patient_id AND file_id when provided.

        Args:
            query_embedding (list[float]): Query vector.
            patient_id (str | None): Filter — exact match on patient_id.
            file_id (str | None): Filter — exact match on file_id.
            top_k (int): Number of results.

        Returns:
            list[dict]: Matching chunk documents (excluding the embedding vector).
        """
        filters: list[dict[str, Any]] = []
        if patient_id:
            filters.append({"term": {"patient_id": patient_id}})
        if file_id:
            filters.append({"term": {"file_id": file_id}})

        query: dict[str, Any] = {"knn": {"embedding": {"vector": query_embedding, "k": top_k}}}
        if filters:
            query = {
                "bool": {
                    "must": [{"knn": {"embedding": {"vector": query_embedding, "k": top_k}}}],
                    "filter": filters,
                }
            }

        resp = self._client.search(index=self._index_name, body={"query": query, "size": top_k})
        results = []
        for hit in resp.get("hits", {}).get("hits", []):
            source = dict(hit.get("_source", {}))
            source.pop("embedding", None)
            results.append(source)
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_doc(chunk: ClinicalChunk, embedding: list[float]) -> dict[str, Any]:
        """Flatten a ClinicalChunk + embedding into an OpenSearch document."""
        return {
            "chunk_id": chunk.chunk_id,
            "chunk_type": chunk.chunk_type,
            "text": chunk.text,
            "embedding": embedding,
            "patient_id": chunk.metadata.patient_id,
            "file_id": chunk.metadata.file_id,
            "source_file": chunk.metadata.source_file,
            "report_type": chunk.metadata.report_type,
            "encounter_id": chunk.metadata.encounter_id,
            "service_request_id": chunk.metadata.service_request_id,
        }
