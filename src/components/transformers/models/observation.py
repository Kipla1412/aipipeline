"""Observation domain model — unified model for all measurable clinical findings.

Vital signs, lab results, ECG measurements, imaging findings, pathology metrics
all use this single model. Designed for future LOINC/code mapping.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BloodPressure(BaseModel):
    systolic: float | None = Field(None, description="Systolic pressure in mmHg")
    diastolic: float | None = Field(None, description="Diastolic pressure in mmHg")


class Observation(BaseModel):
    observation_id: str | None = Field(None, description="Unique observation identifier")
    category: str = Field(
        description="vital_signs | laboratory | imaging | ecg | pathology | microbiology"
    )
    code: str | None = Field(None, description="Terminology code, e.g. LOINC 718-7")
    display_name: str = Field(description="Human-readable name, e.g. 'Hemoglobin'")
    value: int | float | str | None = Field(None, description="Measured value (numeric preferred)")
    value_type: str | None = Field(None, description="quantitative | qualitative | ordinal")
    unit: str | None = Field(None, description="Unit of measure, e.g. 'g/dL', 'mmHg'")
    reference_range: str | None = Field(None, description="Normal reference range")
    interpretation: str | None = Field(
        None, description="low | normal | high | abnormal | critical"
    )
    body_site: str | None = Field(None, description="Body site where measurement was taken")
    method: str | None = Field(None, description="Method of measurement")
    effective_datetime: str | None = Field(None, description="Date/time of observation")
    blood_pressure: BloodPressure | None = Field(
        None, description="Decomposed BP — populated only for Blood Pressure observations"
    )
