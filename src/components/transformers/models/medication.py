"""Medication domain model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Medication(BaseModel):
    medication_name: str = Field(description="Drug name")
    dosage: str | None = Field(None, description="Dose amount, e.g. '500 mg'")
    frequency: str | None = Field(None, description="Dosing frequency, e.g. 'twice daily'")
    duration: str | None = Field(None, description="Treatment duration, e.g. '10 days'")
    route: str | None = Field(None, description="Route of administration, e.g. 'oral', 'IV'")
    strength: str | None = Field(None, description="Drug strength")
    instructions: str | None = Field(None, description="Special instructions")
