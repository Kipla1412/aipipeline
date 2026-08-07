"""Diagnosis domain model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Diagnosis(BaseModel):
    name: str = Field(description="Diagnosis name or condition")
    clinical_status: str | None = Field(None, description="active | resolved | chronic | inactive | recurrence")
    severity: str | None = Field(None, description="mild | moderate | severe | critical | stage I-IV")
    onset_date: str | None = Field(None, description="Date of onset in YYYY-MM-DD")
    notes: str | None = Field(None, description="Additional clinical notes")
