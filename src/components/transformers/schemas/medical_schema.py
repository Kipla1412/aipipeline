from pydantic import BaseModel, Field
from typing import List, Optional


class Vitals(BaseModel):
    blood_pressure: Optional[str] = Field(None)
    heart_rate: Optional[str] = Field(None)
    temperature: Optional[str] = Field(None)
    weight: Optional[str] = Field(None)
    height: Optional[str] = Field(None)
    bmi: Optional[str] = Field(None)


class Section(BaseModel):
    heading: str = Field(description="Section heading")
    content: str = Field(description="Section body text")


class ImagingStudy(BaseModel):
    """DICOM imaging study metadata. Null for non-imaging documents."""
    modality: Optional[str] = Field(None)
    body_part: Optional[str] = Field(None)
    study_uid: Optional[str] = Field(None)
    series_uid: Optional[str] = Field(None)
    sop_instance_uid: Optional[str] = Field(None)
    series_description: Optional[str] = Field(None)
    slice_thickness: Optional[float] = Field(None)
    pixel_spacing: Optional[str] = Field(None, description="Pixel spacing as '[row, col]' string")
    rows: Optional[int] = Field(None)
    columns: Optional[int] = Field(None)
    manufacturer: Optional[str] = Field(None)
    model_name: Optional[str] = Field(None)
    acquisition_date: Optional[str] = Field(None)
    window_center: Optional[float] = Field(None)
    window_width: Optional[float] = Field(None)
    patient_position: Optional[str] = Field(None)
    institution_name: Optional[str] = Field(None)


class MedicalSchema(BaseModel):
    document_id: Optional[str] = Field(None, description="Pipeline-assigned unique document ID")
    report_type: Optional[str] = Field(None, description="Pipeline-assigned report classification")
    source_type: str = Field(default="pdf", description="Source format: pdf, dicom")
    patient_name: str = Field(description="Full patient name")
    patient_id: Optional[str] = Field(None)
    doctor_name: Optional[str] = Field(None)
    diagnoses: List[str] = Field(default_factory=list)
    medications: List[str] = Field(default_factory=list)
    procedures: List[str] = Field(default_factory=list)
    hospital: Optional[str] = Field(None)
    report_date: Optional[str] = Field(None)
    vitals: Optional[Vitals] = Field(None)
    summary: str = Field(description="2-3 sentence clinical summary")
    sections: Optional[List[Section]] = Field(None, description="Dynamic document sections")
    imaging: Optional[ImagingStudy] = Field(None, description="Imaging study metadata (DICOM only)")


class MedicalTransformerConfig(BaseModel):
    model_name: str = Field(default="gpt-4o-mini")
    api_key: str = Field(...)
    base_url: str | None = Field(default=None)
