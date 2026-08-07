"""Procedure domain model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Procedure(BaseModel):
    procedure_name: str = Field(description="Procedure name or description")
    performer: str | None = Field(None, description="Clinician who performed the procedure")
    date: str | None = Field(None, description="Procedure date in YYYY-MM-DD")
    notes: str | None = Field(None, description="Additional notes about the procedure")
