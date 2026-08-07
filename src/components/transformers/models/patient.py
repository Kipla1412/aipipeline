"""Patient domain model — demographic information only. No clinical data."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Patient(BaseModel):
    patient_name: str = Field(description="Full patient name")
    patient_id: str | None = Field(None, description="Patient ID, MRN, or hospital number")
    gender: str | None = Field(None, description="Patient gender")
    age: int | None = Field(None, description="Patient age in years")
    date_of_birth: str | None = Field(None, description="Date of birth in YYYY-MM-DD")
