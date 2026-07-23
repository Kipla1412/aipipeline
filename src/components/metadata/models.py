"""Metadata models — lean index entries and query types."""

from __future__ import annotations
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field


class EntityType(StrEnum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    HOSPITAL = "hospital"
    DISEASE = "disease"
    MEDICATION = "medication"
    PROCEDURE = "procedure"
    REPORT = "report"


class MetadataEntry(BaseModel):
    id: str
    label: str
    entity_type: EntityType
    slug: str = Field(default="")
    source_file: str | None = Field(None)
    references: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchQuery(BaseModel):
    query: str = Field(min_length=1)
    entity_type: EntityType | None = Field(None)
    limit: int = Field(default=10, ge=1, le=100)


class SearchResult(BaseModel):
    entry: MetadataEntry
    score: float = Field(default=1.0, ge=0.0, le=1.0)


class ContextEntity(BaseModel):
    entry: MetadataEntry
    wiki_content: str = Field("")
    neighbors: list[MetadataEntry] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    question: str
    answer: str
    context_entities: list[ContextEntity] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
