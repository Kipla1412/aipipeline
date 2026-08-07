"""MedicalSchema — root aggregation of all clinical domain models.

Uses structured Pydantic models (Diagnosis, Medication, Procedure, Observation)
instead of flat List[str] fields. A serializer layer converts back to flat dict
for backward compatibility with wiki, graph, and metadata consumers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..models.diagnosis import Diagnosis
from ..models.medication import Medication
from ..models.procedure import Procedure
from ..models.observation import Observation
from ..models.imaging import ImagingStudy
from ..models.section import Section
from ..models.vitals import Vitals


class MedicalSchema(BaseModel):
    document_id: str | None = Field(None, description="Pipeline-assigned unique document ID")
    report_type: str | None = Field(None, description="Pipeline-assigned report classification")
    source_type: str = Field(default="pdf", description="Source format: pdf, dicom")

    patient_name: str = Field(description="Full patient name")
    patient_id: str | None = Field(None, description="Patient ID, MRN, or hospital number")
    doctor_name: str | None = Field(None, description="Treating physician or author")
    hospital: str | None = Field(None, description="Hospital, clinic, or facility name")
    report_date: str | None = Field(None, description="Report date in YYYY-MM-DD")

    diagnoses: list[Diagnosis] = Field(default_factory=list, description="Structured diagnoses")
    medications: list[Medication] = Field(default_factory=list, description="Structured medications")
    procedures: list[Procedure] = Field(default_factory=list, description="Structured procedures")
    observations: list[Observation] = Field(
        default_factory=list,
        description="All measurable clinical findings (vitals, labs, ECG, imaging metrics)",
    )

    vitals: Vitals | None = Field(None, description="Deprecated — use observations instead")
    imaging: ImagingStudy | None = Field(None, description="DICOM imaging study metadata")

    summary: str = Field(description="2-4 sentence clinical summary")
    sections: list[Section] | None = Field(None, description="Document section layout")


class MedicalTransformerConfig(BaseModel):
    model_name: str = Field(default="gpt-4o-mini")
    api_key: str = Field(...)
    base_url: str | None = Field(default=None)
