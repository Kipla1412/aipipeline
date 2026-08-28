"""Unit tests for ClinicalDocumentIndexer orchestration (mock-based, no creds).

Verifies chunk → embed → upsert sequencing, count reporting, and that
failures propagate (never silently swallowed).
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.components.indexing.chunker import ClinicalDocumentChunker
from src.components.indexing.indexer import ClinicalDocumentIndexer


@pytest.fixture
def sample_document() -> dict:
    return {
        "summary": "Hypertension follow-up.",
        "diagnoses": [{"name": "Essential Hypertension"}],
        "observations": [
            {"display_name": "Heart Rate", "category": "vital_signs", "value": 78, "unit": "bpm"}
        ],
        "medications": [],
        "procedures": [],
        "imaging": None,
        "sections": None,
    }


def test_index_full_flow(sample_document):
    """Chunker → embedder → repository are called in order and counts returned."""
    embedder = AsyncMock()
    embedder.embed_passages.return_value = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]

    repo = MagicMock()
    repo.upsert_chunks.return_value = 3

    indexer = ClinicalDocumentIndexer(
        chunker=ClinicalDocumentChunker(),
        embedder=embedder,
        repository=repo,
    )
    result = asyncio.run(indexer.index(
        sample_document,
        {"patient_id": "10001", "file_id": "ABC123", "source_file": "r.pdf", "report_type": "lab"},
    ))

    assert result["chunks"] == 3
    assert result["embeddings"] == 3
    assert result["indexed"] == 3
    assert result["file_id"] == "ABC123"
    assert "duration_ms" in result
    embedder.embed_passages.assert_called_once()
    repo.upsert_chunks.assert_called_once()


def test_index_empty_document_no_embedding():
    """A document with no chunks never calls embedder or repository."""
    doc = {"summary": None, "diagnoses": [], "observations": [], "medications": [], "procedures": [], "imaging": None, "sections": None}
    embedder = AsyncMock()
    repo = MagicMock()
    indexer = ClinicalDocumentIndexer(
        chunker=ClinicalDocumentChunker(),
        embedder=embedder,
        repository=repo,
    )
    result = asyncio.run(indexer.index(doc, {"file_id": "F1", "patient_id": "P1"}))
    assert result["chunks"] == 0
    assert result["indexed"] == 0
    embedder.embed_passages.assert_not_called()
    repo.upsert_chunks.assert_not_called()


def test_embedding_failure_propagates(sample_document):
    """Embedding exceptions are re-raised with the stage attributed."""
    embedder = AsyncMock()
    embedder.embed_passages.side_effect = RuntimeError("Jina down")
    repo = MagicMock()
    indexer = ClinicalDocumentIndexer(
        chunker=ClinicalDocumentChunker(),
        embedder=embedder,
        repository=repo,
    )
    with pytest.raises(RuntimeError, match="Jina down"):
        asyncio.run(indexer.index(sample_document, {"file_id": "F2", "patient_id": "P2"}))
    repo.upsert_chunks.assert_not_called()


def test_indexing_failure_propagates(sample_document):
    """OpenSearch failures are re-raised, not swallowed."""
    embedder = AsyncMock()
    embedder.embed_passages.return_value = [[0.1]] * 3
    repo = MagicMock()
    repo.upsert_chunks.side_effect = RuntimeError("OS unreachable")
    indexer = ClinicalDocumentIndexer(
        chunker=ClinicalDocumentChunker(),
        embedder=embedder,
        repository=repo,
    )
    with pytest.raises(RuntimeError, match="OS unreachable"):
        asyncio.run(indexer.index(sample_document, {"file_id": "F3", "patient_id": "P3"}))
