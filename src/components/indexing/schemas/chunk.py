"""Clinical chunk schema — the unit of indexing for document chat.

A chunk is a semantic piece of a Clinical Domain Model JSON document:
one observation, one diagnosis, one medication, one procedure, the
document summary, imaging metadata, or a section. Chunks are embedded
and stored in OpenSearch with structured, filterable metadata.

The metadata is kept separate from the embedding text so retrieval can
filter by patient_id AND file_id before vector search.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    """Structured metadata attached to every chunk (kept out of embedding text)."""

    patient_id: str | None = Field(None, description="Patient ID / MRN")
    file_id: str | None = Field(None, description="Unique external file id (filenest_file_id)")
    source_file: str | None = Field(None, description="Original filename")
    report_type: str | None = Field(None, description="Document classification, e.g. lab_report")
    encounter_id: str | None = Field(None, description="Encounter identifier when present")
    service_request_id: str | None = Field(None, description="Service request identifier when present")


class ClinicalChunk(BaseModel):
    """A single embeddable unit of clinical text with structured metadata."""

    chunk_id: str = Field(description="Deterministic id: sha256(file_id + chunk_type + stable identifier)")
    chunk_type: str = Field(description="summary | diagnosis | observation | medication | procedure | imaging | section")
    text: str = Field(description="Clean, human-readable clinical text for embedding")
    metadata: ChunkMetadata = Field(description="Structured, filterable metadata (not part of embedding text)")


class ChunkingConfig(BaseModel):
    """Configuration for the ClinicalDocumentChunker."""

    max_chars: int = Field(default=1500, gt=0, description="Hard cap for a single chunk; longer sections are split")
    overlap_chars: int = Field(default=150, ge=0, description="Character overlap between sub-chunks when splitting")
