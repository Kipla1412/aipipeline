"""Vital signs model — for backward compatibility only.

Prefer Observation for all measurable clinical findings including vitals.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Vitals(BaseModel):
    blood_pressure: str | None = Field(None)
    heart_rate: str | None = Field(None)
    temperature: str | None = Field(None)
    weight: str | None = Field(None)
    height: str | None = Field(None)
    bmi: str | None = Field(None)
    respiratory_rate: str | None = Field(None)
    oxygen_saturation: str | None = Field(None)
