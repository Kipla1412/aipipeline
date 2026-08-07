"""Imaging study domain model — DICOM metadata for imaging documents."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImagingStudy(BaseModel):
    modality: str | None = Field(None, description="Imaging modality: CT, MRI, XR, US, etc.")
    body_part: str | None = Field(None, description="Body part examined")
    study_uid: str | None = Field(None)
    series_uid: str | None = Field(None)
    sop_instance_uid: str | None = Field(None)
    series_description: str | None = Field(None)
    slice_thickness: float | None = Field(None)
    pixel_spacing: str | None = Field(None, description="Pixel spacing as '[row, col]' string")
    rows: int | None = Field(None)
    columns: int | None = Field(None)
    manufacturer: str | None = Field(None)
    model_name: str | None = Field(None)
    acquisition_date: str | None = Field(None)
    window_center: float | None = Field(None)
    window_width: float | None = Field(None)
    patient_position: str | None = Field(None)
    institution_name: str | None = Field(None)
