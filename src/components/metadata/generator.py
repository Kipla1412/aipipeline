"""MetadataGenerator — produces MetadataEntry objects from structured MedicalDocument."""

import hashlib
import logging
import re
from typing import Any
from .models import MetadataEntry, EntityType

logger = logging.getLogger(__name__)

_REPORT_TYPE_DIR: dict[str, str] = {
    "mri": "MRI", "ct": "CT", "xray": "X-Ray", "ultrasound": "Ultrasound",
    "ecg": "ECG", "blood_report": "Blood", "lab_report": "LabReports",
    "prescription": "Prescription", "discharge_summary": "DischargeSummary",
    "consultation": "Consultation", "operative_report": "OperativeReports",
    "histopathology": "Pathology", "microbiology": "Microbiology", "other": "Other",
}


class MetadataGenerator:
    def __init__(self):
        self._entries: list[MetadataEntry] = []

    def generate(self, document: dict[str, Any]) -> list[MetadataEntry]:
        self._entries.clear()
        patient_name = document.get("patient_name")
        patient_id = document.get("patient_id")
        doctor_name = document.get("doctor_name")
        hospital_name = document.get("hospital")
        diagnoses: list[str] = document.get("diagnoses", [])
        medications: list[str] = document.get("medications", [])
        procedures: list[str] = document.get("procedures", [])
        report_date = document.get("report_date")
        report_type = document.get("report_type", "")
        patient_slug = self._slugify(patient_name or "unknown")
        all_refs = diagnoses + medications + procedures + [doctor_name] if doctor_name else [] + [hospital_name] if hospital_name else []

        if patient_name:
            self._entries.append(MetadataEntry(
                id=self._make_id(EntityType.PATIENT, patient_name), label=patient_name,
                entity_type=EntityType.PATIENT, slug=patient_slug,
                source_file=f"Patients/{patient_slug}/patient.md", references=all_refs,
                metadata={"patient_id": patient_id} if patient_id else {}))

        for diag in diagnoses:
            self._entries.append(MetadataEntry(id=self._make_id(EntityType.DISEASE, diag), label=diag,
                entity_type=EntityType.DISEASE, slug=self._slugify(diag),
                source_file=f"Diseases/{self._slugify(diag)}.md"))

        if medications and patient_name:
            self._entries.append(MetadataEntry(id=self._make_id(EntityType.MEDICATION, patient_name), label=patient_name,
                entity_type=EntityType.MEDICATION, slug=patient_slug,
                source_file=f"Medications/{patient_slug}.md", references=[patient_name]))

        for proc in procedures:
            self._entries.append(MetadataEntry(id=self._make_id(EntityType.PROCEDURE, proc), label=proc,
                entity_type=EntityType.PROCEDURE, slug=self._slugify(proc),
                source_file=f"Procedures/{self._slugify(proc)}.md"))

        if doctor_name:
            self._entries.append(MetadataEntry(id=self._make_id(EntityType.DOCTOR, doctor_name), label=doctor_name,
                entity_type=EntityType.DOCTOR, slug=self._slugify(doctor_name),
                source_file=f"Doctors/{self._slugify(doctor_name)}.md",
                references=[patient_name] if patient_name else [],
                metadata={"hospital": hospital_name} if hospital_name else {}))

        if hospital_name:
            refs = [doctor_name] if doctor_name else []
            if patient_name:
                refs.append(patient_name)
            self._entries.append(MetadataEntry(id=self._make_id(EntityType.HOSPITAL, hospital_name), label=hospital_name,
                entity_type=EntityType.HOSPITAL, slug=self._slugify(hospital_name),
                source_file=f"Hospitals/{self._slugify(hospital_name)}.md", references=refs))

        doc_id = document.get("document_id", "")
        report_file_name = doc_id.rsplit(":", 1)[0] if ":" in doc_id else doc_id
        report_slug = self._slugify(report_file_name or patient_name or "unknown")
        report_dir = _REPORT_TYPE_DIR.get(report_type.lower(), "Other") if report_type else "Other"
        self._entries.append(MetadataEntry(
            id=self._make_id(EntityType.REPORT, report_slug),
            label=report_file_name or (patient_name or "Unknown"), entity_type=EntityType.REPORT,
            slug=report_slug, source_file=f"Patients/{patient_slug}/Reports/{report_dir}/{report_slug}.md",
            metadata={"report_date": report_date or "", "patient": patient_name or "", "report_type": report_type}))

        return list(self._entries)

    @staticmethod
    def _make_id(entity_type: EntityType, label: str) -> str:
        return hashlib.sha256(f"{entity_type.value}:{label.lower().strip()}".encode()).hexdigest()[:16]

    @staticmethod
    def _slugify(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")
